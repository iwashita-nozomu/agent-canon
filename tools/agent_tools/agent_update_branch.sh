#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Validates and pushes Template/AgentCanon agent update branches.
# upstream design ../../agents/workflows/agent-update-branch-workflow.md defines branch lanes
# downstream design ../../.agents/skills/agent-update-branch/SKILL.md documents invocation
# @dependency-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
SUPERPROJECT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-superproject-working-tree 2>/dev/null || true)"
if [ -n "$SUPERPROJECT_DIR" ]; then
  ROOT_DIR="$SUPERPROJECT_DIR"
else
  ROOT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
fi
BASE_REF="${AGENT_UPDATE_BASE_REF:-origin/main}"

usage() {
  cat <<'EOF'
Usage:
  bash tools/agent_tools/agent_update_branch.sh validate <memory-eval|canon-pin|integration> [base-ref]
  bash tools/agent_tools/agent_update_branch.sh push <memory-eval|canon-pin|integration> <branch> [base-ref]

The command validates that an agent update branch only changes the allowed lane
surface, then pushes the current HEAD to the requested branch.
EOF
}

die() {
  echo "agent_update_branch.sh: $*" >&2
  exit 1
}

changed_paths() {
  local base_ref="$1"
  git -C "$ROOT_DIR" diff --name-only "$base_ref"...HEAD
}

path_allowed() {
  local lane="$1"
  local path="$2"
  case "$lane" in
    memory-eval)
      [[ "$path" == memory/* ]] && return 0
      [[ "$path" == evidence/agent-evals/* ]] && return 0
      [[ "$path" == .agents/skills/*/SKILL.md ]] && return 0
      [[ "$path" == reports/agents/*/agent_evaluation.md ]] && return 0
      [[ "$path" == reports/agents/*/workflow_monitoring.md ]] && return 0
      return 1
      ;;
    canon-pin)
      [[ "$path" == .gitmodules ]] && return 0
      [[ "$path" == .agent-canon/* ]] && return 0
      [[ "$path" == vendor/agent-canon ]] && return 0
      [[ "$path" == AGENTS.md ]] && return 0
      [[ "$path" == .agents || "$path" == agents ]] && return 0
      [[ "$path" == .codex/* || "$path" == .github/* ]] && return 0
      [[ "$path" == documents/* || "$path" == memory/* || "$path" == notes/* ]] && return 0
      [[ "$path" == mcp || "$path" == tools || "$path" == tests/agent_tools/* || "$path" == tests/tools/* ]] && return 0
      return 1
      ;;
    integration)
      return 0
      ;;
    *)
      die "unknown lane: $lane"
      ;;
  esac
}

cmd_validate() {
  local lane="$1"
  local base_ref="${2:-$BASE_REF}"
  local path=""
  local failed=0

  git -C "$ROOT_DIR" rev-parse --verify "$base_ref" >/dev/null || die "base ref not found: $base_ref"
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    if ! path_allowed "$lane" "$path"; then
      echo "AGENT_UPDATE_BRANCH_DISALLOWED=$path"
      failed=1
    fi
  done < <(changed_paths "$base_ref")

  if [ "$failed" -ne 0 ]; then
    echo "AGENT_UPDATE_BRANCH_VALIDATE=fail"
    exit 1
  fi
  echo "AGENT_UPDATE_BRANCH_VALIDATE=pass"
  echo "AGENT_UPDATE_BRANCH_LANE=$lane"
  echo "AGENT_UPDATE_BRANCH_BASE=$base_ref"
}

cmd_push() {
  local lane="$1"
  local branch="$2"
  local base_ref="${3:-$BASE_REF}"

  [[ "$branch" == agent-updates/* ]] || die "branch must start with agent-updates/: $branch"
  cmd_validate "$lane" "$base_ref"
  git -C "$ROOT_DIR" push origin "HEAD:refs/heads/$branch"
  echo "AGENT_UPDATE_BRANCH_PUSHED=$branch"
}

main() {
  local command="${1:-}"
  case "$command" in
    validate)
      [ "${2:-}" ] || die "validate requires <lane>"
      cmd_validate "$2" "${3:-$BASE_REF}"
      ;;
    push)
      [ "${2:-}" ] || die "push requires <lane>"
      [ "${3:-}" ] || die "push requires <branch>"
      cmd_push "$2" "$3" "${4:-$BASE_REF}"
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      die "unknown command: $command"
      ;;
  esac
}

main "$@"
