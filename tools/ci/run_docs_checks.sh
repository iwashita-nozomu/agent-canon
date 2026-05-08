#!/usr/bin/env bash
# @dependency-start
# responsibility Runs docs checks CI automation.
# upstream design ../README.md shared automation index
# @dependency-end

set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WORKSPACE_ROOT"

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "python3 or python is required to run documentation checks" >&2
    exit 127
  fi
fi

MARKDOWN_TARGETS=(
  README.md
  QUICK_START.md
  AGENTS.md
  CLAUDE.md
  agents
  docker
  documents
  scripts
  .github
  .agents/skills
  .codex/README.md
)
EXISTING_MARKDOWN_TARGETS=()
for target in "${MARKDOWN_TARGETS[@]}"; do
  if [ -e "$target" ]; then
    EXISTING_MARKDOWN_TARGETS+=("$target")
  fi
done

echo "════════════════════════════════════════════════════════════════"
echo "📝 Documentation checks"
echo "════════════════════════════════════════════════════════════════"
echo ""

if [ "${#EXISTING_MARKDOWN_TARGETS[@]}" -eq 0 ]; then
  echo "DOCS_CHECKS=skip"
  echo "No documentation targets exist in this checkout."
  exit 0
fi

"$PYTHON_BIN" tools/docs/check_markdown_lint.py "${EXISTING_MARKDOWN_TARGETS[@]}"
"$PYTHON_BIN" tools/docs/check_markdown_math.py "${EXISTING_MARKDOWN_TARGETS[@]}"
"$PYTHON_BIN" tools/docs/audit_and_fix_links.py --check "${EXISTING_MARKDOWN_TARGETS[@]}"
"$PYTHON_BIN" tools/docs/check_bootstrap_docs.py

echo ""
echo "Documentation checks completed successfully"
