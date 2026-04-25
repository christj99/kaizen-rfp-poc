"""Rubric Editor — display fit_rubric.yaml as an editable form, save back.

Two main groups:
  - Hard disqualifiers (enable / disable + read-only criterion text)
  - Weighted dimensions (weight slider + scoring guidance text area)

Save writes via PUT /rubric, which audit-logs and bumps the version.
Version history is the audit_log filtered on action='rubric_updated'.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

import api_client
from components import api_health_banner, empty_state, section_divider


def render() -> None:
    st.title("Rubric editor")
    if not api_health_banner():
        return

    try:
        rubric = api_client.get_rubric()
    except api_client.APIError as e:
        st.error(f"Couldn't load rubric: {e}")
        return

    if not rubric:
        empty_state("Rubric is empty.", icon=":material/tune:")
        return

    # Header
    cols = st.columns([2, 1, 1])
    with cols[0]:
        st.markdown(
            f"<div style='font-size:0.78rem;color:#64748b;letter-spacing:0.06em;"
            f"text-transform:uppercase;font-weight:600;'>fit_rubric.yaml</div>"
            f"<div style='font-size:1.3rem;font-weight:700;'>"
            f"v{rubric.get('version', '?')}"
            f"</div>",
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.metric("Last updated", str(rubric.get("last_updated", "—")))
    with cols[2]:
        st.metric("Calibration", str(rubric.get("calibration_status") or "—"))

    # --- hard disqualifiers ---
    section_divider("Hard disqualifiers")
    hd_list = rubric.get("hard_disqualifiers") or []
    if not hd_list:
        st.caption("(none defined)")
    edited_hd: List[Dict[str, Any]] = []
    for i, hd in enumerate(hd_list):
        c = st.columns([1, 4])
        with c[0]:
            enabled = st.toggle("Enabled", value=hd.get("enabled", True), key=f"hd_en_{i}")
        with c[1]:
            st.markdown(f"**{hd.get('id', f'hd_{i}')}** — {hd.get('criterion', '')}")
            if hd.get("check"):
                st.caption(hd["check"])
        new_hd = dict(hd)
        new_hd["enabled"] = enabled
        edited_hd.append(new_hd)

    # --- weighted dimensions ---
    section_divider("Weighted dimensions")
    dims_list = rubric.get("weighted_dimensions") or []
    edited_dims: List[Dict[str, Any]] = []
    total_weight = 0.0
    for i, d in enumerate(dims_list):
        with st.container(border=True):
            cols = st.columns([3, 1])
            with cols[0]:
                st.markdown(f"**{d.get('name', f'dim_{i}')}**")
                if d.get("id"):
                    st.caption(f"id: `{d['id']}`")
            with cols[1]:
                w = st.slider("Weight", min_value=0, max_value=50, value=int(d.get("weight", 0)),
                              key=f"dim_w_{i}", step=1)
            guidance = st.text_area(
                "Scoring guidance",
                value=d.get("scoring_guidance", "") or "",
                height=100,
                key=f"dim_g_{i}",
            )
            new_d = dict(d)
            new_d["weight"] = w
            new_d["scoring_guidance"] = guidance
            edited_dims.append(new_d)
            total_weight += w

    # Weight sum sanity check
    if abs(total_weight - 100) > 0.01:
        st.warning(
            f"Weights currently total **{total_weight:.0f}** — convention is 100."
            "  Save anyway; the screening agent will still run."
        )
    else:
        st.success(f"Weights total {total_weight:.0f}.")

    # --- Save ---
    section_divider("Save")
    save_col, _ = st.columns([1, 4])
    with save_col:
        if st.button(":material/save: Save rubric", type="primary", use_container_width=True):
            payload = dict(rubric)
            payload["hard_disqualifiers"] = edited_hd
            payload["weighted_dimensions"] = edited_dims
            try:
                result = api_client.update_rubric(payload)
                api_client.cache_clear()
                st.success(f"Saved as v{result.get('version')}")
            except api_client.APIError as e:
                st.error(f"Save failed: {e}")

    # --- version history ---
    section_divider("Version history")
    audit = [a for a in api_client.list_audit(limit=50) if a.get("action") == "rubric_updated"]
    if not audit:
        st.caption("No prior edits in audit_log.")
    else:
        for a in audit[:8]:
            d = a.get("details") or {}
            st.markdown(
                f"- `{a['created_at'][:19]}` &middot; **v{d.get('version', '?')}** "
                f"&middot; updated {d.get('last_updated', '?')}"
            )
