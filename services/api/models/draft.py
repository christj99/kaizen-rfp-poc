from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

DraftStatus = Literal["generated", "reviewed", "approved"]

# How each section's content came to be. Surfaced in the UI so reviewers can
# trust "boilerplate" sections without re-reading them, and scrutinize
# "generated" ones.
DraftSectionProvenance = Literal["static", "retrieved", "generated"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DraftSection(BaseModel):
    name: str
    content: str
    provenance: DraftSectionProvenance
    source_proposal_id: Optional[UUID] = None       # for 'retrieved' sections
    confidence: Optional[float] = None              # 0.0 - 1.0
    needs_review: bool = False
    notes: Optional[str] = None                     # why flagged, caveats, etc.


class DraftContent(BaseModel):
    sections: List[DraftSection] = Field(default_factory=list)


class Draft(BaseModel):
    """Mirrors the ``drafts`` table."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    rfp_id: UUID
    screening_id: Optional[UUID] = None
    content: DraftContent = Field(default_factory=DraftContent)
    retrieved_proposal_ids: List[UUID] = Field(default_factory=list)
    status: DraftStatus = "generated"
    created_at: datetime = Field(default_factory=_utcnow)
