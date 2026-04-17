"""Frontend Desktop Agent — Tauri 2.x + React + Rust IPC specialist."""

from __future__ import annotations

from ai_team.agents.react_loop import react_loop
from ai_team.bus import bus
from ai_team.config import get_llm_for_agent


SYSTEM_PROMPT = """You are a Senior Desktop Engineer specializing in Tauri 2.x, React + TypeScript, and Rust.

Rules:
- Tauri 2.x only — use #[tauri::command] for IPC, emit/listen for events
- IPC: invoke() on frontend, #[tauri::command] + tauri::State<Mutex<T>> on Rust side
- Frontend: TypeScript + Tailwind — same rules as a React/Next.js project
- Security: set explicit capability allowlist in tauri.conf.json — never wildcard
- Never use deprecated Tauri 1.x APIs
- Read src-tauri/tauri.conf.json and src-tauri/Cargo.toml before touching Rust code
- For audio/tray/notifications: use tauri plugin ecosystem, not raw JS APIs

After writing Rust code, always run: cargo check --manifest-path src-tauri/Cargo.toml
Report every file you created or modified."""


def _format_work_items(items: list) -> str:
    """Format work items into a readable string for the agent prompt."""
    if not items:
        return ""
    lines = []
    for i, wi in enumerate(items):
        priority = wi.get("priority", 2)
        title = wi.get("title", "")
        description = wi.get("description", "")
        line = f"  {i + 1}. [{priority}] {title}: {description}"
        files_hint = wi.get("files_hint", [])
        if files_hint:
            line += f" (files: {', '.join(files_hint)})"
        lines.append(line)
    return "\n".join(lines)


def frontend_desktop_agent(state: dict) -> dict:
    """Write Tauri 2.x desktop code based on the task and architecture spec."""
    llm = get_llm_for_agent("frontend_desktop")

    inbox = bus.consume("frontend_desktop")
    inject = state.get("inject_message", "")

    task = state.get("task", "")
    project_dir = state.get("project_dir", "")
    project_context = state.get("project_context", "")
    architecture_spec = state.get("architecture_spec", "")
    work_items = state.get("work_items", [])

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

    if inject:
        user_msg += f"\nAdditional context:\n{inject}\n"

    user_msg += """
Instructions:
1. Read src-tauri/tauri.conf.json and src-tauri/Cargo.toml before modifying Rust code
2. Use Tauri 2.x APIs only — no Tauri 1.x patterns
3. Run cargo check --manifest-path src-tauri/Cargo.toml after writing Rust code
4. Run the project linter on TypeScript/React files you touch
5. List every file you created or modified"""

    response, changed_files = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=30,
        agent_name="frontend_desktop",
    )

    bus.publish("frontend_desktop", "Desktop code complete.")

    total_tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = response.usage_metadata
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

    return {
        "code_changes": changed_files,
        "total_tokens": total_tokens,
        "inject_message": "",
    }
