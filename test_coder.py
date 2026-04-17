#!/usr/bin/env python3
"""Direct coder agent test — skips requirements/designer/architect pipeline.

Usage:
  .venv/bin/python test_coder.py                    # frontend_web agent (default)
  .venv/bin/python test_coder.py --agent coder      # generic coder agent
  .venv/bin/python test_coder.py --agent frontend_web
  .venv/bin/python test_coder.py --project /path/to/project --task "your task"
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel

console = Console()


AGENTS = {
    "frontend_web":    "ai_team.agents.frontend_web.frontend_web_agent",
    "frontend_mobile": "ai_team.agents.frontend_mobile.frontend_mobile_agent",
    "frontend_desktop":"ai_team.agents.frontend_desktop.frontend_desktop_agent",
    "coder":           "ai_team.agents.coder.coder_agent",
    "auditor":         "ai_team.agents.auditor.auditor_agent",
    "reviewer":        "ai_team.agents.reviewer.reviewer_agent",
    "tester":          "ai_team.agents.tester.tester_agent",
    "security":        "ai_team.agents.security.security_agent",
}

# ── Pre-built state for MeetSync chat feature ────────────────────────────────

MEETSYNC_CHAT_STATE = {
    "task": (
        "Add in-call text chat panel to MeetSync.\n"
        "1. Create ChatPanel.tsx component with message list + text input\n"
        "2. Wire useDataChannel('chat') in Room.tsx alongside existing 'transcript' channel\n"
        "3. On send: publish message via DataChannel AND call POST /v1/meetings/{id}/chat\n"
        "4. Display sender name, message text, and timestamp in the panel\n"
        "5. Auto-scroll to latest message"
    ),
    "project_dir": "/home/basitdev/Me/MeetSync",
    "project_context": (
        "MeetSync is a self-hosted video meeting platform built with:\n"
        "- Frontend: Next.js 15 App Router, TypeScript, @livekit/components-react\n"
        "- Backend: FastAPI + SQLAlchemy + PostgreSQL\n"
        "- Real-time: LiveKit Server (Docker)\n"
        "- Existing DataChannel: 'transcript' channel already used in Room.tsx via useDataChannel\n"
        "- CSS Modules used for component styling (*.module.css files exist)\n"
        "- No shadcn/ui — plain Tailwind + CSS modules\n"
    ),
    "architecture_spec": (
        "Chat panel architecture:\n\n"
        "Frontend:\n"
        "- New file: frontend/src/components/ChatPanel.tsx\n"
        "- New file: frontend/src/components/ChatPanel.module.css\n"
        "- Modify: frontend/src/components/Room.tsx\n"
        "  - Add useDataChannel('chat') hook\n"
        "  - On receive: append to chatMessages state array\n"
        "  - On send: call room.localParticipant.publishData() on 'chat' channel\n"
        "    AND call fetch('/api/meetings/{id}/chat', {method: POST, body: {sender_name, text}})\n"
        "  - Render <ChatPanel> alongside <TranscriptSidebar>\n\n"
        "DataChannel message format (JSON):\n"
        "  { type: 'chat', sender: 'display_name', text: 'hello', ts: 'ISO8601' }\n\n"
        "ChatPanel props:\n"
        "  messages: Array<{sender: string, text: string, ts: string, isSelf: boolean}>\n"
        "  onSend: (text: string) => void\n\n"
        "Backend (to be done separately — frontend only for this run):\n"
        "  POST /v1/meetings/{id}/chat — persists message to chat_messages table\n"
    ),
    "work_items": [
        {
            "title": "ChatPanel component",
            "description": "Message list with auto-scroll + text input + send button",
            "priority": 1,
            "files_hint": [
                "frontend/src/components/ChatPanel.tsx",
                "frontend/src/components/ChatPanel.module.css",
            ],
        },
        {
            "title": "Wire chat into Room.tsx",
            "description": "Add useDataChannel('chat'), chatMessages state, render ChatPanel",
            "priority": 1,
            "files_hint": ["frontend/src/components/Room.tsx"],
        },
    ],
    "inject_message": "",
    "total_tokens": 0,
}


def import_agent(agent_name: str):
    import importlib
    path = AGENTS[agent_name]
    module_path, fn_name = path.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, fn_name)


def main():
    parser = argparse.ArgumentParser(description="Direct coder agent test")
    parser.add_argument("--agent", default="frontend_web", choices=list(AGENTS.keys()))
    parser.add_argument("--project", type=str, help="Override project_dir")
    parser.add_argument("--task", type=str, help="Override task")
    args = parser.parse_args()

    state = dict(MEETSYNC_CHAT_STATE)
    if args.project:
        state["project_dir"] = args.project
    if args.task:
        state["task"] = args.task

    # Set project dir for RAG + tools
    from ai_team.tools import shell_tools, rag_tools
    shell_tools.set_project_sandbox(state["project_dir"])
    rag_tools.set_rag_project(state["project_dir"])

    console.print(Panel(
        f"[bold]Agent:[/bold] {args.agent}\n"
        f"[bold]Project:[/bold] {state['project_dir']}\n"
        f"[bold]Model:[/bold] {os.getenv('LLM_MODEL', 'default')}\n"
        f"[bold]Provider:[/bold] {os.getenv('LLM_PROVIDER', 'auto')}",
        title="[bold green]Direct Coder Test[/bold green]",
        border_style="green",
    ))

    agent_fn = import_agent(args.agent)

    try:
        result = agent_fn(state)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)

    console.print()
    changed = result.get("code_changes", [])
    tokens = result.get("total_tokens", 0)

    console.print(Panel(
        f"[bold]Files changed:[/bold] {len(changed)}\n"
        + ("\n".join(f"  - {f}" for f in changed) + "\n" if changed else "  (none)\n")
        + f"\n[bold]Tokens used:[/bold] {tokens:,}",
        title="[bold blue]Result[/bold blue]",
        border_style="blue",
    ))


if __name__ == "__main__":
    main()
