#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Extracts source-code dependency edges independently from manifest headers.
# upstream design ../../agents/workflows/hypothesis-validation-workflow.md analysis-first workflow contract
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py verifies scanner behavior
# downstream design ../../tools/README.md documents agent tool inventory
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHANGED=0
PRINT_UNRESOLVED=0
PATHS_FILE=""
ANALYSIS_JSON=""
LEXICAL_ONLY=0
declare -a INPUT_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  scan_code_dependencies.sh [--root DIR] [--changed] [--print-unresolved] [--paths-file FILE] [--analysis-json FILE] [--lexical-only] [paths...]

Delegates normal code dependency extraction to the canonical LSP scan-legacy
report.  The lexical compatibility extractor is available only with
--lexical-only.
This is intentionally separate from dependency manifest header tools:
  - Python: import / from import
  - C/C++: local #include "..."
  - shell: source / . relative-file
  - Rust: LSP/lexical analysis-json sidecar only (no legacy TSV rows)

Output columns:
  CODE_DEPENDENCY<TAB>language<TAB>kind<TAB>source<TAB>target<TAB>symbol<TAB>raw
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT_DIR="$2"
      shift 2
      ;;
    --changed)
      CHANGED=1
      shift
      ;;
    --print-unresolved)
      PRINT_UNRESOLVED=1
      shift
      ;;
    --paths-file)
      [[ $# -ge 2 ]] || { echo "scan_code_dependencies.sh: --paths-file requires a value" >&2; exit 2; }
      PATHS_FILE="$2"
      shift 2
      ;;
    --analysis-json)
      [[ $# -ge 2 ]] || { echo "scan_code_dependencies.sh: --analysis-json requires a value" >&2; exit 2; }
      ANALYSIS_JSON="$2"
      shift 2
      ;;
    --lexical-only)
      LEXICAL_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      INPUT_PATHS+=("$1")
      shift
      ;;
  esac
done

cd "$ROOT_DIR"

if [[ -n "$PATHS_FILE" ]]; then
  if [[ ${#INPUT_PATHS[@]} -gt 0 || "$CHANGED" -eq 1 ]]; then
    echo "scan_code_dependencies.sh: --paths-file cannot be combined with --changed or positional paths" >&2
    exit 2
  fi
  if [[ "$PATHS_FILE" != /* ]]; then
    PATHS_FILE="$ROOT_DIR/$PATHS_FILE"
  fi
  if [[ ! -f "$PATHS_FILE" || -L "$PATHS_FILE" ]]; then
    echo "scan_code_dependencies.sh: --paths-file must name a regular non-symlink file" >&2
    exit 2
  fi
fi

lsp_args=("$TOOL_DIR/lsp_code_analysis.py" scan-legacy --root "$ROOT_DIR")
[[ "$PRINT_UNRESOLVED" -eq 1 ]] && lsp_args+=(--print-unresolved)
[[ "$LEXICAL_ONLY" -eq 1 ]] && lsp_args+=(--lexical-only)
[[ -n "$ANALYSIS_JSON" ]] && lsp_args+=(--analysis-json "$ANALYSIS_JSON")
if [[ "$CHANGED" -eq 1 && ${#INPUT_PATHS[@]} -eq 0 ]]; then
  lsp_args+=(--changed)
elif [[ -n "$PATHS_FILE" ]]; then
  lsp_args+=(--paths-file "$PATHS_FILE")
elif [[ ${#INPUT_PATHS[@]} -gt 0 ]]; then
  lsp_args+=(--files "${INPUT_PATHS[@]}")
fi
exec python3 "${lsp_args[@]}"
