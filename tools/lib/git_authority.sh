#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides Git authority predicate helpers for AgentCanon tool scripts.
# downstream implementation ../agent_tools/repository_topic_clone.py preserves existing user-facing diagnostics.
# @dependency-end

# These predicates return status codes only; they must not emit output or exit.
# Callers that own public CLI behavior should emit diagnostics and exit.

git_authority_requires_creation() {
  case "${1:-}" in
    branch-create|branch-copy|create|submodule-add|worktree-add|worktree-create|force-add|force-create|ref-overwrite)
      return 0
      ;;
  esac
  return 1
}

git_authority_requires_destructive() {
  case "${1:-}" in
    branch-create|branch-copy|create|submodule-add|worktree-add|worktree-create)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

git_authority_check_creation_authority() {
  local branch_authority="${AGENT_CANON_BRANCH_WORKTREE_AUTHORITY:-}"
  local branch_reason="${AGENT_CANON_BRANCH_WORKTREE_REASON:-}"

  if { [ "$branch_authority" = "user_request" ] || [ "$branch_authority" = "agent_canon_workflow" ]; } \
    && [ -n "$branch_reason" ]; then
    return 0
  fi
  return 1
}

git_authority_check_destructive_authority() {
  local destructive_authority="${AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY:-}"
  local destructive_reason="${AGENT_CANON_DESTRUCTIVE_GIT_REASON:-}"

  if [ "$destructive_authority" = "explicit_user_approval" ] \
    && [ -n "$destructive_reason" ]; then
    return 0
  fi
  return 1
}

git_authority_check_protected_git_authority() {
  local mode="$1"
  if git_authority_requires_creation "$mode" \
    && ! git_authority_check_creation_authority; then
    return 1
  fi
  if git_authority_requires_destructive "$mode" \
    && ! git_authority_check_destructive_authority; then
    return 1
  fi
  return 0
}

git_authority_emit_failure() {
  local mode="$1"
  local next_action_default="$2"
  local next_action_creation="$3"
  local detail_prefix="$4"
  local requires_creation=0
  local requires_destructive=0
  local next_action="$next_action_default"
  local detail="${detail_prefix} explicit destructive approval authority"

  if git_authority_requires_creation "$mode"; then
    requires_creation=1
  fi
  if git_authority_requires_destructive "$mode"; then
    requires_destructive=1
  fi
  if [ "$requires_creation" -eq 1 ]; then
    echo "BRANCH_WORKTREE_CREATION_GUARD=block"
  fi
  if [ "$requires_destructive" -eq 1 ]; then
    echo "DESTRUCTIVE_GIT_GUARD=block"
  fi
  if [ "$requires_creation" -eq 1 ] && [ "$requires_destructive" -eq 0 ]; then
    next_action="$next_action_creation"
    detail="${detail_prefix} branch/worktree creation authority"
  elif [ "$requires_creation" -eq 1 ]; then
    detail="${detail_prefix} branch/worktree and explicit destructive approval authority"
  fi
  echo "AGENT_CANON_PROTECTED_GIT_SUBCOMMAND=$mode"
  echo "NEXT_ACTION=$next_action"
  GIT_AUTHORITY_FAILURE_DETAIL="$detail"
}

git_authority_check_commit_request_evidence() {
  local evidence="${AGENT_CANON_COMMIT_REQUEST_EVIDENCE:-}"
  if [[ "$evidence" =~ ^evidence:[0-9a-f]{64}$ ]]; then
    return 0
  fi
  return 1
}

git_authority_check_commit_provenance() {
  local mode="$1"
  git_authority_check_protected_git_authority "$mode" || return 1
  git_authority_check_commit_request_evidence || return 2
  return 0
}
