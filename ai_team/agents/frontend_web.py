"""Frontend Web Agent — React/Next.js/TypeScript specialist coder."""

from __future__ import annotations

from ai_team.config import get_llm_for_agent


SYSTEM_PROMPT = """You are a Senior Frontend Engineer specializing in React, Next.js 14+ App Router, TypeScript, and Tailwind CSS.

Rules:
- TypeScript only — no plain JS files
- Next.js App Router: Server Components by default, 'use client' only when needed
- Tailwind for all styling — no inline styles, no CSS modules unless the project already uses them
- Use shadcn/ui components if present in package.json
- React Query or SWR for data fetching in client components
- Zod for form validation and API response schemas
- Follow existing file naming: kebab-case files, PascalCase components
- Read existing components before creating new ones — match patterns exactly
- Never add npm dependencies without checking package.json first

You have tools to read, write, edit files and run commands.
After writing code, run: npx tsc --noEmit
Report every file you created or modified."""


def _format_work_items(items: list) -> str:
    """Format work items into a readable numbered list."""
    if not items:
        return ""
    lines = []
    for i, wi in enumerate(items):
        priority = wi.get("priority", 2)
        title = wi.get("title", "")
        description = wi.get("description", "")
        files_hint = wi.get("files_hint", [])
        line = f"  {i + 1}. [{priority}] {title}: {description}"
        if files_hint:
            line += f" (files: {', '.join(files_hint)})"
        lines.append(line)
    return "\n".join(lines)


def frontend_web_agent(state: dict) -> dict:
    """Write React/Next.js/TypeScript frontend code based on the task and specs."""
    from ai_team.agents.react_loop import react_loop  # noqa: PLC0415
    from ai_team.bus import bus  # noqa: PLC0415

    llm = get_llm_for_agent("frontend_web")

    inbox = bus.consume("frontend_web")

    task = state.get("task", "")
    project_dir = state.get("project_dir", "")
    project_context = state.get("project_context", "")
    architecture_spec = state.get("architecture_spec", "")
    work_items = state.get("work_items", [])
    inject_message = state.get("inject_message", "")

    user_msg = f"""Task:
{task}

Project Directory: {project_dir}
"""

    if project_context:
        user_msg += f"\nProject Context:\n{project_context}\n"

    if architecture_spec:
        user_msg += f"\nArchitecture Spec:\n{architecture_spec}\n"

    items_text = _format_work_items(work_items)
    if items_text:
        user_msg += f"\nWork plan:\n{items_text}\n"

    if inbox:
        inbox_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in inbox)
        user_msg += f"\nMessages from team:\n{inbox_text}\n"

    if inject_message:
        user_msg += f"\nDirective:\n{inject_message}\n"

    response, changed_files = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=30,
        agent_name="frontend_web",
    )

    bus.publish("frontend_web", "Frontend web code complete.")

    return {
        "code_changes": changed_files,
        "total_tokens": state.get("total_tokens", 0),
        "inject_message": "",
    }
