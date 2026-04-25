"""Tiny layout helpers used across pages."""

from __future__ import annotations

from typing import Iterable, Tuple

import streamlit as st

import api_client


def api_health_banner() -> bool:
    """Show a non-fatal banner if the API is unreachable. Returns True if
    the page should continue rendering."""
    try:
        h = api_client.health()
        if h.get("status") == "ok" and h.get("db"):
            return True
        st.warning(
            "API responded but reports degraded state. "
            f"Detail: {h}. Some pages may be empty."
        )
        return True
    except api_client.APIError as exc:
        st.error(
            "API unavailable — check that `./scripts/demo_start.ps1` is running. "
            f"Detail: {exc}"
        )
        return False
    except Exception as exc:
        st.error(f"Unexpected error reaching the API: {exc}")
        return False


def empty_state(title: str, hint: str = "", icon: str = "📭") -> None:
    """Friendly empty-state block. Avoids blank-screen demo killers.

    ``icon`` should be a plain Unicode emoji — the surrounding wrapper is
    rendered via ``unsafe_allow_html``, where Streamlit doesn't parse
    ``:material/...:`` shortcodes (those only work in widget labels,
    st.tabs, and st.markdown without unsafe_allow_html).
    """
    st.markdown(
        f"<div style='padding:2.5rem 1rem;text-align:center;color:#64748b;'>"
        f"<div style='font-size:2rem;margin-bottom:0.5rem;'>{icon}</div>"
        f"<div style='font-size:1.05rem;font-weight:600;color:#334155;'>{title}</div>"
        f"<div style='margin-top:0.5rem;font-size:0.92rem;'>{hint}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def section_divider(label: str) -> None:
    st.markdown(
        f"<div style='margin-top:1.25rem;margin-bottom:0.5rem;"
        f"font-size:0.78rem;letter-spacing:0.08em;text-transform:uppercase;"
        f"color:#64748b;font-weight:700;'>{label}</div>",
        unsafe_allow_html=True,
    )


def kv_grid(rows: Iterable[Tuple[str, str]], cols: int = 2) -> None:
    """Render label/value pairs in N columns. Values can be raw strings or
    HTML (badges, links). Uses st.markdown(unsafe_allow_html=True) so all
    callers passing user-supplied data should escape first."""
    rows = list(rows)
    if not rows:
        return
    columns = st.columns(cols)
    for i, (label, value) in enumerate(rows):
        with columns[i % cols]:
            st.markdown(
                f"<div style='margin-bottom:0.5rem;'>"
                f"<div style='font-size:0.7rem;color:#64748b;letter-spacing:0.06em;"
                f"text-transform:uppercase;font-weight:600;'>{label}</div>"
                f"<div style='font-size:0.95rem;color:#0f172a;'>{value}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
