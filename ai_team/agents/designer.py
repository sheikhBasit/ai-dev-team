"""Designer Agent — Generates UI component code from requirements."""

from __future__ import annotations

from langgraph.types import interrupt

from ai_team.agents.react_loop import invoke_llm_with_retry
from ai_team.config import get_llm_for_agent

from langchain_core.messages import HumanMessage, SystemMessage


SYSTEM_PROMPT = """You are a Senior UI/UX Designer who outputs working code (not mockups).

Your design process:
1. Read the requirements spec carefully
2. Determine if this task has a UI component
3. If yes: identify all UI components needed, design the hierarchy, and generate working code
4. If no: clearly state this is a backend/API-only task

For projects with a frontend, generate appropriate component code:
- React/Next.js: TSX components with the project's styling framework
- Vue: SFC (.vue) components
- Plain HTML: HTML/CSS/JS
- Backend-only: Skip to "NO UI NEEDED"

For each component, output:
- File path
- Complete component code
- Props/interface definitions
- State management approach

Design principles:
- Mobile-first, responsive
- Accessible (ARIA labels, keyboard navigation)
- Loading and error states for async components

If this is a backend-only task with no UI, output EXACTLY:
NO_UI_NEEDED

Nothing more, nothing less for that decision line."""


def designer_agent(state: dict) -> dict:
    """Generate UI designs as working component code."""
    llm = get_llm_for_agent("designer", temperature=0.3)  # Slightly creative for design
    spec = state.get("requirements_spec", "")
    project_context = state.get("project_context", "")
    feedback = state.get("human_feedback", "")

    user_msg = f"Requirements Spec:\n{spec}"
    if project_context:
        user_msg += f"\n\nProject context:\n{project_context}"
    if feedback:
        user_msg += f"\n\nDesign feedback from user:\n{feedback}"

    response = invoke_llm_with_retry(llm, [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])

    design = response.content

    # Skip approval if no UI needed (case-insensitive check)
    if "NO_UI_NEEDED" in design.upper().replace(" ", "_"):
        return {
            "design_spec": design,
            "phase": "architecture",
            "messages": ["[Designer] No UI needed, skipping to architecture."],
        }

    approval = interrupt({
        "agent": "Designer Agent",
        "phase": "design",
        "output": design,
        "question": "Review the UI design/components. Approve, reject, or give feedback.",
    })

    if approval.get("decision") == "approved":
        return {
            "design_spec": design,
            "phase": "architecture",
            "phase_rejections": 0,
            "messages": ["[Designer] Design approved by user."],
        }
    else:
        rejections = state.get("phase_rejections", 0) + 1
        return {
            "human_feedback": approval.get("feedback", "Please revise the design"),
            "phase": "design",
            "phase_rejections": rejections,
            "messages": [f"[Designer] User requested changes ({rejections}/5): {approval.get('feedback', '')}"],
        }
