"""RAG vector store — embeds code chunks, supports hybrid search, diff-aware updates.

Storage layout per project (~/.ai-dev-team/rag/<slug>/):
  chunks.json      — chunk metadata + content
  embeddings.npy   — L2-normalised float32 vectors (N, D)
  file_mtimes.json — {rel_path: mtime} for diff-aware partial re-embedding
  meta.json        — build metadata
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger("ai_team.rag.store")

STORE_DIR = os.path.expanduser("~/.ai-dev-team/rag")
EMBEDDING_MODEL = "text-embedding-3-small"
TOP_K_DEFAULT = 8
MAX_CHUNKS_TO_EMBED = 2000


# ── Paths ────────────────────────────────────────────────────────────────────


def _project_slug(project_dir: str) -> str:
    h = hashlib.md5(project_dir.encode()).hexdigest()[:8]
    name = Path(project_dir).name.replace(" ", "_")
    return f"{name}_{h}"


def _store_paths(project_dir: str) -> tuple[Path, Path, Path, Path]:
    slug = _project_slug(project_dir)
    base = Path(STORE_DIR) / slug
    base.mkdir(parents=True, exist_ok=True)
    return (
        base / "chunks.json",
        base / "embeddings.npy",
        base / "meta.json",
        base / "file_mtimes.json",
    )


# ── Embedder ─────────────────────────────────────────────────────────────────


def _get_embedder():
    """Return a LangChain embeddings instance.

    Priority:
      1. OPENAI_API_KEY  → OpenAIEmbeddings (text-embedding-3-small)
      2. OPENAI_COMPAT_API_KEY + OPENAI_COMPAT_BASE_URL → compat endpoint
      3. Ollama → OllamaEmbeddings (free/local, needs langchain-ollama)
    """
    try:
        from langchain_openai import OpenAIEmbeddings

        openai_key = os.getenv("OPENAI_API_KEY")
        compat_key = os.getenv("OPENAI_COMPAT_API_KEY")
        compat_url = os.getenv("OPENAI_COMPAT_BASE_URL")
        rag_model = os.getenv("RAG_EMBEDDING_MODEL", EMBEDDING_MODEL)

        if openai_key:
            return OpenAIEmbeddings(model=rag_model, openai_api_key=openai_key)
        if compat_key and compat_url:
            return OpenAIEmbeddings(
                model=os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-small"),
                openai_api_key=compat_key,
                base_url=compat_url,
            )
    except Exception:
        pass

    try:
        from langchain_ollama import OllamaEmbeddings

        ollama_model = os.getenv("RAG_EMBEDDING_MODEL", "nomic-embed-text")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaEmbeddings(model=ollama_model, base_url=ollama_url)
    except Exception as e:
        raise RuntimeError(
            "No embedder available. Set OPENAI_API_KEY, or OPENAI_COMPAT_API_KEY + "
            "OPENAI_COMPAT_BASE_URL, or install langchain-ollama with Ollama running."
        ) from e


def _embed_texts(texts: list[str]) -> np.ndarray:
    """Embed texts, returns L2-normalised (N, D) float32 array."""
    embedder = _get_embedder()
    BATCH = 100
    all_vecs = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i : i + BATCH]
        all_vecs.extend(embedder.embed_documents(batch))
        logger.debug("Embedded batch %d/%d", min(i + BATCH, len(texts)), len(texts))
    arr = np.array(all_vecs, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    return arr / norms


# ── File mtime tracking for diff-aware updates ───────────────────────────────


def _read_mtimes(mtime_path: Path) -> dict[str, float]:
    if mtime_path.exists():
        try:
            return json.loads(mtime_path.read_text())
        except Exception:
            pass
    return {}


def _current_mtimes(project_dir: str) -> dict[str, float]:
    from ai_team.rag.chunker import INDEXABLE_EXTENSIONS, SKIP_DIRS

    root = Path(project_dir).expanduser().resolve()
    mtimes: dict[str, float] = {}
    try:
        for p in root.rglob("*"):
            if any(part in SKIP_DIRS or part.startswith(".") for part in p.relative_to(root).parts):
                continue
            if p.is_file() and p.suffix in INDEXABLE_EXTENSIONS:
                rel = str(p.relative_to(root))
                mtimes[rel] = p.stat().st_mtime
    except Exception:
        pass
    return mtimes


def _changed_files(old_mtimes: dict[str, float], new_mtimes: dict[str, float]) -> set[str]:
    """Files that were added, modified, or deleted."""
    changed = set()
    for rel, mtime in new_mtimes.items():
        if old_mtimes.get(rel) != mtime:
            changed.add(rel)
    for rel in old_mtimes:
        if rel not in new_mtimes:
            changed.add(rel)
    return changed


# ── Index build (diff-aware) ─────────────────────────────────────────────────


def build_index(project_dir: str, force: bool = False) -> bool:
    """Build or incrementally refresh the RAG index.

    Only re-embeds chunks from files that changed since last build.
    Returns True if any update happened, False if fully up-to-date.
    """
    from ai_team.rag.chunker import chunk_file, chunk_project

    chunks_path, emb_path, meta_path, mtime_path = _store_paths(project_dir)

    new_mtimes = _current_mtimes(project_dir)
    old_mtimes = _read_mtimes(mtime_path)
    changed = _changed_files(old_mtimes, new_mtimes)

    index_complete = chunks_path.exists() and emb_path.exists() and meta_path.exists()

    if not force and index_complete and not changed:
        logger.info("RAG index up-to-date for %s", project_dir)
        return False

    # Full rebuild on first run or forced
    if force or not index_complete:
        logger.info("Building full RAG index for %s (%d files)", project_dir, len(new_mtimes))
        chunks = chunk_project(project_dir)
        if not chunks:
            logger.warning("No chunks found in %s", project_dir)
            return False
        if len(chunks) > MAX_CHUNKS_TO_EMBED:
            logger.warning("Capping chunks at %d (was %d)", MAX_CHUNKS_TO_EMBED, len(chunks))
            chunks = chunks[:MAX_CHUNKS_TO_EMBED]
        try:
            embeddings = _embed_texts([c.content for c in chunks])
        except Exception as e:
            logger.error("Embedding failed: %s", e)
            return False

        chunks_path.write_text(json.dumps([c.to_dict() for c in chunks], indent=2))
        np.save(str(emb_path), embeddings)

    else:
        # Incremental update — only re-embed changed files
        logger.info("Incremental RAG update: %d changed files in %s", len(changed), project_dir)
        existing_chunks: list[dict] = json.loads(chunks_path.read_text())
        existing_embeddings: np.ndarray = np.load(str(emb_path))

        # Remove stale chunks (from changed/deleted files)
        keep_mask = [c["file_path"] not in changed for c in existing_chunks]
        kept_chunks = [c for c, keep in zip(existing_chunks, keep_mask) if keep]
        kept_embeddings = existing_embeddings[keep_mask]

        # Chunk and embed only the changed files that still exist
        root = Path(project_dir).expanduser().resolve()
        new_chunks = []
        for rel_path in changed:
            fpath = root / rel_path
            if fpath.exists() and fpath.is_file():
                new_chunks.extend(chunk_file(fpath, rel_path))

        if new_chunks:
            try:
                new_embeddings = _embed_texts([c.content for c in new_chunks])
            except Exception as e:
                logger.error("Incremental embedding failed: %s", e)
                return False
            all_chunks = kept_chunks + [c.to_dict() for c in new_chunks]
            all_embeddings = np.vstack([kept_embeddings, new_embeddings])
        else:
            all_chunks = kept_chunks
            all_embeddings = kept_embeddings

        # Enforce cap
        if len(all_chunks) > MAX_CHUNKS_TO_EMBED:
            all_chunks = all_chunks[:MAX_CHUNKS_TO_EMBED]
            all_embeddings = all_embeddings[:MAX_CHUNKS_TO_EMBED]

        chunks_path.write_text(json.dumps(all_chunks, indent=2))
        np.save(str(emb_path), all_embeddings)

    mtime_path.write_text(json.dumps(new_mtimes))
    meta_path.write_text(json.dumps({
        "project_dir": project_dir,
        "chunk_count": len(json.loads(chunks_path.read_text())),
        "embedding_model": os.getenv("RAG_EMBEDDING_MODEL", EMBEDDING_MODEL),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "changed_files": len(changed),
    }, indent=2))

    logger.info("RAG index ready: %d chunks", len(json.loads(chunks_path.read_text())))
    return True


# ── Search ───────────────────────────────────────────────────────────────────


def search(
    project_dir: str,
    query: str,
    k: int = TOP_K_DEFAULT,
    file_glob: str | None = None,
) -> list[dict]:
    """Hybrid semantic + BM25 search with RRF fusion.

    Args:
        project_dir: Path to the project root.
        query: Natural language or identifier query.
        k: Number of results to return.
        file_glob: Optional glob to restrict results (e.g. '**/routers/*.py').
    """
    chunks_path, emb_path, _, _ = _store_paths(project_dir)

    if not chunks_path.exists() or not emb_path.exists():
        logger.warning("RAG index not built for %s", project_dir)
        return []

    from ai_team.rag.hybrid_search import hybrid_search

    return hybrid_search(project_dir, query, k=k, file_glob=file_glob)


def index_exists(project_dir: str) -> bool:
    chunks_path, emb_path, meta_path, _ = _store_paths(project_dir)
    return chunks_path.exists() and emb_path.exists() and meta_path.exists()


def index_stats(project_dir: str) -> dict:
    """Return stats about the current index."""
    chunks_path, emb_path, meta_path, mtime_path = _store_paths(project_dir)
    if not index_exists(project_dir):
        return {"exists": False}
    try:
        meta = json.loads(meta_path.read_text())
        emb = np.load(str(emb_path))
        return {
            "exists": True,
            "chunk_count": meta.get("chunk_count", 0),
            "embedding_model": meta.get("embedding_model", "unknown"),
            "built_at": meta.get("built_at", "unknown"),
            "embedding_shape": list(emb.shape),
            "store_size_mb": round(
                (chunks_path.stat().st_size + emb_path.stat().st_size) / 1e6, 2
            ),
        }
    except Exception as e:
        return {"exists": True, "error": str(e)}
