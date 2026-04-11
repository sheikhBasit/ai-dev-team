"""State schema for the AI Dev Team graph."""

from __future__ import annotations

import operator
from typing import Annotated, Literal

from typing_extensions import TypedDict

Phase = Literal[
    "requirements",
    "design",
    "architecture",
    "code",
    "review",
    "test",
    "security",
    "evaluate",
    "done",
]


class AgentFinding(TypedDict, total=False):
    agent: str
    severity: Literal["critical", "warn", "info", "pass"]
    message: str
    file: str
    line: int


class WorkItem(TypedDict, total=False):
    """Tracks a single unit of work from the architecture spec."""
    id: str
    description: str
    status: Literal["pending", "in_progress", "done", "failed"]
    files: list[str]


def _keep_recent_messages(existing: list[str], new: list[str]) -> list[str]:
    """Custom reducer: append new messages but cap at 100 most recent."""
    combined = existing + new
    if len(combined) > 100:
        return combined[-100:]
    return combined


class State(TypedDict, total=False):
    # User input
    task: str
    project_dir: str

    # Auto-detected project context (from project_detector)
    project_context: str

    # Codebase index (lightweight map of classes, functions, endpoints)
    codebase_index: str

    # Current phase tracking
    phase: Phase
    iteration: int
    max_iterations: int
    phase_rejections: int  # tracks how many times current phase was rejected

    # Accumulated outputs from each agent
    requirements_spec: str
    design_spec: str
    architecture_spec: str
    code_changes: Annotated[list[str], operator.add]
    review_findings: Annotated[list[AgentFinding], operator.add]
    test_results: Annotated[list[AgentFinding], operator.add]
    security_findings: Annotated[list[AgentFinding], operator.add]

    # Incremental work tracking
    work_items: list[WorkItem]

    # Evaluation
    evaluation: str
    all_passed: bool

    # Git diff for final review
    git_diff: str

    # Human feedback (from interrupt)
    human_feedback: str

    # Token / cost tracking
    total_tokens: int
    total_cost: float

    # Session memory — lessons learned
    lessons_learned: Annotated[list[str], operator.add]

    # Conversation log (capped at 100 messages)
    messages: Annotated[list[str], _keep_recent_messages]
