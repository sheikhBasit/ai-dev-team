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


class State(TypedDict, total=False):
    # User input
    task: str
    project_dir: str

    # Current phase tracking
    phase: Phase
    iteration: int
    max_iterations: int

    # Accumulated outputs from each agent
    requirements_spec: str
    design_spec: str
    architecture_spec: str
    code_changes: Annotated[list[str], operator.add]
    review_findings: Annotated[list[AgentFinding], operator.add]
    test_results: Annotated[list[AgentFinding], operator.add]
    security_findings: Annotated[list[AgentFinding], operator.add]

    # Evaluation
    evaluation: str
    all_passed: bool

    # Human feedback (from interrupt)
    human_feedback: str

    # Conversation log
    messages: Annotated[list[str], operator.add]
