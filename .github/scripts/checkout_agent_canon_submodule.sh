#!/usr/bin/env bash
# @dependency-start
# contract tool
# responsibility Checks out the AgentCanon submodule in GitHub Actions after root checkout.
# upstream design ../../documents/agent-canon-github-remote.md defines private submodule auth policy.
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines GitHub runtime behavior.
# downstream implementation ../../tools/ci/check_github_workflows.py enforces workflow usage.
# @dependency-end

set -euo pipefail

submodule_path="${AGENT_CANON_SUBMODULE_PATH:-vendor/agent-canon}"
token="${AGENT_CANON_REPO_TOKEN:-}"
ssh_key="${AGENT_CANON_REPO_SSH_KEY:-}"
ssh_key_dir=""
ssh_key_persistent=0

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
  if [ "$ssh_key_persistent" = "1" ]; then
    return
  fi
  if [ -n "$ssh_key_dir" ]; then
    rm -rf "$ssh_key_dir"
  fi
}

trap cleanup_ssh_key EXIT

github_repo_path() {
  case "$submodule_url" in
    https://github.com/*)
      printf '%s\n' "${submodule_url#https://github.com/}"
      ;;
    git@github.com:*)
      printf '%s\n' "${submodule_url#git@github.com:}"
      ;;
    *)
      return 1
      ;;
  esac
}

github_ssh_url() {
  repo_path="$(github_repo_path || true)"
  [ -n "$repo_path" ] || return 1
  printf 'git@github.com:%s\n' "$repo_path"
}

persist_github_actions_token_auth() {
  [ -n "${GITHUB_ENV:-}" ] || return 0
  [ -n "$token" ] || return 0
  token_repo_path="$(github_repo_path || true)"
  [ -n "$token_repo_path" ] || return 0

  token_submodule_url="https://x-access-token:${token}@github.com/${token_repo_path}"
  git config --global "url.${token_submodule_url}.insteadOf" "$submodule_url"
  echo "AGENT_CANON_SUBMODULE_AUTH=token_persisted scope=github_actions"
}

persist_github_actions_ssh_auth() {
  [ -n "${GITHUB_ENV:-}" ] || return 0
  ssh_submodule_url="$(github_ssh_url || true)"
  [ -n "$ssh_submodule_url" ] || return 0

  printf 'GIT_SSH_COMMAND=%s\n' "$GIT_SSH_COMMAND" >>"$GITHUB_ENV"
  if [ "$submodule_url" != "$ssh_submodule_url" ]; then
    git config --global "url.${ssh_submodule_url}.insteadOf" "$submodule_url"
  fi
  echo "AGENT_CANON_SUBMODULE_AUTH=ssh_persisted scope=github_actions"
}

prepare_ssh_key() {
  [ -n "$ssh_key" ] || return 0
  [ -z "$token" ] || return 0
  if [ -n "${GITHUB_ENV:-}" ]; then
    ssh_key_dir="${RUNNER_TEMP:-/tmp}/agent-canon-ssh"
    rm -rf "$ssh_key_dir"
    mkdir -p "$ssh_key_dir"
    ssh_key_persistent=1
  else
    ssh_key_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/agent-canon-ssh.XXXXXX")"
  fi
  printf '%s\n' "$ssh_key" | tr -d '\r' >"${ssh_key_dir}/key"
  chmod 600 "${ssh_key_dir}/key"
  ssh-keyscan github.com >"${ssh_key_dir}/known_hosts" 2>/dev/null
  export GIT_SSH_COMMAND="ssh -i ${ssh_key_dir}/key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=${ssh_key_dir}/known_hosts"
  persist_github_actions_ssh_auth
}

if git -C "$submodule_path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [ -n "$(git -C "$submodule_path" status --short --untracked-files=all)" ]; then
    cat >&2 <<EOF
AGENT_CANON_SUBMODULE=dirty
Refusing to update dirty submodule '${submodule_path}'.
Commit AgentCanon-owned artifacts first; stash or clean only explicitly disposable local scratch before running this checkout helper locally.
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
persist_github_actions_token_auth
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
