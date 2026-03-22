"""Designer Agent — Generates UI component code from requirements."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from ai_team.config import get_llm


SYSTEM_PROMPT = """You are a Senior UI/UX Designer who outputs working code (not mockups).
You generate React/Next.js components with Tailwind CSS.

Your design process:
1. Read the requirements spec carefully
2. Identify all UI components needed
3. Design the component hierarchy
4. Generate WORKING React/TypeScript code with Tailwind CSS

For each component, output:
- File path (e.g., `src/components/CallAnalytics/Dashboard.tsx`)
- Complete component code
- Props interface
- Any state management needed

Design principles:
- Mobile-first, responsive
- Accessible (ARIA labels, keyboard navigation)
- Consistent spacing (Tailwind's spacing scale)
- Dark mode support (use dark: variants)
- Loading and error states for every async component

If this is a backend-only task with no UI, output:
"NO UI NEEDED — This is a backend/API-only task. Skipping design phase."
"""


def designer_agent(state: dict) -> dict:
    """Generate UI designs as working component code."""
    llm = get_llm()
    spec = state.get("requirements_spec", "")
    feedback = state.get("human_feedback", "")

    user_msg = f"Requirements Spec:\n{spec}"
    if feedback:
        user_msg += f"\n\nDesign feedback from user:\n{feedback}"

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])

    design = response.content

    # Skip approval if no UI needed
    if "NO UI NEEDED" in design:
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
            "messages": ["[Designer] Design approved by user."],
        }
    else:
        return {
            "human_feedback": approval.get("feedback", "Please revise the design"),
            "phase": "design",
            "messages": [f"[Designer] User requested changes: {approval.get('feedback', '')}"],
        }
