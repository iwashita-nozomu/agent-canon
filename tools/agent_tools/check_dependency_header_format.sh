#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Validates dependency manifest syntax, contract kind metadata, and responsibility metadata.
# upstream design ../../documents/dependency-manifest-design.md dependency manifest DSL design
# upstream design ../../documents/dependency-contract-kinds.toml registered dependency header contract kinds
# upstream implementation ./scan_dependency_headers.sh finds files with manifests
# downstream implementation ./check_dependency_graph.sh consumes validated manifest lines
# @dependency-end
set -euo pipefail

ROOT_DIR="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || pwd)"
REQUIRE_HEADER=0
CHANGED=0
ALLOW_FRONTMATTER=0
HEADER_SCAN_LINES="${DEPENDENCY_HEADER_SCAN_LINES:-80}"
CONTRACT_KIND_REGISTRY="${DEPENDENCY_CONTRACT_KIND_REGISTRY:-}"
declare -a INPUT_PATHS=()

usage() {
  cat <<'EOF'
Usage:
  check_dependency_header_format.sh [--root DIR] [--changed] [--require-header] [--allow-frontmatter] [paths...]

Validates @dependency-start / @dependency-end manifest syntax.
Files without a manifest are skipped unless --require-header is set.
Each manifest must include one registered `contract <kind>` line.
--allow-frontmatter is accepted for policy-explicit callers; frontmatter is allowed by default.
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
    --require-header)
      REQUIRE_HEADER=1
      shift
      ;;
    --allow-frontmatter)
      ALLOW_FRONTMATTER=1
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

contract_kind_registry_path() {
  if [[ -n "$CONTRACT_KIND_REGISTRY" ]]; then
    printf '%s\n' "$CONTRACT_KIND_REGISTRY"
    return
  fi
  if [[ -f "$ROOT_DIR/documents/dependency-contract-kinds.toml" ]]; then
    printf '%s\n' "$ROOT_DIR/documents/dependency-contract-kinds.toml"
    return
  fi
  if [[ -f "$ROOT_DIR/vendor/agent-canon/documents/dependency-contract-kinds.toml" ]]; then
    printf '%s\n' "$ROOT_DIR/vendor/agent-canon/documents/dependency-contract-kinds.toml"
    return
  fi
  local script_path script_dir
  script_path="$(readlink -f "${BASH_SOURCE[0]}")"
  script_dir="$(cd "$(dirname "$script_path")" && pwd)"
  printf '%s\n' "$(realpath -m "$script_dir/../../documents/dependency-contract-kinds.toml")"
}

load_contract_kinds() {
  local registry="$1"
  [[ -f "$registry" ]] || return 1
  awk '
    /^[[:space:]]*allowed_kinds[[:space:]]*=/ { in_allowed = 1; next }
    in_allowed && /^[[:space:]]*\]/ { exit }
    in_allowed {
      line = $0
      while (match(line, /"[a-z0-9][a-z0-9-]*"/)) {
        value = substr(line, RSTART + 1, RLENGTH - 2)
        print value
        line = substr(line, RSTART + RLENGTH)
      }
    }
  ' "$registry"
}

CONTRACT_KIND_REGISTRY_PATH="$(contract_kind_registry_path)"
mapfile -t ALLOWED_CONTRACT_KINDS < <(load_contract_kinds "$CONTRACT_KIND_REGISTRY_PATH" || true)

contract_kind_allowed() {
  local candidate="$1"
  local allowed
  for allowed in "${ALLOWED_CONTRACT_KINDS[@]}"; do
    [[ "$candidate" == "$allowed" ]] && return 0
  done
  return 1
}

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
    .git/*|.pytest_cache/*|.ruff_cache/*|reports/*|LICENSE|LICENSE.*|NOTICE|NOTICE.*|COPYING|COPYING.*|vendor/agent-canon/LICENSE|vendor/agent-canon/LICENSE.*|vendor/agent-canon/NOTICE|vendor/agent-canon/NOTICE.*|vendor/agent-canon/COPYING|vendor/agent-canon/COPYING.*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

collect_paths() {
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

strip_manifest_line() {
  local line="$1"
  line="${line%$'\r'}"
  line="${line#"${line%%[![:space:]]*}"}"
  case "$line" in
    "# "*) line="${line#\# }" ;;
    "#"*) line="${line#\#}" ;;
  esac
  case "$line" in
    "// "*) line="${line#// }" ;;
    "//"*) line="${line#//}" ;;
  esac
  case "$line" in
    "* "*) line="${line#\* }" ;;
    "*"*) line="${line#\*}" ;;
  esac
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  line="${line%,}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  if [[ "$line" == \"*\" ]]; then
    line="${line#\"}"
    line="${line%\"}"
  fi
  printf '%s\n' "$line"
}

normalize_path() {
  local source_file="$1"
  local rel_path="$2"
  local source_context
  local source_dir
  source_context="$(source_context_file "$source_file")"
  source_dir="$(dirname "$source_context")"
  realpath -m --relative-to="$ROOT_DIR" "$source_dir/$rel_path"
}

source_context_file() {
  local source_file="$1"
  case "$source_file" in
    .github/workflows/agent-coordination.yml|.github/PULL_REQUEST_TEMPLATE/agent_canon.md)
      if [[ -f "vendor/agent-canon/$source_file" ]]; then
        printf 'vendor/agent-canon/%s\n' "$source_file"
        return
      fi
      ;;
    .github/scripts/checkout_agent_canon_submodule.sh)
      if [[ -f "vendor/agent-canon/tools/ci/checkout_agent_canon_submodule.sh" ]]; then
        printf '%s\n' "vendor/agent-canon/tools/ci/checkout_agent_canon_submodule.sh"
        return
      fi
      ;;
  esac
  printf '%s\n' "$source_file"
}

check_file() {
  local file="$1"
  local start_count end_count start_line end_line line_no line stripped
  local direction kind rel_path reason target
  local contract_count contract_keyword contract_kind contract_extra
  local coverage_keyword coverage_id coverage_requires coverage_terms
  local responsibility_count responsibility_text
  [[ -f "$file" && ! -L "$file" ]] || return 0

  start_count=0
  end_count=0
  start_line=0
  end_line=0
  line_no=0
  while IFS= read -r line && [[ "$line_no" -lt "$HEADER_SCAN_LINES" ]]; do
    line_no=$((line_no + 1))
    stripped="$(strip_manifest_line "$line")"
    if [[ "$stripped" == "@dependency-start" ]]; then
      if [[ "$start_line" -ne 0 && "$end_line" -eq 0 ]]; then
        echo "$file: duplicate @dependency-start before @dependency-end"
        return 1
      fi
      [[ "$end_line" -ne 0 ]] && break
      start_count=$((start_count + 1))
      start_line="$line_no"
    elif [[ "$stripped" == "@dependency-end" ]]; then
      [[ "$start_line" -eq 0 ]] && {
        echo "$file: @dependency-end appears before @dependency-start"
        return 1
      }
      end_count=$((end_count + 1))
      end_line="$line_no"
      break
    fi
  done < "$file"

  if [[ "$start_count" -eq 0 && "$end_count" -eq 0 ]]; then
    is_checkable_suffix "$file" || return 0
    if [[ "$REQUIRE_HEADER" -eq 1 ]]; then
      echo "$file: missing dependency manifest markers"
      return 1
    fi
    return 0
  fi
  if [[ "$start_count" -ne 1 || "$end_count" -ne 1 ]]; then
    echo "$file: expected one top dependency manifest block"
    return 1
  fi
  if [[ "$start_line" -ge "$end_line" ]]; then
    echo "$file: @dependency-start must appear before @dependency-end"
    return 1
  fi

  line_no=0
  responsibility_count=0
  contract_count=0
  while IFS= read -r line; do
    line_no=$((line_no + 1))
    [[ "$line_no" -gt "$start_line" && "$line_no" -lt "$end_line" ]] || continue
    stripped="$(strip_manifest_line "$line")"
    case "$stripped" in
      ""|"/*"|"*/"|"<!--"|"-->"|'"""'|"'''" )
        continue
        ;;
    esac
    if [[ "$stripped" == responsibility[[:space:]]* ]]; then
      responsibility_text="${stripped#responsibility}"
      responsibility_text="${responsibility_text#"${responsibility_text%%[![:space:]]*}"}"
      if [[ -z "$responsibility_text" ]]; then
        echo "$file:$line_no: responsibility line must include a role statement"
        return 1
      fi
      responsibility_count=$((responsibility_count + 1))
      continue
    fi
    if [[ "$stripped" == contract[[:space:]]* ]]; then
      read -r contract_keyword contract_kind contract_extra <<< "$stripped"
      if [[ -z "${contract_kind:-}" || -n "${contract_extra:-}" ]]; then
        echo "$file:$line_no: contract line must be: contract <registered-kind>; fix: choose one allowed_kinds entry from $CONTRACT_KIND_REGISTRY_PATH"
        return 1
      fi
      if [[ ! "$contract_kind" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
        echo "$file:$line_no: invalid contract kind token '$contract_kind'; fix: use lowercase kebab-case from $CONTRACT_KIND_REGISTRY_PATH"
        return 1
      fi
      if ! contract_kind_allowed "$contract_kind"; then
        echo "$file:$line_no: unregistered contract kind '$contract_kind'; fix: use an existing allowed_kinds entry from $CONTRACT_KIND_REGISTRY_PATH or update the registry with review"
        return 1
      fi
      contract_count=$((contract_count + 1))
      continue
    fi
    if [[ "$stripped" == coverage[[:space:]]* ]]; then
      read -r coverage_keyword coverage_id coverage_requires coverage_terms <<< "$stripped"
      if [[ -z "${coverage_id:-}" || -z "${coverage_requires:-}" || -z "${coverage_terms:-}" ]]; then
        echo "$file:$line_no: coverage line must be: coverage id requires term group"
        return 1
      fi
      if [[ "$coverage_requires" != "requires" ]]; then
        echo "$file:$line_no: coverage line must use 'requires'"
        return 1
      fi
      continue
    fi
    read -r direction kind rel_path reason <<< "$stripped"
    if [[ -z "${direction:-}" || -z "${kind:-}" || -z "${rel_path:-}" || -z "${reason:-}" ]]; then
      echo "$file:$line_no: dependency line must be: direction kind relative-path reason"
      return 1
    fi
    if [[ "$direction" != "upstream" && "$direction" != "downstream" ]]; then
      echo "$file:$line_no: invalid direction '$direction'"
      return 1
    fi
    if [[ "$kind" != "design" && "$kind" != "implementation" && "$kind" != "environment" ]]; then
      echo "$file:$line_no: invalid kind '$kind'"
      return 1
    fi
    if [[ "$rel_path" = /* || "$rel_path" == *"://"* ]]; then
      echo "$file:$line_no: dependency path must be relative: $rel_path"
      return 1
    fi
    target="$(normalize_path "$file" "$rel_path")"
    if [[ ! -e "$target" ]]; then
      echo "$file:$line_no: dependency target does not exist: $rel_path"
      return 1
    fi
  done < "$file"

  if [[ "$responsibility_count" -ne 1 ]]; then
    echo "$file: dependency manifest must contain exactly one responsibility line"
    return 1
  fi
  if [[ "$contract_count" -gt 1 ]]; then
    echo "$file: dependency manifest must contain exactly one contract line; fix: keep one 'contract <registered-kind>' line immediately after @dependency-start"
    return 1
  fi
  if [[ "$contract_count" -ne 1 ]]; then
    echo "$file: dependency manifest must contain exactly one contract line; fix: add 'contract <registered-kind>' after @dependency-start and choose the kind from $CONTRACT_KIND_REGISTRY_PATH"
    return 1
  fi
}

if [[ "${#ALLOWED_CONTRACT_KINDS[@]}" -eq 0 ]]; then
  echo "missing dependency contract kind registry: $CONTRACT_KIND_REGISTRY_PATH; fix: restore documents/dependency-contract-kinds.toml or set DEPENDENCY_CONTRACT_KIND_REGISTRY to the canonical registry"
  echo "DEPENDENCY_HEADER_FORMAT=fail"
  exit 1
fi

failures=0
while IFS= read -r raw_path; do
  [[ -n "$raw_path" ]] || continue
  path="${raw_path#./}"
  if [[ "$path" = /* ]]; then
    path="$(realpath -m --relative-to="$ROOT_DIR" "$path")"
  fi
  is_skip_path "$path" && continue
  if ! check_file "$path"; then
    failures=$((failures + 1))
  fi
done < <(collect_paths)

if [[ "$failures" -gt 0 ]]; then
  echo "DEPENDENCY_HEADER_FORMAT=fail"
  exit 1
fi

echo "DEPENDENCY_HEADER_FORMAT=pass"
