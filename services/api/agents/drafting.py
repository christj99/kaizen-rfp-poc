"""Drafting agent.

One call to Claude produces the whole first-draft proposal — the
system prompt (``drafting_system.txt``) encodes per-section logic
(static/semi_static/dynamic) so Python here only orchestrates
inputs, parses the JSON response, and persists.

The agent never fabricates facts: the system prompt's rules +
``provenance.human_review_required`` flags guarantee that pricing
numbers, named personnel, and similar high-risk fields show up as
explicit placeholders rather than invented plausible-looking data.
Reviewers trust the UI's per-section provenance badges to know what
to scrutinize.

End-to-end flow:
1. Load company_profile.yaml + proposal_template.yaml + drafting_system.txt
2. Retrieve 3-5 similar past proposals via the RAG retriever
3. Build a user prompt that includes RFP, screening, profile, template,
   past-proposal context (with section text and stable proposal_ids so
   Claude can cite them in ``provenance.source_ids``)
4. Call Claude with a larger max_tokens budget — drafts are long
5. Parse the JSON output into a ``Draft`` with typed ``DraftSection``s
6. Persist, transition rfp.status -> 'in_draft', audit-log the call
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..config.loader import get_config
from ..db.client import (
    get_past_proposal,
    insert_draft,
    latest_screening_for_rfp,
    update_rfp_status,
)
from ..llm.client import LLMClient, LLMError
from ..models.draft import Draft, DraftContent, DraftSection, DraftSectionProvenance
from ..models.rfp import RFP
from ..models.screening import Screening
from ..rag.retriever import SimilarProposal, find_similar_proposals

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_DIR = _REPO_ROOT / "config"
_PROMPTS_DIR = _REPO_ROOT / "services" / "api" / "llm" / "prompts"

# Drafting output for an 8-section first-draft proposal is typically
# 8-12k tokens; on RFPs with a heavy technical-approach section (the
# Cloud Data Warehouse / Fiscal Service-style scope) it can run higher.
# 16000 truncated mid-section in observed runs and tripped the retry
# loop with the same outcome. 32000 gives ~2-3× headroom on a realistic
# pursue-band draft. Sonnet 4.5 supports up to 64000 output tokens.
_DRAFT_MAX_TOKENS = 32000

# Map Claude's provenance.source_type strings -> our 3-value enum.
_PROVENANCE_MAP: Dict[str, DraftSectionProvenance] = {
    "generated": "generated",
    "retrieved_from_past_proposal": "retrieved",
    "retrieved_from_profile": "static",
    "static_boilerplate": "static",
}

_CONFIDENCE_MAP: Dict[str, float] = {
    "low": 0.3,
    "medium": 0.6,
    "high": 0.9,
}


class DraftingError(Exception):
    pass


# -- public ------------------------------------------------------------

def draft_proposal(
    rfp: RFP,
    *,
    screening: Optional[Screening] = None,
    llm_client: Optional[LLMClient] = None,
    k_similar: int = 3,
    persist: bool = True,
) -> Draft:
    """Generate a first-draft proposal for ``rfp``.

    ``screening`` is looked up from the DB when not provided. A draft can
    still be produced without a screening (e.g. for a manual "draft this
    even though I haven't screened" UX), but the prompt is more effective
    with one present.
    """
    if screening is None:
        screening = latest_screening_for_rfp(rfp.id)

    profile_yaml = (_CONFIG_DIR / "company_profile.yaml").read_text(encoding="utf-8")
    template_yaml = (_CONFIG_DIR / "proposal_template.yaml").read_text(encoding="utf-8")
    system_prompt = (_PROMPTS_DIR / "drafting_system.txt").read_text(encoding="utf-8")

    similar = find_similar_proposals(_build_retrieval_query(rfp), k=k_similar)
    user_prompt = _build_user_prompt(
        rfp=rfp,
        screening=screening,
        profile_yaml=profile_yaml,
        template_yaml=template_yaml,
        similar=similar,
    )

    client = llm_client or LLMClient()
    cfg = get_config()

    try:
        response = client.call_claude(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema={"type": "object"},   # triggers fence-strip + JSON-retry
            max_tokens=_DRAFT_MAX_TOKENS,
            audit_entity_type="rfp",
            audit_entity_id=rfp.id,
            audit_action="draft_proposal",
        )
    except LLMError as exc:
        log.exception("Drafting LLM call failed for %s", rfp.id)
        raise DraftingError(f"Drafting LLM call failed: {exc}") from exc

    if not isinstance(response, dict):
        raise DraftingError(
            f"Drafting returned non-dict payload: {type(response).__name__}"
        )

    sections = _parse_sections(response, similar)
    retrieved_ids = _collect_retrieved_ids(sections)

    draft = Draft(
        rfp_id=rfp.id,
        screening_id=screening.id if screening else None,
        content=DraftContent(sections=sections),
        retrieved_proposal_ids=retrieved_ids,
        status="generated",
        created_at=datetime.now(timezone.utc),
    )

    if persist:
        insert_draft(draft, overall_metadata=response.get("overall_metadata") or {})
        # Only advance status if we're not already further along.
        if rfp.status in ("new", "screened"):
            update_rfp_status(rfp.id, "in_draft")

    return draft


# -- prompt assembly --------------------------------------------------

def _build_retrieval_query(rfp: RFP) -> str:
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


def _build_user_prompt(
    *,
    rfp: RFP,
    screening: Optional[Screening],
    profile_yaml: str,
    template_yaml: str,
    similar: List[SimilarProposal],
) -> str:
    parts: List[str] = []

    parts.append("# The RFP")
    parts.append(f"**rfp_id:** {rfp.id}")
    parts.append(f"**Title:** {rfp.title or '(not specified)'}")
    parts.append(f"**Agency:** {rfp.agency or '(not specified)'}")
    parts.append(f"**Solicitation Number:** {rfp.external_id or '(not specified)'}")
    parts.append(
        f"**NAICS:** {', '.join(rfp.naics_codes) if rfp.naics_codes else '(not specified)'}"
    )
    parts.append(
        f"**Due Date:** {rfp.due_date.isoformat() if rfp.due_date else '(not specified)'}"
    )
    parts.append("")
    parts.append("**Full RFP text:**")
    parts.append("")
    parts.append(rfp.full_text or "(no full text available)")
    parts.append("")

    parts.append("---")
    parts.append("")
    parts.append("# Screening Assessment")
    if screening:
        parts.append(f"- fit_score: {screening.fit_score}")
        parts.append(f"- recommendation: {screening.recommendation}")
        parts.append(f"- effort_estimate: {screening.effort_estimate}")
        parts.append(f"- rubric_version: {screening.rubric_version}")
        if screening.rationale.recommendation_rationale:
            parts.append(f"- rationale: {screening.rationale.recommendation_rationale}")
        if screening.deal_breakers:
            parts.append("- deal_breakers:")
            for db in screening.deal_breakers:
                parts.append(f"  - [{db.severity}] {db.concern}")
        if screening.open_questions:
            parts.append("- open_questions (incorporate as assumptions or flag for human):")
            for oq in screening.open_questions:
                parts.append(f"  - {oq.question}")
    else:
        parts.append("(no screening run for this RFP — proceed with the full RFP text)")
    parts.append("")

    parts.append("---")
    parts.append("")
    parts.append("# Meridian Company Profile")
    parts.append("")
    parts.append("```yaml")
    parts.append(profile_yaml.strip())
    parts.append("```")
    parts.append("")

    parts.append("---")
    parts.append("")
    parts.append("# Proposal Template")
    parts.append("")
    parts.append("```yaml")
    parts.append(template_yaml.strip())
    parts.append("```")
    parts.append("")

    parts.append("---")
    parts.append("")
    parts.append("# Most Similar Past Proposals")
    parts.append("")
    parts.append(
        "Use these for semi-static section adaptation and dynamic section "
        "structural patterns. Cite proposal_ids in `provenance.source_ids` when "
        "you adapt from a specific past proposal."
    )
    parts.append("")
    parts.append(_format_similar_block(similar))
    parts.append("")

    parts.append("---")
    parts.append("")
    parts.append(
        "Now produce the full first-draft proposal as a JSON object per the "
        "schema in your system instructions. Respect section types. Never "
        "invent facts or numbers. Flag explicitly what the proposal lead must "
        "complete. Output the JSON only."
    )

    return "\n".join(parts)


def _format_similar_block(similar: List[SimilarProposal]) -> str:
    if not similar:
        return "(no similar past proposals retrieved)"
    out: List[str] = []
    for i, s in enumerate(similar, start=1):
        pp = s.proposal
        out.append(f"## Past Proposal #{i}")
        out.append(f"- proposal_id: {pp.id}")
        out.append(f"- title: {pp.title}")
        out.append(f"- agency: {pp.agency}")
        out.append(f"- outcome: {pp.outcome or 'unknown'}")
        if pp.contract_value:
            out.append(f"- contract_value: ${pp.contract_value:,}")
        out.append(f"- similarity: {s.similarity:.3f}")
        out.append("")
        out.append("### Sections")
        if pp.sections:
            for section_name, section_text in pp.sections.items():
                if not section_text:
                    continue
                # Keep prompt-size reasonable: full text when short, summary when huge.
                clipped = section_text.strip()
                if len(clipped) > 2500:
                    clipped = clipped[:2500] + "\n[...truncated for prompt size...]"
                out.append(f"#### {section_name}")
                out.append(clipped)
                out.append("")
        out.append("")
    return "\n".join(out)


# -- response parsing -------------------------------------------------

def _parse_sections(
    payload: Dict[str, Any],
    similar: List[SimilarProposal],
) -> List[DraftSection]:
    raw_sections = payload.get("sections") or []
    if not isinstance(raw_sections, list):
        raise DraftingError(f"Expected 'sections' to be a list, got {type(raw_sections).__name__}")

    valid_retrieved_ids = {s.proposal.id for s in similar}
    out: List[DraftSection] = []

    for raw in raw_sections:
        if not isinstance(raw, dict):
            continue
        content = raw.get("content") or ""
        if not isinstance(content, str):
            content = str(content)
        prov = raw.get("provenance") or {}

        provenance: DraftSectionProvenance = _PROVENANCE_MAP.get(
            str(prov.get("source_type") or "").strip().lower(),
            "generated",
        )

        source_proposal_id = _first_valid_uuid(
            prov.get("source_ids"),
            allowed=valid_retrieved_ids,
        )
        confidence = _CONFIDENCE_MAP.get(
            str(prov.get("confidence") or "").strip().lower(),
            None,
        )
        needs_review = bool(prov.get("human_review_required"))
        review_notes = (
            str(prov.get("review_notes")) if prov.get("review_notes") else None
        )

        out.append(
            DraftSection(
                name=str(raw.get("name") or raw.get("section_id") or "Untitled section"),
                content=content,
                provenance=provenance,
                source_proposal_id=source_proposal_id,
                confidence=confidence,
                needs_review=needs_review,
                notes=review_notes,
            )
        )
    return out


def _first_valid_uuid(
    value: Any, *, allowed: set
) -> Optional[UUID]:
    """Best-effort conversion of Claude's first source_id to a UUID.

    Ignores anything that doesn't parse OR that isn't in the retrieved set —
    defends against the model inventing a plausible-looking UUID.
    """
    if not isinstance(value, list):
        return None
    for item in value:
        if item is None:
            continue
        try:
            candidate = UUID(str(item).strip())
        except (ValueError, TypeError):
            continue
        if candidate in allowed:
            return candidate
    return None


def _collect_retrieved_ids(sections: List[DraftSection]) -> List[UUID]:
    seen: List[UUID] = []
    for s in sections:
        if s.source_proposal_id and s.source_proposal_id not in seen:
            seen.append(s.source_proposal_id)
    return seen


# -- export -----------------------------------------------------------

def export_draft_to_markdown(
    draft: Draft,
    *,
    rfp: Optional[RFP] = None,
    overall_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a ``Draft`` as a single Markdown document for copy-paste
    into Word/Google Docs, or handoff to pandoc.

    Per-section provenance and the original overall_metadata from the
    drafting call are appended as an "Appendix — Drafting provenance"
    block so reviewers keep the audit trail.
    """
    lines: List[str] = []
    title = (rfp.title if rfp else None) or "Proposal Draft"
    lines.append(f"# {title}")
    lines.append("")
    if rfp:
        lines.append(f"_Generated for RFP {rfp.id} — {rfp.agency or ''}_")
        lines.append("")

    for section in draft.content.sections:
        lines.append(f"## {section.name}")
        lines.append("")
        if section.needs_review:
            lines.append(
                f"> **⚠ Needs review** — {section.notes or 'flagged by drafting agent'}"
            )
            lines.append("")
        lines.append(section.content)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Appendix — Drafting provenance")
    lines.append("")
    lines.append(f"- Draft id: `{draft.id}`")
    lines.append(f"- Created: {draft.created_at.isoformat()}")
    lines.append("")
    lines.append("| Section | Provenance | Confidence | Review? | Source proposal |")
    lines.append("|---|---|---|---|---|")
    for s in draft.content.sections:
        conf = f"{s.confidence:.2f}" if s.confidence is not None else "—"
        review = "yes" if s.needs_review else "no"
        src = str(s.source_proposal_id) if s.source_proposal_id else "—"
        lines.append(f"| {s.name} | {s.provenance} | {conf} | {review} | {src} |")
    if overall_metadata:
        lines.append("")
        lines.append("### Overall metadata from drafting call")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(overall_metadata, indent=2, default=str))
        lines.append("```")
    return "\n".join(lines)
