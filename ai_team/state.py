"""State schema for the AI Dev Team graph."""

from __future__ import annotations

import operator
from typing import Annotated, Literal
from typing import TypedDict as _TypedDict

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


class AgentMessage(_TypedDict):
    role: str       # which agent sent it (e.g. "coder", "reviewer")
    content: str    # message text
    timestamp: str  # ISO format timestamp


class WorkItem(_TypedDict):
    title: str
    description: str
    files_hint: list[str]   # suggested files to touch
    priority: int           # 1=high, 2=medium, 3=low


def _keep_recent_messages(existing: list[str], new: list[str]) -> list[str]:
    """Custom reducer: append new messages but cap at 100 most recent."""
    combined = existing + new
    if len(combined) > 100:
        return combined[-100:]
    return combined


def _replace_work_items(old: list, new: list) -> list:
    """Work items are always replaced wholesale, not appended."""
    return new if new else old


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

    # Planner output
    work_items: Annotated[list[WorkItem], _replace_work_items]

    # Debugger output
    debugger_report: str

    # Docs agent output
    docs_output: str

    # Agent-to-agent chat bus messages
    agent_messages: Annotated[list[AgentMessage], operator.add]

    # GitHub PR URL (set after final review)
    pr_url: str

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
