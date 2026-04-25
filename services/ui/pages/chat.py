"""Chat — full-page conversation with the proposals assistant.

Streamlit's layout model doesn't support a floating bottom-right widget
without aggressive CSS hacks; per the Phase 5 plan's explicit fallback,
this is a dedicated nav-item Chat page.

The backend ``POST /chat`` runs Claude with tool calling against the 5
tools declared in ``chat_system.txt`` (search_rfps, search_past_proposals,
get_rfp_detail, get_past_proposal_detail, get_screening_detail).
"""

from __future__ import annotations

from typing import List

import streamlit as st

from .. import api_client
from ..components import api_health_banner


_HISTORY_KEY = "chat_history"
_TOOLS_KEY = "chat_last_tool_calls"


def render() -> None:
    st.title("Chat")
    if not api_health_banner():
        return

    if _HISTORY_KEY not in st.session_state:
        st.session_state[_HISTORY_KEY] = []

    st.caption(
        "Ask about RFPs, past proposals, or screening results. The assistant "
        "is grounded in the actual data via tool calls — it'll cite specific "
        "records when answering. Try: _\"show me high-fit RFPs from this week\"_ "
        "or _\"how did we do on healthcare-data work?\"_"
    )

    # Replay history
    history: List[dict] = st.session_state[_HISTORY_KEY]
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Show last response's tool trace (collapsible) if any
    last_tools = st.session_state.get(_TOOLS_KEY) or []
    if last_tools:
        with st.expander(f"Tool calls in last response  ({len(last_tools)})", expanded=False):
            for t in last_tools:
                st.markdown(
                    f"**{t['tool']}**  \n"
                    f"input: `{t['input']}`  \n"
                    f"output: `{t['output_summary']}`"
                )

    # Reset button + chat input
    cols = st.columns([5, 1])
    with cols[1]:
        if st.button(":material/refresh: New chat", use_container_width=True):
            st.session_state[_HISTORY_KEY] = []
            st.session_state[_TOOLS_KEY] = []
            st.rerun()

    if prompt := st.chat_input("Ask about RFPs, screenings, or past proposals…"):
        st.session_state[_HISTORY_KEY].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching the system…"):
                try:
                    resp = api_client.chat(st.session_state[_HISTORY_KEY])
                except api_client.APIError as e:
                    msg = f"_Couldn't reach the chat backend: {e}_"
                    st.markdown(msg)
                    st.session_state[_HISTORY_KEY].append({"role": "assistant", "content": msg})
                    return

            st.markdown(resp.get("content") or "_(empty response)_")
            st.session_state[_HISTORY_KEY].append(
                {"role": "assistant", "content": resp.get("content") or ""}
            )
            st.session_state[_TOOLS_KEY] = resp.get("tool_calls") or []
