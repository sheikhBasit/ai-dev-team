"""A2A protocol routes — agent discovery and task delegation endpoints.

Spec: https://google.github.io/A2A/specification/
Adds to existing FastAPI app:
  GET  /.well-known/agents              — list all agent cards
  GET  /.well-known/agent/{name}        — single agent card
  POST /a2a/tasks                       — delegate a task to an agent
  GET  /a2a/tasks/{task_id}            — poll task result
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, HTTPException
from pydantic import BaseModel

from ai_team.web.a2a_cards import AGENT_CARDS

# In-memory task store — keyed by task_id
_tasks: dict[str, dict[str, Any]] = {}


class TaskRequest(BaseModel):
    agent: str
    task: str
    metadata: dict = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_card(name: str, base_url: str) -> dict:
    card = dict(AGENT_CARDS[name])
    card["url"] = f"{base_url}/a2a/tasks"
    card["version"] = "1.0"
    card["protocol"] = "a2a/1.0"
    return card


def register_a2a_routes(app, base_url: str = "http://localhost:8765") -> None:
    """Register A2A routes on an existing FastAPI app instance."""

    # -------------------------------------------------------------------------
    # Discovery
    # -------------------------------------------------------------------------

    @app.get("/.well-known/agents")
    async def list_agents():
        """List all available agent cards (A2A discovery endpoint)."""
        return {
            "protocol": "a2a/1.0",
            "agents": [_make_card(name, base_url) for name in AGENT_CARDS],
        }

    @app.get("/.well-known/agent/{name}")
    async def get_agent_card(name: str):
        """Return a single agent card by name."""
        if name not in AGENT_CARDS:
            raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
        return _make_card(name, base_url)

    # -------------------------------------------------------------------------
    # Task delegation
    # -------------------------------------------------------------------------

    @app.post("/a2a/tasks")
    async def submit_task(req: TaskRequest, background_tasks: BackgroundTasks):
        """Submit a task to a named agent. Returns task_id immediately."""
        if req.agent not in AGENT_CARDS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown agent '{req.agent}'. Available: {list(AGENT_CARDS)}",
            )

        task_id = str(uuid.uuid4())
        _tasks[task_id] = {
            "task_id": task_id,
            "agent": req.agent,
            "task": req.task,
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": _now(),
            "completed_at": None,
        }

        background_tasks.add_task(_run_task, task_id, req.agent, req.task)

        return {
            "task_id": task_id,
            "status": "pending",
            "poll_url": f"{base_url}/a2a/tasks/{task_id}",
        }

    @app.get("/a2a/tasks/{task_id}")
    async def get_task(task_id: str):
        """Poll the status and result of a submitted task."""
        if task_id not in _tasks:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        return _tasks[task_id]

    @app.get("/a2a/tasks")
    async def list_tasks():
        """List all tasks (status, agent, created_at)."""
        return {
            "tasks": [
                {k: v for k, v in t.items() if k != "result"}
                for t in _tasks.values()
            ]
        }


async def _run_task(task_id: str, agent_name: str, task: str) -> None:
    """Run a task against an agent via the bus and update task store."""
    try:
        from ai_team.bus import bus

        _tasks[task_id]["status"] = "running"

        # Publish task to the agent via the existing bus
        bus.publish(
            from_role="a2a",
            content=f"[A2A TASK {task_id}] {task}",
            to_role=agent_name,
        )

        # Collect the agent's response from the bus (poll for up to 60s)
        import asyncio
        deadline = 60
        interval = 0.5
        elapsed = 0.0
        result_content = None

        while elapsed < deadline:
            await asyncio.sleep(interval)
            elapsed += interval
            msgs = bus.consume("a2a")
            for msg in msgs:
                if task_id in (msg.get("content") or ""):
                    result_content = msg.get("content")
                    break
            if result_content:
                break

        if result_content:
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["result"] = result_content
        else:
            # Task was queued in the bus — agent will process it when pipeline runs
            _tasks[task_id]["status"] = "queued"
            _tasks[task_id]["result"] = (
                f"Task queued for agent '{agent_name}'. "
                "Agent will process it in the next pipeline run. "
                f"Poll /a2a/tasks/{task_id} for updates."
            )

        _tasks[task_id]["completed_at"] = _now()

    except Exception as e:
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["error"] = str(e)
        _tasks[task_id]["completed_at"] = _now()
