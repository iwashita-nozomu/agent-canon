#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Reports default devcontainer attach status.
# upstream design ../documents/contracts/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream design ../documents/rule/dependency-module-changes.md topic-root source visibility contract
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md default startup profile boundary
# upstream environment devcontainer.json postAttachCommand entrypoint
# @dependency-end
set -euo pipefail

runtime_root="${AGENT_CANON_RUNTIME_ROOT:-/var/lib/agent-canon/runtime}"
repo_root="${AGENT_CANON_REPOSITORY_ROOT:-}"
workspace_layout="${AGENT_CANON_WORKSPACE_LAYOUT:-managed-topic}"
workspace_source="${DEPENDENCY_MODULE_CONTAINER_SOURCE:-}"
workspace_target="${DEPENDENCY_MODULE_CONTAINER_TARGET:-}"
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
gpu_status="${DEVCONTAINER_GPU_MODE:-disabled}"

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

codex_state_status="container-local"
if grep -F '/root/.codex' /proc/self/mountinfo >/dev/null 2>&1; then
  codex_state_status="forbidden-host-mount-detected"
fi

codex_login_status="unauthenticated"
if command -v codex >/dev/null 2>&1 && codex login status >/dev/null 2>&1; then
  codex_login_status="authenticated"
fi

gh_config_status="not-mounted"
if [ -d "${HOME:-}/.config/gh" ]; then
  gh_config_status="mounted"
fi

ssh_dir_status="not-mounted"
if [ -d "${HOME:-}/.ssh" ]; then
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
  local dependency_tool=""
  local candidate
  [ "${AGENT_CANON_WORKSPACE_ROOT:-}" = "/workspace" ] || {
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=AGENT_CANON_WORKSPACE_ROOT must be /workspace" >&2
    return 1
  }
  [ -d /workspace ] || {
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=workspace-root-mount-missing:/workspace" >&2
    return 1
  }
  case "$workspace_layout" in
  managed-topic|direct-repo) ;;
  *)
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=workspace-layout-unsupported:${workspace_layout}" >&2
    return 1
    ;;
  esac
  [ -n "$workspace_source" ] || {
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=workspace-source-readback-missing" >&2
    return 1
  }
  [ -n "$workspace_target" ] || {
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=workspace-target-readback-missing" >&2
    return 1
  }
  expected_target="/workspace"
  if [ "$workspace_layout" = "direct-repo" ]; then
    expected_target="$repo_root"
  fi
  [ "$workspace_target" = "$expected_target" ] || {
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=workspace-target-readback-mismatch:${workspace_target}:${expected_target}" >&2
    return 1
  }
  echo "DEPENDENCY_MODULE_CONTAINER_LAYOUT=${workspace_layout}"
  echo "DEPENDENCY_MODULE_CONTAINER_SOURCE=${workspace_source}"
  echo "DEPENDENCY_MODULE_CONTAINER_TARGET=${workspace_target}"
  if [ "$workspace_layout" = "direct-repo" ]; then
    echo "DEPENDENCY_MODULE_CONTAINER=not-selected layout=direct-repo repository=${repo_root}"
    echo "DEPENDENCY_MODULE_STATUS=not-selected layout=direct-repo"
    return 0
  fi
  for candidate in \
    "${repo_root}/tools/agent_tools/dependency_module_change.py" \
    "${repo_root}/vendor/agent-canon/tools/agent_tools/dependency_module_change.py"; do
    if [ -f "$candidate" ]; then
      dependency_tool="$candidate"
      break
    fi
  done
  [ -n "$dependency_tool" ] || {
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=tool-missing:${repo_root}/tools/agent_tools/dependency_module_change.py:${repo_root}/vendor/agent-canon/tools/agent_tools/dependency_module_change.py" >&2
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
  echo "DEPENDENCY_MODULE_CONTAINER=pass layout=managed-topic tool=${dependency_tool} repository=${repo_root}"
}

check_dependency_module_runtime

runtime_identity_mode="${AGENT_CANON_RUNTIME_IDENTITY_MODE:-}"
runtime_user_name="${AGENT_CANON_CONTAINER_USER:-}"
case "$runtime_identity_mode" in
  project)
    expected_user="project"
    expected_home="/home/project"
    [ "$(id -u)" -ne 0 ] || {
      echo "DEPENDENCY_MODULE_CONTAINER_ERROR=project-identity-is-root" >&2
      exit 1
    }
    ;;
  rootless-root)
    expected_user="root"
    expected_home="/root"
    [ "$(id -u)" -eq 0 ] || {
      echo "DEPENDENCY_MODULE_CONTAINER_ERROR=rootless-root-identity-not-uid-0" >&2
      exit 1
    }
    ;;
  *)
    echo "DEPENDENCY_MODULE_CONTAINER_ERROR=runtime-identity-marker-missing-or-unsupported" >&2
    exit 1
    ;;
esac
[ "$runtime_user_name" = "$expected_user" ] || {
  echo "DEPENDENCY_MODULE_CONTAINER_ERROR=runtime-user-marker-mismatch:$expected_user:${runtime_user_name:-<unset>}" >&2
  exit 1
}
[ "$(id -un)" = "$expected_user" ] || {
  echo "DEPENDENCY_MODULE_CONTAINER_ERROR=runtime-user-name-mismatch:$expected_user:$(id -un)" >&2
  exit 1
}
[ "${HOME:-}" = "$expected_home" ] || {
  echo "DEPENDENCY_MODULE_CONTAINER_ERROR=runtime-home-mismatch:${HOME:-}" >&2
  exit 1
}
[ -w "$repo_root" ] || {
  echo "DEPENDENCY_MODULE_CONTAINER_ERROR=workspace-not-writable:$repo_root" >&2
  exit 1
}
workspace_write_probe_dir="$repo_root/.agent-canon"
mkdir -p "$workspace_write_probe_dir" || {
  echo "DEPENDENCY_MODULE_CONTAINER_ERROR=workspace-write-probe-directory-failed:$workspace_write_probe_dir" >&2
  exit 1
}
workspace_write_probe="$(mktemp "$workspace_write_probe_dir/.runtime-identity-write.XXXXXX")" || {
  echo "DEPENDENCY_MODULE_CONTAINER_ERROR=workspace-write-probe-failed:$repo_root" >&2
  exit 1
}
rm -f "$workspace_write_probe"

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
echo "codex-state: ${codex_state_status}"
echo "runtime-root: ${runtime_root} ($(if [ -d "$runtime_root" ]; then echo available; else echo missing; fi))"
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
