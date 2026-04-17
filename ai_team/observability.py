"""Langfuse v4 observability — traces every agent LLM call with cost tracking.

Set in .env:
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_HOST=https://cloud.langfuse.com

If keys are missing, all functions are no-ops — pipeline always runs.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger("ai_team.observability")

_client = None
_enabled = False


def _get_client():
    global _client, _enabled
    if _client is not None:
        return _client
    pub = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sec = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))
    if not pub or not sec:
        return None
    try:
        from langfuse import Langfuse
        _client = Langfuse(public_key=pub, secret_key=sec, host=host)
        ok = _client.auth_check()
        if not ok:
            logger.warning("Langfuse auth_check failed — observability disabled")
            _client = None
            return None
        _enabled = True
        logger.info("Langfuse observability enabled (host=%s)", host)
    except Exception as e:
        logger.warning("Langfuse init failed: %s — observability disabled", e)
        _client = None
    return _client


class _Noop:
    """No-op span/trace returned when Langfuse is disabled."""
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def update(self, **_): pass
    def end(self, **_): pass


@contextmanager
def trace_agent(
    agent_name: str,
    task: str = "",
    session_id: str = "",
    metadata: dict | None = None,
) -> Generator[Any, None, None]:
    """Context manager wrapping an agent run in a Langfuse trace (v4 API)."""
    client = _get_client()
    if client is None:
        yield _Noop()
        return

    try:
        with client.start_as_current_observation(
            name=agent_name,
            input=task,
            metadata={**(metadata or {}), "session_id": session_id},
        ) as span:
            yield span
    except Exception as e:
        logger.warning("Langfuse trace error: %s", e)
        yield _Noop()
    finally:
        try:
            client.flush()
        except Exception:
            pass


def log_llm_call(
    trace: Any,
    agent_name: str,
    model: str,
    input_messages: list,
    output: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Log a single LLM call as a generation inside the current trace context."""
    client = _get_client()
    if not _enabled or client is None:
        return
    try:
        client.create_event(
            name=f"{agent_name}-generation",
            input=[{
                "role": getattr(m, "type", "user"),
                "content": getattr(m, "content", str(m))[:2000],
            } for m in input_messages],
            output=output[:2000],
            metadata={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )
    except Exception as e:
        logger.warning("Langfuse log_llm_call error: %s", e)


def score_pipeline(name: str, value: float, comment: str = "") -> None:
    """Score the current trace (0.0–1.0). Call after evaluator runs."""
    client = _get_client()
    if not _enabled or client is None:
        return
    try:
        client.score_current_trace(name=name, value=value, comment=comment)
    except Exception as e:
        logger.warning("Langfuse score error: %s", e)


def flush() -> None:
    """Flush all pending events. Call at end of pipeline run."""
    client = _get_client()
    if client:
        try:
            client.flush()
        except Exception:
            pass
