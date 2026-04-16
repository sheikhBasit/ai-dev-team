"""Coder Agent — Writes the actual code based on architecture spec."""

from __future__ import annotations

from ai_team.agents.react_loop import react_loop
from ai_team.config import get_llm_for_agent


SYSTEM_PROMPT = """You are a Senior Software Engineer. You write clean, production-ready code.

Rules:
- Read existing files first to understand the project's patterns and style
- Follow the existing code patterns exactly
- No over-engineering — minimal changes to achieve the goal
- Create files only when necessary, prefer editing existing ones
- Write code that passes the project's linters
- Match the project's import style and structure

You have tools to:
- search_codebase: Semantic search — find relevant code by description (use this first)
- read_file: Read existing code to understand patterns
- write_file: Create new files
- edit_file: Modify existing files (preferred over write_file)
- search_files: Find code patterns in the codebase via regex
- list_directory: Explore project structure
- run_command: Run linters, formatters, tests

IMPORTANT: Work incrementally. If this is a re-run after failed review/tests:
- Focus ONLY on fixing the reported issues
- Do NOT rewrite code that already works
- Read the specific files mentioned in the findings

After writing code, run the project's linter on changed files if available.
Report every file you created or modified."""


def coder_agent(state: dict) -> dict:
    """Write code based on the architecture spec."""
    llm = get_llm_for_agent("coder")
    architecture = state.get("architecture_spec", "")
    requirements = state.get("requirements_spec", "")
    design = state.get("design_spec", "")
    project_dir = state.get("project_dir", "")
    project_context = state.get("project_context", "")
    codebase_index = state.get("codebase_index", "")
    feedback = state.get("human_feedback", "")
    iteration = state.get("iteration", 0)

    # If coming from a failed evaluation, include findings
    review = state.get("review_findings", [])
    tests = state.get("test_results", [])
    security = state.get("security_findings", [])

    is_fix_iteration = iteration > 0 and (review or tests or security)

    if is_fix_iteration:
        # Focus mode: only fix reported issues
        user_msg = f"""## FIX ITERATION {iteration + 1}

You are fixing issues found by reviewers. Do NOT rewrite everything.
Focus ONLY on the specific issues listed below.

Project Directory: {project_dir}
"""
    else:
        user_msg = f"""Architecture Spec:
{architecture}

Requirements:
{requirements}

Design:
{design}

Project Directory: {project_dir}
"""

    if project_context:
        user_msg += f"\nProject Context:\n{project_context}\n"

    if codebase_index:
        user_msg += f"\nCodebase Index (existing code map):\n{codebase_index[:2000]}\n"

    work_items = state.get("work_items", [])
    if work_items and not is_fix_iteration:
        items_text = "\n".join(
            f"  {i+1}. [{wi.get('priority', 2)}] {wi.get('title', '')}: {wi.get('description', '')}"
            + (f" (files: {', '.join(wi.get('files_hint', []))})" if wi.get('files_hint') else "")
            for i, wi in enumerate(work_items)
        )
        user_msg += f"\n\nWork plan:\n{items_text}"

    if not is_fix_iteration:
        user_msg += """
Instructions:
1. Use search_codebase to find relevant existing code before reading files
2. Read the specific files identified to understand patterns exactly
3. Implement the changes described in the architecture spec
4. Run linters on every file you touch
5. List every file you created or modified"""

    if feedback:
        user_msg += f"\n\nUser feedback:\n{feedback}"

    if review:
        critical_review = [f for f in review if f.get("severity") in ("critical", "warn")]
        if critical_review:
            user_msg += "\n\n## Code Review Issues to Fix:\n"
            for f in critical_review:
                user_msg += f"- [{f.get('severity')}] {f.get('file', '')}:{f.get('line', '')} {f.get('message', '')}\n"

    if tests:
        critical_tests = [f for f in tests if f.get("severity") in ("critical", "warn")]
        if critical_tests:
            user_msg += "\n\n## Failing Tests to Fix:\n"
            for f in critical_tests:
                hint = f.get("fix_hint", "")
                category = f.get("error_category", "")
                msg = f.get("message", "")
                user_msg += f"- {msg}"
                if category:
                    user_msg += f" [category: {category}]"
                if hint:
                    user_msg += f" [hint: {hint}]"
                user_msg += "\n"

    if security:
        critical_sec = [f for f in security if f.get("severity") in ("critical", "warn")]
        if critical_sec:
            user_msg += "\n\n## Security Issues to Fix:\n"
            for f in critical_sec:
                user_msg += f"- [{f.get('severity')}] {f.get('message', '')}\n"

    response, changed_files = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=30,
        agent_name="coder",
    )

    return {
        "code_changes": changed_files,
        "phase": "review",
        "messages": [f"[Coder] {'Fixed' if is_fix_iteration else 'Modified'} {len(changed_files)} files: {', '.join(changed_files[:10])}"],
    }
