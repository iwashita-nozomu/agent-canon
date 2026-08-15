#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs PR dependency completeness from trusted changed paths and tracked source manifests.
# upstream design ../../documents/design/dependency-manifest-design.md source-owned dependency validation contract
# upstream implementation ../agent_tools/run_repo_dependency_review.sh validates source headers, relations, and cycles
# upstream implementation ../agent_tools/tool_drift.py validates standalone tool links from source facts
# upstream implementation ../agent_tools/render_dependency_manifest_graph.py renders optional source projections
# downstream implementation ./check_agent_canon_pr.sh records the source dependency gate receipt
# downstream implementation ../../tests/tools/test_agent_canon_pr_dependency_source_gate.py verifies the no-runtime route
# @dependency-end
set -euo pipefail

ROOT=""
TOOLS_ROOT=""
REPORT_DIR=""
CHANGED_PATH_PACKET=""
TRUSTED_BASE_SHA=""
REPOSITORY_MODE=""
SOURCE_REVIEW_REQUIRED=""

usage() {
  cat <<'EOF'
Usage:
  run_pr_dependency_source_gate.sh \
    --root DIR \
    --tools-root DIR \
    --report-dir DIR \
    --changed-path-packet FILE \
    --trusted-base-sha SHA \
    --repository-mode standalone_source|template_or_derived \
    --source-review-required 0|1

Runs the PR dependency gate from tracked source. It never builds, queries, or
reads persisted graph runtime state.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT="$2"
      shift 2
      ;;
    --tools-root)
      TOOLS_ROOT="$2"
      shift 2
      ;;
    --report-dir)
      REPORT_DIR="$2"
      shift 2
      ;;
    --changed-path-packet)
      CHANGED_PATH_PACKET="$2"
      shift 2
      ;;
    --trusted-base-sha)
      TRUSTED_BASE_SHA="$2"
      shift 2
      ;;
    --repository-mode)
      REPOSITORY_MODE="$2"
      shift 2
      ;;
    --source-review-required)
      SOURCE_REVIEW_REQUIRED="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$ROOT" || -z "$TOOLS_ROOT" || -z "$REPORT_DIR" \
  || -z "$CHANGED_PATH_PACKET" || -z "$TRUSTED_BASE_SHA" \
  || -z "$REPOSITORY_MODE" || -z "$SOURCE_REVIEW_REQUIRED" ]]; then
  echo "AGENT_CANON_PR_DEPENDENCY_SOURCE=fail reason=required_argument_missing"
  exit 2
fi
ROOT="$(realpath -e "$ROOT")" || {
  echo "AGENT_CANON_PR_DEPENDENCY_SOURCE=fail reason=root_missing"
  exit 2
}
TOOLS_ROOT="$(realpath -e "$TOOLS_ROOT")" || {
  echo "AGENT_CANON_PR_DEPENDENCY_SOURCE=fail reason=tools_root_missing"
  exit 2
}
case "$REPOSITORY_MODE" in
  standalone_source|template_or_derived) ;;
  *)
    echo "AGENT_CANON_PR_DEPENDENCY_SOURCE=fail reason=repository_mode_invalid"
    exit 2
    ;;
esac
case "$SOURCE_REVIEW_REQUIRED" in
  0|1) ;;
  *)
    echo "AGENT_CANON_PR_DEPENDENCY_SOURCE=fail reason=required_flag_invalid"
    exit 2
    ;;
esac
if [[ ! "$TRUSTED_BASE_SHA" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "AGENT_CANON_PR_DEPENDENCY_SOURCE=fail reason=trusted_base_invalid"
  exit 2
fi
if [[ ! -f "$CHANGED_PATH_PACKET" ]]; then
  echo "AGENT_CANON_PR_DEPENDENCY_SOURCE=fail reason=changed_path_packet_missing"
  exit 2
fi

cd "$ROOT"
review=(
  bash "${TOOLS_ROOT}/agent_tools/run_repo_dependency_review.sh"
  --root "$ROOT"
  --fail-missing
  --changed-path-packet "$CHANGED_PATH_PACKET"
  --trusted-base-sha "$TRUSTED_BASE_SHA"
  --report-dir "$REPORT_DIR"
)

if [[ "$SOURCE_REVIEW_REQUIRED" -eq 0 ]]; then
  "${review[@]}" --header-scan-only
  echo "AGENT_CANON_PR_DEPENDENCY_SOURCE=skipped"
  echo "AGENT_CANON_PR_DEPENDENCY_SOURCE_REASON=changed_paths_outside_declared_surfaces"
  exit 0
fi

if [[ "$REPOSITORY_MODE" == "standalone_source" ]]; then
  python3 "${TOOLS_ROOT}/agent_tools/tool_drift.py" --root "$ROOT"
fi
"${review[@]}" --cycle-report-only
python3 "${TOOLS_ROOT}/agent_tools/render_dependency_manifest_graph.py" \
  --root "$ROOT" \
  --scope full \
  --markdown-out "$REPORT_DIR/dependency_manifest_graph.md" \
  --dot-out "$REPORT_DIR/dependency_manifest_graph.dot"

echo "AGENT_CANON_PR_DEPENDENCY_SOURCE=source"
echo "AGENT_CANON_PR_DEPENDENCY_SOURCE_REASON=tracked_source_validated"
