#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs dedicated secret scanners against current tree and git history.
# upstream design ../../CONTAINER_OPERATIONS.md shared tool-runtime security policy
# upstream implementation ../agent_tools/parent_root_side_effects.py owns scanner scratch allocation and exact cleanup
# downstream environment ../../bootstrap.sh invokes the shared scanner setup
# downstream design ../../tools/README.md documents the command surface
# downstream design ../../documents/tools/README.md documents operator usage
# downstream implementation ../../tests/tools/test_scan_secrets_script.py verifies external read-only scan input and runtime-local scratch
# @dependency-end

set -euo pipefail

root="."
original_args=("$@")
scan_history=1
scan_current=1
trufflehog_results="${AGENT_CANON_TRUFFLEHOG_RESULTS:-verified,unknown}"
detect_secrets_only_verified="${AGENT_CANON_DETECT_SECRETS_ONLY_VERIFIED:-1}"
invocation_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)"
parent_root="${AGENT_CANON_CONTROL_PARENT_ROOT:-${AGENT_CANON_PARENT_ROOT:-}}"
runtime_root="${AGENT_CANON_RUNTIME_ROOT:-}"
script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
boundary_script="${script_root}/tools/agent_tools/parent_root_side_effects.py"
parent_temp_paths=()
created_parent_temp_dir=""

usage() {
  cat <<'EOF'
Usage: bash tools/ci/scan_secrets.sh [--root PATH] [--current-only|--history-only]

Runs gitleaks, trufflehog, and detect-secrets without writing repository state.

Defaults:
  --root .
  scan current tracked tree and full git history
  trufflehog results: verified,unknown
  detect-secrets mode: verified findings only

Environment:
  AGENT_CANON_TRUFFLEHOG_RESULTS=verified,unknown,unverified
  AGENT_CANON_DETECT_SECRETS_ONLY_VERIFIED=0  # include unverified entropy findings
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root)
      root="$2"
      shift 2
      ;;
    --current-only)
      scan_history=0
      scan_current=1
      shift
      ;;
    --history-only)
      scan_history=1
      scan_current=0
      shift
      ;;
    -h | --help)
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

root="$(cd "$root" && pwd -P)"
if [ -z "$parent_root" ]; then
  echo "SECRET_SCAN=missing_control_parent_root" >&2
  exit 2
fi
if [ -z "$runtime_root" ]; then
  echo "SECRET_SCAN=missing_runtime_root" >&2
  exit 2
fi
parent_root="$(cd "$parent_root" && pwd -P)"
runtime_root="$(cd "$runtime_root" && pwd -P)"
case "$runtime_root/" in
  "$parent_root/"*) ;;
  *)
    echo "SECRET_SCAN=runtime_root_outside_control_parent_root" >&2
    exit 2
    ;;
esac
cd "$root"
if [[ "${AGENT_CANON_CHILD_PURPOSE:-}" == "secret-scan-script" ]]; then
  python3 "$boundary_script" verify-child \
    --root "$parent_root" \
    --purpose secret-scan-script \
    --consume >/dev/null
else
  # The control repo and scanned checkout can be distinct.  Bind runtime
  # artifacts to the scanned project while parent_root_side_effects still
  # authenticates the control repository.
  export AGENT_CANON_SOURCE_ROOT="$root"
  exec python3 "$boundary_script" exec-parent-bound \
    --root "$parent_root" \
    --purpose secret-scan-script \
    --issue-handoff \
    -- bash "${BASH_SOURCE[0]}" "${original_args[@]}"
fi
unset AGENT_CANON_CHILD_HANDOFF AGENT_CANON_HANDOFF_AUDIENCE AGENT_CANON_CHILD_PURPOSE

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    cat >&2 <<EOF
SECRET_SCAN=missing_tool tool=${command_name}
Start the shared AgentCanon tool runtime with ./bootstrap.sh, or install ${command_name} locally before scanning.
EOF
    exit 127
  fi
}

require_git_repo() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "SECRET_SCAN=not_git_repo root=${root}" >&2
    exit 2
  fi
}

create_parent_temp_dir() {
  local prefix="$1"
  created_parent_temp_dir="$(
    python3 "$boundary_script" temp-dir \
      --root "$parent_root" \
      --candidate "$runtime_root/secret-scan/tmp" \
      --prefix "$prefix" \
      --purpose secret-scan
  )"
  parent_temp_paths+=("$created_parent_temp_dir")
}

cleanup_parent_temps() {
  local status=$?
  local cleanup_status=0
  local index
  trap - EXIT
  for ((index=${#parent_temp_paths[@]} - 1; index >= 0; index--)); do
    python3 "$boundary_script" remove-tree \
      --root "$parent_root" \
      --candidate "${parent_temp_paths[$index]}" \
      --purpose secret-scan-cleanup >/dev/null || cleanup_status=$?
  done
  if [ "$status" -eq 0 ] && [ "$cleanup_status" -ne 0 ]; then
    status=$cleanup_status
  fi
  exit "$status"
}

collect_current_scan_files() {
  local path

  while IFS= read -r -d '' path; do
    if [ ! -f "$path" ] || [ -L "$path" ]; then
      continue
    fi
    printf '%s\0' "$path"
  done < <(git ls-files --cached --others --exclude-standard -z)
}

make_current_tree_snapshot() {
  local path
  local snapshot_root="$1"

  while IFS= read -r -d '' path; do
    python3 "$boundary_script" copy-read-only \
      --root "$parent_root" \
      --source "${root}/${path}" \
      --candidate "${snapshot_root}/${path}" \
      --purpose secret-scan-current-snapshot >/dev/null
  done < <(collect_current_scan_files)
}

run_gitleaks() {
  local scan_root
  local status

  if [ "$scan_history" = "1" ]; then
    echo "SECRET_SCAN_TOOL=gitleaks mode=git-history"
    gitleaks git --redact --no-banner --exit-code 1 "$root"
  fi
  if [ "$scan_current" = "1" ]; then
    create_parent_temp_dir gitleaks-current.
    scan_root="$created_parent_temp_dir"
    make_current_tree_snapshot "$scan_root"
    echo "SECRET_SCAN_TOOL=gitleaks mode=current-working-tree"
    status=0
    gitleaks dir --redact --no-banner --exit-code 1 "$scan_root" || status=$?
    return "$status"
  fi
}

run_trufflehog() {
  local clone_root
  create_parent_temp_dir trufflehog-clone.
  clone_root="$created_parent_temp_dir"
  git clone --quiet --no-hardlinks "$root" "$clone_root"
  if [ "$scan_history" = "1" ]; then
    echo "SECRET_SCAN_TOOL=trufflehog mode=git-history results=${trufflehog_results}"
    trufflehog git "file://${clone_root}" --no-update --fail --results="$trufflehog_results"
  fi
  if [ "$scan_current" = "1" ]; then
    echo "SECRET_SCAN_TOOL=trufflehog mode=current-head results=${trufflehog_results}"
    trufflehog git "file://${clone_root}" --no-update --fail --max-depth=1 --results="$trufflehog_results"
  fi
}

run_detect_secrets() {
  local detect_args
  local files
  local report_path

  detect_args=(scan)
  if [ "$detect_secrets_only_verified" = "1" ]; then
    detect_args+=(--only-verified)
  fi
  files=()
  while IFS= read -r -d '' path; do
    files+=("$path")
  done < <(collect_current_scan_files)
  if [ "${#files[@]}" -eq 0 ]; then
    echo "SECRET_SCAN_DETECT_SECRETS_FINDINGS=0 reason=no-tracked-files"
    return
  fi
  create_parent_temp_dir detect-secrets-report.
  report_path="$created_parent_temp_dir/report.json"
  echo "SECRET_SCAN_TOOL=detect-secrets mode=current-tracked-tree only_verified=${detect_secrets_only_verified}"
  python3 "$boundary_script" capture-subprocess \
    --root "$parent_root" \
    --candidate "$report_path" \
    --purpose secret-scan-detect-secrets-report \
    -- detect-secrets "${detect_args[@]}" "${files[@]}" >/dev/null
  python3 - "$report_path" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
results = report.get("results", {})
count = sum(len(items) for items in results.values())
if count:
    print(f"SECRET_SCAN_DETECT_SECRETS_FINDINGS={count}")
    for path, items in sorted(results.items()):
        print(f"SECRET_SCAN_DETECT_SECRETS_PATH={path} findings={len(items)}")
    raise SystemExit(1)
print("SECRET_SCAN_DETECT_SECRETS_FINDINGS=0")
PY
}

require_git_repo
if [ ! -f "$boundary_script" ]; then
  echo "SECRET_SCAN=missing_boundary path=${boundary_script}" >&2
  exit 2
fi
trap cleanup_parent_temps EXIT
require_command gitleaks
require_command trufflehog
require_command detect-secrets

run_gitleaks
run_trufflehog
if [ "$scan_current" = "1" ]; then
  run_detect_secrets
fi

echo "SECRET_SCAN=pass root=${root}"
