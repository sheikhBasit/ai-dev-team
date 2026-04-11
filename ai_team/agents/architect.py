"""Architect Agent — Designs system architecture, DB schemas, API contracts."""

from __future__ import annotations

from langgraph.types import interrupt

from ai_team.agents.react_loop import react_loop
from ai_team.config import get_llm


SYSTEM_PROMPT = """You are a Senior Solution Architect. You design the technical implementation
plan that developers will follow exactly.

You have tools to read the existing codebase. USE THEM to understand:
- Existing patterns (how endpoints are structured, how services work)
- Database models (ORM models)
- Existing tests (test patterns, fixtures)
- Configuration (how the app is configured)

Your output must include:

1. **Technical Design**
   - Which existing files to modify and what changes
   - Which new files to create
   - Data flow diagram (text-based)

2. **Database Changes** (if any)
   - New models / modified models
   - Migration strategy
   - Index recommendations

3. **API Contract** (if any)
   - Endpoint paths, methods, request/response schemas
   - Auth requirements
   - Error responses

4. **Integration Points**
   - What existing services/modules are affected
   - External API calls needed
   - Cache/queue usage

5. **Risk Assessment**
   - What could break
   - Performance implications
   - Security considerations

Reference specific files and line numbers from the codebase."""


def architect_agent(state: dict) -> dict:
    """Design the technical architecture."""
    llm = get_llm()
    spec = state.get("requirements_spec", "")
    design = state.get("design_spec", "")
    project_dir = state.get("project_dir", "")
    feedback = state.get("human_feedback", "")

    user_msg = f"""Requirements Spec:
{spec}

Design Spec:
{design}

Project Directory: {project_dir}

Instructions:
1. First, explore the project structure using list_directory and read_file
2. Understand existing patterns by reading key files
3. Then produce the architecture document

Start by listing the project directory to understand the structure."""

    if feedback:
        user_msg += f"\n\nArchitecture feedback from user:\n{feedback}"

    response, _ = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=15,
        agent_name="architect",
    )

    architecture = response.content

    approval = interrupt({
        "agent": "Architect Agent",
        "phase": "architecture",
        "output": architecture,
        "question": "Review the architecture. Approve, reject, or give feedback.",
    })

    if approval.get("decision") == "approved":
        return {
            "architecture_spec": architecture,
            "phase": "code",
            "phase_rejections": 0,
            "messages": ["[Architect] Architecture approved by user."],
        }
    else:
        rejections = state.get("phase_rejections", 0) + 1
        return {
            "human_feedback": approval.get("feedback", "Please revise"),
            "phase": "architecture",
            "phase_rejections": rejections,
            "messages": [f"[Architect] User requested changes ({rejections}/5): {approval.get('feedback', '')}"],
        }
