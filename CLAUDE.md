# CLAUDE.md — AI Dev Team

## What This Is

An autonomous AI engineering team powered by LangGraph. You describe what to build, agents do the work, you approve at checkpoints. One command: `think`.

## Quick Start

```bash
think                                    # interactive mode
think "Add a webhook endpoint"           # build a feature
think fix "Auth token bug"               # skip to coding
think chat                               # persistent chat mode
think bot                                # start Telegram bot
```

## Architecture

### Pipeline Flow

```
START → init → requirements → designer → architect → preflight
      → coder → git_commit → [reviewer + tester + security] (parallel)
      → evaluator → learn_lessons → ci_check → human_final_review → END
                  ↳ (fail) → coder (loop, max N iterations)
```

### Agent Roles

| Agent | Role | Tools | Approval |
|-------|------|-------|----------|
| **Requirements** | Product Manager — writes PRD specs | LLM only | Human approves |
| **Designer** | UI/UX — generates component code | LLM only | Human approves |
| **Architect** | Solution Architect — system design | read_file, search_files, list_directory | Human approves |
| **Coder** | Senior Dev — writes code (30 tool iterations) | ALL tools | Automatic |
| **Reviewer** | Tech Lead — code review | read_file, search_files | Automatic |
| **Tester** | QA Engineer — writes & runs tests | ALL tools | Automatic |
| **Security** | Security auditor — OWASP checks | read_file, search_files, run_command | Automatic |
| **Evaluator** | Eng Manager — ship/no-ship decision | LLM only | Routes to coder or ship |

### Nodes (non-agent)

| Node | Purpose |
|------|---------|
| `init` | Detect project, build codebase index, load memory, create git branch |
| `preflight` | Check linter, test dirs, git status before coding |
| `git_commit` | Auto-commit after each coder iteration for rollback |
| `learn_lessons` | Extract and save lessons from evaluation |
| `ci_check` | Run ruff + pyright same as CI |
| `human_final_review` | Show git diff, get final approval |

## Project Structure

```
ai-dev-team/
├── run.py                         # CLI entry point
├── chat.py                        # Persistent chat CLI
├── bot.py                         # Telegram bot
├── Makefile                       # make think, make build, etc.
├── requirements.txt               # Python dependencies
├── .env.example                   # API key template
├── CLAUDE.md                      # This file
│
└── ai_team/
    ├── config.py                  # Multi-provider LLM config (12 providers)
    ├── state.py                   # LangGraph state schema
    ├── graph.py                   # Main orchestrator (15 nodes)
    │
    ├── agents/
    │   ├── react_loop.py          # Shared ReAct loop + retry + token tracking
    │   ├── project_detector.py    # Auto-detect language, framework, style
    │   ├── codebase_indexer.py    # Index classes, functions, endpoints, models
    │   ├── memory.py              # Persistent lessons between sessions
    │   ├── requirements.py        # Product Manager agent
    │   ├── designer.py            # UI/UX agent
    │   ├── architect.py           # Solution Architect agent
    │   ├── coder.py               # Senior Developer agent
    │   ├── reviewer.py            # Tech Lead reviewer agent
    │   ├── tester.py              # QA Engineer agent
    │   ├── security.py            # Security auditor agent
    │   └── evaluator.py           # Engineering Manager agent
    │
    └── tools/
        └── shell_tools.py         # Sandboxed file ops + safe shell commands
```

## Key Design Decisions

### Security
- **Command allowlist**: Only pytest, ruff, git, python, pip, etc. are allowed. rm, sudo, kill are blocked.
- **Path sandboxing**: Agents can only read/write within the project directory.
- **Credential scrubbing**: API keys, passwords, tokens are redacted from all output.

### State Management
- **LangGraph checkpointer**: SQLite-based session persistence at `~/.ai-dev-team/checkpoints.db`
- **Messages capped at 100**: Custom reducer prevents state bloat
- **Phase rejection counter**: Max 5 rejections per phase, then auto-proceeds

### Context Management
- **Project detection**: Reads CLAUDE.md, pyproject.toml, package.json, requirements.txt to detect language, framework, code style, test patterns
- **Codebase index**: Scans all files for classes, functions, API endpoints, DB models, test files
- **Session memory**: Lessons learned saved to `~/.ai-dev-team/memory/` and loaded in future sessions
- **Incremental work**: Fix iterations focus ONLY on reported issues, not full reimplementation

### History Management
- **Git branch per task**: `ai-dev-team/<task-slug>` created at init
- **Git commit per iteration**: Auto-commits after each coder run for rollback
- **Thread persistence**: Sessions saved to SQLite, resumable with `--thread-id`
- **Structured logging**: All agent actions logged to `~/.ai-dev-team/logs/`
- **Lessons DB**: `~/.ai-dev-team/memory/<project>.json` stores learned patterns

### Cost Control
- **Token tracking**: Input/output tokens counted per LLM call
- **Cost estimation**: Per-model pricing (Claude, GPT, Groq, etc.)
- **Session summary**: Shows total tokens and estimated cost at end
- **Iteration limits**: Max iterations configurable via MAX_ITERATIONS

## LLM Providers (12 supported)

| Provider | Env Var | Auto-detect Prefix |
|----------|---------|-------------------|
| Anthropic | ANTHROPIC_API_KEY | claude* |
| OpenAI | OPENAI_API_KEY | gpt*, o1*, o3*, o4* |
| Google | GOOGLE_API_KEY | gemini* |
| Groq (free) | GROQ_API_KEY | llama*, mixtral* |
| Mistral | MISTRAL_API_KEY | mistral*, codestral* |
| DeepSeek | DEEPSEEK_API_KEY | deepseek* |
| Together | TOGETHER_API_KEY | (explicit) |
| Fireworks | FIREWORKS_API_KEY | (explicit) |
| HuggingFace | HUGGINGFACEHUB_API_TOKEN | (explicit) |
| Ollama (local) | — | LLM_PROVIDER=ollama |
| OpenAI-compat | OPENAI_COMPAT_API_KEY | LLM_PROVIDER=openai_compat |

## Interfaces

### CLI (`think` command)
- `think` — interactive, asks what to build
- `think "task"` — build a feature
- `think fix "bug"` — skip to coding
- `think resume <id>` — resume session

### Chat CLI (`think chat`)
- Persistent conversation with the AI team
- Chat history saved to disk
- `/build`, `/fix`, `/status` commands
- Works offline with Ollama

### Telegram Bot (`think bot`)
- Send tasks from your phone
- Receive approval requests as messages
- Reply approve/reject from anywhere
- Set up: get token from @BotFather, add to .env

### Web Dashboard (`think web`)
- Live agent message stream at http://localhost:8765
- WebSocket auto-reconnects if pipeline restarts
- Color-coded by agent role

## Commands Reference

```bash
# Global command (works from anywhere)
think                          # interactive
think "Add feature X"          # build
think fix "Bug Y"              # fix
think chat                     # chat mode
think bot                      # telegram bot
think web                      # live dashboard
think resume <id>              # resume

# Makefile (from project dir)
make think                     # interactive
make build task="..."          # build
make fix task="..."            # fix
make web                       # live dashboard
make test                      # smoke tests
make status                    # show config
make setup                     # first-time setup
make clean                     # remove venv
make help                      # all commands
```

## Files That Store Data

```
~/.ai-dev-team/
├── checkpoints.db             # Session state (resumable)
├── logs/
│   └── ai-dev-team.log        # Structured logs
├── memory/
│   └── <project>.json         # Lessons learned per project
└── chat_history                # Chat CLI history
```
