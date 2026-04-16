"""Debugger agent — analyses failures and produces a structured debug report."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from ai_team.config import get_llm_for_agent
from ai_team.state import State

logger = logging.getLogger("ai_team.agents.debugger")

SYSTEM_PROMPT = """You are a senior debugging engineer. You receive findings from code review, tests, and security audit, then produce a concise, actionable debug report.

Your report must:
1. Identify the root cause of each failure (not just symptoms)
2. Prioritize: which issue, if fixed, would resolve the most other issues?
3. For each issue, suggest the minimal code change needed
4. Flag if any findings are false positives

Format your response as:

## Debug Report

### Critical Issues (must fix)
- **Issue**: <description>
  **Root cause**: <why it happens>
  **Fix**: <specific code change>

### Warnings (should fix)
- ...

### False Positives (can ignore)
- ...

### Recommended fix order
1. ...
"""


def debugger_agent(state: State) -> dict:
    review_findings = state.get("review_findings", [])
    test_results = state.get("test_results", [])
    security_findings = state.get("security_findings", [])

    all_findings = review_findings + test_results + security_findings
    failures = [f for f in all_findings if f.get("severity") not in ("pass", "info")]

    if not failures:
        return {
            "debugger_report": "No failures detected — all checks passed.",
            "messages": ["[Debugger] No failures to analyze."],
        }

    # Format findings for the LLM
    findings_text = json.dumps(failures, indent=2)

    code_changes = state.get("code_changes", [])
    files_text = "\n".join(f"- {f}" for f in code_changes) if code_changes else "No files recorded"

    user_msg = f"""Changed files:
{files_text}

Findings ({len(failures)} failures):
{findings_text[:4000]}

Produce a debug report with root cause analysis and fix recommendations."""

    llm = get_llm_for_agent("debugger")
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_msg)]

    try:
        response = llm.invoke(messages)
        report = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.warning("Debugger LLM call failed: %s", e)
        report = f"Debug analysis failed: {e}\n\nRaw findings:\n{findings_text[:2000]}"

    logger.info("Debugger report produced (%d chars)", len(report))
    return {
        "debugger_report": report,
        "messages": [f"[Debugger] Analysis complete. Found {len(failures)} failure(s)."],
    }
