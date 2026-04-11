"""Session memory — persists lessons learned between runs."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("ai_team.memory")

MEMORY_DIR = os.path.expanduser("~/.ai-dev-team/memory")


def _ensure_dir():
    os.makedirs(MEMORY_DIR, exist_ok=True)


def _memory_file(project_dir: str) -> Path:
    """Get memory file path for a specific project."""
    # Use a hash of project dir to avoid path issues
    slug = project_dir.replace("/", "_").replace("\\", "_").strip("_")
    return Path(MEMORY_DIR) / f"{slug}.json"


def load_lessons(project_dir: str) -> list[dict]:
    """Load lessons learned for a project."""
    _ensure_dir()
    path = _memory_file(project_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("lessons", [])
    except Exception as e:
        logger.warning("Failed to load memory: %s", e)
        return []


def save_lesson(project_dir: str, lesson: str, category: str = "general") -> None:
    """Save a lesson learned for a project."""
    _ensure_dir()
    path = _memory_file(project_dir)
    data = {"lessons": [], "updated": ""}

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    lessons = data.get("lessons", [])

    # Don't duplicate
    for existing in lessons:
        if existing.get("text", "").strip() == lesson.strip():
            return

    lessons.append({
        "text": lesson,
        "category": category,
        "timestamp": datetime.now().isoformat(),
    })

    # Keep only most recent 50 lessons
    if len(lessons) > 50:
        lessons = lessons[-50:]

    data["lessons"] = lessons
    data["updated"] = datetime.now().isoformat()

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Saved lesson: %s", lesson[:80])


def format_lessons_for_prompt(project_dir: str) -> str:
    """Format lessons as context for agent prompts."""
    lessons = load_lessons(project_dir)
    if not lessons:
        return ""

    lines = ["## Lessons from Previous Sessions"]
    for lesson in lessons[-20:]:  # Only include recent ones
        cat = lesson.get("category", "general")
        text = lesson.get("text", "")
        lines.append(f"- [{cat}] {text}")

    return "\n".join(lines)


def extract_lessons_from_evaluation(evaluation: str, findings: list[dict]) -> list[str]:
    """Extract lessons from an evaluation round for future reference."""
    lessons = []

    critical_findings = [f for f in findings if f.get("severity") == "critical"]
    if critical_findings:
        for f in critical_findings[:3]:
            msg = f.get("message", "")
            if msg:
                lessons.append(f"Critical issue found: {msg}")

    # Extract patterns from evaluation text
    eval_lower = evaluation.lower()
    if "n+1" in eval_lower:
        lessons.append("Watch for N+1 query patterns in this project.")
    if "missing auth" in eval_lower:
        lessons.append("Ensure all new endpoints have auth decorators.")
    if "missing test" in eval_lower or "no test" in eval_lower:
        lessons.append("Tests were missing — always write tests for new code.")
    if "injection" in eval_lower:
        lessons.append("SQL/command injection risk found — validate all user inputs.")

    return lessons
