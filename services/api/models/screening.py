from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

Recommendation = Literal["pursue", "maybe", "skip"]
EffortEstimate = Literal["low", "medium", "high"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RubricDimensionScore(BaseModel):
    """One row of the rubric breakdown the model returns."""

    name: str
    weight: int
    score: int                    # 0-100 within this dimension
    weighted_score: float         # score * weight / 100 — convenience, model or caller may fill
    reasoning: str
    evidence: List[str] = Field(default_factory=list)


class DealBreaker(BaseModel):
    """A hard-disqualifier check result."""

    criterion: str
    triggered: bool
    evidence: Optional[str] = None


class OpenQuestion(BaseModel):
    """An unknown the model wants a human to confirm before pursuing."""

    question: str
    why_it_matters: Optional[str] = None


class ScreeningRationale(BaseModel):
    """Structured rubric breakdown that Claude is expected to produce."""

    dimensions: List[RubricDimensionScore] = Field(default_factory=list)
    summary: Optional[str] = None


class Screening(BaseModel):
    """Mirrors the ``screenings`` table. Zero or more per RFP."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4)
    rfp_id: UUID
    fit_score: Optional[int] = None                 # 0-100, weighted
    recommendation: Optional[Recommendation] = None
    rationale: ScreeningRationale = Field(default_factory=ScreeningRationale)
    effort_estimate: Optional[EffortEstimate] = None
    deal_breakers: List[DealBreaker] = Field(default_factory=list)
    open_questions: List[OpenQuestion] = Field(default_factory=list)
    similar_proposal_ids: List[UUID] = Field(default_factory=list)
    model_version: Optional[str] = None
    rubric_version: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    human_override: Optional[Recommendation] = None
    human_override_reason: Optional[str] = None
