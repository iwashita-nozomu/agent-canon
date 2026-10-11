#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Preserves the legacy scanner entrypoint as a thin SCIP query launcher.
# upstream design ../../../agents/skills/dependency-analysis.md owns optional code-impact evidence.
# upstream implementation ./scip_index.py reads canonical SCIP indexes and projects selected facts.
# downstream implementation ../../../tests/agent_tools/test_dependency_manifest_tools.py verifies the launcher.
# downstream design ../../README.md documents agent tool inventory.
# @dependency-end
set -euo pipefail

TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      cat <<'EOF'
Usage:
  scan_code_dependencies.sh --root DIR --runtime-root DIR --index index.scip [--index ...] --path PATH [--path PATH...]

Compatibility launcher for the standard SCIP query API. The index is produced
by a selected native indexer and must be an external runtime artifact.
This command does not scan source text or provide lexical fallback evidence.
EOF
      exit 0
      ;;
  esac
fi

exec python3 "$TOOL_DIR/scip_index.py" query "$@"
