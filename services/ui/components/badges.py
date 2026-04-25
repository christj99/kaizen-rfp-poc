"""Badge components — small inline HTML pills with consistent colors.

Color discipline (per Phase 5 plan): same colors mean the same thing
on every page. Anyone touching this should keep the palette stable.
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

# Tailwind-ish 100/700 pairings — readable on white, professional.
_BADGE_STYLE = (
    "display:inline-block;padding:2px 10px;border-radius:999px;"
    "font-size:0.75rem;font-weight:600;letter-spacing:0.02em;"
    "background:{bg};color:{fg};"
)

_RECO_COLORS = {
    "pursue": ("#dcfce7", "#166534"),
    "maybe":  ("#fef9c3", "#854d0e"),
    "skip":   ("#fee2e2", "#991b1b"),
}

_SEVERITY_COLORS = {
    "low":    ("#e0e7ff", "#3730a3"),
    "medium": ("#fef3c7", "#92400e"),
    "high":   ("#fee2e2", "#991b1b"),
}

_SOURCE_COLORS = {
    "email":         ("#cffafe", "#155e75"),
    "sam_gov":       ("#ede9fe", "#5b21b6"),
    "manual_upload": ("#e2e8f0", "#1e293b"),
    "url_ingest":    ("#fce7f3", "#9d174d"),
}

_STATUS_COLORS = {
    "new":                  ("#e0f2fe", "#075985"),
    "screened":             ("#dcfce7", "#166534"),
    "in_draft":             ("#fef9c3", "#854d0e"),
    "submitted":            ("#ede9fe", "#5b21b6"),
    "won":                  ("#bbf7d0", "#14532d"),
    "lost":                 ("#fecaca", "#7f1d1d"),
    "dismissed":            ("#e2e8f0", "#475569"),
    "needs_manual_review":  ("#fed7aa", "#9a3412"),
}

_PROVENANCE_COLORS = {
    "static":    ("#e2e8f0", "#1e293b"),
    "retrieved": ("#cffafe", "#155e75"),
    "generated": ("#fef3c7", "#92400e"),
}


def _pill(label: str, bg: str, fg: str) -> str:
    return f"<span style='{_BADGE_STYLE.format(bg=bg, fg=fg)}'>{label}</span>"


def fit_score_badge(score: Optional[int]) -> str:
    """Color-coded fit score: green ≥75, yellow 50-74, red <50, grey if None."""
    if score is None:
        return _pill("— no score", "#e2e8f0", "#475569")
    if score >= 75:
        return _pill(f"{score} / 100", "#dcfce7", "#166534")
    if score >= 50:
        return _pill(f"{score} / 100", "#fef9c3", "#854d0e")
    return _pill(f"{score} / 100", "#fee2e2", "#991b1b")


def recommendation_badge(rec: Optional[str]) -> str:
    if not rec:
        return _pill("not assessed", "#e2e8f0", "#475569")
    bg, fg = _RECO_COLORS.get(rec, ("#e2e8f0", "#475569"))
    return _pill(rec, bg, fg)


def severity_badge(severity: Optional[str]) -> str:
    if not severity:
        return _pill("?", "#e2e8f0", "#475569")
    bg, fg = _SEVERITY_COLORS.get(severity, ("#e2e8f0", "#475569"))
    return _pill(severity, bg, fg)


def source_badge(source_type: Optional[str]) -> str:
    label = {"email": "Email", "sam_gov": "SAM.gov",
             "manual_upload": "Manual upload", "url_ingest": "URL ingest"}.get(source_type or "", source_type or "—")
    bg, fg = _SOURCE_COLORS.get(source_type or "", ("#e2e8f0", "#475569"))
    return _pill(label, bg, fg)


def status_badge(status: Optional[str]) -> str:
    if not status:
        return _pill("—", "#e2e8f0", "#475569")
    bg, fg = _STATUS_COLORS.get(status, ("#e2e8f0", "#475569"))
    return _pill(status.replace("_", " "), bg, fg)


def provenance_badge(provenance: Optional[str]) -> str:
    if not provenance:
        return _pill("—", "#e2e8f0", "#475569")
    bg, fg = _PROVENANCE_COLORS.get(provenance, ("#e2e8f0", "#475569"))
    return _pill(provenance, bg, fg)
