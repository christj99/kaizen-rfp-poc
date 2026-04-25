"""Dashboard — primary surface for the demo.

Sections (top to bottom):
  1. Pipeline summary cards (status counts)
  2. Source breakdown (this-week ingest mix)
  3. Needs Attention queue (status='needs_manual_review')
  4. Recent RFPs table (sortable, source-filtered, color-coded scores)
  5. Recent activity feed (last 10 audit entries)
  6. Ingest CTA — paste / upload / URL forms
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import streamlit as st

import api_client
from components import (
    api_health_banner,
    empty_state,
    fit_score_badge,
    recommendation_badge,
    section_divider,
    source_badge,
    status_badge,
)


def _go_to_rfp(rfp_id: str) -> None:
    """Stash the rfp_id in session state and switch tabs to RFP Detail."""
    st.session_state["selected_rfp_id"] = rfp_id
    st.switch_page("pages/rfp_detail.py") if False else None  # noqa
    # st.switch_page is path-based; using session-state + nav rerun is cleaner
    # in our st.navigation setup, so we just set the key and rely on the user
    # clicking "RFP Detail" in the sidebar. The detail page will pick it up.


def _humanize_age(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 60: return f"{secs}s ago"
        if secs < 3600: return f"{secs // 60}m ago"
        if secs < 86400: return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return iso[:19]


def render() -> None:
    st.title("Dashboard")
    if not api_health_banner():
        return

    # --- pull data once per render (api_client is already cached) ---
    rfps = api_client.list_rfps(with_screening=True, limit=200)
    audit = api_client.list_audit(limit=15)

    # --- 1. Pipeline summary ---
    section_divider("Pipeline summary")
    counts: Dict[str, int] = {}
    for r in rfps:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    cols = st.columns(5)
    for col, (label, key) in zip(cols, [
        ("New", "new"),
        ("Screened", "screened"),
        ("In draft", "in_draft"),
        ("Submitted", "submitted"),
        ("Needs review", "needs_manual_review"),
    ]):
        col.metric(label, counts.get(key, 0))

    # --- 2. Source breakdown (last 7 days) ---
    section_divider("This week — source breakdown")
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    by_source: Dict[str, int] = {}
    for r in rfps:
        try:
            recv = datetime.fromisoformat(r["received_at"].replace("Z", "+00:00"))
            if recv.tzinfo is None: recv = recv.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if recv >= cutoff:
            by_source[r["source_type"]] = by_source.get(r["source_type"], 0) + 1
    total = sum(by_source.values())
    if total == 0:
        empty_state(
            "No new RFPs this week",
            "Send an email to the demo inbox or run a SAM.gov poll to get started.",
            icon="📥",
        )
    else:
        bits = " · ".join(
            f"<b>{n}</b> {label}"
            for label, n in sorted(
                {
                    "email": by_source.get("email", 0),
                    "SAM.gov": by_source.get("sam_gov", 0),
                    "manual upload": by_source.get("manual_upload", 0),
                    "URL ingest": by_source.get("url_ingest", 0),
                }.items(),
                key=lambda kv: -kv[1],
            ) if n
        )
        st.markdown(f"<div style='font-size:0.95rem;color:#334155;'>"
                    f"{total} RFPs ingested in the last 7 days &mdash; {bits}</div>",
                    unsafe_allow_html=True)

    # --- 3. Needs Attention ---
    section_divider("Needs attention")
    needs = [r for r in rfps if r["status"] == "needs_manual_review"]
    if not needs:
        empty_state(
            "Inbox zero — nothing needs manual review.",
            "RFPs that couldn't be ingested cleanly (e.g. SAM.gov description fetch failed) land here.",
            icon="✅",
        )
    else:
        for r in needs[:8]:
            st.markdown(
                f"<div style='padding:0.6rem 0.9rem;border:1px solid #fed7aa;"
                f"background:#fff7ed;border-radius:8px;margin-bottom:0.5rem;'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<div><b>{r.get('title') or '(no title)'}</b><br>"
                f"<span style='color:#64748b;font-size:0.85rem;'>"
                f"{r.get('agency') or '—'} · ingested {_humanize_age(r['received_at'])}</span></div>"
                f"<div>{source_badge(r['source_type'])}</div>"
                f"</div></div>",
                unsafe_allow_html=True,
            )

    # --- 4. Recent RFPs table ---
    section_divider("Recent RFPs")
    filt_cols = st.columns([1, 1, 4])
    with filt_cols[0]:
        f_status = st.selectbox(
            "Status",
            options=["any", "new", "screened", "in_draft", "submitted", "won", "lost", "dismissed", "needs_manual_review"],
            index=0, key="dash_status_filter",
        )
    with filt_cols[1]:
        f_source = st.selectbox(
            "Source",
            options=["any", "email", "sam_gov", "manual_upload", "url_ingest"],
            index=0, key="dash_source_filter",
        )

    visible = rfps
    if f_status != "any":
        visible = [r for r in visible if r["status"] == f_status]
    if f_source != "any":
        visible = [r for r in visible if r["source_type"] == f_source]
    visible = visible[:30]

    if not visible:
        empty_state("No RFPs match the current filters.", icon="🔎")
    else:
        # Render as an HTML table — gives us color badges in cells, click-to-detail.
        rows_html: List[str] = []
        for r in visible:
            rec = r.get("recommendation")
            score = r.get("fit_score")
            received = _humanize_age(r["received_at"])
            rows_html.append(
                f"<tr>"
                f"<td style='padding:0.55rem 0.6rem;'>"
                f"<div style='font-weight:600;'>{(r.get('title') or '(no title)')[:90]}</div>"
                f"<div style='color:#64748b;font-size:0.82rem;'>{r.get('agency') or '—'}</div>"
                f"</td>"
                f"<td style='padding:0.55rem 0.6rem;'>{source_badge(r['source_type'])}</td>"
                f"<td style='padding:0.55rem 0.6rem;'>{status_badge(r['status'])}</td>"
                f"<td style='padding:0.55rem 0.6rem;'>{fit_score_badge(score)}</td>"
                f"<td style='padding:0.55rem 0.6rem;'>{recommendation_badge(rec)}</td>"
                f"<td style='padding:0.55rem 0.6rem;color:#64748b;font-size:0.82rem;'>{received}</td>"
                f"<td style='padding:0.55rem 0.6rem;'><code style='font-size:0.75rem;color:#94a3b8;'>{str(r['id'])[:8]}</code></td>"
                f"</tr>"
            )
        st.markdown(
            "<div style='border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;'>"
            "<table style='width:100%;border-collapse:collapse;font-size:0.92rem;'>"
            "<thead><tr style='background:#f8fafc;text-align:left;color:#475569;font-size:0.75rem;letter-spacing:0.05em;text-transform:uppercase;'>"
            "<th style='padding:0.55rem 0.6rem;'>RFP</th>"
            "<th style='padding:0.55rem 0.6rem;'>Source</th>"
            "<th style='padding:0.55rem 0.6rem;'>Status</th>"
            "<th style='padding:0.55rem 0.6rem;'>Fit</th>"
            "<th style='padding:0.55rem 0.6rem;'>Rec</th>"
            "<th style='padding:0.55rem 0.6rem;'>Received</th>"
            "<th style='padding:0.55rem 0.6rem;'>id</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows_html)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
        # Selectbox-based "open" affordance (avoids per-row buttons that don't render in the HTML table).
        st.markdown("<div style='margin-top:0.5rem;color:#64748b;font-size:0.85rem;'>Open one in detail &darr;</div>", unsafe_allow_html=True)
        select_cols = st.columns([3, 1])
        labels = {
            f"{(r.get('title') or '(no title)')[:60]}  ·  {str(r['id'])[:8]}": r["id"]
            for r in visible
        }
        with select_cols[0]:
            picked = st.selectbox("Pick an RFP", options=list(labels.keys()), label_visibility="collapsed", key="dash_rfp_picker")
        with select_cols[1]:
            if st.button("Open detail", use_container_width=True):
                st.session_state["selected_rfp_id"] = labels[picked]
                st.switch_page("pages/rfp_detail.py") if False else st.info(
                    "Click **RFP Detail** in the sidebar — it'll open the one you selected."
                )

    # --- 5. Recent activity ---
    section_divider("Recent activity")
    if not audit:
        empty_state("No audit entries yet.", icon="🕓")
    else:
        for a in audit[:10]:
            d = a.get("details") or {}
            actor = a.get("actor", "system")
            extra_bits = []
            if "adapter_name" in d: extra_bits.append(f"adapter={d['adapter_name']}")
            if "model" in d: extra_bits.append(f"model={d['model']}")
            if "draft_id" in d: extra_bits.append(f"draft_id={str(d['draft_id'])[:8]}")
            if "duration_seconds" in d: extra_bits.append(f"{float(d['duration_seconds']):.1f}s")
            if "error_class" in d: extra_bits.append(f"err={d['error_class']}")
            extra = " · ".join(extra_bits) if extra_bits else ""
            st.markdown(
                f"<div style='padding:0.4rem 0;border-bottom:1px solid #f1f5f9;font-size:0.92rem;'>"
                f"<span style='color:#64748b;'>{_humanize_age(a['created_at'])}</span> &middot; "
                f"<b>{a['action']}</b> &middot; "
                f"<span style='color:#64748b;'>{actor}</span>"
                f"{('  &middot;  <span style=color:#94a3b8;>' + extra + '</span>') if extra else ''}"
                f"</div>",
                unsafe_allow_html=True,
            )

    # --- 6. Ingest CTA ---
    section_divider("Ingest a new RFP")
    tabs = st.tabs([":material/text_fields: Paste text", ":material/upload_file: PDF upload", ":material/link: URL"])
    with tabs[0]:
        with st.form("ingest_text", clear_on_submit=True):
            title = st.text_input("Title", placeholder="e.g. Cloud Data Warehouse Modernization")
            agency = st.text_input("Agency (optional)")
            naics_str = st.text_input("NAICS codes (comma-separated)", placeholder="541511, 518210")
            full_text = st.text_area("RFP text", height=240, placeholder="Paste the RFP body here…")
            submitted = st.form_submit_button("Ingest", type="primary")
            if submitted:
                if not title or not full_text.strip():
                    st.error("Title and RFP text are required.")
                else:
                    try:
                        naics = [n.strip() for n in naics_str.split(",") if n.strip()]
                        result = api_client.ingest_rfp({
                            "source_type": "manual_upload", "title": title,
                            "agency": agency or None, "naics_codes": naics,
                            "full_text": full_text,
                        })
                        api_client.cache_clear()
                        st.success(f"Ingested. RFP id: {result['rfp']['id']}")
                        st.session_state["selected_rfp_id"] = result["rfp"]["id"]
                    except api_client.APIError as e:
                        st.error(f"Ingest failed: {e}")
    with tabs[1]:
        with st.form("ingest_pdf", clear_on_submit=True):
            uploaded = st.file_uploader("Drop a PDF", type=["pdf"], accept_multiple_files=False)
            title2 = st.text_input("Override title (optional)", key="upload_title")
            agency2 = st.text_input("Agency (optional)", key="upload_agency")
            submitted2 = st.form_submit_button("Upload", type="primary")
            if submitted2:
                if not uploaded:
                    st.error("Pick a PDF first.")
                else:
                    try:
                        result = api_client.upload_pdf(
                            uploaded.getvalue(), uploaded.name,
                            title=title2 or None, agency=agency2 or None,
                        )
                        api_client.cache_clear()
                        st.success(f"Ingested. RFP id: {result['rfp']['id']}")
                        st.session_state["selected_rfp_id"] = result["rfp"]["id"]
                    except api_client.APIError as e:
                        st.error(f"Upload failed: {e}")
    with tabs[2]:
        with st.form("ingest_url", clear_on_submit=True):
            url = st.text_input("URL", placeholder="https://sam.gov/workspace/contract/opp/…")
            title3 = st.text_input("Title (optional)", key="url_title")
            agency3 = st.text_input("Agency (optional)", key="url_agency")
            submitted3 = st.form_submit_button("Fetch + ingest", type="primary")
            if submitted3:
                if not url:
                    st.error("URL required.")
                else:
                    try:
                        result = api_client.ingest_url(url, title=title3 or None, agency=agency3 or None)
                        api_client.cache_clear()
                        st.success(f"Ingested. RFP id: {result['rfp']['id']}")
                        st.session_state["selected_rfp_id"] = result["rfp"]["id"]
                    except api_client.APIError as e:
                        st.error(f"Fetch failed: {e}")
