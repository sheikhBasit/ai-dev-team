SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PROJECT ?= $(shell grep DEFAULT_PROJECT_DIR .env 2>/dev/null | grep -v '^\#' | cut -d= -f2 || echo ".")

.PHONY: install setup think build fix review chat bot web test clean status rag-status rag-rebuild help

# ── The one command you need ─────────────────────────────────────────────────

think: ## Start the AI dev team (interactive pipeline)
	@source $(VENV)/bin/activate && python run.py -p "$(PROJECT)"

# ── Interfaces ───────────────────────────────────────────────────────────────

chat: ## Chat with your AI team (messaging CLI)
	@source $(VENV)/bin/activate && python chat.py

bot: ## Start Telegram bot (control from phone)
	@source $(VENV)/bin/activate && python bot.py

web: ## Start live dashboard (http://localhost:8765)
	@source $(VENV)/bin/activate && python -m ai_team.web.app

# ── Pipeline shortcuts ───────────────────────────────────────────────────────

build: ## Build a feature: make build task="Add health check"
	@source $(VENV)/bin/activate && python run.py -p "$(PROJECT)" -t "$(task)"

fix: ## Fix a bug: make fix task="Auth token bug"
	@source $(VENV)/bin/activate && python run.py -p "$(PROJECT)" -t "$(task)" --start-phase code

review: ## Review code: make review task="Review auth module"
	@source $(VENV)/bin/activate && python run.py -p "$(PROJECT)" -t "$(task)" --start-phase code

resume: ## Resume session: make resume id=<thread-id>
	@source $(VENV)/bin/activate && python run.py --thread-id "$(id)"

verbose: ## Verbose mode: make verbose task="Add caching"
	@source $(VENV)/bin/activate && python run.py -p "$(PROJECT)" -t "$(task)" -v

# ── Setup ────────────────────────────────────────────────────────────────────

install: $(VENV)/bin/activate ## Install all dependencies
	@$(PIP) install -r requirements.txt
	@echo "Done. Run: make setup"

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

setup: install ## First-time setup (install + create .env)
	@test -f .env || cp .env.example .env
	@chmod +x run.py chat.py bot.py
	@echo ""
	@echo "================================================"
	@echo "  Setup complete!"
	@echo ""
	@echo "  1. Edit .env → add your API key"
	@echo "  2. Then run one of:"
	@echo ""
	@echo "     think          pipeline mode"
	@echo "     think chat     messaging CLI"
	@echo "     think bot      Telegram bot"
	@echo ""
	@echo "================================================"

# ── Utilities ────────────────────────────────────────────────────────────────

test: ## Run smoke tests
	@source $(VENV)/bin/activate && python -c "\
from ai_team.graph import build_graph; \
g = build_graph(); \
print('Graph: OK (' + str(len(g.nodes)) + ' nodes)'); \
from ai_team.tools.shell_tools import _validate_command; \
assert _validate_command('pytest -v') is None; \
assert _validate_command('rm -rf /') is not None; \
print('Security: OK'); \
from ai_team.agents.react_loop import parse_findings; \
f = parse_findings('{\"severity\": \"pass\", \"message\": \"ok\"}'); \
print('Parser: OK'); \
print('ALL TESTS PASSED'); \
"

status: ## Show current project config
	@echo "Project:  $(PROJECT)"
	@echo "Model:    $$(grep LLM_MODEL .env 2>/dev/null | grep -v '^\#' | cut -d= -f2 || echo 'not set')"
	@echo "Provider: $$(grep LLM_PROVIDER .env 2>/dev/null | grep -v '^\#' | cut -d= -f2 || echo 'auto-detect')"
	@echo "Max iter: $$(grep MAX_ITERATIONS .env 2>/dev/null | grep -v '^\#' | cut -d= -f2 || echo '5')"
	@echo "Logs:     ~/.ai-dev-team/logs/"
	@echo "Memory:   ~/.ai-dev-team/memory/"
	@echo "History:  ~/.ai-dev-team/chat_history.json"

rag-status: ## Show RAG index stats for the current project
	@source $(VENV)/bin/activate && python -c "\
from ai_team.rag.store import index_stats; \
from ai_team.config import get_project_dir; \
import json; \
s = index_stats(get_project_dir('$(PROJECT)')); \
print(json.dumps(s, indent=2)); \
"

rag-rebuild: ## Force-rebuild the RAG index for the current project
	@source $(VENV)/bin/activate && python -c "\
from ai_team.rag.store import build_index; \
from ai_team.config import get_project_dir; \
p = get_project_dir('$(PROJECT)'); \
print('Rebuilding index for:', p); \
build_index(p, force=True); \
print('Done.'); \
"

clean: ## Remove venv and cache
	rm -rf $(VENV) __pycache__ ai_team/__pycache__ ai_team/agents/__pycache__ ai_team/tools/__pycache__
	@echo "Cleaned. Run 'make install' to reinstall."

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
