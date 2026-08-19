#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Resolves the repository root and AgentCanon source tools for standalone and vendored runs.
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
  if [ -d "$repository_root/vendor/agent-canon/tools/agent_tools" ]; then
    printf '%s\n' "$repository_root/vendor/agent-canon/tools"
  elif [ -d "$repository_root/tools/agent_tools" ]; then
    printf '%s\n' "$repository_root/tools"
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
  if [ -d "$repository_root/tools" ] && [ -f "$repository_root/tools/sync_agent_canon.sh" ]; then
    printf '%s\n' "$repository_root/tools"
    return 0
  fi
  return 1
}
