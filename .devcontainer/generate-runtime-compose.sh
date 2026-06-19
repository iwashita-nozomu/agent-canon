#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Renders shared devcontainer compose from repo-local Docker pack.
# upstream design ../documents/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream environment devcontainer.json initializeCommand entrypoint
# @dependency-end

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pack="${repo_root}/docker/packs/default.toml"
output="${repo_root}/.devcontainer/docker-compose.generated.yml"
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
  mapfile -t pack_values < <(
    python3 - "$pack" <<'PY'
from __future__ import annotations

import sys
import json
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

with open(sys.argv[1], "rb") as handle:
    data = tomllib.load(handle)
pack = data["pack"]
runtime = data.get("runtime", {})
print(f"dockerfile={pack['dockerfile']}")
print(f"workdir={runtime.get('workdir', '/workspace')}")
print(f"workspace_mount={runtime.get('workspace_mount', '/workspace')}")
for mount in runtime.get("mounts", []):
    print(f"mount={mount}")
for item in runtime.get("env", []):
    name, separator, value = str(item).partition("=")
    if separator:
        print(f"ENV:{name}: {json.dumps(value)}")
PY
  )

  compose_mode="repo-docker-pack"
  dockerfile=""
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
  pack_environment_lines=()
  for pack_value in "${pack_values[@]}"; do
    case "$pack_value" in
      dockerfile=*) dockerfile="${pack_value#dockerfile=}" ;;
      workdir=*) workdir="${pack_value#workdir=}" ;;
      workspace_mount=*) workspace_mount="${pack_value#workspace_mount=}" ;;
      mount=*) pack_mounts+=("${pack_value#mount=}") ;;
      ENV:*) pack_environment_lines+=("      ${pack_value#ENV:}") ;;
    esac
  done
else
  compose_mode="agent-canon-source-only"
  dockerfile=""
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
  pack_environment_lines=()
fi

volume_lines=("      - ..:${workspace_mount}:cached")
for pack_mount in "${pack_mounts[@]}"; do
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
if [ -d "${HOME}/.codex" ]; then
  volume_lines+=("      - ${HOME}/.codex:/root/.codex")
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
  "${pack_environment_lines[@]}"
)
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
  if [ "$compose_mode" = "repo-docker-pack" ]; then
    printf '    build:\n'
    printf '      context: ..\n'
    printf '      dockerfile: %s\n' "$dockerfile"
  else
    printf '    image: mcr.microsoft.com/devcontainers/base:ubuntu-22.04\n'
  fi
  printf '    working_dir: %s\n' "$workdir"
  printf '    volumes:\n'
  printf '%s\n' "${volume_lines[@]}"
  printf '    command: /bin/bash -lc "sleep infinity"\n'
  printf '    tty: true\n'
  printf '    init: true\n'
  if [ "$gpu_mode" = "enabled" ]; then
    printf '    gpus: all\n'
  fi
  printf '    environment:\n'
  printf '%s\n' "${environment_lines[@]}"
} > "$output"

printf 'devcontainer runtime generated: name=%s gpu=%s mode=%s network=auto secret_mount=%s pack=%s\n' "$compose_project_name" "$gpu_mode" "$compose_mode" "$secret_mount_status" "$pack"
