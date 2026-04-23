from __future__ import annotations

from datetime import date
from typing import Any, Dict, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

ProposalOutcome = Literal["won", "lost", "withdrawn"]


class PastProposal(BaseModel):
    """Mirrors the ``past_proposals`` table.

    ``sections`` is a free-form dict keyed by human-readable section name
    (``"Executive Summary"``, ``"Technical Approach"`` …). The rationale:
    proposal templates evolve and different clients require different
    sections, so pinning the shape in pydantic would guarantee future drift.
    The drafting template is the authoritative canonical set.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    title: Optional[str] = None
    agency: Optional[str] = None
    submitted_date: Optional[date] = None
    outcome: Optional[ProposalOutcome] = None
    contract_value: Optional[int] = None
    full_text: Optional[str] = None
    sections: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
