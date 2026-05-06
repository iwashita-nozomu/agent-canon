#!/usr/bin/env bash
# @dependency-start
# responsibility Checks out the AgentCanon submodule in GitHub Actions after root checkout.
# upstream design ../../documents/agent-canon-github-remote.md defines private submodule auth policy.
# upstream design ../../agents/workflows/github-copilot-workflow.md defines GitHub runtime behavior.
# downstream implementation ../../tools/ci/check_github_workflows.py enforces workflow usage.
# @dependency-end

set -euo pipefail

submodule_path="${AGENT_CANON_SUBMODULE_PATH:-vendor/agent-canon}"
token="${AGENT_CANON_REPO_TOKEN:-}"
ssh_key="${AGENT_CANON_REPO_SSH_KEY:-}"
ssh_key_dir=""

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
  if [ -n "$ssh_key_dir" ]; then
    rm -rf "$ssh_key_dir"
  fi
}

trap cleanup_ssh_key EXIT

prepare_ssh_key() {
  [ -n "$ssh_key" ] || return 0
  ssh_key_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/agent-canon-ssh.XXXXXX")"
  printf '%s\n' "$ssh_key" | tr -d '\r' >"${ssh_key_dir}/key"
  chmod 600 "${ssh_key_dir}/key"
  ssh-keyscan github.com >"${ssh_key_dir}/known_hosts" 2>/dev/null
  export GIT_SSH_COMMAND="ssh -i ${ssh_key_dir}/key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${ssh_key_dir}/known_hosts"
}

if git -C "$submodule_path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [ -n "$(git -C "$submodule_path" status --short --untracked-files=all)" ]; then
    cat >&2 <<EOF
AGENT_CANON_SUBMODULE=dirty
Refusing to update dirty submodule '${submodule_path}'.
Commit, stash, or clean the AgentCanon worktree before running this checkout helper locally.
EOF
    exit 87
  fi
fi

git_auth() {
  if [ -n "$token" ]; then
    git \
      -c "url.https://x-access-token:${token}@github.com/.insteadOf=https://github.com/" \
      -c "url.https://x-access-token:${token}@github.com/.insteadOf=git@github.com:" \
      "$@"
    return
  fi
  if [ -n "$ssh_key" ]; then
    git \
      -c "url.git@github.com:.insteadOf=https://github.com/" \
      "$@"
    return
  fi
  git "$@"
}

export GIT_TERMINAL_PROMPT=0
git config --global --add safe.directory "$PWD" || true
prepare_ssh_key

if ! git_auth ls-remote "$submodule_url" HEAD >/dev/null 2>&1; then
  if [ -z "$token" ] && [ -z "$ssh_key" ]; then
    cat >&2 <<EOF
AGENT_CANON_SUBMODULE_AUTH=missing
AgentCanon submodule '${submodule_url}' is not readable with the default workflow credentials.
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
git config --global --add safe.directory "$PWD/$submodule_path" || true

submodule_sha="$(git -C "$submodule_path" rev-parse HEAD)"
echo "AGENT_CANON_SUBMODULE=ready path=${submodule_path} sha=${submodule_sha}"
