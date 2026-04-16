"""Self-healing import node — detects missing packages and auto-installs them."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

from ai_team.state import State

logger = logging.getLogger("ai_team.agents.import_healer")

# Only allow installing packages on this allowlist — never arbitrary user input
INSTALLABLE_PACKAGES = frozenset({
    "requests", "httpx", "aiohttp", "fastapi", "uvicorn", "pydantic",
    "sqlalchemy", "alembic", "psycopg2-binary", "pymongo", "redis",
    "celery", "boto3", "google-cloud-storage", "stripe", "twilio",
    "pillow", "numpy", "pandas", "scipy", "matplotlib", "seaborn",
    "pytest", "pytest-asyncio", "pytest-cov", "faker", "factory-boy",
    "python-jose", "passlib", "bcrypt", "cryptography",
    "python-multipart", "python-dotenv", "pyyaml", "toml",
    "rich", "click", "typer", "tabulate",
    "langchain", "langchain-core", "langchain-anthropic", "langchain-openai",
    "openai", "anthropic", "tiktoken",
    "black", "ruff", "mypy", "isort",
})

# Two patterns to extract package names from ImportError messages:
# 1. "No module named 'pkg'" — the canonical Python form
# 2. "ImportError: pkg" — direct form (when not followed by "No module named")
_IMPORT_ERROR_RE = re.compile(
    r"No module named ['\"]?([a-zA-Z0-9_\-\.]+)['\"]?"
    r"|(?:ModuleNotFoundError|ImportError):\s+(?!No\s)([a-zA-Z0-9_\-\.]+)",
    re.IGNORECASE,
)


def _extract_missing_packages(messages: list[str]) -> list[str]:
    """Scan coder messages for ImportError patterns and return package names."""
    found = []
    for msg in messages:
        for match in _IMPORT_ERROR_RE.finditer(msg):
            # group(1) = "No module named" capture; group(2) = direct ImportError capture
            raw = match.group(1) or match.group(2)
            if not raw:
                continue
            pkg = raw.replace("_", "-").lower()
            # Map common module names to pip package names
            pkg = {"PIL": "pillow", "cv2": "opencv-python", "sklearn": "scikit-learn"}.get(pkg, pkg)
            if pkg in INSTALLABLE_PACKAGES and pkg not in found:
                found.append(pkg)
    return found


def import_healer_node(state: State) -> dict:
    """Detect missing imports in coder output and auto-install them."""
    messages = state.get("messages", [])
    # Only scan the most recent messages (last 10 — from this coder iteration)
    recent = messages[-10:] if len(messages) > 10 else messages

    missing = _extract_missing_packages(recent)

    if not missing:
        return {"messages": ["[ImportHealer] No missing imports detected."]}

    installed = []
    failed = []
    pip = str(Path(sys.executable).parent / "pip")

    for pkg in missing:
        try:
            result = subprocess.run(
                [pip, "install", pkg],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                logger.info("Auto-installed: %s", pkg)
                installed.append(pkg)
            else:
                logger.warning("Failed to install %s: %s", pkg, result.stderr[:200])
                failed.append(pkg)
        except Exception as e:
            logger.warning("Install error for %s: %s", pkg, e)
            failed.append(pkg)

    parts = []
    if installed:
        parts.append(f"installed: {', '.join(installed)}")
    if failed:
        parts.append(f"failed: {', '.join(failed)}")

    summary = f"[ImportHealer] {'; '.join(parts)}" if parts else "[ImportHealer] No packages needed."
    return {"messages": [summary]}
