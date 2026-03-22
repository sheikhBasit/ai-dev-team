"""Evaluator Agent — Decides whether to ship or loop back."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt

from ai_team.config import get_llm


SYSTEM_PROMPT = """You are an Engineering Manager making the ship/no-ship decision.

You receive findings from three agents:
- Code Reviewer (quality, patterns, correctness)
- Tester (test results, coverage)
- Security Auditor (vulnerabilities)

Decision criteria:
- ANY "critical" finding from ANY agent → NO SHIP, loop back to coder
- More than 3 "warn" findings total → NO SHIP, loop back to coder
- Only "info" or "pass" findings → SHIP

Output your decision as:
DECISION: SHIP or DECISION: NO_SHIP

Then explain why in 2-3 sentences.
List the critical/warn issues that need fixing (if any)."""


def evaluator_agent(state: dict) -> Command[Literal["coder", "human_final_review"]]:
    """Evaluate all findings and decide: ship or loop back."""
    llm = get_llm()
    review = state.get("review_findings", [])
    tests = state.get("test_results", [])
    security = state.get("security_findings", [])
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 5)

    all_findings = review + tests + security

    user_msg = f"""Iteration: {iteration + 1} / {max_iterations}

Code Review Findings:
{_format_findings(review)}

Test Results:
{_format_findings(tests)}

Security Findings:
{_format_findings(security)}

Make your SHIP / NO_SHIP decision."""

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])

    evaluation = response.content
    has_critical = any(f.get("severity") == "critical" for f in all_findings)
    warn_count = sum(1 for f in all_findings if f.get("severity") == "warn")
    should_ship = not has_critical and warn_count <= 3

    # Force ship if max iterations reached
    if iteration + 1 >= max_iterations:
        should_ship = True
        evaluation += f"\n\n[FORCED] Max iterations ({max_iterations}) reached. Shipping with current state."

    if should_ship:
        return Command(
            update={
                "evaluation": evaluation,
                "all_passed": True,
                "messages": [f"[Evaluator] SHIP — iteration {iteration + 1}"],
            },
            goto="human_final_review",
        )
    else:
        return Command(
            update={
                "evaluation": evaluation,
                "all_passed": False,
                "iteration": iteration + 1,
                "messages": [f"[Evaluator] NO_SHIP — looping back, iteration {iteration + 1}"],
            },
            goto="coder",
        )


def _format_findings(findings: list) -> str:
    if not findings:
        return "  (none)"
    lines = []
    for f in findings:
        sev = f.get("severity", "?")
        msg = f.get("message", "")
        fpath = f.get("file", "")
        line = f.get("line", "")
        loc = f"{fpath}:{line}" if fpath else ""
        lines.append(f"  [{sev}] {loc} {msg}")
    return "\n".join(lines)
