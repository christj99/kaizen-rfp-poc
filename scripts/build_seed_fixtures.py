"""Build the demo seed fixtures from the current DB + hand-crafted synthetic
records.

Run once after a useful demo run; the resulting JSON files are committed
and reused by ``scripts/seed_data.sh`` to rebuild a populated demo state
in seconds.

What it captures from the DB (real email-source RFPs):
- 5 chosen RFPs by id (USDA FNS, VHA, NIH, DOJ Supply Chain, Cherry Hill)
- Their most-recent screening
- Their most-recent draft (if status is in_draft)

Cross-table UUID references (similar_proposal_ids, retrieved_proposal_ids,
similar_past_proposals_analysis[].proposal_id, draft sections'
source_proposal_id) are stripped at dump time. Past proposals get fresh
UUIDs each time the indexer runs, so preserving stale ids would break
referential integrity. The text content of each screening / draft
section is preserved — that's what the demo actually shows.

What it adds as synthetic:
- 2 manual_upload (status=new)
- 1 url_ingest (status=new)
- 1 SAM.gov (status=new)
- 1 SAM.gov (status=needs_manual_review — exercises the fallback queue)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import UUID, uuid4

from services.api.db.client import db_cursor
from services.api import _env  # noqa: F401


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "sample_data" / "seed"
SEED_DIR.mkdir(parents=True, exist_ok=True)


# Hand-picked email RFPs — chosen for variety of agency, status, and screening output.
# Order matters: drives the order things appear on the dashboard. We match by
# title substring + status rather than hardcoding UUIDs, since UUIDs change on
# every email re-ingestion.
CAPTURE_PICKS: List[Dict[str, str]] = [
    {"title_contains": "USDA FNS SNAP",                              "status": "in_draft"},
    {"title_contains": "VHA Healthcare",                             "status": "in_draft"},
    {"title_contains": "NIH Clinical Research",                      "status": "screened"},
    {"title_contains": "Supply Chain Analytics Platform DOJ",        "status": "screened"},
    {"title_contains": "cherry hill",                                "status": "screened"},
]


def _strip_uuid_refs(value: Any) -> Any:
    """Replace any UUID-looking field that points across-table at past
    proposals with None / [], so reseeding doesn't carry stale ids."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in ("source_proposal_id", "proposal_id"):
                # Field could be a real UUID or already-None; just drop it.
                out[k] = None
                continue
            if k in ("similar_proposal_ids", "retrieved_proposal_ids"):
                out[k] = []
                continue
            out[k] = _strip_uuid_refs(v)
        return out
    if isinstance(value, list):
        return [_strip_uuid_refs(x) for x in value]
    return value


def _row_to_jsonable(row: Dict[str, Any]) -> Dict[str, Any]:
    """psycopg2 DictRow → plain dict with serializable values."""
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif hasattr(v, "isoformat"):  # date
            out[k] = v.isoformat()
        else:
            out[k] = v
    return _strip_uuid_refs(out)


def capture_from_db() -> Dict[str, List[Dict[str, Any]]]:
    rfps: List[Dict[str, Any]] = []
    screenings: List[Dict[str, Any]] = []
    drafts: List[Dict[str, Any]] = []
    draft_jobs: List[Dict[str, Any]] = []
    audit_entries: List[Dict[str, Any]] = []

    captured_ids: List[str] = []
    captured_screening_ids: List[str] = []
    captured_draft_ids: List[str] = []

    with db_cursor() as cur:
        for pick in CAPTURE_PICKS:
            cur.execute(
                """SELECT * FROM rfps
                    WHERE source_type='email' AND status=%s
                      AND title ILIKE %s
                    ORDER BY received_at DESC LIMIT 1""",
                (pick["status"], f"%{pick['title_contains']}%"),
            )
            row = cur.fetchone()
            if not row:
                print(f"[capture] WARN  no match for {pick}; skipping")
                continue
            rfps.append(_row_to_jsonable(row))
            rfp_id = row["id"]
            captured_ids.append(str(rfp_id))

            cur.execute(
                "SELECT * FROM screenings WHERE rfp_id = %s ORDER BY created_at DESC LIMIT 1",
                (str(rfp_id),),
            )
            sc = cur.fetchone()
            if sc:
                screenings.append(_row_to_jsonable(sc))
                captured_screening_ids.append(str(sc["id"]))

            cur.execute(
                "SELECT * FROM drafts WHERE rfp_id = %s ORDER BY created_at DESC LIMIT 1",
                (str(rfp_id),),
            )
            dr = cur.fetchone()
            if dr:
                drafts.append(_row_to_jsonable(dr))
                captured_draft_ids.append(str(dr["id"]))

        # Capture draft_jobs that produced the captured drafts (terminal state only).
        if captured_draft_ids:
            cur.execute(
                "SELECT * FROM draft_jobs WHERE draft_id = ANY(%s::uuid[])",
                (captured_draft_ids,),
            )
            for j in cur.fetchall():
                draft_jobs.append(_row_to_jsonable(j))

        # Capture audit-log entries for the captured RFPs + their screenings + drafts +
        # jobs, so the demo Audit pages have substance from t=0.
        related_ids = (
            captured_ids
            + captured_screening_ids
            + captured_draft_ids
            + [j["id"] for j in draft_jobs]
        )
        if related_ids:
            cur.execute(
                """SELECT * FROM audit_log
                    WHERE entity_id = ANY(%s::uuid[])
                    ORDER BY created_at ASC""",
                (related_ids,),
            )
            for a in cur.fetchall():
                audit_entries.append(_row_to_jsonable(a))

    return {
        "rfps": rfps,
        "screenings": screenings,
        "drafts": drafts,
        "draft_jobs": draft_jobs,
        "audit_log": audit_entries,
    }


# ---------- synthetic content -----------------------------------------

def synthetic_rfps() -> List[Dict[str, Any]]:
    """Hand-crafted RFP rows. status='new' so no screenings/drafts needed.

    All five fill out the source-type variety (manual_upload, url_ingest,
    sam_gov) and surface the Needs Attention queue case.
    """
    now = datetime.now(timezone.utc)

    base = lambda **k: {
        "id": str(uuid4()),
        "source_adapter_version": None,
        "source_metadata": {},
        "external_id": None,
        "title": "",
        "agency": None,
        "naics_codes": [],
        "due_date": None,
        "value_estimate_low": None,
        "value_estimate_high": None,
        "full_text": None,
        "source_url": None,
        "received_at": now.isoformat(),
        "status": "new",
        "dedupe_hash": None,
        **k,
    }

    return [
        base(
            source_type="manual_upload",
            source_adapter_version="manual_upload_v1",
            source_metadata={"filename": "MA-Data-Modernization-RFP.pdf",
                             "content_type": "application/pdf",
                             "title": "Massachusetts Data Modernization RFP"},
            title="Massachusetts Executive Office for Administration & Finance — Data Modernization Initiative",
            agency="Commonwealth of Massachusetts, EOAF",
            naics_codes=["541511", "541512"],
            due_date=(now + timedelta(days=24)).replace(hour=17, minute=0, second=0, microsecond=0).isoformat(),
            value_estimate_low=2_400_000,
            value_estimate_high=4_800_000,
            full_text=(
                "The Commonwealth of Massachusetts seeks a prime contractor to modernize "
                "its enterprise data platform supporting cross-agency analytics. Scope "
                "includes (a) consolidating eight legacy departmental data warehouses "
                "into a unified Snowflake environment on AWS, (b) rebuilding ETL "
                "pipelines in dbt with documented data lineage, (c) implementing "
                "self-service analytics using Tableau for program staff across HHS, "
                "DOR, and EOLWD, (d) maintaining data classification + encryption "
                "consistent with M.G.L. c. 93H. Period of performance: 18 months "
                "with two 12-month options. NAICS 541511. Set-aside: none; full and "
                "open. Place of performance: Boston, MA, with remote flexibility. "
                "Response due date: see solicitation cover page."
            ),
            source_url=None,
            received_at=(now - timedelta(hours=4)).isoformat(),
            status="new",
            dedupe_hash="seed-mass-eoaf-data-mod",
        ),
        base(
            source_type="manual_upload",
            source_adapter_version="manual_upload_v1",
            source_metadata={"filename": "DoEd-Title-I-Reporting.pdf",
                             "content_type": "application/pdf",
                             "title": "DoEd Title I Reporting Platform"},
            title="U.S. Department of Education — Title I Performance Reporting Platform",
            agency="U.S. Department of Education, Office of Elementary and Secondary Education",
            naics_codes=["541511"],
            due_date=(now + timedelta(days=18)).replace(hour=14, minute=0, second=0, microsecond=0).isoformat(),
            value_estimate_low=1_800_000,
            value_estimate_high=3_200_000,
            full_text=(
                "The Office of Elementary and Secondary Education (OESE) seeks a "
                "contractor to design and implement a unified Title I performance "
                "reporting platform consolidating district-level data submissions "
                "from all 50 states. Scope: data ingestion APIs, validation rules "
                "engine, longitudinal analytics dashboards, public-facing data "
                "release pipelines (FERPA-compliant aggregation). Cloud target: "
                "AWS GovCloud. NAICS 541511. Set-aside: full and open. 24 months "
                "with one 12-month option."
            ),
            source_url=None,
            received_at=(now - timedelta(hours=8)).isoformat(),
            status="new",
            dedupe_hash="seed-doed-title1-platform",
        ),
        base(
            source_type="url_ingest",
            source_adapter_version="url_ingest_v1",
            source_metadata={"url": "https://sam.gov/workspace/contract/opp/example-state-mn-bi/view",
                             "page_title": "Minnesota DHS Business Intelligence RFI"},
            title="Minnesota DHS — Business Intelligence Modernization (RFI)",
            agency="Minnesota Department of Human Services",
            naics_codes=["541511", "541512"],
            due_date=(now + timedelta(days=10)).replace(hour=16, minute=0, second=0, microsecond=0).isoformat(),
            value_estimate_low=None,
            value_estimate_high=None,
            full_text=(
                "Request for Information (RFI). The Minnesota Department of Human "
                "Services is conducting market research for a forthcoming "
                "solicitation to modernize its statewide BI environment supporting "
                "Medicaid analytics, behavioral health reporting, and child welfare "
                "outcomes tracking. This RFI seeks vendor input on technical "
                "approach, integration with MMIS, and FedRAMP-aligned cloud "
                "deployments. Responses will inform but not determine the "
                "subsequent RFP. NAICS 541511. No award will result from this RFI."
            ),
            source_url="https://sam.gov/workspace/contract/opp/example-state-mn-bi/view",
            received_at=(now - timedelta(hours=12)).isoformat(),
            status="new",
            dedupe_hash="seed-mn-dhs-bi-rfi",
        ),
        base(
            source_type="sam_gov",
            source_adapter_version="sam_gov_v1",
            source_metadata={
                "notice_id": "75D301-26-Q-21088",
                "notice_type": "Solicitation",
                "set_aside": "Total Small Business Set-Aside (FAR 19.5)",
                "posted_date": (now - timedelta(days=2)).date().isoformat(),
                "active": "Yes",
                "description_fetch_status": "ok",
            },
            external_id="75D301-26-Q-21088",
            title="HHS CDC — Public Health Data Modernization Support Services",
            agency="HEALTH AND HUMAN SERVICES, DEPARTMENT OF.CENTERS FOR DISEASE CONTROL AND PREVENTION",
            naics_codes=["541511"],
            due_date=(now + timedelta(days=21)).replace(hour=17, minute=0, second=0, microsecond=0).isoformat(),
            value_estimate_low=1_200_000,
            value_estimate_high=2_400_000,
            full_text=(
                "CDC seeks a prime contractor to support the Data Modernization "
                "Initiative (DMI), specifically: (a) ingesting state-level "
                "syndromic surveillance feeds into the CDC unified data platform, "
                "(b) building dbt-based transformations for cross-condition "
                "analytics, (c) developing Tableau dashboards for state and local "
                "epidemiologists, (d) maintaining FedRAMP Moderate posture. Total "
                "small business set-aside. NAICS 541511. 24 months base + two "
                "12-month options. Place of performance: Atlanta, GA / remote."
            ),
            source_url="https://sam.gov/workspace/contract/opp/synthetic-cdc-dmi/view",
            received_at=(now - timedelta(days=2)).isoformat(),
            status="new",
            dedupe_hash="seed-cdc-dmi-support",
        ),
        base(
            source_type="sam_gov",
            source_adapter_version="sam_gov_v1",
            source_metadata={
                "notice_id": "12345678-NEEDS-REVIEW",
                "notice_type": "Sources Sought",
                "set_aside": None,
                "posted_date": (now - timedelta(days=1)).date().isoformat(),
                "active": "Yes",
                "description_fetch_status": "http_500",
                "fallback_on_failure": "flag_for_manual_review",
            },
            external_id="12345678-NEEDS-REVIEW",
            title="Treasury — Tax Data Platform Sources Sought (description fetch failed)",
            agency="TREASURY, DEPARTMENT OF THE.INTERNAL REVENUE SERVICE",
            naics_codes=["541511"],
            due_date=(now + timedelta(days=14)).replace(hour=14, minute=0, second=0, microsecond=0).isoformat(),
            value_estimate_low=None,
            value_estimate_high=None,
            full_text=None,   # description fetch failed; full_text is intentionally absent
            source_url="https://sam.gov/workspace/contract/opp/synthetic-irs-tax-data/view",
            received_at=(now - timedelta(days=1)).isoformat(),
            status="needs_manual_review",
            dedupe_hash="seed-irs-tax-data-needs-review",
        ),
    ]


def synthetic_draft_jobs_and_audit(
    rfps: List[Dict[str, Any]],
    screenings: List[Dict[str, Any]],
    drafts: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """For each captured draft, synthesize a matching ``completed`` draft_job.
    For every RFP / screening / draft, synthesize the audit_log entries that
    would have been written during the live flow (discovery_ingest,
    screen_rfp, draft_proposal, draft_job state transitions).

    Output: (draft_jobs, audit_entries). Lets the SQL Console's
    "Audit trail for the most recent RFP" and "Draft jobs and durations"
    example queries return non-empty results from t=0.
    """
    now = datetime.now(timezone.utc)
    draft_jobs: List[Dict[str, Any]] = []
    audit_entries: List[Dict[str, Any]] = []

    rfps_by_id = {r["id"]: r for r in rfps}
    drafts_by_rfp = {d["rfp_id"]: d for d in drafts}
    screenings_by_rfp = {s["rfp_id"]: s for s in screenings}

    for r in rfps:
        rfp_id = r["id"]
        # discovery_ingest entry per RFP (pre-dates everything else)
        ingested_at = r.get("received_at")
        try:
            ingest_dt = datetime.fromisoformat(ingested_at) if ingested_at else now - timedelta(hours=24)
        except Exception:
            ingest_dt = now - timedelta(hours=24)
        audit_entries.append({
            "id": str(uuid4()),
            "entity_type": "rfp",
            "entity_id": rfp_id,
            "action": "discovery_ingest" if r.get("source_type") != "manual_upload" else "rfp_ingested",
            "actor": "system",
            "details": {
                "adapter_name": (
                    "demo_gmail" if r.get("source_type") == "email"
                    else "sam_gov_primary" if r.get("source_type") == "sam_gov"
                    else r.get("source_type")
                ),
                "source_identifier": (r.get("source_metadata") or {}).get("imap_uid")
                                     or r.get("external_id") or rfp_id,
                "was_new": True,
                "title": r.get("title"),
                "status": r.get("status"),
            },
            "created_at": ingest_dt.isoformat(),
        })

        # screen_rfp + (for in_draft) the draft_job lifecycle
        sc = screenings_by_rfp.get(rfp_id)
        if sc:
            sc_at = sc.get("created_at")
            try:
                sc_dt = datetime.fromisoformat(sc_at) if sc_at else ingest_dt + timedelta(minutes=2)
            except Exception:
                sc_dt = ingest_dt + timedelta(minutes=2)
            audit_entries.append({
                "id": str(uuid4()),
                "entity_type": "rfp",
                "entity_id": rfp_id,
                "action": "screen_rfp",
                "actor": "claude",
                "details": {
                    "model": sc.get("model_version") or "claude-sonnet-4-5",
                    "input_tokens": 28000, "output_tokens": 4200,
                    "schema_enforced": True,
                },
                "created_at": sc_dt.isoformat(),
            })

        d = drafts_by_rfp.get(rfp_id)
        if d:
            d_at = d.get("created_at")
            try:
                d_dt = datetime.fromisoformat(d_at) if d_at else now
            except Exception:
                d_dt = now
            # ~5 min before completion
            queued_dt = d_dt - timedelta(minutes=5, seconds=20)
            running_dt = queued_dt + timedelta(milliseconds=80)
            completed_dt = d_dt + timedelta(milliseconds=120)
            job_id = str(uuid4())
            draft_jobs.append({
                "id": job_id,
                "rfp_id": rfp_id,
                "status": "completed",
                "started_at": running_dt.isoformat(),
                "completed_at": completed_dt.isoformat(),
                "draft_id": d["id"],
                "error_message": None,
                "created_at": queued_dt.isoformat(),
            })
            audit_entries.append({
                "id": str(uuid4()), "entity_type": "draft_job", "entity_id": job_id,
                "action": "queued", "actor": "system",
                "details": {"rfp_id": rfp_id, "mode": "full_auto"},
                "created_at": queued_dt.isoformat(),
            })
            audit_entries.append({
                "id": str(uuid4()), "entity_type": "draft_job", "entity_id": job_id,
                "action": "running", "actor": "system",
                "details": {"rfp_id": rfp_id},
                "created_at": running_dt.isoformat(),
            })
            audit_entries.append({
                "id": str(uuid4()), "entity_type": "rfp", "entity_id": rfp_id,
                "action": "draft_proposal", "actor": "claude",
                "details": {
                    "model": "claude-sonnet-4-5",
                    "input_tokens": 42000, "output_tokens": 11500,
                    "schema_enforced": True,
                },
                "created_at": d_dt.isoformat(),
            })
            audit_entries.append({
                "id": str(uuid4()), "entity_type": "draft_job", "entity_id": job_id,
                "action": "completed", "actor": "system",
                "details": {
                    "rfp_id": rfp_id, "draft_id": d["id"],
                    "duration_seconds": (completed_dt - running_dt).total_seconds(),
                },
                "created_at": completed_dt.isoformat(),
            })

    audit_entries.sort(key=lambda a: a["created_at"])
    return draft_jobs, audit_entries


# ---------- main ------------------------------------------------------

def main() -> None:
    captured = capture_from_db()
    print(f"[capture] {len(captured['rfps'])} rfps, "
          f"{len(captured['screenings'])} screenings, "
          f"{len(captured['drafts'])} drafts, "
          f"{len(captured['draft_jobs'])} draft_jobs, "
          f"{len(captured['audit_log'])} audit entries")

    syn = synthetic_rfps()
    print(f"[synthetic] {len(syn)} rfps")

    # Combine — synthetics get appended after captured.
    rfps = captured["rfps"] + syn

    # If the source DB had no draft_jobs / audit_log entries (e.g. they were
    # truncated by an earlier seed_data run), synthesize a minimal but
    # realistic set covering the captured RFPs, screenings, and drafts.
    syn_jobs, syn_audit = synthetic_draft_jobs_and_audit(
        rfps=rfps,
        screenings=captured["screenings"],
        drafts=captured["drafts"],
    )
    draft_jobs = captured["draft_jobs"] or syn_jobs
    audit_entries = captured["audit_log"] or syn_audit
    if captured["draft_jobs"]:
        print(f"[capture] using {len(draft_jobs)} captured draft_jobs from DB")
    else:
        print(f"[synthetic] {len(draft_jobs)} draft_jobs (DB had none)")
    if captured["audit_log"]:
        print(f"[capture] using {len(audit_entries)} captured audit entries from DB")
    else:
        print(f"[synthetic] {len(audit_entries)} audit entries (DB had none)")

    out = {
        "rfps.json":       rfps,
        "screenings.json": captured["screenings"],
        "drafts.json":     captured["drafts"],
        "draft_jobs.json": draft_jobs,
        "audit_log.json":  audit_entries,
    }
    for name, data in out.items():
        path = SEED_DIR / name
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        print(f"  wrote {path.relative_to(REPO_ROOT)}: {len(data)} records")

    # Status-distribution summary
    from collections import Counter
    by_status = Counter(r["status"] for r in rfps)
    by_source = Counter(r["source_type"] for r in rfps)
    print("\n[summary]")
    print(f"  total RFPs:       {len(rfps)}")
    print(f"  by status:        {dict(by_status)}")
    print(f"  by source_type:   {dict(by_source)}")
    print(f"  with screenings:  {len(captured['screenings'])}")
    print(f"  with drafts:      {len(captured['drafts'])}")
    print(f"  draft_jobs:       {len(captured['draft_jobs'])}")
    print(f"  audit_entries:    {len(captured['audit_log'])}")


if __name__ == "__main__":
    main()
