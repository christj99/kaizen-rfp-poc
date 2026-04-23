from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

Recommendation = Literal["pursue", "maybe", "skip"]
EffortEstimate = Literal["low", "medium", "high"]
ConfidenceLevel = Literal["low", "medium", "high"]
RelevanceStrength = Literal["strong", "moderate", "weak"]
Severity = Literal["low", "medium", "high"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HardDisqualifierResult(BaseModel):
    """Per-disqualifier pass/fail check, per the rubric."""

    id: str
    triggered: bool
    evidence: Optional[str] = None
    reasoning: Optional[str] = None


class RubricDimensionScore(BaseModel):
    """One row of the weighted-dimension breakdown the model returns."""

    id: Optional[str] = None
    name: str
    weight: float
    score: int                      # 0-100 within this dimension
    reasoning: str
    evidence_citations: List[str] = Field(default_factory=list)


class SimilarProposalAnalysis(BaseModel):
    """Claude's explicit take on why each retrieved past proposal is relevant."""

    proposal_id: str                # UUID from retrieval, as string
    relevance_strength: RelevanceStrength
    why_relevant: str
    reusable_sections: List[str] = Field(default_factory=list)


class DealBreaker(BaseModel):
    """A concern that, if confirmed, would change the recommendation."""

    concern: str
    severity: Severity
    would_change_recommendation_to: Optional[Recommendation] = None
    how_to_verify: Optional[str] = None


class OpenQuestion(BaseModel):
    """An ambiguity in the RFP the proposals lead needs to resolve."""

    question: str
    why_it_matters: Optional[str] = None
    best_guess: Optional[str] = None


class ScreeningRationale(BaseModel):
    """Everything the agent produces beyond the top-level fit/recommendation."""

    recommendation_rationale: Optional[str] = None
    confidence_level: Optional[ConfidenceLevel] = None
    confidence_notes: Optional[str] = None
    hard_disqualifier_results: List[HardDisqualifierResult] = Field(default_factory=list)
    dimensions: List[RubricDimensionScore] = Field(default_factory=list)
    effort_reasoning: Optional[str] = None
    similar_past_proposals_analysis: List[SimilarProposalAnalysis] = Field(default_factory=list)
    calibration_notes: Optional[str] = None


class Screening(BaseModel):
    """Mirrors the ``screenings`` table. One per screening run; many per RFP."""

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
