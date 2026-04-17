"""FastAPI live dashboard — split-view with intervention controls."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Redis connection — optional, graceful fallback to in-memory
# ---------------------------------------------------------------------------

try:
    import redis as redis_lib

    _redis = redis_lib.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        decode_responses=True,
    )
    _redis.ping()
    logger_boot = logging.getLogger("ai_team.web")
    logger_boot.info("Redis connected at %s", os.getenv("REDIS_URL", "redis://localhost:6379"))
except Exception:
    _redis = None  # type: ignore[assignment]

try:
    from pydantic import BaseModel, Field

    class InjectPayload(BaseModel):
        message: str = Field(..., min_length=1, max_length=2000)

except ImportError:
    pass  # fastapi/pydantic not installed; create_app() will raise cleanly

logger = logging.getLogger("ai_team.web")

_MAX_OUTPUT = 2000


# ---------------------------------------------------------------------------
# Control state
# ---------------------------------------------------------------------------

_REDIS_STATE_KEY = "ai_team:control"
_REDIS_OUTPUT_KEY = "ai_team:live_output"


@dataclass
class ControlState:
    """In-memory control state.

    When Redis is available, all reads/writes go through Redis so that
    multiple workers share the same state.  Falls back to this in-memory
    object transparently when Redis is unavailable.
    """

    paused: bool = False
    inject_message: str = ""
    skip_current: bool = False
    abort: bool = False
    live_output: list = field(default_factory=list)

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _redis_get_state() -> dict:
        """Read state dict from Redis; returns empty dict on any error."""
        if _redis is None:
            return {}
        try:
            raw = _redis.get(_REDIS_STATE_KEY)
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    @staticmethod
    def _redis_set_state(data: dict) -> None:
        """Write state dict to Redis; silently ignores errors."""
        if _redis is None:
            return
        try:
            _redis.set(_REDIS_STATE_KEY, json.dumps(data))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Paused property — persisted to Redis when available
    # ------------------------------------------------------------------

    @property  # type: ignore[override]
    def paused(self) -> bool:  # type: ignore[override]
        if _redis is not None:
            return bool(self._redis_get_state().get("paused", False))
        return self._paused

    @paused.setter
    def paused(self, value: bool) -> None:
        self._paused: bool = value
        if _redis is not None:
            state = self._redis_get_state()
            state["paused"] = value
            self._redis_set_state(state)

    # ------------------------------------------------------------------
    # inject_message property
    # ------------------------------------------------------------------

    @property  # type: ignore[override]
    def inject_message(self) -> str:  # type: ignore[override]
        if _redis is not None:
            return str(self._redis_get_state().get("inject_message", ""))
        return self._inject_message

    @inject_message.setter
    def inject_message(self, value: str) -> None:
        self._inject_message: str = value
        if _redis is not None:
            state = self._redis_get_state()
            state["inject_message"] = value
            self._redis_set_state(state)

    # ------------------------------------------------------------------
    # skip_current property
    # ------------------------------------------------------------------

    @property  # type: ignore[override]
    def skip_current(self) -> bool:  # type: ignore[override]
        if _redis is not None:
            return bool(self._redis_get_state().get("skip_current", False))
        return self._skip_current

    @skip_current.setter
    def skip_current(self, value: bool) -> None:
        self._skip_current: bool = value
        if _redis is not None:
            state = self._redis_get_state()
            state["skip_current"] = value
            self._redis_set_state(state)

    # ------------------------------------------------------------------
    # abort property
    # ------------------------------------------------------------------

    @property  # type: ignore[override]
    def abort(self) -> bool:  # type: ignore[override]
        if _redis is not None:
            return bool(self._redis_get_state().get("abort", False))
        return self._abort

    @abort.setter
    def abort(self, value: bool) -> None:
        self._abort: bool = value
        if _redis is not None:
            state = self._redis_get_state()
            state["abort"] = value
            self._redis_set_state(state)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

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


# Initialise backing fields so the setters in __init__ work correctly
# before Redis properties are fully active.
def _make_control() -> ControlState:
    obj = object.__new__(ControlState)
    obj._paused = False
    obj._inject_message = ""
    obj._skip_current = False
    obj._abort = False
    obj.live_output = []
    return obj


control = _make_control()


def push_output(line: str) -> None:
    """Append a line to the live output buffer, capped at _MAX_OUTPUT entries.

    Uses Redis list when available so all workers share the same stream.
    Falls back to the in-memory list when Redis is unavailable.
    """
    if _redis is not None:
        try:
            _redis.rpush(_REDIS_OUTPUT_KEY, line)
            # Trim from the left so the list never exceeds the cap
            _redis.ltrim(_REDIS_OUTPUT_KEY, -_MAX_OUTPUT, -1)
            return
        except Exception:
            pass  # fall through to in-memory
    control.live_output.append(line)
    if len(control.live_output) > _MAX_OUTPUT:
        del control.live_output[: len(control.live_output) - _MAX_OUTPUT]


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app():
    try:
        from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse
    except ImportError:
        raise ImportError("Install fastapi and uvicorn: pip install fastapi uvicorn")

    from ai_team.bus import bus
    from ai_team.web.a2a_routes import register_a2a_routes
    from ai_team.web.agui_routes import register_agui_routes

    app = FastAPI(title="AI Dev Team Dashboard")
    register_a2a_routes(app)
    register_agui_routes(app)

    # ------------------------------------------------------------------
    # REST — control endpoints
    # ------------------------------------------------------------------

    @app.post("/control/pause")
    async def control_pause():
        control.paused = True
        bus.publish("dashboard", "control:pause", to_role="all")
        return {"status": "paused"}

    @app.post("/control/resume")
    async def control_resume():
        control.paused = False
        bus.publish("dashboard", "control:resume", to_role="all")
        return {"status": "resumed"}

    @app.post("/control/inject")
    async def control_inject(payload: InjectPayload = Body(...)):
        control.inject_message = payload.message
        bus.publish("dashboard", f"control:inject:{payload.message}", to_role="all")
        return {"status": "injected", "message": payload.message}

    @app.post("/control/skip")
    async def control_skip():
        control.skip_current = True
        bus.publish("dashboard", "control:skip", to_role="all")
        return {"status": "skipped"}

    @app.post("/control/abort")
    async def control_abort():
        control.abort = True
        bus.publish("dashboard", "control:abort", to_role="all")
        return {"status": "aborted"}

    @app.get("/control/state")
    async def control_state():
        return control.to_dict()

    # ------------------------------------------------------------------
    # REST — read endpoints
    # ------------------------------------------------------------------

    @app.get("/messages")
    async def get_messages():
        return {"messages": bus.all_messages()}

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "message_count": len(bus.all_messages()),
            "paused": control.paused,
        }

    # ------------------------------------------------------------------
    # WebSocket — team conversation stream
    # ------------------------------------------------------------------

    @app.websocket("/ws/team")
    async def ws_team(websocket: WebSocket):
        await websocket.accept()
        logger.info("Team WS client connected")
        sent_count = 0
        last_control: dict | None = None
        while True:
            try:
                all_msgs = bus.all_messages()
                if len(all_msgs) > sent_count:
                    for msg in all_msgs[sent_count:]:
                        await websocket.send_text(
                            json.dumps({"type": "team", "data": msg})
                        )
                    sent_count = len(all_msgs)
                # Push control state only when it changes
                current_control = control.to_dict()
                if current_control != last_control:
                    await websocket.send_text(
                        json.dumps({"type": "control", "data": current_control})
                    )
                    last_control = current_control
                await asyncio.sleep(0.5)
            except WebSocketDisconnect:
                logger.info("Team WS client disconnected")
                break
            except Exception as exc:
                logger.warning("Team WS error: %s", exc)
                break

    # ------------------------------------------------------------------
    # WebSocket — live output stream
    # ------------------------------------------------------------------

    @app.websocket("/ws/output")
    async def ws_output(websocket: WebSocket):
        await websocket.accept()
        logger.info("Output WS client connected")
        sent_count = 0
        while True:
            try:
                # Read from Redis when available, otherwise fall back to
                # the in-memory list that push_output() maintains.
                if _redis is not None:
                    try:
                        snapshot = _redis.lrange(_REDIS_OUTPUT_KEY, 0, -1)
                    except Exception:
                        snapshot = list(control.live_output)
                else:
                    snapshot = list(control.live_output)

                if len(snapshot) > sent_count:
                    for line in snapshot[sent_count:]:
                        await websocket.send_text(
                            json.dumps({"type": "output", "data": line})
                        )
                    sent_count = len(snapshot)
                await asyncio.sleep(0.3)
            except WebSocketDisconnect:
                logger.info("Output WS client disconnected")
                break
            except Exception as exc:
                logger.warning("Output WS error: %s", exc)
                break

    # ------------------------------------------------------------------
    # Dashboard HTML
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(content=_dashboard_html())

    return app


# ---------------------------------------------------------------------------
# HTML dashboard
# ---------------------------------------------------------------------------

def _dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Dev Team — Live Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    font-family: monospace;
    background: #0d1117;
    color: #c9d1d9;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 16px;
    background: #161b22;
    border-bottom: 1px solid #30363d;
    flex-shrink: 0;
  }
  header h1 { color: #58a6ff; font-size: 1rem; margin: 0; }
  #status-team, #status-output {
    font-size: 0.75rem;
    padding: 2px 8px;
    border-radius: 10px;
    background: #21262d;
  }
  #status-team.connected, #status-output.connected { color: #3fb950; }
  #status-team.disconnected, #status-output.disconnected { color: #f85149; }
  #paused-badge {
    font-size: 0.75rem;
    padding: 2px 8px;
    border-radius: 10px;
    background: #f0883e;
    color: #0d1117;
    display: none;
  }
  #paused-badge.visible { display: inline; }

  .workspace {
    display: flex;
    flex: 1;
    overflow: hidden;
  }
  .panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-right: 1px solid #30363d;
  }
  .panel:last-child { border-right: none; }
  #panel-team { width: 45%; }
  #panel-output { flex: 1; }

  .panel-title {
    font-size: 0.8rem;
    font-weight: bold;
    color: #8b949e;
    padding: 6px 12px;
    background: #161b22;
    border-bottom: 1px solid #30363d;
    flex-shrink: 0;
  }
  .panel-body {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  /* Team messages */
  .msg {
    padding: 5px 10px;
    margin-bottom: 4px;
    border-radius: 4px;
    background: #161b22;
    border-left: 3px solid #30363d;
    font-size: 0.82rem;
  }
  .msg.coder        { border-left-color: #58a6ff; }
  .msg.reviewer     { border-left-color: #f0883e; }
  .msg.architect    { border-left-color: #bc8cff; }
  .msg.tester       { border-left-color: #3fb950; }
  .msg.security     { border-left-color: #f85149; }
  .msg.debugger     { border-left-color: #ffa657; }
  .msg.planner      { border-left-color: #79c0ff; }
  .msg.docs         { border-left-color: #56d364; }
  .msg.dashboard    { border-left-color: #6e7681; }
  .role  { font-weight: bold; margin-right: 6px; }
  .ts    { color: #6e7681; font-size: 0.72rem; margin-right: 6px; }

  /* Output lines */
  .out-line {
    font-size: 0.8rem;
    color: #c9d1d9;
    padding: 2px 0;
    white-space: pre-wrap;
    word-break: break-all;
  }

  /* Footer — intervention bar */
  footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: #161b22;
    border-top: 1px solid #30363d;
    flex-shrink: 0;
    flex-wrap: wrap;
  }
  #inject-input {
    flex: 1;
    min-width: 200px;
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 4px;
    color: #c9d1d9;
    font-family: monospace;
    font-size: 0.85rem;
    padding: 5px 10px;
    outline: none;
  }
  #inject-input:focus { border-color: #58a6ff; }
  .btn {
    font-family: monospace;
    font-size: 0.8rem;
    padding: 5px 12px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    color: #0d1117;
  }
  .btn-inject  { background: #58a6ff; }
  .btn-pause   { background: #f0883e; }
  .btn-resume  { background: #3fb950; }
  .btn-skip    { background: #ffa657; }
  .btn-abort   { background: #f85149; }
  .btn:hover { opacity: 0.85; }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
</head>
<body>

<header>
  <h1>AI Dev Team</h1>
  <span id="status-team" class="disconnected">Team: connecting...</span>
  <span id="status-output" class="disconnected">Output: connecting...</span>
  <span id="paused-badge">PAUSED</span>
</header>

<div class="workspace">
  <div class="panel" id="panel-team">
    <div class="panel-title">Team Conversation</div>
    <div class="panel-body" id="team-body"></div>
  </div>
  <div class="panel" id="panel-output">
    <div class="panel-title">Live Output</div>
    <div class="panel-body" id="output-body"></div>
  </div>
</div>

<footer>
  <input id="inject-input" type="text" placeholder="Inject message to agents..." />
  <button class="btn btn-inject" onclick="doInject()">Inject</button>
  <button class="btn btn-pause"  onclick="doControl('pause')">Pause</button>
  <button class="btn btn-resume" onclick="doControl('resume')">Resume</button>
  <button class="btn btn-skip"   onclick="doControl('skip')">Skip</button>
  <button class="btn btn-abort"  onclick="doControl('abort')">Abort</button>
</footer>

<script>
(function () {
  'use strict';

  var teamBody   = document.getElementById('team-body');
  var outputBody = document.getElementById('output-body');
  var statusTeam = document.getElementById('status-team');
  var statusOut  = document.getElementById('status-output');
  var pausedBadge = document.getElementById('paused-badge');

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  function scrollBottom(el) {
    el.scrollTop = el.scrollHeight;
  }

  function addTeamMessage(msg) {
    var div = document.createElement('div');
    div.className = 'msg ' + (msg.role || 'unknown');

    var roleSpan = document.createElement('span');
    roleSpan.className = 'role';
    roleSpan.textContent = '[' + (msg.role || '?') + ']';

    var tsSpan = document.createElement('span');
    tsSpan.className = 'ts';
    tsSpan.textContent = msg.timestamp ? msg.timestamp.substring(11, 19) : '';

    var contentSpan = document.createElement('span');
    contentSpan.textContent = msg.content || '';

    div.appendChild(roleSpan);
    div.appendChild(tsSpan);
    div.appendChild(contentSpan);
    teamBody.appendChild(div);
    scrollBottom(teamBody);
  }

  function addOutputLine(line) {
    var div = document.createElement('div');
    div.className = 'out-line';
    div.textContent = line;
    outputBody.appendChild(div);
    scrollBottom(outputBody);
  }

  function applyControlState(state) {
    if (state.paused) {
      pausedBadge.className = 'visible';
    } else {
      pausedBadge.className = '';
    }
  }

  // -------------------------------------------------------------------------
  // Team WebSocket
  // -------------------------------------------------------------------------

  function connectTeam() {
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var ws = new WebSocket(proto + '//' + location.host + '/ws/team');

    ws.onopen = function () {
      statusTeam.textContent = 'Team: connected';
      statusTeam.className = 'connected';
    };

    ws.onmessage = function (event) {
      try {
        var envelope = JSON.parse(event.data);
        if (envelope.type === 'team') {
          addTeamMessage(envelope.data);
        } else if (envelope.type === 'control') {
          applyControlState(envelope.data);
        }
      } catch (e) { /* malformed frame — ignore */ }
    };

    ws.onclose = function () {
      statusTeam.textContent = 'Team: reconnecting...';
      statusTeam.className = 'disconnected';
      setTimeout(connectTeam, 3000);
    };

    ws.onerror = function () { ws.close(); };
  }

  // -------------------------------------------------------------------------
  // Output WebSocket
  // -------------------------------------------------------------------------

  function connectOutput() {
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var ws = new WebSocket(proto + '//' + location.host + '/ws/output');

    ws.onopen = function () {
      statusOut.textContent = 'Output: connected';
      statusOut.className = 'connected';
    };

    ws.onmessage = function (event) {
      try {
        var envelope = JSON.parse(event.data);
        if (envelope.type === 'output') {
          addOutputLine(envelope.data);
        }
      } catch (e) { /* malformed frame — ignore */ }
    };

    ws.onclose = function () {
      statusOut.textContent = 'Output: reconnecting...';
      statusOut.className = 'disconnected';
      setTimeout(connectOutput, 3000);
    };

    ws.onerror = function () { ws.close(); };
  }

  // -------------------------------------------------------------------------
  // Intervention controls
  // -------------------------------------------------------------------------

  function doControl(action) {
    fetch('/control/' + action, { method: 'POST' })
      .catch(function (err) {
        console.error('Control action failed:', action, err);
      });
  }

  window.doControl = doControl;

  window.doInject = function () {
    var input = document.getElementById('inject-input');
    var msg = input.value.trim();
    if (!msg) { return; }
    fetch('/control/inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    }).then(function () {
      input.value = '';
    }).catch(function (err) {
      console.error('Inject failed:', err);
    });
  };

  // Allow Enter key in inject input
  document.getElementById('inject-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { window.doInject(); }
  });

  // -------------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------------

  connectTeam();
  connectOutput();
}());
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point for direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        raise SystemExit("Install uvicorn: pip install uvicorn")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
