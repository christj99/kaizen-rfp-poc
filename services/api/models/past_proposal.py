from __future__ import annotations

from datetime import date
from typing import Any, Dict, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

ProposalOutcome = Literal["won", "lost", "withdrawn"]


class ProposalSections(BaseModel):
    """Canonical section set used for retrieval + drafting."""

    exec_summary: Optional[str] = None
    qualifications: Optional[str] = None
    technical: Optional[str] = None
    pricing: Optional[str] = None
    attachments: Optional[str] = None


class PastProposal(BaseModel):
    """Mirrors the ``past_proposals`` table."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    title: Optional[str] = None
    agency: Optional[str] = None
    submitted_date: Optional[date] = None
    outcome: Optional[ProposalOutcome] = None
    contract_value: Optional[int] = None
    full_text: Optional[str] = None
    sections: ProposalSections = Field(default_factory=ProposalSections)
    metadata: Dict[str, Any] = Field(default_factory=dict)
