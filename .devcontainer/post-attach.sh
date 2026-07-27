#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Reports shared devcontainer attach status.
# upstream design ../documents/contracts/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream design ../documents/rule/dependency-module-changes.md topic-root source visibility contract
# upstream design ../documents/experiments/gpu-admission-r5-source-packet.md observational readback receipt contract
# upstream environment devcontainer.json postAttachCommand entrypoint
# upstream implementation finalize-shared-runtime.sh publishes the exact readback receipt
# @dependency-end
set -euo pipefail

runtime_root="${AGENT_CANON_RUNTIME_ROOT:-/var/lib/agent-canon/runtime}"
repo_root="${AGENT_CANON_REPOSITORY_ROOT:-}"
[ -n "$repo_root" ] || {
  echo "DEPENDENCY_MODULE_CONTAINER_ERROR=repository-root-env-missing" >&2
  exit 1
}
case "$repo_root" in
  /workspace/*/*)
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=repository-root-must-be-direct-child-of-workspace:${repo_root}" >&2
    exit 1
    ;;
  /workspace/*) ;;
  *)
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=repository-root-outside-workspace:${repo_root}" >&2
    exit 1
    ;;
esac
[ -d "$repo_root" ] || {
  echo "DEPENDENCY_MODULE_CONTAINER_ERROR=repository-root-missing:${repo_root}" >&2
  exit 1
}
source_projection_root="${AGENT_CANON_SOURCE_PROJECTION_ROOT:-${repo_root}/reports/agents/devcontainer/runtime}"
readback_receipt="${runtime_root}/shared-runtime-readback.json"

gpu_device_visible() {
  [ -e /dev/nvidia0 ] && return 0
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1
}

gpu_status="unavailable (notice only)"
case "${DEVCONTAINER_GPU_MODE:-unavailable}" in
  enabled)
    if gpu_device_visible; then
      gpu_status="enabled"
    else
      gpu_status="unavailable (requested, not visible)"
    fi
    ;;
  disabled)
    gpu_status="disabled"
    ;;
  unavailable)
    gpu_status="unavailable (notice only)"
    ;;
  *)
    gpu_status="${DEVCONTAINER_GPU_MODE}"
    ;;
esac

mnt_git_status="not-mounted"
if [ -d /mnt/git ]; then
  mnt_git_status="mounted"
fi

secret_mount_target="${AGENT_CANON_SECRET_MOUNT:-/mnt/agent-canon-secrets}"
secret_mount_status="not-mounted"
if [ -d "$secret_mount_target" ]; then
  secret_mount_status="mounted"
fi

docker_socket_status="unavailable"
if [ -S /var/run/docker.sock ]; then
  docker_socket_status="mounted"
fi

codex_home_status="container-local (host mount forbidden)"
if grep -F '/root/.codex' /proc/self/mountinfo >/dev/null 2>&1; then
  codex_home_status="forbidden-host-mount-detected"
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

codex_approval_policy="<unset>"
codex_sandbox_mode="<unset>"
if [ -f "${repo_root}/.codex/config.toml" ]; then
  codex_approval_policy="$(awk -F'=' '/^approval_policy[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${repo_root}/.codex/config.toml")"
  codex_sandbox_mode="$(awk -F'=' '/^sandbox_mode[[:space:]]*=/{gsub(/[ "]/, "", $2); print $2; exit}' "${repo_root}/.codex/config.toml")"
  codex_approval_policy="${codex_approval_policy:-<unset>}"
  codex_sandbox_mode="${codex_sandbox_mode:-<unset>}"
fi

check_dependency_module_runtime() {
  local dependency_tool="${repo_root}/tools/agent_tools/dependency_module_change.py"
  [ "${AGENT_CANON_WORKSPACE_ROOT:-}" = "/workspace" ] || {
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=AGENT_CANON_WORKSPACE_ROOT must be /workspace" >&2
    return 1
  }
  [ -d /workspace ] || {
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=workspace-root-mount-missing:/workspace" >&2
    return 1
  }
  [ -f "$dependency_tool" ] || {
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=tool-missing:${dependency_tool}" >&2
    return 1
  }
  if [ -f "${repo_root}/.gitmodules" ]; then
    topic="$(git -C "$repo_root" config --local --get agent-canon.topic.topic || true)"
    [ -n "$topic" ] || {
      echo "DEPENDENCY_MODULE_CONTAINER_ERROR=topic-marker-missing:${repo_root}" >&2
      return 1
    }
    python3 "$dependency_tool" --root "$repo_root" status --topic "$topic"
  fi
  echo "DEPENDENCY_MODULE_CONTAINER=pass tool=${dependency_tool} repository=${repo_root}"
}

check_dependency_module_runtime

echo
echo "----------------------------------------"
echo "AgentCanon devcontainer"
echo "----------------------------------------"
echo "repository: ${repo_root}"
echo "gpu: ${gpu_status}"
echo "gpu-notice: ${DEVCONTAINER_GPU_NOTICE:-<unset>}"
echo "/mnt/git: ${mnt_git_status}"
echo "secret-mount: ${secret_mount_status} (${secret_mount_target}, mode=${AGENT_CANON_SECRET_DIR_MODE:-ro})"
echo "docker-socket: ${docker_socket_status}"
echo "host-codex-home: ${codex_home_status}"
echo "runtime-root: ${runtime_root} ($(if [ -d "$runtime_root" ]; then echo available; else echo missing; fi))"
echo "runtime-readback: ${readback_receipt} ($(if [ -f "$readback_receipt" ]; then echo published; else echo missing; fi))"
echo "source-projection: ${source_projection_root} ($(if [ -f "$runtime_root/tool-availability.json" ]; then echo cataloged-tools-readback; else echo missing; fi))"
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
