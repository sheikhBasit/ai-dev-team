# AI Dev Team

> Autonomous AI engineering team powered by LangGraph. Describe what to build — agents handle requirements, architecture, planning, coding, review, testing, security, debugging, docs, and CI. You approve at checkpoints.

**Works with 12 LLM providers** — Claude, GPT-4, Gemini, Groq (free), DeepSeek, Mistral, Ollama (local/free), and more. One command to start: `think`.

---

## How It Works

You describe a task. The pipeline runs end-to-end with human approval at critical points.

```
START → init → requirements → designer → architect → preflight → planner
      → coder → import_healer → git_commit
      → [reviewer + tester + security + debugger] (parallel)
      → evaluator → learn_lessons → docs → ci_check → human_final_review
      → [gh pr create] → END
               ↑
        (fail loop, max N iterations)
```

**Human approval checkpoints:** Requirements spec · Architecture plan · Final diff

> **[Interactive Pipeline Visualizer](pipeline-viz.html)** — open in browser to see every agent, edge, and log stream animated step by step.

**What each agent does:**

| Agent | Role |
|-------|------|
| Requirements | Writes full PRD from your task description |
| Designer | UI/UX component design |
| Architect | Reads your codebase, designs the solution |
| **Planner** | Breaks task into structured WorkItems for the coder |
| Coder | Writes the actual code (30 tool iterations, RAG-assisted) |
| Reviewer | Tech lead review — uses semantic codebase search for context |
| Tester | Writes and runs tests |
| Security | OWASP audit |
| **Debugger** | Root-cause analysis of test/review failures |
| **Docs** | Updates docstrings and README sections for changed files |
| Evaluator | Ship / no-ship decision, reads debug report |

**New infrastructure:**

| Feature | What it does |
|---------|-------------|
| **RAG codebase search** | Hybrid BM25 + semantic search over your entire codebase — agents find related code before writing |
| **Agent chat bus** | In-process pub/sub so agents message each other (architect → coder, reviewer → coder) |
| **Per-agent model routing** | Set `AGENT_MODEL_CODER=claude-opus-4-7`, `LLM_MODEL_CHEAP=claude-haiku-4-5` etc. per role |
| **Self-healing imports** | Detects `ModuleNotFoundError` in coder output, auto-installs from a safe allowlist |
| **GitHub PR auto-open** | After your approval, opens a PR via `gh` CLI automatically |
| **Live dashboard** | WebSocket stream of all agent messages at `http://localhost:8765` (`make web`) |
| **Session memory** | Lessons learned per project, loaded at start of every future session via RAG |

---

## Quick Start

```bash
git clone https://github.com/sheikhBasit/ai-dev-team
cd ai-dev-team
make setup
```

Edit `.env` — add your API key and set your model:

```bash
# Free option — Groq (no credit card needed)
LLM_MODEL=llama-3.3-70b-versatile
LLM_PROVIDER=openai_compat
OPENAI_COMPAT_BASE_URL=https://api.groq.com/openai/v1
OPENAI_COMPAT_API_KEY=your_groq_key   # free at console.groq.com

# Or Claude (best results)
LLM_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=your_key

# Route cheap agents (requirements, docs) to a faster/cheaper model
LLM_MODEL_CHEAP=claude-haiku-4-5-20251001

# Or fully local — no API key at all
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:14b
```

Then point it at your project and run:

```bash
think "Add rate limiting to the API"
think fix "JWT tokens not expiring correctly"
think chat    # persistent conversation mode
make web      # open live dashboard at http://localhost:8765
```

---

## Commands

```bash
think                          # interactive — asks what to build
think "Add feature X"          # build a feature
think fix "Auth token bug"     # skip straight to coding
think chat                     # persistent chat mode
think bot                      # Telegram bot (control from phone)
think resume <thread-id>       # resume a previous session
```

Or via Makefile:

```bash
make think
make build task="Add caching layer"
make fix task="Null pointer in auth"
make resume id=<thread-id>
make web                       # live agent dashboard
make rag-status                # show RAG index stats
make rag-rebuild               # force-rebuild semantic index
```

---

## Per-Agent Model Routing

Route expensive agents to powerful models and cheap agents to fast ones:

```bash
# .env
LLM_MODEL=claude-sonnet-4-6           # default for all agents
LLM_MODEL_CHEAP=claude-haiku-4-5-20251001  # fast agents use this

# Override per role
AGENT_MODEL_CODER=claude-opus-4-7
AGENT_MODEL_ARCHITECT=claude-opus-4-7
AGENT_MODEL_REQUIREMENTS=claude-haiku-4-5-20251001
AGENT_MODEL_DESIGNER=claude-haiku-4-5-20251001
AGENT_MODEL_EVALUATOR=claude-haiku-4-5-20251001
```

---

## LLM Providers

| Provider | Model examples | Free? |
|----------|---------------|-------|
| **Groq** | `llama-3.3-70b-versatile` | Free tier |
| **Ollama** | `qwen2.5-coder:14b`, `llama3.3` | Free (local) |
| **DeepSeek** | `deepseek-chat` | Very cheap |
| **Anthropic** | `claude-sonnet-4-6` | Paid |
| **OpenAI** | `gpt-4o`, `o4-mini` | Paid |
| **Google** | `gemini-2.5-pro` | Paid |
| **Mistral** | `mistral-large-latest` | Paid |
| **Together AI** | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Paid |
| **Fireworks** | `llama-v3p3-70b-instruct` | Paid |
| **OpenAI-compat** | any vLLM / LM Studio model | Self-hosted |

Provider is **auto-detected from the model name** — no extra config needed for most cases.

---

## Setup

**Prerequisites:** Python 3.11+ · One API key (or Ollama running locally)

```bash
make setup        # creates venv, installs deps, copies .env.example → .env
```

Install only the providers you need:

```bash
pip install langchain-groq           # Groq
pip install langchain-google-genai   # Gemini
pip install langchain-mistralai      # Mistral
pip install langchain-ollama         # Ollama (local)
```

**Ollama (fully local, free):**

```bash
ollama pull qwen2.5-coder:14b
ollama serve
# then: LLM_PROVIDER=ollama LLM_MODEL=qwen2.5-coder:14b
```

**Telegram Bot (control from phone):**

```bash
# Get token from @BotFather, add to .env:
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ALLOWED_USERS=your_telegram_user_id

think bot   # start the bot
```

Send tasks as messages. Bot sends you approval requests — reply `approve` or `reject`.

**Live Dashboard:**

```bash
pip install fastapi uvicorn
make web    # starts at http://localhost:8765
```

Watch all agent messages stream in real-time, color-coded by role.

---

## Sessions & Memory

Sessions are persisted in SQLite — resume any past run:

```bash
think resume 2126cbb9-aae8-48fd-9a5b-be326bf576d8
```

The pipeline learns from each session. Lessons are saved per-project, embedded via RAG, and only the task-relevant ones are loaded at the start of the next run.

```
~/.ai-dev-team/
├── checkpoints.db      # resumable session state
├── logs/               # structured agent logs
├── memory/             # lessons learned per project
└── rag/                # semantic codebase + lessons index
```

---

## Security

- **Command allowlist** — agents can only run `pytest`, `ruff`, `git`, `python`, `pip`. `rm`, `sudo`, `kill` are blocked.
- **Path sandboxing** — agents read/write only within the target project directory.
- **Credential scrubbing** — API keys and tokens are redacted from all agent output.
- **Import allowlist** — self-healing node only installs packages from a vetted 35-package list.

---

## Project Structure

```
ai-dev-team/
├── run.py              # CLI entry point (`think` command)
├── chat.py             # Persistent chat CLI
├── bot.py              # Telegram bot
├── Makefile
├── requirements.txt
├── .env.example
└── ai_team/
    ├── config.py       # Multi-provider LLM config (12 providers, per-agent routing)
    ├── state.py        # LangGraph state schema (WorkItem, AgentMessage, etc.)
    ├── graph.py        # Pipeline orchestrator (19 nodes)
    ├── bus.py          # In-process agent chat bus
    ├── agents/
    │   ├── planner.py      # NEW: task → WorkItems
    │   ├── debugger.py     # NEW: root cause analysis
    │   ├── docs.py         # NEW: docstring updater
    │   ├── import_healer.py # NEW: auto-install missing packages
    │   ├── requirements.py
    │   ├── designer.py
    │   ├── architect.py
    │   ├── coder.py
    │   ├── reviewer.py     # UPGRADED: RAG-aware
    │   ├── tester.py
    │   ├── security.py
    │   └── evaluator.py
    ├── rag/
    │   ├── chunker.py      # Semantic code chunking
    │   ├── store.py        # Diff-aware vector index
    │   ├── hybrid_search.py # BM25 + semantic RRF fusion
    │   └── lessons_rag.py  # Per-task lesson retrieval
    ├── tools/
    │   ├── shell_tools.py  # Sandboxed file ops + shell
    │   └── rag_tools.py    # search_codebase, reindex_codebase
    └── web/
        └── app.py          # FastAPI live dashboard
```

---

Built by [Abdul Basit](https://github.com/sheikhBasit) · LangGraph · FastAPI · Python 3.11
