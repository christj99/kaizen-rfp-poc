"""FastAPI entrypoint.

Phase 2 endpoints:

* ``POST /rfp/ingest``              — create an RFP from text/URL/PDF
* ``POST /rfp/{id}/screen``         — run the screening agent
* ``GET  /rfp/{id}``                — RFP + latest screening
* ``GET  /rfp/{id}/similar-proposals`` — RAG retrieval only
* ``POST /rfp/{id}/override``       — human override on a screening
* ``GET  /rfps``                    — list RFPs (filter, paginate)
* ``POST /discovery/sam_gov/poll``  — on-demand SAM.gov ingestion
* ``GET  /health``                  — readiness check

The UI and n8n both talk to these — not Postgres directly.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import _env  # noqa: F401 — populates os.environ from .env
from .agents.discovery import DiscoveryError, fetch_sam_gov_rfps
from .agents.screening import screen_rfp
from .config.loader import get_config
from .db.client import (
    db_cursor,
    get_rfp,
    latest_screening_for_rfp,
    list_rfps,
    ping,
    set_screening_override,
    upsert_rfp,
)
from .models.rfp import RFP, RFPSource, RFPStatus
from .models.screening import Recommendation, Screening
from .rag.retriever import find_similar_proposals

log = logging.getLogger(__name__)

app = FastAPI(title="Kaizen RFP POC", version="0.2.0")


# -- request/response schemas -----------------------------------------

class IngestRFPRequest(BaseModel):
    source: RFPSource = "manual"
    title: str
    agency: Optional[str] = None
    external_id: Optional[str] = None
    naics_codes: List[str] = Field(default_factory=list)
    due_date: Optional[datetime] = None
    value_estimate_low: Optional[int] = None
    value_estimate_high: Optional[int] = None
    full_text: Optional[str] = None
    source_url: Optional[str] = None
    dedupe_hash: Optional[str] = None


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


class DiscoveryPollRequest(BaseModel):
    naics_codes: Optional[List[str]] = None     # falls back to config
    lookback_days: int = 30
    limit: int = 50
    fetch_full_text: bool = True


class DiscoveryPollResult(BaseModel):
    new_rfps: List[RFP]
    count: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: bool


# -- health ------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_ok = ping()
    return HealthResponse(status="ok" if db_ok else "degraded", db=db_ok)


# -- RFP endpoints -----------------------------------------------------

@app.post("/rfp/ingest", response_model=RFP, status_code=201)
def ingest_rfp(body: IngestRFPRequest) -> RFP:
    rfp = RFP(**body.model_dump())
    return upsert_rfp(rfp)


@app.post("/rfp/upload", response_model=RFP, status_code=201)
async def ingest_rfp_pdf(
    file: UploadFile,
    title: Optional[str] = None,
    agency: Optional[str] = None,
) -> RFP:
    """Accept a PDF upload, extract text via pypdf, and persist as an RFP."""
    import io

    from pypdf import PdfReader

    raw = await file.read()
    try:
        reader = PdfReader(io.BytesIO(raw))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse PDF: {exc}")

    if not text:
        raise HTTPException(status_code=400, detail="PDF had no extractable text.")

    rfp = RFP(
        source="manual",
        title=title or file.filename or "Uploaded RFP",
        agency=agency,
        full_text=text,
    )
    return upsert_rfp(rfp)


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
    except Exception as exc:  # noqa: BLE001 — surfaced to client for POC debugging
        log.exception("Screening failed for %s", rfp_id)
        raise HTTPException(status_code=500, detail=f"Screening failed: {exc}")


@app.get("/rfp/{rfp_id}/similar-proposals", response_model=List[SimilarProposalResult])
def similar_proposals_endpoint(rfp_id: UUID, k: int = 3) -> List[SimilarProposalResult]:
    rfp = get_rfp(rfp_id)
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")
    query = "\n\n".join(
        p for p in [rfp.title, rfp.agency, rfp.full_text] if p
    )
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


@app.post("/rfp/{rfp_id}/override", status_code=204)
def override_screening_endpoint(rfp_id: UUID, body: OverrideRequest) -> None:
    screening = latest_screening_for_rfp(rfp_id)
    if not screening:
        raise HTTPException(status_code=404, detail="No screening found for this RFP")
    set_screening_override(screening.id, body.recommendation, body.reason)

    # Audit trail so the rubric-calibration story has data to work with later.
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log
                (entity_type, entity_id, action, actor, details)
            VALUES ('screening', %s, 'human_override', 'user', %s::jsonb)
            """,
            (
                str(screening.id),
                '{"recommendation": "%s", "reason": %s}'
                % (
                    body.recommendation,
                    ('"' + (body.reason or "").replace('"', '\\"') + '"')
                    if body.reason
                    else "null",
                ),
            ),
        )


# -- discovery ---------------------------------------------------------

@app.post("/discovery/sam_gov/poll", response_model=DiscoveryPollResult)
def poll_sam_gov(body: Optional[DiscoveryPollRequest] = None) -> DiscoveryPollResult:
    body = body or DiscoveryPollRequest()
    cfg = get_config()
    naics = body.naics_codes or cfg.sources.sam_gov.naics_filter
    if not naics:
        raise HTTPException(
            status_code=400,
            detail="No NAICS codes provided and none configured in sources.sam_gov.naics_filter",
        )
    try:
        from datetime import datetime as _dt
        from datetime import timedelta, timezone

        modified_since = _dt.now(timezone.utc) - timedelta(days=body.lookback_days)
        new_rfps = fetch_sam_gov_rfps(
            naics_codes=naics,
            modified_since=modified_since,
            limit=body.limit,
            fetch_full_text=body.fetch_full_text,
        )
    except DiscoveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return DiscoveryPollResult(new_rfps=new_rfps, count=len(new_rfps))
