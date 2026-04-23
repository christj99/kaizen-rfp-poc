"""Parse past-proposal Markdown files → PastProposal + chunk+embed → Postgres.

File format (see ``sample_data/past_proposals/`` for examples):

    # Free-form title comment lines (YAML comments, stripped by yaml.safe_load)
    # …

    metadata:
      proposal_id: "PP-…"
      title: "…"
      client: "…"
      submitted_date: "YYYY-MM-DD"
      contract_value: 8_400_000
      outcome: "won" | "lost" | "withdrawn"
      …

    ---

    ## Executive Summary
    <body>

    ## Company Qualifications
    <body>

    … etc.

The separator between metadata and body is a line consisting only of ``---``.
Sections under the body are delimited by ``## `` headers.

Can be run as ``python -m services.api.rag.indexer`` to (re)index every file
under ``sample_data/past_proposals/``.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

import yaml

from ..db.client import (
    delete_all_past_proposals,
    insert_past_proposal,
    past_proposal_count,
)
from ..models.past_proposal import PastProposal
from .embeddings import embed_texts


DEFAULT_PAST_PROPOSALS_DIR = (
    Path(__file__).resolve().parents[3] / "sample_data" / "past_proposals"
)

_SEPARATOR_RE = re.compile(r"^\s*---\s*$", re.MULTILINE)
_SECTION_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

# ~350 words ≈ 500 tokens for most English prose. Close enough for POC RAG.
DEFAULT_CHUNK_WORD_BUDGET = 350


@dataclass
class PastProposalDocument:
    """Parsed-but-not-yet-persisted view of a past proposal file."""

    path: Path
    metadata: Dict[str, object]
    sections: Dict[str, str]  # {section_name: section_body}
    full_text: str            # body only (metadata stripped)

    def to_model(self) -> PastProposal:
        md = self.metadata
        contract_value = md.get("contract_value")
        if isinstance(contract_value, str):
            try:
                contract_value = int(contract_value.replace(",", "").replace("_", ""))
            except ValueError:
                contract_value = None

        submitted = md.get("submitted_date")
        if isinstance(submitted, str):
            try:
                submitted = date.fromisoformat(submitted)
            except ValueError:
                submitted = None

        return PastProposal(
            id=uuid4(),
            title=md.get("title") or self.path.stem,  # type: ignore[arg-type]
            agency=md.get("client") or md.get("agency"),  # type: ignore[arg-type]
            submitted_date=submitted,  # type: ignore[arg-type]
            outcome=md.get("outcome"),  # type: ignore[arg-type]
            contract_value=contract_value,  # type: ignore[arg-type]
            full_text=self.full_text,
            sections=self.sections,
            metadata={k: v for k, v in md.items()},
        )


def parse_past_proposal_file(path: Path) -> PastProposalDocument:
    """Split a proposal file into metadata + per-section body text."""
    raw = path.read_text(encoding="utf-8")

    # Header block is everything before the first bare "---" line on its own.
    # Body is everything after.
    parts = _SEPARATOR_RE.split(raw, maxsplit=1)
    if len(parts) != 2:
        raise ValueError(
            f"{path.name}: expected a '---' separator between metadata and body"
        )
    header_text, body_text = parts[0], parts[1].lstrip("\n")

    parsed_header = yaml.safe_load(header_text) or {}
    if not isinstance(parsed_header, dict):
        raise ValueError(f"{path.name}: header block is not a YAML mapping")
    metadata = parsed_header.get("metadata", {}) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"{path.name}: 'metadata' key is not a mapping")

    sections = _split_sections(body_text)
    return PastProposalDocument(
        path=path,
        metadata=metadata,
        sections=sections,
        full_text=body_text.strip(),
    )


def _split_sections(body: str) -> Dict[str, str]:
    """Split a Markdown body into {section_name: section_body}.

    If no ``## `` headers are found, the whole body goes under ``"body"``.
    """
    headers = list(_SECTION_HEADER_RE.finditer(body))
    if not headers:
        return {"body": body.strip()}

    sections: Dict[str, str] = {}
    for idx, match in enumerate(headers):
        name = match.group(1).strip()
        start = match.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else len(body)
        chunk = body[start:end].strip()
        sections[name] = chunk
    return sections


def chunk_section(
    text: str, *, word_budget: int = DEFAULT_CHUNK_WORD_BUDGET
) -> List[str]:
    """Greedily pack paragraphs into ~``word_budget``-word chunks."""
    if not text.strip():
        return []

    # Paragraph-first splitting preserves semantic boundaries.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: List[str] = []
    buffer: List[str] = []
    buffer_words = 0

    for para in paragraphs:
        words = para.split()
        if buffer and buffer_words + len(words) > word_budget:
            chunks.append("\n\n".join(buffer))
            buffer = []
            buffer_words = 0
        # A single paragraph longer than the budget still goes in whole — we
        # don't hard-split mid-sentence for a POC.
        buffer.append(para)
        buffer_words += len(words)

    if buffer:
        chunks.append("\n\n".join(buffer))
    return chunks


def build_chunks(
    doc: PastProposalDocument, *, word_budget: int = DEFAULT_CHUNK_WORD_BUDGET
) -> List[Tuple[str, str]]:
    """Flatten doc sections → ``[(section_name, chunk_text), ...]``."""
    out: List[Tuple[str, str]] = []
    for name, body in doc.sections.items():
        for chunk in chunk_section(body, word_budget=word_budget):
            out.append((name, chunk))
    return out


def index_past_proposals_dir(
    directory: Optional[Path] = None,
    *,
    replace_existing: bool = True,
    word_budget: int = DEFAULT_CHUNK_WORD_BUDGET,
) -> List[PastProposal]:
    """Parse, chunk, embed, and persist every ``*.md`` under ``directory``."""
    target_dir = directory or DEFAULT_PAST_PROPOSALS_DIR
    files = sorted(target_dir.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No .md files found in {target_dir}")

    if replace_existing:
        removed = delete_all_past_proposals()
        print(f"[indexer] cleared {removed} existing past_proposals")

    persisted: List[PastProposal] = []
    for path in files:
        doc = parse_past_proposal_file(path)
        chunks = build_chunks(doc, word_budget=word_budget)
        if not chunks:
            print(f"[indexer] {path.name}: no chunks, skipping")
            continue

        texts = [c[1] for c in chunks]
        embeddings = embed_texts(texts)

        model = doc.to_model()
        triples = [
            (section, text, embedding)
            for (section, text), embedding in zip(chunks, embeddings)
        ]
        insert_past_proposal(model, triples)
        persisted.append(model)
        print(
            f"[indexer] {path.name}: {len(chunks)} chunks -> "
            f"proposal_id={model.id} (outcome={model.outcome})"
        )

    print(f"[indexer] total proposals now in DB: {past_proposal_count()}")
    return persisted


def _cli(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Index past proposals for RAG.")
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Directory of past-proposal .md files (default: sample_data/past_proposals)",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Don't wipe past_proposals + chunks before indexing.",
    )
    parser.add_argument(
        "--word-budget",
        type=int,
        default=DEFAULT_CHUNK_WORD_BUDGET,
        help=f"Target words per chunk (default: {DEFAULT_CHUNK_WORD_BUDGET}).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    index_past_proposals_dir(
        directory=args.dir,
        replace_existing=not args.keep_existing,
        word_budget=args.word_budget,
    )
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
