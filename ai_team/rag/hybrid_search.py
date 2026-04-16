"""Hybrid search — combines BM25 keyword search with semantic vector search via RRF.

Reciprocal Rank Fusion (RRF) merges two ranked lists without needing score normalisation.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import numpy as np

logger = logging.getLogger("ai_team.rag.hybrid")

RRF_K = 60  # RRF constant — higher = smoother fusion, less sensitive to top ranks


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric, keep identifiers intact."""
    return re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*|[0-9]+", text.lower())


def _bm25_search(chunks_data: list[dict], query: str, k: int) -> list[tuple[int, float]]:
    """Run BM25 over chunk content. Returns (index, score) pairs sorted desc."""
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        logger.warning("rank-bm25 not installed — BM25 disabled. pip install rank-bm25")
        return []

    tokenized_corpus = [_tokenize(c["content"]) for c in chunks_data]
    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = _tokenize(query)
    scores = bm25.get_scores(query_tokens)
    top_indices = np.argsort(scores)[::-1][:k]
    return [(int(i), float(scores[i])) for i in top_indices if scores[i] > 0]


def _semantic_search(
    embeddings: np.ndarray,
    query: str,
    k: int,
) -> list[tuple[int, float]]:
    """Run cosine similarity search. Returns (index, score) pairs sorted desc."""
    try:
        from ai_team.rag.store import _get_embedder

        embedder = _get_embedder()
        q_vec = np.array(embedder.embed_query(query), dtype=np.float32)
        norm = np.linalg.norm(q_vec)
        if norm > 0:
            q_vec = q_vec / norm
    except Exception as e:
        logger.error("Query embedding failed: %s", e)
        return []

    scores = embeddings @ q_vec
    top_indices = np.argsort(scores)[::-1][:k]
    return [(int(i), float(scores[i])) for i in top_indices]


def _rrf_fuse(
    ranked_lists: list[list[tuple[int, float]]],
    k: int = RRF_K,
) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion over multiple ranked lists.

    Each list is (doc_index, score). Returns fused (doc_index, rrf_score) sorted desc.
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, (idx, _) in enumerate(ranked):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def hybrid_search(
    project_dir: str,
    query: str,
    k: int = 8,
    file_glob: str | None = None,
) -> list[dict]:
    """Hybrid semantic + BM25 search with RRF fusion.

    Args:
        project_dir: Path to the project root.
        query: Natural language or identifier query.
        k: Number of results to return.
        file_glob: Optional glob pattern to restrict results (e.g. '**/routers/*.py').

    Returns list of chunk dicts with added 'score' (RRF) and 'match_type' fields.
    """
    from ai_team.rag.store import _store_paths

    chunks_path, emb_path, _ = _store_paths(project_dir)

    if not chunks_path.exists() or not emb_path.exists():
        logger.warning("RAG index not built for %s", project_dir)
        return []

    chunks_data: list[dict] = json.loads(chunks_path.read_text())
    embeddings: np.ndarray = np.load(str(emb_path))

    # Apply file_glob filter if specified
    if file_glob:
        filtered = [
            (i, c) for i, c in enumerate(chunks_data)
            if Path(c["file_path"]).match(file_glob)
        ]
        if not filtered:
            logger.warning("file_glob %r matched no chunks", file_glob)
            return []
        indices, filtered_chunks = zip(*filtered)
        indices = list(indices)
        filtered_chunks = list(filtered_chunks)
        filtered_embeddings = embeddings[indices]
    else:
        indices = list(range(len(chunks_data)))
        filtered_chunks = chunks_data
        filtered_embeddings = embeddings

    fetch_k = min(k * 3, len(filtered_chunks))  # fetch more, then fuse

    # Run both searches
    bm25_results = _bm25_search(filtered_chunks, query, fetch_k)
    semantic_results = _semantic_search(filtered_embeddings, query, fetch_k)

    # Remap local indices back to original chunk indices
    def _remap(results: list[tuple[int, float]]) -> list[tuple[int, float]]:
        return [(indices[local_i], score) for local_i, score in results]

    bm25_global = _remap(bm25_results)
    semantic_global = _remap(semantic_results)

    # Determine match type per chunk before fusion
    bm25_ids = {i for i, _ in bm25_global}
    semantic_ids = {i for i, _ in semantic_global}

    fused = _rrf_fuse([semantic_global, bm25_global])[:k]

    results = []
    for idx, rrf_score in fused:
        chunk = chunks_data[idx].copy()
        chunk["score"] = round(rrf_score, 4)

        in_bm25 = idx in bm25_ids
        in_semantic = idx in semantic_ids
        if in_bm25 and in_semantic:
            chunk["match_type"] = "hybrid"
        elif in_semantic:
            chunk["match_type"] = "semantic"
        else:
            chunk["match_type"] = "keyword"

        results.append(chunk)

    return results
