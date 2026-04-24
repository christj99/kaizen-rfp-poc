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

from fastapi import FastAPI, Form, HTTPException, UploadFile
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
from .db.client import (
    db_cursor,
    get_draft,
    get_rfp,
    latest_draft_for_rfp,
    latest_screening_for_rfp,
    list_rfps,
    ping,
    set_screening_override,
)
from .models.draft import Draft
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


# -- health ------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_ok = ping()
    return HealthResponse(status="ok" if db_ok else "degraded", db=db_ok)


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

@app.get("/rfps", response_model=List[RFP])
def list_rfps_endpoint(
    status: Optional[RFPStatus] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[RFP]:
    return list_rfps(status=status, limit=limit, offset=offset)


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


@app.post("/rfp/{rfp_id}/draft", response_model=Draft, status_code=201)
def draft_rfp_endpoint(rfp_id: UUID) -> Draft:
    """Generate a first-draft proposal via the drafting agent."""
    rfp = get_rfp(rfp_id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")
    try:
        return draft_proposal(rfp)
    except DraftingError as exc:
        log.exception("Drafting failed for %s", rfp_id)
        raise HTTPException(status_code=500, detail=str(exc))


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
