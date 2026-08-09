#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Renders shared devcontainer compose from repo-local Docker pack and the host process identity.
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
if [[ "$(basename "$workspace_root")" == workspace-* \
  && "$(basename "$workspace_parent")" != "workspace" ]]; then
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
if [[ "${PROJECT_UID+x}" = "x" || "${PROJECT_GID+x}" = "x" ]]; then
  printf 'DEVCONTAINER_IDENTITY_ERROR=PROJECT_IDS_OVERRIDE_FORBIDDEN:canonical=host-process-identity\n' >&2
  exit 1
fi
project_user="project"
project_uid="$(id -u)"
project_gid="$(id -g)"
if [[ ! "$project_uid" =~ ^[1-9][0-9]*$ || ! "$project_gid" =~ ^[1-9][0-9]*$ ]]; then
  printf 'DEVCONTAINER_IDENTITY_ERROR=PROJECT_IDS_MUST_BE_POSITIVE_DECIMAL:uid=%s:gid=%s\n' "$project_uid" "$project_gid" >&2
  exit 1
fi
project_home="/home/${project_user}"
gpu_profile="${AGENT_CANON_GPU_ADMISSION_PROFILE:-default}"
case "$gpu_profile" in
  default|gpu-admission) ;;
  *)
    printf 'devcontainer GPU admission profile is unsupported: %s\n' "$gpu_profile" >&2
    exit 1
    ;;
esac
pack_name="default"
if [ "$gpu_profile" = "gpu-admission" ]; then
  pack_name="gpu-admission"
fi
pack="${repo_root}/docker/packs/${pack_name}.toml"
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
    python3 - "$pack" "$repo_root" <<'PY'
from __future__ import annotations

import base64
import json
import sys
import re
from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

pack_path = sys.argv[1]
repo_root = Path(sys.argv[2])
with open(pack_path, "rb") as handle:
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
known_optional_profiles = {
    "host-zshrc",
    "host-git",
    "host-secrets",
    "host-credentials",
    "ssh-agent",
    "docker-host",
    "linked-data-roots",
}
optional_mount_profiles = runtime.get("optional_mount_profiles", [])
if not isinstance(optional_mount_profiles, list) or not all(
    isinstance(item, str) for item in optional_mount_profiles
):
    raise SystemExit("runtime.optional_mount_profiles must be a string array")
seen_profiles = set()
for profile in optional_mount_profiles:
    if not profile or profile != profile.strip():
        raise SystemExit(
            "runtime.optional_mount_profiles cannot contain empty or whitespace entries"
        )
    if profile not in known_optional_profiles:
        raise SystemExit(
            f"runtime.optional_mount_profiles contains unknown profile: {profile}"
        )
    if profile in seen_profiles:
        raise SystemExit(
            f"runtime.optional_mount_profiles contains duplicate profile: {profile}"
        )
    seen_profiles.add(profile)
linked_data_roots_present = "linked_data_roots" in runtime
linked_data_roots = runtime.get("linked_data_roots", [])
if linked_data_roots_present and not isinstance(linked_data_roots, list):
    raise SystemExit("runtime.linked_data_roots must be an inline table array")
if ("linked-data-roots" in seen_profiles) != linked_data_roots_present:
    raise SystemExit(
        "linked-data-roots profile and linked_data_roots list must both be present or absent"
    )
if "linked-data-roots" in seen_profiles and not linked_data_roots:
    raise SystemExit("linked-data-roots profile requires a non-empty linked_data_roots list")
seen_links = set()
seen_targets = set()
linked_data_values = []
target_re = re.compile(r"/mnt/[a-z]/[^/].*\Z")
for index, item in enumerate(linked_data_roots):
    if not isinstance(item, dict) or set(item) != {"link", "target"}:
        raise SystemExit(
            f"runtime.linked_data_roots entry {index} must contain only link and target"
        )
    link = item["link"]
    target = item["target"]
    if not isinstance(link, str) or not isinstance(target, str):
        raise SystemExit(
            f"runtime.linked_data_roots entry {index} requires string link and target"
        )
    link_path = Path(link)
    if (
        not link
        or any(ord(char) < 32 for char in link)
        or link_path.is_absolute()
        or link != link_path.as_posix()
        or any(part in {"", ".", ".."} for part in link_path.parts)
        or not (repo_root / link).is_symlink()
    ):
        raise SystemExit(
            f"runtime.linked_data_roots link is not a normalized repository symlink: {link}"
        )
    target_path = Path(target)
    if (
        not target_re.fullmatch(target)
        or any(ord(char) < 32 for char in target)
        or ":" in target
        or "," in target
        or target != target_path.as_posix()
        or any(part in {"", ".", ".."} for part in target_path.parts)
        or target in {"/mnt", "/mnt/l"}
    ):
        raise SystemExit(
            f"runtime.linked_data_roots target is not a narrow /mnt/<letter> path: {target}"
        )
    if link in seen_links or target in seen_targets:
        raise SystemExit("runtime.linked_data_roots link and target values must be unique")
    seen_links.add(link)
    seen_targets.add(target)
    linked_data_values.append((link, target))
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
    "AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE",
    "AGENT_CANON_SHARED_RUNTIME_TARGET",
    "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT",
    "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT",
    "AGENT_CANON_CODEX_SESSION_ROOT",
    "AGENT_CANON_WORKSPACE_LAYOUT",
    "AGENT_CANON_WORKSPACE_ROOT",
    "AGENT_CANON_REPOSITORY_ROOT",
    "DEPENDENCY_MODULE_CONTAINER_SOURCE",
    "DEPENDENCY_MODULE_CONTAINER_TARGET",
    "PROJECT_UID",
    "PROJECT_GID",
    "PROJECT_USER",
    "HOME",
    "SHELL",
    "AGENT_CANON_CONTAINER_USER",
}
print(f"dockerfile={pack['dockerfile']}")
target = pack.get("target")
if target is not None and (
    not isinstance(target, str)
    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", target) is None
):
    raise SystemExit("pack.target must be a safe Docker build stage name")
if target is not None:
    print(f"target={target}")
print(f"runtime_shell={runtime_shell}")
print(f"dependency_profile={dependency_profile}")
print(f"platform={runtime_platform}")
print(f"workdir={runtime.get('workdir', '/workspace')}")
print(f"workspace_mount={runtime.get('workspace_mount', '/workspace')}")
for profile in optional_mount_profiles:
    print(f"optional_profile={profile}")
if linked_data_roots_present:
    print("linked_data_roots_present=1")
for link, target in linked_data_values:
    payload = json.dumps([link, target], separators=(",", ":")).encode("utf-8")
    print(f"linked_data_root_b64={base64.urlsafe_b64encode(payload).decode('ascii')}")
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
  build_target=""
  runtime_shell="/bin/bash"
  dependency_profile="full"
  runtime_platform="linux/amd64"
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_optional_mount_profiles=()
  linked_data_root_specs=()
  linked_data_roots_present=false
  pack_mounts=()
  pack_environment_lines=()
  for pack_value in "${pack_values[@]}"; do
    case "$pack_value" in
      dockerfile=*) dockerfile="${pack_value#dockerfile=}" ;;
      target=*) build_target="${pack_value#target=}" ;;
      runtime_shell=*) runtime_shell="${pack_value#runtime_shell=}" ;;
      dependency_profile=*) dependency_profile="${pack_value#dependency_profile=}" ;;
      platform=*) runtime_platform="${pack_value#platform=}" ;;
      workdir=*) workdir="${pack_value#workdir=}" ;;
      workspace_mount=*) workspace_mount="${pack_value#workspace_mount=}" ;;
      optional_profile=*) pack_optional_mount_profiles+=("${pack_value#optional_profile=}") ;;
      linked_data_roots_present=1) linked_data_roots_present=true ;;
      linked_data_root_b64=*) linked_data_root_specs+=("${pack_value#linked_data_root_b64=}") ;;
      mount=*) pack_mounts+=("${pack_value#mount=}") ;;
      ENV:*) pack_environment_lines+=("      ${pack_value#ENV:}") ;;
    esac
  done
else
  compose_mode="agent-canon-source-only"
  dockerfile=""
  build_target=""
  runtime_shell="/bin/bash"
  dependency_profile="full"
  runtime_platform="linux/amd64"
  workdir="/workspace"
  workspace_mount="/workspace"
  pack_optional_mount_profiles=()
  linked_data_root_specs=()
  linked_data_roots_present=false
  pack_mounts=()
  pack_environment_lines=()
fi

if [ "$gpu_profile" = "gpu-admission" ]; then
  if [ ! -f "$pack" ]; then
    printf 'devcontainer GPU admission profile requires pack: %s\n' "$pack" >&2
    exit 1
  fi
  if [ "$build_target" != "gpu-runtime" ]; then
    printf 'devcontainer GPU admission pack target must be gpu-runtime: %s\n' "${build_target:-missing}" >&2
    exit 1
  fi
elif [ "$build_target" = "gpu-runtime" ]; then
  printf 'devcontainer default profile rejects GPU build target: %s\n' "$build_target" >&2
  exit 1
fi

parent_layout=false
if [ -d "${repo_root}/vendor/agent-canon" ]; then
  parent_layout=true
fi

if [ "$gpu_profile" = "gpu-admission" ]; then
  compose_project_name="${compose_project_name}-gpu-admission"
  [[ "$compose_project_name" =~ ^[a-z0-9][a-z0-9_-]*-gpu-admission$ ]] || {
    printf 'devcontainer GPU admission project name is invalid: %s\n' "$compose_project_name" >&2
    exit 1
  }
fi

optional_mounts=""
env_optional_mount_profiles=()
if [[ "${AGENT_CANON_OPTIONAL_MOUNTS+x}" = "x" ]]; then
  optional_mounts_raw="$AGENT_CANON_OPTIONAL_MOUNTS"
  if [ -z "$optional_mounts_raw" ] || [[ "$optional_mounts_raw" == ,* ]] \
    || [[ "$optional_mounts_raw" == *, ]] || [[ "$optional_mounts_raw" == *",,"* ]]; then
    printf 'devcontainer optional mount profile source cannot be empty\n' >&2
    exit 1
  fi
  IFS=',' read -r -a optional_mount_values <<< "$optional_mounts_raw"
  declare -A env_optional_mount_seen=()
  for optional_mount in "${optional_mount_values[@]}"; do
    if [ -z "$optional_mount" ] || [[ "$optional_mount" =~ [[:space:]] ]]; then
      printf 'devcontainer optional mount profile source contains an empty or whitespace entry\n' >&2
      exit 1
    fi
    case "$optional_mount" in
      host-zshrc|host-git|host-secrets|host-credentials|ssh-agent|docker-host|linked-data-roots) ;;
      *)
        printf 'devcontainer optional mount profile is unsupported: %s\n' "$optional_mount" >&2
        exit 1
        ;;
    esac
    if [ -n "${env_optional_mount_seen[$optional_mount]:-}" ]; then
      printf 'devcontainer optional mount profile is duplicated: %s\n' "$optional_mount" >&2
      exit 1
    fi
    env_optional_mount_seen["$optional_mount"]=1
    env_optional_mount_profiles+=("$optional_mount")
  done
fi
declare -A optional_mount_seen=()
for optional_mount in "${pack_optional_mount_profiles[@]}" "${env_optional_mount_profiles[@]}"; do
  if [ -z "${optional_mount_seen[$optional_mount]:-}" ]; then
    optional_mount_seen["$optional_mount"]=1
    if [ -n "$optional_mounts" ]; then
      optional_mounts+=","
    fi
    optional_mounts+="$optional_mount"
  fi
done
optional_mount_enabled() {
  local requested="$1"
  case ",${optional_mounts}," in
    *,"${requested}",*) return 0 ;;
    *) return 1 ;;
  esac
}
if optional_mount_enabled linked-data-roots && [ "$linked_data_roots_present" != true ]; then
  printf 'devcontainer linked-data-roots profile requires linked_data_roots in the runtime pack\n' >&2
  exit 1
fi
if [ "$linked_data_roots_present" = true ] && ! optional_mount_enabled linked-data-roots; then
  printf 'devcontainer linked_data_roots requires the linked-data-roots profile\n' >&2
  exit 1
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
host_home="${HOME:-}"
host_zshrc_source=""
if optional_mount_enabled host-zshrc \
  && [ -n "$host_home" ] \
  && { [ -e "$host_home/.zshrc" ] || [ -L "$host_home/.zshrc" ]; }; then
  resolved_zshrc="$(realpath -e -- "$host_home/.zshrc" 2>/dev/null || true)"
  if [ -n "$resolved_zshrc" ] && [ -f "$resolved_zshrc" ]; then
    host_zshrc_source="$resolved_zshrc"
  fi
fi
if [ -n "$host_zshrc_source" ]; then
  zshrc_source_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$host_zshrc_source")"
  volume_lines+=(
    "      - type: bind"
    "        source: ${zshrc_source_yaml}"
    "        target: \"${project_home}/.zshrc\""
    "        read_only: true"
  )
fi
host_zsh_source=""
if optional_mount_enabled host-zshrc \
  && [ -n "$host_home" ] \
  && { [ -e "$host_home/.zsh" ] || [ -L "$host_home/.zsh" ]; }; then
  resolved_zsh="$(realpath -e -- "$host_home/.zsh" 2>/dev/null || true)"
  if [ -n "$resolved_zsh" ] && [ -d "$resolved_zsh" ]; then
    host_zsh_source="$resolved_zsh"
  fi
fi
if [ -n "$host_zsh_source" ]; then
  zsh_source_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$host_zsh_source")"
  volume_lines+=(
    "      - type: bind"
    "        source: ${zsh_source_yaml}"
    "        target: \"${project_home}/.zsh\""
    "        read_only: true"
  )
fi
declare -A linked_data_source_seen=()
declare -A linked_data_target_seen=()
for linked_data_root_spec in "${linked_data_root_specs[@]}"; do
  linked_data_pair="$(python3 - "$linked_data_root_spec" <<'PY'
from __future__ import annotations

import base64
import json
import sys

try:
    link, target = json.loads(
        base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8")
    )
except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid linked_data_roots payload: {exc}") from exc
print(f"{link}\t{target}")
PY
)"
  IFS=$'\t' read -r linked_data_link linked_data_target <<< "$linked_data_pair"
  linked_data_source="$(realpath -e -- "$repo_root/$linked_data_link" 2>/dev/null || true)"
  if [ -z "$linked_data_source" ] || [ ! -d "$linked_data_source" ]; then
    printf 'devcontainer linked_data_roots source must resolve to an existing directory: %s\n' "$linked_data_link" >&2
    exit 1
  fi
  if [ "$linked_data_source" != "$linked_data_target" ]; then
    printf 'devcontainer linked_data_roots target does not match resolved source: %s -> %s\n' "$linked_data_link" "$linked_data_target" >&2
    exit 1
  fi
  if [ -n "${linked_data_source_seen[$linked_data_source]:-}" ] || [ -n "${linked_data_target_seen[$linked_data_target]:-}" ]; then
    printf 'devcontainer linked_data_roots sources and targets must be unique\n' >&2
    exit 1
  fi
  linked_data_source_seen["$linked_data_source"]=1
  linked_data_target_seen["$linked_data_target"]=1
  linked_data_source_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$linked_data_source")"
  linked_data_target_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$linked_data_target")"
  volume_lines+=(
    "      - type: bind"
    "        source: ${linked_data_source_yaml}"
    "        target: ${linked_data_target_yaml}"
    "        read_only: false"
  )
done
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
if optional_mount_enabled docker-host; then
  if [ ! -S /var/run/docker.sock ]; then
    printf 'devcontainer docker-host profile requires an existing Unix socket: /var/run/docker.sock\n' >&2
    exit 1
  fi
  volume_lines+=("      - /var/run/docker.sock:/var/run/docker.sock")
fi

gpu_mode="disabled"
gpu_notice="default-profile-disabled"
runtime_route="CONTAINER_LOCAL"
runtime_bind_source=""
runtime_target="/var/lib/agent-canon/runtime"
runtime_host_source=""
provision_receipt="${runtime_target}/shared-runtime-provision.json"
readback_receipt="${runtime_target}/shared-runtime-readback.json"
if [ "$gpu_profile" = "gpu-admission" ]; then
  runtime_route="MANAGED_CONTAINER"
  runtime_bind_source="${AGENT_CANON_SHARED_RUNTIME_SOURCE:-${repo_root}/.agent-canon/runtime}"
  runtime_host_source="${AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE:-$runtime_bind_source}"
  runtime_target="${AGENT_CANON_SHARED_RUNTIME_TARGET:-/var/lib/agent-canon/runtime}"
  [ "$runtime_bind_source" = "$repo_root/.agent-canon/runtime" ] || {
    printf 'devcontainer GPU admission runtime source must be repository-local .agent-canon/runtime\n' >&2
    exit 1
  }
  [ "$runtime_host_source" = "$runtime_bind_source" ] || {
    printf 'devcontainer GPU admission host runtime source must match the bind source\n' >&2
    exit 1
  }
  [ "$runtime_target" = "/var/lib/agent-canon/runtime" ] || {
    printf 'devcontainer GPU admission runtime target must be /var/lib/agent-canon/runtime\n' >&2
    exit 1
  }
  [ "${AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT:-$runtime_bind_source/shared-runtime-provision.json}" = "$runtime_bind_source/shared-runtime-provision.json" ] || {
    printf 'devcontainer GPU admission provision receipt path is not canonical\n' >&2
    exit 1
  }
  [ "${AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT:-$runtime_bind_source/shared-runtime-readback.json}" = "$runtime_bind_source/shared-runtime-readback.json" ] || {
    printf 'devcontainer GPU admission host readback receipt path is not canonical\n' >&2
    exit 1
  }
  [ -d "$runtime_bind_source" ] || {
    printf 'devcontainer GPU admission runtime source is not provisioned: %s\n' "$runtime_bind_source" >&2
    exit 1
  }
  gpu_mode="enabled"
  gpu_notice="explicit-gpu-admission-profile"
else
  for forbidden_profile_value in \
    "${DEVCONTAINER_GPU_REQUEST:-}" \
    "${AGENT_CANON_SHARED_RUNTIME_SOURCE:-}" \
    "${AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE:-}" \
    "${AGENT_CANON_SHARED_RUNTIME_TARGET:-}" \
    "${AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT:-}" \
    "${AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT:-}"; do
    [ -z "$forbidden_profile_value" ] || {
      printf 'devcontainer GPU admission fields require the gpu-admission profile\n' >&2
      exit 1
    }
  done
fi

if [ "$gpu_profile" = "gpu-admission" ]; then
  runtime_source_yaml="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$runtime_bind_source")"
  volume_lines+=(
    "      - type: bind"
    "        source: ${runtime_source_yaml}"
    "        target: \"${runtime_target}\""
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
    "      AGENT_CANON_SHARED_RUNTIME_SOURCE: \"${runtime_target}\""
    "      AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE: \"${runtime_host_source}\""
    "      AGENT_CANON_SHARED_RUNTIME_TARGET: \"${runtime_target}\""
    "      AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT: \"${runtime_target}/shared-runtime-provision.json\""
    "      AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT: \"${runtime_target}/shared-runtime-readback.json\""
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
  fi
  if [ "$compose_mode" = "repo-docker-pack" ]; then
    printf '    build:\n'
    printf '      context: ..\n'
    printf '      dockerfile: %s\n' "$dockerfile"
    if [ -n "$build_target" ]; then
      printf '      target: %s\n' "$build_target"
    fi
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
