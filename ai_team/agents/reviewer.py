"""Reviewer Agent — Senior Tech Lead code review."""

from __future__ import annotations

from ai_team.agents.react_loop import parse_findings, react_loop
from ai_team.config import get_llm_for_agent


SYSTEM_PROMPT = """You are a Senior Tech Lead performing a thorough code review.

Review every changed file for:

1. **Correctness** — Does the code do what the spec says? Logic errors? Off-by-one?
2. **Patterns** — Does it follow the project's existing patterns? (read similar files to compare)
3. **Error handling** — Are API boundaries validated? Are DB errors caught?
4. **Performance** — N+1 queries? Missing indexes? Unnecessary loops? Memory leaks?
5. **Readability** — Clear variable names? No magic numbers? Reasonable complexity?
6. **Edge cases** — Empty inputs? Null values? Concurrent access?

For each finding, output EXACTLY this JSON format (one per line):
{"severity": "critical|warn|info", "file": "path", "line": 123, "message": "description"}

If the code is good, output:
{"severity": "pass", "file": "", "line": 0, "message": "Code review passed. No issues found."}

Be thorough but fair. Don't flag style issues that linters handle."""


def reviewer_agent(state: dict) -> dict:
    """Review code changes."""
    llm = get_llm_for_agent("reviewer")
    code_changes = state.get("code_changes", [])
    project_dir = state.get("project_dir", "")
    architecture = state.get("architecture_spec", "")

    user_msg = f"""Review these changed files:
{chr(10).join(code_changes)}

Architecture spec (what the code should do):
{architecture}

Project directory: {project_dir}

Instructions:
1. Read each changed file
2. Read similar existing files to compare patterns
3. Check against the architecture spec
4. Output findings in JSON format"""

    response, _ = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=12,
        agent_name="reviewer",
    )

    findings = parse_findings(response.content)
    for f in findings:
        f["agent"] = "reviewer"

    return {
        "review_findings": findings,
        "messages": [f"[Reviewer] {len(findings)} findings."],
    }
