#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs dedicated secret scanners against current tree and git history.
# upstream design ../../../../CONTAINER_OPERATIONS.md shared tool-runtime security policy
# upstream implementation ../../../runtime/dispatch/agent-canon/src/runtime_boundary.rs owns scanner scratch allocation and exact cleanup
# downstream environment ../../../../bootstrap.sh invokes the shared scanner setup
# downstream design ../../../README.md documents the command surface
# downstream design ../../../../documents/tools/README.md documents operator usage
# downstream implementation ../../../../tests/tools/test_scan_secrets_script.py verifies external read-only scan input and runtime-local scratch
# @dependency-end

set -euo pipefail

root="."
scan_history=1
scan_current=1
trufflehog_results="${AGENT_CANON_TRUFFLEHOG_RESULTS:-verified,unknown}"
detect_secrets_only_verified="${AGENT_CANON_DETECT_SECRETS_ONLY_VERIFIED:-1}"
invocation_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)"
parent_root="${AGENT_CANON_CONTROL_PARENT_ROOT:-${AGENT_CANON_PARENT_ROOT:-}}"
runtime_root="${AGENT_CANON_RUNTIME_ROOT:-}"
script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd -P)"
boundary_cli="${AGENT_CANON_NATIVE_BIN:-${AGENT_CANON_CLI:-${script_root}/tools/bin/agent-canon}}"
parent_temp_paths=()
created_parent_temp_dir=""

run_boundary() {
  local action="$1"
  shift
  "$boundary_cli" runtime-paths "$action" --source-root "$root" --runtime-root "$runtime_root" "$@"
}

usage() {
  cat <<'EOF'
Usage: bash tools/validation/ci/checks/scan_secrets.sh [--root PATH] [--current-only|--history-only]

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
export AGENT_CANON_SOURCE_ROOT="$root"
unset AGENT_CANON_CHILD_HANDOFF AGENT_CANON_HANDOFF_AUDIENCE AGENT_CANON_CHILD_PURPOSE

# Scanner scratch and tool caches remain inside the caller's runtime.
# Validate every caller override before creating any of these directories.
scanner_environment_names=(TMPDIR TEMP TMP XDG_CACHE_HOME PYTHONPYCACHEPREFIX AGENT_CANON_TOOLS_HOME CARGO_HOME CARGO_TARGET_DIR AGENT_CANON_CLI_TARGET_DIR)
scanner_environment_defaults=(tmp tmp tmp cache cache/pycache tools cache/cargo-home cache/cargo-target cache/cargo-target)
scanner_environment_paths=()
for index in "${!scanner_environment_names[@]}"; do
  name="${scanner_environment_names[$index]}"
  candidate="${!name:-${runtime_root}/${scanner_environment_defaults[$index]}}"
  scanner_environment_paths+=("$(run_boundary path --candidate "$candidate")")
done
if [[ "${scanner_environment_paths[7]}" != "${scanner_environment_paths[8]}" ]]; then
  echo "SECRET_SCAN=target_alias_mismatch" >&2
  exit 2
fi
for index in "${!scanner_environment_names[@]}"; do
  run_boundary ensure-dir --candidate "${scanner_environment_paths[$index]}" >/dev/null
  export "${scanner_environment_names[$index]}=${scanner_environment_paths[$index]}"
done

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
    run_boundary temp-dir \
      --candidate "$runtime_root/secret-scan/tmp" \
      --prefix "$prefix"
  )"
  parent_temp_paths+=("$created_parent_temp_dir")
}

cleanup_parent_temps() {
  local status=$?
  local cleanup_status=0
  local index
  trap - EXIT
  for ((index=${#parent_temp_paths[@]} - 1; index >= 0; index--)); do
    run_boundary remove-tree \
      --candidate "${parent_temp_paths[$index]}" >/dev/null || cleanup_status=$?
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
    run_boundary copy-read-only \
      --source "${root}/${path}" \
      --candidate "${snapshot_root}/${path}" >/dev/null
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
  run_boundary capture-subprocess \
    --candidate "$report_path" \
    -- detect-secrets "${detect_args[@]}" "${files[@]}" >/dev/null
  "$boundary_cli" runtime-paths detect-secrets-report --input "$report_path"
}

require_git_repo
if [ ! -x "$boundary_cli" ]; then
  echo "SECRET_SCAN=missing_boundary path=${boundary_cli}" >&2
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
