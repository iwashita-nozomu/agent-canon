#!/usr/bin/env bash
# Dependency Files:
# - vendor/agent-canon/AGENTS.md
# - vendor/agent-canon/agents/canonical/CODEX_WORKFLOW.md
# - vendor/agent-canon/tools/README.md
set -euo pipefail
# Check each git worktree for WORKTREE_SCOPE.md and report
OUT=reports/worktree_scope_report.txt
mkdir -p $(dirname "$OUT")
echo "Worktree scope check" > "$OUT"
git worktree list --porcelain | awk '/worktree /{print $2}' | while read -r wt; do
  echo "Worktree: $wt" >> "$OUT"
  if [ -f "$wt/WORKTREE_SCOPE.md" ]; then
    echo "  OK: WORKTREE_SCOPE.md present" >> "$OUT"
  else
    echo "  MISSING: WORKTREE_SCOPE.md" >> "$OUT"
  fi
done
echo "Report written to $OUT"
cat "$OUT"
