"""Typed contracts mirroring the database schema.

These are the types that flow across agents, API boundaries, and the UI —
anything that needs to be serialized should end up in one of them.
"""

from .audit import AuditActor, AuditEntry
from .draft import (
    Draft,
    DraftContent,
    DraftSection,
    DraftSectionProvenance,
    DraftStatus,
)
from .past_proposal import PastProposal, ProposalOutcome
from .rfp import RFP, RFPSource, RFPStatus
from .screening import (
    ConfidenceLevel,
    DealBreaker,
    EffortEstimate,
    HardDisqualifierResult,
    OpenQuestion,
    Recommendation,
    RelevanceStrength,
    RubricDimensionScore,
    Screening,
    ScreeningRationale,
    Severity,
    SimilarProposalAnalysis,
)

__all__ = [
    "AuditActor",
    "AuditEntry",
    "ConfidenceLevel",
    "DealBreaker",
    "HardDisqualifierResult",
    "RelevanceStrength",
    "Severity",
    "SimilarProposalAnalysis",
    "Draft",
    "DraftContent",
    "DraftSection",
    "DraftSectionProvenance",
    "DraftStatus",
    "EffortEstimate",
    "OpenQuestion",
    "PastProposal",
    "ProposalOutcome",
    "RFP",
    "RFPSource",
    "RFPStatus",
    "Recommendation",
    "RubricDimensionScore",
    "Screening",
    "ScreeningRationale",
]
