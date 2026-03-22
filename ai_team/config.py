"""Configuration for the AI Dev Team."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get_llm():
    """Get the configured LLM instance."""
    model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

    if model.startswith("claude"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=0, max_tokens=8192)
    else:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, temperature=0, max_tokens=8192)


def get_project_dir(override: str | None = None) -> str:
    """Get the project directory to work on."""
    return override or os.getenv(
        "DEFAULT_PROJECT_DIR", os.path.expanduser("~/Villaex/VoiceAgentAPI")
    )


def get_max_iterations() -> int:
    return int(os.getenv("MAX_ITERATIONS", "5"))
