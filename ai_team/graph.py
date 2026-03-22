"""Main LangGraph orchestrator — wires all agents into the pipeline."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ai_team.agents.architect import architect_agent
from ai_team.agents.coder import coder_agent
from ai_team.agents.designer import designer_agent
from ai_team.agents.evaluator import evaluator_agent
from ai_team.agents.requirements import requirements_agent
from ai_team.agents.reviewer import reviewer_agent
from ai_team.agents.security import security_agent
from ai_team.agents.tester import tester_agent
from ai_team.state import State


# ── Phase routing ────────────────────────────────────────────────────────────

def route_after_requirements(state: State) -> Literal["requirements", "designer"]:
    """Loop requirements if user rejected, else move to design."""
    if state.get("phase") == "requirements":
        return "requirements"
    return "designer"


def route_after_design(state: State) -> Literal["designer", "architect"]:
    if state.get("phase") == "design":
        return "designer"
    return "architect"


def route_after_architecture(state: State) -> Literal["architect", "coder"]:
    if state.get("phase") == "architecture":
        return "architect"
    return "coder"


def fan_out_verification(state: State) -> list[Send]:
    """After coding, fan out to reviewer + tester + security in parallel."""
    return [
        Send("reviewer", state),
        Send("tester", state),
        Send("security", state),
    ]


def human_final_review(state: State) -> dict:
    """Final checkpoint — show results to user before shipping."""
    from langgraph.types import interrupt

    code_changes = state.get("code_changes", [])
    evaluation = state.get("evaluation", "")

    approval = interrupt({
        "agent": "Final Review",
        "phase": "done",
        "output": f"Evaluation:\n{evaluation}\n\nChanged files:\n" + "\n".join(code_changes),
        "question": "Ship it? (approve to commit, reject to abandon)",
    })

    if approval.get("decision") == "approved":
        return {
            "phase": "done",
            "messages": ["[Ship] User approved. Ready to commit."],
        }
    else:
        return {
            "phase": "done",
            "messages": [f"[Abandoned] User rejected: {approval.get('feedback', '')}"],
        }


# ── Merge node for parallel results ─────────────────────────────────────────

def merge_verification(state: State) -> dict:
    """After all verification agents complete, move to evaluator."""
    return {"messages": ["[Merge] All verification agents complete. Moving to evaluator."]}


# ── Build the graph ──────────────────────────────────────────────────────────

def build_graph():
    """Build and compile the AI Dev Team graph."""
    builder = StateGraph(State)

    # Add all agent nodes
    builder.add_node("requirements", requirements_agent)
    builder.add_node("designer", designer_agent)
    builder.add_node("architect", architect_agent)
    builder.add_node("coder", coder_agent)
    builder.add_node("reviewer", reviewer_agent)
    builder.add_node("tester", tester_agent)
    builder.add_node("security", security_agent)
    builder.add_node("evaluator", evaluator_agent)
    builder.add_node("human_final_review", human_final_review)

    # Phase 1: Requirements (with human approval loop)
    builder.add_edge(START, "requirements")
    builder.add_conditional_edges("requirements", route_after_requirements)

    # Phase 2: Design (with human approval loop)
    builder.add_conditional_edges("designer", route_after_design)

    # Phase 3: Architecture (with human approval loop)
    builder.add_conditional_edges("architect", route_after_architecture)

    # Phase 4: Code
    # After coding, fan out to parallel verification
    builder.add_conditional_edges("coder", fan_out_verification, ["reviewer", "tester", "security"])

    # Phase 5: Verification agents all flow to evaluator
    builder.add_edge("reviewer", "evaluator")
    builder.add_edge("tester", "evaluator")
    builder.add_edge("security", "evaluator")

    # Phase 6: Evaluator decides — Command routes to either "coder" or "human_final_review"
    # (routing is handled inside the evaluator_agent via Command)

    # Phase 7: Final human review → END
    builder.add_edge("human_final_review", END)

    # Compile with SQLite checkpointer for persistence
    from langgraph.checkpoint.sqlite import SqliteSaver

    import os
    db_path = os.getenv("CHECKPOINT_DB", "./checkpoints.db")
    checkpointer = SqliteSaver.from_conn_string(db_path)

    graph = builder.compile(checkpointer=checkpointer)
    return graph
