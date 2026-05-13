#!/usr/bin/env bash
# @dependency-start
# responsibility Reports shared devcontainer attach status.
# upstream design ../documents/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream environment devcontainer.json postAttachCommand entrypoint
# @dependency-end
set -euo pipefail

gpu_status="disabled"
if [ "${DEVCONTAINER_GPU_MODE:-disabled}" = "enabled" ]; then
  gpu_status="enabled"
fi

mnt_git_status="not-mounted"
if [ -d /mnt/git ]; then
  mnt_git_status="mounted"
fi

docker_socket_status="unavailable"
if [ -S /var/run/docker.sock ]; then
  docker_socket_status="mounted"
fi

codex_home_status="not-mounted"
if [ -d /root/.codex ] || [ -d "${HOME:-/root}/.codex" ]; then
  codex_home_status="mounted"
fi

codex_login_status="unauthenticated"
if command -v codex >/dev/null 2>&1 && codex login status >/dev/null 2>&1; then
  codex_login_status="authenticated"
fi

gh_config_status="not-mounted"
if [ -d /root/.config/gh ] || [ -d "${HOME:-/root}/.config/gh" ]; then
  gh_config_status="mounted"
fi

ssh_dir_status="not-mounted"
if [ -d /root/.ssh ] || [ -d "${HOME:-/root}/.ssh" ]; then
  ssh_dir_status="mounted"
fi

ssh_agent_status="not-forwarded"
if [ -n "${SSH_AUTH_SOCK:-}" ] && [ -S "${SSH_AUTH_SOCK}" ]; then
  ssh_agent_status="forwarded"
fi

gh_auth_status="unauthenticated"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh_auth_status="authenticated"
fi

repo_root="/workspace"
if [ ! -f "${repo_root}/.codex/config.toml" ]; then
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd "${script_dir}/.." && pwd)"
fi

codex_approval_policy="<unset>"
codex_sandbox_mode="<unset>"
if [ -f "${repo_root}/.codex/config.toml" ]; then
  codex_approval_policy="$(awk -F'=' '/^approval_policy[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${repo_root}/.codex/config.toml")"
  codex_sandbox_mode="$(awk -F'=' '/^sandbox_mode[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${repo_root}/.codex/config.toml")"
  codex_approval_policy="${codex_approval_policy:-<unset>}"
  codex_sandbox_mode="${codex_sandbox_mode:-<unset>}"
fi

echo
echo "----------------------------------------"
echo "AgentCanon devcontainer"
echo "----------------------------------------"
echo "workspace: ${repo_root}"
echo "gpu: ${gpu_status}"
echo "/mnt/git: ${mnt_git_status}"
echo "docker-socket: ${docker_socket_status}"
echo "host-codex-home: ${codex_home_status}"
echo "codex-login: ${codex_login_status}"
echo "host-gh-config: ${gh_config_status}"
echo "host-ssh-dir: ${ssh_dir_status}"
echo "ssh-agent: ${ssh_agent_status}"
echo "gh-auth: ${gh_auth_status}"
echo "codex-approval: ${codex_approval_policy}"
echo "codex-sandbox: ${codex_sandbox_mode}"
echo "pythonpath: ${PYTHONPATH:-<unset>}"
echo
echo "quick checks:"
echo "  make ci-quick"
echo "  make docs-check"
echo "  make docker-build-check"
echo "----------------------------------------"
