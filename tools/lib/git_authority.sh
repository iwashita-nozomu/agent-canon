#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Provides Git authority predicate helpers for AgentCanon tool scripts.
# downstream implementation ../sync_agent_canon.sh preserves existing user-facing diagnostics.
# downstream implementation ../update_agent_canon.sh preserves existing user-facing diagnostics.
# @dependency-end

# These predicates return status codes only; they must not emit output or exit.
# Callers that own public CLI behavior should emit diagnostics and exit.

git_authority_check_protected_git_authority() {
  local mode="$1"
  local branch_authority="${AGENT_CANON_BRANCH_WORKTREE_AUTHORITY:-}"
  local branch_reason="${AGENT_CANON_BRANCH_WORKTREE_REASON:-}"
  local destructive_authority="${AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY:-}"
  local destructive_reason="${AGENT_CANON_DESTRUCTIVE_GIT_REASON:-}"

  if { [ "$branch_authority" = "user_request" ] || [ "$branch_authority" = "agent_canon_workflow" ]; } \
    && [ -n "$branch_reason" ] \
    && [ "$destructive_authority" = "explicit_user_approval" ] \
    && [ -n "$destructive_reason" ]; then
    return 0
  fi

  return 1
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
