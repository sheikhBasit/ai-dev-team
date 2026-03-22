"""Architect Agent — Designs system architecture, DB schemas, API contracts."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt

from ai_team.config import get_llm
from ai_team.tools.shell_tools import ALL_TOOLS


SYSTEM_PROMPT = """You are a Senior Solution Architect. You design the technical implementation
plan that developers will follow exactly.

You have tools to read the existing codebase. USE THEM to understand:
- Existing patterns (how endpoints are structured, how services work)
- Database models (SQLAlchemy models)
- Existing tests (test patterns, fixtures)
- Configuration (how the app is configured)

Your output must include:

1. **Technical Design**
   - Which existing files to modify and what changes
   - Which new files to create
   - Data flow diagram (text-based)

2. **Database Changes** (if any)
   - New models / modified models (SQLAlchemy)
   - Migration strategy
   - Index recommendations

3. **API Contract** (if any)
   - Endpoint paths, methods, request/response schemas
   - Auth requirements
   - Error responses

4. **Integration Points**
   - What existing services/modules are affected
   - External API calls needed
   - Cache/Redis usage

5. **Risk Assessment**
   - What could break
   - Performance implications
   - Security considerations

Reference specific files and line numbers from the codebase."""


def architect_agent(state: dict) -> dict:
    """Design the technical architecture."""
    llm = get_llm().bind_tools(ALL_TOOLS)
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

    # Run agent loop — let LLM call tools until it has enough context
    from langchain_core.messages import AIMessage

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ]

    # Simple ReAct loop: let the LLM call tools up to 10 times
    for _ in range(10):
        response = llm.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        # Execute tool calls
        from langchain_core.messages import ToolMessage

        for tool_call in response.tool_calls:
            tool_map = {t.name: t for t in ALL_TOOLS}
            tool_fn = tool_map.get(tool_call["name"])
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
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
            "messages": ["[Architect] Architecture approved by user."],
        }
    else:
        return {
            "human_feedback": approval.get("feedback", "Please revise"),
            "phase": "architecture",
            "messages": [f"[Architect] User requested changes: {approval.get('feedback', '')}"],
        }
