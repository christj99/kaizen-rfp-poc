"""Settings — operational-maturity surface.

Two main blocks:
  - System Configuration: mode switcher, threshold sliders, source toggles.
    Writes via PUT /config; hot-reload on mtime means the next API call
    sees the new values without a restart.
  - Adapter Management: per-adapter status, "Run now" + "Test connection"
    buttons. Per supplemental Amendment 5.B.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

import api_client
from components import (
    api_health_banner,
    empty_state,
    section_divider,
    source_badge,
)


def render() -> None:
    st.title("Settings")
    if not api_health_banner():
        return

    try:
        cfg = api_client.get_config()
    except api_client.APIError as e:
        st.error(f"Couldn't load config: {e}")
        return

    # =====================================================================
    section_divider("System configuration")
    # =====================================================================

    cols = st.columns([1, 1, 1])
    with cols[0]:
        new_mode = st.selectbox(
            "Mode",
            options=["manual", "chain", "full_auto"],
            index=["manual", "chain", "full_auto"].index(cfg.get("mode", "manual")),
            help="manual: ingest only. chain: + auto-screen. full_auto: + auto-draft when fit ≥ threshold.",
        )

    with cols[1]:
        new_pursue = st.slider(
            "Pursue threshold",
            min_value=50, max_value=100,
            value=int(cfg.get("screening", {}).get("threshold_pursue", 75)),
        )
    with cols[2]:
        new_maybe = st.slider(
            "Maybe threshold",
            min_value=20, max_value=80,
            value=int(cfg.get("screening", {}).get("threshold_maybe", 50)),
        )

    cols2 = st.columns([1, 1, 1])
    with cols2[0]:
        new_auto = st.slider(
            "Auto-draft threshold",
            min_value=50, max_value=100,
            value=int(cfg.get("drafting", {}).get("auto_draft_threshold", 80)),
            help="In full_auto mode, RFPs whose fit ≥ this threshold get drafted automatically.",
        )
    with cols2[1]:
        new_slack = st.slider(
            "Slack notify threshold",
            min_value=0, max_value=100,
            value=int(cfg.get("slack", {}).get("notification_threshold", 50)),
            help="Screening cards fire on fit ≥ this. Lower = more cards.",
        )

    cols3 = st.columns([1, 1, 2])
    with cols3[0]:
        email_on = st.toggle(
            "Email source",
            value=bool(cfg.get("sources", {}).get("email", {}).get("enabled", True)),
        )
    with cols3[1]:
        sam_on = st.toggle(
            "SAM.gov source",
            value=bool(cfg.get("sources", {}).get("sam_gov", {}).get("enabled", True)),
        )

    save_cols = st.columns([1, 5])
    with save_cols[0]:
        if st.button(":material/save: Save", type="primary", use_container_width=True):
            try:
                api_client.update_config({
                    "mode": new_mode,
                    "screening_threshold_pursue": new_pursue,
                    "screening_threshold_maybe": new_maybe,
                    "drafting_auto_draft_threshold": new_auto,
                    "slack_notification_threshold": new_slack,
                    "sources_email_enabled": email_on,
                    "sources_sam_gov_enabled": sam_on,
                })
                api_client.cache_clear()
                st.success("Saved. Hot-reload will pick up on the next API call.")
            except api_client.APIError as e:
                st.error(f"Save failed: {e}")

    # =====================================================================
    section_divider("Adapter management")
    # =====================================================================

    try:
        adapters = api_client.list_adapters()
    except api_client.APIError as e:
        st.error(f"Couldn't list adapters: {e}")
        return

    if not adapters:
        empty_state("No adapters configured.", icon=":material/cable:")
        return

    for a in adapters:
        with st.container(border=True):
            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                st.markdown(
                    f"<div style='font-weight:600;'>{a['name']}</div>"
                    f"<div style='color:#64748b;font-size:0.85rem;'>"
                    f"{source_badge(a['adapter_type'])}  &middot; {a.get('detail') or ''}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                meta = a.get("metadata") or {}
                if meta:
                    bits = []
                    if "total" in meta: bits.append(f"{meta['total']} total")
                    if "unread" in meta: bits.append(f"{meta['unread']} unread")
                    if "naics_filter" in meta:
                        bits.append("NAICS: " + ", ".join(meta["naics_filter"]))
                    if bits:
                        st.caption(" · ".join(bits))
            with cols[1]:
                status = a.get("status", "unknown")
                color = {"ok": "#166534", "degraded": "#854d0e", "down": "#991b1b"}.get(status, "#475569")
                st.markdown(
                    f"<div style='text-align:center;'>"
                    f"<div style='font-size:0.7rem;color:#64748b;text-transform:uppercase;'>health</div>"
                    f"<div style='font-weight:700;color:{color};'>{status}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with cols[2]:
                if st.button(":material/play_arrow: Run now", key=f"run_{a['name']}", use_container_width=True):
                    with st.spinner(f"Running {a['name']}…"):
                        try:
                            result = api_client.run_adapter(a["name"])
                            api_client.cache_clear()
                            st.success(
                                f"Done. new={result['total_new']}  duplicates={result['total_duplicates']}  errors={result['total_errors']}"
                            )
                            errs = result["adapters"][0].get("errors") if result.get("adapters") else []
                            if errs:
                                with st.expander("Errors"):
                                    st.json(errs)
                        except api_client.APIError as e:
                            st.error(f"Run failed: {e}")
            with cols[3]:
                if st.button(":material/cable: Test connection", key=f"test_{a['name']}", use_container_width=True):
                    # Health check is what list_adapters already returned; we just refresh.
                    api_client.list_adapters.clear()  # type: ignore[attr-defined]
                    st.toast("Refreshed adapter status.")
                    st.rerun()
