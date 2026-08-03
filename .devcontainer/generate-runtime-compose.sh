#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Renders shared devcontainer compose from repo-local Docker pack.
# upstream design ../documents/contracts/github-first-module-and-devcontainer-policy.md devcontainer boundary
# upstream design ../documents/rule/dependency-module-changes.md topic-root source visibility contract
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md parent layout and runtime shell boundary
# upstream implementation ../tools/agent_tools/dependency_module_change.py topic clone lifecycle tool
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md default startup profile boundary
# upstream design ../documents/experiments/gpu-admission-r5-source-packet.md opt-in GPU runtime identity wiring
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
if [ "$(basename "$workspace_root")" = "workspace" ]; then
  workspace_layout="direct-repo"
elif [ "$(basename "$workspace_parent")" != "workspace" ]; then
  case "$(basename "$workspace_root")" in
    workspace-*)
      printf 'devcontainer rejects legacy workspace-<topic-slug> root: %s\n' "$workspace_root" >&2
      ;;
    *)
      printf 'devcontainer requires a topic workspace root under workspace/<topic-slug>: %s\n' "$workspace_root" >&2
      ;;
  esac
  exit 1
else
  workspace_layout="managed-topic"
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
dependency_profile = runtime.get("dependency_profile", "full")
if not isinstance(dependency_profile, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", dependency_profile) is None:
    raise SystemExit("runtime.dependency_profile must be a non-empty profile name")
print(f"dockerfile={pack['dockerfile']}")
print(f"runtime_shell={runtime_shell}")
print(f"dependency_profile={dependency_profile}")
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
  dependency_profile="full"
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
  pack_environment_lines=()
  for pack_value in "${pack_values[@]}"; do
    case "$pack_value" in
      dockerfile=*) dockerfile="${pack_value#dockerfile=}" ;;
      runtime_shell=*) runtime_shell="${pack_value#runtime_shell=}" ;;
      dependency_profile=*) dependency_profile="${pack_value#dependency_profile=}" ;;
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
  dependency_profile="full"
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
  pack_environment_lines=()
fi

parent_layout=false
parent_environment_enabled=false
parent_environment_source="${repo_root}/.devcontainer/parent-environment.sh"
parent_environment_manifest="${repo_root}/.devcontainer/parent-environment.toml"
if [ -d "${repo_root}/vendor/agent-canon" ]; then
  parent_layout=true
  if [ -e "$parent_environment_source" ] || [ -L "$parent_environment_source" ] \
    || [ -e "$parent_environment_manifest" ] || [ -L "$parent_environment_manifest" ]; then
    if [ ! -f "$parent_environment_source" ]; then
      printf 'devcontainer parent environment source does not resolve to a file: %s\n' "$parent_environment_source" >&2
      exit 1
    fi
    if [ ! -f "$parent_environment_manifest" ]; then
      printf 'devcontainer parent environment manifest does not resolve to a file: %s\n' "$parent_environment_manifest" >&2
      exit 1
    fi
    parent_environment_enabled=true
  fi
fi

if [[ "$runtime_shell" != /* || "$runtime_shell" == *[!A-Za-z0-9._/-]* ]]; then
  printf 'devcontainer runtime.shell must be one absolute executable path: %s\n' "$runtime_shell" >&2
  exit 1
fi

workspace_mount_source="$workspace_root"
workspace_mount_target="/workspace"
if [ "$workspace_layout" = "direct-repo" ]; then
  workspace_mount_source="$repo_root"
  workspace_mount_target="$container_repo_root"
fi
workspace_mount_source_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$workspace_mount_source")"
volume_lines=(
  "      - type: bind"
  "        source: ${workspace_mount_source_yaml}"
  "        target: \"${workspace_mount_target}\""
)
if [ "$parent_layout" = true ]; then
  volume_lines+=(
    "      - type: bind"
    '        source: "${HOME}/.zshrc"'
    '        target: "/etc/project-template/zsh/.zshrc"'
    "        read_only: true"
  )
fi
if [ "$parent_environment_enabled" = true ]; then
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

gpu_mode="disabled"
gpu_notice="default-profile-disabled"

environment_lines=(
  "      DEVCONTAINER_RUNTIME_MODE: \"${compose_mode}\""
  "      DEVCONTAINER_GPU_MODE: \"${gpu_mode}\""
  "      DEVCONTAINER_GPU_NOTICE: \"${gpu_notice}\""
  "      AGENT_CANON_SECRET_MOUNT: \"${secret_target}\""
  "      AGENT_CANON_SECRET_DIR_MODE: \"${secret_mode}\""
  "      AGENT_CANON_DEPENDENCY_PROFILE: \"${dependency_profile}\""
  "      AGENT_CANON_WORKSPACE_LAYOUT: \"${workspace_layout}\""
  '      AGENT_CANON_WORKSPACE_ROOT: "/workspace"'
  "      AGENT_CANON_REPOSITORY_ROOT: \"${container_repo_root}\""
  "${pack_environment_lines[@]}"
)
if [ "$parent_layout" = true ]; then
  environment_lines=(
    '      ZDOTDIR: "/etc/project-template/zsh"'
    "      SHELL: \"${runtime_shell}\""
    "${environment_lines[@]}"
  )
fi
if [ -n "${SSH_AUTH_SOCK:-}" ] && [ -S "${SSH_AUTH_SOCK}" ]; then
  environment_lines+=('      SSH_AUTH_SOCK: "/ssh-agent"')
fi
mkdir -p "$(dirname "$compose_output")"

{
  printf 'name: %s\n' "$compose_project_name"
  printf 'services:\n'
  printf '  workspace:\n'
  if [ "$compose_mode" = "repo-docker-pack" ]; then
    printf '    build:\n'
    printf '      context: ..\n'
    printf '      dockerfile: %s\n' "$dockerfile"
  else
    printf '    image: ubuntu:22.04\n'
  fi
  printf '    working_dir: %s\n' "$container_repo_root"
  printf '    volumes:\n'
  printf '%s\n' "${volume_lines[@]}"
  printf '    command: %s -lc "sleep infinity"\n' "$runtime_shell"
  printf '    tty: true\n'
  printf '    init: true\n'
  printf '    environment:\n'
  printf '%s\n' "${environment_lines[@]}"
} > "$compose_output"


printf 'devcontainer runtime generated: name=%s layout=%s gpu=%s mode=%s network=auto secret_mount=%s pack=%s\n' "$compose_project_name" "$workspace_layout" "$gpu_mode" "$compose_mode" "$secret_mount_status" "$pack"
