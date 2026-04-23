"""Look up past proposals most similar to an RFP query string.

Aggregation strategy: embed the query, fetch top-N chunks by cosine
distance, then collapse to proposal level keeping each proposal's
*best* chunk as the explainability excerpt. Simpler than re-ranking,
good enough for POC scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..db.client import find_similar_chunks, get_past_proposals
from ..models.past_proposal import PastProposal
from .embeddings import embed_one


@dataclass
class SimilarProposal:
    proposal: PastProposal
    similarity: float             # 0.0-1.0 (1 == identical), derived from cosine distance
    best_section: Optional[str]   # section that produced the top match
    best_excerpt: Optional[str]   # the actual chunk text — for UI rationale


def find_similar_proposals(
    query_text: str,
    *,
    k: int = 3,
    chunk_candidates: int = 20,
) -> List[SimilarProposal]:
    """Return the top-``k`` past proposals most similar to ``query_text``.

    Fetches ``chunk_candidates`` chunks from Postgres, rolls them up to the
    proposal level, and returns the best ``k`` proposals.
    """
    if not query_text.strip():
        return []

    embedding = embed_one(query_text)
    chunks = find_similar_chunks(embedding, k=chunk_candidates)
    if not chunks:
        return []

    # Roll up: keep the best (smallest-distance) chunk per proposal.
    best_per_proposal: dict = {}
    for row in chunks:
        pid = row["past_proposal_id"]
        distance = float(row["distance"])
        current = best_per_proposal.get(pid)
        if current is None or distance < current["distance"]:
            best_per_proposal[pid] = {
                "distance": distance,
                "section": row["chunk_section"],
                "excerpt": row["chunk_text"],
            }

    # Sort proposals by best chunk distance, take top k.
    top = sorted(best_per_proposal.items(), key=lambda kv: kv[1]["distance"])[:k]
    proposals = {
        pp.id: pp for pp in get_past_proposals([pid for pid, _ in top])
    }

    out: List[SimilarProposal] = []
    for pid, info in top:
        pp = proposals.get(pid)
        if not pp:
            continue
        # pgvector's <=> returns cosine *distance*; similarity is 1 - distance,
        # clipped because tiny numerical noise can push it slightly outside.
        similarity = max(0.0, min(1.0, 1.0 - info["distance"]))
        out.append(
            SimilarProposal(
                proposal=pp,
                similarity=similarity,
                best_section=info["section"],
                best_excerpt=info["excerpt"],
            )
        )
    return out
