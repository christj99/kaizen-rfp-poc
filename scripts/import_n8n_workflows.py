"""Import every n8n workflow JSON under ``services/n8n/workflows/`` via the
n8n public REST API.

Usage::

    # Prereq: set N8N_API_KEY in .env (generate from n8n UI: Settings ->
    # n8n API -> Create an API key)
    ./.venv/Scripts/python.exe scripts/import_n8n_workflows.py

    # Also activate the scheduled ones (discovery_email + completion watcher):
    ./.venv/Scripts/python.exe scripts/import_n8n_workflows.py --activate

    # Re-import: updates existing workflows by name (PUT), creates missing ones.
    # Safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Workflow names contain em-dashes + arrows; the default cp1252 Windows
# console can't encode them. Reconfigure stdout/stderr to UTF-8 early.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except AttributeError:
        pass

# Workflows to flip to active=true when --activate is passed. Test harnesses
# (chain_mode, full_auto_mode, slack_notification) stay inactive by design.
# The ingest sub-workflow MUST be active — its production webhook URL is
# what discovery_email / discovery_sam_gov call for the 📥 ingest card.
DEFAULT_ACTIVE = {
    "Discovery — Email (primary)",
    "Draft completion watcher",
    "Slack ingest notification (sub-workflow)",
}

ALLOWED_TOP_LEVEL_KEYS = {"name", "nodes", "connections", "settings"}
ALLOWED_SETTINGS_KEYS = {"executionOrder"}


def _load_env() -> None:
    """Minimal .env loader so this script stands on its own without importing
    from services.api. Only pulls keys we care about."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        # Don't clobber a real shell-exported value with a placeholder.
        if k and k not in os.environ:
            os.environ[k] = v


def _sanitize(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """Trim the workflow payload to fields n8n's POST /workflows accepts.

    n8n 1.x rejects extras like ``active``/``pinData``/``tags`` on create,
    returning a 400 with a 'unknown field' message. Strip everything except
    the four canonical fields.
    """
    trimmed = {k: v for k, v in workflow.items() if k in ALLOWED_TOP_LEVEL_KEYS}
    settings = trimmed.get("settings") or {}
    trimmed["settings"] = {k: v for k, v in settings.items() if k in ALLOWED_SETTINGS_KEYS}
    # Default to sequential execution if the settings block got stripped clean.
    trimmed["settings"].setdefault("executionOrder", "v1")
    return trimmed


def _list_existing(client: httpx.Client) -> List[Dict[str, Any]]:
    r = client.get("/api/v1/workflows")
    r.raise_for_status()
    payload = r.json()
    # n8n returns {data: [...], nextCursor: ...}
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def _find_by_name(existing: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for wf in existing:
        if wf.get("name") == name:
            return wf
    return None


def _activate(client: httpx.Client, workflow_id: str) -> None:
    r = client.post(f"/api/v1/workflows/{workflow_id}/activate")
    if r.status_code not in (200, 204):
        raise RuntimeError(f"activate failed ({r.status_code}): {r.text[:240]}")


def _deactivate(client: httpx.Client, workflow_id: str) -> None:
    # Required before PUT on an active workflow — n8n refuses updates to
    # running workflows with a 400 ("active workflows cannot be modified").
    r = client.post(f"/api/v1/workflows/{workflow_id}/deactivate")
    if r.status_code not in (200, 204, 400):
        raise RuntimeError(f"deactivate failed ({r.status_code}): {r.text[:240]}")


def import_all(
    workflows_dir: Path,
    *,
    activate: bool,
    api_url: str,
    api_key: str,
) -> int:
    headers = {"X-N8N-API-KEY": api_key, "Accept": "application/json"}
    with httpx.Client(base_url=api_url, headers=headers, timeout=30) as client:
        existing = _list_existing(client)
        print(f"[import] n8n currently has {len(existing)} workflow(s).")

        files = sorted(workflows_dir.glob("*.json"))
        if not files:
            print(f"[import] no JSON files under {workflows_dir}", file=sys.stderr)
            return 1

        created = 0
        updated = 0
        activated: List[str] = []
        for path in files:
            raw = json.loads(path.read_text(encoding="utf-8"))
            name = raw.get("name", path.stem)
            payload = _sanitize(raw)
            match = _find_by_name(existing, name)

            if match:
                # Update in place — deactivate first so n8n lets us PUT.
                wf_id = match["id"]
                if match.get("active"):
                    _deactivate(client, wf_id)
                r = client.put(f"/api/v1/workflows/{wf_id}", json=payload)
                if r.status_code not in (200, 201):
                    raise RuntimeError(
                        f"PUT {wf_id} ({name!r}) failed {r.status_code}: {r.text[:300]}"
                    )
                updated += 1
                print(f"[import] UPDATED  id={wf_id}  {name}")
            else:
                r = client.post("/api/v1/workflows", json=payload)
                if r.status_code not in (200, 201):
                    raise RuntimeError(
                        f"POST ({name!r}) failed {r.status_code}: {r.text[:300]}"
                    )
                wf_id = r.json()["id"]
                created += 1
                print(f"[import] CREATED  id={wf_id}  {name}")

            if activate and name in DEFAULT_ACTIVE:
                try:
                    _activate(client, wf_id)
                    activated.append(name)
                except Exception as exc:
                    print(f"[import] activate {name!r} skipped: {exc}")

        print(f"\n[import] summary: created={created} updated={updated}")
        if activate:
            print(f"[import] activated: {activated or '(none)'}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "services" / "n8n" / "workflows",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="n8n base URL (default: http://localhost:${N8N_PORT:-5678})",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help=f"After import, activate the scheduled workflows ({', '.join(sorted(DEFAULT_ACTIVE))}).",
    )
    args = parser.parse_args(argv)

    _load_env()
    api_key = os.environ.get("N8N_API_KEY", "").strip()
    if not api_key:
        print(
            "N8N_API_KEY not set. Generate one in the n8n UI (Settings -> n8n API) "
            "and add it to .env.",
            file=sys.stderr,
        )
        return 2

    api_url = args.api_url or f"http://localhost:{os.environ.get('N8N_PORT', '5678')}"

    return import_all(
        args.dir,
        activate=args.activate,
        api_url=api_url,
        api_key=api_key,
    )


if __name__ == "__main__":
    sys.exit(main())
