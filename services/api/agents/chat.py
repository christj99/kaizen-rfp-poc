"""Tool-calling chat agent.

Pairs ``chat_system.txt`` with the five tools that prompt names. Each
tool executes Python directly against the DB / RAG retriever (we're
inside the API, so direct access is fine). The agent runs in a small
loop: call Claude → if it requests a tool, run it and feed the result
back → repeat until the model returns no more tool_use blocks. Cap the
loop at 6 iterations to keep latency bounded.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import anthropic

from .. import _env  # noqa: F401
from ..config.loader import get_config
from ..db.client import (
    db_cursor,
    get_past_proposal,
    get_rfp,
    list_past_proposals,
    list_rfps_with_screening,
)
from ..llm.client import LLMClient   # only for mock-mode helper; main call uses streaming directly
from ..models.audit import AuditEntry
from ..rag.retriever import find_similar_proposals

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "llm" / "prompts"
_MAX_TOOL_LOOPS = 6
_CHAT_MAX_TOKENS = 2048
_CHAT_TEMPERATURE = 0.4   # slightly above screening to keep replies natural


# ---------- tool schemas (Anthropic format) -------------------------

TOOL_DEFS: List[Dict[str, Any]] = [
    {
        "name": "search_rfps",
        "description": (
            "Search RFPs in Meridian's system. Returns matching RFPs with "
            "id, title, agency, status, source_type, fit_score, recommendation, "
            "received_at. Use this when the user asks 'show me RFPs that ...' "
            "or 'find recent ...' style questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status (new|screened|in_draft|...)"},
                "source_type": {"type": "string", "description": "Filter by source (email|sam_gov|manual_upload|url_ingest)"},
                "min_fit_score": {"type": "integer", "description": "Inclusive minimum fit_score from latest screening"},
                "max_fit_score": {"type": "integer", "description": "Inclusive maximum fit_score from latest screening"},
                "agency_contains": {"type": "string", "description": "Substring match on agency (case-insensitive)"},
                "title_contains": {"type": "string", "description": "Substring match on title (case-insensitive)"},
                "limit": {"type": "integer", "description": "Max results to return (default 20)"},
            },
        },
    },
    {
        "name": "search_past_proposals",
        "description": (
            "Semantic search over Meridian's past proposal corpus via the RAG "
            "index. Returns the top-k most relevant past proposals with their "
            "id, title, agency, outcome, contract_value, similarity, and the "
            "best-matching section excerpt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language query"},
                "k": {"type": "integer", "description": "Number of results (default 3, max 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_rfp_detail",
        "description": (
            "Fetch full details for one RFP by id, including the latest "
            "screening if available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"rfp_id": {"type": "string", "description": "UUID of the RFP"}},
            "required": ["rfp_id"],
        },
    },
    {
        "name": "get_past_proposal_detail",
        "description": "Fetch the full content of a past proposal by id (sections + metadata).",
        "input_schema": {
            "type": "object",
            "properties": {"proposal_id": {"type": "string", "description": "UUID of the past proposal"}},
            "required": ["proposal_id"],
        },
    },
    {
        "name": "get_screening_detail",
        "description": "Fetch the full screening for an RFP by RFP id (rubric breakdown, deal-breakers, open questions).",
        "input_schema": {
            "type": "object",
            "properties": {"rfp_id": {"type": "string", "description": "UUID of the RFP whose latest screening is wanted"}},
            "required": ["rfp_id"],
        },
    },
]


# ---------- tool implementations ------------------------------------

def _tool_search_rfps(args: Dict[str, Any]) -> Dict[str, Any]:
    rows = list_rfps_with_screening(
        status=args.get("status"),
        source_type=args.get("source_type"),
        limit=int(args.get("limit") or 20),
    )
    title_q = (args.get("title_contains") or "").lower().strip()
    agency_q = (args.get("agency_contains") or "").lower().strip()
    min_fit = args.get("min_fit_score")
    max_fit = args.get("max_fit_score")

    out: List[Dict[str, Any]] = []
    for r in rows:
        if title_q and title_q not in (r.get("title") or "").lower():
            continue
        if agency_q and agency_q not in (r.get("agency") or "").lower():
            continue
        fs = r.get("fit_score")
        if min_fit is not None and (fs is None or fs < int(min_fit)):
            continue
        if max_fit is not None and (fs is None or fs > int(max_fit)):
            continue
        out.append({
            "id": str(r["id"]),
            "title": r.get("title"),
            "agency": r.get("agency"),
            "status": r.get("status"),
            "source_type": r.get("source_type"),
            "fit_score": r.get("fit_score"),
            "recommendation": r.get("recommendation"),
            "received_at": str(r.get("received_at")) if r.get("received_at") else None,
            "screening_id": str(r.get("screening_id")) if r.get("screening_id") else None,
        })
    return {"count": len(out), "rfps": out}


def _tool_search_past_proposals(args: Dict[str, Any]) -> Dict[str, Any]:
    q = args.get("query", "")
    k = max(1, min(int(args.get("k") or 3), 10))
    results = find_similar_proposals(q, k=k)
    return {
        "count": len(results),
        "proposals": [
            {
                "id": str(r.proposal.id),
                "title": r.proposal.title,
                "agency": r.proposal.agency,
                "outcome": r.proposal.outcome,
                "contract_value": r.proposal.contract_value,
                "similarity": round(r.similarity, 3),
                "best_section": r.best_section,
                "best_excerpt": (r.best_excerpt or "")[:400],
            }
            for r in results
        ],
    }


def _tool_get_rfp_detail(args: Dict[str, Any]) -> Dict[str, Any]:
    rfp_id = args["rfp_id"]
    try:
        rfp = get_rfp(UUID(str(rfp_id)))
    except Exception:
        return {"error": f"invalid rfp_id: {rfp_id!r}"}
    if not rfp:
        return {"error": f"no rfp with id {rfp_id}"}
    from ..db.client import latest_screening_for_rfp
    screening = latest_screening_for_rfp(rfp.id)
    return {
        "rfp": rfp.model_dump(mode="json"),
        "screening": screening.model_dump(mode="json") if screening else None,
    }


def _tool_get_past_proposal_detail(args: Dict[str, Any]) -> Dict[str, Any]:
    pid = args["proposal_id"]
    try:
        pp = get_past_proposal(UUID(str(pid)))
    except Exception:
        return {"error": f"invalid proposal_id: {pid!r}"}
    if not pp:
        return {"error": f"no past proposal with id {pid}"}
    return pp.model_dump(mode="json")


def _tool_get_screening_detail(args: Dict[str, Any]) -> Dict[str, Any]:
    from ..db.client import latest_screening_for_rfp
    rfp_id = args["rfp_id"]
    try:
        s = latest_screening_for_rfp(UUID(str(rfp_id)))
    except Exception:
        return {"error": f"invalid rfp_id: {rfp_id!r}"}
    if not s:
        return {"error": f"no screening for rfp {rfp_id}"}
    return s.model_dump(mode="json")


_TOOL_IMPL = {
    "search_rfps": _tool_search_rfps,
    "search_past_proposals": _tool_search_past_proposals,
    "get_rfp_detail": _tool_get_rfp_detail,
    "get_past_proposal_detail": _tool_get_past_proposal_detail,
    "get_screening_detail": _tool_get_screening_detail,
}


# ---------- the run loop --------------------------------------------

def run_chat_turn(body) -> Any:
    """Drive one tool-calling loop. Returns ``ChatResponse`` (imported lazily
    to avoid circular import with main.py)."""
    from ..main import ChatResponse, ChatToolCallSummary  # local to break cycle

    cfg = get_config()
    system_prompt = (_PROMPTS_DIR / "chat_system.txt").read_text(encoding="utf-8")

    # Translate ChatTurn list into Anthropic message shape.
    history: List[Dict[str, Any]] = [
        {"role": m.role, "content": m.content} for m in body.messages
    ]
    if not history or history[-1]["role"] != "user":
        return ChatResponse(content="(no user message provided)")

    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return ChatResponse(content="(ANTHROPIC_API_KEY not set on the server)")
    client = anthropic.Anthropic(api_key=api_key)

    tool_summaries: List[Any] = []

    for _ in range(_MAX_TOOL_LOOPS):
        with client.messages.stream(
            model=cfg.llm.model,
            max_tokens=_CHAT_MAX_TOKENS,
            temperature=_CHAT_TEMPERATURE,
            system=system_prompt,
            tools=TOOL_DEFS,
            messages=history,
        ) as stream:
            final = stream.get_final_message()

        tool_uses = [b for b in final.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            text = "".join(
                b.text for b in final.content if getattr(b, "type", None) == "text"
            )
            # Audit the call (best-effort).
            try:
                from ..db.client import write_audit
                write_audit(AuditEntry(
                    entity_type="chat", action="chat_response", actor="claude",
                    details={
                        "input_turns": len(body.messages),
                        "tools_used": [t.tool for t in tool_summaries],
                        "model": cfg.llm.model,
                    },
                ))
            except Exception:
                log.exception("chat audit write failed")
            return ChatResponse(content=text.strip(), tool_calls=tool_summaries)

        # Append the assistant turn (model's tool requests) and run each tool.
        history.append({"role": "assistant", "content": [b.model_dump() for b in final.content]})
        tool_results: List[Dict[str, Any]] = []
        for tu in tool_uses:
            name = tu.name
            args = tu.input or {}
            impl = _TOOL_IMPL.get(name)
            if impl is None:
                result_obj = {"error": f"unknown tool {name!r}"}
            else:
                try:
                    result_obj = impl(args)
                except Exception as exc:
                    log.exception("tool %s failed", name)
                    result_obj = {"error": f"{type(exc).__name__}: {exc}"}
            summary = json.dumps(result_obj, default=str)
            tool_summaries.append(ChatToolCallSummary(
                tool=name, input=args, output_summary=(summary[:300] + "…") if len(summary) > 300 else summary,
            ))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": summary,
            })
        history.append({"role": "user", "content": tool_results})

    # Loop hit max iterations without a final text response.
    return ChatResponse(
        content="(stopped after the maximum tool-loop iterations — try rephrasing the question)",
        tool_calls=tool_summaries,
    )
