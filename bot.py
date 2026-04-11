#!/usr/bin/env python3
"""Telegram bot — control your AI dev team from your phone."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ai_team.bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS = os.getenv("TELEGRAM_ALLOWED_USERS", "")  # comma-separated IDs
AI_TEAM_DIR = Path(__file__).parent
VENV_PYTHON = AI_TEAM_DIR / ".venv" / "bin" / "python"


def check_deps():
    try:
        from telegram import Update  # noqa: F401
    except ImportError:
        print("Installing python-telegram-bot...")
        subprocess.run(
            [str(VENV_PYTHON), "-m", "pip", "install", "python-telegram-bot"],
            check=True,
        )


def get_allowed_users() -> set[int]:
    if not ALLOWED_USER_IDS:
        return set()
    try:
        return {int(uid.strip()) for uid in ALLOWED_USER_IDS.split(",") if uid.strip()}
    except ValueError:
        return set()


# ── Lazy imports (after dep check) ──────────────────────────────────────────

def create_bot():
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

    allowed_users = get_allowed_users()

    def is_authorized(update: Update) -> bool:
        if not allowed_users:
            return True  # no restriction if not configured
        return update.effective_user and update.effective_user.id in allowed_users

    # ── Chat state per user ──────────────────────────────────────────────────
    user_history: dict[int, list[dict]] = {}

    def get_history(user_id: int) -> list[dict]:
        if user_id not in user_history:
            user_history[user_id] = []
        return user_history[user_id]

    # ── Handlers ─────────────────────────────────────────────────────────────

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update):
            await update.message.reply_text("Unauthorized. Add your user ID to TELEGRAM_ALLOWED_USERS in .env")
            return
        await update.message.reply_text(
            "AI Dev Team Bot\n\n"
            "Commands:\n"
            "/build <task> — Build a feature\n"
            "/fix <bug> — Fix a bug\n"
            "/status — Show project config\n"
            "/cost — Show token usage\n"
            "/clear — Clear chat history\n\n"
            "Or just chat with me to discuss architecture, plan features, etc."
        )

    async def cmd_build(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update):
            return
        task = " ".join(context.args) if context.args else ""
        if not task:
            await update.message.reply_text("Usage: /build Add a health check endpoint")
            return

        await update.message.reply_text(f"Starting pipeline for: {task}\n\nThis may take several minutes...")

        # Run the pipeline in background
        result = await asyncio.to_thread(
            _run_pipeline, task, start_phase=None
        )
        # Send result in chunks (Telegram has 4096 char limit)
        for chunk in _chunk_text(result, 4000):
            await update.message.reply_text(chunk, parse_mode="Markdown")

    async def cmd_fix(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update):
            return
        task = " ".join(context.args) if context.args else ""
        if not task:
            await update.message.reply_text("Usage: /fix Auth token not refreshing")
            return

        await update.message.reply_text(f"Fixing: {task}\n\nSkipping to code phase...")

        result = await asyncio.to_thread(
            _run_pipeline, task, start_phase="code"
        )
        for chunk in _chunk_text(result, 4000):
            await update.message.reply_text(chunk, parse_mode="Markdown")

    async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update):
            return
        from ai_team.config import get_project_dir
        project = get_project_dir()
        model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
        await update.message.reply_text(
            f"Project: {project}\n"
            f"Model: {model}\n"
            f"User ID: {update.effective_user.id}"
        )

    async def cmd_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update):
            return
        from ai_team.agents.react_loop import get_token_usage
        usage = get_token_usage()
        model = os.getenv("LLM_MODEL", "")
        usage.estimate_cost(model)
        await update.message.reply_text(
            f"Tokens: {usage.total_tokens:,} ({usage.calls} calls)\n"
            f"Input: {usage.input_tokens:,} | Output: {usage.output_tokens:,}\n"
            f"Est. cost: ${usage.estimated_cost:.2f}"
        )

    async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_authorized(update):
            return
        uid = update.effective_user.id
        user_history[uid] = []
        await update.message.reply_text("Chat history cleared.")

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular chat messages — conversational mode."""
        if not is_authorized(update):
            return

        user_text = update.message.text
        uid = update.effective_user.id
        history = get_history(uid)

        # Get LLM response
        response = await asyncio.to_thread(
            _chat_response, user_text, history
        )

        history.append({"role": "user", "text": user_text})
        history.append({"role": "assistant", "text": response})
        # Keep history manageable
        if len(history) > 40:
            user_history[uid] = history[-40:]

        for chunk in _chunk_text(response, 4000):
            await update.message.reply_text(chunk, parse_mode="Markdown")

    # ── Build application ────────────────────────────────────────────────────

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("build", cmd_build))
    app.add_handler(CommandHandler("fix", cmd_fix))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cost", cmd_cost))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


# ── Pipeline runner ──────────────────────────────────────────────────────────

def _run_pipeline(task: str, start_phase: str | None = None) -> str:
    """Run the AI dev team pipeline and return a text summary."""
    try:
        result = subprocess.run(
            [
                str(VENV_PYTHON), str(AI_TEAM_DIR / "run.py"),
                "-t", task,
                *(["--start-phase", start_phase] if start_phase else []),
            ],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            cwd=str(AI_TEAM_DIR),
        )
        output = result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout
        if result.returncode != 0 and result.stderr:
            output += f"\n\nErrors:\n{result.stderr[-1000:]}"
        return output or "Pipeline completed (no output captured)."
    except subprocess.TimeoutExpired:
        return "Pipeline timed out after 10 minutes."
    except Exception as e:
        return f"Pipeline error: {e}"


def _chat_response(user_text: str, history: list[dict]) -> str:
    """Get a chat response using the LLM."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
        from ai_team.config import get_llm, get_project_dir
        from ai_team.agents.react_loop import invoke_llm_with_retry

        project = get_project_dir()
        system_msg = (
            "You are the lead of an AI engineering team. "
            f"Current project: {project}. "
            "Help the user plan features, discuss architecture, and make decisions. "
            "When they're ready to build, tell them to use /build or /fix. "
            "Keep responses concise — this is a mobile chat."
        )

        messages = [SystemMessage(content=system_msg)]
        for msg in history[-8:]:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["text"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["text"]))
        messages.append(HumanMessage(content=user_text))

        llm = get_llm(temperature=0.3)
        response = invoke_llm_with_retry(llm, messages)
        return response.content
    except Exception as e:
        return f"Error: {e}"


def _chunk_text(text: str, max_len: int) -> list[str]:
    """Split text into chunks for Telegram's message limit."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("ERROR: Set TELEGRAM_BOT_TOKEN in .env")
        print("")
        print("How to get a bot token:")
        print("  1. Open Telegram, search for @BotFather")
        print("  2. Send /newbot")
        print("  3. Follow the prompts to name your bot")
        print("  4. Copy the token to .env:")
        print("     TELEGRAM_BOT_TOKEN=123456:ABC-DEF...")
        print("")
        print("Optional — restrict to your user ID:")
        print("  1. Search for @userinfobot in Telegram")
        print("  2. Send any message to get your user ID")
        print("  3. Add to .env:")
        print("     TELEGRAM_ALLOWED_USERS=123456789")
        sys.exit(1)

    check_deps()
    print(f"Starting Telegram bot...")
    print(f"Project: {os.getenv('DEFAULT_PROJECT_DIR', '.')}")
    print(f"Model: {os.getenv('LLM_MODEL', 'claude-sonnet-4-20250514')}")
    if ALLOWED_USER_IDS:
        print(f"Allowed users: {ALLOWED_USER_IDS}")
    else:
        print("WARNING: No user restriction — anyone can use this bot!")
    print("Bot is running. Press Ctrl+C to stop.\n")

    app = create_bot()
    app.run_polling()


if __name__ == "__main__":
    main()
