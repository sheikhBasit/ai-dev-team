"""Requirements Agent — Product Manager that creates specs from user requests."""

from __future__ import annotations

from langgraph.types import interrupt

from ai_team.agents.react_loop import invoke_llm_with_retry
from ai_team.config import get_llm_for_agent

from langchain_core.messages import HumanMessage, SystemMessage


SYSTEM_PROMPT = """You are a Senior Product Manager. Write a concise PRD for the given feature request.

Your PRD must have exactly these 6 sections and nothing else:
1. **Objective** — What are we building and why?
2. **User Stories** — As a [user], I want [feature], so that [benefit]
3. **Acceptance Criteria** — Specific, testable conditions for "done"
4. **Scope** — What's IN scope and what's explicitly OUT of scope
5. **Edge Cases** — What could go wrong? What weird inputs might happen?
6. **Dependencies** — What existing systems does this touch?

Stop writing after section 6. Do not add any other sections. Keep the total PRD under 500 words."""


def requirements_agent(state: dict) -> dict:
    """Gather requirements and produce a PRD spec."""
    llm = get_llm_for_agent("requirements", max_tokens=1500)
    task = state["task"]
    project_dir = state.get("project_dir", "")
    project_context = state.get("project_context", "")
    feedback = state.get("human_feedback", "")

    user_msg = f"Feature request: {task}"
    if feedback:
        user_msg += f"\n\nPrevious feedback from the user:\n{feedback}"
    if project_dir:
        user_msg += f"\n\nProject directory: {project_dir}"
    if project_context:
        user_msg += f"\n\nProject context:\n{project_context}"

    response = invoke_llm_with_retry(llm, [
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
            "phase_rejections": 0,
            "messages": ["[Requirements] Spec approved by user."],
        }
    else:
        rejections = state.get("phase_rejections", 0) + 1
        return {
            "human_feedback": approval.get("feedback", "Please revise"),
            "phase": "requirements",
            "phase_rejections": rejections,
            "messages": [f"[Requirements] User requested changes ({rejections}/5): {approval.get('feedback', '')}"],
        }
