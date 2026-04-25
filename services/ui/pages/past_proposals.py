"""Past Proposals — searchable list + detail view with sections.

Title/agency search hits ``/past_proposals?search=...``. The
"semantic search" affordance (RAG over chunks) lives behind the chat
widget; this page is intentionally simple — pick a proposal, read it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from .. import api_client
from ..components import api_health_banner, empty_state, section_divider


def _format_value(pp: Dict[str, Any]) -> str:
    v = pp.get("contract_value")
    return f"${v:,}" if v else "—"


def _outcome_chip(outcome: Optional[str]) -> str:
    if not outcome:
        return ""
    color = {"won": "#166534", "lost": "#7f1d1d", "withdrawn": "#475569"}.get(outcome, "#475569")
    bg = {"won": "#dcfce7", "lost": "#fee2e2", "withdrawn": "#e2e8f0"}.get(outcome, "#e2e8f0")
    return (f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
            f"font-size:0.72rem;font-weight:700;background:{bg};color:{color};"
            f"text-transform:uppercase;letter-spacing:0.05em;'>{outcome}</span>")


def render() -> None:
    st.title("Past Proposals")
    if not api_health_banner():
        return

    # --- search bar ---
    q = st.text_input("Search by title or agency", key="pp_search", placeholder="e.g. healthcare, DOC, ITA")
    proposals = api_client.list_past_proposals(search=(q or None), limit=200)

    if not proposals:
        empty_state(
            "No past proposals found.",
            "Re-index via `python -m services.api.rag.indexer` if the corpus looks empty.",
            icon=":material/folder_off:",
        )
        return

    # --- list view ---
    section_divider(f"{len(proposals)} proposals")
    selected_id = st.session_state.get("selected_past_proposal_id")

    for pp in proposals:
        cols = st.columns([4, 1, 1, 1])
        with cols[0]:
            st.markdown(
                f"<div style='font-weight:600;'>{pp.get('title') or '(no title)'}</div>"
                f"<div style='color:#64748b;font-size:0.85rem;'>{pp.get('agency') or '—'} · "
                f"{pp.get('submitted_date') or '—'}</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.markdown(_outcome_chip(pp.get("outcome")), unsafe_allow_html=True)
        with cols[2]:
            st.markdown(f"<span style='color:#475569;font-size:0.9rem;'>{_format_value(pp)}</span>",
                        unsafe_allow_html=True)
        with cols[3]:
            if st.button("Open", key=f"pp_open_{pp['id']}", use_container_width=True):
                st.session_state["selected_past_proposal_id"] = pp["id"]
                selected_id = pp["id"]
        st.markdown("<hr style='margin:0.4rem 0;border:0;border-top:1px solid #f1f5f9;'>",
                    unsafe_allow_html=True)

    # --- detail view ---
    if selected_id:
        try:
            pp = api_client.get_past_proposal(selected_id)
        except api_client.APIError as e:
            st.error(f"Couldn't load proposal: {e}")
            return

        st.divider()
        section_divider("Detail")
        st.subheader(pp.get("title") or "(no title)")
        meta_cols = st.columns(4)
        meta_cols[0].metric("Agency", pp.get("agency") or "—")
        meta_cols[1].metric("Outcome", (pp.get("outcome") or "—").upper())
        meta_cols[2].metric("Value", _format_value(pp))
        meta_cols[3].metric("Submitted", str(pp.get("submitted_date") or "—"))

        sections = pp.get("sections") or {}
        if not sections:
            empty_state("No sections parsed for this proposal.", icon=":material/description:")
            return

        # Highlight LESSONS LEARNED prominently for lost proposals.
        lessons_keys = [k for k in sections if "lessons" in k.lower()]
        if pp.get("outcome") == "lost" and lessons_keys:
            for k in lessons_keys:
                st.warning(f"### {k}\n\n{sections[k]}")

        for name, body in sections.items():
            if name in lessons_keys:
                continue
            with st.expander(name, expanded=False):
                st.markdown(body)
