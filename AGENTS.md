# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Cursor, GitHub Copilot, etc.)
working in this repository.

## Project
Autonomous AI engineering team built on LangGraph — 19-node pipeline with agents for requirements,
planning, coding, parallel review/test/security/debug, documentation, and CI. Supports 12 LLM
providers. Implements MCP and A2A protocols. Includes Langfuse observability.

## Architecture
- `ai_team/graph.py` — LangGraph orchestrator wiring all nodes
- `ai_team/agents/` — individual agent implementations (requirements, coder, reviewer, etc.)
- `ai_team/agents/react_loop.py` — shared ReAct loop with retry and token tracking
- `ai_team/bus.py` — in-process pub/sub agent chat bus with SQLite persistence
- `ai_team/observability.py` — Langfuse tracing (no-op if keys not set)
- `ai_team/web/` — FastAPI dashboard + A2A protocol endpoints
- `ai_team/rag/` — hybrid RAG store (BM25 + semantic, RRF fusion)
- `ai_team/tools/shell_tools.py` — sandboxed file ops and safe shell commands

## Agent Protocol Endpoints (A2A)
- `GET /.well-known/agents` — list all agent cards
- `GET /.well-known/agent/{name}` — single agent card
- `POST /a2a/tasks` — delegate task to an agent
- `GET /a2a/tasks/{task_id}` — poll result

## Security Rules (CRITICAL)
- Command allowlist in `shell_tools.py` — do NOT add `rm`, `sudo`, `kill`, or other destructive commands
- Path sandboxing — agents may only read/write within the project directory
- Credential scrubbing — API keys must never appear in bus messages or logs

## LLM Provider Routing
Set `LLM_PROVIDER` and agent-specific `AGENT_MODEL_<ROLE>` env vars. See `config.py`.

## Observability
Set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` in `.env` to enable tracing.
All agent LLM calls are traced automatically via `observability.py`.

## Testing
- `make test` — runs smoke tests
- `pytest` — full test suite

## Commits
- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`
- No WIP commits to main

## What NOT to do
- Do not modify the command allowlist without security review
- Do not add mutable global state outside `bus.py` and `app.py`
- Do not hardcode model names — use `get_llm_for_agent()` from `config.py`
