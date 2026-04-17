"""Shared ReAct loop with retry, error handling, token tracking, and progress."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from ai_team.tools.shell_tools import ALL_TOOLS

logger = logging.getLogger("ai_team.agents")

# Build tool map once (not per iteration)
TOOL_MAP = {t.name: t for t in ALL_TOOLS}

# ── Cost estimates per 1M tokens (input/output) ─────────────────────────────
COST_PER_1M = {
    "claude-sonnet": (3.0, 15.0),
    "claude-opus": (15.0, 75.0),
    "claude-haiku": (0.25, 1.25),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "o1": (15.0, 60.0),
    "o3-mini": (1.10, 4.40),
    "gemini-2.0-flash": (0.075, 0.30),
    "gemini-2.5-pro": (1.25, 10.0),
    "llama": (0.0, 0.0),  # Groq free tier
    "mixtral": (0.0, 0.0),
    "deepseek": (0.14, 0.28),
    "mistral-large": (2.0, 6.0),
    "codestral": (0.3, 0.9),
    "default": (1.0, 3.0),
}


@dataclass
class TokenUsage:
    """Tracks token usage and cost across the session."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    calls: int = 0

    def add(self, response: AIMessage) -> None:
        """Extract token usage from LLM response metadata."""
        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = response.usage_metadata
        elif hasattr(response, "response_metadata"):
            meta = response.response_metadata or {}
            usage = meta.get("usage", meta.get("token_usage", {}))

        inp = usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
        out = usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
        self.input_tokens += inp
        self.output_tokens += out
        self.total_tokens += inp + out
        self.calls += 1

    def estimate_cost(self, model: str = "") -> float:
        """Estimate cost based on model name."""
        model_lower = model.lower()
        rates = COST_PER_1M["default"]
        for prefix, r in COST_PER_1M.items():
            if prefix in model_lower:
                rates = r
                break
        cost = (self.input_tokens * rates[0] + self.output_tokens * rates[1]) / 1_000_000
        self.estimated_cost = cost
        return cost


# Global token tracker
_token_usage = TokenUsage()


def get_token_usage() -> TokenUsage:
    return _token_usage


def reset_token_usage() -> None:
    global _token_usage
    _token_usage = TokenUsage()


# ── LLM invocation with retry ───────────────────────────────────────────────

def invoke_llm_with_retry(
    llm: Any,
    messages: list[BaseMessage],
    max_retries: int = 3,
    base_delay: float = 2.0,
    agent_name: str = "unknown",
    trace: Any = None,
) -> AIMessage:
    """Invoke LLM with exponential backoff retry on transient errors.

    On 429 rate-limit for openai_compat (OpenRouter), rotates to the next key.
    Logs each call to Langfuse if a trace is provided.
    """
    import os
    from ai_team.config import _next_openrouter_key

    for attempt in range(max_retries):
        try:
            response = llm.invoke(messages)
            _token_usage.add(response)
            # Log to Langfuse if tracing is active
            if trace is not None:
                try:
                    from ai_team.observability import log_llm_call
                    usage = getattr(response, "usage_metadata", {}) or {}
                    log_llm_call(
                        trace=trace,
                        agent_name=agent_name,
                        model=getattr(llm, "model_name", getattr(llm, "model", "unknown")),
                        input_messages=messages,
                        output=response.content,
                        input_tokens=usage.get("input_tokens", 0),
                        output_tokens=usage.get("output_tokens", 0),
                    )
                except Exception:
                    pass  # observability must never break the pipeline
            return response
        except Exception as e:
            error_str = str(e).lower()
            is_rate_limit = "429" in error_str or "rate_limit" in error_str or "rate limit" in error_str
            is_transient = is_rate_limit or any(
                keyword in error_str
                for keyword in ["503", "timeout", "overloaded"]
            )
            if is_transient and attempt < max_retries - 1:
                # Rotate OpenRouter key on 429 before retrying
                if is_rate_limit and os.getenv("LLM_PROVIDER") == "openai_compat":
                    next_key = _next_openrouter_key()
                    if next_key:
                        logger.warning(
                            "OpenRouter 429 — rotating to next key (attempt %d/%d)",
                            attempt + 1, max_retries,
                        )
                        try:
                            llm = llm.copy(update={"openai_api_key": next_key})
                        except Exception:
                            pass  # copy not available on all LLM classes
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1, max_retries, e, delay,
                )
                time.sleep(delay)
            else:
                raise


# ── Tool execution ───────────────────────────────────────────────────────────

def execute_tool_call(tool_call: dict) -> ToolMessage:
    """Execute a single tool call safely, returning error as ToolMessage on failure."""
    tool_name = tool_call["name"]
    tool_fn = TOOL_MAP.get(tool_name)

    if not tool_fn:
        return ToolMessage(
            content=f"ERROR: Unknown tool '{tool_name}'. Available: {', '.join(TOOL_MAP.keys())}",
            tool_call_id=tool_call["id"],
        )

    try:
        result = tool_fn.invoke(tool_call["args"])
        return ToolMessage(content=str(result), tool_call_id=tool_call["id"])
    except Exception as e:
        logger.error("Tool '%s' failed: %s", tool_name, e)
        return ToolMessage(
            content=f"ERROR: Tool '{tool_name}' failed: {e}",
            tool_call_id=tool_call["id"],
        )


# ── Progress callback ───────────────────────────────────────────────────────

_progress_callback: Any = None


def set_progress_callback(callback: Any) -> None:
    """Set a callback function(agent_name, iteration, max_iter, action) for progress updates."""
    global _progress_callback
    _progress_callback = callback


def _emit_progress(agent: str, iteration: int, max_iter: int, action: str) -> None:
    if _progress_callback:
        try:
            _progress_callback(agent, iteration, max_iter, action)
        except Exception:
            pass


# ── ReAct loop ───────────────────────────────────────────────────────────────

@dataclass
class ReactResult:
    """Result from a ReAct loop execution."""
    response: AIMessage
    changed_files: list[str] = field(default_factory=list)
    iterations_used: int = 0
    max_iterations: int = 0
    tool_calls_made: int = 0


def react_loop(
    llm: Any,
    system_prompt: str,
    user_message: str,
    max_iterations: int = 15,
    tools: list | None = None,
    agent_name: str = "agent",
) -> tuple[AIMessage, list[str]]:
    """Run a ReAct loop: LLM calls tools until it produces a final response.

    Returns:
        Tuple of (final AIMessage, list of changed file paths)
    """
    if tools is None:
        tools = ALL_TOOLS

    llm_with_tools = llm.bind_tools(tools)

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    changed_files: list[str] = []
    last_response: AIMessage | None = None
    total_tool_calls = 0

    for iteration in range(max_iterations):
        _emit_progress(agent_name, iteration + 1, max_iterations, "thinking")

        response = invoke_llm_with_retry(llm_with_tools, messages)
        messages.append(response)
        last_response = response

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            _emit_progress(agent_name, iteration + 1, max_iterations, f"using {tool_name}")

            tool_message = execute_tool_call(tool_call)
            messages.append(tool_message)
            total_tool_calls += 1

            # Track file modifications
            if tool_name in ("write_file", "edit_file"):
                fpath = tool_call["args"].get("file_path", "")
                if fpath and fpath not in changed_files:
                    changed_files.append(fpath)

        logger.debug(
            "[%s] iteration %d/%d, %d tool calls (total: %d)",
            agent_name, iteration + 1, max_iterations,
            len(response.tool_calls), total_tool_calls,
        )

    if last_response is None:
        last_response = AIMessage(content="ERROR: Agent did not produce any response.")

    return last_response, changed_files


# ── Finding parser ───────────────────────────────────────────────────────────

def parse_findings(text: str) -> list[dict]:
    """Parse structured findings from agent output with balanced brace matching."""
    findings = []

    # Extract from code blocks first, fall back to full text
    code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    text_to_parse = "\n".join(code_blocks) if code_blocks else text

    # Balanced brace JSON extraction
    i = 0
    while i < len(text_to_parse):
        if text_to_parse[i] == "{":
            depth = 0
            start = i
            for j in range(i, len(text_to_parse)):
                if text_to_parse[j] == "{":
                    depth += 1
                elif text_to_parse[j] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text_to_parse[start : j + 1]
                        try:
                            obj = json.loads(candidate)
                            if isinstance(obj, dict) and "severity" in obj:
                                valid_severities = {"critical", "warn", "info", "pass"}
                                if obj["severity"] in valid_severities:
                                    findings.append({
                                        "severity": obj["severity"],
                                        "message": obj.get("message", ""),
                                        "file": obj.get("file", ""),
                                        "line": obj.get("line", 0),
                                        "agent": obj.get("agent", ""),
                                    })
                        except (json.JSONDecodeError, TypeError):
                            pass
                        i = j + 1
                        break
            else:
                i += 1
        else:
            i += 1

    if not findings:
        text_lower = text.lower()
        if any(w in text_lower for w in ["no issues", "all pass", "looks good", "no vulnerabilities", "no problems"]):
            findings = [{"severity": "pass", "file": "", "line": 0, "message": "No issues found."}]
        else:
            findings = [{"severity": "info", "file": "", "line": 0, "message": "Agent completed but produced no structured findings. Review output manually."}]

    return findings


# ── Error categorizer (for tester) ──────────────────────────────────────────

def categorize_test_error(output: str) -> dict:
    """Parse test output and categorize the failure type."""
    output_lower = output.lower()

    if "importerror" in output_lower or "modulenotfounderror" in output_lower:
        return {"category": "import_error", "hint": "Missing import or package. Check requirements and imports."}
    if "syntaxerror" in output_lower:
        return {"category": "syntax_error", "hint": "Syntax error in code. Check for typos, missing colons, unmatched brackets."}
    if "assertionerror" in output_lower:
        return {"category": "assertion_error", "hint": "Test assertion failed. Check expected vs actual values."}
    if "timeout" in output_lower or "timedout" in output_lower:
        return {"category": "timeout", "hint": "Test timed out. Check for infinite loops or slow DB queries."}
    if "fixture" in output_lower and ("not found" in output_lower or "error" in output_lower):
        return {"category": "fixture_error", "hint": "Missing test fixture. Check conftest.py for available fixtures."}
    if "connectionrefused" in output_lower or "connection refused" in output_lower:
        return {"category": "connection_error", "hint": "Database or service not running. Check Docker containers."}
    if "permissionerror" in output_lower:
        return {"category": "permission_error", "hint": "File permission issue. Check file ownership."}
    if "typeerror" in output_lower:
        return {"category": "type_error", "hint": "Type mismatch. Check function arguments and return types."}
    if "keyerror" in output_lower or "attributeerror" in output_lower:
        return {"category": "attribute_error", "hint": "Missing key or attribute. Check dict keys and object properties."}
    if "422" in output_lower or "validation" in output_lower:
        return {"category": "validation_error", "hint": "Request validation failed. Check Pydantic schemas and request body."}

    return {"category": "unknown", "hint": "Unclassified error. Read the full stack trace."}
