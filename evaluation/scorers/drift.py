"""
evaluation/scorers/drift.py

Cosine similarity scorer: is the current query drifting from the conversation topic?
Compares the current query embedding against the previous query embedding stored
in a simple in-memory cache keyed by conversation_id.

Returns a float 0.0–1.0 where:
  1.0 = same topic (no drift)
  0.0 = completely off-topic
  None = first turn (no previous query to compare)
"""

import structlog
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

log = structlog.get_logger()

# In-memory store: conversation_id → last query embedding
# Good enough for InMemorySaver backend; for Redis/Postgres backends
# this should also move to the same persistent store (TODO).
_last_embeddings: dict[str, list[float]] = {}


def _embed(text: str) -> list[float]:
    """
    Simple TF-style character n-gram embedding using tiktoken token IDs.
    Lightweight, no model call needed. Replace with a real embedding model
    for production-quality drift detection.

    TODO: swap for AzureOpenAIEmbeddings or a local sentence-transformer.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text.lower())
        if not tokens:
            return [0.0] * 100

        # Build a fixed-size frequency vector over token id buckets
        vec = [0.0] * 100
        for t in tokens:
            vec[t % 100] += 1.0

        # L2 normalise
        norm = sum(x ** 2 for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    except Exception:
        return [0.0] * 100


async def score(
    query: str,
    answer: str,
    context: str = "",
    conversation_id: str = "",
    **kwargs,
) -> float | None:
    try:
        current_embedding = _embed(query)

        if not conversation_id or conversation_id not in _last_embeddings:
            # First turn — store and return None (no drift to measure yet)
            if conversation_id:
                _last_embeddings[conversation_id] = current_embedding
            return None

        prev_embedding = _last_embeddings[conversation_id]

        # Update stored embedding for next turn
        _last_embeddings[conversation_id] = current_embedding

        # Cosine similarity between current and previous query
        sim = cosine_similarity(
            np.array(current_embedding).reshape(1, -1),
            np.array(prev_embedding).reshape(1, -1),
        )[0][0]

        return float(round(max(0.0, min(1.0, sim)), 4))

    except Exception as e:
        log.warning("eval.drift.failed", error=str(e))
        return None
