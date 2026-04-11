#!/usr/bin/env python3
"""CLI runner for the AI Dev Team — with progress, cost tracking, and proper interrupts."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from ai_team.config import get_max_iterations, get_project_dir
from ai_team.graph import build_graph

console = Console()

# ── Logging setup ────────────────────────────────────────────────────────────

LOG_DIR = os.path.expanduser("~/.ai-dev-team/logs")
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging(verbose: bool = False):
    log_file = os.path.join(LOG_DIR, "ai-dev-team.log")
    log_handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
    if verbose:
        log_handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=log_handlers,
    )


# ── Startup validation ──────────────────────────────────────────────────────

def validate_startup(project_dir: str | None):
    errors = []
    api_keys = [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
        "GROQ_API_KEY", "TOGETHER_API_KEY", "FIREWORKS_API_KEY",
        "MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "HUGGINGFACEHUB_API_TOKEN",
    ]
    has_key = any(os.getenv(k) for k in api_keys)
    provider = os.getenv("LLM_PROVIDER", "")
    if not has_key and provider not in ("ollama", "openai_compat"):
        errors.append(
            "No API key found. Set at least one in .env:\n"
            "  ANTHROPIC_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, etc.\n"
            "  Or use LLM_PROVIDER=ollama for local models."
        )
    if project_dir:
        from pathlib import Path
        p = Path(project_dir).expanduser()
        if not p.exists():
            errors.append(f"Project directory not found: {project_dir}")
        elif not p.is_dir():
            errors.append(f"Not a directory: {project_dir}")
    if errors:
        for err in errors:
            console.print(f"[red]ERROR:[/red] {err}")
        sys.exit(1)


# ── Progress callback ───────────────────────────────────────────────────────

def make_progress_callback():
    """Create a progress callback that updates console."""
    def callback(agent: str, iteration: int, max_iter: int, action: str):
        console.print(f"  [dim][{agent}] step {iteration}/{max_iter}: {action}[/dim]")
    return callback


# ── Human-in-the-loop handler ───────────────────────────────────────────────

def handle_interrupt(interrupt_value: dict) -> dict:
    agent = interrupt_value.get("agent", "Agent")
    output = interrupt_value.get("output", "")
    question = interrupt_value.get("question", "Approve?")

    console.print()
    console.print(Panel(
        Markdown(output),
        title=f"[bold cyan]{agent}[/bold cyan]",
        border_style="cyan",
        expand=True,
    ))
    console.print()
    console.print(f"[bold yellow]{question}[/bold yellow]")
    console.print("[dim]Options: approve / reject / or type your feedback directly[/dim]")

    response = Prompt.ask("Your decision").strip().lower()

    if response in ("approve", "approved", "yes", "y", "ship", "lgtm", "ok"):
        return {"decision": "approved"}
    else:
        feedback = response if response not in ("reject", "rejected", "no", "n") else ""
        if not feedback:
            feedback = Prompt.ask("What should be changed?")
        return {"decision": "rejected", "feedback": feedback}


# ── Main run loop ────────────────────────────────────────────────────────────

def run(
    task: str,
    project_dir: str | None = None,
    thread_id: str | None = None,
    start_phase: str | None = None,
    verbose: bool = False,
):
    setup_logging(verbose)

    resolved_project = get_project_dir(project_dir)
    validate_startup(resolved_project)

    # Set up progress streaming
    from ai_team.agents.react_loop import get_token_usage, reset_token_usage, set_progress_callback
    reset_token_usage()
    set_progress_callback(make_progress_callback())

    tid = thread_id or str(uuid.uuid4())

    console.print(Panel(
        f"[bold]Task:[/bold] {task}\n"
        f"[bold]Project:[/bold] {resolved_project}\n"
        f"[bold]Thread:[/bold] {tid}\n"
        f"[bold]Model:[/bold] {os.getenv('LLM_MODEL', 'claude-sonnet-4-20250514')}",
        title="[bold green]AI Dev Team[/bold green]",
        border_style="green",
    ))
    console.print(f"[dim]Resume: python run.py --thread-id {tid}[/dim]")
    console.print(f"[dim]Logs:   {LOG_DIR}/ai-dev-team.log[/dim]\n")

    graph = build_graph()
    config = {"configurable": {"thread_id": tid}}

    initial_state = {
        "task": task,
        "project_dir": resolved_project,
        "phase": start_phase or "requirements",
        "iteration": 0,
        "max_iterations": get_max_iterations(),
    }

    graph_input = initial_state

    while True:
        # Stream the graph — pauses at interrupt() calls
        for event in graph.stream(graph_input, config, stream_mode="updates"):
            for node_name, update in event.items():
                if isinstance(update, dict):
                    messages = update.get("messages", [])
                    for msg in messages:
                        console.print(f"  {msg}")

                    phase = update.get("phase", "")
                    if phase:
                        console.print(f"  [dim]Phase → {phase}[/dim]")

        # Check state
        state = graph.get_state(config)

        if not state.next:
            console.print("\n[bold green]Pipeline complete![/bold green]")
            break

        # Handle interrupts
        handled = False
        if state.tasks:
            for task_obj in state.tasks:
                if hasattr(task_obj, "interrupts") and task_obj.interrupts:
                    for intr in task_obj.interrupts:
                        interrupt_value = intr.value if hasattr(intr, "value") else {}
                        approval = handle_interrupt(interrupt_value)

                        from langgraph.types import Command
                        graph_input = Command(resume=approval)
                        handled = True

        if not handled:
            # state.next exists but no interrupts — graph may be stuck
            console.print("[yellow]Graph paused with no interrupt. Check logs.[/yellow]")
            console.print(f"[dim]Pending nodes: {state.next}[/dim]")
            break

    # ── Final summary with cost tracking ─────────────────────────────────────
    final_state = graph.get_state(config)
    token_usage = get_token_usage()
    model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
    token_usage.estimate_cost(model)

    console.print()
    console.print(Panel(
        _build_summary(final_state.values, token_usage),
        title="[bold]Session Summary[/bold]",
        border_style="blue",
    ))


def _build_summary(values: dict, token_usage) -> str:
    lines = []

    changes = values.get("code_changes", [])
    if changes:
        lines.append(f"**Files modified:** {len(changes)}")
        for f in changes[:15]:
            lines.append(f"  - {f}")
        if len(changes) > 15:
            lines.append(f"  ... and {len(changes) - 15} more")

    iterations = values.get("iteration", 0)
    lines.append(f"\n**Iterations:** {iterations}")

    passed = values.get("all_passed", False)
    status = "PASSED" if passed else "SHIPPED WITH WARNINGS"
    lines.append(f"**Status:** {status}")

    # Token usage
    if token_usage.total_tokens > 0:
        lines.append(f"\n**Tokens:** {token_usage.total_tokens:,} ({token_usage.calls} LLM calls)")
        lines.append(f"  Input: {token_usage.input_tokens:,} | Output: {token_usage.output_tokens:,}")
        lines.append(f"**Estimated cost:** ${token_usage.estimated_cost:.2f}")

    # Lessons learned
    lessons = values.get("lessons_learned", [])
    if lessons:
        lines.append(f"\n**Lessons saved:** {len(lessons)}")
        for l in lessons[:5]:
            lines.append(f"  - {l}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="AI Dev Team — Your autonomous engineering team",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py --task "Add a webhook endpoint for Slack"
  python run.py --project ~/my-project --task "Fix auth bug"
  python run.py --thread-id abc123  # resume session
  python run.py --task "Add caching" --start-phase code
  python run.py --task "Refactor auth" -v  # verbose logging
        """,
    )
    parser.add_argument("--task", "-t", type=str, help="What to build/fix")
    parser.add_argument("--project", "-p", type=str, help="Project directory to work on")
    parser.add_argument("--thread-id", type=str, help="Resume a previous session")
    parser.add_argument("--start-phase", type=str, choices=[
        "requirements", "design", "architecture", "code",
    ], help="Skip to a specific phase")
    parser.add_argument("--model", "-m", type=str, help="LLM model to use (overrides .env LLM_MODEL)")
    parser.add_argument("--provider", type=str, help="LLM provider to use (overrides .env LLM_PROVIDER)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging to console")

    args = parser.parse_args()

    # Apply model/provider overrides before anything reads from env
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider

    if not args.task and not args.thread_id:
        console.print("[bold]What should the team build?[/bold]")
        args.task = Prompt.ask("Task")

    if not args.task and not args.thread_id:
        console.print("[red]No task provided. Exiting.[/red]")
        sys.exit(1)

    try:
        run(
            task=args.task or "",
            project_dir=args.project,
            thread_id=args.thread_id,
            start_phase=args.start_phase,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Session saved — resume with --thread-id[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
