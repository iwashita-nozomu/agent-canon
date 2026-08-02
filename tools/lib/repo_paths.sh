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
