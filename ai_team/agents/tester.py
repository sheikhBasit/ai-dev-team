"""Tester Agent — QA Engineer that writes and runs tests."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from ai_team.config import get_llm
from ai_team.tools.shell_tools import ALL_TOOLS


SYSTEM_PROMPT = """You are a Senior QA Engineer. You write comprehensive tests and run them.

Your process:
1. Read the changed files to understand what was implemented
2. Read existing test files to understand the test patterns (conftest.py, existing tests)
3. Write tests covering:
   - Happy path (normal operation)
   - Edge cases (empty input, max values, special characters)
   - Error cases (invalid auth, missing fields, DB errors)
   - Integration (full request → response cycle)
4. Run the tests with pytest -v
5. If tests fail, diagnose and fix them

Test patterns to follow:
- Use the project's existing conftest.py fixtures
- async tests with httpx AsyncClient
- Test file goes in api/tests/api_tests/
- Name: test_<feature>.py
- Class: Test<Feature>

After running tests, output findings in this JSON format (one per line):
{"severity": "critical|warn|info|pass", "file": "test_file.py", "line": 0, "message": "description"}

Use severity "critical" for failing tests, "pass" if all tests pass."""


def tester_agent(state: dict) -> dict:
    """Write and run tests."""
    llm = get_llm().bind_tools(ALL_TOOLS)
    code_changes = state.get("code_changes", [])
    project_dir = state.get("project_dir", "")
    requirements = state.get("requirements_spec", "")

    user_msg = f"""Changed files:
{chr(10).join(code_changes)}

Requirements (what to test against):
{requirements}

Project directory: {project_dir}

Instructions:
1. Read the conftest.py at {project_dir}/backend/api/tests/conftest.py
2. Read a few existing tests to understand patterns
3. Read the changed files
4. Write comprehensive tests
5. Run: cd {project_dir}/backend/api && python -m pytest tests/ -v
6. If tests fail, fix them and re-run
7. Output findings in JSON format"""

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ]

    for _ in range(15):
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

    import json
    import re

    findings = []
    for line in response.content.splitlines():
        json_matches = re.findall(r'\{[^}]+\}', line)
        for match in json_matches:
            try:
                finding = json.loads(match)
                if "severity" in finding:
                    findings.append(finding)
            except json.JSONDecodeError:
                continue

    if not findings:
        findings = [{"severity": "info", "file": "", "line": 0, "message": "Tests completed, no structured findings."}]

    return {
        "test_results": findings,
        "messages": [f"[Tester] {len(findings)} test findings."],
    }
