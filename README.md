# AI Dev Team

> Autonomous AI engineering team powered by LangGraph. Describe what to build — agents handle requirements, architecture, coding, review, testing, security, and CI. You approve at checkpoints.

**Works with 12 LLM providers** — Claude, GPT-4, Gemini, Groq (free), DeepSeek, Mistral, Ollama (local/free), and more. One command to start: `think`.

---

## How It Works

You describe a task. The pipeline runs end-to-end with human approval at critical points.

```
START → init → requirements → designer → architect → preflight
      → coder → git_commit → [reviewer + tester + security] (parallel)
      → evaluator → learn_lessons → ci_check → human_final_review → END
                  ↗ (fail loop, max N iterations)
```

**Human approval checkpoints:** Requirements spec · Architecture plan · Final diff

**What each agent does:**

| Agent | Role |
|-------|------|
| Requirements | Writes full PRD from your task description |
| Architect | Reads your codebase, designs the solution |
| Coder | Writes the actual code (30 tool iterations) |
| Reviewer | Tech lead code review |
| Tester | Writes and runs tests |
| Security | OWASP audit |
| Evaluator | Ship / no-ship decision |

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
LLM_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=your_key

# Or local — no API key at all
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:14b
```

Then point it at your project and run:

```bash
think "Add rate limiting to the API"
think fix "JWT tokens not expiring correctly"
think chat    # persistent conversation mode
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
```

---

## LLM Providers

| Provider | Model examples | Free? |
|----------|---------------|-------|
| **Groq** | `llama-3.3-70b-versatile` | Free tier |
| **Ollama** | `qwen2.5-coder:14b`, `llama3.3` | Free (local) |
| **DeepSeek** | `deepseek-chat` | Very cheap |
| **Anthropic** | `claude-sonnet-4-20250514` | Paid |
| **OpenAI** | `gpt-4o`, `o4-mini` | Paid |
| **Google** | `gemini-2.5-pro` | Paid |
| **Mistral** | `mistral-large-latest` | Paid |
| **Together AI** | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Paid |
| **Fireworks** | `llama-v3p3-70b-instruct` | Paid |
| **OpenAI-compat** | any vLLM / LM Studio model | Self-hosted |

Provider is **auto-detected from the model name** — no extra config needed for most cases.

Override per-run without touching `.env`:

```bash
think --model claude-sonnet-4-20250514 "Add rate limiting"
LLM_MODEL=gpt-4o think "Review this PR"
```

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

---

## Sessions & Memory

Sessions are persisted in SQLite — resume any past run:

```bash
think resume 2126cbb9-aae8-48fd-9a5b-be326bf576d8
```

The pipeline learns from each session — lessons are saved per-project and loaded at the start of the next run.

```
~/.ai-dev-team/
├── checkpoints.db      # resumable session state
├── logs/               # structured agent logs
└── memory/             # lessons learned per project
```

---

## Security

- **Command allowlist** — agents can only run `pytest`, `ruff`, `git`, `python`, `pip`. `rm`, `sudo`, `kill` are blocked.
- **Path sandboxing** — agents read/write only within the target project directory.
- **Credential scrubbing** — API keys and tokens are redacted from all agent output.

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
    ├── config.py       # Multi-provider LLM config (12 providers)
    ├── state.py        # LangGraph state schema
    ├── graph.py        # Pipeline orchestrator (15 nodes)
    ├── agents/
    │   ├── requirements.py
    │   ├── designer.py
    │   ├── architect.py
    │   ├── coder.py
    │   ├── reviewer.py
    │   ├── tester.py
    │   ├── security.py
    │   └── evaluator.py
    └── tools/
        └── shell_tools.py
```

---

Built by [Abdul Basit](https://github.com/sheikhBasit) · FastAPI · LangGraph · Python 3.11
