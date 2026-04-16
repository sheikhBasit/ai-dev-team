"""FastAPI live dashboard — streams agent messages via WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger("ai_team.web")


def create_app():
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import HTMLResponse
    except ImportError:
        raise ImportError("Install fastapi and uvicorn: pip install fastapi uvicorn")

    from ai_team.bus import bus

    app = FastAPI(title="AI Dev Team Dashboard")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(content=_dashboard_html())

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        logger.info("Dashboard client connected")
        sent_count = 0
        try:
            while True:
                all_msgs = bus.all_messages()
                if len(all_msgs) > sent_count:
                    for msg in all_msgs[sent_count:]:
                        await websocket.send_text(json.dumps(msg))
                    sent_count = len(all_msgs)
                await asyncio.sleep(0.5)
        except WebSocketDisconnect:
            logger.info("Dashboard client disconnected")
        except Exception as e:
            logger.warning("WebSocket error: %s", e)

    @app.get("/messages")
    async def get_messages():
        return {"messages": bus.all_messages()}

    @app.get("/health")
    async def health():
        return {"status": "ok", "message_count": len(bus.all_messages())}

    return app


def _dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Dev Team — Live Dashboard</title>
<style>
  body { font-family: monospace; background: #0d1117; color: #c9d1d9; margin: 0; padding: 16px; }
  h1 { color: #58a6ff; font-size: 1.2rem; margin-bottom: 8px; }
  #status { font-size: 0.8rem; margin-bottom: 12px; }
  #status.connected { color: #3fb950; }
  #status.disconnected { color: #f85149; }
  #messages { list-style: none; padding: 0; margin: 0; }
  #messages li { padding: 6px 10px; margin-bottom: 4px; border-radius: 4px; background: #161b22; border-left: 3px solid #30363d; font-size: 0.85rem; }
  #messages li.coder { border-left-color: #58a6ff; }
  #messages li.reviewer { border-left-color: #f0883e; }
  #messages li.architect { border-left-color: #bc8cff; }
  #messages li.tester { border-left-color: #3fb950; }
  #messages li.security { border-left-color: #f85149; }
  #messages li.debugger { border-left-color: #ffa657; }
  #messages li.planner { border-left-color: #79c0ff; }
  #messages li.docs { border-left-color: #56d364; }
  .role { font-weight: bold; margin-right: 8px; }
  .ts { color: #6e7681; font-size: 0.75rem; margin-right: 8px; }
  #count { color: #6e7681; font-size: 0.8rem; margin-top: 8px; }
</style>
</head>
<body>
<h1>AI Dev Team — Live Dashboard</h1>
<div id="status" class="disconnected">Connecting...</div>
<ul id="messages"></ul>
<div id="count"></div>
<script>
(function() {
  var list = document.getElementById('messages');
  var statusEl = document.getElementById('status');
  var countEl = document.getElementById('count');
  var total = 0;

  function addMessage(msg) {
    var li = document.createElement('li');
    li.className = msg.role || 'unknown';

    var roleSpan = document.createElement('span');
    roleSpan.className = 'role';
    roleSpan.textContent = '[' + (msg.role || '?') + ']';

    var tsSpan = document.createElement('span');
    tsSpan.className = 'ts';
    var ts = msg.timestamp ? msg.timestamp.substring(11, 19) : '';
    tsSpan.textContent = ts;

    var contentSpan = document.createElement('span');
    contentSpan.textContent = msg.content || '';

    li.appendChild(roleSpan);
    li.appendChild(tsSpan);
    li.appendChild(contentSpan);
    list.appendChild(li);

    total++;
    countEl.textContent = total + ' messages';
    window.scrollTo(0, document.body.scrollHeight);
  }

  function connect() {
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var ws = new WebSocket(proto + '//' + location.host + '/ws');

    ws.onopen = function() {
      statusEl.textContent = 'Connected';
      statusEl.className = 'connected';
    };

    ws.onmessage = function(event) {
      try {
        var msg = JSON.parse(event.data);
        addMessage(msg);
      } catch(e) {}
    };

    ws.onclose = function() {
      statusEl.textContent = 'Disconnected — reconnecting in 3s...';
      statusEl.className = 'disconnected';
      setTimeout(connect, 3000);
    };

    ws.onerror = function() {
      ws.close();
    };
  }

  connect();
})();
</script>
</body>
</html>"""


# Entry point for direct execution
if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        raise SystemExit("Install uvicorn: pip install uvicorn")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
