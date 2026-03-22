#!/bin/bash
set -euo pipefail

# ============================================================================
# MACHINE PERSONALIZATION SCRIPT
# Sets up a fresh Ubuntu machine with all dev tools for basitdev
# Run: chmod +x setup-machine.sh && ./setup-machine.sh
# ============================================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[x]${NC} $1"; }

# ── System packages ──────────────────────────────────────────────────────────
log "Updating system packages..."
sudo apt update && sudo apt upgrade -y

log "Installing base dependencies..."
sudo apt install -y \
    build-essential \
    curl \
    wget \
    git \
    unzip \
    zip \
    jq \
    htop \
    tmux \
    vim \
    tree \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    pkg-config

# ── Python ───────────────────────────────────────────────────────────────────
log "Setting up Python..."
sudo apt install -y python3 python3-pip python3-venv python3-dev

# pipx for global CLI tools
if ! command -v pipx &>/dev/null; then
    sudo apt install -y pipx
    pipx ensurepath
fi

# ── Node.js (via nvm) ───────────────────────────────────────────────────────
log "Setting up Node.js..."
if ! command -v nvm &>/dev/null && [ ! -d "$HOME/.nvm" ]; then
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    nvm install --lts
else
    log "nvm already installed, skipping"
fi

# ── Docker ───────────────────────────────────────────────────────────────────
log "Setting up Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    warn "Docker installed. You may need to log out and back in for group changes."
else
    log "Docker already installed: $(docker --version)"
fi

# ── Rust / Cargo ─────────────────────────────────────────────────────────────
log "Setting up Rust..."
if ! command -v cargo &>/dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
else
    log "Rust already installed: $(cargo --version)"
fi

# ── Go ───────────────────────────────────────────────────────────────────────
log "Setting up Go..."
if ! command -v go &>/dev/null; then
    GO_VERSION="1.23.4"
    wget -q "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -O /tmp/go.tar.gz
    sudo rm -rf /usr/local/go
    sudo tar -C /usr/local -xzf /tmp/go.tar.gz
    rm /tmp/go.tar.gz
    echo 'export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin' >> "$HOME/.bashrc"
    export PATH=$PATH:/usr/local/go/bin:$HOME/go/bin
else
    log "Go already installed: $(go version)"
fi

# ── Java (OpenJDK 17) ───────────────────────────────────────────────────────
log "Setting up Java..."
if ! command -v java &>/dev/null; then
    sudo apt install -y openjdk-17-jdk
else
    log "Java already installed: $(java -version 2>&1 | head -1)"
fi

# ── Dev CLI Tools ────────────────────────────────────────────────────────────
log "Installing dev CLI tools..."

# ruff (Python linter/formatter)
if ! command -v ruff &>/dev/null; then
    pipx install ruff
else
    log "ruff already installed"
fi

# pyright (type checker)
if ! command -v pyright &>/dev/null; then
    npm install -g pyright
else
    log "pyright already installed"
fi

# Task (task runner - taskfile.dev)
if ! command -v task &>/dev/null; then
    sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b "$HOME/.local/bin"
else
    log "task already installed"
fi

# GitHub CLI
if ! command -v gh &>/dev/null; then
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    sudo apt update && sudo apt install -y gh
else
    log "gh already installed"
fi

# ── Claude Code ──────────────────────────────────────────────────────────────
log "Installing Claude Code..."
if ! command -v claude &>/dev/null; then
    npm install -g @anthropic-ai/claude-code
else
    log "Claude Code already installed: $(claude --version 2>/dev/null || echo 'installed')"
fi

# ── Git Configuration ────────────────────────────────────────────────────────
log "Configuring git..."
git config --global user.name "abdulbasit-star"
git config --global user.email "abdul.basit@villaextechnologies.com"
git config --global init.defaultBranch main
git config --global pull.rebase false
git config --global core.editor vim

# SSH key
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
    log "Generating SSH key..."
    ssh-keygen -t ed25519 -C "abdul.basit@villaextechnologies.com" -f "$HOME/.ssh/id_ed25519" -N ""
    warn "Add this public key to GitHub:"
    cat "$HOME/.ssh/id_ed25519.pub"
else
    log "SSH key already exists"
fi

# ── PostgreSQL Client ────────────────────────────────────────────────────────
log "Installing PostgreSQL client..."
sudo apt install -y postgresql-client

# ── Redis CLI ────────────────────────────────────────────────────────────────
log "Installing Redis tools..."
sudo apt install -y redis-tools

# ── Bash Aliases & Shortcuts ─────────────────────────────────────────────────
log "Setting up bash aliases..."
ALIAS_BLOCK='
# ── basitdev custom aliases ──
alias ll="ls -alh"
alias gs="git status"
alias gd="git diff"
alias gl="git log --oneline -20"
alias gp="git push"
alias dc="docker compose"
alias dcu="docker compose up -d"
alias dcd="docker compose down"
alias dps="docker ps --format \"table {{.Names}}\t{{.Status}}\t{{.Ports}}\""
alias py="python3"
alias pip="pip3"
alias venv="python3 -m venv"
alias activate="source .venv/bin/activate"

# PATH additions
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/go/bin:/usr/local/go/bin:$PATH"
'

if ! grep -q "basitdev custom aliases" "$HOME/.bashrc" 2>/dev/null; then
    echo "$ALIAS_BLOCK" >> "$HOME/.bashrc"
    log "Aliases added to .bashrc"
else
    log "Aliases already in .bashrc"
fi

# ── VoiceAgentAPI Project Setup ──────────────────────────────────────────────
log "Setting up VoiceAgentAPI project..."
VOICEAPI_DIR="$HOME/Villaex/VoiceAgentAPI"

if [ -d "$VOICEAPI_DIR" ]; then
    log "VoiceAgentAPI directory found at $VOICEAPI_DIR"

    # API virtual environment
    if [ ! -d "$VOICEAPI_DIR/backend/api/.venv" ]; then
        log "Creating API virtual environment..."
        python3 -m venv "$VOICEAPI_DIR/backend/api/.venv"
        source "$VOICEAPI_DIR/backend/api/.venv/bin/activate"
        pip install --upgrade pip
        pip install -r "$VOICEAPI_DIR/backend/api/requirements.txt"
        deactivate
    else
        log "API venv already exists"
    fi

    # Agent virtual environment
    if [ ! -d "$VOICEAPI_DIR/backend/agent/.venv" ]; then
        log "Creating Agent virtual environment..."
        python3 -m venv "$VOICEAPI_DIR/backend/agent/.venv"
        source "$VOICEAPI_DIR/backend/agent/.venv/bin/activate"
        pip install --upgrade pip
        pip install -r "$VOICEAPI_DIR/backend/agent/requirements.txt"
        deactivate
    else
        log "Agent venv already exists"
    fi

    # Start infrastructure
    log "Starting Docker infrastructure..."
    cd "$VOICEAPI_DIR"
    docker compose up -d postgres redis || warn "Docker compose failed - check docker-compose.yml"

    # Run migrations
    log "Running database migrations..."
    cd "$VOICEAPI_DIR/backend/api"
    source .venv/bin/activate
    alembic upgrade head || warn "Migrations failed - check .env and database connection"
    deactivate
else
    warn "VoiceAgentAPI not found at $VOICEAPI_DIR"
    warn "Clone it first: git clone <repo-url> $VOICEAPI_DIR"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "============================================"
log "Machine setup complete!"
echo "============================================"
echo ""
echo "Installed:"
echo "  Python:     $(python3 --version 2>&1)"
echo "  Node:       $(node --version 2>&1)"
echo "  Docker:     $(docker --version 2>&1)"
echo "  Git:        $(git --version 2>&1)"
echo "  Rust:       $(cargo --version 2>&1 || echo 'restart shell')"
echo "  Go:         $(go version 2>&1 || echo 'restart shell')"
echo "  Claude:     $(claude --version 2>&1 || echo 'installed')"
echo ""
echo "Next steps:"
echo "  1. source ~/.bashrc"
echo "  2. Set up API keys in .env files"
echo "  3. Run: ./setup-langgraph.sh  (to set up AI dev team)"
echo ""
