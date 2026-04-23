from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

AuditActor = Literal["system", "user", "claude"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditEntry(BaseModel):
    """Mirrors the ``audit_log`` table.

    Used for: LLM call bookkeeping (tokens, model, rubric version), human
    overrides on screenings, and any state transition reviewers might need to
    reconstruct after the fact.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    action: str
    actor: AuditActor = "system"
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
