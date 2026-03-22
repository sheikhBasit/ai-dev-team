"""Shell tools for agents to interact with the filesystem and run commands."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from langchain_core.tools import tool


@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file. Returns the file content with line numbers."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return f"ERROR: File not found: {file_path}"
    if not path.is_file():
        return f"ERROR: Not a file: {file_path}"
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        numbered = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)
    except Exception as e:
        return f"ERROR reading {file_path}: {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed."""
    path = Path(file_path).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"OK: Written {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"ERROR writing {file_path}: {e}"


@tool
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """Replace old_string with new_string in a file. old_string must be unique in the file."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return f"ERROR: File not found: {file_path}"
    try:
        content = path.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return f"ERROR: old_string not found in {file_path}"
        if count > 1:
            return f"ERROR: old_string found {count} times in {file_path}, must be unique. Provide more context."
        new_content = content.replace(old_string, new_string, 1)
        path.write_text(new_content, encoding="utf-8")
        return f"OK: Replaced in {file_path}"
    except Exception as e:
        return f"ERROR editing {file_path}: {e}"


@tool
def list_directory(dir_path: str) -> str:
    """List files and directories at the given path."""
    path = Path(dir_path).expanduser()
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
    import re

    path = Path(directory).expanduser()
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


@tool
def run_command(command: str, working_dir: str = ".") -> str:
    """Run a shell command and return stdout + stderr. Use for: pytest, ruff, git, etc.
    WARNING: Commands run with real permissions. Do not run destructive commands.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=os.path.expanduser(working_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        output += f"\n[EXIT CODE: {result.returncode}]"
        # Truncate very long output
        if len(output) > 10000:
            output = output[:5000] + "\n...(truncated)...\n" + output[-3000:]
        return output
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 120 seconds"
    except Exception as e:
        return f"ERROR running command: {e}"


ALL_TOOLS = [read_file, write_file, edit_file, list_directory, search_files, run_command]
