# AI Dev Team Major Upgrades — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the AI dev team with: planner node, debugger agent, docs agent, per-agent model routing, local agent-to-agent chat bus, self-healing imports, RAG-aware reviewer, GitHub PR auto-open, structured work items, and a FastAPI+WebSocket live UI.

**Architecture:**
The pipeline grows from 15 nodes to 19. New agents (planner, debugger, docs) follow the same `react_loop` + `interrupt` pattern as existing agents. Agent-to-agent chat uses an in-process publish/subscribe bus (no external broker) stored in state. Per-agent model routing is a thin wrapper in `config.py`. The Web UI is a separate FastAPI process subscribing to the same event bus via async queues.

**Tech Stack:** Python 3.12, LangGraph 0.4+, LangChain Core, FastAPI, WebSockets, Rich (existing), rank-bm25 (existing), numpy (existing)

**Final pipeline:**
```
START → init → requirements → designer → architect → preflight
      → planner → coder → git_commit → [reviewer + tester + security] (parallel)
      → import_healer → debugger → evaluator
      → (fail) → coder (loop)
      → (ship) → learn_lessons → docs → ci_check → human_final_review → END
```

---

## Phase 1: Foundation

### Task 1: Per-Agent Model Config

**Files:**
- Modify: `ai_team/config.py`
- Modify: `ai_team/agents/requirements.py`, `designer.py`, `architect.py`, `coder.py`, `reviewer.py`, `tester.py`, `security.py`, `evaluator.py`

- [ ] **Step 1: Add `AGENT_ROLE_DEFAULTS` and `get_llm_for_agent()` to `config.py`**

Add after the existing `get_llm()` function:

```python
AGENT_ROLE_DEFAULTS = {
    "requirements": os.getenv("AGENT_MODEL_REQUIREMENTS", os.getenv("LLM_MODEL_CHEAP", "")),
    "designer":     os.getenv("AGENT_MODEL_DESIGNER",     os.getenv("LLM_MODEL_CHEAP", "")),
    "evaluator":    os.getenv("AGENT_MODEL_EVALUATOR",    os.getenv("LLM_MODEL_CHEAP", "")),
    "docs":         os.getenv("AGENT_MODEL_DOCS",         os.getenv("LLM_MODEL_CHEAP", "")),
    "architect":    os.getenv("AGENT_MODEL_ARCHITECT",    ""),
    "coder":        os.getenv("AGENT_MODEL_CODER",        ""),
    "reviewer":     os.getenv("AGENT_MODEL_REVIEWER",     ""),
    "tester":       os.getenv("AGENT_MODEL_TESTER",       ""),
    "security":     os.getenv("AGENT_MODEL_SECURITY",     ""),
    "planner":      os.getenv("AGENT_MODEL_PLANNER",      ""),
    "debugger":     os.getenv("AGENT_MODEL_DEBUGGER",     ""),
}


def get_llm_for_agent(
    agent_name: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
):
    """Get LLM configured for a specific agent role.

    Checks AGENT_MODEL_<NAME> env var first, then LLM_MODEL_CHEAP for lightweight
    agents, then falls back to LLM_MODEL.
    """
    model_override = AGENT_ROLE_DEFAULTS.get(agent_name, "")
    return get_llm(
        model_override=model_override or None,
        temperature=temperature,
        max_tokens=max_tokens,
    )
```

- [ ] **Step 2: Add env var docs to `.env.example`**

Append to `.env.example`:
```bash
# Per-agent model overrides (optional — falls back to LLM_MODEL)
# LLM_MODEL_CHEAP=claude-haiku-4-20250514
# AGENT_MODEL_CODER=claude-sonnet-4-20250514
# AGENT_MODEL_ARCHITECT=claude-sonnet-4-20250514
```

- [ ] **Step 3: Swap `get_llm()` to `get_llm_for_agent()` in all existing agents**

In each file change the import and the llm call:

`requirements.py`:
```python
from ai_team.config import get_llm_for_agent
# in requirements_agent():
llm = get_llm_for_agent("requirements")
```

`designer.py`:
```python
from ai_team.config import get_llm_for_agent
# in designer_agent():
llm = get_llm_for_agent("designer", temperature=0.3)
```

`architect.py`:
```python
from ai_team.config import get_llm_for_agent
# in architect_agent():
llm = get_llm_for_agent("architect")
```

`coder.py`:
```python
from ai_team.config import get_llm_for_agent
# in coder_agent():
llm = get_llm_for_agent("coder")
```

`reviewer.py`:
```python
from ai_team.config import get_llm_for_agent
# in reviewer_agent():
llm = get_llm_for_agent("reviewer")
```

`tester.py`:
```python
from ai_team.config import get_llm_for_agent
# in tester_agent():
llm = get_llm_for_agent("tester")
```

`security.py`:
```python
from ai_team.config import get_llm_for_agent
# in security_agent():
llm = get_llm_for_agent("security")
```

`evaluator.py`:
```python
from ai_team.config import get_llm_for_agent
# in evaluator_agent():
llm = get_llm_for_agent("evaluator")
```

- [ ] **Step 4: Verify imports**

```bash
cd /home/basitdev/Me/ai-dev-team
PYTHONPATH=. .venv/bin/python -c "
from ai_team.config import get_llm_for_agent
from ai_team.agents.requirements import requirements_agent
from ai_team.agents.coder import coder_agent
print('OK')
"
```
Expected: `OK`

- [ ] **Step 5: Run smoke tests**

```bash
make test
```
Expected: `ALL TESTS PASSED`

- [ ] **Step 6: Commit**

```bash
cd /home/basitdev/Me/ai-dev-team
git add ai_team/config.py ai_team/agents/requirements.py ai_team/agents/designer.py \
  ai_team/agents/architect.py ai_team/agents/coder.py ai_team/agents/reviewer.py \
  ai_team/agents/tester.py ai_team/agents/security.py ai_team/agents/evaluator.py .env.example
git commit -m "feat: per-agent model routing via AGENT_MODEL_<NAME> env vars"
```

---

### Task 2: State Extensions

**Files:**
- Modify: `ai_team/state.py`

- [ ] **Step 1: Add `AgentMessage` TypedDict and `_replace_work_items` reducer**

Add after the existing `WorkItem` class in `ai_team/state.py`:

```python
class AgentMessage(TypedDict, total=False):
    """A message sent between agents on the internal chat bus."""
    from_agent: str
    to_agent: str
    content: str
    timestamp: str
    message_type: Literal["info", "question", "warning", "handoff"]


def _replace_work_items(existing: list, new: list) -> list:
    """Replace work items entirely (planner owns the list)."""
    return new if new else existing
```

- [ ] **Step 2: Extend `State` class with new fields**

Add these fields to the `State` TypedDict (after `work_items`):

```python
    # Replace existing work_items line with:
    work_items: Annotated[list[WorkItem], _replace_work_items]

    # New fields:
    debugger_report: str
    docs_output: str
    agent_messages: Annotated[list[AgentMessage], operator.add]
    pr_url: str
```

- [ ] **Step 3: Verify**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.state import State, AgentMessage, WorkItem
keys = list(State.__annotations__.keys())
assert 'agent_messages' in keys
assert 'debugger_report' in keys
assert 'docs_output' in keys
assert 'pr_url' in keys
print('State keys OK:', keys)
"
```

- [ ] **Step 4: Commit**

```bash
git add ai_team/state.py
git commit -m "feat: extend state with agent_messages, debugger_report, docs_output, pr_url"
```

---

## Phase 2: Agent-to-Agent Chat Bus

### Task 3: Chat Bus Module

**Files:**
- Create: `ai_team/bus.py`

- [ ] **Step 1: Create `ai_team/bus.py`**

```python
"""Local agent-to-agent message bus.

Agents call post() to broadcast messages. Bus stores history and notifies
in-process subscribers (the Web UI WebSocket handlers).
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Callable

from ai_team.state import AgentMessage

logger = logging.getLogger("ai_team.bus")

_subscribers: list[Callable[[AgentMessage], None]] = []
_async_queues: list[asyncio.Queue] = []
_event_history: deque = deque(maxlen=200)


def subscribe(callback: Callable[[AgentMessage], None]) -> None:
    _subscribers.append(callback)


def unsubscribe(callback: Callable[[AgentMessage], None]) -> None:
    if callback in _subscribers:
        _subscribers.remove(callback)


def register_async_queue(q: asyncio.Queue) -> None:
    _async_queues.append(q)


def unregister_async_queue(q: asyncio.Queue) -> None:
    if q in _async_queues:
        _async_queues.remove(q)


def get_event_history() -> list[AgentMessage]:
    return list(_event_history)


def post(
    from_agent: str,
    content: str,
    to_agent: str = "",
    message_type: str = "info",
) -> AgentMessage:
    """Post a message. Returns the AgentMessage dict for appending to state."""
    msg: AgentMessage = {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_type": message_type,  # type: ignore[typeddict-item]
    }

    _event_history.append(msg)
    logger.debug("[bus] %s → %s: %s", from_agent, to_agent or "all", content[:80])

    for callback in list(_subscribers):
        try:
            callback(msg)
        except Exception as e:
            logger.warning("Bus subscriber error: %s", e)

    for q in list(_async_queues):
        try:
            q.put_nowait(msg)
        except Exception:
            pass

    return msg


def format_bus_messages(messages: list[AgentMessage], viewer_agent: str = "") -> str:
    """Format bus messages as a readable section for agent prompts."""
    if not messages:
        return ""
    relevant = [
        m for m in messages
        if not m.get("to_agent") or m.get("to_agent") == viewer_agent
    ]
    if not relevant:
        return ""
    lines = ["## Messages from other agents"]
    for m in relevant[-20:]:
        frm = m.get("from_agent", "?")
        mtype = m.get("message_type", "info")
        content = m.get("content", "")
        to = m.get("to_agent", "")
        addr = f"→ {to}" if to else "(broadcast)"
        lines.append(f"- [{mtype}] {frm} {addr}: {content}")
    return "\n".join(lines)
```

- [ ] **Step 2: Verify bus**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.bus import post, format_bus_messages
msg = post('architect', 'Auth uses JWT middleware', to_agent='coder', message_type='handoff')
formatted = format_bus_messages([msg], viewer_agent='coder')
assert 'JWT' in formatted
print('Bus OK:', msg['from_agent'], '->', msg['content'][:30])
"
```
Expected: `Bus OK: architect -> Auth uses JWT middleware`

- [ ] **Step 3: Commit**

```bash
git add ai_team/bus.py
git commit -m "feat: local agent-to-agent message bus with async queue support for Web UI"
```

---

### Task 4: Wire Bus into Agents

**Files:**
- Modify: `ai_team/agents/architect.py`
- Modify: `ai_team/agents/coder.py`
- Modify: `ai_team/agents/reviewer.py`

- [ ] **Step 1: Update `architect.py` — post handoff after approval**

In `architect_agent()`, replace the approved return block:

```python
    if approval.get("decision") == "approved":
        from ai_team.bus import post as bus_post
        bus_msg = bus_post(
            "architect",
            f"Architecture approved. Key decisions: {architecture[:400]}",
            message_type="handoff",
        )
        return {
            "architecture_spec": architecture,
            "phase": "code",
            "phase_rejections": 0,
            "agent_messages": [bus_msg],
            "messages": ["[Architect] Architecture approved by user."],
        }
```

- [ ] **Step 2: Update `coder.py` — read bus messages before coding**

In `coder_agent()`, after `project_context = state.get("project_context", "")`, add:

```python
    from ai_team.bus import format_bus_messages
    agent_messages = state.get("agent_messages", [])
    bus_context = format_bus_messages(agent_messages, viewer_agent="coder")
```

Then after the `if project_context:` block, add:

```python
    if bus_context:
        user_msg += f"\n\n{bus_context}\n"
```

- [ ] **Step 3: Update `reviewer.py` — post critical findings to bus**

In `reviewer_agent()`, replace the return statement:

```python
    from ai_team.bus import post as bus_post
    bus_msgs = []
    critical = [f for f in findings if f.get("severity") == "critical"]
    for f in critical[:3]:
        bus_msg = bus_post(
            "reviewer",
            f"Critical: {f.get('file','')}:{f.get('line','')} — {f.get('message','')}",
            to_agent="debugger",
            message_type="warning",
        )
        bus_msgs.append(bus_msg)
    return {
        "review_findings": findings,
        "agent_messages": bus_msgs,
        "messages": [f"[Reviewer] {len(findings)} findings."],
    }
```

- [ ] **Step 4: Verify**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.agents.architect import architect_agent
from ai_team.agents.coder import coder_agent
from ai_team.agents.reviewer import reviewer_agent
from ai_team.graph import build_graph
g = build_graph()
print('Bus wiring OK, graph nodes:', len(g.nodes))
"
```
Expected: nodes count unchanged (bus adds no new nodes).

- [ ] **Step 5: Commit**

```bash
git add ai_team/agents/architect.py ai_team/agents/coder.py ai_team/agents/reviewer.py
git commit -m "feat: wire agent-to-agent bus into architect/coder/reviewer"
```

---

## Phase 3: New Agents

### Task 5: Planner Agent

**Files:**
- Create: `ai_team/agents/planner.py`
- Modify: `ai_team/graph.py`
- Modify: `ai_team/agents/coder.py`

- [ ] **Step 1: Create `ai_team/agents/planner.py`**

```python
"""Planner Agent — Breaks architecture spec into ordered WorkItems for coder."""

from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from ai_team.agents.react_loop import invoke_llm_with_retry
from ai_team.bus import post as bus_post
from ai_team.config import get_llm_for_agent
from ai_team.state import WorkItem

logger = logging.getLogger("ai_team.agents.planner")

SYSTEM_PROMPT = """You are a Senior Engineering Lead. Break the architecture spec into
ordered, concrete implementation tasks for a developer.

Rules:
- Tasks must be in dependency order (no task can depend on a later task's output)
- Each task specifies exact files to create or modify
- One concern per task — don't mix model creation + endpoint + tests in one task
- Maximum 10 tasks

Output ONLY valid JSON — a list of objects, no markdown:
[
  {
    "id": "1",
    "description": "Create User model in app/models/user.py with fields: id, email, hashed_password, created_at",
    "files": ["app/models/user.py"],
    "status": "pending"
  }
]"""


def planner_agent(state: dict) -> dict:
    """Break architecture spec into ordered WorkItems."""
    llm = get_llm_for_agent("planner")
    architecture = state.get("architecture_spec", "")
    requirements = state.get("requirements_spec", "")
    project_dir = state.get("project_dir", "")
    codebase_index = state.get("codebase_index", "")

    user_msg = f"""Architecture Spec:
{architecture}

Requirements:
{requirements}

Project directory: {project_dir}

Existing codebase (files already present):
{codebase_index[:1500] if codebase_index else "(empty project)"}

Output ONLY the JSON array of tasks."""

    response = invoke_llm_with_retry(llm, [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_msg),
    ])

    work_items = _parse_work_items(response.content)
    summary = ", ".join(f"[{w['id']}] {w['description'][:50]}" for w in work_items[:4])
    bus_msg = bus_post("planner", f"Plan ready — {len(work_items)} tasks: {summary}", message_type="info")

    logger.info("Planner produced %d work items", len(work_items))
    return {
        "work_items": work_items,
        "agent_messages": [bus_msg],
        "messages": [f"[Planner] {len(work_items)} tasks planned."],
    }


def _parse_work_items(text: str) -> list[WorkItem]:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if not match:
        logger.warning("Planner produced no JSON array — using single fallback task")
        return [WorkItem(id="1", description=text[:200], status="pending", files=[])]
    try:
        raw = json.loads(match.group(0))
        return [
            WorkItem(
                id=str(item.get("id", i)),
                description=item.get("description", ""),
                status="pending",
                files=item.get("files", []),
            )
            for i, item in enumerate(raw, 1)
        ]
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse planner JSON: %s", e)
        return [WorkItem(id="1", description="Implement architecture spec", status="pending", files=[])]
```

- [ ] **Step 2: Wire planner into `graph.py`**

Add import:
```python
from ai_team.agents.planner import planner_agent
```

In `build_graph()`, add node:
```python
builder.add_node("planner", planner_agent)
```

Replace edge `preflight → coder`:
```python
# Remove: builder.add_edge("preflight", "coder")
# Add:
builder.add_edge("preflight", "planner")
builder.add_edge("planner", "coder")
```

- [ ] **Step 3: Update `coder.py` to display work items**

In `coder_agent()`, after `iteration = state.get("iteration", 0)`, add:
```python
    work_items = state.get("work_items", [])
    pending_items = [w for w in work_items if w.get("status") == "pending"]
```

In the non-fix `user_msg` block, after the Architecture Spec section, add:
```python
    if pending_items:
        items_text = "\n".join(
            f"  [{w['id']}] {w['description']} (files: {', '.join(w.get('files', []))})"
            for w in pending_items[:5]
        )
        user_msg += f"\n\n## Work Items (implement ALL):\n{items_text}\n"
```

- [ ] **Step 4: Verify 16 nodes**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.graph import build_graph
g = build_graph()
assert len(g.nodes) == 16, f'Expected 16, got {len(g.nodes)}'
assert 'planner' in g.nodes
print('OK — 16 nodes:', list(g.nodes))
"
```

- [ ] **Step 5: Smoke tests**

```bash
make test
```

- [ ] **Step 6: Commit**

```bash
git add ai_team/agents/planner.py ai_team/graph.py ai_team/agents/coder.py
git commit -m "feat: planner agent — ordered WorkItems before coder runs"
```

---

### Task 6: Debugger Agent

**Files:**
- Create: `ai_team/agents/debugger.py`
- Modify: `ai_team/graph.py`
- Modify: `ai_team/agents/coder.py`

- [ ] **Step 1: Create `ai_team/agents/debugger.py`**

```python
"""Debugger Agent — Root cause analysis before handing back to coder."""

from __future__ import annotations

import logging

from ai_team.agents.react_loop import react_loop
from ai_team.bus import format_bus_messages, post as bus_post
from ai_team.config import get_llm_for_agent

logger = logging.getLogger("ai_team.agents.debugger")

SYSTEM_PROMPT = """You are a Principal Engineer specialising in root cause analysis.

You receive failing test output, code review findings, and security issues.
Your job is NOT to fix the code — identify WHY it is broken so the coder
can fix it with minimal effort.

For each critical/warn finding:
1. Read the source file at the reported line
2. Trace the call chain if needed
3. Identify the exact root cause (not symptoms)
4. Write a one-paragraph fix prescription

Output:

## Root Cause Analysis

### Issue 1: [short title]
**File:** path/to/file.py:line
**Root Cause:** precise explanation of what is wrong
**Fix:** exact prescription — which function/variable to change and how

If all findings are false positives, output:
## Root Cause Analysis
No real issues found."""


def debugger_agent(state: dict) -> dict:
    """Analyse failures and produce a root cause report for the coder."""
    llm = get_llm_for_agent("debugger")
    review = state.get("review_findings", [])
    tests = state.get("test_results", [])
    security = state.get("security_findings", [])
    project_dir = state.get("project_dir", "")
    agent_messages = state.get("agent_messages", [])

    all_findings = review + tests + security
    critical_or_warn = [f for f in all_findings if f.get("severity") in ("critical", "warn")]

    if not critical_or_warn:
        msg = bus_post("debugger", "No critical/warn findings — skipping.", message_type="info")
        return {
            "debugger_report": "No issues requiring root cause analysis.",
            "agent_messages": [msg],
            "messages": ["[Debugger] No issues to analyse."],
        }

    bus_context = format_bus_messages(agent_messages, viewer_agent="debugger")
    findings_text = "\n".join(
        f"[{f.get('severity')}] {f.get('agent','?')} — "
        f"{f.get('file','')}:{f.get('line','')} — {f.get('message','')}"
        for f in critical_or_warn
    )

    user_msg = f"""Project directory: {project_dir}

Critical/Warn findings:
{findings_text}
"""
    if bus_context:
        user_msg += f"\n{bus_context}\n"
    user_msg += """
Instructions:
1. Use search_codebase to find relevant code sections
2. Read files at the reported lines
3. Trace calls as needed
4. Produce Root Cause Analysis report"""

    response, _ = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=15,
        agent_name="debugger",
    )

    bus_msg = bus_post(
        "debugger",
        f"Root cause analysis complete — {len(critical_or_warn)} issues diagnosed",
        to_agent="coder",
        message_type="handoff",
    )
    return {
        "debugger_report": response.content,
        "agent_messages": [bus_msg],
        "messages": [f"[Debugger] Root cause analysis: {len(critical_or_warn)} issues."],
    }
```

- [ ] **Step 2: Wire debugger into `graph.py`**

Add import:
```python
from ai_team.agents.debugger import debugger_agent
```

Add node:
```python
builder.add_node("debugger", debugger_agent)
```

Change verification fan-out downstream (reviewer/tester/security → debugger → evaluator):
```python
# Replace the three direct edges to evaluator:
# builder.add_edge("reviewer", "evaluator")
# builder.add_edge("tester", "evaluator")
# builder.add_edge("security", "evaluator")
# With:
builder.add_edge("reviewer", "debugger")
builder.add_edge("tester", "debugger")
builder.add_edge("security", "debugger")
builder.add_edge("debugger", "evaluator")
```

- [ ] **Step 3: Update `coder.py` — use debugger_report in fix iterations**

In `coder_agent()`, after `is_fix_iteration = ...`, add:
```python
    debugger_report = state.get("debugger_report", "")
```

In the fix iteration `user_msg` block, after the header, add:
```python
    if debugger_report and "No issues" not in debugger_report:
        user_msg += f"\n## Root Cause Analysis (Debugger):\n{debugger_report}\n"
        user_msg += "\nFix EXACTLY what the debugger identified. Do not touch other code.\n"
```

- [ ] **Step 4: Verify 17 nodes**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.graph import build_graph
g = build_graph()
assert len(g.nodes) == 17, f'Expected 17, got {len(g.nodes)}'
assert 'debugger' in g.nodes
print('OK — 17 nodes')
"
```

- [ ] **Step 5: Smoke tests**

```bash
make test
```

- [ ] **Step 6: Commit**

```bash
git add ai_team/agents/debugger.py ai_team/graph.py ai_team/agents/coder.py
git commit -m "feat: debugger agent — root cause analysis between verification and coder"
```

---

### Task 7: Docs Agent

**Files:**
- Create: `ai_team/agents/docs.py`
- Modify: `ai_team/graph.py`

Pipeline: `learn_lessons → docs → ci_check`

- [ ] **Step 1: Create `ai_team/agents/docs.py`**

```python
"""Docs Agent — Updates docstrings and README based on code changes."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ai_team.agents.react_loop import react_loop
from ai_team.bus import post as bus_post
from ai_team.config import get_llm_for_agent

logger = logging.getLogger("ai_team.agents.docs")

SYSTEM_PROMPT = """You are a Technical Writer. You update documentation to reflect code changes.

Rules:
- ONLY write or update documentation — never change logic or tests
- Add/update docstrings for new or modified public functions, classes, and endpoints
- Update README.md if there is a new endpoint or user-facing feature
- Do NOT document private functions (starting with _)
- Keep docstrings concise: one-line summary + Args + Returns only if non-obvious

Python docstring format (Google style):
    def function(arg: str) -> str:
        \"\"\"One-line summary.

        Args:
            arg: What this argument is.

        Returns:
            What this returns.
        \"\"\"

After writing docs, summarise what you documented."""


def docs_agent(state: dict) -> dict:
    """Write/update docs for changed public APIs."""
    llm = get_llm_for_agent("docs")
    code_changes = state.get("code_changes", [])
    project_dir = state.get("project_dir", "")
    git_diff = state.get("git_diff", "")

    if not code_changes:
        return {
            "docs_output": "No files changed — nothing to document.",
            "messages": ["[Docs] No changed files, skipping."],
        }

    if not git_diff and project_dir and Path(project_dir).joinpath(".git").exists():
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD~1", "--", "*.py"],
                cwd=project_dir, capture_output=True, text=True, timeout=15,
            )
            git_diff = result.stdout[:8000] if result.stdout else ""
        except Exception:
            pass

    user_msg = f"""Changed files:
{chr(10).join(code_changes)}

Project directory: {project_dir}

Git diff (Python files):
{git_diff[:5000] if git_diff else "(no diff — read files directly)"}

Instructions:
1. Read each changed file
2. Identify new or modified public functions/classes/endpoints
3. Add/update their docstrings
4. Update README.md if there is a new endpoint or user-facing change
5. Report what you documented"""

    response, changed_docs = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        max_iterations=12,
        agent_name="docs",
    )

    bus_msg = bus_post("docs", f"Documentation updated for {len(changed_docs)} files", message_type="info")
    return {
        "docs_output": response.content,
        "agent_messages": [bus_msg],
        "messages": [f"[Docs] Updated documentation in {len(changed_docs)} files."],
    }
```

- [ ] **Step 2: Wire docs into `graph.py`**

Add import:
```python
from ai_team.agents.docs import docs_agent
```

Add node:
```python
builder.add_node("docs", docs_agent)
```

Replace edge:
```python
# Remove: builder.add_edge("learn_lessons", "ci_check")
# Add:
builder.add_edge("learn_lessons", "docs")
builder.add_edge("docs", "ci_check")
```

- [ ] **Step 3: Verify 18 nodes**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.graph import build_graph
g = build_graph()
assert len(g.nodes) == 18, f'Expected 18, got {len(g.nodes)}'
assert 'docs' in g.nodes
print('OK — 18 nodes:', list(g.nodes))
"
```

- [ ] **Step 4: Smoke tests + commit**

```bash
make test
git add ai_team/agents/docs.py ai_team/graph.py
git commit -m "feat: docs agent — auto-updates docstrings and README after each ship"
```

---

## Phase 4: Intelligence

### Task 8: RAG-Aware Reviewer

**Files:**
- Modify: `ai_team/agents/reviewer.py`

- [ ] **Step 1: Replace `SYSTEM_PROMPT` in `reviewer.py`**

```python
SYSTEM_PROMPT = """You are a Senior Tech Lead performing a thorough code review.

Start by using search_codebase to find project-specific patterns:
- Existing tests for changed modules: query "tests for <module_name>"
- Similar existing patterns: query "how is <feature> implemented"
- Error handling conventions: query "error handling middleware"
- Auth patterns (if endpoints changed): query "auth decorator authentication"

Then review every changed file against BOTH generic standards AND the project's own patterns:

1. **Correctness** — Does the code do what the spec says? Logic errors?
2. **Pattern conformance** — Does it match how THIS project does similar things?
3. **Error handling** — Are API boundaries validated? DB errors caught?
4. **Performance** — N+1 queries? Unnecessary loops?
5. **Test coverage** — Are there tests for the new code?
6. **Edge cases** — Empty inputs? Null values?

For each finding (one per line):
{"severity": "critical|warn|info", "file": "path", "line": 123, "message": "description"}

If the code is good:
{"severity": "pass", "file": "", "line": 0, "message": "Code review passed."}

Cite the project pattern you compared against when flagging violations."""
```

- [ ] **Step 2: Update `user_msg` in `reviewer_agent()`**

```python
    user_msg = f"""Review these changed files:
{chr(10).join(code_changes)}

Architecture spec:
{architecture}

Project directory: {project_dir}

Instructions:
1. Use search_codebase to find relevant tests, patterns, and conventions for these files
2. Read each changed file carefully
3. Compare against the project's own patterns (not just generic best practices)
4. Output findings in JSON format"""
```

- [ ] **Step 3: Verify**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.agents.reviewer import SYSTEM_PROMPT
assert 'search_codebase' in SYSTEM_PROMPT
print('RAG reviewer OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add ai_team/agents/reviewer.py
git commit -m "feat: RAG-aware reviewer — searches project patterns before reviewing"
```

---

### Task 9: Self-Healing Import Node

**Files:**
- Create: `ai_team/agents/import_healer.py`
- Modify: `ai_team/graph.py`

- [ ] **Step 1: Create `ai_team/agents/import_healer.py`**

```python
"""Import Healer — auto-installs missing packages when tests report ImportError."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from ai_team.bus import post as bus_post

logger = logging.getLogger("ai_team.agents.import_healer")

SAFE_PACKAGES = {
    "requests", "httpx", "aiohttp", "fastapi", "uvicorn", "pydantic",
    "sqlalchemy", "alembic", "psycopg2", "asyncpg", "redis", "celery",
    "pytest", "pytest-asyncio", "pytest-cov", "anyio",
    "python-jose", "passlib", "bcrypt", "cryptography",
    "pillow", "boto3", "stripe", "sendgrid", "twilio",
    "pandas", "numpy", "scipy", "scikit-learn",
    "langchain", "langchain-core", "langchain-openai", "langchain-anthropic",
    "openai", "anthropic", "tiktoken",
    "rich", "typer", "click", "python-dotenv",
}

_MODULE_TO_PACKAGE = {
    "PIL": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "jose": "python-jose[cryptography]",
    "passlib": "passlib[bcrypt]",
    "dotenv": "python-dotenv",
    "psycopg2": "psycopg2-binary",
}


def _extract_missing_module(error_message: str) -> str | None:
    patterns = [
        r"No module named '([^']+)'",
        r"ModuleNotFoundError: No module named '([^']+)'",
    ]
    for pat in patterns:
        m = re.search(pat, error_message)
        if m:
            return m.group(1).split(".")[0]
    return None


def _find_venv_pip(project_dir: str) -> str | None:
    for candidate in [".venv/bin/pip", "venv/bin/pip", ".env/bin/pip"]:
        pip_path = Path(project_dir) / candidate
        if pip_path.exists():
            return str(pip_path)
    return None


def import_healer_node(state: dict) -> dict:
    """Check test results for ImportErrors and auto-install missing packages."""
    test_results = state.get("test_results", [])
    project_dir = state.get("project_dir", "")

    import_errors = [
        f for f in test_results
        if f.get("severity") == "critical"
        and any(kw in f.get("message", "") for kw in ["ImportError", "ModuleNotFoundError", "No module named"])
    ]

    if not import_errors:
        return {"messages": ["[ImportHealer] No import errors detected."]}

    pip = _find_venv_pip(project_dir)
    if not pip:
        return {"messages": ["[ImportHealer] No venv pip found, cannot auto-install."]}

    installed = []
    failed = []

    for finding in import_errors:
        module = _extract_missing_module(finding.get("message", ""))
        if not module:
            continue
        package = _MODULE_TO_PACKAGE.get(module, module.replace("_", "-"))
        top_package = package.split("[")[0]
        if top_package not in SAFE_PACKAGES:
            failed.append(package)
            continue
        try:
            result = subprocess.run(
                [pip, "install", package, "--quiet"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                installed.append(package)
            else:
                failed.append(package)
        except Exception as e:
            logger.error("pip install error: %s", e)
            failed.append(package)

    msgs = []
    bus_msgs = []
    if installed:
        bus_msg = bus_post("import_healer", f"Auto-installed: {', '.join(installed)}", message_type="info")
        bus_msgs.append(bus_msg)
        msgs.append(f"[ImportHealer] Installed: {', '.join(installed)}")
    if failed:
        msgs.append(f"[ImportHealer] Could not auto-install: {', '.join(failed)}")
    if not msgs:
        msgs.append("[ImportHealer] No actionable import errors.")

    return {"agent_messages": bus_msgs, "messages": msgs}
```

- [ ] **Step 2: Wire import_healer into `graph.py` between fan-out and debugger**

Add import:
```python
from ai_team.agents.import_healer import import_healer_node
```

Add node:
```python
builder.add_node("import_healer", import_healer_node)
```

Change routing (fan-out → import_healer → debugger → evaluator):
```python
# Replace:
# builder.add_edge("reviewer", "debugger")
# builder.add_edge("tester", "debugger")
# builder.add_edge("security", "debugger")
# With:
builder.add_edge("reviewer", "import_healer")
builder.add_edge("tester", "import_healer")
builder.add_edge("security", "import_healer")
builder.add_edge("import_healer", "debugger")
```

- [ ] **Step 3: Verify 19 nodes**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.graph import build_graph
g = build_graph()
assert len(g.nodes) == 19, f'Expected 19, got {len(g.nodes)}'
assert 'import_healer' in g.nodes
print('OK — 19 nodes:', list(g.nodes))
"
```

- [ ] **Step 4: Smoke tests + commit**

```bash
make test
git add ai_team/agents/import_healer.py ai_team/graph.py
git commit -m "feat: import_healer node — auto-installs missing packages from test ImportErrors"
```

---

### Task 10: GitHub PR Auto-Open

**Files:**
- Modify: `ai_team/graph.py`
- Modify: `run.py`

- [ ] **Step 1: Add `import shutil` to `graph.py` imports**

In `graph.py` at the top with the other stdlib imports:
```python
import shutil
```

- [ ] **Step 2: Add `_open_github_pr()` helper in `graph.py`**

Add before `human_final_review()`:

```python
def _open_github_pr(project_dir: str, task: str, evaluation: str) -> str:
    """Push current branch and open a GitHub PR via gh CLI. Returns PR URL or ''."""
    if not shutil.which("gh"):
        logger.info("gh CLI not found — skipping PR creation")
        return ""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=project_dir, capture_output=True, text=True, timeout=5,
        )
        branch = result.stdout.strip()
        if not branch or branch in ("main", "master"):
            return ""
        subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=project_dir, capture_output=True, timeout=30,
        )
        body = f"## Summary\n\nTask: {task}\n\n## Evaluation\n\n{evaluation[:2000]}\n\n---\n*Auto-opened by AI Dev Team*"
        result = subprocess.run(
            ["gh", "pr", "create", "--title", task[:70], "--body", body, "--head", branch],
            cwd=project_dir, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            pr_url = result.stdout.strip()
            logger.info("PR opened: %s", pr_url)
            return pr_url
        logger.warning("gh pr create failed: %s", result.stderr[:200])
        return ""
    except Exception as e:
        logger.warning("PR creation failed: %s", e)
        return ""
```

- [ ] **Step 3: Call `_open_github_pr()` in `human_final_review()` after approval**

In `human_final_review()`, replace the approved return with:

```python
    if approval.get("decision") == "approved":
        pr_url = _open_github_pr(
            project_dir=project_dir,
            task=state.get("task", "AI Dev Team task"),
            evaluation=state.get("evaluation", ""),
        )
        return {
            "phase": "done",
            "git_diff": diff_text,
            "pr_url": pr_url,
            "messages": [f"[Ship] User approved. PR: {pr_url or 'not created'}."],
        }
```

- [ ] **Step 4: Show PR URL in `run.py` summary**

In `_build_summary()`, after the `iterations` line, add:
```python
    pr_url = values.get("pr_url", "")
    if pr_url:
        lines.append(f"\n**PR:** {pr_url}")
```

- [ ] **Step 5: Verify**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.graph import _open_github_pr
print('PR helper importable OK')
"
```

- [ ] **Step 6: Commit**

```bash
git add ai_team/graph.py run.py
git commit -m "feat: auto-open GitHub PR after final approval via gh CLI"
```

---

## Phase 5: Web UI

### Task 11: FastAPI + WebSocket Live Dashboard

**Files:**
- Create: `ai_team/web/__init__.py`
- Create: `ai_team/web/app.py`
- Modify: `requirements.txt`
- Modify: `Makefile`

- [ ] **Step 1: Install dependencies**

```bash
cd /home/basitdev/Me/ai-dev-team
.venv/bin/pip install "fastapi>=0.115.0" "uvicorn[standard]>=0.30.0" "websockets>=13.0"
```

- [ ] **Step 2: Add to `requirements.txt`** (under `# Core (always needed)`):

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
websockets>=13.0
```

- [ ] **Step 3: Create `ai_team/web/__init__.py`** (empty file):

```python
```

- [ ] **Step 4: Create `ai_team/web/app.py`**

```python
"""FastAPI Web UI — live agent activity dashboard."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from ai_team.bus import get_event_history, register_async_queue, unregister_async_queue

logger = logging.getLogger("ai_team.web")

app = FastAPI(title="AI Dev Team Dashboard")


@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    """Stream all agent bus events to connected browsers."""
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue()
    register_async_queue(q)
    try:
        for msg in get_event_history():
            await ws.send_text(json.dumps(msg))
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
                await ws.send_text(json.dumps(msg))
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({"ping": True}))
    except WebSocketDisconnect:
        pass
    finally:
        unregister_async_queue(q)


@app.get("/api/history")
def get_history():
    return get_event_history()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _build_dashboard_html()


def _build_dashboard_html() -> str:
    """Build the dashboard HTML. Uses safe DOM methods — no innerHTML with untrusted data."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Dev Team</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'SF Mono','Fira Code',monospace;background:#0d1117;color:#c9d1d9}
  header{background:#161b22;border-bottom:1px solid #30363d;padding:12px 20px;display:flex;align-items:center;gap:12px}
  header h1{font-size:1rem;color:#58a6ff}
  #status{font-size:.75rem;padding:2px 8px;border-radius:12px;background:#21262d}
  #status.connected{background:#1a3a2a;color:#3fb950}
  #status.disconnected{background:#3a1a1a;color:#f85149}
  main{display:grid;grid-template-columns:200px 1fr;height:calc(100vh - 45px)}
  aside{background:#161b22;border-right:1px solid #30363d;padding:12px;overflow-y:auto}
  aside h2{font-size:.7rem;text-transform:uppercase;color:#8b949e;margin-bottom:8px;letter-spacing:.08em}
  .agent-pill{padding:4px 10px;border-radius:4px;font-size:.75rem;margin-bottom:4px;cursor:pointer}
  .agent-pill.active,.agent-pill:hover{background:#21262d}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:#30363d}
  .agent-pill.active .dot{background:#3fb950}
  #feed{padding:16px;overflow-y:auto;display:flex;flex-direction:column;gap:6px}
  .event{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:10px 14px;font-size:.8rem}
  .event.handoff{border-color:#388bfd44}
  .event.warning{border-color:#f8514966}
  .event-header{display:flex;gap:8px;align-items:center;margin-bottom:4px}
  .from{font-weight:600;color:#58a6ff}
  .arrow{color:#484f58}
  .badge{font-size:.65rem;padding:1px 6px;border-radius:10px;background:#21262d;color:#8b949e}
  .badge.handoff{background:#1c2a3a;color:#388bfd}
  .badge.warning{background:#3a1a1a;color:#f85149}
  .content{color:#c9d1d9;line-height:1.4}
  .ts{color:#484f58;font-size:.65rem;margin-left:auto}
  #clear-btn{background:none;border:1px solid #30363d;color:#8b949e;padding:2px 8px;border-radius:4px;cursor:pointer;font-size:.7rem;margin-left:auto}
</style>
</head>
<body>
<header>
  <h1>AI Dev Team</h1>
  <span id="status" class="disconnected">disconnected</span>
  <button id="clear-btn">Clear</button>
</header>
<main>
  <aside><h2>Agents</h2><div id="agents"></div></aside>
  <div id="feed"></div>
</main>
<script>
const feed=document.getElementById('feed');
const statusEl=document.getElementById('status');
const agentsEl=document.getElementById('agents');
const knownAgents=new Set();
let activeFilter=null;
let allEvents=[];
const AGENT_COLORS={architect:'#388bfd',coder:'#3fb950',reviewer:'#d29922',tester:'#bc8cff',security:'#f85149',planner:'#58a6ff',debugger:'#ff7b72',docs:'#79c0ff',evaluator:'#ffa657',requirements:'#56d364',designer:'#ff9bce',import_healer:'#d2a8ff'};
function agentColor(n){return AGENT_COLORS[n]||'#8b949e'}

document.getElementById('clear-btn').addEventListener('click',()=>{
  feed.replaceChildren();
});

function updateAgentPill(name){
  if(knownAgents.has(name))return;
  knownAgents.add(name);
  const pill=document.createElement('div');
  pill.className='agent-pill';
  pill.dataset.agent=name;
  const dot=document.createElement('span');
  dot.className='dot';
  dot.style.background=agentColor(name);
  const label=document.createTextNode(name);
  pill.appendChild(dot);
  pill.appendChild(label);
  pill.addEventListener('click',()=>{
    activeFilter=activeFilter===name?null:name;
    document.querySelectorAll('.agent-pill').forEach(p=>p.classList.toggle('active',p.dataset.agent===activeFilter));
    renderFeed();
  });
  agentsEl.appendChild(pill);
}

function renderFeed(){
  const events=activeFilter?allEvents.filter(e=>e.from_agent===activeFilter||e.to_agent===activeFilter):allEvents;
  feed.replaceChildren();
  events.slice(-150).forEach(appendEvent);
  feed.scrollTop=feed.scrollHeight;
}

function appendEvent(msg){
  if(msg.ping)return;
  const mtype=msg.message_type||'info';
  const ts=msg.timestamp?new Date(msg.timestamp).toLocaleTimeString():'';

  const div=document.createElement('div');
  div.className='event '+mtype;

  const hdr=document.createElement('div');
  hdr.className='event-header';

  const from=document.createElement('span');
  from.className='from';
  from.style.color=agentColor(msg.from_agent);
  from.textContent=msg.from_agent||'?';
  hdr.appendChild(from);

  const arrow=document.createElement('span');
  arrow.className='arrow';
  arrow.textContent=msg.to_agent?'→':'⬡';
  hdr.appendChild(arrow);

  if(msg.to_agent){
    const to=document.createElement('span');
    to.style.color='#d2a8ff';
    to.textContent=msg.to_agent;
    hdr.appendChild(to);
  }

  const badge=document.createElement('span');
  badge.className='badge '+mtype;
  badge.textContent=mtype;
  hdr.appendChild(badge);

  const tsEl=document.createElement('span');
  tsEl.className='ts';
  tsEl.textContent=ts;
  hdr.appendChild(tsEl);

  div.appendChild(hdr);

  const content=document.createElement('div');
  content.className='content';
  content.textContent=msg.content||'';
  div.appendChild(content);

  feed.appendChild(div);
}

function connect(){
  const ws=new WebSocket('ws://'+location.host+'/ws/events');
  ws.onopen=()=>{statusEl.textContent='connected';statusEl.className='connected'};
  ws.onclose=()=>{statusEl.textContent='reconnecting…';statusEl.className='disconnected';setTimeout(connect,2000)};
  ws.onmessage=e=>{
    const msg=JSON.parse(e.data);
    if(msg.ping)return;
    allEvents.push(msg);
    if(allEvents.length>500)allEvents=allEvents.slice(-500);
    updateAgentPill(msg.from_agent);
    if(!activeFilter||msg.from_agent===activeFilter||msg.to_agent===activeFilter){
      appendEvent(msg);
      feed.scrollTop=feed.scrollHeight;
    }
  };
}
connect();
</script>
</body>
</html>"""
```

Note: all DOM manipulation uses `textContent` and `document.createElement` — no `innerHTML` with dynamic data.

- [ ] **Step 5: Add `web` target to `Makefile`**

Add to `.PHONY` line: `web`

Add before `clean`:
```makefile
web: ## Start live Web UI dashboard on port 7788
	@source $(VENV)/bin/activate && uvicorn ai_team.web.app:app --host 0.0.0.0 --port 7788 --reload
```

- [ ] **Step 6: Verify web app**

```bash
PYTHONPATH=. .venv/bin/python -c "
from ai_team.web.app import app, dashboard
routes = [r.path for r in app.routes]
assert '/ws/events' in routes
assert '/api/history' in routes
assert '/' in routes
print('Web app OK. Routes:', routes)
"
```
Expected: `Web app OK. Routes: ['/ws/events', '/api/history', '/api/health', '/']`

- [ ] **Step 7: Full smoke tests**

```bash
make test
```
Expected: `ALL TESTS PASSED`

- [ ] **Step 8: Commit**

```bash
git add ai_team/web/ requirements.txt Makefile
git commit -m "feat: FastAPI+WebSocket live dashboard at :7788 — streams all agent bus events"
```

---

## Self-Review

**Spec coverage:**
1. ✅ Planner agent (Task 5)
2. ✅ Debugger agent (Task 6)
3. ✅ Docs agent (Task 7)
4. ✅ Per-agent model routing (Task 1)
5. ✅ Local agent-to-agent chat bus (Tasks 3-4)
6. ✅ Self-healing imports (Task 9)
7. ✅ RAG-aware reviewer (Task 8)
8. ✅ GitHub PR auto-open (Task 10)
9. ✅ Structured work items (Task 2 state + Task 5 planner + Task 5 coder update)
10. ✅ Web UI (Task 11)

**Node progression:** 15 → 16 (planner) → 17 (debugger) → 18 (docs) → 19 (import_healer) = **19 final nodes**

**Type consistency:** `AgentMessage` defined in Task 2 (`state.py`), used in Task 3 (`bus.py`). `get_llm_for_agent` defined Task 1, called in Tasks 5/6/7. `WorkItem` exists in `state.py`, `_replace_work_items` reducer added Task 2, populated Task 5.

**Security:** Web UI uses `textContent` / `createElement` exclusively — no `innerHTML` with dynamic data.

**Placeholder scan:** All code blocks are complete and executable.
