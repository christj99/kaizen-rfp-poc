"""FastAPI entrypoint.

Phase 2 (+supplemental amendment 2.H / 2.E) endpoints:

Ingestion:
  * POST /rfp/ingest              — structured-field ingestion (manual_upload adapter)
  * POST /rfp/upload              — PDF upload (manual_upload adapter)
  * POST /rfp/ingest_url          — URL fetch + ingest (url_ingest adapter)

Discovery (pollable adapters):
  * POST /discovery/run                   — every enabled adapter
  * POST /discovery/run/{adapter_name}    — a specific adapter
  * POST /discovery/sam_gov/poll          — DEPRECATED alias (kept for backward
                                            compat with the primary-plan shape)
  * GET  /discovery/adapters              — list configured adapters + health

RFPs + screening:
  * GET  /rfps
  * GET  /rfp/{id}
  * POST /rfp/{id}/screen
  * GET  /rfp/{id}/similar-proposals
  * POST /rfp/{id}/override

Infra:
  * GET  /health
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from datetime import datetime as _dt, timezone
from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import _env  # noqa: F401 — populates os.environ from .env
from .agents.discovery import (
    DiscoveryRunResult,
    adapter_health_snapshot,
    build_adapter_by_name,
    build_record_from_pdf,
    build_record_from_structured,
    build_record_from_url,
    ingest_raw_record,
    run_adapter,
    run_discovery,
)
from .agents.drafting import DraftingError, draft_proposal, export_draft_to_markdown
from .agents.screening import screen_rfp
from .config.loader import get_config
from .db.client import (
    db_cursor,
    get_draft,
    get_draft_job,
    get_past_proposal,
    get_rfp,
    insert_draft_job,
    latest_draft_for_rfp,
    latest_screening_for_rfp,
    list_audit_entries,
    list_past_proposals,
    list_rfps,
    list_rfps_with_screening,
    ping,
    set_screening_override,
    update_draft_job,
    write_audit,
)
from .models.audit import AuditEntry
from .models.draft import Draft
from .models.draft_job import DraftJob, DraftJobStatus
from .models.past_proposal import PastProposal
from .models.rfp import RFP, RFPSourceType, RFPStatus
from .models.screening import Recommendation, Screening
from .rag.retriever import find_similar_proposals

log = logging.getLogger(__name__)

app = FastAPI(title="Kaizen RFP POC", version="0.3.0")


# -- request/response schemas -----------------------------------------

class IngestRFPRequest(BaseModel):
    # source_type is authoritative for the row; default matches the manual_upload adapter.
    source_type: RFPSourceType = "manual_upload"
    title: str
    full_text: str
    agency: Optional[str] = None
    external_id: Optional[str] = None
    naics_codes: List[str] = Field(default_factory=list)
    due_date: Optional[datetime] = None
    value_estimate_low: Optional[int] = None
    value_estimate_high: Optional[int] = None
    source_url: Optional[str] = None
    dedupe_hash: Optional[str] = None


class IngestURLRequest(BaseModel):
    url: str
    title: Optional[str] = None
    agency: Optional[str] = None
    naics_codes: List[str] = Field(default_factory=list)


class IngestResult(BaseModel):
    rfp: RFP
    was_new: bool


class RFPWithScreening(BaseModel):
    rfp: RFP
    screening: Optional[Screening] = None


class SimilarProposalResult(BaseModel):
    proposal_id: UUID
    title: Optional[str]
    agency: Optional[str]
    outcome: Optional[str]
    similarity: float
    best_section: Optional[str]
    best_excerpt: Optional[str]


class OverrideRequest(BaseModel):
    recommendation: Recommendation
    reason: Optional[str] = None


class AdapterRunSummary(BaseModel):
    adapter_name: str
    adapter_type: str
    new_count: int
    duplicate_count: int
    error_count: int
    new_rfp_ids: List[UUID]
    errors: List[Dict[str, Any]]


class DiscoveryRunResponse(BaseModel):
    total_new: int
    total_duplicates: int
    total_errors: int
    adapters: List[AdapterRunSummary]


class AdapterHealth(BaseModel):
    name: str
    adapter_type: str
    status: Literal["ok", "degraded", "down"]
    detail: str
    metadata: Dict[str, Any]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: bool


class OrchestrateRequest(BaseModel):
    rfp_id: UUID
    # Lets callers force a specific mode for a one-off run without editing
    # config.yaml. Defaults to None which means "use whatever config.mode says".
    mode_override: Optional[Literal["manual", "chain", "full_auto"]] = None


class OrchestrateResponse(BaseModel):
    rfp_id: UUID
    mode: Literal["manual", "chain", "full_auto"]
    steps_taken: List[str] = Field(default_factory=list)
    screening: Optional[Screening] = None
    draft_job_id: Optional[UUID] = None
    notes: List[str] = Field(default_factory=list)


# -- health ------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_ok = ping()
    return HealthResponse(status="ok" if db_ok else "degraded", db=db_ok)


# -- orchestration (Phase 4 primary-plan Step 4.1) --------------------

@app.post("/orchestrate", response_model=OrchestrateResponse)
def orchestrate_endpoint(
    body: OrchestrateRequest,
    background_tasks: BackgroundTasks,
) -> OrchestrateResponse:
    """Run the configured mode's pipeline against an already-ingested RFP.

    The discovery adapters land RFPs in the DB. n8n workflows then call
    this endpoint per RFP so the same mode rules apply no matter where
    the RFP came from (email, SAM.gov, manual upload, URL ingest).

    * mode='manual'    → no auto-chaining; returns just the RFP
    * mode='chain'     → runs screening synchronously
    * mode='full_auto' → screening synchronously, then if score >=
                         config.drafting.auto_draft_threshold, queues an
                         async drafting job (BackgroundTasks). n8n's
                         draft_completion_watcher workflow will fire the
                         'draft ready' Slack notification when the job
                         finishes.
    """
    rfp = get_rfp(body.rfp_id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    cfg = get_config()
    mode = body.mode_override or cfg.mode
    resp = OrchestrateResponse(rfp_id=rfp.id, mode=mode)

    if mode == "manual":
        resp.steps_taken.append("returned_rfp_only")
        return resp

    # chain + full_auto both run screening synchronously.
    try:
        screening = screen_rfp(rfp)
        resp.screening = screening
        resp.steps_taken.append("screened")
    except Exception as exc:  # noqa: BLE001
        log.exception("Orchestrator screening failed for %s", body.rfp_id)
        resp.notes.append(f"screening_failed: {type(exc).__name__}: {exc}")
        return resp

    if mode == "chain":
        return resp

    # full_auto — kick off async drafting only if the fit score clears
    # the auto_draft_threshold. A recommendation of 'skip' also short-circuits.
    threshold = cfg.drafting.auto_draft_threshold
    score = screening.fit_score if screening.fit_score is not None else -1

    if screening.recommendation == "skip":
        resp.notes.append(f"auto_draft_skipped: recommendation=skip")
        return resp

    if score < threshold:
        resp.notes.append(
            f"auto_draft_skipped: fit_score={score} < threshold={threshold}"
        )
        return resp

    job = DraftJob(rfp_id=body.rfp_id, status="queued")
    insert_draft_job(job)
    _audit_draft_job(job.id, body.rfp_id, "queued", mode="full_auto")
    background_tasks.add_task(_run_draft_job, job.id, body.rfp_id)
    resp.draft_job_id = job.id
    resp.steps_taken.append("draft_queued")
    resp.notes.append(
        f"auto_drafting_queued: fit_score={score} >= threshold={threshold}"
    )
    return resp


# -- RFP ingestion -----------------------------------------------------

@app.post("/rfp/ingest", response_model=IngestResult, status_code=201)
def ingest_rfp(body: IngestRFPRequest) -> IngestResult:
    """Structured-field ingestion. Routes through the manual_upload adapter
    so the normalize → dedupe → upsert pipeline is identical to every other
    source."""
    record = build_record_from_structured(
        title=body.title,
        full_text=body.full_text,
        agency=body.agency,
        naics_codes=body.naics_codes,
        external_id=body.external_id,
        source_url=body.source_url,
        due_date=body.due_date,
        value_estimate_low=body.value_estimate_low,
        value_estimate_high=body.value_estimate_high,
        dedupe_hash=body.dedupe_hash,
    )
    rfp, was_new = ingest_raw_record(record)
    # If caller wants a non-default source_type (e.g. 'url_ingest'), honor it
    # by re-upserting the persisted row. Mostly a UX nicety for API callers.
    if body.source_type != "manual_upload" and rfp.source_type != body.source_type:
        from .db.client import db_cursor as _dbc
        with _dbc() as cur:
            cur.execute(
                "UPDATE rfps SET source_type = %s WHERE id = %s",
                (body.source_type, str(rfp.id)),
            )
        rfp.source_type = body.source_type
    return IngestResult(rfp=rfp, was_new=was_new)


@app.post("/rfp/upload", response_model=IngestResult, status_code=201)
async def ingest_rfp_pdf(
    file: UploadFile,
    title: Optional[str] = Form(default=None),
    agency: Optional[str] = Form(default=None),
) -> IngestResult:
    """PDF upload via multipart form. Uses pypdf via the manual_upload adapter."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload")
    try:
        record = build_record_from_pdf(
            raw,
            filename=file.filename or "upload.pdf",
            content_type=file.content_type,
            title=title,
            agency=agency,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PDF parse failed: {exc}")
    rfp, was_new = ingest_raw_record(record)
    return IngestResult(rfp=rfp, was_new=was_new)


@app.post("/rfp/ingest_url", response_model=IngestResult, status_code=201)
def ingest_rfp_url(body: IngestURLRequest) -> IngestResult:
    """URL ingestion — fetch the page, strip to text, ingest."""
    try:
        record = build_record_from_url(
            body.url,
            title=body.title,
            agency=body.agency,
            naics_codes=body.naics_codes,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"URL fetch failed: {exc}")
    rfp, was_new = ingest_raw_record(record)
    return IngestResult(rfp=rfp, was_new=was_new)


# -- RFP read / screening ----------------------------------------------

@app.get("/rfps")
def list_rfps_endpoint(
    status: Optional[RFPStatus] = None,
    source_type: Optional[RFPSourceType] = None,
    with_screening: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    """List RFPs (newest first). Pass ``with_screening=true`` to inline the
    most-recent screening summary (fit_score, recommendation, effort) per
    RFP — used by the Dashboard table to avoid N+1 calls."""
    if with_screening:
        return list_rfps_with_screening(
            status=status, source_type=source_type, limit=limit, offset=offset
        )
    return list_rfps(status=status, source_type=source_type, limit=limit, offset=offset)


@app.get("/rfp/{rfp_id}", response_model=RFPWithScreening)
def get_rfp_endpoint(rfp_id: UUID) -> RFPWithScreening:
    rfp = get_rfp(rfp_id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")
    screening = latest_screening_for_rfp(rfp_id)
    return RFPWithScreening(rfp=rfp, screening=screening)


@app.post("/rfp/{rfp_id}/screen", response_model=Screening)
def screen_rfp_endpoint(rfp_id: UUID) -> Screening:
    rfp = get_rfp(rfp_id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")
    try:
        return screen_rfp(rfp)
    except Exception as exc:  # noqa: BLE001
        log.exception("Screening failed for %s", rfp_id)
        raise HTTPException(status_code=500, detail=f"Screening failed: {exc}")


@app.get("/rfp/{rfp_id}/similar-proposals", response_model=List[SimilarProposalResult])
def similar_proposals_endpoint(rfp_id: UUID, k: int = 3) -> List[SimilarProposalResult]:
    rfp = get_rfp(rfp_id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")
    query = "\n\n".join(p for p in [rfp.title, rfp.agency, rfp.full_text] if p)
    results = find_similar_proposals(query, k=k)
    return [
        SimilarProposalResult(
            proposal_id=r.proposal.id,
            title=r.proposal.title,
            agency=r.proposal.agency,
            outcome=r.proposal.outcome,
            similarity=r.similarity,
            best_section=r.best_section,
            best_excerpt=r.best_excerpt,
        )
        for r in results
    ]


class DraftJobQueued(BaseModel):
    """Response for ``POST /rfp/{id}/draft?mode=async``."""
    job_id: UUID
    rfp_id: UUID
    status: Literal["queued"] = "queued"
    estimated_duration_seconds: int = 300


class DraftJobStatusResponse(BaseModel):
    """Response for ``GET /draft/job/{id}``.

    When ``job.status == 'completed'`` the ``draft`` field is populated so
    pollers don't need a second call to ``/draft/{id}``.
    """
    job: DraftJob
    draft: Optional[Draft] = None


# Estimated duration surfaced to clients in the queued response. 300s matches
# the observed 5-6 min drafting latency in smoke tests.
_DRAFT_ESTIMATED_DURATION_S = 300


def _audit_draft_job(job_id: UUID, rfp_id: UUID, action: str, **details: Any) -> None:
    """Best-effort audit write. Failures here must never break the job path."""
    try:
        write_audit(
            AuditEntry(
                entity_type="draft_job",
                entity_id=job_id,
                action=action,
                actor="system",
                details={"rfp_id": str(rfp_id), **details},
            )
        )
    except Exception:
        log.exception("audit write failed for draft_job %s action=%s", job_id, action)


def _run_draft_job(job_id: UUID, rfp_id: UUID) -> None:
    """Background worker.

    Intentionally avoids re-fetching the RFP until we've flipped the job to
    'running', so that a missing RFP manifests as a clean failed-job state
    rather than a silent stuck-in-queued.
    """
    now = _dt.now(timezone.utc)
    update_draft_job(job_id, status="running", started_at=now)
    _audit_draft_job(job_id, rfp_id, "running")

    try:
        rfp = get_rfp(rfp_id)
        if rfp is None:
            raise DraftingError(f"RFP {rfp_id} no longer exists")
        draft = draft_proposal(rfp)
        end = _dt.now(timezone.utc)
        update_draft_job(
            job_id,
            status="completed",
            completed_at=end,
            draft_id=draft.id,
        )
        _audit_draft_job(
            job_id, rfp_id, "completed",
            draft_id=str(draft.id),
            duration_seconds=(end - now).total_seconds(),
        )
    except Exception as exc:
        end = _dt.now(timezone.utc)
        msg = f"{type(exc).__name__}: {exc}"
        log.exception("Draft job %s for rfp %s failed", job_id, rfp_id)
        update_draft_job(
            job_id,
            status="failed",
            completed_at=end,
            error_message=msg[:2000],
        )
        _audit_draft_job(
            job_id, rfp_id, "failed",
            error_class=type(exc).__name__,
            duration_seconds=(end - now).total_seconds(),
        )


@app.post(
    "/rfp/{rfp_id}/draft",
    response_model=None,                  # Union response, hand-serialized
    status_code=201,
)
def draft_rfp_endpoint(
    rfp_id: UUID,
    background_tasks: BackgroundTasks,
    mode: Literal["async", "sync"] = "async",
):
    """Generate a first-draft proposal.

    ``mode=async`` (default): returns immediately with a ``DraftJobQueued``
    payload and runs the drafting agent via ``BackgroundTasks``. Poll
    ``GET /draft/job/{job_id}`` for progress and the completed draft.

    ``mode=sync``: preserves the Phase 3 behavior (request blocks ~5 min,
    returns the full ``Draft``). Kept as a deterministic demo safety net.
    """
    rfp = get_rfp(rfp_id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    if mode == "sync":
        try:
            return draft_proposal(rfp)
        except DraftingError as exc:
            log.exception("Synchronous drafting failed for %s", rfp_id)
            raise HTTPException(status_code=500, detail=str(exc))

    # async mode
    job = DraftJob(rfp_id=rfp_id, status="queued")
    insert_draft_job(job)
    _audit_draft_job(job.id, rfp_id, "queued", mode="async")
    background_tasks.add_task(_run_draft_job, job.id, rfp_id)
    return DraftJobQueued(
        job_id=job.id,
        rfp_id=rfp_id,
        estimated_duration_seconds=_DRAFT_ESTIMATED_DURATION_S,
    )


@app.get("/draft/job/{job_id}", response_model=DraftJobStatusResponse)
def get_draft_job_endpoint(job_id: UUID) -> DraftJobStatusResponse:
    job = get_draft_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Draft job not found")
    draft: Optional[Draft] = None
    if job.status == "completed" and job.draft_id:
        result = get_draft(job.draft_id)
        if result:
            draft, _meta = result
    return DraftJobStatusResponse(job=job, draft=draft)


@app.get("/draft_jobs", response_model=List[DraftJob])
def list_draft_jobs_endpoint(
    status: Optional[DraftJobStatus] = None,
    since: Optional[datetime] = None,
    limit: int = 50,
) -> List[DraftJob]:
    """List draft jobs. The n8n draft_completion_watcher workflow uses
    ``?status=completed&since=<last_tick>`` to find newly-finished jobs."""
    sql = "SELECT * FROM draft_jobs"
    clauses: List[str] = []
    params: List[Any] = []
    if status:
        clauses.append("status = %s")
        params.append(status)
    if since:
        clauses.append("completed_at > %s")
        params.append(since)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY completed_at DESC NULLS LAST, created_at DESC LIMIT %s"
    params.append(limit)
    from .db.client import _row_to_draft_job
    with db_cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_draft_job(r) for r in cur.fetchall()]


@app.get("/draft/{draft_id}", response_model=Draft)
def get_draft_endpoint(draft_id: UUID) -> Draft:
    result = get_draft(draft_id)
    if not result:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft, _meta = result
    return draft


@app.get("/draft/{draft_id}/export")
def export_draft_endpoint(draft_id: UUID):
    from fastapi.responses import PlainTextResponse
    result = get_draft(draft_id)
    if not result:
        raise HTTPException(status_code=404, detail="Draft not found")
    draft, overall_meta = result
    rfp = get_rfp(draft.rfp_id)
    md = export_draft_to_markdown(draft, rfp=rfp, overall_metadata=overall_meta)
    return PlainTextResponse(
        content=md,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'inline; filename="draft-{draft.id}.md"',
        },
    )


@app.post("/rfp/{rfp_id}/override", status_code=204)
def override_screening_endpoint(rfp_id: UUID, body: OverrideRequest) -> None:
    screening = latest_screening_for_rfp(rfp_id)
    if not screening:
        raise HTTPException(status_code=404, detail="No screening found for this RFP")
    set_screening_override(screening.id, body.recommendation, body.reason)
    with db_cursor() as cur:
        import json as _json
        cur.execute(
            """
            INSERT INTO audit_log
                (entity_type, entity_id, action, actor, details)
            VALUES ('screening', %s, 'human_override', 'user', %s::jsonb)
            """,
            (
                str(screening.id),
                _json.dumps({"recommendation": body.recommendation, "reason": body.reason}),
            ),
        )


# -- discovery (pollable adapters) ------------------------------------

def _run_result_to_response(result: DiscoveryRunResult) -> DiscoveryRunResponse:
    return DiscoveryRunResponse(
        total_new=result.total_new,
        total_duplicates=result.total_duplicates,
        total_errors=result.total_errors,
        adapters=[
            AdapterRunSummary(
                adapter_name=a.adapter_name,
                adapter_type=a.adapter_type,
                new_count=len(a.new_rfps),
                duplicate_count=a.duplicates,
                error_count=len(a.errors),
                new_rfp_ids=[r.id for r in a.new_rfps],
                errors=a.errors,
            )
            for a in result.adapters_run
        ],
    )


@app.post("/discovery/run", response_model=DiscoveryRunResponse)
def discovery_run_all() -> DiscoveryRunResponse:
    return _run_result_to_response(run_discovery())


@app.post("/discovery/run/{adapter_name}", response_model=DiscoveryRunResponse)
def discovery_run_one(adapter_name: str) -> DiscoveryRunResponse:
    adapter = build_adapter_by_name(adapter_name)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"No configured adapter named {adapter_name!r}")
    adapter_result = run_adapter(adapter)
    result = DiscoveryRunResult(adapters_run=[adapter_result])
    return _run_result_to_response(result)


@app.get("/discovery/adapters", response_model=List[AdapterHealth])
def discovery_adapters() -> List[AdapterHealth]:
    return [AdapterHealth(**h) for h in adapter_health_snapshot()]


# -- audit log (Phase 5 dashboard activity feed) ----------------------

@app.get("/audit_log", response_model=List[AuditEntry])
def list_audit_log_endpoint(limit: int = 25) -> List[AuditEntry]:
    return list_audit_entries(limit=limit)


# -- past proposals (Phase 5 Past Proposals page) --------------------

@app.get("/past_proposals", response_model=List[PastProposal])
def list_past_proposals_endpoint(
    search: Optional[str] = None,
    limit: int = 100,
) -> List[PastProposal]:
    """List past proposals. ``search`` does a case-insensitive title/agency
    match (semantic search over chunks already lives at
    /rfp/{id}/similar-proposals)."""
    proposals = list_past_proposals(limit=limit)
    if search:
        s = search.strip().lower()
        proposals = [
            p for p in proposals
            if s in (p.title or "").lower() or s in (p.agency or "").lower()
        ]
    return proposals


@app.get("/past_proposal/{proposal_id}", response_model=PastProposal)
def get_past_proposal_endpoint(proposal_id: UUID) -> PastProposal:
    p = get_past_proposal(proposal_id)
    if not p:
        raise HTTPException(status_code=404, detail="Past proposal not found")
    return p


# -- config + rubric editing (Phase 5 Settings + Rubric pages) -------

class ConfigUpdateRequest(BaseModel):
    """Partial-update shape for the Settings page. Only fields that come
    in non-None are written. Hot-reload-on-mtime picks up the change on
    the next /orchestrate or /chat call."""
    mode: Optional[Literal["manual", "chain", "full_auto"]] = None
    screening_threshold_pursue: Optional[int] = None
    screening_threshold_maybe: Optional[int] = None
    drafting_auto_draft_threshold: Optional[int] = None
    slack_notification_threshold: Optional[int] = None
    sources_email_enabled: Optional[bool] = None
    sources_sam_gov_enabled: Optional[bool] = None


@app.get("/config")
def get_config_endpoint():
    """Return the current AppConfig as the Settings page sees it."""
    return get_config().model_dump(mode="json")


@app.put("/config")
def update_config_endpoint(body: ConfigUpdateRequest):
    """Patch config.yaml in place. Hot-reload picks up on next call."""
    import yaml as _yaml
    from .config.loader import DEFAULT_CONFIG_PATH, reload_config
    raw = _yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")) or {}

    if body.mode is not None:
        raw["mode"] = body.mode
    raw.setdefault("screening", {})
    if body.screening_threshold_pursue is not None:
        raw["screening"]["threshold_pursue"] = body.screening_threshold_pursue
    if body.screening_threshold_maybe is not None:
        raw["screening"]["threshold_maybe"] = body.screening_threshold_maybe
    raw.setdefault("drafting", {})
    if body.drafting_auto_draft_threshold is not None:
        raw["drafting"]["auto_draft_threshold"] = body.drafting_auto_draft_threshold
    raw.setdefault("slack", {})
    if body.slack_notification_threshold is not None:
        raw["slack"]["notification_threshold"] = body.slack_notification_threshold
    raw.setdefault("sources", {}).setdefault("email", {})
    if body.sources_email_enabled is not None:
        raw["sources"]["email"]["enabled"] = body.sources_email_enabled
    raw["sources"].setdefault("sam_gov", {})
    if body.sources_sam_gov_enabled is not None:
        raw["sources"]["sam_gov"]["enabled"] = body.sources_sam_gov_enabled

    DEFAULT_CONFIG_PATH.write_text(
        _yaml.safe_dump(raw, sort_keys=False),
        encoding="utf-8",
    )
    cfg = reload_config()

    write_audit(AuditEntry(
        action="config_updated", actor="user",
        details=body.model_dump(exclude_none=True),
    ))
    return cfg.model_dump(mode="json")


@app.get("/rubric")
def get_rubric_endpoint():
    """Return the parsed fit_rubric.yaml for the Rubric Editor."""
    from .config.loader import DEFAULT_CONFIG_PATH
    import yaml as _yaml
    rubric_path = DEFAULT_CONFIG_PATH.parent / "fit_rubric.yaml"
    return _yaml.safe_load(rubric_path.read_text(encoding="utf-8"))


class RubricUpdateRequest(BaseModel):
    """Saves the rubric as a full document. Caller (Rubric Editor) sends
    the complete dict; we bump ``version`` if not provided and audit-log
    it so version history is reconstructible."""
    rubric: Dict[str, Any]


@app.put("/rubric")
def update_rubric_endpoint(body: RubricUpdateRequest):
    from .config.loader import DEFAULT_CONFIG_PATH
    import yaml as _yaml
    from datetime import date as _date

    rubric_path = DEFAULT_CONFIG_PATH.parent / "fit_rubric.yaml"
    rubric = dict(body.rubric)

    # Auto-bump version if caller didn't change it; also stamp last_updated.
    current = _yaml.safe_load(rubric_path.read_text(encoding="utf-8")) or {}
    if rubric.get("version") == current.get("version"):
        # Bump trailing minor: '1.0' -> '1.1', '1.0.0' -> '1.0.1', etc.
        parts = str(current.get("version", "1.0")).split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        rubric["version"] = ".".join(parts)
    rubric["last_updated"] = _date.today().isoformat()

    rubric_path.write_text(
        _yaml.safe_dump(rubric, sort_keys=False),
        encoding="utf-8",
    )
    write_audit(AuditEntry(
        action="rubric_updated", actor="user",
        details={"version": rubric["version"], "last_updated": rubric["last_updated"]},
    ))
    return {"version": rubric["version"], "last_updated": rubric["last_updated"]}


# -- chat (Phase 5 Step 5.3) ------------------------------------------

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatTurn]


class ChatToolCallSummary(BaseModel):
    tool: str
    input: Dict[str, Any]
    output_summary: str


class ChatResponse(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    tool_calls: List[ChatToolCallSummary] = Field(default_factory=list)


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(body: ChatRequest) -> ChatResponse:
    """Tool-calling chat backed by Claude.

    Tools (matching chat_system.txt's contract):
      - search_rfps(filters)
      - search_past_proposals(query, k)
      - get_rfp_detail(rfp_id)
      - get_past_proposal_detail(proposal_id)
      - get_screening_detail(screening_id)
    """
    from .agents.chat import run_chat_turn   # lazy import; chat module is heavy

    return run_chat_turn(body)


# -- admin SQL console (Phase 7 polish) -------------------------------

class SqlAdminRequest(BaseModel):
    query: str


class SqlAdminError(BaseModel):
    error: str
    detail: Optional[str] = None


@app.post("/admin/sql", response_model=None)
def admin_sql_endpoint(body: SqlAdminRequest):
    """Read-only SQL surface for the demo SQL console.

    Three layers of defense in depth (parser, role, transaction settings).
    See ``services/api/db/admin_sql.py`` for the rationale + implementation.
    Failures (parser rejection, permission denied, statement timeout, bad
    SQL syntax) come back as 400 with a structured ``{error, detail}``
    body, not 500.
    """
    from .db import admin_sql as _admin

    ok, err = _admin.validate_select_query(body.query)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "rejected", "detail": err})

    import psycopg2

    try:
        result = _admin.execute_select(body.query)
    except psycopg2.errors.QueryCanceled as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "statement_timeout",
                    "detail": f"query exceeded {_admin.STATEMENT_TIMEOUT_SECONDS}s; "
                              "tighten the query or add a more selective filter"},
        )
    except psycopg2.Error as exc:
        # InsufficientPrivilege, SyntaxError, UndefinedTable, etc. all land here.
        raise HTTPException(
            status_code=400,
            detail={"error": type(exc).__name__,
                    "detail": str(exc).strip()[:600]},
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Unexpected failure in /admin/sql")
        raise HTTPException(
            status_code=500,
            detail={"error": "internal", "detail": str(exc)[:300]},
        )

    # Best-effort audit. Read-only access still warrants a trail.
    try:
        write_audit(AuditEntry(
            entity_type="admin_sql_query",
            action="sql_select",
            actor="admin",
            details={
                "query": body.query[:500],
                "row_count": result["row_count"],
                "truncated": result["truncated"],
                "duration_ms": result["execution_time_ms"],
            },
        ))
    except Exception:
        log.exception("admin_sql audit write failed")

    return result


# -- deprecated --------------------------------------------------------

@app.post(
    "/discovery/sam_gov/poll",
    response_model=DiscoveryRunResponse,
    deprecated=True,
    summary="DEPRECATED — alias for POST /discovery/run/sam_gov_primary",
)
def deprecated_sam_gov_poll() -> DiscoveryRunResponse:
    """Kept for backward compat with the primary plan's endpoint shape.
    New callers should use ``/discovery/run/{adapter_name}``."""
    adapter = build_adapter_by_name("sam_gov_primary")
    if not adapter:
        raise HTTPException(
            status_code=500,
            detail="No 'sam_gov_primary' adapter configured in config.yaml.",
        )
    result = DiscoveryRunResult(adapters_run=[run_adapter(adapter)])
    return _run_result_to_response(result)
