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
from .past_proposal import PastProposal, ProposalOutcome, ProposalSections
from .rfp import RFP, RFPSource, RFPStatus
from .screening import (
    DealBreaker,
    EffortEstimate,
    OpenQuestion,
    Recommendation,
    RubricDimensionScore,
    Screening,
    ScreeningRationale,
)

__all__ = [
    "AuditActor",
    "AuditEntry",
    "DealBreaker",
    "Draft",
    "DraftContent",
    "DraftSection",
    "DraftSectionProvenance",
    "DraftStatus",
    "EffortEstimate",
    "OpenQuestion",
    "PastProposal",
    "ProposalOutcome",
    "ProposalSections",
    "RFP",
    "RFPSource",
    "RFPStatus",
    "Recommendation",
    "RubricDimensionScore",
    "Screening",
    "ScreeningRationale",
]
