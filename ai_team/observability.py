"""Langfuse observability — wraps LLM calls with traces, spans, and cost tracking.

Set in .env:
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_HOST=https://cloud.langfuse.com   # or self-hosted URL

If keys are missing, all functions are no-ops so the pipeline still runs.
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
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    if not pub or not sec:
        return None
    try:
        from langfuse import Langfuse
        _client = Langfuse(public_key=pub, secret_key=sec, host=host)
        _enabled = True
        logger.info("Langfuse observability enabled (host=%s)", host)
    except Exception as e:
        logger.warning("Langfuse init failed: %s — observability disabled", e)
        _client = None
    return _client


class _NoopSpan:
    def update(self, **_): pass
    def end(self, **_): pass
    def generation(self, **_): return self
    def score(self, **_): pass


@contextmanager
def trace_agent(
    agent_name: str,
    task: str = "",
    session_id: str = "",
    metadata: dict | None = None,
) -> Generator[Any, None, None]:
    """Context manager that wraps an agent run in a Langfuse trace."""
    client = _get_client()
    if client is None:
        yield _NoopSpan()
        return
    try:
        tr = client.trace(
            name=agent_name,
            input=task,
            session_id=session_id or None,
            metadata=metadata or {},
            tags=[agent_name, "ai-dev-team"],
        )
        yield tr
        tr.update(output=task)
    except Exception as e:
        logger.warning("Langfuse trace error: %s", e)
        yield _NoopSpan()
    finally:
        try:
            client.flush()
        except Exception:
            pass


def log_llm_call(
    trace,
    agent_name: str,
    model: str,
    input_messages: list,
    output: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Log a single LLM call as a generation span inside an existing trace."""
    if not _enabled or trace is None or isinstance(trace, _NoopSpan):
        return
    try:
        trace.generation(
            name=f"{agent_name}-llm",
            model=model,
            input=[{"role": getattr(m, 'type', 'user'), "content": getattr(m, 'content', str(m))} for m in input_messages],
            output=output,
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
        )
    except Exception as e:
        logger.warning("Langfuse generation log error: %s", e)


def score_response(
    trace,
    name: str,
    value: float,
    comment: str = "",
) -> None:
    """Add a numeric score to a trace (0.0–1.0). Use for hallucination rate, quality etc."""
    if not _enabled or trace is None or isinstance(trace, _NoopSpan):
        return
    try:
        trace.score(name=name, value=value, comment=comment)
    except Exception as e:
        logger.warning("Langfuse score error: %s", e)


def flush() -> None:
    """Flush all pending events to Langfuse. Call at end of pipeline."""
    client = _get_client()
    if client:
        try:
            client.flush()
        except Exception:
            pass
