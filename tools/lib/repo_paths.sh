#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Resolves the repository root and AgentCanon tool view for standalone and parent-projected runs.
# downstream implementation ../ci/run_all_checks.sh uses the resolved tool view for repository checks.
# downstream implementation ../ci/check_fresh_clone.sh uses the resolved root for temporary clone checks.
# downstream implementation ../update_agent_canon.sh uses the resolved root and tool view for pin updates.
# @dependency-end

agent_canon_repo_root() {
  local script_path="${1:-${BASH_SOURCE[1]:-$0}}"
  local script_dir=""
  local source_root=""
  local superproject_root=""

  script_dir="$(cd "$(dirname "$script_path")" && pwd -P)"
  if [ "$(basename "$script_dir")" = "tools" ]; then
    source_root="$(cd "$script_dir/.." && pwd -P)"
  else
    source_root="$(cd "$script_dir/../.." && pwd -P)"
  fi
  superproject_root="$(git -C "$source_root" rev-parse --show-superproject-working-tree 2>/dev/null || true)"
  if [ -n "$superproject_root" ]; then
    printf '%s\n' "$superproject_root"
    return 0
  fi
  git -C "$source_root" rev-parse --show-toplevel
}

agent_canon_tools_root() {
  local repository_root="$1"
  if [ -d "$repository_root/tools/agent_tools" ]; then
    printf '%s\n' "$repository_root/tools"
  else
    printf '%s\n' "$repository_root/tools/agent-canon"
  fi
}

agent_canon_source_tools_root() {
  local repository_root="$1"
  local source_prefix="${2:-vendor/agent-canon}"

  if git -C "$repository_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    local declared_mode=""
    declared_mode="$(
      git -C "$repository_root" ls-tree -d --full-tree HEAD "$source_prefix" 2>/dev/null \
        | awk '{print $1}'
    )"
    if [ "$declared_mode" = "160000" ]; then
      local submodule_path="${repository_root}/${source_prefix}"
      if [ ! -f "${submodule_path}/.git" ] && [ ! -d "${submodule_path}/.git" ]; then
        echo "AGENT_CANON_SOURCE_TOOLS_ROOT_BLOCKER=submodule_vendor_agent_canon_not_checked_out"
        echo "AGENT_CANON_SOURCE_TOOLS_ROOT_MODE=160000"
        echo "AGENT_CANON_SOURCE_TOOLS_ROOT_PREFIX=${source_prefix}"
        return 1
      fi
    fi
  fi

  if [ -d "$repository_root/$source_prefix/tools" ] \
    && [ -f "$repository_root/$source_prefix/tools/sync_agent_canon.sh" ]; then
    printf '%s\n' "$repository_root/$source_prefix/tools"
    return 0
  fi
  if [ -d "$repository_root/tools/agent-canon" ] \
    && [ -f "$repository_root/tools/agent-canon/sync_agent_canon.sh" ]; then
    printf '%s\n' "$repository_root/tools/agent-canon"
    return 0
  fi
  if [ -d "$repository_root/tools" ] && [ -f "$repository_root/tools/sync_agent_canon.sh" ]; then
    printf '%s\n' "$repository_root/tools"
    return 0
  fi
  return 1
}

# Resolve the tool tree that owns dependency-analysis implementation/runtime.
#
# The repository under review is data only: its tools/ and vendor/ trees must
# never become the analyzer merely because --root points at that repository.
# Explicit roots are capability-bearing paths and therefore require a physical
# directory beneath the authenticated parent.  The invocation-source default
# is intentionally read-only and may live outside that parent (for example a
# canonical tool checkout used to inspect a fixture repository).
agent_canon_analyzer_tools_root() {
  local invocation_script="${1:-}"
  local explicit_root="${2:-}"
  local authenticated_parent="${3:-}"
  local allow_physical_default="${4:-0}"
  local required_entry=""
  local analyzer_root=""
  local physical_invocation=""
  local physical_source_root=""
  local lexical_root=""
  local physical_parent=""
  local explicit_leaf=""
  local requested_entries=()

  if [[ -z "$invocation_script" ]]; then
    echo "ANALYZER_TOOLS_ROOT_ERROR=invocation_script_missing" >&2
    return 2
  fi

  if [[ -z "$explicit_root" ]]; then
    explicit_root="${AGENT_CANON_ANALYZER_TOOLS_ROOT:-}"
  fi

  if [[ -n "$explicit_root" ]]; then
    explicit_leaf="${explicit_root%/}"
    lexical_root="$(realpath -m "$explicit_root" 2>/dev/null || true)"
    if [[ -z "$lexical_root" || ! -d "$lexical_root" \
      || -L "$explicit_root" || ( -n "$explicit_leaf" && -L "$explicit_leaf" ) ]]; then
      echo "ANALYZER_TOOLS_ROOT_ERROR=explicit_root_not_regular_directory" >&2
      return 2
    fi
    analyzer_root="$(realpath -e "$lexical_root" 2>/dev/null || true)"
    if [[ -z "$analyzer_root" || "$analyzer_root" != "$lexical_root" ]]; then
      echo "ANALYZER_TOOLS_ROOT_ERROR=explicit_root_symlink_escape" >&2
      return 2
    fi
    physical_invocation="$(realpath -e "$invocation_script" 2>/dev/null || true)"
    if [[ -n "$physical_invocation" ]]; then
      physical_source_root="$(cd "$(dirname "$physical_invocation")/.." && pwd -P)"
    fi
    if [[ "$allow_physical_default" == "1" && "$analyzer_root" == "$physical_source_root" ]]; then
      :
    elif [[ -z "$authenticated_parent" ]]; then
      echo "ANALYZER_TOOLS_ROOT_ERROR=authenticated_parent_missing" >&2
      return 2
    else
      physical_parent="$(realpath -e "$authenticated_parent" 2>/dev/null || true)"
      if [[ -z "$physical_parent" || ! -d "$physical_parent" ]]; then
        echo "ANALYZER_TOOLS_ROOT_ERROR=authenticated_parent_missing" >&2
        return 2
      fi
      case "$analyzer_root" in
        "$physical_parent"|"$physical_parent"/*) ;;
        *)
          echo "ANALYZER_TOOLS_ROOT_ERROR=explicit_root_outside_authenticated_parent" >&2
          return 2
          ;;
      esac
    fi
  else
    physical_invocation="$(realpath -e "$invocation_script" 2>/dev/null || true)"
    if [[ -z "$physical_invocation" || ! -f "$physical_invocation" ]]; then
      echo "ANALYZER_TOOLS_ROOT_ERROR=invocation_script_missing" >&2
      return 2
    fi
    analyzer_root="$(cd "$(dirname "$physical_invocation")/.." && pwd -P)"
  fi

  if [[ "$#" -gt 4 ]]; then
    requested_entries=("${@:5}")
  else
    requested_entries=(
      "bin/agent-canon"
    )
  fi

  for required_entry in "${requested_entries[@]}"; do
    if [[ ! -f "$analyzer_root/$required_entry" ]]; then
      echo "ANALYZER_TOOLS_ROOT_ERROR=required_entrypoint_missing path=$required_entry" >&2
      return 2
    fi
    if [[ "$required_entry" == "bin/agent-canon" && ! -x "$analyzer_root/$required_entry" ]]; then
      echo "ANALYZER_TOOLS_ROOT_ERROR=required_entrypoint_not_executable path=$required_entry" >&2
      return 2
    fi
  done

  printf '%s\n' "$analyzer_root"
}
