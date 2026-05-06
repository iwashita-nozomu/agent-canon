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

if [ ! -f ".gitmodules" ]; then
  echo "AGENT_CANON_SUBMODULE=absent reason=no_gitmodules"
  exit 0
fi

submodule_url="$(git config -f .gitmodules --get "submodule.${submodule_path}.url" || true)"
if [ -z "$submodule_url" ]; then
  echo "AGENT_CANON_SUBMODULE=absent reason=no_agent_canon_entry path=${submodule_path}"
  exit 0
fi

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
  git "$@"
}

export GIT_TERMINAL_PROMPT=0
git config --global --add safe.directory "$PWD" || true

if ! git_auth ls-remote "$submodule_url" HEAD >/dev/null 2>&1; then
  if [ -z "$token" ]; then
    cat >&2 <<EOF
AGENT_CANON_SUBMODULE_AUTH=missing
AgentCanon submodule '${submodule_url}' is not readable with the default workflow credentials.
For private AgentCanon repositories, add a repository secret named AGENT_CANON_REPO_TOKEN
with read-only Contents access to the AgentCanon repository, then rerun the workflow.
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
