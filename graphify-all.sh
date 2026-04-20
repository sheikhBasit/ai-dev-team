#!/usr/bin/env bash
# graphify-all.sh
# 1. Runs /understand (builds knowledge graph) in every repo if graph is missing.
# 2. Commits + pushes .understand-anything/ and this script only for sheikhBasit-owned repos.
# 3. All other repos: local-only (no git touch).
#
# Repos that also get this script + README section:
#   SecondBrain, ai-dev-team, MeetSync, Quran_App, VoiceNote,
#   ashi, env-mcp-server, fixibot-backend, log-mcp-server,
#   openapi-mcp-server, pasha, pg-mcp-server

set -euo pipefail

SCRIPT_PATH="$(realpath "$0")"
CLAUDE_CMD="claude --dangerously-skip-permissions --print"

# ── Repo registry ─────────────────────────────────────────────────────────────
# push=1 → commit+push to GitHub (sheikhBasit owned)
# push=0 → local only
declare -A REPOS=(
  ["/home/basitdev/Me/ai-dev-team"]=1
  ["/home/basitdev/Me/basit-knowledge-graph"]=1
  ["/home/basitdev/Me/BMS"]=1
  ["/home/basitdev/Me/daraqutni_scraper"]=0
  ["/home/basitdev/Me/ibn_khuzaymah_scraper"]=0
  ["/home/basitdev/Me/IImiAI-Hadith-AbdulBasit"]=0   # nxbsolution owned
  ["/home/basitdev/Me/IImiAI-Tafseer-AbdulBasit"]=0  # nxbsolution owned
  ["/home/basitdev/Me/MeetSync"]=1
  ["/home/basitdev/Me/mishkat_scraper"]=0
  ["/home/basitdev/Me/portfolio"]=0
  ["/home/basitdev/Me/Quran_App"]=1
  ["/home/basitdev/Me/sheikhBasit"]=1
  ["/home/basitdev/Me/tams"]=0                       # usm4nhafeez owned
  ["/home/basitdev/Me/VoiceNote"]=1
  ["/home/basitdev/Me/Worksheet daily"]=1
  ["/home/basitdev/workspace/ashi"]=1
  ["/home/basitdev/workspace/deerflow"]=0            # bytedance owned
  ["/home/basitdev/workspace/env-mcp-server"]=1
  ["/home/basitdev/workspace/fixibot-backend"]=1
  ["/home/basitdev/workspace/log-mcp-server"]=1
  ["/home/basitdev/workspace/observability"]=0
  ["/home/basitdev/workspace/openapi-mcp-server"]=1
  ["/home/basitdev/workspace/pasha"]=1
  ["/home/basitdev/workspace/pg-mcp-server"]=1
  ["/home/basitdev/workspace/resume-optimizer"]=0
  ["/home/basitdev/Developer/villaex"]=0             # local only per instruction
  ["/home/basitdev/SecondBrain"]=0                   # local vault
)

# Repos that get this script + README knowledge graph section copied into them
SCRIPT_REPOS=(
  "/home/basitdev/SecondBrain"
  "/home/basitdev/Me/ai-dev-team"
  "/home/basitdev/Me/MeetSync"
  "/home/basitdev/Me/Quran_App"
  "/home/basitdev/Me/VoiceNote"
  "/home/basitdev/workspace/ashi"
  "/home/basitdev/workspace/env-mcp-server"
  "/home/basitdev/workspace/fixibot-backend"
  "/home/basitdev/workspace/log-mcp-server"
  "/home/basitdev/workspace/openapi-mcp-server"
  "/home/basitdev/workspace/pasha"
  "/home/basitdev/workspace/pg-mcp-server"
)

README_SECTION='
---

## Knowledge Graph

This repo is indexed by [Understand Anything](https://github.com/Lum1104/Understand-Anything) — a multi-agent pipeline that builds a knowledge graph of every file, function, class, and dependency.

The graph lives at `.understand-anything/knowledge-graph.json` and can be explored visually:

```bash
# In Claude Code, from this repo root:
/understand-dashboard
```

To rebuild the graph after major changes:

```bash
~/scripts/graphify-all.sh
```

> Graph covers: files · functions · classes · imports · architecture layers · plain-English summaries · guided tours.'

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; }

pushed=0
local_only=0
failed=0

# ── Step 1: Copy script + README section into designated repos ─────────────────
echo "── Syncing script + README section ──────────────────────────────────────"
for dir in "${SCRIPT_REPOS[@]}"; do
  [ -d "$dir" ] || continue

  # Copy this script into the repo root
  cp "$SCRIPT_PATH" "$dir/graphify-all.sh"
  chmod +x "$dir/graphify-all.sh"

  # Append README section if not already present
  readme="$dir/README.md"
  [ -f "$readme" ] || echo "# $(basename "$dir")" > "$readme"
  if ! grep -q "Knowledge Graph" "$readme" 2>/dev/null; then
    echo "$README_SECTION" >> "$readme"
    ok "README updated: $dir"
  fi
done

# ── Step 2: Build graphs + commit/push ────────────────────────────────────────
echo ""
echo "── Processing repos ─────────────────────────────────────────────────────"
for dir in "${!REPOS[@]}"; do
  push="${REPOS[$dir]}"

  if [ ! -d "$dir" ]; then
    warn "Skipping (not found): $dir"
    continue
  fi

  graph="$dir/.understand-anything/knowledge-graph.json"

  if [ ! -f "$graph" ]; then
    warn "No graph found for $dir — building..."
    mkdir -p "$dir/.understand-anything"
    (cd "$dir" && $CLAUDE_CMD "/understand" 2>/dev/null) || {
      fail "Could not build graph for $dir"
      failed=$((failed+1))
      continue
    }
  fi

  if [ "$push" -eq 0 ]; then
    ok "Local-only: $dir"
    local_only=$((local_only+1))
    continue
  fi

  if [ ! -d "$dir/.git" ]; then
    warn "No .git in $dir — skipping push"
    local_only=$((local_only+1))
    continue
  fi

  (
    set +e
    cd "$dir"

    # Ensure .understand-anything is not gitignored
    if [ -f .gitignore ] && grep -q "^\.understand-anything" .gitignore 2>/dev/null; then
      sed -i '/^\.understand-anything/d' .gitignore
      git add .gitignore
    fi

    git add .understand-anything/ README.md 2>/dev/null || true
    [ -f graphify-all.sh ] && git add graphify-all.sh || true

    git diff --cached --quiet 2>/dev/null
    has_changes=$?
    if [ "$has_changes" -eq 0 ]; then
      ok "Nothing new to commit: $dir"
      exit 0
    fi
    git commit -m "chore: add knowledge graph and graphify script" || exit 1
    git push origin HEAD || exit 1
  ) && { ok "Pushed: $dir"; pushed=$((pushed+1)); } || { fail "Push failed: $dir"; failed=$((failed+1)); }

done

echo ""
echo "────────────────────────────────────"
echo "  Pushed:     $pushed repos"
echo "  Local-only: $local_only repos"
echo "  Failed:     $failed repos"
echo "────────────────────────────────────"
