"""Codebase indexer — builds a lightweight map of classes, functions, endpoints, models."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger("ai_team.agents.indexer")

# File extensions to index
INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".php",
}

# Skip these directories
SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "egg-info", ".next", "coverage",
}

MAX_INDEX_FILES = 500
MAX_FILE_SIZE = 500_000  # 500KB


def build_codebase_index(project_dir: str) -> str:
    """Build a lightweight index of the codebase.

    Returns a structured string with:
    - File tree
    - Classes and their methods
    - Top-level functions
    - API endpoints (FastAPI/Flask/Express patterns)
    - Database models (SQLAlchemy/Django/Prisma)
    - Test files and test classes
    """
    root = Path(project_dir).expanduser().resolve()
    if not root.exists():
        return "Project directory not found."

    sections = []
    classes = []
    functions = []
    endpoints = []
    models = []
    test_files = []
    file_count = 0

    for file_path in _walk_files(root):
        if file_count >= MAX_INDEX_FILES:
            sections.append(f"(truncated at {MAX_INDEX_FILES} files)")
            break
        file_count += 1

        rel_path = str(file_path.relative_to(root))
        suffix = file_path.suffix

        # Track test files
        if "test" in rel_path.lower():
            test_files.append(rel_path)

        if suffix not in INDEXABLE_EXTENSIONS:
            continue

        if file_path.stat().st_size > MAX_FILE_SIZE:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines = content.splitlines()

        if suffix == ".py":
            _index_python(rel_path, lines, classes, functions, endpoints, models)
        elif suffix in (".js", ".ts", ".tsx", ".jsx"):
            _index_javascript(rel_path, lines, classes, functions, endpoints)
        elif suffix == ".go":
            _index_go(rel_path, lines, functions, endpoints)

    # Build the index string
    parts = []

    if endpoints:
        parts.append("## API Endpoints")
        for ep in endpoints[:50]:
            parts.append(f"  {ep}")

    if models:
        parts.append("\n## Database Models")
        for m in models[:30]:
            parts.append(f"  {m}")

    if classes:
        parts.append("\n## Classes")
        for c in classes[:50]:
            parts.append(f"  {c}")

    if functions:
        parts.append("\n## Key Functions")
        for f in functions[:50]:
            parts.append(f"  {f}")

    if test_files:
        parts.append(f"\n## Test Files ({len(test_files)})")
        for t in test_files[:20]:
            parts.append(f"  {t}")

    parts.append(f"\n## Stats: {file_count} files indexed")

    return "\n".join(parts) if parts else "Empty project."


def _walk_files(root: Path):
    """Walk files, skipping unneeded directories."""
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        if entry.is_dir():
            yield from _walk_files(entry)
        elif entry.is_file():
            yield entry


def _index_python(
    rel_path: str,
    lines: list[str],
    classes: list,
    functions: list,
    endpoints: list,
    models: list,
):
    """Index Python file for classes, functions, endpoints, models."""
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Classes
        match = re.match(r"^class\s+(\w+)", stripped)
        if match:
            # Check if it's a DB model
            if any(base in stripped for base in ("Base", "Model", "SQLModel", "DeclarativeBase")):
                models.append(f"{rel_path}:{i} — class {match.group(1)} (model)")
            else:
                classes.append(f"{rel_path}:{i} — class {match.group(1)}")

        # Top-level functions (not methods — no leading whitespace)
        if not line.startswith(" ") and not line.startswith("\t"):
            match = re.match(r"^(?:async\s+)?def\s+(\w+)", stripped)
            if match and not match.group(1).startswith("_"):
                functions.append(f"{rel_path}:{i} — {match.group(1)}()")

        # FastAPI endpoints
        for decorator in ("@app.", "@router."):
            if decorator in stripped:
                method_match = re.search(r"\.(get|post|put|delete|patch)\s*\(\s*[\"']([^\"']+)", stripped)
                if method_match:
                    method = method_match.group(1).upper()
                    path = method_match.group(2)
                    endpoints.append(f"{method} {path} — {rel_path}:{i}")

        # Flask endpoints
        if "@app.route" in stripped or "@bp.route" in stripped:
            route_match = re.search(r"route\s*\(\s*[\"']([^\"']+)", stripped)
            if route_match:
                endpoints.append(f"ROUTE {route_match.group(1)} — {rel_path}:{i}")

        # SQLAlchemy table names
        if "__tablename__" in stripped:
            table_match = re.search(r"__tablename__\s*=\s*[\"'](\w+)", stripped)
            if table_match:
                models.append(f"{rel_path}:{i} — table: {table_match.group(1)}")


def _index_javascript(
    rel_path: str,
    lines: list[str],
    classes: list,
    functions: list,
    endpoints: list,
):
    """Index JS/TS file."""
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Classes
        match = re.match(r"^(?:export\s+)?class\s+(\w+)", stripped)
        if match:
            classes.append(f"{rel_path}:{i} — class {match.group(1)}")

        # Exported functions
        match = re.match(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", stripped)
        if match:
            functions.append(f"{rel_path}:{i} — {match.group(1)}()")

        # Express/Next.js endpoints
        for method in ("get", "post", "put", "delete", "patch"):
            if f".{method}(" in stripped or f"router.{method}(" in stripped:
                route_match = re.search(rf"\.{method}\s*\(\s*[\"'`]([^\"'`]+)", stripped)
                if route_match:
                    endpoints.append(f"{method.upper()} {route_match.group(1)} — {rel_path}:{i}")


def _index_go(
    rel_path: str,
    lines: list[str],
    functions: list,
    endpoints: list,
):
    """Index Go file."""
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        match = re.match(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", stripped)
        if match:
            functions.append(f"{rel_path}:{i} — {match.group(1)}()")

        # HTTP handlers
        for method in ("Get", "Post", "Put", "Delete", "Handle"):
            if f".{method}(" in stripped or f".{method}Func(" in stripped:
                route_match = re.search(rf"\.{method}(?:Func)?\s*\(\s*[\"']([^\"']+)", stripped)
                if route_match:
                    endpoints.append(f"{method.upper()} {route_match.group(1)} — {rel_path}:{i}")
