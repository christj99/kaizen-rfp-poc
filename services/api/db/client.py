"""Thin psycopg2 helpers. Intentionally minimal — no ORM, no Alembic.

Grows opportunistically as agents need new persistence ops. Everything
goes through ``db_cursor`` for consistent transaction + cleanup handling.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from uuid import UUID

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from .. import _env  # noqa: F401 — populates os.environ from .env
from ..models.audit import AuditEntry
from ..models.draft import Draft, DraftContent, DraftSection
from ..models.draft_job import DraftJob
from ..models.past_proposal import PastProposal
from ..models.rfp import RFP
from ..models.screening import Screening

# Return UUID columns as uuid.UUID rather than str, so Python-side dict keys
# and equality comparisons line up with pydantic model fields.
psycopg2.extras.register_uuid()


def _connect():
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "kaizen_rfp"),
        user=os.environ.get("POSTGRES_USER", "kaizen"),
        password=os.environ.get("POSTGRES_PASSWORD", "kaizen_dev_password"),
    )
    # pgvector adapter so VECTOR columns round-trip as python lists.
    register_vector(conn)
    return conn


@contextlib.contextmanager
def db_cursor() -> Iterator[psycopg2.extras.DictCursor]:
    """Auto-committing cursor context manager. Rolls back on exception."""
    conn = _connect()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                yield cur
    finally:
        conn.close()


def ping() -> bool:
    try:
        with db_cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone()[0] == 1
    except Exception:
        return False


# -- audit_log ---------------------------------------------------------

def list_audit_entries(*, limit: int = 25) -> List[AuditEntry]:
    """Recent audit_log entries for the Dashboard activity feed."""
    with db_cursor() as cur:
        cur.execute(
            """SELECT id, entity_type, entity_id, action, actor, details, created_at
                 FROM audit_log
                ORDER BY created_at DESC
                LIMIT %s""",
            (limit,),
        )
        return [
            AuditEntry(
                id=r["id"],
                entity_type=r["entity_type"],
                entity_id=r["entity_id"],
                action=r["action"],
                actor=r["actor"],
                details=r["details"] or {},
                created_at=r["created_at"],
            )
            for r in cur.fetchall()
        ]


def write_audit(entry: AuditEntry) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log
                (id, entity_type, entity_id, action, actor, details, created_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                str(entry.id),
                entry.entity_type,
                str(entry.entity_id) if entry.entity_id else None,
                entry.action,
                entry.actor,
                json.dumps(entry.details, default=str),
                entry.created_at,
            ),
        )


# -- rfps --------------------------------------------------------------

def upsert_rfp(rfp: RFP) -> RFP:
    """Insert or, when ``dedupe_hash`` matches an existing row, return that row.

    Returns the canonical RFP (with the persisted ID — may differ from the
    one passed in if it was already in the DB).
    """
    with db_cursor() as cur:
        if rfp.dedupe_hash:
            cur.execute("SELECT id FROM rfps WHERE dedupe_hash = %s", (rfp.dedupe_hash,))
            row = cur.fetchone()
            if row:
                existing_id = row["id"]
                return get_rfp(existing_id)  # type: ignore[arg-type]
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
                str(rfp.id),
                rfp.source_type,
                rfp.source_adapter_version,
                json.dumps(rfp.source_metadata, default=str),
                rfp.external_id,
                rfp.title,
                rfp.agency,
                rfp.naics_codes,
                rfp.due_date,
                rfp.value_estimate_low,
                rfp.value_estimate_high,
                rfp.full_text,
                rfp.source_url,
                rfp.received_at,
                rfp.status,
                rfp.dedupe_hash,
            ),
        )
    return rfp


def _row_to_rfp(row: psycopg2.extras.DictRow) -> RFP:
    return RFP(
        id=row["id"],
        source_type=row["source_type"],
        source_adapter_version=row["source_adapter_version"],
        source_metadata=row["source_metadata"] or {},
        external_id=row["external_id"],
        title=row["title"],
        agency=row["agency"],
        naics_codes=list(row["naics_codes"]) if row["naics_codes"] else [],
        due_date=row["due_date"],
        value_estimate_low=row["value_estimate_low"],
        value_estimate_high=row["value_estimate_high"],
        full_text=row["full_text"],
        source_url=row["source_url"],
        received_at=row["received_at"],
        status=row["status"],
        dedupe_hash=row["dedupe_hash"],
    )


def get_rfp(rfp_id: UUID) -> Optional[RFP]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM rfps WHERE id = %s", (str(rfp_id),))
        row = cur.fetchone()
        return _row_to_rfp(row) if row else None


def list_rfps(
    *,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[RFP]:
    sql = "SELECT * FROM rfps"
    clauses: List[str] = []
    params: List[Any] = []
    if status:
        clauses.append("status = %s")
        params.append(status)
    if source_type:
        clauses.append("source_type = %s")
        params.append(source_type)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY received_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    with db_cursor() as cur:
        cur.execute(sql, params)
        return [_row_to_rfp(r) for r in cur.fetchall()]


def list_rfps_with_screening(
    *,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List RFPs along with the most-recent screening summary inline.

    Used by Dashboard / RFPs table — avoids N+1 calls to /rfp/{id}. Returns
    plain dicts to keep the typing flexible (UI just needs fit_score +
    recommendation alongside RFP fields).
    """
    where: List[str] = []
    params: List[Any] = []
    if status:
        where.append("r.status = %s")
        params.append(status)
    if source_type:
        where.append("r.source_type = %s")
        params.append(source_type)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT r.*,
               s.id            AS screening_id,
               s.fit_score     AS fit_score,
               s.recommendation AS recommendation,
               s.effort_estimate AS effort_estimate,
               s.created_at    AS screening_created_at,
               s.human_override AS human_override
          FROM rfps r
     LEFT JOIN LATERAL (
                  SELECT id, fit_score, recommendation, effort_estimate,
                         created_at, human_override
                    FROM screenings
                   WHERE rfp_id = r.id
                   ORDER BY created_at DESC
                   LIMIT 1
              ) s ON TRUE
        {where_sql}
        ORDER BY r.received_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with db_cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def update_rfp_status(rfp_id: UUID, status: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE rfps SET status = %s WHERE id = %s",
            (status, str(rfp_id)),
        )


# -- screenings --------------------------------------------------------

def insert_screening(screening: Screening) -> Screening:
    with db_cursor() as cur:
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
                str(screening.id),
                str(screening.rfp_id),
                screening.fit_score,
                screening.recommendation,
                screening.rationale.model_dump_json(),
                screening.effort_estimate,
                json.dumps([db.model_dump() for db in screening.deal_breakers], default=str),
                json.dumps([oq.model_dump() for oq in screening.open_questions], default=str),
                [str(pid) for pid in screening.similar_proposal_ids],
                screening.model_version,
                screening.rubric_version,
                screening.created_at,
                screening.human_override,
                screening.human_override_reason,
            ),
        )
    return screening


def _row_to_screening(row: psycopg2.extras.DictRow) -> Screening:
    from ..models.screening import ScreeningRationale

    rationale_raw = row["rationale"] or {}
    deal_raw = row["deal_breakers"] or []
    open_q_raw = row["open_questions"] or []
    return Screening(
        id=row["id"],
        rfp_id=row["rfp_id"],
        fit_score=row["fit_score"],
        recommendation=row["recommendation"],
        rationale=ScreeningRationale.model_validate(rationale_raw),
        effort_estimate=row["effort_estimate"],
        deal_breakers=deal_raw,
        open_questions=open_q_raw,
        similar_proposal_ids=list(row["similar_proposal_ids"]) if row["similar_proposal_ids"] else [],
        model_version=row["model_version"],
        rubric_version=row["rubric_version"],
        created_at=row["created_at"],
        human_override=row["human_override"],
        human_override_reason=row["human_override_reason"],
    )


def latest_screening_for_rfp(rfp_id: UUID) -> Optional[Screening]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM screenings
             WHERE rfp_id = %s
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (str(rfp_id),),
        )
        row = cur.fetchone()
        return _row_to_screening(row) if row else None


def set_screening_override(
    screening_id: UUID, override: str, reason: Optional[str]
) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE screenings
               SET human_override = %s, human_override_reason = %s
             WHERE id = %s
            """,
            (override, reason, str(screening_id)),
        )


# -- drafts -----------------------------------------------------------

def insert_draft(
    draft: Draft,
    *,
    overall_metadata: Optional[Dict[str, Any]] = None,
) -> Draft:
    """Persist a Draft. ``overall_metadata`` (from Claude's drafting call) is
    stored inside ``drafts.content.meta`` so the export route can reproduce
    the reviewer-facing provenance block later.
    """
    content_payload: Dict[str, Any] = draft.content.model_dump(mode="json")
    if overall_metadata:
        content_payload["meta"] = overall_metadata

    with db_cursor() as cur:
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
                str(draft.id),
                str(draft.rfp_id),
                str(draft.screening_id) if draft.screening_id else None,
                json.dumps(content_payload, default=str),
                [str(pid) for pid in draft.retrieved_proposal_ids],
                draft.status,
                draft.created_at,
            ),
        )
    return draft


def _row_to_draft(row: psycopg2.extras.DictRow) -> Tuple[Draft, Dict[str, Any]]:
    raw = row["content"] or {}
    # Pull the overall_metadata blob out so the DraftContent model stays clean.
    overall_meta = raw.pop("meta", {}) if isinstance(raw, dict) else {}
    content = DraftContent.model_validate(raw) if raw else DraftContent()
    draft = Draft(
        id=row["id"],
        rfp_id=row["rfp_id"],
        screening_id=row["screening_id"],
        content=content,
        retrieved_proposal_ids=list(row["retrieved_proposal_ids"]) if row["retrieved_proposal_ids"] else [],
        status=row["status"],
        created_at=row["created_at"],
    )
    return draft, overall_meta


def get_draft(draft_id: UUID) -> Optional[Tuple[Draft, Dict[str, Any]]]:
    """Return ``(draft, overall_metadata)`` or ``None``."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM drafts WHERE id = %s", (str(draft_id),))
        row = cur.fetchone()
        return _row_to_draft(row) if row else None


def latest_draft_for_rfp(rfp_id: UUID) -> Optional[Tuple[Draft, Dict[str, Any]]]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM drafts WHERE rfp_id = %s ORDER BY created_at DESC LIMIT 1",
            (str(rfp_id),),
        )
        row = cur.fetchone()
        return _row_to_draft(row) if row else None


# -- draft_jobs (Phase 3B async drafting) -----------------------------

def insert_draft_job(job: DraftJob) -> DraftJob:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO draft_jobs
                (id, rfp_id, status, started_at, completed_at,
                 draft_id, error_message, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(job.id),
                str(job.rfp_id),
                job.status,
                job.started_at,
                job.completed_at,
                str(job.draft_id) if job.draft_id else None,
                job.error_message,
                job.created_at,
            ),
        )
    return job


def update_draft_job(
    job_id: UUID,
    *,
    status: Optional[str] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    draft_id: Optional[UUID] = None,
    error_message: Optional[str] = None,
) -> None:
    """Patch a draft_jobs row. Only non-None kwargs are written."""
    sets: List[str] = []
    params: List[Any] = []
    if status is not None:
        sets.append("status = %s"); params.append(status)
    if started_at is not None:
        sets.append("started_at = %s"); params.append(started_at)
    if completed_at is not None:
        sets.append("completed_at = %s"); params.append(completed_at)
    if draft_id is not None:
        sets.append("draft_id = %s"); params.append(str(draft_id))
    if error_message is not None:
        sets.append("error_message = %s"); params.append(error_message)
    if not sets:
        return
    params.append(str(job_id))
    with db_cursor() as cur:
        cur.execute(
            f"UPDATE draft_jobs SET {', '.join(sets)} WHERE id = %s",
            params,
        )


def _row_to_draft_job(row: psycopg2.extras.DictRow) -> DraftJob:
    return DraftJob(
        id=row["id"],
        rfp_id=row["rfp_id"],
        status=row["status"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        draft_id=row["draft_id"],
        error_message=row["error_message"],
        created_at=row["created_at"],
    )


def get_draft_job(job_id: UUID) -> Optional[DraftJob]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM draft_jobs WHERE id = %s", (str(job_id),))
        row = cur.fetchone()
        return _row_to_draft_job(row) if row else None


# -- past_proposals + chunks ------------------------------------------

def insert_past_proposal(
    proposal: PastProposal,
    chunks: Sequence[Tuple[str, str, Sequence[float]]],
) -> None:
    """Insert a proposal row + its embedding chunks in one transaction.

    ``chunks`` is ``[(section_name, chunk_text, embedding), ...]``.
    """
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO past_proposals
                (id, title, agency, submitted_date, outcome,
                 contract_value, full_text, sections, metadata)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                str(proposal.id),
                proposal.title,
                proposal.agency,
                proposal.submitted_date,
                proposal.outcome,
                proposal.contract_value,
                proposal.full_text,
                json.dumps(proposal.sections),
                json.dumps(proposal.metadata, default=str),
            ),
        )
        for section_name, chunk_text, embedding in chunks:
            cur.execute(
                """
                INSERT INTO proposal_chunks
                    (past_proposal_id, chunk_section, chunk_text, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                (str(proposal.id), section_name, chunk_text, list(embedding)),
            )


def delete_all_past_proposals() -> int:
    """Wipe past_proposals + proposal_chunks. Returns rows deleted."""
    with db_cursor() as cur:
        cur.execute("DELETE FROM past_proposals")
        # CASCADE on proposal_chunks FK handles the chunks
        return cur.rowcount


def past_proposal_count() -> int:
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM past_proposals")
        return cur.fetchone()[0]


def _row_to_past_proposal(row: psycopg2.extras.DictRow) -> PastProposal:
    sections = row["sections"] or {}
    metadata = row["metadata"] or {}
    return PastProposal(
        id=row["id"],
        title=row["title"],
        agency=row["agency"],
        submitted_date=row["submitted_date"],
        outcome=row["outcome"],
        contract_value=row["contract_value"],
        full_text=row["full_text"],
        sections=sections,
        metadata=metadata,
    )


def get_past_proposal(proposal_id: UUID) -> Optional[PastProposal]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM past_proposals WHERE id = %s", (str(proposal_id),))
        row = cur.fetchone()
        return _row_to_past_proposal(row) if row else None


def get_past_proposals(proposal_ids: Iterable[UUID]) -> List[PastProposal]:
    ids = [str(pid) for pid in proposal_ids]
    if not ids:
        return []
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM past_proposals WHERE id = ANY(%s::uuid[])", (ids,)
        )
        return [_row_to_past_proposal(r) for r in cur.fetchall()]


def list_past_proposals(limit: int = 200) -> List[PastProposal]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM past_proposals ORDER BY submitted_date DESC NULLS LAST LIMIT %s",
            (limit,),
        )
        return [_row_to_past_proposal(r) for r in cur.fetchall()]


def find_similar_chunks(
    embedding: Sequence[float],
    *,
    k: int = 20,
) -> List[Dict[str, Any]]:
    """Return top-k chunks by cosine distance.

    Each row has: past_proposal_id, chunk_section, chunk_text, distance.
    Callers aggregate to proposal level themselves (see rag.retriever).
    """
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT past_proposal_id, chunk_section, chunk_text,
                   embedding <=> %s::vector AS distance
              FROM proposal_chunks
             ORDER BY embedding <=> %s::vector
             LIMIT %s
            """,
            (list(embedding), list(embedding), k),
        )
        return [dict(r) for r in cur.fetchall()]
