"""Reviewer Agent — Senior Tech Lead code review."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from ai_team.config import get_llm
from ai_team.tools.shell_tools import ALL_TOOLS


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

Be thorough but fair. Don't flag style issues that ruff handles."""


def reviewer_agent(state: dict) -> dict:
    """Review code changes."""
    llm = get_llm().bind_tools(ALL_TOOLS)
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

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ]

    for _ in range(10):
        response = llm.invoke(messages)
        messages.append(response)
        if not response.tool_calls:
            break
        for tool_call in response.tool_calls:
            tool_map = {t.name: t for t in ALL_TOOLS}
            tool_fn = tool_map.get(tool_call["name"])
            if tool_fn:
                result = tool_fn.invoke(tool_call["args"])
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                )

    # Parse findings from response
    import json
    import re

    findings = []
    for line in response.content.splitlines():
        line = line.strip()
        # Try to extract JSON objects from the line
        json_matches = re.findall(r'\{[^}]+\}', line)
        for match in json_matches:
            try:
                finding = json.loads(match)
                if "severity" in finding:
                    findings.append(finding)
            except json.JSONDecodeError:
                continue

    if not findings:
        findings = [{"severity": "pass", "file": "", "line": 0, "message": "Review complete, no structured findings."}]

    return {
        "review_findings": findings,
        "messages": [f"[Reviewer] Found {len(findings)} issues."],
    }
