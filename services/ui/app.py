"""Streamlit entrypoint — Kaizen RFP POC dashboard.

Multi-page app via ``st.navigation``. Each page module under ``pages/``
is a callable that draws itself; nothing outside this file calls
Streamlit setup helpers, which keeps page modules importable in
isolation for testing.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Kaizen RFP POC",
    page_icon=":memo:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----- pages -----
from .pages import dashboard as page_dashboard          # noqa: E402
from .pages import rfp_detail as page_rfp_detail        # noqa: E402
from .pages import past_proposals as page_past_proposals  # noqa: E402
from .pages import rubric_editor as page_rubric_editor  # noqa: E402
from .pages import settings as page_settings            # noqa: E402
from .pages import chat as page_chat                    # noqa: E402

# Header inside the sidebar — sits above the auto-generated nav.
with st.sidebar:
    st.markdown(
        "<div style='padding:0.5rem 0 0.75rem 0;'>"
        "<div style='font-size:0.7rem;letter-spacing:0.12em;color:#64748b;"
        "font-weight:700;text-transform:uppercase;'>Meridian Data Solutions</div>"
        "<div style='font-size:1.15rem;font-weight:700;color:#0F766E;"
        "margin-top:0.1rem;'>RFP Pipeline</div>"
        "</div>",
        unsafe_allow_html=True,
    )

nav = st.navigation([
    st.Page(page_dashboard.render,       title="Dashboard",      icon=":material/dashboard:",        default=True),
    st.Page(page_rfp_detail.render,      title="RFP Detail",     icon=":material/description:"),
    st.Page(page_past_proposals.render,  title="Past Proposals", icon=":material/folder_open:"),
    st.Page(page_rubric_editor.render,   title="Rubric",         icon=":material/tune:"),
    st.Page(page_settings.render,        title="Settings",       icon=":material/settings:"),
    st.Page(page_chat.render,            title="Chat",           icon=":material/chat:"),
])
nav.run()
