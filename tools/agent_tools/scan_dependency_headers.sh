#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides scan dependency headers agent workflow automation.
# upstream design ../../documents/design/source-owned-dependency-validation.md tracked-source authority
# upstream design ../../documents/design/dependency-manifest-design.md dependency manifest DSL design
# downstream implementation ./check_dependency_header_format.sh validates manifest syntax
# downstream implementation ./check_dependency_graph.sh consumes manifest edges
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
FAIL_MISSING=0
CHANGED=0
EXPLAIN_MISSING=0
ALLOW_FRONTMATTER=0
HEADER_SCAN_LINES="${DEPENDENCY_HEADER_SCAN_LINES:-80}"
MISSING_PREVIEW_LINES="${DEPENDENCY_MISSING_PREVIEW_LINES:-20}"
CHANGED_PATH_PACKET=""
TRUSTED_BASE_SHA=""
declare -a INPUT_PATHS=()
declare -a CHANGED_PATHS=()
declare -a BASELINE_MISSING_PATHS=()
declare -a CHANGED_MISSING_PATHS=()
declare -A CHANGED_PATH_SET=()
declare -a DECLARED_SURFACES=()

usage() {
  cat <<'EOF'
Usage:
  scan_dependency_headers.sh [--root DIR] [--changed] [--fail-missing] [--allow-frontmatter] [--explain-missing] [--changed-path-packet FILE] [--trusted-base-sha SHA] [paths...]

Scans checkable text files for @dependency-start / @dependency-end manifest markers.
Without --fail-missing this is report-only and exits 0.
--allow-frontmatter is accepted for policy-explicit callers; frontmatter is allowed by default.
--explain-missing prints a short first-lines preview and owner classification for missing manifests.
--changed-path-packet validates trusted PR base/head path evidence, reports unchanged missing
headers as baseline, and makes only changed missing headers blocking under --fail-missing.
--trusted-base-sha binds the packet to the caller's independently trusted PR base.
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
    --fail-missing)
      FAIL_MISSING=1
      shift
      ;;
    --allow-frontmatter)
      ALLOW_FRONTMATTER=1
      shift
      ;;
    --explain-missing)
      EXPLAIN_MISSING=1
      shift
      ;;
    --changed-path-packet)
      [[ $# -ge 2 ]] || { echo "DEPENDENCY_HEADER_SCAN=fail reason=changed_path_packet_argument_missing"; exit 2; }
      CHANGED_PATH_PACKET="$2"
      shift 2
      ;;
    --trusted-base-sha)
      [[ $# -ge 2 ]] || { echo "DEPENDENCY_HEADER_SCAN=fail reason=trusted_base_argument_missing"; exit 2; }
      TRUSTED_BASE_SHA="$2"
      shift 2
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
ROOT_DIR="$(pwd -P)"

load_declared_surfaces() {
  local registry="${DEPENDENCY_CONTRACT_KIND_REGISTRY:-}"
  if [[ -z "$registry" && -f "$ROOT_DIR/documents/design/dependency-contract-kinds.toml" ]]; then
    registry="$ROOT_DIR/documents/design/dependency-contract-kinds.toml"
  elif [[ -z "$registry" && -f "$ROOT_DIR/vendor/agent-canon/documents/design/dependency-contract-kinds.toml" ]]; then
    registry="$ROOT_DIR/vendor/agent-canon/documents/design/dependency-contract-kinds.toml"
  elif [[ -z "$registry" ]]; then
    local script_path script_dir
    script_path="$(readlink -f "${BASH_SOURCE[0]}")"
    script_dir="$(cd "$(dirname "$script_path")" && pwd)"
    registry="$(realpath -m "$script_dir/../../documents/design/dependency-contract-kinds.toml")"
  fi
  [[ -f "$registry" ]] || return 0
  awk '''
    /^header_surfaces[[:space:]]*=[[:space:]]*\[/ { in_block = 1; next }
    in_block && /^[[:space:]]*\]/ { exit }
    in_block {
      line = $0
      while (match(line, /"[^"]+"/)) {
        print substr(line, RSTART + 1, RLENGTH - 2)
        line = substr(line, RSTART + RLENGTH)
      }
    }
  ''' "$registry"
}
mapfile -t DECLARED_SURFACES < <(load_declared_surfaces)

matches_declared_surface() {
  local path="$1"
  local pattern=""
  for pattern in "${DECLARED_SURFACES[@]}"; do
    case "$pattern" in
      "$path") return 0 ;;
      */**)
        local prefix="${pattern%/**}"
        [[ "$path" == "$prefix"/* ]] && return 0
        ;;
      *) [[ "$path" == $pattern ]] && return 0 ;;
    esac
  done
  return 1
}

packet_fail() {
  echo "DEPENDENCY_HEADER_SCAN=fail"
  echo "DEPENDENCY_HEADER_SCAN_REASON=$1"
  exit 2
}

load_changed_path_packet() {
  local packet_path="$CHANGED_PATH_PACKET"
  local packet_schema packet_root packet_base_sha packet_head_sha packet_base_tree
  local packet_head_tree packet_merge_base packet_digest packet_paths actual_paths
  [[ -n "$packet_path" ]] || return 0
  command -v jq >/dev/null 2>&1 || packet_fail "changed_path_packet_jq_missing"
  [[ "$TRUSTED_BASE_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || packet_fail "trusted_base_argument_missing_or_invalid"
  packet_path="$(realpath -m "$packet_path")"
  [[ -f "$packet_path" && ! -L "$packet_path" ]] || packet_fail "changed_path_packet_missing_or_wrong_type"
  if ! jq -e '
    type == "object" and
    .schema == "agent-canon.pr-changed-paths.v1" and
    (.root | type == "string" and length > 0) and
    (.base_sha | type == "string" and test("^[0-9a-fA-F]{40}$")) and
    (.base_source | type == "string" and length > 0) and
    (.base_tree | type == "string" and test("^[0-9a-fA-F]{40}$")) and
    (.head_sha | type == "string" and test("^[0-9a-fA-F]{40}$")) and
    (.head_tree | type == "string" and test("^[0-9a-fA-F]{40}$")) and
    (.merge_base | type == "string" and test("^[0-9a-fA-F]{40}$")) and
    (.changed_paths | type == "array" and all(.[]; type == "string" and length > 0)) and
    (.changed_paths_sha256 | type == "string" and test("^[0-9a-f]{64}$"))
  ' "$packet_path" >/dev/null; then
    packet_fail "changed_path_packet_invalid"
  fi
  [[ -z "${INPUT_PATHS[*]}" ]] || packet_fail "changed_path_packet_input_paths_conflict"
  packet_schema="$(jq -r '.schema' "$packet_path")"
  packet_root="$(jq -r '.root' "$packet_path")"
  packet_base_sha="$(jq -r '.base_sha' "$packet_path")"
  packet_head_sha="$(jq -r '.head_sha' "$packet_path")"
  packet_base_tree="$(jq -r '.base_tree' "$packet_path")"
  packet_head_tree="$(jq -r '.head_tree' "$packet_path")"
  packet_merge_base="$(jq -r '.merge_base' "$packet_path")"
  packet_digest="$(jq -r '.changed_paths_sha256' "$packet_path")"
  [[ "$packet_schema" == "agent-canon.pr-changed-paths.v1" ]] || packet_fail "changed_path_packet_schema_mismatch"
  [[ "$packet_root" == "$ROOT_DIR" ]] || packet_fail "changed_path_packet_root_mismatch"
  [[ "$packet_base_sha" == "$TRUSTED_BASE_SHA" ]] || packet_fail "changed_path_packet_trusted_base_mismatch"

  local resolved_trusted_base resolved_base resolved_base_tree resolved_head_tree resolved_merge_base
  resolved_trusted_base="$(git rev-parse --verify --end-of-options "${TRUSTED_BASE_SHA}^{commit}" 2>/dev/null)" || packet_fail "trusted_base_unresolved"
  [[ "$resolved_trusted_base" == "$TRUSTED_BASE_SHA" ]] || packet_fail "trusted_base_identity_mismatch"
  resolved_base="$(git rev-parse --verify --end-of-options "${packet_base_sha}^{commit}" 2>/dev/null)" || packet_fail "changed_path_packet_base_unresolved"
  [[ "$resolved_base" == "$packet_base_sha" ]] || packet_fail "changed_path_packet_base_identity_mismatch"
  resolved_base_tree="$(git rev-parse --verify --end-of-options "${packet_base_sha}^{tree}" 2>/dev/null)" || packet_fail "changed_path_packet_base_tree_unresolved"
  [[ "$resolved_base_tree" == "$packet_base_tree" ]] || packet_fail "changed_path_packet_base_tree_mismatch"
  resolved_head_tree="$(git rev-parse --verify --end-of-options "${packet_head_sha}^{tree}" 2>/dev/null)" || packet_fail "changed_path_packet_head_tree_unresolved"
  [[ "$(git rev-parse HEAD 2>/dev/null)" == "$packet_head_sha" ]] || packet_fail "changed_path_packet_head_identity_mismatch"
  [[ "$resolved_head_tree" == "$packet_head_tree" ]] || packet_fail "changed_path_packet_head_tree_mismatch"
  resolved_merge_base="$(git merge-base "$packet_base_sha" "$packet_head_sha" 2>/dev/null)" || packet_fail "changed_path_packet_merge_base_unresolved"
  [[ "$resolved_merge_base" == "$packet_merge_base" ]] || packet_fail "changed_path_packet_merge_base_mismatch"

  packet_paths="$(jq -r '.changed_paths[]' "$packet_path")"
  actual_paths="$(git diff --name-only "${packet_base_sha}...${packet_head_sha}" -- 2>/dev/null)" || packet_fail "changed_path_packet_diff_failed"
  [[ "$packet_paths" == "$actual_paths" ]] || packet_fail "changed_path_packet_paths_mismatch"
  local computed_digest
  computed_digest="$(jq -j '.changed_paths | join("\u0000")' "$packet_path" | sha256sum | awk '{print $1}')" || packet_fail "changed_path_packet_digest_failed"
  [[ "$computed_digest" == "$packet_digest" ]] || packet_fail "changed_path_packet_digest_mismatch"
  mapfile -t CHANGED_PATHS < <(jq -r '.changed_paths[]' "$packet_path")
  local changed_path
  for changed_path in "${CHANGED_PATHS[@]}"; do
    [[ -n "$changed_path" ]] || packet_fail "changed_path_packet_empty_path"
    [[ -z "${CHANGED_PATH_SET[$changed_path]+present}" ]] || packet_fail "changed_path_packet_duplicate_path"
    CHANGED_PATH_SET["$changed_path"]=1
  done
}

load_changed_path_packet

is_checkable_suffix() {
  case "$1" in
    *.bash|*.cfg|*.css|*.h|*.hpp|*.html|*.c|*.cc|*.cpp|*.md|*.py|*.rst|*.sh|*.toml|*.txt|*.yaml|*.yml|*.zsh)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_skip_path() {
  case "$1" in
    .git/*|.pytest_cache/*|.ruff_cache/*|reports/*|tests/fixtures/nvidia/*.txt|LICENSE|LICENSE.*|NOTICE|NOTICE.*|COPYING|COPYING.*|vendor/agent-canon/LICENSE|vendor/agent-canon/LICENSE.*|vendor/agent-canon/NOTICE|vendor/agent-canon/NOTICE.*|vendor/agent-canon/COPYING|vendor/agent-canon/COPYING.*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_binary_file() {
  LC_ALL=C grep -Iq . "$1" 2>/dev/null
}

has_manifest_marker() {
  local path="$1"
  local marker="$2"
  awk -v max_lines="$HEADER_SCAN_LINES" -v marker="$marker" '
    NR > max_lines { exit 1 }
    index($0, marker) { found = 1; exit 0 }
    END {
      if (!found) {
        exit 1
      }
    }
  ' "$path"
}

has_manifest_markers() {
  local path="$1"
  has_manifest_marker "$path" '@dependency-start' &&
    has_manifest_marker "$path" '@dependency-end'
}

display_path() {
  local raw="$1"
  raw="${raw#./}"
  if [[ "$raw" = /* ]]; then
    case "$raw" in
      "$ROOT_DIR"/*) printf '%s\n' "${raw#$ROOT_DIR/}" ;;
      *) realpath -m --relative-to="$ROOT_DIR" "$raw" ;;
    esac
    return
  fi
  printf '%s\n' "$raw"
}

to_repo_path() {
  local raw="$1"
  raw="${raw#./}"
  if [[ "$raw" = /* ]]; then
    case "$raw" in
      "$ROOT_DIR"/*) printf '%s\n' "${raw#$ROOT_DIR/}" ;;
      *) realpath -m --relative-to="$ROOT_DIR" "$raw" ;;
    esac
    return
  fi
  printf '%s\n' "$raw"
}

real_source_path() {
  realpath -m --relative-to="$ROOT_DIR" "$1"
}

path_owner() {
  local path="$1"
  case "$path" in
    vendor/agent-canon/*)
      printf '%s\n' "submodule_source"
      return
      ;;
    .github/workflows/agent-coordination.yml|.github/PULL_REQUEST_TEMPLATE/agent_canon.md)
      printf '%s\n' "root_view"
      return
      ;;
  esac
  if [[ -L "$path" ]]; then
    printf '%s\n' "symlink"
    return
  fi
  printf '%s\n' "product_file"
}

missing_reason() {
  local path="$1"
  local has_start=0
  local has_end=0
  if has_manifest_marker "$path" '@dependency-start'; then
    has_start=1
  fi
  if has_manifest_marker "$path" '@dependency-end'; then
    has_end=1
  fi
  if [[ "$has_start" -eq 0 && "$has_end" -eq 0 ]]; then
    printf '%s\n' "missing_start_and_end_markers_in_first_${HEADER_SCAN_LINES}_lines"
  elif [[ "$has_start" -eq 0 ]]; then
    printf '%s\n' "missing_start_marker_in_first_${HEADER_SCAN_LINES}_lines"
  else
    printf '%s\n' "missing_end_marker_in_first_${HEADER_SCAN_LINES}_lines"
  fi
}

print_missing_explanation() {
  local path="$1"
  local shown
  shown="$(display_path "$path")"
  echo "MISSING_DEPENDENCY_EXPLANATION_BEGIN=$shown"
  echo "MISSING_DEPENDENCY_REASON=$shown $(missing_reason "$path")"
  echo "MISSING_DEPENDENCY_PREVIEW_LINES=$shown count=$MISSING_PREVIEW_LINES"
  sed -n "1,${MISSING_PREVIEW_LINES}p" "$path" | nl -ba -w1 -s ':'
  echo "MISSING_DEPENDENCY_EXPLANATION_END=$shown"
}

collect_paths() {
  if [[ -n "$CHANGED_PATH_PACKET" ]]; then
    {
      git ls-files
      printf '%s\n' "${CHANGED_PATHS[@]}"
    } | awk 'NF && !seen[$0]++'
    return
  fi
  if [[ ${#INPUT_PATHS[@]} -gt 0 ]]; then
    printf '%s\n' "${INPUT_PATHS[@]}"
    return
  fi
  if [[ "$CHANGED" -eq 1 ]]; then
    {
      git diff --name-only --diff-filter=ACMRT HEAD -- 2>/dev/null || true
      git ls-files --others --exclude-standard 2>/dev/null || true
    } | awk 'NF'
    return
  fi
  git ls-files
}

missing=0
checked=0
skipped=0
missing_product_file=0
missing_root_view=0
missing_symlink=0
missing_submodule_source=0
missing_other=0
blocking_missing=0
baseline_missing=0

is_changed_path() {
  [[ -n "$CHANGED_PATH_PACKET" && -n "${CHANGED_PATH_SET[$1]+present}" ]]
}

is_selected_surface() {
  local path="$1"
  if [[ ${#INPUT_PATHS[@]} -gt 0 ]]; then
    return 0
  fi
  # A trusted changed-path packet supplies the complete baseline universe;
  # retain unchanged files so missing headers remain baseline evidence.
  if [[ -n "$CHANGED_PATH_PACKET" ]]; then
    return 0
  fi
  if matches_declared_surface "$path"; then
    return 0
  fi
  is_changed_path "$path"
}

while IFS= read -r raw_path; do
  [[ -n "$raw_path" ]] || continue
  path="$(to_repo_path "$raw_path")"
  [[ -f "$path" && ! -L "$path" ]] || { skipped=$((skipped + 1)); continue; }
  is_skip_path "$path" && { skipped=$((skipped + 1)); continue; }
  is_checkable_suffix "$path" || { skipped=$((skipped + 1)); continue; }
  is_selected_surface "$path" || { skipped=$((skipped + 1)); continue; }
  is_binary_file "$path" || { skipped=$((skipped + 1)); continue; }
  checked=$((checked + 1))
  if ! has_manifest_markers "$path"; then
    owner="$(path_owner "$path")"
    case "$owner" in
      product_file) missing_product_file=$((missing_product_file + 1)) ;;
      root_view) missing_root_view=$((missing_root_view + 1)) ;;
      symlink) missing_symlink=$((missing_symlink + 1)) ;;
      submodule_source) missing_submodule_source=$((missing_submodule_source + 1)) ;;
      *) missing_other=$((missing_other + 1)) ;;
    esac
    classification="strict"
    if [[ -n "$CHANGED_PATH_PACKET" ]]; then
      if is_changed_path "$path"; then
        classification="changed"
        blocking_missing=$((blocking_missing + 1))
        CHANGED_MISSING_PATHS+=("$path")
      else
        classification="baseline"
        baseline_missing=$((baseline_missing + 1))
        BASELINE_MISSING_PATHS+=("$path")
      fi
    else
      blocking_missing=$((blocking_missing + 1))
      CHANGED_MISSING_PATHS+=("$path")
    fi
    echo "MISSING_DEPENDENCY_MANIFEST=$(display_path "$path") owner=$owner classification=$classification realpath=$(real_source_path "$path") reason=$(missing_reason "$path")"
    if [[ "$EXPLAIN_MISSING" -eq 1 ]]; then
      print_missing_explanation "$path"
    fi
    missing=$((missing + 1))
  fi
done < <(collect_paths)

echo "DEPENDENCY_HEADER_SCAN_CHECKED=$checked"
echo "DEPENDENCY_HEADER_SCAN_SKIPPED=$skipped"
echo "DEPENDENCY_HEADER_SCAN_MISSING=$missing"
echo "DEPENDENCY_HEADER_SCAN_MISSING_BY_OWNER product_file=$missing_product_file root_view=$missing_root_view symlink=$missing_symlink submodule_source=$missing_submodule_source other=$missing_other"
echo "DEPENDENCY_HEADER_SCAN_BLOCKING=$blocking_missing"
echo "DEPENDENCY_HEADER_SCAN_BASELINE=$baseline_missing"
for path in "${CHANGED_MISSING_PATHS[@]}"; do
  echo "DEPENDENCY_HEADER_SCAN_CHANGED_MISSING_PATH=$(display_path "$path")"
done
for path in "${BASELINE_MISSING_PATHS[@]}"; do
  echo "DEPENDENCY_HEADER_SCAN_BASELINE_MISSING_PATH=$(display_path "$path")"
done

if [[ "$blocking_missing" -gt 0 && "$FAIL_MISSING" -eq 1 ]]; then
  echo "DEPENDENCY_HEADER_SCAN=fail"
  exit 1
fi

echo "DEPENDENCY_HEADER_SCAN=pass"
