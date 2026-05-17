#!/usr/bin/env bash
# @dependency-start
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
devcontainer_subnet="${DEVCONTAINER_SUBNET:-192.168.248.16/28}"
devcontainer_gateway="${DEVCONTAINER_GATEWAY:-192.168.248.17}"

if [ -f "$pack" ]; then
  mapfile -t pack_values < <(
    python3 - "$pack" <<'PY'
from __future__ import annotations

import sys
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
PY
  )

  compose_mode="repo-docker-pack"
  dockerfile=""
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
  for pack_value in "${pack_values[@]}"; do
    case "$pack_value" in
      dockerfile=*) dockerfile="${pack_value#dockerfile=}" ;;
      workdir=*) workdir="${pack_value#workdir=}" ;;
      workspace_mount=*) workspace_mount="${pack_value#workspace_mount=}" ;;
      mount=*) pack_mounts+=("${pack_value#mount=}") ;;
    esac
  done
else
  compose_mode="agent-canon-source-only"
  dockerfile=""
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
fi

volume_lines=("      - ..:${workspace_mount}:cached")
for pack_mount in "${pack_mounts[@]}"; do
  volume_lines+=("      - ${pack_mount}")
done
if [ -d /mnt/git ]; then
  volume_lines+=("      - /mnt/git:/mnt/git")
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

gpu_mode="disabled"
if [ -e /dev/nvidiactl ] || command -v nvidia-smi >/dev/null 2>&1; then
  gpu_mode="enabled"
fi

environment_lines=(
  "      DEVCONTAINER_RUNTIME_MODE: \"${compose_mode}\""
  "      DEVCONTAINER_GPU_MODE: \"${gpu_mode}\""
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
  printf '    networks:\n'
  printf '      default:\n'
  printf 'networks:\n'
  printf '  default:\n'
  printf '    ipam:\n'
  printf '      config:\n'
  printf '        - subnet: %s\n' "$devcontainer_subnet"
  printf '          gateway: %s\n' "$devcontainer_gateway"
} > "$output"

printf 'devcontainer runtime generated: name=%s gpu=%s mode=%s subnet=%s gateway=%s pack=%s\n' "$compose_project_name" "$gpu_mode" "$compose_mode" "$devcontainer_subnet" "$devcontainer_gateway" "$pack"
