"""Screening agent.

Orchestrates RAG retrieval + prompt rendering + a Claude call, then
translates the model's JSON into a persisted ``Screening`` row.

Failure modes handled here:

* Claude returns invalid JSON -> one retry via ``LLMClient`` at temp=0; if it
  still fails, an ``error`` screening is persisted so the UI can surface it.
* Required top-level fields missing -> captured as a parse error with the raw
  response stored in the rationale for postmortem.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..config.loader import get_config
from ..db.client import insert_screening, update_rfp_status
from ..llm.client import LLMClient, LLMError
from ..models.rfp import RFP
from ..models.screening import (
    DealBreaker,
    HardDisqualifierResult,
    OpenQuestion,
    RubricDimensionScore,
    Screening,
    ScreeningRationale,
    SimilarProposalAnalysis,
)
from ..rag.retriever import SimilarProposal, find_similar_proposals

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_DIR = _REPO_ROOT / "config"
_PROMPTS_DIR = _REPO_ROOT / "services" / "api" / "llm" / "prompts"

_PLACEHOLDER = "(not specified)"


# -- public ------------------------------------------------------------

def screen_rfp(
    rfp: RFP,
    *,
    llm_client: Optional[LLMClient] = None,
    k_similar: int = 3,
    persist: bool = True,
) -> Screening:
    """Run the screening agent on ``rfp`` and return the ``Screening``.

    Set ``persist=False`` for dry-runs (tests, calibration runs the user
    doesn't want to save).
    """
    profile_yaml = (_CONFIG_DIR / "company_profile.yaml").read_text(encoding="utf-8")
    rubric_yaml = (_CONFIG_DIR / "fit_rubric.yaml").read_text(encoding="utf-8")
    rubric_version = _rubric_version(rubric_yaml)

    retrieval_query = _build_retrieval_query(rfp)
    similar = find_similar_proposals(retrieval_query, k=k_similar)

    system_prompt = (_PROMPTS_DIR / "screening_system.txt").read_text(encoding="utf-8")
    user_template = (_PROMPTS_DIR / "screening_user.txt").read_text(encoding="utf-8")
    user_prompt = _render_template(
        user_template,
        _build_prompt_vars(rfp, profile_yaml, rubric_yaml, similar),
    )

    client = llm_client or LLMClient()
    cfg = get_config()

    try:
        response = client.call_claude(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            # Empty schema triggers the LLMClient's fence-stripping + retry-on-parse-failure
            # path without cluttering the system prompt; the prompt itself already specifies
            # the detailed schema.
            response_schema={"type": "object"},
            audit_entity_type="rfp",
            audit_entity_id=rfp.id,
            audit_action="screen_rfp",
        )
    except LLMError as exc:
        log.exception("Claude call failed for RFP %s", rfp.id)
        screening = _error_screening(rfp, cfg.llm.model, rubric_version, str(exc), similar)
        if persist:
            insert_screening(screening)
        return screening

    if not isinstance(response, dict):
        screening = _error_screening(
            rfp,
            cfg.llm.model,
            rubric_version,
            f"Claude returned non-dict payload: {type(response).__name__}",
            similar,
            raw_response=response,
        )
    else:
        screening = _translate_response(
            response, rfp, similar, rubric_version, cfg.llm.model
        )

    if persist:
        insert_screening(screening)
        update_rfp_status(rfp.id, "screened")
    return screening


# -- prompt rendering --------------------------------------------------

def _render_template(template: str, variables: Dict[str, str]) -> str:
    """Substitute ``{{key}}`` markers with ``variables[key]``.

    Unknown markers are left as-is — makes missing substitutions visible at
    review time rather than silently blanking content.
    """
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def _build_prompt_vars(
    rfp: RFP,
    profile_yaml: str,
    rubric_yaml: str,
    similar: List[SimilarProposal],
) -> Dict[str, str]:
    today = date.today()
    due_iso = rfp.due_date.date().isoformat() if rfp.due_date else _PLACEHOLDER
    days_to_deadline = _PLACEHOLDER
    if rfp.due_date:
        delta = (rfp.due_date.date() - today).days
        days_to_deadline = str(delta)

    return {
        "rfp_title": rfp.title or _PLACEHOLDER,
        "rfp_agency": rfp.agency or _PLACEHOLDER,
        "rfp_solicitation_number": rfp.external_id or _PLACEHOLDER,
        "rfp_naics": ", ".join(rfp.naics_codes) if rfp.naics_codes else _PLACEHOLDER,
        "rfp_set_aside": _PLACEHOLDER,              # not in schema yet; reserved for richer SAM.gov ingest
        "rfp_value_estimate": _format_value_range(rfp) or _PLACEHOLDER,
        "rfp_due_date": due_iso,
        "rfp_place_of_performance": _PLACEHOLDER,   # likewise
        "rfp_full_text": rfp.full_text or _PLACEHOLDER,
        "company_profile_yaml": profile_yaml.strip(),
        "fit_rubric_yaml": rubric_yaml.strip(),
        "similar_past_proposals_block": _format_similar_block(similar),
        "current_pursuit_load": _PLACEHOLDER,        # POC doesn't track in-flight pursuits
        "days_to_deadline": days_to_deadline,
        "current_date": today.isoformat(),
    }


def _build_retrieval_query(rfp: RFP) -> str:
    """Compose the text we embed for similar-proposal lookup.

    Title + agency + full text gives the embedding enough signal; we truncate
    to keep the call fast and within OpenAI limits.
    """
    parts: List[str] = []
    if rfp.title:
        parts.append(rfp.title)
    if rfp.agency:
        parts.append(f"Agency: {rfp.agency}")
    if rfp.naics_codes:
        parts.append("NAICS: " + ", ".join(rfp.naics_codes))
    if rfp.full_text:
        parts.append(rfp.full_text[:4000])
    return "\n\n".join(parts)


def _format_value_range(rfp: RFP) -> Optional[str]:
    low = rfp.value_estimate_low
    high = rfp.value_estimate_high
    if low and high and low != high:
        return f"${low:,} - ${high:,}"
    if low:
        return f"${low:,}"
    if high:
        return f"${high:,}"
    return None


def _format_similar_block(similar: List[SimilarProposal]) -> str:
    if not similar:
        return "(no similar past proposals retrieved)"
    lines: List[str] = []
    for i, s in enumerate(similar, start=1):
        pp = s.proposal
        outcome = (pp.outcome or "unknown").upper()
        value_bit = f" - ${pp.contract_value:,}" if pp.contract_value else ""
        lines.append(f"## Similar proposal #{i}")
        lines.append(f"- proposal_id: {pp.id}")
        lines.append(f"- title: {pp.title}")
        lines.append(f"- agency: {pp.agency}")
        lines.append(f"- outcome: {outcome}{value_bit}")
        lines.append(f"- similarity: {s.similarity:.3f}")
        lines.append(f"- top matching section: {s.best_section}")
        if s.best_excerpt:
            excerpt = s.best_excerpt.strip().replace("\n", " ")
            if len(excerpt) > 500:
                excerpt = excerpt[:500] + "..."
            lines.append(f"- excerpt: {excerpt}")
        lines.append("")
    return "\n".join(lines)


# -- response translation ---------------------------------------------

_RECOMMENDATION_VALUES = {"pursue", "maybe", "skip"}
_EFFORT_VALUES = {"low", "medium", "high"}
_CONFIDENCE_VALUES = {"low", "medium", "high"}


def _coerce_enum(value: Any, allowed: set) -> Optional[str]:
    """Coerce a free-form model response to a known Literal or None.

    Claude occasionally returns 'n/a', 'unknown', 'not applicable', etc. for
    low-information RFPs. Rather than 500 on validation, we surface these as
    None so the UI can show them as 'not assessed'.
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    return s if s in allowed else None


def _translate_response(
    data: Dict[str, Any],
    rfp: RFP,
    similar: List[SimilarProposal],
    rubric_version: Optional[str],
    model_name: str,
) -> Screening:
    rationale = ScreeningRationale(
        recommendation_rationale=_safe_str(data.get("recommendation_rationale")),
        confidence_level=_coerce_enum(data.get("confidence_level"), _CONFIDENCE_VALUES),
        confidence_notes=_safe_str(data.get("confidence_notes")),
        hard_disqualifier_results=[
            HardDisqualifierResult.model_validate(x)
            for x in data.get("hard_disqualifier_results", [])
            if isinstance(x, dict)
        ],
        dimensions=[
            RubricDimensionScore.model_validate(x)
            for x in data.get("dimension_scores", [])
            if isinstance(x, dict)
        ],
        effort_reasoning=_safe_str(data.get("effort_reasoning")),
        similar_past_proposals_analysis=[
            SimilarProposalAnalysis.model_validate(x)
            for x in data.get("similar_past_proposals_analysis", [])
            if isinstance(x, dict)
        ],
        calibration_notes=_safe_str(data.get("calibration_notes")),
    )
    deal_breakers = [
        DealBreaker.model_validate(x)
        for x in data.get("deal_breakers", [])
        if isinstance(x, dict)
    ]
    open_questions = [
        OpenQuestion.model_validate(x)
        for x in data.get("open_questions", [])
        if isinstance(x, dict)
    ]

    raw_score = data.get("fit_score")
    fit_score: Optional[int]
    try:
        fit_score = int(raw_score) if raw_score is not None else None
    except (TypeError, ValueError):
        fit_score = None

    return Screening(
        rfp_id=rfp.id,
        fit_score=fit_score,
        recommendation=_coerce_enum(data.get("recommendation"), _RECOMMENDATION_VALUES),
        rationale=rationale,
        effort_estimate=_coerce_enum(data.get("effort_estimate"), _EFFORT_VALUES),
        deal_breakers=deal_breakers,
        open_questions=open_questions,
        similar_proposal_ids=[s.proposal.id for s in similar],
        model_version=model_name,
        rubric_version=rubric_version,
        created_at=datetime.now(timezone.utc),
    )


def _error_screening(
    rfp: RFP,
    model_name: str,
    rubric_version: Optional[str],
    message: str,
    similar: List[SimilarProposal],
    raw_response: Any = None,
) -> Screening:
    """Persist something recognizable on failure instead of swallowing silently."""
    rationale = ScreeningRationale(
        recommendation_rationale=f"[screening error] {message}",
        confidence_level="low",
        confidence_notes="Claude call failed — see audit_log and calibration_notes for raw payload.",
        calibration_notes=(
            json.dumps(raw_response, default=str)[:2000]
            if raw_response is not None
            else None
        ),
    )
    return Screening(
        rfp_id=rfp.id,
        fit_score=None,
        recommendation=None,
        rationale=rationale,
        similar_proposal_ids=[s.proposal.id for s in similar],
        model_version=model_name,
        rubric_version=rubric_version,
    )


def _rubric_version(rubric_yaml: str) -> Optional[str]:
    try:
        data = yaml.safe_load(rubric_yaml)
        if isinstance(data, dict):
            v = data.get("version")
            return str(v) if v is not None else None
    except yaml.YAMLError:
        pass
    return None


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)
