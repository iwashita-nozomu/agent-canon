#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks out the AgentCanon submodule without persisting repository credentials across workflow steps.
# upstream design ../../documents/agent-canon/agent-canon-github-remote.md defines private submodule auth policy.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines GitHub runtime behavior.
# upstream implementation ../../tools/agent_tools/parent_root_side_effects.py owns temporary credential material and exact cleanup.
# downstream implementation ../../tools/ci/check_github_workflows.py enforces workflow usage.
# downstream implementation ../../tests/tools/test_checkout_agent_canon_submodule.py verifies process-local auth and credential cleanup.
# @dependency-end

set -euo pipefail

submodule_path="${AGENT_CANON_SUBMODULE_PATH:-vendor/agent-canon}"
token="${AGENT_CANON_REPO_TOKEN:-}"
ssh_key="${AGENT_CANON_REPO_SSH_KEY:-}"
unset AGENT_CANON_REPO_TOKEN AGENT_CANON_REPO_SSH_KEY
ssh_key_dir=""
parent_root="$(git rev-parse --show-toplevel)"
boundary_script="${parent_root}/tools/agent_tools/parent_root_side_effects.py"
if [ ! -f "$boundary_script" ] && [ -f "${parent_root}/vendor/agent-canon/tools/agent_tools/parent_root_side_effects.py" ]; then
  boundary_script="${parent_root}/vendor/agent-canon/tools/agent_tools/parent_root_side_effects.py"
fi
if [ ! -f "$boundary_script" ]; then
  echo "AGENT_CANON_SUBMODULE=missing_boundary path=${boundary_script}" >&2
  exit 2
fi
cd "$parent_root"

# Credentials are never written to GITHUB_ENV, and no global URL rewrite is
# persisted.

if [ ! -f ".gitmodules" ]; then
  echo "AGENT_CANON_SUBMODULE=absent reason=no_gitmodules"
  exit 0
fi

submodule_url="$(git config -f .gitmodules --get "submodule.${submodule_path}.url" || true)"
if [ -z "$submodule_url" ]; then
  echo "AGENT_CANON_SUBMODULE=absent reason=no_agent_canon_entry path=${submodule_path}"
  exit 0
fi

cleanup_ssh_key() {
  local status=$?
  local cleanup_status=0
  trap - EXIT
  if [ -n "$ssh_key_dir" ]; then
    python3 "$boundary_script" remove-tree \
      --root "$parent_root" \
      --candidate "$ssh_key_dir" \
      --purpose agent-canon-submodule-auth-cleanup >/dev/null || cleanup_status=$?
  fi
  if [ "$status" -eq 0 ] && [ "$cleanup_status" -ne 0 ]; then
    status=$cleanup_status
  fi
  exit "$status"
}

trap cleanup_ssh_key EXIT

if git -c "safe.directory=${parent_root}/${submodule_path}" -C "$submodule_path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [ -n "$(git -c "safe.directory=${parent_root}/${submodule_path}" -C "$submodule_path" status --short --untracked-files=all)" ]; then
    cat >&2 <<EOF
AGENT_CANON_SUBMODULE=dirty
Refusing to update dirty submodule '${submodule_path}'.
Commit AgentCanon-owned artifacts first; stash or clean only explicitly disposable local scratch before running this checkout helper locally.
EOF
    exit 87
  fi
fi

prepare_ssh_key() {
  [ -n "$ssh_key" ] || return 0
  [ -z "$token" ] || return 0

  ssh_key_dir="$(
    python3 "$boundary_script" temp-dir \
      --root "$parent_root" \
      --candidate "$parent_root/.agent-canon/tmp" \
      --prefix agent-canon-ssh. \
      --purpose agent-canon-submodule-auth
  )"
  printf '%s\n' "$ssh_key" | tr -d '\r' | python3 "$boundary_script" write \
    --root "$parent_root" \
    --candidate "${ssh_key_dir}/key" \
    --purpose agent-canon-submodule-ssh-key >/dev/null
  python3 "$boundary_script" capture-subprocess \
    --root "$parent_root" \
    --candidate "${ssh_key_dir}/known_hosts" \
    --purpose agent-canon-submodule-known-hosts \
    -- ssh-keyscan github.com >/dev/null
  export GIT_SSH_COMMAND="ssh -i ${ssh_key_dir}/key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${ssh_key_dir}/known_hosts"
}

git_auth() {
  local safe_directory_args=(
    -c "safe.directory=${parent_root}"
    -c "safe.directory=${parent_root}/${submodule_path}"
  )
  if [ -n "$token" ]; then
    git \
      "${safe_directory_args[@]}" \
      -c "url.https://x-access-token:${token}@github.com/.insteadOf=https://github.com/" \
      -c "url.https://x-access-token:${token}@github.com/.insteadOf=git@github.com:" \
      "$@"
    return
  fi
  if [ -n "$ssh_key" ]; then
    git \
      "${safe_directory_args[@]}" \
      -c "url.git@github.com:.insteadOf=https://github.com/" \
      "$@"
    return
  fi
  git "${safe_directory_args[@]}" "$@"
}

export GIT_TERMINAL_PROMPT=0

if git ls-remote "$submodule_url" HEAD >/dev/null 2>&1; then
  token=""
  ssh_key=""
  echo "AGENT_CANON_SUBMODULE_AUTH=anonymous"
else
  prepare_ssh_key
fi

if ! git_auth ls-remote "$submodule_url" HEAD >/dev/null 2>&1; then
  if [ -z "$token" ] && [ -z "$ssh_key" ]; then
    cat >&2 <<EOF
AGENT_CANON_SUBMODULE_AUTH=missing
AgentCanon submodule '${submodule_url}' is not readable anonymously.
For private AgentCanon repositories, add a repository secret named AGENT_CANON_REPO_TOKEN
with read-only Contents access to the AgentCanon repository, then rerun the workflow.
Alternatively, configure AGENT_CANON_REPO_SSH_KEY as a read-only deploy key
for the AgentCanon repository.
If this is a fork-like or untrusted PR context, repository secrets may be intentionally
unavailable; request a trusted maintainer rerun after reviewing the workflow diff.
Do not remove the submodule or change implementation code to hide this authentication failure.
EOF
  elif [ -n "$ssh_key" ] && [ -z "$token" ]; then
    cat >&2 <<EOF
AGENT_CANON_SUBMODULE_AUTH=ssh_denied
AGENT_CANON_REPO_SSH_KEY is set, but it cannot read '${submodule_url}'.
Check that the matching public key is installed as a read-only deploy key on the AgentCanon repository.
EOF
  else
    cat >&2 <<EOF
AGENT_CANON_SUBMODULE_AUTH=denied
AGENT_CANON_REPO_TOKEN is set, but it cannot read '${submodule_url}'.
Check that the token has read-only Contents access to the AgentCanon repository.
EOF
  fi
  exit 86
fi

git_auth submodule sync --recursive "$submodule_path"
git_auth -c protocol.version=2 submodule update --init --force --depth=1 --recursive "$submodule_path"

submodule_sha="$(git -c "safe.directory=${parent_root}/${submodule_path}" -C "$submodule_path" rev-parse HEAD)"
echo "AGENT_CANON_SUBMODULE=ready path=${submodule_path} sha=${submodule_sha}"
