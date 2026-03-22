"""Requirements Agent — Product Manager that creates specs from user requests."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from ai_team.config import get_llm


SYSTEM_PROMPT = """You are a Senior Product Manager. Your job is to take a user's feature request
and produce a clear, actionable Product Requirements Document (PRD).

Your PRD must include:
1. **Objective** — What are we building and why?
2. **User Stories** — As a [user], I want [feature], so that [benefit]
3. **Acceptance Criteria** — Specific, testable conditions for "done"
4. **Scope** — What's IN scope and what's explicitly OUT of scope
5. **Edge Cases** — What could go wrong? What weird inputs might happen?
6. **Dependencies** — What existing systems does this touch?

Be specific. Developers will code directly from this spec.
Ask clarifying questions if the request is ambiguous — do NOT assume."""


def requirements_agent(state: dict) -> dict:
    """Gather requirements and produce a PRD spec."""
    llm = get_llm()
    task = state["task"]
    project_dir = state.get("project_dir", "")
    feedback = state.get("human_feedback", "")

    user_msg = f"Feature request: {task}"
    if feedback:
        user_msg += f"\n\nPrevious feedback from the user:\n{feedback}"
    if project_dir:
        user_msg += f"\n\nProject directory: {project_dir}"

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])

    spec = response.content

    # Pause for human approval
    approval = interrupt({
        "agent": "Requirements Agent",
        "phase": "requirements",
        "output": spec,
        "question": "Review the requirements spec. Approve, reject, or give feedback.",
    })

    if approval.get("decision") == "approved":
        return {
            "requirements_spec": spec,
            "phase": "design",
            "messages": [f"[Requirements] Spec approved by user."],
        }
    else:
        return {
            "human_feedback": approval.get("feedback", "Please revise"),
            "phase": "requirements",
            "messages": [f"[Requirements] User requested changes: {approval.get('feedback', '')}"],
        }
