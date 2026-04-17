"""Frontend Mobile Agent — Android Kotlin/Jetpack Compose specialist."""

from __future__ import annotations

from ai_team.bus import bus


SYSTEM_PROMPT = """You are a Senior Android Engineer specializing in Kotlin, Jetpack Compose, and KMP.

Rules:
- Kotlin only — no Java
- Jetpack Compose for all UI — no XML layouts
- MVVM: ViewModel + StateFlow + Repository pattern
- Hilt for DI if already in build.gradle.kts
- Room for local DB, Retrofit + OkHttp for networking
- Coroutines + Flow — no RxJava
- Material3 components — match existing theme
- Read existing ViewModels and composables before creating new ones
- Never modify build.gradle.kts dependencies without explicit instruction

After writing code, run: ./gradlew lint
Report every file you created or modified."""


def _format_work_items(items: list) -> str:
    """Format a list of work item dicts into a readable string."""
    if not items:
        return ""
    lines = []
    for i, wi in enumerate(items):
        line = (
            f"  {i + 1}. [{wi.get('priority', 2)}] "
            f"{wi.get('title', '')}: {wi.get('description', '')}"
        )
        files_hint = wi.get("files_hint", [])
        if files_hint:
            line += f" (files: {', '.join(files_hint)})"
        lines.append(line)
    return "\n".join(lines)


def frontend_mobile_agent(state: dict) -> dict:
    """Write Android Kotlin/Jetpack Compose code based on architecture spec."""
    from ai_team.agents.react_loop import react_loop  # noqa: PLC0415
    from ai_team.config import get_llm_for_agent  # noqa: PLC0415

    llm = get_llm_for_agent("frontend_mobile")

    inbox = bus.consume("frontend_mobile")

    project_dir = state.get("project_dir", "")
    project_context = state.get("project_context", "")
    architecture_spec = state.get("architecture_spec", "")
    work_items = state.get("work_items", [])
    inject = state.get("inject_message", "")

    user_msg = f"""Architecture Spec:
{architecture_spec}

Project Directory: {project_dir}
"""

    if project_context:
        user_msg += f"\nProject Context:\n{project_context}\n"

    items_text = _format_work_items(work_items)
    if items_text:
        user_msg += f"\n\nWork plan:\n{items_text}"

    if inbox:
        inbox_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in inbox)
        user_msg += f"\n\nMessages from team:\n{inbox_text}"

    if inject:
        user_msg += f"\n\nAdditional instructions:\n{inject}"

    response, changed_files = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=30,
        agent_name="frontend_mobile",
    )

    bus.publish("frontend_mobile", "Mobile code complete.")

    return {
        "code_changes": changed_files,
        "total_tokens": 0,
        "inject_message": "",
    }
