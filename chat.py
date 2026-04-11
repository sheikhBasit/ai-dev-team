#!/usr/bin/env python3
"""Persistent chat CLI — talk to your AI dev team like a messaging app."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ai_team.config import get_llm, get_project_dir

console = Console()

CHAT_DIR = os.path.expanduser("~/.ai-dev-team")
HISTORY_FILE = os.path.join(CHAT_DIR, "chat_history.json")
os.makedirs(CHAT_DIR, exist_ok=True)


# ── Chat history persistence ────────────────────────────────────────────────

def load_history() -> list[dict]:
    if Path(HISTORY_FILE).exists():
        try:
            return json.loads(Path(HISTORY_FILE).read_text())[-50:]  # keep last 50
        except Exception:
            return []
    return []


def save_history(history: list[dict]):
    Path(HISTORY_FILE).write_text(json.dumps(history[-100:], indent=2))


def add_message(history: list[dict], role: str, text: str) -> list[dict]:
    history.append({
        "role": role,
        "text": text,
        "time": datetime.now().strftime("%H:%M"),
    })
    save_history(history)
    return history


# ── Display ──────────────────────────────────────────────────────────────────

def show_message(role: str, text: str, timestamp: str = ""):
    time_str = f" [dim]{timestamp}[/dim]" if timestamp else ""
    if role == "user":
        console.print(Panel(
            text,
            title=f"[bold green]You[/bold green]{time_str}",
            border_style="green",
            title_align="left",
            padding=(0, 1),
        ))
    elif role == "system":
        console.print(f"  [dim]{text}[/dim]")
    else:
        console.print(Panel(
            Markdown(text),
            title=f"[bold cyan]Team[/bold cyan]{time_str}",
            border_style="cyan",
            title_align="left",
            padding=(0, 1),
        ))


def show_recent_history(history: list[dict], count: int = 5):
    recent = history[-count:] if len(history) > count else history
    if recent:
        console.print("[dim]─── Recent messages ───[/dim]")
        for msg in recent:
            show_message(msg["role"], msg["text"], msg.get("time", ""))
        console.print("[dim]──────────────────────[/dim]\n")


# ── Commands ─────────────────────────────────────────────────────────────────

COMMANDS = {
    "/build": "Start building a feature (enters full pipeline)",
    "/fix": "Fix a bug (skips to coding phase)",
    "/status": "Show project status and config",
    "/history": "Show chat history",
    "/clear": "Clear chat history",
    "/project": "Change project directory",
    "/model": "Show/change current model",
    "/cost": "Show token usage this session",
    "/help": "Show available commands",
    "/quit": "Exit chat",
}


def handle_command(cmd: str, args: str, history: list[dict]) -> str | None:
    """Handle slash commands. Returns response text or None."""
    if cmd == "/help":
        table = Table(title="Commands", show_header=False, border_style="dim")
        for c, desc in COMMANDS.items():
            table.add_row(f"[cyan]{c}[/]", desc)
        console.print(table)
        return None

    elif cmd == "/build":
        if not args:
            return "Usage: /build <description of what to build>"
        console.print(f"\n[bold]Starting pipeline for:[/bold] {args}\n")
        os.system(f'source {os.path.dirname(__file__)}/.venv/bin/activate && python {os.path.dirname(__file__)}/run.py -t "{args}"')
        return None

    elif cmd == "/fix":
        if not args:
            return "Usage: /fix <description of the bug>"
        console.print(f"\n[bold]Fixing:[/bold] {args}\n")
        os.system(f'source {os.path.dirname(__file__)}/.venv/bin/activate && python {os.path.dirname(__file__)}/run.py -t "{args}" --start-phase code')
        return None

    elif cmd == "/status":
        project = get_project_dir()
        model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
        return f"**Project:** {project}\n**Model:** {model}\n**History:** {len(history)} messages"

    elif cmd == "/history":
        if not history:
            return "No chat history yet."
        show_recent_history(history, count=20)
        return None

    elif cmd == "/clear":
        history.clear()
        save_history(history)
        console.clear()
        return "Chat history cleared."

    elif cmd == "/project":
        if not args:
            return f"Current project: {get_project_dir()}\nUsage: /project <path>"
        os.environ["DEFAULT_PROJECT_DIR"] = os.path.expanduser(args)
        return f"Project set to: {args}"

    elif cmd == "/model":
        if not args:
            return f"Current model: {os.getenv('LLM_MODEL', 'claude-sonnet-4-20250514')}"
        os.environ["LLM_MODEL"] = args
        return f"Model set to: {args}"

    elif cmd == "/cost":
        from ai_team.agents.react_loop import get_token_usage
        usage = get_token_usage()
        model = os.getenv("LLM_MODEL", "")
        usage.estimate_cost(model)
        return (
            f"**Tokens:** {usage.total_tokens:,} ({usage.calls} calls)\n"
            f"**Input:** {usage.input_tokens:,} | **Output:** {usage.output_tokens:,}\n"
            f"**Est. cost:** ${usage.estimated_cost:.2f}"
        )

    elif cmd == "/quit":
        console.print("[dim]Goodbye![/dim]")
        sys.exit(0)

    return f"Unknown command: {cmd}. Type /help for available commands."


# ── Chat with LLM ───────────────────────────────────────────────────────────

def chat_response(user_text: str, history: list[dict]) -> str:
    """Get a response from the LLM with conversation context."""
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

    project = get_project_dir()
    project_context = ""
    try:
        from ai_team.agents.project_detector import detect_project_context
        project_context = detect_project_context(project)[:1500]
    except Exception:
        pass

    system_msg = f"""You are the lead of an AI engineering team. You help the user plan, discuss, and make decisions about their software projects.

Current project: {project}
{f"Project context: {project_context}" if project_context else ""}

You can:
- Discuss architecture, design, and implementation approaches
- Answer questions about the codebase
- Help plan features and break them into tasks
- Suggest best practices

When the user is ready to build, tell them to use /build or /fix commands.
Keep responses concise — this is a chat, not a document."""

    # Build message history for LLM (last 10 messages for context)
    messages = [SystemMessage(content=system_msg)]
    for msg in history[-10:]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["text"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["text"]))
    messages.append(HumanMessage(content=user_text))

    try:
        llm = get_llm(temperature=0.3)
        from ai_team.agents.react_loop import invoke_llm_with_retry
        response = invoke_llm_with_retry(llm, messages)
        return response.content
    except Exception as e:
        return f"Error: {e}\n\nMake sure your API key is set in .env"


# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    console.print(Panel(
        "[bold]AI Dev Team Chat[/bold]\n"
        "Talk to your engineering team. Type /help for commands.\n"
        "Use /build or /fix when ready to start coding.",
        border_style="blue",
    ))

    history = load_history()
    show_recent_history(history)

    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory

        prompt_history = os.path.join(CHAT_DIR, "prompt_history")
        session = PromptSession(history=FileHistory(prompt_history))
        get_input = lambda: session.prompt("You> ")
    except ImportError:
        get_input = lambda: input("You> ")

    while True:
        try:
            user_input = get_input().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session saved. Goodbye![/dim]")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            parts = user_input.split(" ", 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            result = handle_command(cmd, args, history)
            if result:
                show_message("assistant", result)
                history = add_message(history, "assistant", result)
            continue

        # Regular chat message
        show_message("user", user_input)
        history = add_message(history, "user", user_input)

        with console.status("[bold cyan]Thinking...[/]"):
            response = chat_response(user_input, history)

        show_message("assistant", response)
        history = add_message(history, "assistant", response)


if __name__ == "__main__":
    main()
