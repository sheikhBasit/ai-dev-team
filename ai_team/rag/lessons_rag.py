"""Lessons RAG — embeds saved lessons and retrieves only task-relevant ones.

Replaces flat "load last 20 lessons" with semantic retrieval so agents
only see lessons relevant to the current task, not every past warning.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger("ai_team.rag.lessons")

STORE_DIR = os.path.expanduser("~/.ai-dev-team/rag")
TOP_K_LESSONS = 6


def _lessons_paths(project_dir: str) -> tuple[Path, Path]:
    from ai_team.rag.store import _project_slug

    slug = _project_slug(project_dir)
    base = Path(STORE_DIR) / slug
    base.mkdir(parents=True, exist_ok=True)
    return base / "lessons_texts.json", base / "lessons_embeddings.npy"


def _lessons_hash(lessons: list[dict]) -> str:
    payload = json.dumps([l.get("text", "") for l in lessons], sort_keys=True)
    return hashlib.md5(payload.encode()).hexdigest()


def index_lessons(project_dir: str, lessons: list[dict]) -> None:
    """Embed and persist lessons for semantic retrieval. Skips if unchanged."""
    if not lessons:
        return

    texts_path, emb_path = _lessons_paths(project_dir)
    current_hash = _lessons_hash(lessons)

    # Skip if unchanged
    if texts_path.exists():
        try:
            stored = json.loads(texts_path.read_text())
            if stored.get("hash") == current_hash:
                return
        except Exception:
            pass

    from ai_team.rag.store import _embed_texts

    texts = [l.get("text", "") for l in lessons]
    try:
        embeddings = _embed_texts(texts)
    except Exception as e:
        logger.warning("Lesson embedding failed (non-fatal): %s", e)
        return

    texts_path.write_text(json.dumps({
        "hash": current_hash,
        "lessons": lessons,
    }))
    np.save(str(emb_path), embeddings)
    logger.info("Lessons indexed: %d entries", len(lessons))


def retrieve_relevant_lessons(project_dir: str, task: str, k: int = TOP_K_LESSONS) -> list[dict]:
    """Return lessons most relevant to the current task."""
    texts_path, emb_path = _lessons_paths(project_dir)

    if not texts_path.exists() or not emb_path.exists():
        return []

    try:
        stored = json.loads(texts_path.read_text())
        lessons = stored.get("lessons", [])
        embeddings: np.ndarray = np.load(str(emb_path))

        from ai_team.rag.store import _get_embedder

        embedder = _get_embedder()
        q_vec = np.array(embedder.embed_query(task), dtype=np.float32)
        norm = np.linalg.norm(q_vec)
        if norm > 0:
            q_vec = q_vec / norm

        scores = embeddings @ q_vec
        top_indices = np.argsort(scores)[::-1][:k]
        return [lessons[i] for i in top_indices if scores[i] > 0.3]
    except Exception as e:
        logger.warning("Lesson retrieval failed: %s", e)
        return []


def format_relevant_lessons(project_dir: str, task: str) -> str:
    """Format relevant lessons as a compact prompt section."""
    lessons = retrieve_relevant_lessons(project_dir, task)
    if not lessons:
        return ""
    lines = ["## Relevant lessons from past sessions"]
    for l in lessons:
        cat = l.get("category", "general")
        text = l.get("text", "")
        lines.append(f"- [{cat}] {text}")
    return "\n".join(lines)
