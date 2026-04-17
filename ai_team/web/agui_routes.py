"""AG-UI (Agent-User Interaction Protocol) — SSE event stream endpoint.

Spec: https://docs.ag-ui.com/protocol/events
Adds to existing FastAPI app:
  GET  /agui/stream          — SSE stream of AG-UI events from the agent bus
  POST /agui/run             — start a pipeline run and stream events back
  GET  /agui/schema          — AG-UI agent manifest (capabilities + event types)

AG-UI event types emitted:
  RUN_STARTED        — pipeline accepted the task
  STEP_STARTED       — a named agent node began
  TEXT_MESSAGE_START — agent started writing output
  TEXT_MESSAGE_DELTA — next chunk of agent output (token streaming)
  TEXT_MESSAGE_END   — agent finished writing
  TOOL_CALL_START    — agent invoked a tool
  TOOL_CALL_END      — tool call completed
  STATE_DELTA        — pipeline state changed (current node, iteration)
  RUN_FINISHED       — pipeline completed
  RUN_ERROR          — pipeline failed

Transport: Server-Sent Events (SSE) — works with any EventSource client,
React useChat hooks, or the @ag-ui/client SDK.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, AsyncGenerator

from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ai_team.bus import bus
from ai_team.web.a2a_cards import AGENT_CARDS


# ---------------------------------------------------------------------------
# AG-UI event helpers
# ---------------------------------------------------------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)


def _event(event_type: str, data: dict) -> str:
    """Format a single SSE message with AG-UI envelope."""
    payload = {
        "type": event_type,
        "timestamp": _now_ms(),
        **data,
    }
    return f"data: {json.dumps(payload)}\n\n"


def _run_started(run_id: str, task: str) -> str:
    return _event("RUN_STARTED", {
        "runId": run_id,
        "threadId": run_id,
        "input": [{"role": "user", "content": task}],
    })


def _run_finished(run_id: str) -> str:
    return _event("RUN_FINISHED", {"runId": run_id})


def _run_error(run_id: str, message: str) -> str:
    return _event("RUN_ERROR", {"runId": run_id, "message": message})


def _step_started(run_id: str, step_name: str) -> str:
    return _event("STEP_STARTED", {
        "runId": run_id,
        "stepName": step_name,
        "stepId": f"{run_id}-{step_name}",
    })


def _step_finished(run_id: str, step_name: str) -> str:
    return _event("STEP_FINISHED", {
        "runId": run_id,
        "stepName": step_name,
        "stepId": f"{run_id}-{step_name}",
    })


def _text_message(run_id: str, role: str, content: str) -> str:
    """Emit a full text message as start + delta + end sequence."""
    msg_id = str(uuid.uuid4())
    start = _event("TEXT_MESSAGE_START", {
        "runId": run_id,
        "messageId": msg_id,
        "role": role,
    })
    # Chunk content into ~80-char pieces to simulate token streaming
    chunks = [content[i:i+80] for i in range(0, len(content), 80)]
    deltas = "".join(
        _event("TEXT_MESSAGE_DELTA", {
            "runId": run_id,
            "messageId": msg_id,
            "delta": chunk,
        })
        for chunk in chunks
    )
    end = _event("TEXT_MESSAGE_END", {
        "runId": run_id,
        "messageId": msg_id,
    })
    return start + deltas + end


def _state_delta(run_id: str, delta: dict) -> str:
    return _event("STATE_DELTA", {
        "runId": run_id,
        "delta": delta,
    })


def _tool_call(run_id: str, tool_name: str, args: dict, result: Any = None) -> str:
    call_id = str(uuid.uuid4())
    start = _event("TOOL_CALL_START", {
        "runId": run_id,
        "toolCallId": call_id,
        "toolCallName": tool_name,
        "parentMessageId": run_id,
    })
    end = _event("TOOL_CALL_END", {
        "runId": run_id,
        "toolCallId": call_id,
        "result": json.dumps(result) if result is not None else "",
    })
    return start + end


# ---------------------------------------------------------------------------
# Bus → AG-UI event translator
# ---------------------------------------------------------------------------

# Map agent bus roles to AG-UI step names
_ROLE_TO_STEP = {
    "requirements":  "Requirements Analysis",
    "designer":      "UI/UX Design",
    "architect":     "Architecture Design",
    "planner":       "Task Planning",
    "coder":         "Code Generation",
    "reviewer":      "Code Review",
    "tester":        "Testing",
    "security":      "Security Audit",
    "debugger":      "Debugging",
    "evaluator":     "Evaluation",
    "docs":          "Documentation",
    "git_commit":    "Git Commit",
    "ci_check":      "CI Check",
    "dashboard":     "Dashboard",
    "a2a":           "A2A Task",
}


async def _stream_bus_as_agui(
    run_id: str,
    task: str,
    start_msg_index: int,
    timeout: float = 300.0,
) -> AsyncGenerator[str, None]:
    """Translate existing bus messages into AG-UI SSE events."""
    yield _run_started(run_id, task)

    seen_roles: set[str] = set()
    active_step: str | None = None
    deadline = asyncio.get_event_loop().time() + timeout
    poll_index = start_msg_index

    while asyncio.get_event_loop().time() < deadline:
        all_msgs = bus.all_messages()
        new_msgs = all_msgs[poll_index:]
        poll_index = len(all_msgs)

        for msg in new_msgs:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            step_name = _ROLE_TO_STEP.get(role, role.title())

            # Emit STEP_STARTED when a new agent role appears
            if role not in seen_roles and role not in ("dashboard", "a2a"):
                if active_step:
                    yield _step_finished(run_id, active_step)
                yield _step_started(run_id, step_name)
                active_step = step_name
                seen_roles.add(role)

                # Emit state delta showing current agent
                yield _state_delta(run_id, {
                    "currentAgent": role,
                    "seenAgents": list(seen_roles),
                })

            # Skip control messages — emit as state, not text
            if content.startswith("control:"):
                action = content.replace("control:", "")
                yield _state_delta(run_id, {"controlAction": action})
                continue

            # Emit agent content as streaming text message
            if content:
                yield _text_message(run_id, role, content)

        await asyncio.sleep(0.3)

    # Close final step
    if active_step:
        yield _step_finished(run_id, active_step)
    yield _run_finished(run_id)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    task: str
    metadata: dict = {}


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_agui_routes(app, base_url: str = "http://localhost:8765") -> None:
    """Register AG-UI routes on an existing FastAPI app instance."""

    # ── Schema / manifest ───────────────────────────────────────────────────

    @app.get("/agui/schema")
    async def agui_schema():
        """AG-UI agent manifest — describes capabilities and supported events."""
        return {
            "protocol": "ag-ui/1.0",
            "name": "AI Dev Team",
            "description": "Autonomous AI engineering team — LangGraph pipeline with 19 nodes.",
            "streamUrl": f"{base_url}/agui/stream",
            "runUrl": f"{base_url}/agui/run",
            "supportedEvents": [
                "RUN_STARTED", "RUN_FINISHED", "RUN_ERROR",
                "STEP_STARTED", "STEP_FINISHED",
                "TEXT_MESSAGE_START", "TEXT_MESSAGE_DELTA", "TEXT_MESSAGE_END",
                "TOOL_CALL_START", "TOOL_CALL_END",
                "STATE_DELTA",
            ],
            "agents": [
                {"name": name, **{k: v for k, v in card.items() if k != "name"}}
                for name, card in AGENT_CARDS.items()
            ],
        }

    # ── Live bus stream (GET SSE) ────────────────────────────────────────────

    @app.get("/agui/stream")
    async def agui_stream(request: Request):
        """SSE stream of all bus activity translated to AG-UI events.

        Connect with:
            const es = new EventSource('http://localhost:8765/agui/stream');
            es.onmessage = (e) => console.log(JSON.parse(e.data));

        Or with the @ag-ui/client SDK:
            import { AgUiClient } from '@ag-ui/client';
            const client = new AgUiClient({ streamUrl: 'http://localhost:8765/agui/stream' });
        """
        run_id = str(uuid.uuid4())
        start_index = len(bus.all_messages())

        async def generate():
            # Heartbeat comment every 15s to keep connection alive
            async def heartbeat():
                while True:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(15)

            stream = _stream_bus_as_agui(run_id, "live-monitor", start_index, timeout=3600)
            async for chunk in stream:
                if await request.is_disconnected():
                    break
                yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # ── Run endpoint (POST → SSE) ────────────────────────────────────────────

    @app.post("/agui/run")
    async def agui_run(req: RunRequest, request: Request):
        """Submit a task and receive AG-UI event stream back.

        The pipeline must be running externally (via `think` CLI).
        This endpoint translates bus activity into AG-UI events for
        any AG-UI-compatible frontend to consume.

        Usage with fetch + ReadableStream:
            const resp = await fetch('/agui/run', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task: 'Add a login endpoint'}),
            });
            const reader = resp.body.getReader();
            // read chunks...
        """
        run_id = str(uuid.uuid4())
        start_index = len(bus.all_messages())

        # Publish task to the bus so pipeline agents can pick it up
        bus.publish(
            from_role="agui",
            content=f"[AG-UI RUN {run_id}] {req.task}",
            to_role="all",
        )

        async def generate():
            async for chunk in _stream_bus_as_agui(
                run_id, req.task, start_index, timeout=300
            ):
                if await request.is_disconnected():
                    break
                yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # ── Health check ────────────────────────────────────────────────────────

    @app.get("/agui/health")
    async def agui_health():
        return {
            "protocol": "ag-ui/1.0",
            "status": "ok",
            "transport": "sse",
            "agents": list(AGENT_CARDS.keys()),
        }
