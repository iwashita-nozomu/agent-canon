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

repo_root="${AGENT_CANON_DEVCONTAINER_REPO_ROOT:-${AGENT_CANON_ACTIVE_REPOSITORY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
repo_root="$(cd "$repo_root" && pwd -P)"
workspace_root="$(cd "${repo_root}/.." && pwd -P)"
[ -d "$workspace_root" ] || {
  printf 'devcontainer workspace root is unavailable: %s\n' "$workspace_root" >&2
  exit 1
}
workspace_parent="$(cd "${workspace_root}/.." && pwd -P)"
if [[ "$(basename "$workspace_root")" == workspace-* ]]; then
  printf 'devcontainer legacy workspace root is rejected: %s\n' "$workspace_root" >&2
  exit 1
fi
is_managed_topic_root() {
  [ "$(basename "$1")" = "workspace" ]
}
if is_managed_topic_root "$workspace_parent"; then
  workspace_layout="managed-topic"
else
  workspace_layout="direct-repo"
fi
repo_basename="$(basename "$repo_root")"
container_repo_root="/workspace/${repo_basename}"
if [[ "${PROJECT_USER+x}" = "x" ]]; then
  printf 'DEVCONTAINER_IDENTITY_ERROR=PROJECT_USER_OVERRIDE_FORBIDDEN:canonical=project:received=%s\n' "$PROJECT_USER" >&2
  exit 1
fi
project_user="project"
project_uid="${PROJECT_UID:-$(id -u)}"
project_gid="${PROJECT_GID:-$(id -g)}"
if [[ ! "$project_uid" =~ ^[1-9][0-9]*$ || ! "$project_gid" =~ ^[1-9][0-9]*$ ]]; then
  printf 'DEVCONTAINER_IDENTITY_ERROR=PROJECT_IDS_MUST_BE_POSITIVE_DECIMAL:uid=%s:gid=%s\n' "$project_uid" "$project_gid" >&2
  exit 1
fi
project_home="/home/${project_user}"
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
runtime_platform = pack.get("platform", "linux/amd64")
if runtime_platform != "linux/amd64":
    raise SystemExit("pack.platform must be linux/amd64")
reserved_environment = {
    "DEVCONTAINER_RUNTIME_MODE",
    "DEVCONTAINER_GPU_MODE",
    "DEVCONTAINER_GPU_NOTICE",
    "DEVCONTAINER_GPU_REQUEST",
    "AGENT_CANON_GPU_ADMISSION_PROFILE",
    "AGENT_CANON_SECRET_MOUNT",
    "AGENT_CANON_SECRET_DIR_MODE",
    "AGENT_CANON_OPTIONAL_MOUNTS",
    "AGENT_CANON_DEPENDENCY_PROFILE",
    "AGENT_CANON_RUNTIME_ROUTE",
    "AGENT_CANON_RUNTIME_GID",
    "AGENT_CANON_HOST_SUPPLEMENTARY_GIDS",
    "AGENT_CANON_SHARED_RUNTIME_SOURCE",
    "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT",
    "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT",
    "AGENT_CANON_CODEX_SESSION_ROOT",
    "AGENT_CANON_WORKSPACE_LAYOUT",
    "AGENT_CANON_WORKSPACE_ROOT",
    "AGENT_CANON_REPOSITORY_ROOT",
    "DEPENDENCY_MODULE_CONTAINER_SOURCE",
    "DEPENDENCY_MODULE_CONTAINER_TARGET",
    "HOME",
    "SHELL",
    "AGENT_CANON_CONTAINER_USER",
}
print(f"dockerfile={pack['dockerfile']}")
print(f"runtime_shell={runtime_shell}")
print(f"dependency_profile={dependency_profile}")
print(f"platform={runtime_platform}")
print(f"workdir={runtime.get('workdir', '/workspace')}")
print(f"workspace_mount={runtime.get('workspace_mount', '/workspace')}")
for mount in runtime.get("mounts", []):
    print(f"mount={mount}")
for item in runtime.get("env", []):
    name, separator, value = str(item).partition("=")
    if separator:
        if name in reserved_environment:
            raise SystemExit(f"runtime.env cannot override reserved key: {name}")
        print(f"ENV:{name}: {json.dumps(value)}")
PY
  )"
  mapfile -t pack_values <<< "$pack_values_raw"

  compose_mode="repo-docker-pack"
  dockerfile=""
  runtime_shell="/bin/bash"
  dependency_profile="full"
  runtime_platform="linux/amd64"
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
  pack_environment_lines=()
  for pack_value in "${pack_values[@]}"; do
    case "$pack_value" in
      dockerfile=*) dockerfile="${pack_value#dockerfile=}" ;;
      runtime_shell=*) runtime_shell="${pack_value#runtime_shell=}" ;;
      dependency_profile=*) dependency_profile="${pack_value#dependency_profile=}" ;;
      platform=*) runtime_platform="${pack_value#platform=}" ;;
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
  runtime_platform="linux/amd64"
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_mounts=()
  pack_environment_lines=()
fi

parent_layout=false
if [ -d "${repo_root}/vendor/agent-canon" ]; then
  parent_layout=true
fi

gpu_profile="${AGENT_CANON_GPU_ADMISSION_PROFILE:-default}"
case "$gpu_profile" in
  default|gpu-admission) ;;
  *)
    printf 'devcontainer GPU admission profile is unsupported: %s\n' "$gpu_profile" >&2
    exit 1
    ;;
esac
if [ "$gpu_profile" = "gpu-admission" ]; then
  compose_project_name="${compose_project_name}-gpu-admission"
  [[ "$compose_project_name" =~ ^[a-z0-9][a-z0-9_-]*-gpu-admission$ ]] || {
    printf 'devcontainer GPU admission project name is invalid: %s\n' "$compose_project_name" >&2
    exit 1
  }
fi

optional_mounts=""
optional_mounts_raw="${AGENT_CANON_OPTIONAL_MOUNTS:-}"
declare -A optional_mount_seen=()
if [ -n "$optional_mounts_raw" ]; then
  IFS=',' read -r -a optional_mount_values <<< "$optional_mounts_raw"
  for optional_mount in "${optional_mount_values[@]}"; do
    case "$optional_mount" in
      host-zshrc|host-git|host-secrets|host-credentials|ssh-agent|docker-host) ;;
      shared-runtime)
        if [ "$gpu_profile" != "gpu-admission" ]; then
          printf 'devcontainer shared-runtime mount requires the gpu-admission profile\n' >&2
          exit 1
        fi
        ;;
      *)
        printf 'devcontainer optional mount profile is unsupported: %s\n' "$optional_mount" >&2
        exit 1
        ;;
    esac
    if [ -n "${optional_mount_seen[$optional_mount]:-}" ]; then
      printf 'devcontainer optional mount profile is duplicated: %s\n' "$optional_mount" >&2
      exit 1
    fi
    optional_mount_seen["$optional_mount"]=1
    if [ -n "$optional_mounts" ]; then
      optional_mounts+=","
    fi
    optional_mounts+="$optional_mount"
  done
fi
optional_mount_enabled() {
  local requested="$1"
  case ",${optional_mounts}," in
    *,"${requested}",*) return 0 ;;
    *) return 1 ;;
  esac
}

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
host_home="${HOME:-}"
if optional_mount_enabled host-zshrc \
  && [ -n "$host_home" ] \
  && [ -f "$host_home/.zshrc" ] \
  && [ ! -L "$host_home/.zshrc" ]; then
  zshrc_source_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$host_home/.zshrc")"
  volume_lines+=(
    "      - type: bind"
    "        source: ${zshrc_source_yaml}"
    "        target: \"${project_home}/.zshrc\""
    "        read_only: true"
  )
fi
for pack_mount in "${pack_mounts[@]}"; do
  printf 'devcontainer shared generator rejects raw runtime.mounts; use an explicit public mount profile: %s\n' "$pack_mount" >&2
  exit 1
done
if optional_mount_enabled host-git && [ -d /mnt/git ]; then
  volume_lines+=("      - /mnt/git:/mnt/git")
fi
secret_mount_status="disabled"
canonical_secret_target="/mnt/agent-canon-secrets"
if [ -n "${AGENT_CANON_SECRET_MOUNT:-}" ] \
  && [ "${AGENT_CANON_SECRET_MOUNT}" != "$canonical_secret_target" ]; then
  printf 'devcontainer secret target is fixed at %s; custom targets are rejected\n' "$canonical_secret_target" >&2
  exit 1
fi
secret_target="$canonical_secret_target"
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
if optional_mount_enabled host-secrets \
  && [ -n "${AGENT_CANON_SECRET_DIR:-}" ] \
  && [ "$secret_mode" != "invalid" ]; then
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
if optional_mount_enabled host-credentials \
  && [ -n "$host_home" ] \
  && [ -d "$host_home/.config/gh" ]; then
  volume_lines+=("      - ${host_home}/.config/gh:${project_home}/.config/gh:ro")
fi
if optional_mount_enabled host-credentials \
  && [ -n "$host_home" ] \
  && [ -d "$host_home/.ssh" ]; then
  volume_lines+=("      - ${host_home}/.ssh:${project_home}/.ssh:ro")
fi
if optional_mount_enabled ssh-agent \
  && [ -n "${SSH_AUTH_SOCK:-}" ] \
  && [ -S "${SSH_AUTH_SOCK}" ]; then
  volume_lines+=("      - ${SSH_AUTH_SOCK}:/ssh-agent")
fi
if optional_mount_enabled docker-host && [ -S /var/run/docker.sock ]; then
  volume_lines+=("      - /var/run/docker.sock:/var/run/docker.sock")
fi

gpu_mode="disabled"
gpu_notice="default-profile-disabled"
runtime_route="CONTAINER_LOCAL"
runtime_source=""
runtime_gid=""
host_supplementary_gids=""
provision_receipt=""
readback_receipt=""
if [ "$gpu_profile" = "gpu-admission" ]; then
  runtime_route="MANAGED_CONTAINER"
  runtime_source="${AGENT_CANON_SHARED_RUNTIME_SOURCE:-/var/lib/agent-canon/runtime}"
  runtime_gid="${AGENT_CANON_RUNTIME_GID:-}"
  host_supplementary_gids="${AGENT_CANON_HOST_SUPPLEMENTARY_GIDS:-}"
  provision_receipt="${AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT:-${runtime_source}/shared-runtime-provision.json}"
  readback_receipt="${AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT:-${runtime_source}/shared-runtime-readback.json}"
  [ "$runtime_source" = "/var/lib/agent-canon/runtime" ] || {
    printf 'devcontainer GPU admission runtime source must be /var/lib/agent-canon/runtime\n' >&2
    exit 1
  }
  [[ "$runtime_gid" =~ ^[1-9][0-9]*$ ]] || {
    printf 'devcontainer GPU admission runtime GID must be a positive decimal\n' >&2
    exit 1
  }
  [ -n "$host_supplementary_gids" ] || {
    printf 'devcontainer GPU admission host supplementary GIDs are required\n' >&2
    exit 1
  }
  read -r -a host_supplementary_gid_values <<< "$host_supplementary_gids"
  [ "${#host_supplementary_gid_values[@]}" -gt 0 ] || {
    printf 'devcontainer GPU admission host supplementary GIDs are empty\n' >&2
    exit 1
  }
  declare -A host_supplementary_gid_seen=()
  for host_gid_value in "${host_supplementary_gid_values[@]}"; do
    [[ "$host_gid_value" =~ ^[1-9][0-9]*$ ]] || {
      printf 'devcontainer GPU admission host supplementary GID is invalid: %s\n' "$host_gid_value" >&2
      exit 1
    }
    [ -z "${host_supplementary_gid_seen[$host_gid_value]:-}" ] || {
      printf 'devcontainer GPU admission host supplementary GIDs contain a duplicate: %s\n' "$host_gid_value" >&2
      exit 1
    }
    host_supplementary_gid_seen["$host_gid_value"]=1
  done
  [ -n "${host_supplementary_gid_seen[$runtime_gid]:-}" ] || {
    printf 'devcontainer GPU admission runtime GID is absent from host supplementary GIDs\n' >&2
    exit 1
  }
  [ "$provision_receipt" = "${runtime_source}/shared-runtime-provision.json" ] || {
    printf 'devcontainer GPU admission provision receipt path is not canonical\n' >&2
    exit 1
  }
  [ "$readback_receipt" = "${runtime_source}/shared-runtime-readback.json" ] || {
    printf 'devcontainer GPU admission readback receipt path is not canonical\n' >&2
    exit 1
  }
  optional_mount_enabled shared-runtime || {
    printf 'devcontainer GPU admission requires AGENT_CANON_OPTIONAL_MOUNTS=shared-runtime\n' >&2
    exit 1
  }
  gpu_mode="enabled"
  gpu_notice="explicit-gpu-admission-profile"
else
  for forbidden_profile_value in \
    "${DEVCONTAINER_GPU_REQUEST:-}" \
    "${AGENT_CANON_RUNTIME_GID:-}" \
    "${AGENT_CANON_SHARED_RUNTIME_SOURCE:-}" \
    "${AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT:-}" \
    "${AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT:-}"; do
    [ -z "$forbidden_profile_value" ] || {
      printf 'devcontainer GPU admission fields require the gpu-admission profile\n' >&2
      exit 1
    }
  done
fi

if [ "$gpu_profile" = "gpu-admission" ]; then
  runtime_source_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$runtime_source")"
  volume_lines+=(
    "      - type: bind"
    "        source: ${runtime_source_yaml}"
    '        target: "/var/lib/agent-canon/runtime"'
  )
fi

environment_lines=(
  "      DEVCONTAINER_RUNTIME_MODE: \"${compose_mode}\""
  "      DEVCONTAINER_GPU_MODE: \"${gpu_mode}\""
  "      DEVCONTAINER_GPU_NOTICE: \"${gpu_notice}\""
  "      AGENT_CANON_SECRET_MOUNT: \"${secret_target}\""
  "      AGENT_CANON_SECRET_DIR_MODE: \"${secret_mode}\""
  "      AGENT_CANON_OPTIONAL_MOUNTS: \"${optional_mounts}\""
  "      AGENT_CANON_DEPENDENCY_PROFILE: \"${dependency_profile}\""
  "      AGENT_CANON_RUNTIME_ROUTE: \"${runtime_route}\""
  "      AGENT_CANON_WORKSPACE_LAYOUT: \"${workspace_layout}\""
  "      AGENT_CANON_CODEX_SESSION_ROOT: \"${project_home}/.codex/sessions\""
  '      AGENT_CANON_WORKSPACE_ROOT: "/workspace"'
  "      AGENT_CANON_REPOSITORY_ROOT: \"${container_repo_root}\""
  "      DEPENDENCY_MODULE_CONTAINER_SOURCE: ${workspace_mount_source_yaml}"
  "      DEPENDENCY_MODULE_CONTAINER_TARGET: \"${workspace_mount_target}\""
  "${pack_environment_lines[@]}"
)
if [ "$gpu_profile" = "gpu-admission" ]; then
  environment_lines+=(
    '      DEVCONTAINER_GPU_REQUEST: "all"'
    '      AGENT_CANON_GPU_ADMISSION_PROFILE: "gpu-admission"'
    "      AGENT_CANON_RUNTIME_GID: \"${runtime_gid}\""
    "      AGENT_CANON_HOST_SUPPLEMENTARY_GIDS: \"${host_supplementary_gids}\""
    "      AGENT_CANON_SHARED_RUNTIME_SOURCE: \"${runtime_source}\""
    "      AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT: \"${provision_receipt}\""
    "      AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT: \"${readback_receipt}\""
  )
fi
if [ "$parent_layout" = true ]; then
  environment_lines=(
    "      HOME: \"${project_home}\""
    "      SHELL: \"${runtime_shell}\""
    "      AGENT_CANON_CONTAINER_USER: \"${project_user}\""
    "${environment_lines[@]}"
  )
fi
if optional_mount_enabled ssh-agent \
  && [ -n "${SSH_AUTH_SOCK:-}" ] \
  && [ -S "${SSH_AUTH_SOCK}" ]; then
  environment_lines+=('      SSH_AUTH_SOCK: "/ssh-agent"')
fi
mkdir -p "$(dirname "$compose_output")"

{
  printf 'name: %s\n' "$compose_project_name"
  printf 'services:\n'
  printf '  workspace:\n'
  printf '    platform: %s\n' "$runtime_platform"
  printf '    user: "%s:%s"\n' "$project_uid" "$project_gid"
  if [ "$gpu_profile" = "gpu-admission" ]; then
    printf '    gpus: all\n'
    printf '    group_add:\n'
    for host_gid_value in "${host_supplementary_gid_values[@]}"; do
      printf '      - "%s"\n' "$host_gid_value"
    done
  fi
  if [ "$compose_mode" = "repo-docker-pack" ]; then
    printf '    build:\n'
    printf '      context: ..\n'
    printf '      dockerfile: %s\n' "$dockerfile"
    printf '      args:\n'
    printf '        PROJECT_UID: "%s"\n' "$project_uid"
    printf '        PROJECT_GID: "%s"\n' "$project_gid"
  else
    printf '    build:\n'
    printf '      context: ..\n'
    printf '      dockerfile: .devcontainer/Dockerfile\n'
    printf '      args:\n'
    printf '        PROJECT_UID: "%s"\n' "$project_uid"
    printf '        PROJECT_GID: "%s"\n' "$project_gid"
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
