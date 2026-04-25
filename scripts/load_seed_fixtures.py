"""Load committed seed fixtures into Postgres.

Idempotent — TRUNCATEs the user-data tables (rfps, screenings, drafts,
draft_jobs, audit_log) and reinserts from ``sample_data/seed/*.json``.
Past-proposal data (past_proposals + proposal_chunks) is preserved if
it's already populated; if empty, seed_data.sh kicks the indexer first.

Pure JSON load: no LLM calls, no embedding API calls. Runs in seconds.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from services.api import _env  # noqa: F401
from services.api.db.client import db_cursor


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "sample_data" / "seed"


def _parse_iso(value: Any):
    """Convert ISO-string fields back to datetime/date for psycopg2."""
    if value is None or not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return value


def _truncate_user_tables() -> None:
    with db_cursor() as cur:
        cur.execute("""
            TRUNCATE TABLE
                draft_jobs, drafts, screenings, rfps,
                audit_log
            RESTART IDENTITY CASCADE
        """)


def _insert_rfps(rfps: List[Dict[str, Any]]) -> None:
    with db_cursor() as cur:
        for r in rfps:
            cur.execute(
                """
                INSERT INTO rfps
                    (id, source_type, source_adapter_version, source_metadata,
                     external_id, title, agency, naics_codes,
                     due_date, value_estimate_low, value_estimate_high,
                     full_text, source_url, received_at, status, dedupe_hash)
                VALUES
                    (%s, %s, %s, %s::jsonb,
                     %s, %s, %s, %s,
                     %s, %s, %s,
                     %s, %s, %s, %s, %s)
                """,
                (
                    r["id"], r["source_type"], r.get("source_adapter_version"),
                    json.dumps(r.get("source_metadata") or {}),
                    r.get("external_id"), r["title"], r.get("agency"),
                    r.get("naics_codes") or [],
                    _parse_iso(r.get("due_date")),
                    r.get("value_estimate_low"), r.get("value_estimate_high"),
                    r.get("full_text"), r.get("source_url"),
                    _parse_iso(r.get("received_at")) or datetime.utcnow(),
                    r.get("status") or "new",
                    r.get("dedupe_hash"),
                ),
            )


def _insert_screenings(screenings: List[Dict[str, Any]]) -> None:
    with db_cursor() as cur:
        for s in screenings:
            cur.execute(
                """
                INSERT INTO screenings
                    (id, rfp_id, fit_score, recommendation, rationale,
                     effort_estimate, deal_breakers, open_questions,
                     similar_proposal_ids, model_version, rubric_version,
                     created_at, human_override, human_override_reason)
                VALUES
                    (%s, %s, %s, %s, %s::jsonb,
                     %s, %s::jsonb, %s::jsonb,
                     %s::uuid[], %s, %s,
                     %s, %s, %s)
                """,
                (
                    s["id"], s["rfp_id"], s.get("fit_score"), s.get("recommendation"),
                    json.dumps(s.get("rationale") or {}),
                    s.get("effort_estimate"),
                    json.dumps(s.get("deal_breakers") or []),
                    json.dumps(s.get("open_questions") or []),
                    s.get("similar_proposal_ids") or [],
                    s.get("model_version"), s.get("rubric_version"),
                    _parse_iso(s.get("created_at")) or datetime.utcnow(),
                    s.get("human_override"), s.get("human_override_reason"),
                ),
            )


def _insert_drafts(drafts: List[Dict[str, Any]]) -> None:
    with db_cursor() as cur:
        for d in drafts:
            cur.execute(
                """
                INSERT INTO drafts
                    (id, rfp_id, screening_id, content,
                     retrieved_proposal_ids, status, created_at)
                VALUES
                    (%s, %s, %s, %s::jsonb,
                     %s::uuid[], %s, %s)
                """,
                (
                    d["id"], d["rfp_id"], d.get("screening_id"),
                    json.dumps(d.get("content") or {}),
                    d.get("retrieved_proposal_ids") or [],
                    d.get("status") or "generated",
                    _parse_iso(d.get("created_at")) or datetime.utcnow(),
                ),
            )


def _check_past_proposals() -> int:
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM past_proposals")
        return cur.fetchone()[0]


def main() -> None:
    rfps_path = SEED_DIR / "rfps.json"
    screenings_path = SEED_DIR / "screenings.json"
    drafts_path = SEED_DIR / "drafts.json"

    if not rfps_path.exists():
        raise SystemExit(
            f"Seed fixtures not found at {SEED_DIR}. "
            f"Run scripts/build_seed_fixtures.py first."
        )

    rfps = json.loads(rfps_path.read_text(encoding="utf-8"))
    screenings = json.loads(screenings_path.read_text(encoding="utf-8")) if screenings_path.exists() else []
    drafts = json.loads(drafts_path.read_text(encoding="utf-8")) if drafts_path.exists() else []

    print(f"[seed] truncating user tables ...")
    _truncate_user_tables()

    print(f"[seed] inserting {len(rfps)} RFPs ...")
    _insert_rfps(rfps)
    print(f"[seed] inserting {len(screenings)} screenings ...")
    _insert_screenings(screenings)
    print(f"[seed] inserting {len(drafts)} drafts ...")
    _insert_drafts(drafts)

    pp_count = _check_past_proposals()
    if pp_count == 0:
        print("[seed] WARN: past_proposals is empty. Run "
              "`python -m services.api.rag.indexer` to seed it.")
    else:
        print(f"[seed] past_proposals already populated ({pp_count} proposals); skipping reindex.")

    # Sanity dump
    from collections import Counter
    by_status = Counter(r["status"] for r in rfps)
    by_source = Counter(r["source_type"] for r in rfps)
    print(f"\n[seed] DONE.")
    print(f"  RFPs by status:      {dict(by_status)}")
    print(f"  RFPs by source_type: {dict(by_source)}")
    print(f"  screenings:          {len(screenings)}")
    print(f"  drafts:              {len(drafts)}")
    print(f"  past_proposals:      {pp_count}")


if __name__ == "__main__":
    main()
