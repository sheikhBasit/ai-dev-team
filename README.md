# AI Dev Team

An autonomous AI engineering team powered by LangGraph. Describe what to build — agents handle requirements, architecture, coding, review, testing, security, and CI. You approve at checkpoints.

Supports 12 LLM providers: Claude, GPT-4, Gemini, Groq (free), DeepSeek, Mistral, Ollama (local), and more.

## Quick Start

```bash
git clone https://github.com/sheikhBasit/ai-dev-team
cd ai-dev-team
make setup
# Edit .env → add your API key
think "Add a webhook endpoint for Slack"
```

## Commands

```bash
think                          # interactive — asks what to build
think "Add feature X"          # build a feature
think fix "Auth token bug"     # skip straight to coding
think chat                     # persistent chat mode
think bot                      # Telegram bot (control from phone)
think resume <thread-id>       # resume a previous session
```

Or with the Makefile from the project directory:

```bash
make think                     # interactive
make build task="Add caching"
make fix task="Null pointer in auth"
make resume id=<thread-id>
```

## Pipeline

```
START → init → requirements → designer → architect → preflight
      → coder → git_commit → [reviewer + tester + security]
      → evaluator → learn_lessons → ci_check → human_final_review → END
                  ↗ (fail loop, max N iterations)
```

Human approval checkpoints: Requirements spec, Architecture plan, Final diff.

## LLM Providers

Set `LLM_MODEL` in `.env` — provider is auto-detected from the model name.

| Provider | Model examples | Setup |
|----------|---------------|-------|
| **Anthropic** (best for coding) | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY=...` |
| **OpenAI** | `gpt-4o`, `o4-mini` | `OPENAI_API_KEY=...` |
| **Google** | `gemini-2.5-pro`, `gemini-2.0-flash` | `GOOGLE_API_KEY=...` |
| **Groq** (free, fast) | `llama-3.3-70b-versatile` | `GROQ_API_KEY=...` |
| **DeepSeek** (cheap) | `deepseek-chat` | `DEEPSEEK_API_KEY=...` |
| **Mistral** | `mistral-large-latest` | `MISTRAL_API_KEY=...` |
| **Together AI** | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | `TOGETHER_API_KEY=...` |
| **Fireworks** | `accounts/fireworks/models/llama-v3p3-70b` | `FIREWORKS_API_KEY=...` |
| **Ollama** (local, free) | `qwen2.5-coder:14b`, `llama3.3` | `LLM_PROVIDER=ollama` |
| **OpenAI-compat** | any vLLM / LM Studio model | `LLM_PROVIDER=openai_compat` |

### Switching models per-run

Override the model without touching `.env`:

```bash
# Claude for this run
think --model claude-sonnet-4-20250514 "Add rate limiting"

# Free Groq inference
think --model llama-3.3-70b-versatile "Refactor auth"

# Local Ollama
think --model qwen2.5-coder:14b --provider ollama "Fix the bug"

# Or via environment
LLM_MODEL=gpt-4o think "Review this PR"
```

## Setup

### Prerequisites

- Python 3.11+
- At least one: API key from a provider above, or [Ollama](https://ollama.ai) running locally

### Install

```bash
make setup        # creates venv, installs deps, copies .env.example → .env
```

Edit `.env` and set your `LLM_MODEL` and API key.

### Install extra providers (only what you need)

```bash
pip install langchain-groq          # Groq
pip install langchain-google-genai  # Gemini
pip install langchain-mistralai     # Mistral
pip install langchain-together      # Together AI
pip install langchain-fireworks     # Fireworks
pip install langchain-huggingface   # HuggingFace
pip install langchain-ollama        # Ollama (local)
```

### Ollama (local, free)

```bash
ollama pull qwen2.5-coder:14b   # best for coding tasks
ollama serve
```

Then in `.env`:
```
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:14b
```

### Telegram Bot

Control the team from your phone:

```bash
# 1. Get a token from @BotFather
# 2. Add to .env:
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ALLOWED_USERS=your_telegram_user_id

# 3. Start
think bot
```

Send tasks as messages. The bot sends you approval requests — reply `approve` or `reject`.

## Configuration

All settings in `.env` (copy from `.env.example`):

```bash
LLM_MODEL=claude-sonnet-4-20250514   # model to use
LLM_PROVIDER=anthropic               # explicit provider (auto-detected if omitted)
LLM_TEMPERATURE=0                    # 0 = deterministic
LLM_MAX_TOKENS=8192

MAX_ITERATIONS=5                     # max coder retry loops
DEFAULT_PROJECT_DIR=~/my-project     # default project to work on
```

## Data & Sessions

Sessions are persisted in SQLite — resume any past run:

```bash
think resume 2126cbb9-aae8-48fd-9a5b-be326bf576d8
```

Stored at `~/.ai-dev-team/`:
```
~/.ai-dev-team/
├── checkpoints.db      # session state
├── logs/               # structured logs
└── memory/             # lessons learned per project
```

## Security

- **Command allowlist** — agents can only run `pytest`, `ruff`, `git`, `python`, `pip`. `rm`, `sudo`, `kill` are blocked.
- **Path sandboxing** — agents read/write only within the target project directory.
- **Credential scrubbing** — API keys and tokens are redacted from all agent output.

## Project Structure

```
ai-dev-team/
├── run.py              # CLI entry point
├── chat.py             # Persistent chat CLI
├── bot.py              # Telegram bot
├── Makefile
├── requirements.txt
├── .env.example
└── ai_team/
    ├── config.py       # Multi-provider LLM config
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
