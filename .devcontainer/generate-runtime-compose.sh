#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Renders shared devcontainer compose from repo-local Docker pack.
# upstream design ../documents/contracts/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream design ../documents/rule/dependency-module-changes.md topic-root source visibility contract
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md parent layout and runtime shell boundary
# upstream implementation ../tools/agent_tools/dependency_module_change.py topic clone lifecycle tool
# upstream design ../documents/experiments/gpu-admission-r5-source-packet.md exact Compose runtime identity wiring
# upstream environment devcontainer.json initializeCommand entrypoint
# @dependency-end

set -euo pipefail

repo_root="${AGENT_CANON_DEVCONTAINER_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
repo_root="$(cd "$repo_root" && pwd -P)"
workspace_root="$(cd "${repo_root}/.." && pwd -P)"
[ -d "$workspace_root" ] || {
  printf 'devcontainer workspace root is unavailable: %s\n' "$workspace_root" >&2
  exit 1
}
workspace_parent="$(cd "${workspace_root}/.." && pwd -P)"
if [ "$(basename "$workspace_parent")" != "workspace" ]; then
  case "$(basename "$workspace_root")" in
    workspace-*)
      printf 'devcontainer rejects legacy workspace-<topic-slug> root: %s\n' "$workspace_root" >&2
      ;;
    *)
      printf 'devcontainer requires a topic workspace root under workspace/<topic-slug>: %s\n' "$workspace_root" >&2
      ;;
  esac
  exit 1
fi
repo_basename="$(basename "$repo_root")"
container_repo_root="/workspace/${repo_basename}"
pack="${repo_root}/docker/packs/default.toml"
compose_output_raw="${AGENT_CANON_DOCKER_COMPOSE_OUTPUT:-.devcontainer/docker-compose.generated.yml}"
if [ "${compose_output_raw#/}" = "$compose_output_raw" ]; then
  compose_output="${repo_root}/${compose_output_raw}"
else
  compose_output="$compose_output_raw"
fi
default_project_name="$(
  python3 - "$repo_root" <<'PY'
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

repo_root = sys.argv[1]
repo_name = Path(repo_root).name.casefold()
slug = re.sub(r"[^a-z0-9_-]+", "-", repo_name).strip("-_") or "workspace"
digest = hashlib.sha1(repo_root.encode("utf-8")).hexdigest()[:8]
print(f"{slug}-{digest}-devcontainer")
PY
)"
compose_project_name="${DEVCONTAINER_PROJECT_NAME:-$default_project_name}"

if [ -f "$pack" ]; then
  pack_values_raw="$(
    python3 - "$pack" <<'PY'
from __future__ import annotations

import sys
import json
import re
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

with open(sys.argv[1], "rb") as handle:
    data = tomllib.load(handle)
pack = data["pack"]
runtime = data.get("runtime", {})
runtime_shell = runtime.get("shell", "/bin/bash")
if not isinstance(runtime_shell, str) or re.fullmatch(r"/[A-Za-z0-9._/-]+", runtime_shell) is None:
    raise SystemExit("runtime.shell must be one absolute executable path")
print(f"dockerfile={pack['dockerfile']}")
print(f"runtime_shell={runtime_shell}")
print(f"workdir={runtime.get('workdir', '/workspace')}")
print(f"workspace_mount={runtime.get('workspace_mount', '/workspace')}")
for mount in runtime.get("mounts", []):
    print(f"mount={mount}")
for item in runtime.get("env", []):
    name, separator, value = str(item).partition("=")
    if separator:
        print(f"ENV:{name}: {json.dumps(value)}")
PY
  )"
  mapfile -t pack_values <<< "$pack_values_raw"

  compose_mode="repo-docker-pack"
  dockerfile=""
  runtime_shell="/bin/bash"
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
  pack_environment_lines=()
  for pack_value in "${pack_values[@]}"; do
    case "$pack_value" in
      dockerfile=*) dockerfile="${pack_value#dockerfile=}" ;;
      runtime_shell=*) runtime_shell="${pack_value#runtime_shell=}" ;;
      workdir=*) workdir="${pack_value#workdir=}" ;;
      workspace_mount=*) workspace_mount="${pack_value#workspace_mount=}" ;;
      mount=*) pack_mounts+=("${pack_value#mount=}") ;;
      ENV:*) pack_environment_lines+=("      ${pack_value#ENV:}") ;;
    esac
  done
else
  compose_mode="agent-canon-source-only"
  dockerfile=""
  runtime_shell="/bin/bash"
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
  pack_environment_lines=()
fi

parent_layout=false
parent_environment_source="${repo_root}/.devcontainer/parent-environment.sh"
if [ -d "${repo_root}/vendor/agent-canon" ]; then
  parent_layout=true
  if [ ! -f "$parent_environment_source" ] || [ -L "$parent_environment_source" ]; then
    printf 'devcontainer parent environment source must be a regular file: %s\n' "$parent_environment_source" >&2
    exit 1
  fi
  host_zshrc="${HOME}/.zshrc"
  if [ ! -f "$host_zshrc" ] || [ -L "$host_zshrc" ]; then
    printf 'devcontainer requires a regular host zshrc source: %s\n' "$host_zshrc" >&2
    exit 1
  fi
fi

if [[ "$runtime_shell" != /* || "$runtime_shell" == *[!A-Za-z0-9._/-]* ]]; then
  printf 'devcontainer runtime.shell must be one absolute executable path: %s\n' "$runtime_shell" >&2
  exit 1
fi

workspace_root_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$workspace_root")"
volume_lines=(
  "      - type: bind"
  "        source: ${workspace_root_yaml}"
  '        target: "/workspace"'
)
volume_lines+=(
  "      - type: bind"
  "        source: /var/lib/agent-canon/runtime"
  "        target: /var/lib/agent-canon/runtime"
)
if [ "$parent_layout" = true ]; then
  host_zshrc_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$host_zshrc")"
  volume_lines+=(
    "      - type: bind"
    "        source: ${host_zshrc_yaml}"
    '        target: "/etc/project-template/zsh/.zshrc"'
    "        read_only: true"
  )
  parent_environment_source_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$parent_environment_source")"
  volume_lines+=(
    "      - type: bind"
    "        source: ${parent_environment_source_yaml}"
    '        target: "/etc/project-template/parent-environment.sh"'
    "        read_only: true"
  )
fi
for pack_mount in "${pack_mounts[@]}"; do
  case "$pack_mount" in
    *:/workspace|*:/workspace:*)
      printf 'devcontainer runtime pack duplicates the workspace-root mount: %s\n' "$pack_mount" >&2
      exit 1
      ;;
  esac
  volume_lines+=("      - ${pack_mount}")
done
if [ -d /mnt/git ]; then
  volume_lines+=("      - /mnt/git:/mnt/git")
fi
secret_mount_status="disabled"
secret_target="${AGENT_CANON_SECRET_MOUNT:-/mnt/agent-canon-secrets}"
secret_mode="${AGENT_CANON_SECRET_DIR_MODE:-ro}"
secret_read_only="true"
case "$secret_mode" in
  ro|readonly) secret_read_only="true" ;;
  rw|readwrite) secret_read_only="false" ;;
  *)
    printf 'devcontainer secret mount skipped: AGENT_CANON_SECRET_DIR_MODE must be ro or rw\n' >&2
    secret_mode="invalid"
    ;;
esac
if [ -n "${AGENT_CANON_SECRET_DIR:-}" ] && [ "$secret_mode" != "invalid" ]; then
  if [ ! -d "${AGENT_CANON_SECRET_DIR}" ]; then
    printf 'devcontainer secret mount skipped: AGENT_CANON_SECRET_DIR is not an existing directory\n' >&2
  elif [[ "$secret_target" != /* ]]; then
    printf 'devcontainer secret mount skipped: AGENT_CANON_SECRET_MOUNT must be an absolute container path\n' >&2
  else
    secret_source_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "${AGENT_CANON_SECRET_DIR}")"
    secret_target_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$secret_target")"
    volume_lines+=(
      "      - type: bind"
      "        source: ${secret_source_yaml}"
      "        target: ${secret_target_yaml}"
      "        read_only: ${secret_read_only}"
    )
    secret_mount_status="enabled"
  fi
fi
if [ -d "${HOME}/.config/gh" ]; then
  volume_lines+=("      - ${HOME}/.config/gh:/root/.config/gh")
fi
if [ -d "${HOME}/.ssh" ]; then
  volume_lines+=("      - ${HOME}/.ssh:/root/.ssh:ro")
fi
if [ -n "${SSH_AUTH_SOCK:-}" ] && [ -S "${SSH_AUTH_SOCK}" ]; then
  volume_lines+=("      - ${SSH_AUTH_SOCK}:/ssh-agent")
fi

host_gpu_visible() {
  [ -e /dev/nvidiactl ] && return 0
  command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1
}

docker_gpu_runtime_available() {
  command -v docker >/dev/null 2>&1 || return 1
  docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'
}

gpu_request_raw="${DEVCONTAINER_GPU_REQUEST:-auto}"
gpu_request="auto"
gpu_mode="unavailable"
gpu_notice="host-gpu-not-visible"
case "$gpu_request_raw" in
  auto | "")
    if host_gpu_visible; then
      if docker_gpu_runtime_available; then
        gpu_mode="enabled"
        gpu_notice="docker-nvidia-runtime-available"
      else
        gpu_notice="docker-nvidia-runtime-unavailable"
      fi
    fi
    ;;
  disabled | off | false | FALSE | 0)
    gpu_request="disabled"
    gpu_mode="disabled"
    gpu_notice="disabled-by-request"
    ;;
  enabled | on | true | TRUE | 1)
    gpu_request="enabled"
    if host_gpu_visible && docker_gpu_runtime_available; then
      gpu_mode="enabled"
      gpu_notice="docker-nvidia-runtime-available"
    elif host_gpu_visible; then
      gpu_notice="docker-nvidia-runtime-unavailable"
    fi
    ;;
  *)
    printf 'devcontainer gpu request ignored: DEVCONTAINER_GPU_REQUEST must be auto, enabled, or disabled\n' >&2
    if host_gpu_visible && docker_gpu_runtime_available; then
      gpu_mode="enabled"
      gpu_notice="docker-nvidia-runtime-available"
    fi
    ;;
esac

if [ "$gpu_mode" = "unavailable" ]; then
  printf 'devcontainer gpu unavailable: %s; continuing without gpus: all\n' "$gpu_notice" >&2
fi

environment_lines=(
  "      DEVCONTAINER_RUNTIME_MODE: \"${compose_mode}\""
  "      DEVCONTAINER_GPU_MODE: \"${gpu_mode}\""
  "      DEVCONTAINER_GPU_NOTICE: \"${gpu_notice}\""
  "      DEVCONTAINER_GPU_REQUEST: \"${gpu_request}\""
  "      AGENT_CANON_SECRET_MOUNT: \"${secret_target}\""
  "      AGENT_CANON_SECRET_DIR_MODE: \"${secret_mode}\""
  '      AGENT_CANON_RUNTIME_ROUTE: "MANAGED_CONTAINER"'
  '      AGENT_CANON_WORKSPACE_ROOT: "/workspace"'
  "      AGENT_CANON_REPOSITORY_ROOT: \"${container_repo_root}\""
  '      AGENT_CANON_SHARED_RUNTIME_SOURCE: "/var/lib/agent-canon/runtime"'
  '      AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT: "/var/lib/agent-canon/runtime/shared-runtime-provision.json"'
  "${pack_environment_lines[@]}"
)
if [ "$parent_layout" = true ]; then
  environment_lines=(
    '      HOME: "/tmp/project-template-home"'
    '      ZDOTDIR: "/etc/project-template/zsh"'
    "      SHELL: \"${runtime_shell}\""
    "${environment_lines[@]}"
  )
fi
if [ -n "${SSH_AUTH_SOCK:-}" ] && [ -S "${SSH_AUTH_SOCK}" ]; then
  environment_lines+=('      SSH_AUTH_SOCK: "/ssh-agent"')
fi
if [ "$gpu_mode" = "enabled" ]; then
  environment_lines+=(
    "      NVIDIA_VISIBLE_DEVICES: all"
    '      NVIDIA_DRIVER_CAPABILITIES: "compute,utility"'
  )
fi

{
  printf 'name: %s\n' "$compose_project_name"
  printf 'services:\n'
  printf '  workspace:\n'
  printf '    user: "${LOCAL_UID}:${LOCAL_GID}"\n'
  printf '    group_add:\n'
  printf '      - "${AGENT_CANON_RUNTIME_GID}"\n'
  if [ "$compose_mode" = "repo-docker-pack" ]; then
    printf '    build:\n'
    printf '      context: ..\n'
    printf '      dockerfile: %s\n' "$dockerfile"
  else
    printf '    image: mcr.microsoft.com/devcontainers/base:ubuntu-22.04\n'
  fi
  printf '    working_dir: %s\n' "$container_repo_root"
  if [ "$parent_layout" = true ]; then
    printf '    tmpfs:\n'
    printf '      - /tmp/project-template-home:uid=${LOCAL_UID},gid=${LOCAL_GID},mode=700\n'
  fi
  printf '    volumes:\n'
  printf '%s\n' "${volume_lines[@]}"
  printf '    command: %s -lc "sleep infinity"\n' "$runtime_shell"
  printf '    tty: true\n'
  printf '    init: true\n'
  if [ "$gpu_mode" = "enabled" ]; then
    printf '    gpus: all\n'
  fi
  printf '    environment:\n'
  printf '%s\n' "${environment_lines[@]}"
} > "$compose_output"


printf 'devcontainer runtime generated: name=%s gpu=%s mode=%s network=auto secret_mount=%s pack=%s\n' "$compose_project_name" "$gpu_mode" "$compose_mode" "$secret_mount_status" "$pack"
