# AI Dev Team — Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 specialist agents (frontend-web, frontend-mobile, frontend-desktop, auditor), split coder by target, upgrade the dashboard from a log stream to a split-view team workspace with intervention controls (pause/redirect/skip/abort).

**Architecture:** New agents follow the exact same pattern as existing ones (`react_loop` + `get_llm_for_agent` + system prompt). The graph gets a frontend routing branch after `planner`. The bus gets persistent SQLite logging. The dashboard gets rebuilt as a split-view HTML page served by FastAPI — DOM manipulation uses safe `textContent`/`createElement` only (no `innerHTML`).

**Tech Stack:** Python 3.11, LangGraph, FastAPI, SQLite, WebSocket, vanilla JS (no framework — dashboard is a single HTML file served by FastAPI)

---

## File Map

### New files
- `ai_team/agents/frontend_web.py` — React/Next.js/TypeScript specialist coder
- `ai_team/agents/frontend_mobile.py` — Android Kotlin / Jetpack Compose specialist coder
- `ai_team/agents/frontend_desktop.py` — Tauri + React + Rust IPC specialist coder
- `ai_team/agents/auditor.py` — Code quality, architecture drift, tech debt auditor

### Modified files
- `ai_team/agents/project_detector.py` — Add `detect_frontend_target()` (reads `tauri.conf.json`, `build.gradle.kts`, `package.json`)
- `ai_team/state.py` — Add `frontend_target`, `audit_findings`, `paused`, `inject_message`, `skip_current`, `abort`
- `ai_team/bus.py` — Add SQLite persistence (`_persist`, `load_thread`) and `thread_id` tracking
- `ai_team/graph.py` — Add `frontend_router_node`, conditional edges, auditor in parallel review block, `_check_intervention` helper
- `ai_team/config.py` — Add `AGENT_MODEL_FRONTEND_WEB/MOBILE/DESKTOP/AUDITOR` env var lookups
- `ai_team/web/app.py` — Full rewrite: split-view dashboard, REST control endpoints, two WebSocket streams
- `.env.example` — Add new `AGENT_MODEL_*` and `FRONTEND_TARGET` vars
- `run.py` — Add `--target` CLI flag

---

## Task 1: Add new fields to State

**Files:**
- Modify: `ai_team/state.py`

- [ ] **Step 1: Add fields to the State TypedDict**

In `ai_team/state.py`, add these fields inside `class State(TypedDict, total=False):` after `human_feedback`:

```python
# Frontend routing
frontend_target: str  # "backend" | "web" | "mobile" | "desktop"

# Auditor output
audit_findings: Annotated[list[AgentFinding], operator.add]

# Dashboard intervention controls
paused: bool
inject_message: str
skip_current: bool
abort: bool
```

- [ ] **Step 2: Verify import**

```bash
cd /path/to/ai-dev-team && python -c "from ai_team.state import State; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add ai_team/state.py
git commit -m "feat(state): add frontend_target, audit_findings, intervention control fields"
```

---

## Task 2: Upgrade bus.py — SQLite persistence

**Files:**
- Modify: `ai_team/bus.py`

- [ ] **Step 1: Replace bus.py with persistent version**

```python
"""In-process agent-to-agent pub/sub chat bus with SQLite persistence."""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

logger = logging.getLogger("ai_team.bus")

_DB_PATH = Path.home() / ".ai-dev-team" / "bus.db"


def _ensure_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                to_role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.commit()


class AgentBus:
    """Thread-safe in-process pub/sub message bus with SQLite persistence."""

    def __init__(self) -> None:
        self._messages: list[dict] = []
        self._cursors: dict[str, int] = defaultdict(int)
        self._lock = Lock()
        self._thread_id: str = ""
        _ensure_db(_DB_PATH)

    def set_thread(self, thread_id: str) -> None:
        self._thread_id = thread_id

    def publish(self, from_role: str, content: str, to_role: str = "all") -> None:
        msg: dict = {
            "role": from_role,
            "to": to_role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._messages.append(msg)
        self._persist(msg)
        logger.debug("[bus] %s -> %s: %s", from_role, to_role, content[:80])

    def _persist(self, msg: dict) -> None:
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO messages (thread_id, role, to_role, content, timestamp) VALUES (?,?,?,?,?)",
                    (self._thread_id, msg["role"], msg["to"], msg["content"], msg["timestamp"]),
                )
                conn.commit()
        except Exception as e:
            logger.warning("Bus persist error: %s", e)

    def load_thread(self, thread_id: str) -> None:
        """Load all messages for a thread into memory (called on dashboard connect)."""
        try:
            with sqlite3.connect(_DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT role, to_role, content, timestamp FROM messages WHERE thread_id=? ORDER BY id",
                    (thread_id,),
                ).fetchall()
            with self._lock:
                self._messages = [
                    {"role": r[0], "to": r[1], "content": r[2], "timestamp": r[3]}
                    for r in rows
                ]
        except Exception as e:
            logger.warning("Bus load error: %s", e)

    def consume(self, role: str) -> list[dict]:
        with self._lock:
            cursor = self._cursors[role]
            pending = [
                m for m in self._messages[cursor:]
                if m["to"] in (role, "all") and m["role"] != role
            ]
            self._cursors[role] = len(self._messages)
        return pending

    def all_messages(self) -> list[dict]:
        with self._lock:
            return list(self._messages)

    def as_state_messages(self) -> list[dict]:
        with self._lock:
            return [
                {"role": m["role"], "content": m["content"], "timestamp": m["timestamp"]}
                for m in self._messages
            ]

    def reset(self) -> None:
        with self._lock:
            self._messages.clear()
            self._cursors.clear()


bus = AgentBus()
```

- [ ] **Step 2: Verify bus works and DB is created**

```bash
cd /path/to/ai-dev-team && python -c "
from ai_team.bus import bus
bus.publish('test', 'hello')
msgs = bus.all_messages()
assert len(msgs) == 1
assert msgs[0]['content'] == 'hello'
print('bus ok')
"
```

Expected: `bus ok`

```bash
ls ~/.ai-dev-team/bus.db
```

Expected: file exists

- [ ] **Step 3: Commit**

```bash
git add ai_team/bus.py
git commit -m "feat(bus): add SQLite persistence and thread tracking"
```

---

## Task 3: Add frontend target detection to project_detector.py

**Files:**
- Modify: `ai_team/agents/project_detector.py`

- [ ] **Step 1: Add detect_frontend_target function**

Add this function in `ai_team/agents/project_detector.py` just before the `_find_file` helper at the bottom:

```python
def detect_frontend_target(project_dir: str, override: str | None = None) -> str:
    """Return 'web' | 'mobile' | 'desktop' | 'backend'.

    Priority: explicit override > tauri.conf.json/Cargo.toml(tauri) > build.gradle.kts > package.json(react/next) > backend.
    """
    if override and override in ("web", "mobile", "desktop", "backend"):
        return override

    root = Path(project_dir).expanduser().resolve()

    if _find_file(root, "tauri.conf.json"):
        return "desktop"

    cargo = _find_file(root, "Cargo.toml")
    if cargo:
        try:
            if "tauri" in cargo.read_text(encoding="utf-8").lower():
                return "desktop"
        except Exception:
            pass

    if _find_file(root, "build.gradle.kts") or _find_file(root, "AndroidManifest.xml"):
        return "mobile"

    pkg = _find_file(root, "package.json")
    if pkg:
        try:
            content = pkg.read_text(encoding="utf-8").lower()
            if any(kw in content for kw in ("react", "next", "vue", "svelte", "vite")):
                return "web"
        except Exception:
            pass

    return "backend"
```

- [ ] **Step 2: Write and run tests**

Create `tests/test_frontend_detector.py`:

```python
import tempfile
from pathlib import Path
from ai_team.agents.project_detector import detect_frontend_target


def test_detects_tauri():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "tauri.conf.json").write_text("{}")
        assert detect_frontend_target(d) == "desktop"


def test_detects_android():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "build.gradle.kts").write_text("")
        assert detect_frontend_target(d) == "mobile"


def test_detects_react():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "package.json").write_text('{"dependencies":{"react":"18"}}')
        assert detect_frontend_target(d) == "web"


def test_override_wins():
    with tempfile.TemporaryDirectory() as d:
        Path(d, "tauri.conf.json").write_text("{}")
        assert detect_frontend_target(d, override="mobile") == "mobile"


def test_default_backend():
    with tempfile.TemporaryDirectory() as d:
        assert detect_frontend_target(d) == "backend"
```

```bash
cd /path/to/ai-dev-team && python -m pytest tests/test_frontend_detector.py -v
```

Expected: 5 passed

- [ ] **Step 3: Commit**

```bash
git add ai_team/agents/project_detector.py tests/test_frontend_detector.py
git commit -m "feat(detector): add detect_frontend_target() with tauri/mobile/web/backend detection"
```

---

## Task 4: Add frontend_web.py agent

**Files:**
- Create: `ai_team/agents/frontend_web.py`

- [ ] **Step 1: Create the file**

```python
"""Frontend Web Agent — React / Next.js / TypeScript specialist."""

from __future__ import annotations

from ai_team.agents.react_loop import react_loop
from ai_team.config import get_llm_for_agent

SYSTEM_PROMPT = """You are a Senior Frontend Engineer specializing in React, Next.js 14+ App Router, TypeScript, and Tailwind CSS.

Rules:
- TypeScript only — no plain JS files
- Next.js App Router: Server Components by default, 'use client' only when needed
- Tailwind for all styling — no inline styles, no CSS modules unless the project already uses them
- Use shadcn/ui components if present in package.json
- React Query or SWR for data fetching in client components
- Zod for form validation and API response schemas
- Follow existing file naming: kebab-case files, PascalCase components
- Read existing components before creating new ones — match patterns exactly
- Never add npm dependencies without checking package.json first

You have tools to read, write, edit files and run commands.
After writing code, run: npx tsc --noEmit
Report every file you created or modified."""


def frontend_web_agent(state: dict) -> dict:
    """Write frontend web code (React/Next.js/TypeScript)."""
    llm = get_llm_for_agent("frontend_web")
    from ai_team.bus import bus

    inbox = bus.consume("frontend_web")
    inbox_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in inbox) if inbox else ""
    inject = state.get("inject_message", "")

    user_msg = (
        f"Task: {state.get('task', '')}\n\n"
        f"Project directory: {state.get('project_dir', '')}\n\n"
        f"Project context:\n{state.get('project_context', '')}\n\n"
        f"Architecture spec:\n{state.get('architecture_spec', '')}\n\n"
        f"Work items:\n{_format_work_items(state.get('work_items', []))}\n\n"
        + (f"Messages from team:\n{inbox_text}\n\n" if inbox_text else "")
        + (f"INTERVENTION — Sultan says: {inject}\n\n" if inject else "")
        + "Write the frontend web code. Read existing components first. Match project patterns exactly."
    )

    response, tokens = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        project_dir=state.get("project_dir", ""),
        max_iterations=30,
    )

    bus.publish("frontend_web", "Frontend web code complete.")
    return {
        "code_changes": [response],
        "total_tokens": state.get("total_tokens", 0) + tokens,
        "inject_message": "",
    }


def _format_work_items(items: list) -> str:
    if not items:
        return "No work items."
    return "\n".join(
        f"{i+1}. {item.get('title','')}: {item.get('description','')}"
        for i, item in enumerate(items)
    )
```

- [ ] **Step 2: Register in config.py**

In `ai_team/config.py`, find the `_AGENT_MODEL_OVERRIDES` dict (or equivalent agent name map inside `get_llm_for_agent`) and add:

```python
"frontend_web": os.getenv("AGENT_MODEL_FRONTEND_WEB"),
"frontend_mobile": os.getenv("AGENT_MODEL_FRONTEND_MOBILE"),
"frontend_desktop": os.getenv("AGENT_MODEL_FRONTEND_DESKTOP"),
"auditor": os.getenv("AGENT_MODEL_AUDITOR"),
```

- [ ] **Step 3: Verify import**

```bash
cd /path/to/ai-dev-team && python -c "from ai_team.agents.frontend_web import frontend_web_agent; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add ai_team/agents/frontend_web.py ai_team/config.py
git commit -m "feat(agents): add frontend_web agent (React/Next.js/TypeScript)"
```

---

## Task 5: Add frontend_mobile.py agent

**Files:**
- Create: `ai_team/agents/frontend_mobile.py`

- [ ] **Step 1: Create the file**

```python
"""Frontend Mobile Agent — Android Kotlin / Jetpack Compose specialist."""

from __future__ import annotations

from ai_team.agents.react_loop import react_loop
from ai_team.config import get_llm_for_agent

SYSTEM_PROMPT = """You are a Senior Android Engineer specializing in Kotlin, Jetpack Compose, and KMP.

Rules:
- Kotlin only — no Java
- Jetpack Compose for all UI — no XML layouts
- MVVM: ViewModel + StateFlow + Repository pattern
- Hilt for DI if already in build.gradle.kts
- Room for local DB, Retrofit + OkHttp for networking
- Coroutines + Flow — no RxJava
- Material3 components — match existing theme
- Read existing ViewModels and composables before creating new ones
- Never modify build.gradle.kts dependencies without explicit instruction

After writing code, run: ./gradlew lint
Report every file you created or modified."""


def frontend_mobile_agent(state: dict) -> dict:
    """Write Android Kotlin / Jetpack Compose code."""
    llm = get_llm_for_agent("frontend_mobile")
    from ai_team.bus import bus

    inbox = bus.consume("frontend_mobile")
    inbox_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in inbox) if inbox else ""
    inject = state.get("inject_message", "")

    user_msg = (
        f"Task: {state.get('task', '')}\n\n"
        f"Project directory: {state.get('project_dir', '')}\n\n"
        f"Project context:\n{state.get('project_context', '')}\n\n"
        f"Architecture spec:\n{state.get('architecture_spec', '')}\n\n"
        f"Work items:\n{_format_work_items(state.get('work_items', []))}\n\n"
        + (f"Messages from team:\n{inbox_text}\n\n" if inbox_text else "")
        + (f"INTERVENTION — Sultan says: {inject}\n\n" if inject else "")
        + "Write the Android Kotlin code. Read existing ViewModels and composables first."
    )

    response, tokens = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        project_dir=state.get("project_dir", ""),
        max_iterations=30,
    )

    bus.publish("frontend_mobile", "Mobile code complete.")
    return {
        "code_changes": [response],
        "total_tokens": state.get("total_tokens", 0) + tokens,
        "inject_message": "",
    }


def _format_work_items(items: list) -> str:
    if not items:
        return "No work items."
    return "\n".join(
        f"{i+1}. {item.get('title','')}: {item.get('description','')}"
        for i, item in enumerate(items)
    )
```

- [ ] **Step 2: Verify import**

```bash
cd /path/to/ai-dev-team && python -c "from ai_team.agents.frontend_mobile import frontend_mobile_agent; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add ai_team/agents/frontend_mobile.py
git commit -m "feat(agents): add frontend_mobile agent (Android Kotlin/Jetpack Compose)"
```

---

## Task 6: Add frontend_desktop.py agent

**Files:**
- Create: `ai_team/agents/frontend_desktop.py`

- [ ] **Step 1: Create the file**

```python
"""Frontend Desktop Agent — Tauri 2.x + React + Rust IPC specialist."""

from __future__ import annotations

from ai_team.agents.react_loop import react_loop
from ai_team.config import get_llm_for_agent

SYSTEM_PROMPT = """You are a Senior Desktop Engineer specializing in Tauri 2.x, React + TypeScript, and Rust.

Rules:
- Tauri 2.x only — use `#[tauri::command]` for IPC, `emit`/`listen` for events
- IPC: `invoke()` on frontend, `#[tauri::command]` + `tauri::State<Mutex<T>>` on Rust side
- Frontend: TypeScript + Tailwind — same rules as a React/Next.js project
- Security: set explicit capability allowlist in `tauri.conf.json` — never wildcard
- Never use deprecated Tauri 1.x APIs
- Read `src-tauri/tauri.conf.json` and `src-tauri/Cargo.toml` before touching Rust code
- For audio/tray/notifications: use tauri plugin ecosystem, not raw JS APIs

After writing Rust code, always run: cargo check --manifest-path src-tauri/Cargo.toml
Report every file you created or modified."""


def frontend_desktop_agent(state: dict) -> dict:
    """Write Tauri desktop code (Rust + React/TypeScript)."""
    llm = get_llm_for_agent("frontend_desktop")
    from ai_team.bus import bus

    inbox = bus.consume("frontend_desktop")
    inbox_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in inbox) if inbox else ""
    inject = state.get("inject_message", "")

    user_msg = (
        f"Task: {state.get('task', '')}\n\n"
        f"Project directory: {state.get('project_dir', '')}\n\n"
        f"Project context:\n{state.get('project_context', '')}\n\n"
        f"Architecture spec:\n{state.get('architecture_spec', '')}\n\n"
        f"Work items:\n{_format_work_items(state.get('work_items', []))}\n\n"
        + (f"Messages from team:\n{inbox_text}\n\n" if inbox_text else "")
        + (f"INTERVENTION — Sultan says: {inject}\n\n" if inject else "")
        + "Write the Tauri desktop code. Read tauri.conf.json and existing Rust commands first."
    )

    response, tokens = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        project_dir=state.get("project_dir", ""),
        max_iterations=30,
    )

    bus.publish("frontend_desktop", "Desktop code complete.")
    return {
        "code_changes": [response],
        "total_tokens": state.get("total_tokens", 0) + tokens,
        "inject_message": "",
    }


def _format_work_items(items: list) -> str:
    if not items:
        return "No work items."
    return "\n".join(
        f"{i+1}. {item.get('title','')}: {item.get('description','')}"
        for i, item in enumerate(items)
    )
```

- [ ] **Step 2: Verify import**

```bash
cd /path/to/ai-dev-team && python -c "from ai_team.agents.frontend_desktop import frontend_desktop_agent; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add ai_team/agents/frontend_desktop.py
git commit -m "feat(agents): add frontend_desktop agent (Tauri 2.x/React/Rust)"
```

---

## Task 7: Add auditor.py agent

**Files:**
- Create: `ai_team/agents/auditor.py`

- [ ] **Step 1: Create the file**

```python
"""Auditor Agent — Code quality, architecture drift, tech debt scoring."""

from __future__ import annotations

from ai_team.agents.react_loop import parse_findings, react_loop
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

    user_msg = (
        f"Audit these changed files:\n{chr(10).join(code_changes)}\n\n"
        f"Project directory: {project_dir}\n\n"
        f"Architecture spec (what was intended):\n{state.get('architecture_spec', '')}\n\n"
        "Instructions:\n"
        "1. Read each changed file\n"
        "2. Compare patterns against existing codebase\n"
        "3. Score tech debt and drift\n"
        "4. Output findings in JSON format"
    )

    from ai_team.bus import bus

    response, tokens = react_loop(
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        user_message=user_msg,
        project_dir=project_dir,
        max_iterations=10,
    )

    findings = parse_findings(response)
    bus.publish("auditor", f"Audit complete. {len(findings)} findings.")

    return {
        "audit_findings": findings,
        "total_tokens": state.get("total_tokens", 0) + tokens,
    }
```

- [ ] **Step 2: Verify import**

```bash
cd /path/to/ai-dev-team && python -c "from ai_team.agents.auditor import auditor_agent; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add ai_team/agents/auditor.py
git commit -m "feat(agents): add auditor agent (quality/architecture/tech-debt)"
```

---

## Task 8: Wire new agents into graph.py

**Files:**
- Modify: `ai_team/graph.py`

- [ ] **Step 1: Add imports**

After existing agent imports at the top of `ai_team/graph.py`, add:

```python
from ai_team.agents.frontend_web import frontend_web_agent
from ai_team.agents.frontend_mobile import frontend_mobile_agent
from ai_team.agents.frontend_desktop import frontend_desktop_agent
from ai_team.agents.auditor import auditor_agent
from ai_team.agents.project_detector import detect_frontend_target
```

- [ ] **Step 2: Add frontend router node and conditional edge function**

After the `init_node` function, add:

```python
def frontend_router_node(state: State) -> dict:
    """Detect or read frontend_target and publish routing decision."""
    from ai_team.bus import bus as _bus

    target = state.get("frontend_target", "")
    if not target:
        target = detect_frontend_target(state.get("project_dir", ""))

    _bus.publish("router", f"Routing to {target} coder.")
    return {"frontend_target": target}


def route_to_coder(state: State) -> str:
    """Conditional edge: returns which coder node to activate."""
    return {
        "web": "frontend_web",
        "mobile": "frontend_mobile",
        "desktop": "frontend_desktop",
    }.get(state.get("frontend_target", "backend"), "coder")
```

- [ ] **Step 3: Add intervention check helper**

Add after `frontend_router_node`:

```python
def _check_intervention(state: State) -> None:
    """Block pipeline while paused. Raise on abort."""
    import time
    while state.get("paused", False):
        time.sleep(1)
    if state.get("abort", False):
        raise SystemExit("Pipeline aborted by Sultan.")
```

- [ ] **Step 4: Register new nodes in build_graph()**

In the `build_graph()` function where nodes are added with `graph.add_node(...)`, add:

```python
graph.add_node("frontend_router", frontend_router_node)
graph.add_node("frontend_web", frontend_web_agent)
graph.add_node("frontend_mobile", frontend_mobile_agent)
graph.add_node("frontend_desktop", frontend_desktop_agent)
graph.add_node("auditor", auditor_agent)
```

- [ ] **Step 5: Add routing edges**

Find the edge that currently goes `planner -> coder` (or `preflight -> coder`) and change it to route through `frontend_router`:

```python
# Remove: graph.add_edge("planner", "coder")
# Add instead:
graph.add_edge("planner", "frontend_router")
graph.add_conditional_edges("frontend_router", route_to_coder, {
    "coder": "coder",
    "frontend_web": "frontend_web",
    "frontend_mobile": "frontend_mobile",
    "frontend_desktop": "frontend_desktop",
})
# All specialist coders feed into import_healer same as coder
graph.add_edge("frontend_web", "import_healer")
graph.add_edge("frontend_mobile", "import_healer")
graph.add_edge("frontend_desktop", "import_healer")
```

- [ ] **Step 6: Add auditor to parallel review block**

Find the section where `reviewer`, `tester`, `security` are added as parallel nodes (the `Send` pattern or fan-out block) and add auditor in the same group:

```python
# In the parallel fan-out section, add auditor alongside reviewer/tester/security:
graph.add_edge("git_commit", "auditor")  # same source as reviewer/tester/security
# In the fan-in (join) section, add auditor as a prerequisite same as the others
```

- [ ] **Step 7: Verify graph compiles**

```bash
cd /path/to/ai-dev-team && python -c "from ai_team.graph import build_graph; g = build_graph(); print('graph ok')"
```

Expected: `graph ok`

- [ ] **Step 8: Commit**

```bash
git add ai_team/graph.py
git commit -m "feat(graph): add frontend routing branch and auditor to parallel review"
```

---

## Task 9: Rewrite web/app.py — split-view dashboard with intervention controls

**Files:**
- Modify: `ai_team/web/app.py`

- [ ] **Step 1: Replace ai_team/web/app.py**

```python
"""FastAPI dashboard — split-view team workspace with intervention controls."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("ai_team.web")


@dataclass
class ControlState:
    paused: bool = False
    inject_message: str = ""
    skip_current: bool = False
    abort: bool = False
    live_output: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "paused": self.paused,
            "inject_message": self.inject_message,
            "skip_current": self.skip_current,
            "abort": self.abort,
        }

    def clear_transient(self) -> None:
        self.inject_message = ""
        self.skip_current = False


control = ControlState()


def push_output(line: str) -> None:
    """Called by agents to push live output to the right panel."""
    control.live_output.append(line)
    if len(control.live_output) > 2000:
        control.live_output = control.live_output[-2000:]


def create_app():
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse
        from pydantic import BaseModel
    except ImportError:
        raise ImportError("Install fastapi and uvicorn: pip install fastapi uvicorn")

    from ai_team.bus import bus

    app = FastAPI(title="AI Dev Team — Team Workspace")

    class InjectPayload(BaseModel):
        message: str

    @app.post("/control/pause")
    async def pause():
        control.paused = True
        bus.publish("sultan", "Pipeline paused.", to_role="all")
        return {"status": "paused"}

    @app.post("/control/resume")
    async def resume():
        control.paused = False
        bus.publish("sultan", "Pipeline resumed.", to_role="all")
        return {"status": "resumed"}

    @app.post("/control/inject")
    async def inject(payload: InjectPayload):
        control.inject_message = payload.message
        bus.publish("sultan", f"Intervention: {payload.message}", to_role="all")
        return {"status": "injected", "message": payload.message}

    @app.post("/control/skip")
    async def skip():
        control.skip_current = True
        bus.publish("sultan", "Skipped current agent.", to_role="all")
        return {"status": "skipped"}

    @app.post("/control/abort")
    async def abort():
        control.abort = True
        bus.publish("sultan", "Pipeline aborted.", to_role="all")
        return {"status": "aborted"}

    @app.get("/control/state")
    async def get_control_state():
        return control.to_dict()

    @app.websocket("/ws/team")
    async def team_ws(websocket: WebSocket):
        await websocket.accept()
        sent_count = 0
        try:
            while True:
                all_msgs = bus.all_messages()
                if len(all_msgs) > sent_count:
                    for msg in all_msgs[sent_count:]:
                        await websocket.send_text(json.dumps({"type": "team", "data": msg}))
                    sent_count = len(all_msgs)
                await websocket.send_text(json.dumps({"type": "control", "data": control.to_dict()}))
                await asyncio.sleep(0.5)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("team_ws error: %s", e)

    @app.websocket("/ws/output")
    async def output_ws(websocket: WebSocket):
        await websocket.accept()
        sent_count = 0
        try:
            while True:
                if len(control.live_output) > sent_count:
                    for line in control.live_output[sent_count:]:
                        await websocket.send_text(json.dumps({"type": "output", "data": line}))
                    sent_count = len(control.live_output)
                await asyncio.sleep(0.3)
        except WebSocketDisconnect:
            pass

    @app.get("/messages")
    async def get_messages():
        return {"messages": bus.all_messages()}

    @app.get("/health")
    async def health():
        return {"status": "ok", "message_count": len(bus.all_messages()), "paused": control.paused}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(content=_dashboard_html())

    return app


def _dashboard_html() -> str:
    # All DOM manipulation in JS uses textContent and createElement — no innerHTML on untrusted data
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Dev Team</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Cascadia Code','Fira Code',monospace;background:#0d1117;color:#c9d1d9;height:100vh;display:flex;flex-direction:column}
header{padding:10px 16px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:16px}
header h1{color:#58a6ff;font-size:1rem}
#badge{font-size:.75rem;padding:2px 8px;border-radius:12px;background:#3fb950;color:#0d1117;font-weight:bold}
#badge.paused{background:#f0883e}
#badge.aborted{background:#f85149}
main{flex:1;display:flex;overflow:hidden}
#team-panel{width:45%;border-right:1px solid #21262d;display:flex;flex-direction:column}
#team-panel h2,#output-panel h2{font-size:.8rem;color:#8b949e;padding:8px 12px;border-bottom:1px solid #21262d}
#team-messages{flex:1;overflow-y:auto;padding:8px}
.msg{padding:8px 10px;margin-bottom:6px;border-radius:6px;background:#161b22;border-left:3px solid #30363d;font-size:.8rem}
.msg-header{display:flex;gap:8px;margin-bottom:4px;align-items:baseline}
.msg-role{font-weight:bold;font-size:.75rem}
.msg-to{color:#6e7681;font-size:.7rem}
.msg-ts{color:#6e7681;font-size:.7rem;margin-left:auto}
.msg-content{color:#c9d1d9;line-height:1.4;word-break:break-word;white-space:pre-wrap}
.msg.sultan{border-left-color:#ffa657;background:#1c1a10}
.msg.coder,.msg.frontend_web,.msg.frontend_mobile,.msg.frontend_desktop{border-left-color:#58a6ff}
.msg.reviewer{border-left-color:#f0883e}
.msg.architect{border-left-color:#bc8cff}
.msg.tester{border-left-color:#3fb950}
.msg.security{border-left-color:#f85149}
.msg.auditor{border-left-color:#d2a8ff}
.msg.debugger{border-left-color:#ffa657}
.msg.planner{border-left-color:#79c0ff}
.msg.router,.msg.docs{border-left-color:#56d364}
#output-panel{flex:1;display:flex;flex-direction:column}
#output-stream{flex:1;overflow-y:auto;padding:8px;font-size:.78rem;line-height:1.5;white-space:pre-wrap;word-break:break-word}
footer{border-top:1px solid #21262d;padding:10px 16px;display:flex;gap:8px;align-items:center}
#inject-input{flex:1;background:#161b22;border:1px solid #30363d;color:#c9d1d9;padding:6px 10px;border-radius:6px;font-family:inherit;font-size:.85rem}
#inject-input:focus{outline:none;border-color:#58a6ff}
button{padding:6px 14px;border-radius:6px;border:none;cursor:pointer;font-size:.8rem;font-weight:bold;font-family:inherit}
#btn-inject{background:#58a6ff;color:#0d1117}
#btn-pause{background:#f0883e;color:#0d1117}
#btn-resume{background:#3fb950;color:#0d1117}
#btn-skip{background:#bc8cff;color:#0d1117}
#btn-abort{background:#f85149;color:#fff}
</style>
</head>
<body>
<header>
  <h1>AI Dev Team — Team Workspace</h1>
  <span id="badge">RUNNING</span>
  <span id="msg-count" style="color:#6e7681;font-size:.75rem;margin-left:auto"></span>
</header>
<main>
  <div id="team-panel">
    <h2>Team Conversation</h2>
    <div id="team-messages"></div>
  </div>
  <div id="output-panel">
    <h2>Live Output</h2>
    <div id="output-stream"></div>
  </div>
</main>
<footer>
  <input id="inject-input" type="text" placeholder="Type intervention message and press Inject...">
  <button id="btn-inject">Inject</button>
  <button id="btn-pause">Pause</button>
  <button id="btn-resume">Resume</button>
  <button id="btn-skip">Skip</button>
  <button id="btn-abort">Abort</button>
</footer>
<script>
(function(){
  var teamEl=document.getElementById('team-messages');
  var outputEl=document.getElementById('output-stream');
  var badge=document.getElementById('badge');
  var countEl=document.getElementById('msg-count');
  var total=0;

  var COLORS={
    coder:'#58a6ff',frontend_web:'#58a6ff',frontend_mobile:'#58a6ff',
    frontend_desktop:'#58a6ff',reviewer:'#f0883e',architect:'#bc8cff',
    tester:'#3fb950',security:'#f85149',auditor:'#d2a8ff',
    debugger:'#ffa657',planner:'#79c0ff',docs:'#56d364',
    router:'#56d364',sultan:'#ffa657'
  };

  function addTeamMsg(msg){
    var div=document.createElement('div');
    div.className='msg '+(msg.role||'unknown');

    var header=document.createElement('div');
    header.className='msg-header';

    var roleSpan=document.createElement('span');
    roleSpan.className='msg-role';
    roleSpan.style.color=COLORS[msg.role]||'#c9d1d9';
    roleSpan.textContent='['+( msg.role||'?')+']';
    header.appendChild(roleSpan);

    if(msg.to&&msg.to!=='all'){
      var toSpan=document.createElement('span');
      toSpan.className='msg-to';
      toSpan.textContent='-> '+msg.to;
      header.appendChild(toSpan);
    }

    var tsSpan=document.createElement('span');
    tsSpan.className='msg-ts';
    tsSpan.textContent=msg.timestamp?msg.timestamp.substring(11,19):'';
    header.appendChild(tsSpan);

    var content=document.createElement('div');
    content.className='msg-content';
    content.textContent=msg.content||'';

    div.appendChild(header);
    div.appendChild(content);
    teamEl.appendChild(div);

    total++;
    countEl.textContent=total+' messages';
    teamEl.scrollTop=teamEl.scrollHeight;
  }

  function addOutput(line){
    var span=document.createElement('span');
    span.textContent=line+'\n';
    outputEl.appendChild(span);
    outputEl.scrollTop=outputEl.scrollHeight;
  }

  function updateBadge(state){
    if(state.abort){badge.textContent='ABORTED';badge.className='aborted';}
    else if(state.paused){badge.textContent='PAUSED';badge.className='paused';}
    else{badge.textContent='RUNNING';badge.className='';}
  }

  function connectTeam(){
    var proto=location.protocol==='https:'?'wss:':'ws:';
    var ws=new WebSocket(proto+'//'+location.host+'/ws/team');
    ws.onmessage=function(e){
      try{
        var pkt=JSON.parse(e.data);
        if(pkt.type==='team')addTeamMsg(pkt.data);
        else if(pkt.type==='control')updateBadge(pkt.data);
      }catch(_){}
    };
    ws.onclose=function(){setTimeout(connectTeam,2000);};
  }

  function connectOutput(){
    var proto=location.protocol==='https:'?'wss:':'ws:';
    var ws=new WebSocket(proto+'//'+location.host+'/ws/output');
    ws.onmessage=function(e){
      try{
        var pkt=JSON.parse(e.data);
        if(pkt.type==='output')addOutput(pkt.data);
      }catch(_){}
    };
    ws.onclose=function(){setTimeout(connectOutput,2000);};
  }

  function ctrl(path,body){
    fetch(path,{
      method:'POST',
      headers:body?{'Content-Type':'application/json'}:{},
      body:body?JSON.stringify(body):undefined
    });
  }

  document.getElementById('btn-inject').onclick=function(){
    var msg=document.getElementById('inject-input').value.trim();
    if(msg){ctrl('/control/inject',{message:msg});document.getElementById('inject-input').value='';}
  };
  document.getElementById('inject-input').onkeydown=function(e){
    if(e.key==='Enter')document.getElementById('btn-inject').click();
  };
  document.getElementById('btn-pause').onclick=function(){ctrl('/control/pause');};
  document.getElementById('btn-resume').onclick=function(){ctrl('/control/resume');};
  document.getElementById('btn-skip').onclick=function(){ctrl('/control/skip');};
  document.getElementById('btn-abort').onclick=function(){
    if(confirm('Abort the pipeline? All agents stop immediately.'))ctrl('/control/abort');
  };

  connectTeam();
  connectOutput();
})();
</script>
</body>
</html>"""


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        raise SystemExit("Install uvicorn: pip install uvicorn")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
```

- [ ] **Step 2: Verify dashboard app creates**

```bash
cd /path/to/ai-dev-team && python -c "from ai_team.web.app import create_app, push_output; app = create_app(); print('dashboard ok')"
```

Expected: `dashboard ok`

- [ ] **Step 3: Commit**

```bash
git add ai_team/web/app.py
git commit -m "feat(dashboard): split-view workspace with intervention controls (pause/resume/inject/skip/abort)"
```

---

## Task 10: Update .env.example and run.py for --target flag

**Files:**
- Modify: `.env.example`
- Modify: `run.py`

- [ ] **Step 1: Append to .env.example**

```bash
# Per-agent model routing — specialist agents
AGENT_MODEL_FRONTEND_WEB=
AGENT_MODEL_FRONTEND_MOBILE=
AGENT_MODEL_FRONTEND_DESKTOP=
AGENT_MODEL_AUDITOR=

# Frontend target override (auto-detected if blank)
# Options: web | mobile | desktop | backend
FRONTEND_TARGET=
```

- [ ] **Step 2: Add --target to run.py CLI**

Find the `argparse` setup in `run.py` and add:

```python
parser.add_argument(
    "--target",
    choices=["web", "mobile", "desktop", "backend"],
    default=None,
    help="Override frontend target detection",
)
```

Then where `initial_state` dict is built, add:

```python
if args.target:
    initial_state["frontend_target"] = args.target
```

- [ ] **Step 3: Verify --target appears in help**

```bash
cd /path/to/ai-dev-team && python run.py --help | grep target
```

Expected output contains: `--target {web,mobile,desktop,backend}`

- [ ] **Step 4: Commit**

```bash
git add .env.example run.py
git commit -m "feat(cli): add --target flag for frontend agent routing override"
```

---

## Task 11: Smoke test — end-to-end verification

- [ ] **Step 1: Start dashboard**

```bash
cd /path/to/ai-dev-team && python -m ai_team.web.app
```

Open http://localhost:8765 — verify split-view layout with Team Conversation (left), Live Output (right), intervention bar (bottom).

- [ ] **Step 2: Verify all agent imports in one shot**

```bash
cd /path/to/ai-dev-team && python -c "
from ai_team.agents.frontend_web import frontend_web_agent
from ai_team.agents.frontend_mobile import frontend_mobile_agent
from ai_team.agents.frontend_desktop import frontend_desktop_agent
from ai_team.agents.auditor import auditor_agent
from ai_team.graph import build_graph
g = build_graph()
print('all imports ok, graph compiled')
"
```

Expected: `all imports ok, graph compiled`

- [ ] **Step 3: Test frontend routing detection**

```bash
cd /path/to/ai-dev-team && python -c "
import tempfile
from pathlib import Path
from ai_team.agents.project_detector import detect_frontend_target

with tempfile.TemporaryDirectory() as d:
    Path(d, 'tauri.conf.json').write_text('{}')
    assert detect_frontend_target(d) == 'desktop', 'tauri detection failed'

with tempfile.TemporaryDirectory() as d:
    Path(d, 'package.json').write_text('{\"dependencies\":{\"react\":\"18\"}}')
    assert detect_frontend_target(d) == 'web', 'react detection failed'

print('routing detection ok')
"
```

Expected: `routing detection ok`

- [ ] **Step 4: Test control endpoints**

Start dashboard in background, then:

```bash
curl -s -X POST http://localhost:8765/control/pause | python -m json.tool
```

Expected: `{"status": "paused"}`

```bash
curl -s -X POST http://localhost:8765/control/resume | python -m json.tool
```

Expected: `{"status": "resumed"}`

```bash
curl -s -X POST http://localhost:8765/control/inject -H "Content-Type: application/json" -d '{"message":"use TypeScript strict mode"}' | python -m json.tool
```

Expected: `{"status": "injected", "message": "use TypeScript strict mode"}`

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: smoke tests passed — all new agents and dashboard verified"
```
