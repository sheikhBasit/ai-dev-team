"""Main LangGraph orchestrator — wires all agents into the pipeline."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from ai_team.agents.architect import architect_agent
from ai_team.agents.codebase_indexer import build_codebase_index
from ai_team.agents.coder import coder_agent
from ai_team.agents.debugger import debugger_agent
from ai_team.agents.designer import designer_agent
from ai_team.agents.evaluator import evaluator_agent
from ai_team.agents.memory import (
    extract_lessons_from_evaluation,
    format_lessons_for_prompt,
    save_lesson,
)
from ai_team.agents.planner import planner_agent
from ai_team.agents.project_detector import detect_project_context
from ai_team.agents.requirements import requirements_agent
from ai_team.agents.reviewer import reviewer_agent
from ai_team.agents.security import security_agent
from ai_team.agents.tester import tester_agent
from ai_team.state import State
from ai_team.tools.rag_tools import set_rag_project
from ai_team.tools.shell_tools import set_project_sandbox

logger = logging.getLogger("ai_team.graph")

MAX_PHASE_REJECTIONS = 5  # max times user can reject a single phase


# ── Init node — runs once at start ──────────────────────────────────────────


def init_node(state: State) -> dict:
    """Initialize: detect project, build index, set sandbox, create git branch, load memory."""
    project_dir = state.get("project_dir", "")

    # Set file sandbox
    if project_dir:
        set_project_sandbox(project_dir)
        set_rag_project(project_dir)
        logger.info("Sandbox set to: %s", project_dir)

    # Detect project patterns
    context = ""
    if project_dir:
        context = detect_project_context(project_dir)
        logger.info("Project context detected (%d chars)", len(context))

    # Build codebase index (symbol map)
    index = ""
    if project_dir:
        index = build_codebase_index(project_dir)
        logger.info("Codebase indexed (%d chars)", len(index))

    # Build RAG semantic index (background, skipped if up-to-date)
    if project_dir:
        try:
            from ai_team.rag.store import build_index

            built = build_index(project_dir)
            if built:
                logger.info("RAG index built for %s", project_dir)
                context += "\n\n[RAG] Semantic codebase search is available via search_codebase tool."
            else:
                logger.info("RAG index already up-to-date")
        except Exception as e:
            logger.warning("RAG index build failed (non-fatal): %s", e)

    # Load task-relevant lessons via RAG (falls back to flat load if RAG unavailable)
    task = state.get("task", "")
    if project_dir:
        try:
            from ai_team.rag.lessons_rag import format_relevant_lessons, index_lessons
            from ai_team.agents.memory import load_lessons

            all_lessons = load_lessons(project_dir)
            if all_lessons:
                index_lessons(project_dir, all_lessons)
                relevant = format_relevant_lessons(project_dir, task) if task else ""
                if relevant:
                    context += f"\n\n{relevant}"
                    logger.info("Loaded relevant lessons via RAG")
                else:
                    # Fall back to flat load when no task yet or embedding unavailable
                    flat = format_lessons_for_prompt(project_dir)
                    if flat:
                        context += f"\n\n{flat}"
        except Exception as e:
            logger.warning("Lessons RAG failed, using flat load: %s", e)
            flat = format_lessons_for_prompt(project_dir)
            if flat:
                context += f"\n\n{flat}"

    # Create a working git branch
    if project_dir and Path(project_dir).joinpath(".git").exists():
        task_slug = re.sub(r"[^a-z0-9-]", "-", state.get("task", "task")[:40].lower())
        task_slug = re.sub(r"-+", "-", task_slug).strip("-")
        branch_name = f"ai-dev-team/{task_slug}"
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=project_dir,
                capture_output=True,
                timeout=10,
            )
            logger.info("Created git branch: %s", branch_name)
        except Exception as e:
            logger.warning("Could not create git branch: %s", e)

    return {
        "project_context": context,
        "codebase_index": index,
        "phase_rejections": 0,
        "messages": ["[Init] Project detected. Codebase indexed. RAG index ready. Pipeline starting."],
    }


# ── Pre-flight validation (before coding) ───────────────────────────────────

def preflight_node(state: State) -> dict:
    """Run pre-flight checks before coding starts."""
    project_dir = state.get("project_dir", "")
    messages = []

    if not project_dir:
        return {"messages": ["[Preflight] No project directory, skipping checks."]}

    # Check if linter is available
    try:
        result = subprocess.run(
            ["ruff", "check", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            messages.append(f"[Preflight] ruff available: {result.stdout.strip()}")
    except Exception:
        messages.append("[Preflight] ruff not found — code won't be auto-linted")

    # Check if tests can run
    test_dirs = ["tests", "test", "backend/api/tests"]
    for td in test_dirs:
        test_path = Path(project_dir) / td
        if test_path.exists():
            messages.append(f"[Preflight] Test directory found: {td}")
            break
    else:
        messages.append("[Preflight] No test directory found — tester may not work")

    # Check git status
    if Path(project_dir).joinpath(".git").exists():
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=project_dir, capture_output=True, text=True, timeout=5,
            )
            dirty_count = len(result.stdout.strip().splitlines()) if result.stdout.strip() else 0
            if dirty_count > 0:
                messages.append(f"[Preflight] WARNING: {dirty_count} uncommitted changes in project")
            else:
                messages.append("[Preflight] Git tree clean")
        except Exception:
            pass

    messages.append("[Preflight] Pre-flight complete. Starting code generation.")
    return {"messages": messages}


# ── Phase routing ────────────────────────────────────────────────────────────

def route_after_requirements(state: State) -> Literal["requirements", "designer"]:
    if state.get("phase") == "requirements":
        if state.get("phase_rejections", 0) >= MAX_PHASE_REJECTIONS:
            return "designer"  # force proceed
        return "requirements"
    return "designer"


def route_after_design(state: State) -> Literal["designer", "architect"]:
    if state.get("phase") == "design":
        if state.get("phase_rejections", 0) >= MAX_PHASE_REJECTIONS:
            return "architect"
        return "designer"
    return "architect"


def route_after_architecture(state: State) -> Literal["architect", "preflight"]:
    if state.get("phase") == "architecture":
        if state.get("phase_rejections", 0) >= MAX_PHASE_REJECTIONS:
            return "preflight"
        return "architect"
    return "preflight"


def fan_out_verification(state: State) -> list[Send]:
    """After coding, fan out to reviewer + tester + security + debugger in parallel."""
    return [
        Send("reviewer", state),
        Send("tester", state),
        Send("security", state),
        Send("debugger", state),
    ]


# ── Git commit node — after each coder iteration ────────────────────────────

def git_commit_node(state: State) -> dict:
    """Commit changes after coding so we can rollback if needed."""
    project_dir = state.get("project_dir", "")
    iteration = state.get("iteration", 0)

    if not project_dir or not Path(project_dir).joinpath(".git").exists():
        return {"messages": ["[Git] No git repo, skipping commit."]}

    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=project_dir, capture_output=True, timeout=10,
        )
        msg = f"ai-dev-team: iteration {iteration + 1} — auto-commit"
        result = subprocess.run(
            ["git", "commit", "-m", msg, "--allow-empty"],
            cwd=project_dir, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("Git commit: %s", msg)
            return {"messages": [f"[Git] Committed iteration {iteration + 1}"]}
        else:
            return {"messages": ["[Git] Nothing to commit (clean tree)"]}
    except Exception as e:
        logger.warning("Git commit failed: %s", e)
        return {"messages": [f"[Git] Commit failed: {e}"]}


# ── Learn lessons node — after evaluator ─────────────────────────────────────

def learn_lessons_node(state: State) -> dict:
    """Extract and save lessons from evaluation for future sessions."""
    project_dir = state.get("project_dir", "")
    evaluation = state.get("evaluation", "")
    all_findings = (
        state.get("review_findings", [])
        + state.get("test_results", [])
        + state.get("security_findings", [])
    )

    lessons = extract_lessons_from_evaluation(evaluation, all_findings)
    saved = []
    for lesson in lessons:
        if project_dir:
            save_lesson(project_dir, lesson, category="auto")
            saved.append(lesson)

    if saved:
        return {
            "lessons_learned": saved,
            "messages": [f"[Memory] Saved {len(saved)} lessons for future sessions."],
        }
    return {"messages": ["[Memory] No new lessons to save."]}


# ── Final human review with git diff ────────────────────────────────────────

def human_final_review(state: State) -> dict:
    """Final checkpoint — show git diff and results to user before shipping."""
    code_changes = state.get("code_changes", [])
    evaluation = state.get("evaluation", "")
    iteration = state.get("iteration", 0)
    project_dir = state.get("project_dir", "")

    # Get actual git diff
    diff_text = ""
    if project_dir and Path(project_dir).joinpath(".git").exists():
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD~1", "--stat"],
                cwd=project_dir, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                diff_text = f"\n## Git Diff Summary\n```\n{result.stdout[:3000]}\n```"

            # Get detailed diff (truncated)
            result = subprocess.run(
                ["git", "diff", "HEAD~1"],
                cwd=project_dir, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                full_diff = result.stdout
                if len(full_diff) > 5000:
                    full_diff = full_diff[:5000] + "\n... (diff truncated, run 'git diff HEAD~1' for full)"
                diff_text += f"\n\n## Detailed Changes\n```diff\n{full_diff}\n```"
        except Exception:
            pass

    output = (
        f"## Evaluation (after {iteration} iterations)\n\n{evaluation}\n\n"
        f"## Changed files ({len(code_changes)})\n"
        + "\n".join(f"- {f}" for f in code_changes)
        + diff_text
    )

    approval = interrupt({
        "agent": "Final Review",
        "phase": "done",
        "output": output,
        "question": "Ship it? (approve to commit, reject to abandon)",
    })

    if approval.get("decision") == "approved":
        return {
            "phase": "done",
            "git_diff": diff_text,
            "messages": ["[Ship] User approved. Ready to commit."],
        }
    else:
        return {
            "phase": "done",
            "messages": [f"[Abandoned] User rejected: {approval.get('feedback', '')}"],
        }


# ── CI check node ────────────────────────────────────────────────────────────

def ci_check_node(state: State) -> dict:
    """Run the same checks CI would run before declaring success."""
    project_dir = state.get("project_dir", "")
    messages = []

    if not project_dir:
        return {"messages": ["[CI] No project directory."]}

    # Run ruff check if available
    try:
        result = subprocess.run(
            ["ruff", "check", "."],
            cwd=project_dir, capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            messages.append("[CI] ruff check: PASSED")
        else:
            error_lines = result.stdout.strip().splitlines()[:10]
            messages.append(f"[CI] ruff check: FAILED ({len(error_lines)} issues)")
    except FileNotFoundError:
        messages.append("[CI] ruff not available, skipping lint")
    except Exception as e:
        messages.append(f"[CI] ruff error: {e}")

    # Run pyright if available
    try:
        result = subprocess.run(
            ["pyright", "--outputjson"],
            cwd=project_dir, capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            messages.append("[CI] pyright: PASSED")
        else:
            messages.append("[CI] pyright: WARNINGS/ERRORS found")
    except FileNotFoundError:
        pass
    except Exception:
        pass

    if not messages:
        messages.append("[CI] No CI tools available to run.")

    return {"messages": messages}


# ── Build the graph ──────────────────────────────────────────────────────────

def build_graph():
    """Build and compile the AI Dev Team graph."""
    builder = StateGraph(State)

    # Add all nodes
    builder.add_node("init", init_node)
    builder.add_node("requirements", requirements_agent)
    builder.add_node("designer", designer_agent)
    builder.add_node("architect", architect_agent)
    builder.add_node("preflight", preflight_node)
    builder.add_node("planner", planner_agent)
    builder.add_node("coder", coder_agent)
    builder.add_node("git_commit", git_commit_node)
    builder.add_node("reviewer", reviewer_agent)
    builder.add_node("tester", tester_agent)
    builder.add_node("security", security_agent)
    builder.add_node("debugger", debugger_agent)
    builder.add_node("evaluator", evaluator_agent)
    builder.add_node("learn_lessons", learn_lessons_node)
    builder.add_node("ci_check", ci_check_node)
    builder.add_node("human_final_review", human_final_review)

    # START → init → requirements
    builder.add_edge(START, "init")
    builder.add_edge("init", "requirements")

    # Phase 1: Requirements (with human approval loop, max rejections)
    builder.add_conditional_edges("requirements", route_after_requirements)

    # Phase 2: Design (with human approval loop)
    builder.add_conditional_edges("designer", route_after_design)

    # Phase 3: Architecture (with human approval loop) → preflight
    builder.add_conditional_edges("architect", route_after_architecture)

    # Phase 3.5: Preflight → planner → coder
    builder.add_edge("preflight", "planner")
    builder.add_edge("planner", "coder")

    # Phase 4: Code → git commit → parallel verification
    builder.add_edge("coder", "git_commit")
    builder.add_conditional_edges("git_commit", fan_out_verification, ["reviewer", "tester", "security", "debugger"])

    # Phase 5: Verification agents → evaluator
    builder.add_edge("reviewer", "evaluator")
    builder.add_edge("tester", "evaluator")
    builder.add_edge("security", "evaluator")
    builder.add_edge("debugger", "evaluator")

    # Phase 6: Evaluator → Command routes to "coder" or "learn_lessons"
    # (evaluator uses Command(goto=...) so no explicit edges needed here,
    #  but we need to update evaluator to go to learn_lessons instead of human_final_review)

    # Phase 6.5: Learn lessons → CI check → human final review
    builder.add_edge("learn_lessons", "ci_check")
    builder.add_edge("ci_check", "human_final_review")

    # Phase 7: Final → END
    builder.add_edge("human_final_review", END)

    # Compile with checkpointer
    from langgraph.checkpoint.memory import InMemorySaver

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3

        db_path = os.getenv("CHECKPOINT_DB", os.path.expanduser("~/.ai-dev-team/checkpoints.db"))
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
    except Exception:
        logger.warning("SQLite checkpointer failed, using in-memory (sessions won't persist)")
        checkpointer = InMemorySaver()

    graph = builder.compile(checkpointer=checkpointer)
    return graph
