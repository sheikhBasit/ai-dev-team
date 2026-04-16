"""Shell tools for agents to interact with the filesystem and run commands."""

from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger("ai_team.tools")

# ── Path sandboxing ──────────────────────────────────────────────────────────

# Set at runtime by the graph before agents start
_allowed_project_dir: Path | None = None


def set_project_sandbox(project_dir: str) -> None:
    """Set the project directory that agents are allowed to access."""
    global _allowed_project_dir
    _allowed_project_dir = Path(project_dir).expanduser().resolve()


def _validate_path(file_path: str) -> Path:
    """Resolve and validate a file path is within the project sandbox."""
    path = Path(file_path).expanduser().resolve()
    if _allowed_project_dir and not (
        path == _allowed_project_dir
        or path.is_relative_to(_allowed_project_dir)
    ):
        raise PermissionError(
            f"Access denied: {file_path} is outside project directory {_allowed_project_dir}"
        )
    return path


# ── Credential scrubbing ─────────────────────────────────────────────────────

_SECRET_PATTERNS = re.compile(
    r"(sk-ant-[a-zA-Z0-9\-]+|sk-[a-zA-Z0-9]{20,}|gsk_[a-zA-Z0-9]+|"
    r"hf_[a-zA-Z0-9]+|ghp_[a-zA-Z0-9]+|"
    r"password\s*[=:]\s*\S+|"
    r"secret\s*[=:]\s*\S+|"
    r"token\s*[=:]\s*\S+|"
    r"PRIVATE KEY-----[^-]+-----)",
    re.IGNORECASE,
)


def _scrub_secrets(text: str) -> str:
    """Remove API keys, passwords, and tokens from output."""
    return _SECRET_PATTERNS.sub("[REDACTED]", text)


# ── Command allowlist ────────────────────────────────────────────────────────

ALLOWED_COMMANDS = {
    # Testing
    "pytest", "python", "python3",
    # Linting / formatting
    "ruff", "pyright", "mypy", "black", "isort", "flake8",
    # Git (read operations + commit)
    "git",
    # Package management (read only)
    "pip", "pip3", "npm", "node",
    # Build / run
    "alembic", "uvicorn", "celery", "task",
    # File inspection (safe)
    "ls", "find", "wc", "head", "tail", "cat", "tree", "file", "stat",
    "diff", "sort", "uniq", "grep", "rg",
    # Docker (inspect only)
    "docker",
}

BLOCKED_SUBCOMMANDS = {
    # Dangerous git operations
    ("git", "push", "--force"),
    ("git", "reset", "--hard"),
    ("git", "clean", "-f"),
    # Dangerous docker operations
    ("docker", "rm"),
    ("docker", "rmi"),
    ("docker", "system", "prune"),
}

BLOCKED_PATTERNS = re.compile(
    r"(rm\s+-rf|rm\s+-r|rmdir|mkfs|dd\s+if=|shutdown|reboot|"
    r"chmod\s+777|chown|sudo|su\s+|"
    r"curl.*\|\s*sh|wget.*\|\s*sh|"
    r">\s*/etc/|>\s*/dev/|"
    r"eval\s*\(|exec\s*\(|"
    r"\bkill\b|\bkillall\b)",
    re.IGNORECASE,
)


def _validate_command(command: str) -> str | None:
    """Validate a command against the allowlist. Returns error message or None if OK."""
    stripped = command.strip()
    if not stripped:
        return "Empty command"

    # Check for blocked patterns first
    if BLOCKED_PATTERNS.search(stripped):
        return f"BLOCKED: Command matches a dangerous pattern: {stripped[:80]}"

    # Extract the base command (handle pipes, chains)
    # For piped commands, validate each segment
    segments = re.split(r"\s*[|;&]+\s*", stripped)
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        # Skip env var assignments like FOO=bar
        if re.match(r"^[A-Z_]+=", segment):
            continue
        # Get the base command name
        parts = shlex.split(segment)
        if not parts:
            continue
        base_cmd = Path(parts[0]).name  # handle /usr/bin/python -> python
        if base_cmd not in ALLOWED_COMMANDS:
            return (
                f"BLOCKED: '{base_cmd}' is not in the allowed commands list. "
                f"Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"
            )

    # Check for blocked subcommand combinations
    try:
        parts = shlex.split(stripped)
    except ValueError:
        parts = stripped.split()

    for blocked in BLOCKED_SUBCOMMANDS:
        if all(b in parts for b in blocked):
            return f"BLOCKED: Dangerous subcommand combination: {' '.join(blocked)}"

    return None


# ── File tools ───────────────────────────────────────────────────────────────

MAX_FILE_READ_SIZE = 2 * 1024 * 1024  # 2MB


@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file. Returns the file content with line numbers."""
    try:
        path = _validate_path(file_path)
    except PermissionError as e:
        return f"ERROR: {e}"

    if not path.exists():
        return f"ERROR: File not found: {file_path}"
    if not path.is_file():
        return f"ERROR: Not a file: {file_path}"
    if path.stat().st_size > MAX_FILE_READ_SIZE:
        return f"ERROR: File too large ({path.stat().st_size} bytes). Max: {MAX_FILE_READ_SIZE} bytes."
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        numbered = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)
    except Exception as e:
        return f"ERROR reading {file_path}: {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed. Must be within project directory."""
    try:
        path = _validate_path(file_path)
    except PermissionError as e:
        return f"ERROR: {e}"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("Wrote %d bytes to %s", len(content), file_path)
        return f"OK: Written {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"ERROR writing {file_path}: {e}"


@tool
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """Replace old_string with new_string in a file. old_string must be unique in the file."""
    try:
        path = _validate_path(file_path)
    except PermissionError as e:
        return f"ERROR: {e}"

    if not path.exists():
        return f"ERROR: File not found: {file_path}"
    try:
        content = path.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return f"ERROR: old_string not found in {file_path}"
        if count > 1:
            return (
                f"ERROR: old_string found {count} times in {file_path}, "
                f"must be unique. Provide more context."
            )
        new_content = content.replace(old_string, new_string, 1)
        path.write_text(new_content, encoding="utf-8")
        logger.info("Edited %s", file_path)
        return f"OK: Replaced in {file_path}"
    except Exception as e:
        return f"ERROR editing {file_path}: {e}"


@tool
def list_directory(dir_path: str) -> str:
    """List files and directories at the given path."""
    try:
        path = _validate_path(dir_path)
    except PermissionError as e:
        return f"ERROR: {e}"

    if not path.exists():
        return f"ERROR: Directory not found: {dir_path}"
    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        result = []
        for entry in entries:
            prefix = "d " if entry.is_dir() else "f "
            size = entry.stat().st_size if entry.is_file() else ""
            result.append(f"{prefix}{entry.name}  {size}")
        return "\n".join(result) if result else "(empty directory)"
    except Exception as e:
        return f"ERROR listing {dir_path}: {e}"


@tool
def search_files(directory: str, pattern: str, file_glob: str = "**/*") -> str:
    """Search for a regex pattern in files matching file_glob under directory.
    Returns matching lines with file paths and line numbers.
    """
    try:
        path = _validate_path(directory)
    except PermissionError as e:
        return f"ERROR: {e}"

    if not path.exists():
        return f"ERROR: Directory not found: {directory}"
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"ERROR: Invalid regex: {e}"

    results = []
    match_count = 0
    for file_path in path.glob(file_glob):
        if not file_path.is_file():
            continue
        if any(part.startswith(".") for part in file_path.parts):
            continue
        if file_path.suffix in (".pyc", ".pyo", ".so", ".o", ".a"):
            continue
        # Skip large files
        if file_path.stat().st_size > MAX_FILE_READ_SIZE:
            continue
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, 1):
                if regex.search(line):
                    results.append(f"{file_path}:{i}: {line.strip()}")
                    match_count += 1
                    if match_count >= 50:
                        results.append("... (truncated at 50 matches)")
                        return "\n".join(results)
        except Exception:
            continue
    return "\n".join(results) if results else f"No matches for '{pattern}' in {directory}"


# ── Shell command tool ───────────────────────────────────────────────────────

COMMAND_TIMEOUT = 180  # seconds


@tool
def run_command(command: str, working_dir: str = ".") -> str:
    """Run a safe shell command and return stdout + stderr.
    Only allowed commands: pytest, ruff, git, python, pip, alembic, docker, ls, grep, etc.
    Destructive commands (rm, sudo, kill, etc.) are blocked.
    """
    # Validate against allowlist
    error = _validate_command(command)
    if error:
        return f"ERROR: {error}"

    resolved_dir = os.path.expanduser(working_dir)
    if _allowed_project_dir and not Path(resolved_dir).resolve().is_relative_to(
        _allowed_project_dir
    ):
        return f"ERROR: working_dir must be within project directory: {_allowed_project_dir}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=resolved_dir,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        output += f"\n[EXIT CODE: {result.returncode}]"

        # Scrub secrets from output
        output = _scrub_secrets(output)

        # Truncate very long output
        if len(output) > 10000:
            output = output[:5000] + "\n...(truncated)...\n" + output[-3000:]
        return output
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out after {COMMAND_TIMEOUT} seconds"
    except Exception as e:
        return f"ERROR running command: {_scrub_secrets(str(e))}"


from ai_team.tools.rag_tools import rag_index_status, reindex_codebase, search_codebase  # noqa: E402

ALL_TOOLS = [
    read_file, write_file, edit_file, list_directory, search_files, run_command,
    search_codebase, reindex_codebase, rag_index_status,
]
