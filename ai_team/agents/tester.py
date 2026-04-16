"""Tester Agent — QA Engineer that writes and runs tests."""

from __future__ import annotations

from ai_team.agents.react_loop import categorize_test_error, parse_findings, react_loop


SYSTEM_PROMPT = """You are a Senior QA Engineer. You write comprehensive tests and run them.

Your process:
1. Read the changed files to understand what was implemented
2. Read existing test files to understand the test patterns and fixtures
3. Write tests covering:
   - Happy path (normal operation)
   - Edge cases (empty input, max values, special characters)
   - Error cases (invalid auth, missing fields)
   - Integration (full request/response cycle)
4. Run the tests
5. If tests fail, diagnose the failure using the error categories below

Error diagnosis guide — when tests fail, classify the error:
- ImportError/ModuleNotFoundError → Check requirements and imports
- SyntaxError → Fix typos, missing colons, unmatched brackets
- AssertionError → Check expected vs actual values
- Fixture not found → Check conftest.py for available fixtures
- ConnectionRefused → Database/service not running
- TypeError → Check function arguments and return types
- 422/ValidationError → Check Pydantic schemas

Follow the project's existing test patterns exactly (fixtures, naming, structure).

After running tests, output findings in this JSON format (one per line):
{"severity": "critical|warn|info|pass", "file": "test_file.py", "line": 0, "message": "description"}

Use severity "critical" for failing tests, "pass" if all tests pass."""


def tester_agent(state: dict) -> dict:
    """Write and run tests."""
    llm = get_llm_for_agent("tester")
    code_changes = state.get("code_changes", [])
    project_dir = state.get("project_dir", "")
    requirements = state.get("requirements_spec", "")
    project_context = state.get("project_context", "")
    codebase_index = state.get("codebase_index", "")

    user_msg = f"""Changed files:
{chr(10).join(code_changes)}

Requirements (what to test against):
{requirements}

Project directory: {project_dir}
"""
    if project_context:
        user_msg += f"\nProject context:\n{project_context}\n"

    if codebase_index:
        # Include test files from index
        test_lines = [l for l in codebase_index.splitlines() if "test" in l.lower()]
        if test_lines:
            user_msg += "\nExisting test files:\n" + "\n".join(test_lines[:15]) + "\n"

    user_msg += """
Instructions:
1. Explore the test directory to find existing test patterns and conftest.py
2. Read a few existing tests to understand patterns
3. Read the changed files
4. Write comprehensive tests following existing patterns
5. Run the tests
6. If tests fail, classify the error type and fix accordingly
7. Output findings in JSON format"""

    response, _ = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=20,
        agent_name="tester",
    )

    findings = parse_findings(response.content)

    # Enrich findings with error categorization
    for f in findings:
        f["agent"] = "tester"
        if f.get("severity") == "critical" and f.get("message"):
            error_info = categorize_test_error(f["message"])
            f["error_category"] = error_info["category"]
            f["fix_hint"] = error_info["hint"]

    return {
        "test_results": findings,
        "messages": [f"[Tester] {len(findings)} test findings."],
    }
