#!/bin/bash
set -euo pipefail

# ============================================================================
# LANGGRAPH AI DEV TEAM SETUP
# Sets up the multi-agent LangGraph project with all dependencies
# Run: chmod +x setup-langgraph.sh && ./setup-langgraph.sh
# ============================================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Python virtual environment ───────────────────────────────────────────────
log "Creating virtual environment..."
cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip

# ── Install dependencies ─────────────────────────────────────────────────────
log "Installing LangGraph and dependencies..."
pip install -r requirements.txt

# ── Environment file ─────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    log "Creating .env from template..."
    cp .env.example .env
    warn "Edit .env and add your API keys before running the agent team!"
    warn "  nano $PROJECT_DIR/.env"
else
    log ".env already exists"
fi

# ── Verify installation ─────────────────────────────────────────────────────
log "Verifying installation..."
python3 -c "
import langgraph
import langchain_core
import langchain_anthropic
print(f'  langgraph:          {langgraph.__version__}')
print(f'  langchain-core:     {langchain_core.__version__}')
print(f'  langchain-anthropic: {langchain_anthropic.__version__}')
"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
log "LangGraph AI Dev Team is ready!"
echo "============================================"
echo ""
echo "Usage:"
echo "  source .venv/bin/activate"
echo ""
echo "  # Interactive mode (agent asks you questions):"
echo "  python run.py --task 'Add a webhook endpoint for Slack notifications'"
echo ""
echo "  # Point it at a specific project:"
echo "  python run.py --project ~/Villaex/VoiceAgentAPI --task 'Fix auth bug'"
echo ""
echo "  # Resume a previous session:"
echo "  python run.py --thread-id <thread-id>"
echo ""
echo "  # Skip to a specific phase:"
echo "  python run.py --task 'Build dashboard' --start-phase code"
echo ""
echo "Don't forget to set your API keys in .env first!"
echo ""
