"""Evaluator Agent — Decides whether to ship or loop back."""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command

from ai_team.agents.react_loop import invoke_llm_with_retry

logger = logging.getLogger("ai_team.agents.evaluator")

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


def evaluator_agent(state: dict) -> Command[Literal["coder", "learn_lessons"]]:
    """Evaluate all findings and decide: ship or loop back."""
    llm = get_llm_for_agent("evaluator")
    review = state.get("review_findings", [])
    tests = state.get("test_results", [])
    security = state.get("security_findings", [])
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 5)

    all_findings = review + tests + security
    has_critical = any(f.get("severity") == "critical" for f in all_findings)
    warn_count = sum(1 for f in all_findings if f.get("severity") == "warn")

    user_msg = f"""Iteration: {iteration + 1} / {max_iterations}

Code Review Findings:
{_format_findings(review)}

Test Results:
{_format_findings(tests)}

Security Findings:
{_format_findings(security)}

Make your SHIP / NO_SHIP decision."""

    response = invoke_llm_with_retry(llm, [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])

    evaluation = response.content
    should_ship = not has_critical and warn_count <= 3

    new_iteration = iteration + 1

    # Force ship if max iterations reached
    if new_iteration >= max_iterations and not should_ship:
        should_ship = True
        evaluation += (
            f"\n\n[FORCED] Max iterations ({max_iterations}) reached. "
            f"Shipping with {sum(1 for f in all_findings if f.get('severity') == 'critical')} "
            f"critical and {warn_count} warn issues remaining."
        )
        logger.warning("Forcing ship at max iterations (%d)", max_iterations)

    if should_ship:
        logger.info("SHIP decision at iteration %d", new_iteration)
        return Command(
            update={
                "evaluation": evaluation,
                "all_passed": not has_critical,
                "iteration": new_iteration,
                "messages": [f"[Evaluator] SHIP at iteration {new_iteration}"],
            },
            goto="learn_lessons",
        )
    else:
        logger.info(
            "NO_SHIP at iteration %d — %d critical, %d warn",
            new_iteration, int(has_critical), warn_count,
        )
        return Command(
            update={
                "evaluation": evaluation,
                "all_passed": False,
                "iteration": new_iteration,
                "messages": [f"[Evaluator] NO_SHIP — looping back (iteration {new_iteration}/{max_iterations})"],
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
