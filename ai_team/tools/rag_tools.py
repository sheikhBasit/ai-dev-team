"""RAG tools — semantic + keyword codebase search for agents."""

from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger("ai_team.tools.rag")

_project_dir: str = ""


def set_rag_project(project_dir: str) -> None:
    global _project_dir
    _project_dir = project_dir


@tool
def search_codebase(query: str, k: int = 8, file_glob: str = "") -> str:
    """Semantically + keyword search the codebase for relevant code.

    Combines vector similarity with BM25 keyword search (RRF fusion) so it finds
    both conceptual matches ("how is auth handled") and exact identifiers ("UserService").

    Args:
        query: Natural language or identifier to search for.
        k: Number of results (default 8, max 20).
        file_glob: Optional glob to restrict search, e.g. '**/routers/*.py' or 'backend/**'.
    """
    if not _project_dir:
        return "ERROR: RAG not initialized. No project directory set."

    from ai_team.rag.store import index_exists, search

    if not index_exists(_project_dir):
        return (
            "RAG index not available. Use reindex_codebase to build it, "
            "or fall back to search_files for regex search."
        )

    k = min(k, 20)
    results = search(_project_dir, query, k=k, file_glob=file_glob or None)

    if not results:
        return f"No results found for: {query!r}"

    lines = [f"## Codebase search: {query!r}\n"]
    for i, r in enumerate(results, 1):
        match_badge = {"hybrid": "[H]", "semantic": "[S]", "keyword": "[K]"}.get(
            r.get("match_type", ""), ""
        )
        lines.append(
            f"### [{i}] {match_badge} {r['file_path']} "
            f"lines {r['start_line']}-{r['end_line']}"
        )
        lines.append("```")
        lines.append(r["content"])
        lines.append("```\n")

    lines.append("Legend: [H]=hybrid match  [S]=semantic only  [K]=keyword only")
    return "\n".join(lines)


@tool
def reindex_codebase() -> str:
    """Refresh the semantic search index after writing new files.

    Only re-embeds files that changed — fast for small edits.
    Call this after creating or editing source files so search_codebase finds new code.
    """
    if not _project_dir:
        return "ERROR: RAG not initialized."

    from ai_team.rag.store import build_index, index_stats

    try:
        built = build_index(_project_dir)
        stats = index_stats(_project_dir)
        if built:
            return (
                f"RAG index refreshed: {stats.get('chunk_count')} chunks, "
                f"{stats.get('store_size_mb')}MB, model={stats.get('embedding_model')}"
            )
        return f"RAG index already up-to-date ({stats.get('chunk_count')} chunks)."
    except Exception as e:
        return f"ERROR refreshing RAG index: {e}"


@tool
def rag_index_status() -> str:
    """Show the current status of the semantic search index."""
    if not _project_dir:
        return "ERROR: RAG not initialized."

    from ai_team.rag.store import index_stats

    stats = index_stats(_project_dir)
    if not stats.get("exists"):
        return "RAG index: not built yet. Run reindex_codebase to build it."

    return (
        f"RAG index: {stats.get('chunk_count')} chunks | "
        f"model={stats.get('embedding_model')} | "
        f"built={stats.get('built_at')} | "
        f"size={stats.get('store_size_mb')}MB | "
        f"shape={stats.get('embedding_shape')}"
    )
