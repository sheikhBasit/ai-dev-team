#!/usr/bin/env python3
"""CLI runner for the AI Dev Team."""

from __future__ import annotations

import argparse
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


def handle_interrupt(graph, config, interrupt_data: dict) -> dict:
    """Handle a human-in-the-loop interrupt."""
    agent = interrupt_data.get("agent", "Agent")
    output = interrupt_data.get("output", "")
    question = interrupt_data.get("question", "Approve?")

    console.print()
    console.print(Panel(
        Markdown(output),
        title=f"[bold cyan]{agent}[/bold cyan]",
        border_style="cyan",
        expand=True,
    ))
    console.print()
    console.print(f"[bold yellow]{question}[/bold yellow]")
    console.print("[dim]Options: approve / reject / or type feedback[/dim]")

    response = Prompt.ask("Your decision").strip().lower()

    if response in ("approve", "approved", "yes", "y", "ship", "lgtm"):
        return {"decision": "approved"}
    else:
        feedback = response if response not in ("reject", "rejected", "no", "n") else ""
        if not feedback:
            feedback = Prompt.ask("What should be changed?")
        return {"decision": "rejected", "feedback": feedback}


def run(task: str, project_dir: str | None = None, thread_id: str | None = None, start_phase: str | None = None):
    """Run the AI Dev Team on a task."""
    console.print(Panel(
        f"[bold]Task:[/bold] {task}\n[bold]Project:[/bold] {get_project_dir(project_dir)}\n[bold]Thread:[/bold] {thread_id or 'new'}",
        title="[bold green]AI Dev Team[/bold green]",
        border_style="green",
    ))

    graph = build_graph()

    config = {
        "configurable": {
            "thread_id": thread_id or str(uuid.uuid4()),
        }
    }

    initial_state = {
        "task": task,
        "project_dir": get_project_dir(project_dir),
        "phase": start_phase or "requirements",
        "iteration": 0,
        "max_iterations": get_max_iterations(),
    }

    console.print(f"\n[dim]Thread ID: {config['configurable']['thread_id']}[/dim]")
    console.print("[dim]Use this ID to resume: python run.py --thread-id <id>[/dim]\n")

    # Stream the graph execution
    try:
        # Use stream to watch progress
        for event in graph.stream(initial_state, config, stream_mode="updates"):
            for node_name, update in event.items():
                # Print agent messages
                messages = update.get("messages", [])
                for msg in messages:
                    console.print(f"  {msg}")

                phase = update.get("phase", "")
                if phase:
                    console.print(f"  [dim]Phase: {phase}[/dim]")

    except Exception as e:
        # Check if this is an interrupt (human-in-the-loop)
        error_str = str(e)
        if "interrupt" in error_str.lower() or hasattr(e, "__cause__"):
            # Get the graph state to find the interrupt
            state = graph.get_state(config)

            while state.next:  # While there are pending interrupts
                # Get interrupt data
                interrupts = state.tasks
                for task_obj in interrupts:
                    if hasattr(task_obj, "interrupts") and task_obj.interrupts:
                        for intr in task_obj.interrupts:
                            interrupt_data = intr.value if hasattr(intr, "value") else {}
                            approval = handle_interrupt(graph, config, interrupt_data)

                            # Resume with the approval
                            from langgraph.types import Command

                            for event in graph.stream(
                                Command(resume=approval),
                                config,
                                stream_mode="updates",
                            ):
                                for node_name, update in event.items():
                                    msgs = update.get("messages", [])
                                    for msg in msgs:
                                        console.print(f"  {msg}")

                state = graph.get_state(config)
        else:
            console.print(f"[red]Error: {e}[/red]")
            raise

    console.print("\n[bold green]Done![/bold green]")


def main():
    parser = argparse.ArgumentParser(description="AI Dev Team — Your autonomous engineering team")
    parser.add_argument("--task", "-t", type=str, help="What to build/fix")
    parser.add_argument("--project", "-p", type=str, help="Project directory to work on")
    parser.add_argument("--thread-id", type=str, help="Resume a previous session")
    parser.add_argument("--start-phase", type=str, choices=[
        "requirements", "design", "architecture", "code", "review", "test",
    ], help="Skip to a specific phase")

    args = parser.parse_args()

    if not args.task and not args.thread_id:
        console.print("[bold]What should the team build?[/bold]")
        args.task = Prompt.ask("Task")

    if not args.task and not args.thread_id:
        console.print("[red]No task provided. Exiting.[/red]")
        sys.exit(1)

    run(
        task=args.task or "",
        project_dir=args.project,
        thread_id=args.thread_id,
        start_phase=args.start_phase,
    )


if __name__ == "__main__":
    main()
