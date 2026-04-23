from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

RFPSource = Literal["sam_gov", "email", "manual"]
RFPStatus = Literal[
    "new",
    "screened",
    "in_draft",
    "submitted",
    "won",
    "lost",
    "dismissed",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RFP(BaseModel):
    """Mirrors the ``rfps`` table. One record per ingested opportunity."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    source: RFPSource
    external_id: Optional[str] = None
    title: str
    agency: Optional[str] = None
    naics_codes: List[str] = Field(default_factory=list)
    due_date: Optional[datetime] = None
    value_estimate_low: Optional[int] = None
    value_estimate_high: Optional[int] = None
    full_text: Optional[str] = None
    source_url: Optional[str] = None
    received_at: datetime = Field(default_factory=_utcnow)
    status: RFPStatus = "new"
    dedupe_hash: Optional[str] = None
