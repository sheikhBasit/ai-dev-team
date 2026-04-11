"""Auto-detect project patterns — language, framework, test setup, code style."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("ai_team.agents.project_detector")


def detect_project_context(project_dir: str) -> str:
    """Scan the project directory and return a context string describing its patterns.

    This replaces hardcoded assumptions about the project structure.
    """
    root = Path(project_dir).expanduser().resolve()
    if not root.exists():
        return f"WARNING: Project directory not found: {project_dir}"

    context_parts = []

    # ── CLAUDE.md (highest priority — project-specific instructions) ─────────
    for claude_md in [root / "CLAUDE.md", root / "claude.md"]:
        if claude_md.exists():
            try:
                content = claude_md.read_text(encoding="utf-8")
                context_parts.append(f"## Project Instructions (CLAUDE.md)\n{content[:3000]}")
            except Exception:
                pass
            break

    # ── Language detection ────────────────────────────────────────────────────
    languages = []
    markers = {
        "Python": ["requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"],
        "JavaScript/TypeScript": ["package.json", "tsconfig.json"],
        "Go": ["go.mod"],
        "Rust": ["Cargo.toml"],
        "Java": ["pom.xml", "build.gradle"],
        "Ruby": ["Gemfile"],
        "PHP": ["composer.json"],
    }
    for lang, files in markers.items():
        for f in files:
            if _find_file(root, f):
                languages.append(lang)
                break

    if languages:
        context_parts.append(f"## Languages: {', '.join(languages)}")

    # ── Framework detection ──────────────────────────────────────────────────
    frameworks = []
    # Python frameworks
    for req_file in root.rglob("requirements.txt"):
        try:
            content = req_file.read_text(encoding="utf-8").lower()
            if "fastapi" in content:
                frameworks.append("FastAPI")
            if "django" in content:
                frameworks.append("Django")
            if "flask" in content:
                frameworks.append("Flask")
            if "livekit" in content:
                frameworks.append("LiveKit")
            if "celery" in content:
                frameworks.append("Celery")
            if "sqlalchemy" in content:
                frameworks.append("SQLAlchemy")
            if "alembic" in content:
                frameworks.append("Alembic")
        except Exception:
            continue

    # JS frameworks
    pkg_json = _find_file(root, "package.json")
    if pkg_json:
        try:
            content = pkg_json.read_text(encoding="utf-8").lower()
            if "next" in content:
                frameworks.append("Next.js")
            if "react" in content:
                frameworks.append("React")
            if "vue" in content:
                frameworks.append("Vue")
            if "express" in content:
                frameworks.append("Express")
        except Exception:
            pass

    if frameworks:
        context_parts.append(f"## Frameworks: {', '.join(set(frameworks))}")

    # ── Code style detection ─────────────────────────────────────────────────
    style_info = []
    pyproject = _find_file(root, "pyproject.toml")
    if pyproject:
        try:
            content = pyproject.read_text(encoding="utf-8")
            if "ruff" in content:
                style_info.append("Linter: ruff")
            if "black" in content:
                style_info.append("Formatter: black")
            if "line-length" in content:
                import re
                match = re.search(r"line-length\s*=\s*(\d+)", content)
                if match:
                    style_info.append(f"Line length: {match.group(1)}")
        except Exception:
            pass

    if style_info:
        context_parts.append(f"## Code Style: {', '.join(style_info)}")

    # ── Test detection ───────────────────────────────────────────────────────
    test_dirs = []
    for name in ["tests", "test", "api/tests", "backend/api/tests", "src/tests", "__tests__"]:
        test_dir = root / name
        if test_dir.is_dir():
            test_dirs.append(str(test_dir.relative_to(root)))

    pytest_ini = _find_file(root, "pytest.ini")
    conftest = None
    for td in test_dirs:
        cf = root / td / "conftest.py"
        if cf.exists():
            conftest = str(cf.relative_to(root))
            break

    test_info = []
    if test_dirs:
        test_info.append(f"Test directories: {', '.join(test_dirs)}")
    if pytest_ini:
        test_info.append(f"pytest.ini: {pytest_ini.relative_to(root)}")
    if conftest:
        test_info.append(f"conftest.py: {conftest}")

    if test_info:
        context_parts.append(f"## Testing\n" + "\n".join(f"- {t}" for t in test_info))

    # ── Project structure ────────────────────────────────────────────────────
    top_level = sorted([
        p.name + ("/" if p.is_dir() else "")
        for p in root.iterdir()
        if not p.name.startswith(".") and p.name not in ("__pycache__", "node_modules", ".venv", "venv")
    ])
    if top_level:
        context_parts.append(f"## Top-level structure\n```\n{chr(10).join(top_level[:30])}\n```")

    # ── Docker / CI ──────────────────────────────────────────────────────────
    infra = []
    if _find_file(root, "docker-compose.yml") or _find_file(root, "docker-compose.yaml"):
        infra.append("Docker Compose")
    if _find_file(root, "Dockerfile"):
        infra.append("Dockerfile")
    if (root / ".github" / "workflows").is_dir():
        infra.append("GitHub Actions CI")
    if _find_file(root, "Taskfile.yml"):
        infra.append("Taskfile (task runner)")

    if infra:
        context_parts.append(f"## Infrastructure: {', '.join(infra)}")

    return "\n\n".join(context_parts) if context_parts else "No project metadata detected."


def _find_file(root: Path, name: str) -> Path | None:
    """Find a file by name in root or one level deep."""
    direct = root / name
    if direct.exists():
        return direct
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            candidate = child / name
            if candidate.exists():
                return candidate
    return None
