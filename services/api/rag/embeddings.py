"""OpenAI embeddings wrapper.

Anthropic doesn't offer an embeddings endpoint (as of plan writing), so
RAG uses ``text-embedding-3-small`` — 1536 dims to match ``schema.sql``.

A single batch call per invocation; the sample past-proposal corpus is
small enough that batching 100 inputs at a time is plenty.
"""

from __future__ import annotations

import os
from typing import List, Sequence

from openai import OpenAI

from .. import _env  # noqa: F401 — populates os.environ from .env

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

_BATCH_SIZE = 100


class EmbeddingError(RuntimeError):
    pass


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EmbeddingError(
            "OPENAI_API_KEY not set. Embeddings are required for RAG; "
            "populate .env before running the indexer."
        )
    _client = OpenAI(api_key=api_key)
    return _client


def embed_texts(texts: Sequence[str], *, model: str = EMBEDDING_MODEL) -> List[List[float]]:
    """Return one embedding vector per input. Preserves input order."""
    if not texts:
        return []
    client = _get_client()
    out: List[List[float]] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = list(texts[start : start + _BATCH_SIZE])
        resp = client.embeddings.create(model=model, input=batch)
        # The OpenAI SDK returns data ordered to match input.
        out.extend(item.embedding for item in resp.data)
    return out


def embed_one(text: str, *, model: str = EMBEDDING_MODEL) -> List[float]:
    return embed_texts([text], model=model)[0]
