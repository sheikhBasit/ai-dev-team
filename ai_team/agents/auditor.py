"""Auditor Agent — Code quality, architecture drift, and tech debt auditor."""

from __future__ import annotations

from ai_team.agents.react_loop import get_token_usage, parse_findings, react_loop
from ai_team.bus import bus
from ai_team.config import get_llm_for_agent


SYSTEM_PROMPT = """You are a Principal Engineer performing a technical code audit.

Assess four dimensions:
1. Code Quality — naming, function length (>50 lines is a smell), dead code, duplicate logic
2. Architecture Drift — does new code follow the project's existing patterns (ORM style, error handling, layering)?
3. Tech Debt — hardcoded values, missing abstractions, copy-paste code, commented-out blocks
4. Test Coverage — critical paths tested? edge cases covered? untested public functions?

For each finding output EXACTLY this JSON:
{"severity": "critical|warn|info", "file": "path", "line": 123, "message": "Category: description"}

Categories: Quality | Architecture | TechDebt | TestCoverage

End with a summary line:
{"severity": "info", "file": "", "line": 0, "message": "Audit score: X/10. Critical: N, Warnings: N"}

If no issues:
{"severity": "pass", "file": "", "line": 0, "message": "Audit passed. Score: 9/10. No significant issues."}"""


def auditor_agent(state: dict) -> dict:
    """Audit code for quality, architecture drift, and tech debt."""
    llm = get_llm_for_agent("auditor")
    code_changes = state.get("code_changes", [])
    project_dir = state.get("project_dir", "")
    architecture_spec = state.get("architecture_spec", "")

    user_msg = f"""Audit these changed files for code quality, architecture drift, and tech debt:
{chr(10).join(code_changes)}

Project directory: {project_dir}

Architecture spec:
{architecture_spec}

Instructions:
1. Read each changed file carefully
2. Check Code Quality — naming, function length, dead code, duplicate logic
3. Check Architecture Drift — compare against existing project patterns
4. Check Tech Debt — hardcoded values, missing abstractions, commented-out blocks
5. Check Test Coverage — critical paths tested? untested public functions?
6. Output findings in JSON format with the correct Category prefix"""

    response, _ = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=10,
        agent_name="auditor",
    )

    findings = parse_findings(response.content)
    for f in findings:
        f["agent"] = "auditor"

    bus.publish("auditor", f"Audit complete. {len(findings)} findings.")

    return {
        "audit_findings": findings,
        "total_tokens": get_token_usage().total_tokens,
    }
