"""RFP Detail — second-most-visited page; carries the demo's narrative weight.

Layout:
  1. RFP metadata header (title, agency, value, due, NAICS, source badge,
     source-metadata expandable, source URL).
  2. Screening result card (score, recommendation, confidence,
     rubric-breakdown expandable). Hard disqualifiers as a callout if any
     triggered. Deal-breakers + open questions.
  3. Similar past proposals (3 cards w/ relevance + reusable sections).
  4. Action row: "Generate draft" (async kickoff + polling), "Override
     recommendation" (dialog), "Dismiss".
  5. Draft section (when present) — per-section content with provenance,
     confidence, review flags + Markdown export link.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import streamlit as st

from .. import api_client
from ..components import (
    api_health_banner,
    empty_state,
    fit_score_badge,
    kv_grid,
    provenance_badge,
    recommendation_badge,
    section_divider,
    severity_badge,
    source_badge,
    status_badge,
)


# ---------- helpers --------------------------------------------------

def _format_value(rfp: Dict[str, Any]) -> str:
    lo, hi = rfp.get("value_estimate_low"), rfp.get("value_estimate_high")
    if lo and hi and lo != hi:
        return f"${lo:,} – ${hi:,}"
    if lo:
        return f"${lo:,}"
    if hi:
        return f"${hi:,}"
    return "—"


def _format_due(rfp: Dict[str, Any]) -> str:
    d = rfp.get("due_date")
    if not d:
        return "—"
    try:
        dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
        days = (dt.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
        return f"{dt.strftime('%Y-%m-%d')}  ({days:+d}d)"
    except Exception:
        return d[:19]


def _pick_rfp(rfps: List[Dict[str, Any]]) -> Optional[str]:
    """Selectbox to pick an RFP if no session-state default is set."""
    if not rfps:
        empty_state(
            "No RFPs ingested yet.",
            "Send an email to the demo inbox or use the Dashboard's Ingest tab to add one.",
            icon=":material/inbox:",
        )
        return None
    labels = {
        f"{(r.get('title') or '(no title)')[:80]}  ·  {str(r['id'])[:8]}": r["id"]
        for r in rfps
    }
    pick = st.selectbox("Choose an RFP", options=list(labels.keys()))
    return labels[pick] if pick else None


# ---------- main render ---------------------------------------------

def render() -> None:
    st.title("RFP Detail")
    if not api_health_banner():
        return

    # --- pick which RFP to show ---
    rfps = api_client.list_rfps(with_screening=False, limit=200)
    selected = st.session_state.get("selected_rfp_id")
    if selected and not any(str(r["id"]) == str(selected) for r in rfps):
        # stale selection (e.g. demo_reset) — clear and fall through
        selected = None

    if not selected:
        selected = _pick_rfp(rfps)
        if not selected:
            return

    # --- fetch full detail ---
    try:
        ctx = api_client.get_rfp(str(selected))
    except api_client.APIError as exc:
        st.error(f"Couldn't load RFP: {exc}")
        return

    rfp = ctx["rfp"]
    screening = ctx.get("screening")

    # ---- 1. Header ----
    st.markdown(
        f"<div style='font-size:0.78rem;color:#64748b;letter-spacing:0.06em;"
        f"text-transform:uppercase;font-weight:600;'>RFP</div>"
        f"<div style='font-size:1.6rem;font-weight:700;line-height:1.2;'>{rfp.get('title') or '(no title)'}</div>",
        unsafe_allow_html=True,
    )

    meta_pairs: List[tuple] = [
        ("Agency", rfp.get("agency") or "—"),
        ("Source", source_badge(rfp.get("source_type")) + "  " + status_badge(rfp.get("status"))),
        ("NAICS", ", ".join(rfp.get("naics_codes") or []) or "—"),
        ("Value estimate", _format_value(rfp)),
        ("Due date", _format_due(rfp)),
        ("Solicitation #", rfp.get("external_id") or "—"),
    ]
    if rfp.get("source_url"):
        meta_pairs.append(("Source URL", f"<a href='{rfp['source_url']}' target='_blank'>open ↗</a>"))
    kv_grid(meta_pairs, cols=3)

    with st.expander("Source metadata"):
        st.json(rfp.get("source_metadata") or {})
    with st.expander(f"Full RFP text  ({len(rfp.get('full_text') or '')} chars)"):
        st.text(rfp.get("full_text") or "(empty)")

    # ---- 2. Screening result ----
    section_divider("Screening result")

    if not screening:
        col1, col2 = st.columns([1, 2])
        with col1:
            empty_state("Not screened yet.", "", icon=":material/pending:")
        with col2:
            if st.button("Screen now", type="primary"):
                with st.spinner("Calling Claude — typically 60-120s"):
                    try:
                        api_client.screen_rfp(str(selected))
                        api_client.cache_clear()
                        st.success("Screened. Refreshing…")
                        time.sleep(0.5)
                        st.rerun()
                    except api_client.APIError as e:
                        st.error(f"Screening failed: {e}")
    else:
        rationale = screening.get("rationale") or {}
        sc_pairs = [
            ("Fit score", fit_score_badge(screening.get("fit_score"))),
            ("Recommendation", recommendation_badge(screening.get("recommendation"))),
            ("Effort", screening.get("effort_estimate") or "—"),
            ("Confidence", rationale.get("confidence_level") or "—"),
            ("Rubric version", screening.get("rubric_version") or "—"),
            ("Model", screening.get("model_version") or "—"),
        ]
        if screening.get("human_override"):
            sc_pairs.append((
                "Human override",
                recommendation_badge(screening.get("human_override")) +
                f" &mdash; <span style='color:#64748b;'>{screening.get('human_override_reason') or ''}</span>",
            ))
        kv_grid(sc_pairs, cols=3)

        if rationale.get("recommendation_rationale"):
            st.markdown(
                f"<div style='margin:0.75rem 0 1rem 0;padding:0.75rem 1rem;"
                f"background:#f8fafc;border-left:3px solid #0F766E;border-radius:4px;'>"
                f"{rationale['recommendation_rationale']}</div>",
                unsafe_allow_html=True,
            )

        # Hard disqualifiers callout
        hd_results = rationale.get("hard_disqualifier_results") or []
        triggered = [h for h in hd_results if h.get("triggered")]
        if triggered:
            st.error(
                ":material/block: **Hard disqualifier(s) triggered**\n\n" +
                "\n\n".join(
                    f"- **{h.get('id', '?')}** — {h.get('reasoning', '')}"
                    + (f"\n  > _evidence:_ {h['evidence']}" if h.get("evidence") else "")
                    for h in triggered
                )
            )

        # Rubric dimension breakdown
        with st.expander("Why this score?  (rubric breakdown)"):
            dims = rationale.get("dimensions") or []
            if not dims:
                st.write("_No dimensions returned._")
            for d in sorted(dims, key=lambda x: -(x.get("weight", 0) * x.get("score", 0) / 100)):
                weighted = (d.get("weight", 0) * d.get("score", 0)) / 100
                st.markdown(
                    f"**{d.get('name')}** — score {d.get('score')} × weight {d.get('weight')} "
                    f"= {weighted:.1f}"
                )
                st.caption(d.get("reasoning") or "")
                evd = d.get("evidence_citations") or []
                if evd:
                    with st.container(border=False):
                        for citation in evd[:3]:
                            st.markdown(f"<small>· {citation[:200]}</small>", unsafe_allow_html=True)
                st.divider()

        # Deal-breakers
        dbs = screening.get("deal_breakers") or []
        if dbs:
            section_divider(f"Deal breakers ({len(dbs)})")
            for db in dbs:
                st.markdown(
                    f"<div style='border-left:3px solid #ef4444;padding:0.5rem 0.75rem;"
                    f"margin-bottom:0.5rem;background:#fef2f2;'>"
                    f"{severity_badge(db.get('severity'))}  "
                    f"<b>{db.get('concern', '')}</b>"
                    f"{(' &mdash; would change rec to <b>' + db['would_change_recommendation_to'] + '</b>') if db.get('would_change_recommendation_to') else ''}"
                    f"<div style='color:#64748b;font-size:0.85rem;margin-top:0.25rem;'>"
                    f"How to verify: {db.get('how_to_verify') or '—'}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # Open questions
        oqs = screening.get("open_questions") or []
        if oqs:
            section_divider(f"Open questions ({len(oqs)})")
            for q in oqs:
                st.markdown(
                    f"- **{q.get('question')}**"
                    + (f"  \n  _why it matters:_ {q['why_it_matters']}" if q.get("why_it_matters") else "")
                    + (f"  \n  _best guess:_ {q['best_guess']}" if q.get("best_guess") else "")
                )

        # Similar past proposals (from screening's similar_past_proposals_analysis)
        spa = rationale.get("similar_past_proposals_analysis") or []
        if spa:
            section_divider(f"Similar past proposals  ({len(spa)})")
            cols = st.columns(min(3, len(spa)))
            for i, sim in enumerate(spa[:3]):
                with cols[i]:
                    rs = sim.get("relevance_strength", "—")
                    rs_color = {"strong": "#166534", "moderate": "#854d0e", "weak": "#7f1d1d"}.get(rs, "#475569")
                    st.markdown(
                        f"<div style='border:1px solid #e2e8f0;border-radius:8px;padding:0.75rem;height:100%;'>"
                        f"<div style='font-size:0.7rem;color:{rs_color};font-weight:700;text-transform:uppercase;letter-spacing:0.05em;'>{rs}</div>"
                        f"<div style='font-size:0.85rem;margin-top:0.4rem;color:#334155;'>"
                        f"{sim.get('why_relevant', '')[:240]}</div>"
                        f"<div style='margin-top:0.5rem;font-size:0.78rem;color:#64748b;'>"
                        f"Reusable: {', '.join(sim.get('reusable_sections') or []) or '—'}</div>"
                        f"<div style='margin-top:0.4rem;font-size:0.7rem;color:#94a3b8;font-family:monospace;'>"
                        f"{str(sim.get('proposal_id', ''))[:8]}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    # ---- 4. Action row ----
    section_divider("Actions")
    a1, a2, a3, a4 = st.columns([1, 1, 1, 1])

    # Re-screen (always available)
    with a1:
        if st.button(":material/refresh: Re-screen", use_container_width=True):
            with st.spinner("Calling Claude…"):
                try:
                    api_client.screen_rfp(str(selected))
                    api_client.cache_clear()
                    st.rerun()
                except api_client.APIError as e:
                    st.error(f"Screening failed: {e}")

    # Generate draft
    job_state_key = f"draft_job__{selected}"
    with a2:
        draft_disabled = bool(st.session_state.get(job_state_key))
        if st.button(
            ":material/edit_document: Generate draft",
            disabled=draft_disabled,
            use_container_width=True,
            type="primary",
        ):
            try:
                kicked = api_client.kickoff_draft(str(selected), mode="async")
                st.session_state[job_state_key] = kicked["job_id"]
                api_client.cache_clear()
                st.rerun()
            except api_client.APIError as e:
                st.error(f"Couldn't queue drafting: {e}")

    # Override recommendation
    with a3:
        with st.popover(":material/edit_note: Override", use_container_width=True, disabled=not screening):
            new_rec = st.selectbox("Recommendation", ["pursue", "maybe", "skip"], key=f"ov_rec_{selected}")
            reason = st.text_area("Reason", key=f"ov_reason_{selected}", height=80)
            if st.button("Save override", key=f"ov_save_{selected}", type="primary"):
                try:
                    api_client.override_screening(str(selected), new_rec, reason or None)
                    api_client.cache_clear()
                    st.success("Saved.")
                    time.sleep(0.4)
                    st.rerun()
                except api_client.APIError as e:
                    st.error(f"Override failed: {e}")

    # Dismiss
    with a4:
        if st.button(":material/close: Dismiss", use_container_width=True, disabled=rfp.get("status") == "dismissed"):
            try:
                # Use a small inline write through the override endpoint? No — status is its own field.
                # We don't expose a status PATCH endpoint yet; for POC, skip and surface a hint.
                st.toast("Dismiss endpoint not wired in this build.")
            except api_client.APIError as e:
                st.error(f"Dismiss failed: {e}")

    # ---- 5. Draft section (with async polling) ----
    section_divider("Draft")
    job_id = st.session_state.get(job_state_key)
    existing_draft_id = None  # populated below if a completed draft exists

    if job_id:
        try:
            j = api_client.get_draft_job(job_id)
        except api_client.APIError as e:
            st.error(f"Couldn't poll draft job: {e}")
            j = None
        if j:
            status = j["job"]["status"]
            if status in ("queued", "running"):
                st.info(
                    f":material/hourglass: **Drafting in progress** — {status} "
                    f"(typically 3-5 min on Sonnet).  Job: `{job_id[:8]}…`"
                )
                # auto-refresh every 8s — Streamlit will rerun naturally; we hint via caption
                st.caption("This page will refresh automatically.")
                # gentle programmatic poll
                time.sleep(8)
                st.rerun()
            elif status == "completed":
                existing_draft_id = j["job"]["draft_id"]
                # Clear the in-progress marker so we render the draft below
                st.session_state.pop(job_state_key, None)
                st.success(f"Draft completed in this session — id: `{(existing_draft_id or '')[:8]}…`")
            elif status == "failed":
                st.session_state.pop(job_state_key, None)
                st.error(
                    f"**Draft failed.**  \n`{j['job'].get('error_message', '(no error message)')[:600]}`"
                )

    # If no in-flight job, show the latest persisted draft (if any).
    if not existing_draft_id:
        # Try latest_draft_for_rfp via API: not exposed directly; we can derive
        # by listing draft_jobs for this rfp and finding the most recent completed.
        # For POC simplicity, fall through unless a completed in-session id exists.
        pass

    if existing_draft_id:
        try:
            draft = api_client.get_draft(existing_draft_id)
        except api_client.APIError as e:
            st.error(f"Couldn't load draft: {e}")
            draft = None

        if draft:
            sections = (draft.get("content") or {}).get("sections") or []
            section_divider(f"Generated draft  ·  {len(sections)} sections")

            export_url = api_client.export_draft_url(existing_draft_id)
            st.markdown(
                f"<a href='{export_url}' target='_blank' style='display:inline-block;"
                f"padding:0.4rem 0.8rem;background:#0F766E;color:#fff;border-radius:6px;"
                f"text-decoration:none;font-size:0.9rem;font-weight:600;'>"
                f":material/download: Export Markdown</a>",
                unsafe_allow_html=True,
            )

            for sec in sections:
                review_marker = " ⚠️" if sec.get("needs_review") else ""
                conf = sec.get("confidence")
                conf_text = f"{conf:.2f}" if conf is not None else "—"
                with st.expander(f"{sec.get('name', 'Section')}{review_marker}  ·  {conf_text}"):
                    cols = st.columns([2, 1])
                    with cols[0]:
                        st.markdown(provenance_badge(sec.get("provenance")), unsafe_allow_html=True)
                        if sec.get("source_proposal_id"):
                            st.caption(f"sourced from past proposal: `{str(sec['source_proposal_id'])[:8]}`")
                    with cols[1]:
                        st.caption(
                            ("⚠️ Needs review — " + (sec.get("notes") or ""))
                            if sec.get("needs_review")
                            else ""
                        )
                    st.markdown(sec.get("content") or "_empty_")
    elif not job_id:
        st.caption(
            "No draft for this RFP yet — click **Generate draft** above. "
            "Drafting runs asynchronously; you can navigate away and come back."
        )
