"""Tiny reusable Streamlit components — badges, score chips, cards.

Kept intentionally small so every page stays consistent without a CSS
framework. Streamlit's native widgets do the heavy lifting; these
helpers just standardize colors and labels.
"""

from .badges import (
    fit_score_badge,
    provenance_badge,
    recommendation_badge,
    severity_badge,
    source_badge,
    status_badge,
)
from .layout import api_health_banner, empty_state, kv_grid, section_divider

__all__ = [
    "api_health_banner",
    "empty_state",
    "fit_score_badge",
    "kv_grid",
    "provenance_badge",
    "recommendation_badge",
    "section_divider",
    "severity_badge",
    "source_badge",
    "status_badge",
]
