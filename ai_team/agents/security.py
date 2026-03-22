"""Security Agent — Audits code for vulnerabilities."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from ai_team.config import get_llm
from ai_team.tools.shell_tools import ALL_TOOLS


SYSTEM_PROMPT = """You are a Senior Security Engineer performing a security audit.

Check every changed file for:

1. **Injection** — SQL injection (raw queries?), command injection (subprocess with user input?),
   template injection, LDAP injection
2. **Authentication** — Missing auth on endpoints? Weak token validation? Hardcoded secrets?
3. **Authorization** — Can users access other users' data? Missing role checks? IDOR?
4. **Data Exposure** — Passwords in logs? Sensitive data in responses? PII leaks?
5. **Input Validation** — Unvalidated user input at API boundaries? Missing Pydantic schemas?
6. **Cryptography** — Weak hashing? Hardcoded keys? HTTP instead of HTTPS?
7. **Dependencies** — Known vulnerable packages?

Also run these commands if applicable:
- ruff check <files> (catches some security patterns)
- Search for: password, secret, key, token in changed files (potential hardcoded secrets)

For each finding, output EXACTLY this JSON format:
{"severity": "critical|warn|info", "file": "path", "line": 123, "message": "OWASP category: description"}

If no issues found:
{"severity": "pass", "file": "", "line": 0, "message": "Security audit passed."}"""


def security_agent(state: dict) -> dict:
    """Audit code for security vulnerabilities."""
    llm = get_llm().bind_tools(ALL_TOOLS)
    code_changes = state.get("code_changes", [])
    project_dir = state.get("project_dir", "")

    user_msg = f"""Audit these changed files for security vulnerabilities:
{chr(10).join(code_changes)}

Project directory: {project_dir}

Instructions:
1. Read each changed file carefully
2. Check for OWASP Top 10 vulnerabilities
3. Search for hardcoded secrets or credentials
4. Check that all endpoints have proper auth
5. Output findings in JSON format"""

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
        findings = [{"severity": "pass", "file": "", "line": 0, "message": "Security audit complete."}]

    return {
        "security_findings": findings,
        "messages": [f"[Security] {len(findings)} security findings."],
    }
