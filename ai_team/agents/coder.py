"""Coder Agent — Writes the actual code based on architecture spec."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

from ai_team.config import get_llm
from ai_team.tools.shell_tools import ALL_TOOLS


SYSTEM_PROMPT = """You are a Senior Software Engineer. You write clean, production-ready code.

Rules:
- Follow existing code patterns exactly (read existing files first!)
- Python 3.11+, double quotes, line length 88
- Use type hints
- No over-engineering — minimal changes to achieve the goal
- Create files only when necessary, prefer editing existing ones
- Write code that passes ruff and pyright
- Every endpoint needs auth (PermissionsValidator pattern)
- Every DB model needs an Alembic migration
- Match the project's import style and structure

You have tools to:
- read_file: Read existing code to understand patterns
- write_file: Create new files
- edit_file: Modify existing files (preferred over write_file)
- search_files: Find code patterns in the codebase
- list_directory: Explore project structure
- run_command: Run linters, formatters, etc.

After writing code, always run:
1. ruff check <files> --fix
2. ruff format <files>

Report every file you created or modified."""


def coder_agent(state: dict) -> dict:
    """Write code based on the architecture spec."""
    llm = get_llm().bind_tools(ALL_TOOLS)
    architecture = state.get("architecture_spec", "")
    requirements = state.get("requirements_spec", "")
    design = state.get("design_spec", "")
    project_dir = state.get("project_dir", "")
    feedback = state.get("human_feedback", "")

    # If coming from a failed evaluation, include findings
    review = state.get("review_findings", [])
    tests = state.get("test_results", [])
    security = state.get("security_findings", [])

    user_msg = f"""Architecture Spec:
{architecture}

Requirements:
{requirements}

Design:
{design}

Project Directory: {project_dir}

Instructions:
1. Read the existing code to understand patterns
2. Implement the changes described in the architecture spec
3. Run ruff check and ruff format on every file you touch
4. List every file you created or modified"""

    if feedback:
        user_msg += f"\n\nUser feedback:\n{feedback}"

    if review:
        user_msg += "\n\nCode review findings to fix:\n"
        for f in review:
            user_msg += f"- [{f.get('severity', 'info')}] {f.get('message', '')}\n"

    if tests:
        user_msg += "\n\nFailing tests to fix:\n"
        for f in tests:
            user_msg += f"- {f.get('message', '')}\n"

    if security:
        user_msg += "\n\nSecurity issues to fix:\n"
        for f in security:
            user_msg += f"- [{f.get('severity', 'info')}] {f.get('message', '')}\n"

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ]

    changed_files = []

    # ReAct loop — let LLM use tools until done (up to 25 iterations for complex tasks)
    for _ in range(25):
        response = llm.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_map = {t.name: t for t in ALL_TOOLS}
            tool_fn = tool_map.get(tool_call["name"])
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )
                # Track file changes
                if tool_call["name"] in ("write_file", "edit_file"):
                    fpath = tool_call["args"].get("file_path", "")
                    if fpath and fpath not in changed_files:
                        changed_files.append(fpath)

    return {
        "code_changes": changed_files,
        "phase": "review",
        "messages": [f"[Coder] Modified {len(changed_files)} files: {', '.join(changed_files)}"],
        # Clear previous findings for fresh evaluation
        "review_findings": [],
        "test_results": [],
        "security_findings": [],
    }
