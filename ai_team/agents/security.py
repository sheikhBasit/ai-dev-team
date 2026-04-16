"""Security Agent — Audits code for vulnerabilities."""

from __future__ import annotations

from ai_team.agents.react_loop import parse_findings, react_loop


SYSTEM_PROMPT = """You are a Senior Security Engineer performing a security audit.

Check every changed file for:

1. **Injection** — SQL injection (raw queries?), command injection (subprocess with user input?),
   template injection, LDAP injection
2. **Authentication** — Missing auth on endpoints? Weak token validation? Hardcoded secrets?
3. **Authorization** — Can users access other users' data? Missing role checks? IDOR?
4. **Data Exposure** — Passwords in logs? Sensitive data in responses? PII leaks?
5. **Input Validation** — Unvalidated user input at API boundaries? Missing schemas?
6. **Cryptography** — Weak hashing? Hardcoded keys? HTTP instead of HTTPS?
7. **Dependencies** — Known vulnerable packages?

Also search for hardcoded secrets: password, secret, key, token in changed files.

For each finding, output EXACTLY this JSON format:
{"severity": "critical|warn|info", "file": "path", "line": 123, "message": "OWASP category: description"}

If no issues found:
{"severity": "pass", "file": "", "line": 0, "message": "Security audit passed."}"""


def security_agent(state: dict) -> dict:
    """Audit code for security vulnerabilities."""
    llm = get_llm_for_agent("security")
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

    response, _ = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=12,
        agent_name="security",
    )

    findings = parse_findings(response.content)
    for f in findings:
        f["agent"] = "security"

    return {
        "security_findings": findings,
        "messages": [f"[Security] {len(findings)} security findings."],
    }
