"""Streamlit entrypoint — Phase 0 placeholder.

The full multi-page app is built in Phase 5.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Kaizen RFP POC", page_icon=":memo:", layout="wide")

st.title("Kaizen RFP POC")
st.caption("Phase 0 placeholder — dashboard, RFP detail, and chat arrive in Phase 5.")

st.markdown(
    """
    ### Services

    - **API**: http://localhost:8000/docs
    - **n8n**: http://localhost:5678
    - **UI**: you are here

    Configure the stack via `config/config.yaml`.
    """
)
