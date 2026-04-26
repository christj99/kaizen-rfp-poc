"""SQL Console — read-only admin surface for the demo's data-layer beat.

POSTs to ``/admin/sql``. The endpoint enforces SELECT-only, statement
timeout, and result-row truncation; this page is just the textarea +
Run button + result table + click-to-insert example queries.
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pandas as pd
import streamlit as st

import api_client
from components import api_health_banner, section_divider


# Keep the textarea's widget key and the click-to-load key the SAME.
# Streamlit ignores ``value=`` once a keyed widget has rendered — to
# pre-populate the textarea from a button click, we have to write to the
# textarea's own session_state key before its next render.
_QUERY_KEY = "sql_console_textarea"

# Public tables — used by the schema-explorer dropdown. Listed in the
# order we tend to walk them in the demo (lifecycle entities first, then
# the RAG corpus, then the audit trail).
_PUBLIC_TABLES = [
    "rfps",
    "screenings",
    "drafts",
    "draft_jobs",
    "past_proposals",
    "proposal_chunks",
    "audit_log",
]


def _schema_query(table: str) -> str:
    return (
        "SELECT\n"
        "  column_name,\n"
        "  data_type,\n"
        "  is_nullable,\n"
        "  column_default\n"
        "FROM information_schema.columns\n"
        f"WHERE table_name = '{table}' AND table_schema = 'public'\n"
        "ORDER BY ordinal_position;"
    )


def _all_tables_overview_query() -> str:
    return (
        "SELECT\n"
        "  table_name,\n"
        "  COUNT(*) AS column_count\n"
        "FROM information_schema.columns\n"
        "WHERE table_schema = 'public'\n"
        "GROUP BY table_name\n"
        "ORDER BY table_name;"
    )


# Pre-canned demo queries. Each is a (label, sql) pair. Clicking a label
# button copies the SQL into the textarea and runs it.
EXAMPLE_QUERIES: List[Dict[str, str]] = [
    {
        "label": "RFP lifecycle by source + status",
        "sql": (
            "SELECT\n"
            "  source_type,\n"
            "  status,\n"
            "  COUNT(*) AS rfp_count\n"
            "FROM rfps\n"
            "GROUP BY source_type, status\n"
            "ORDER BY source_type, status;"
        ),
    },
    {
        "label": "Latest screening with JSONB rationale",
        "sql": (
            "SELECT\n"
            "  s.rfp_id,\n"
            "  r.title,\n"
            "  s.fit_score,\n"
            "  s.recommendation,\n"
            "  s.rationale->>'confidence_level' AS confidence_level,\n"
            "  s.rubric_version,\n"
            "  s.rationale\n"
            "FROM screenings s\n"
            "JOIN rfps r ON r.id = s.rfp_id\n"
            "ORDER BY s.created_at DESC\n"
            "LIMIT 1;"
        ),
    },
    {
        "label": "Audit trail for the most recent RFP",
        "sql": (
            "SELECT\n"
            "  actor,\n"
            "  action,\n"
            "  details,\n"
            "  created_at\n"
            "FROM audit_log\n"
            "WHERE entity_id = (\n"
            "  SELECT id FROM rfps ORDER BY received_at DESC LIMIT 1\n"
            ")\n"
            "ORDER BY created_at;"
        ),
    },
    {
        "label": "Async draft jobs and durations",
        "sql": (
            "SELECT\n"
            "  dj.id AS job_id,\n"
            "  r.title,\n"
            "  dj.status,\n"
            "  dj.started_at,\n"
            "  dj.completed_at,\n"
            "  EXTRACT(EPOCH FROM (dj.completed_at - dj.started_at)) AS duration_seconds,\n"
            "  dj.error_message\n"
            "FROM draft_jobs dj\n"
            "JOIN rfps r ON r.id = dj.rfp_id\n"
            "ORDER BY dj.created_at DESC\n"
            "LIMIT 10;"
        ),
    },
    {
        "label": "Past-proposal corpus (RAG knowledge base)",
        "sql": (
            "SELECT\n"
            "  pp.title,\n"
            "  pp.agency,\n"
            "  pp.outcome,\n"
            "  pp.contract_value,\n"
            "  pp.submitted_date,\n"
            "  COUNT(pc.id) AS chunk_count\n"
            "FROM past_proposals pp\n"
            "LEFT JOIN proposal_chunks pc ON pc.past_proposal_id = pp.id\n"
            "GROUP BY pp.id\n"
            "ORDER BY pp.submitted_date DESC NULLS LAST;"
        ),
    },
]


def _run_query(sql: str) -> Dict[str, Any]:
    """POST /admin/sql. Returns the raw dict on success; raises with a
    user-facing message on rejection."""
    base = api_client._api_base()
    with httpx.Client(timeout=30.0) as c:
        r = c.post(f"{base}/admin/sql", json={"query": sql})
    if r.status_code == 400:
        try:
            detail = r.json().get("detail") or {}
        except Exception:
            detail = {"error": "bad_request", "detail": r.text[:200]}
        raise api_client.APIError(
            f"{detail.get('error', 'rejected')}: {detail.get('detail', '')}",
            status_code=400,
        )
    if r.status_code >= 500:
        raise api_client.APIError(f"server error {r.status_code}: {r.text[:200]}",
                                  status_code=r.status_code)
    return r.json()


def render() -> None:
    st.title("SQL Console")
    st.caption(
        "Read-only SELECT surface against the demo Postgres. "
        "Three-layer enforcement: an application-level parser, a "
        "`rfp_readonly` Postgres role with SELECT-only privileges, and "
        "per-query `SET TRANSACTION READ ONLY` + 5-second `statement_timeout`. "
        "Results are capped at 1000 rows."
    )
    if not api_health_banner():
        return

    # --- example queries ---
    section_divider("Example queries — click to load")
    cols = st.columns(2)
    for i, eq in enumerate(EXAMPLE_QUERIES):
        with cols[i % 2]:
            if st.button(eq["label"], key=f"ex_{i}", use_container_width=True):
                st.session_state[_QUERY_KEY] = eq["sql"]
                st.session_state["_run_now"] = True
                st.rerun()

    # --- schema explorer ---
    section_divider("Schema explorer")
    schema_cols = st.columns([2, 1, 1])
    with schema_cols[0]:
        selected_table = st.selectbox(
            "Table",
            options=_PUBLIC_TABLES,
            index=0,
            key="sql_console_schema_table",
            label_visibility="collapsed",
        )
    with schema_cols[1]:
        if st.button(":material/table_chart: Show columns",
                     use_container_width=True, key="show_schema_btn"):
            st.session_state[_QUERY_KEY] = _schema_query(selected_table)
            st.session_state["_run_now"] = True
            st.rerun()
    with schema_cols[2]:
        if st.button(":material/list: All tables",
                     use_container_width=True, key="all_tables_btn"):
            st.session_state[_QUERY_KEY] = _all_tables_overview_query()
            st.session_state["_run_now"] = True
            st.rerun()

    # --- query editor ---
    section_divider("Query")
    # The textarea reads/writes session_state[_QUERY_KEY] directly because
    # _QUERY_KEY IS the widget's own key — that's how button clicks above
    # are able to repopulate it. Don't pass ``value=`` here; Streamlit
    # would warn about setting both ``value`` and an existing session_state
    # entry on the same widget.
    sql = st.text_area(
        "SQL",
        height=200,
        key=_QUERY_KEY,
        label_visibility="collapsed",
        placeholder="SELECT ...",
    )
    run_cols = st.columns([1, 1, 4])
    with run_cols[0]:
        run_clicked = st.button(":material/play_arrow: Run query", type="primary",
                                use_container_width=True)
    with run_cols[1]:
        if st.button(":material/clear: Clear", use_container_width=True):
            st.session_state[_QUERY_KEY] = ""
            st.session_state.pop("_run_now", None)
            st.rerun()

    should_run = run_clicked or st.session_state.pop("_run_now", False)
    if not should_run or not sql.strip():
        return

    # No need to mirror sql back into session_state — the textarea owns
    # _QUERY_KEY and Streamlit retains its own value across reruns.

    # --- execute ---
    section_divider("Result")
    try:
        with st.spinner("Running…"):
            result = _run_query(sql)
    except api_client.APIError as e:
        st.error(f"**Query rejected.**  \n`{e}`")
        return

    # Header line
    note_bits = []
    note_bits.append(f"{result['row_count']} row{'s' if result['row_count'] != 1 else ''}")
    if result.get("truncated"):
        note_bits.append("**truncated at 1000**")
    note_bits.append(f"{result['execution_time_ms']:.1f} ms")
    st.markdown(" · ".join(note_bits))

    if result.get("note"):
        st.info(result["note"])
        return

    if not result["rows"]:
        st.caption("No rows returned.")
        return

    # Render as a DataFrame. Each cell is already JSON-serializable from
    # the backend (UUID/datetime stringified, JSONB as dict). pandas will
    # display dicts as their repr — fine for demo inspection.
    df = pd.DataFrame(result["rows"], columns=result["columns"])
    st.dataframe(df, use_container_width=True, hide_index=True)
