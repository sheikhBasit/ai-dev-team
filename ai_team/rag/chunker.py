"""Code chunker — splits source files into semantic chunks for embedding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".php",
    ".md", ".txt", ".yaml", ".yml", ".toml", ".json",
}

SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".next", "coverage", ".eggs",
}

MAX_FILE_SIZE = 200_000  # 200KB
CHUNK_SIZE = 60          # lines per chunk
CHUNK_OVERLAP = 10       # lines of overlap between chunks


@dataclass
class CodeChunk:
    content: str
    file_path: str   # relative to project root
    start_line: int
    end_line: int
    chunk_id: str    # unique: "rel/path.py:10-70"

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_id": self.chunk_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CodeChunk":
        return cls(
            content=d["content"],
            file_path=d["file_path"],
            start_line=d["start_line"],
            end_line=d["end_line"],
            chunk_id=d["chunk_id"],
        )


def _walk_files(root: Path):
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        if entry.is_dir():
            yield from _walk_files(entry)
        elif entry.is_file() and entry.suffix in INDEXABLE_EXTENSIONS:
            yield entry


def _split_python_by_symbol(lines: list[str]) -> list[tuple[int, int]]:
    """Split Python file at class/function boundaries. Returns (start, end) pairs (0-indexed)."""
    boundaries = [0]
    for i, line in enumerate(lines):
        if re.match(r"^(class |def |async def )", line):
            if i > 0 and i not in boundaries:
                boundaries.append(i)
    boundaries.append(len(lines))

    segments = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        # merge tiny segments with next
        if end - start < 5 and i < len(boundaries) - 2:
            continue
        segments.append((start, end))
    return segments if segments else [(0, len(lines))]


def chunk_file(file_path: Path, rel_path: str) -> list[CodeChunk]:
    """Chunk a single file into overlapping segments."""
    if file_path.stat().st_size > MAX_FILE_SIZE:
        return []

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lines = content.splitlines()
    if not lines:
        return []

    chunks = []

    if file_path.suffix == ".py":
        segments = _split_python_by_symbol(lines)
        for start, end in segments:
            # If segment is large, further split with overlap
            if end - start > CHUNK_SIZE * 2:
                for s in range(start, end, CHUNK_SIZE - CHUNK_OVERLAP):
                    e = min(s + CHUNK_SIZE, end)
                    chunk_lines = lines[s:e]
                    chunk_id = f"{rel_path}:{s+1}-{e}"
                    chunks.append(CodeChunk(
                        content="\n".join(chunk_lines),
                        file_path=rel_path,
                        start_line=s + 1,
                        end_line=e,
                        chunk_id=chunk_id,
                    ))
            else:
                chunk_lines = lines[start:end]
                chunk_id = f"{rel_path}:{start+1}-{end}"
                chunks.append(CodeChunk(
                    content="\n".join(chunk_lines),
                    file_path=rel_path,
                    start_line=start + 1,
                    end_line=end,
                    chunk_id=chunk_id,
                ))
    else:
        # Sliding window for non-Python files
        for start in range(0, len(lines), CHUNK_SIZE - CHUNK_OVERLAP):
            end = min(start + CHUNK_SIZE, len(lines))
            chunk_lines = lines[start:end]
            chunk_id = f"{rel_path}:{start+1}-{end}"
            chunks.append(CodeChunk(
                content="\n".join(chunk_lines),
                file_path=rel_path,
                start_line=start + 1,
                end_line=end,
                chunk_id=chunk_id,
            ))
            if end == len(lines):
                break

    return chunks


def chunk_project(project_dir: str) -> list[CodeChunk]:
    """Chunk all indexable files in the project. Returns list of CodeChunk."""
    root = Path(project_dir).expanduser().resolve()
    if not root.exists():
        return []

    all_chunks: list[CodeChunk] = []
    for file_path in _walk_files(root):
        rel_path = str(file_path.relative_to(root))
        file_chunks = chunk_file(file_path, rel_path)
        all_chunks.extend(file_chunks)

    return all_chunks
