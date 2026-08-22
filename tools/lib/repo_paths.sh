#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Resolves the standalone AgentCanon repository root and tool view.
# downstream implementation ../ci/run_all_checks.sh uses the resolved tool view for repository checks.
# downstream implementation ../ci/run_standalone_static_gate_unit.sh uses the resolved tool view.
# @dependency-end

agent_canon_repo_root() {
  local script_path="${1:-${BASH_SOURCE[1]:-$0}}"
  local script_dir=""
  local source_root=""

  script_dir="$(cd "$(dirname "$script_path")" && pwd -P)"
  if [ "$(basename "$script_dir")" = "tools" ]; then
    source_root="$(cd "$script_dir/.." && pwd -P)"
  else
    source_root="$(cd "$script_dir/../.." && pwd -P)"
  fi
  git -C "$source_root" rev-parse --show-toplevel
}

agent_canon_tools_root() {
  local repository_root="$1"
  printf '%s\n' "$repository_root/tools"
}

agent_canon_source_tools_root() {
  local repository_root="$1"
  if [ -d "$repository_root/tools" ] && [ -f "$repository_root/tools/bin/agent-canon" ]; then
    printf '%s\n' "$repository_root/tools"
    return 0
  fi
  return 1
}
