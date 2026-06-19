#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Runs dedicated secret scanners against current tree and git history.
# upstream design ../../CONTAINER_OPERATIONS.md shared devcontainer security tooling policy
# downstream environment ../../.devcontainer/post-create.sh installs scanner commands
# downstream design ../../tools/README.md documents the command surface
# downstream design ../../documents/tools/README.md documents operator usage
# @dependency-end

set -euo pipefail

root="."
scan_history=1
scan_current=1
trufflehog_results="${AGENT_CANON_TRUFFLEHOG_RESULTS:-verified,unknown}"
detect_secrets_only_verified="${AGENT_CANON_DETECT_SECRETS_ONLY_VERIFIED:-1}"

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
cd "$root"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    cat >&2 <<EOF
SECRET_SCAN=missing_tool tool=${command_name}
Install the shared devcontainer, rerun .devcontainer/post-create.sh, or install ${command_name} locally before scanning.
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
    mkdir -p "${snapshot_root}/$(dirname "$path")"
    cp -p "$path" "${snapshot_root}/${path}"
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
    scan_root="$(mktemp -d)"
    make_current_tree_snapshot "$scan_root"
    echo "SECRET_SCAN_TOOL=gitleaks mode=current-working-tree"
    status=0
    gitleaks dir --redact --no-banner --exit-code 1 "$scan_root" || status=$?
    rm -rf "$scan_root"
    return "$status"
  fi
}

run_trufflehog() {
  local clone_root
  clone_root="$(mktemp -d)"
  git clone --quiet --no-hardlinks "$root" "$clone_root"
  trap 'rm -rf "$clone_root"' RETURN
  if [ "$scan_history" = "1" ]; then
    echo "SECRET_SCAN_TOOL=trufflehog mode=git-history results=${trufflehog_results}"
    trufflehog git "file://${clone_root}" --no-update --fail --results="$trufflehog_results"
  fi
  if [ "$scan_current" = "1" ]; then
    echo "SECRET_SCAN_TOOL=trufflehog mode=current-head results=${trufflehog_results}"
    trufflehog git "file://${clone_root}" --no-update --fail --max-depth=1 --results="$trufflehog_results"
  fi
  rm -rf "$clone_root"
  trap - RETURN
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
  report_path="$(mktemp)"
  echo "SECRET_SCAN_TOOL=detect-secrets mode=current-tracked-tree only_verified=${detect_secrets_only_verified}"
  detect-secrets "${detect_args[@]}" "${files[@]}" >"$report_path"
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
  rm -f "$report_path"
}

require_git_repo
require_command gitleaks
require_command trufflehog
require_command detect-secrets

run_gitleaks
run_trufflehog
if [ "$scan_current" = "1" ]; then
  run_detect_secrets
fi

echo "SECRET_SCAN=pass root=${root}"
