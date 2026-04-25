"""Streamlit entrypoint — Kaizen RFP POC dashboard.

Multi-page app via ``st.navigation``. Each page module under ``screens/``
is a callable that draws itself.

Streamlit runs this file as a script (``streamlit run services/ui/app.py``),
not as a Python package, so we insert the script's directory into ``sys.path``
before any sibling imports. ``screens/`` is deliberately NOT named ``pages/``
because Streamlit auto-discovers a sibling ``pages/`` directory and would
override the navigation defined here.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `api_client`, `components`, `screens` importable as bare names.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

st.set_page_config(
    page_title="Kaizen RFP POC",
    page_icon=":memo:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----- pages -----
from screens import dashboard as page_dashboard            # noqa: E402
from screens import rfp_detail as page_rfp_detail          # noqa: E402
from screens import past_proposals as page_past_proposals  # noqa: E402
from screens import rubric_editor as page_rubric_editor    # noqa: E402
from screens import settings as page_settings              # noqa: E402
from screens import sql_admin as page_sql_admin            # noqa: E402
from screens import chat as page_chat                      # noqa: E402

# Sidebar header sits above the auto-generated nav.
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

# url_path on every Page is required because each module exports a callable
# named ``render`` — without it, st.navigation's pathname inference collapses
# every page to the same URL and raises StreamlitAPIException.
nav = st.navigation([
    st.Page(page_dashboard.render,       title="Dashboard",      icon=":material/dashboard:",   url_path="dashboard",      default=True),
    st.Page(page_rfp_detail.render,      title="RFP Detail",     icon=":material/description:", url_path="rfp"),
    st.Page(page_past_proposals.render,  title="Past Proposals", icon=":material/folder_open:", url_path="past_proposals"),
    st.Page(page_rubric_editor.render,   title="Rubric",         icon=":material/tune:",        url_path="rubric"),
    st.Page(page_settings.render,        title="Settings",       icon=":material/settings:",    url_path="settings"),
    st.Page(page_sql_admin.render,       title="SQL Console",    icon=":material/database:",    url_path="sql"),
    st.Page(page_chat.render,            title="Chat",           icon=":material/chat:",        url_path="chat"),
])
nav.run()
