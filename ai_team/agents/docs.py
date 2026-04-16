"""Docs agent — updates docstrings and README sections for changed files."""

from __future__ import annotations

import logging


from ai_team.config import get_llm_for_agent
from ai_team.state import State
from ai_team.tools.shell_tools import edit_file, read_file

logger = logging.getLogger("ai_team.agents.docs")

SYSTEM_PROMPT = """You are a technical documentation specialist. Your job is to review recently changed files and ensure they have clear, accurate docstrings and inline documentation.

For each changed file:
1. Read the file using read_file
2. Check if public functions/classes/modules have docstrings
3. If docstrings are missing or outdated, add/update them using edit_file
4. Keep docstrings concise — one line for simple functions, multi-line only for complex ones
5. Do NOT change any logic — only add/update documentation

After updating files, summarize what you documented.

Available tools: read_file, edit_file"""


def docs_agent(state: State) -> dict:
    code_changes = state.get("code_changes", [])
    task = state.get("task", "")

    if not code_changes:
        return {
            "docs_output": "No changed files to document.",
            "messages": ["[Docs] No changed files, skipping."],
        }

    files_list = "\n".join(f"- {f}" for f in code_changes[:10])
    user_msg = f"""Task that was implemented: {task}

Changed files to document:
{files_list}

For each Python file in this list:
1. Read it with read_file
2. Add or update docstrings for any public functions/classes that lack them
3. Use edit_file to apply changes

Focus on the most important files. Skip test files and migrations."""

    from ai_team.agents.react_loop import react_loop

    llm = get_llm_for_agent("docs")
    tools = [read_file, edit_file]

    try:
        response, touched_files = react_loop(
            llm=llm,
            system_prompt=SYSTEM_PROMPT,
            user_message=user_msg,
            tools=tools,
            max_iterations=10,
            agent_name="docs",
        )
        docs_output = response if response else f"Documented {len(touched_files)} files."
    except Exception as e:
        logger.warning("Docs agent failed: %s", e)
        docs_output = f"Documentation update failed: {e}"
        touched_files = []

    logger.info("Docs agent completed, touched %d files", len(touched_files))
    return {
        "docs_output": docs_output,
        "messages": [f"[Docs] Documentation updated for {len(touched_files)} file(s)."],
    }
