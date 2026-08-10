#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Owns the explicit GPU-admission devcontainer lifecycle.
# upstream design ../CONTAINER_OPERATIONS.md GPU-admission host operation and failure semantics
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md GPU-admission profile clauses
# upstream design ../documents/experiments/gpu-admission-r5-source-packet.md shared runtime receipt owner
# downstream implementation generate-runtime-compose.sh projects the profile bind and GPU request
# downstream implementation finalize-shared-runtime.sh validates the container bind and publishes readback
# downstream implementation ../tools/experiments/execution_resource_plan.py owns receipt parsing and atomic publication
# @dependency-end

set -euo pipefail

fail() {
  printf 'GPU admission opt-in failed: %s\n' "$1" >&2
  exit 1
}

[ "$#" -eq 0 ] || fail "the profile entrypoint does not accept positional overrides"
command -v devcontainer >/dev/null 2>&1 || fail "devcontainer CLI is unavailable"
command -v nvidia-smi >/dev/null 2>&1 || fail "nvidia-smi is required for the explicit profile"
nvidia-smi -L >/dev/null 2>&1 || fail "NVIDIA GPU discovery failed"

repository_root="${AGENT_CANON_ACTIVE_REPOSITORY_ROOT:-}"
if [ -z "$repository_root" ]; then
  repository_root="$(git rev-parse --show-toplevel 2>/dev/null)" || fail "repository root is unavailable"
fi
repository_root="$(cd "$repository_root" && pwd -P)"
profile_config="$repository_root/.devcontainer/gpu-admission/devcontainer.json"
profile_compose="$repository_root/.agent-canon/gpu-admission-compose.generated.yml"
[ -f "$profile_config" ] || fail "GPU-admission selector is unavailable: $profile_config"

runtime_source="$repository_root/.agent-canon/runtime"
runtime_target="/var/lib/agent-canon/runtime"
locks_root="$runtime_source/locks"
receipts_root="$runtime_source/receipts"
probe_path="$locks_root/bootstrap-probe.lock"
provision_receipt="$runtime_source/shared-runtime-provision.json"
readback_receipt="$runtime_source/shared-runtime-readback.json"
agent_canon_root="$(cd -P "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

host_uid="$(id -u)"
host_gid="$(id -g)"
[ "$host_uid" -ne 0 ] || fail "UID 0 is not a valid managed runtime identity"
[ ! -L "$repository_root/.agent-canon" ] || fail "repository runtime parent must not be a symlink"
mkdir -p "$repository_root/.agent-canon"
[ -d "$repository_root/.agent-canon" ] || fail "repository runtime parent is not a directory"

umask 0007
[ "$(umask)" = "0007" ] || fail "process umask is not exactly 0007"

ensure_directory() {
  local path="$1"
  [ ! -L "$path" ] || fail "runtime directory must not be a symlink: $path"
  mkdir -p "$path"
  [ -d "$path" ] || fail "runtime path is not a directory: $path"
  chmod 2770 "$path"
  [ "$(stat -c '%a' "$path")" = "2770" ] || fail "runtime directory mode is not 02770: $path"
}

ensure_directory "$runtime_source"
ensure_directory "$locks_root"
ensure_directory "$receipts_root"

filesystem_type="$(stat -f -c '%T' "$runtime_source")"
case "$filesystem_type" in
  btrfs|ext4|xfs) ;;
  *) fail "runtime filesystem is not btrfs, ext4, or xfs: $filesystem_type" ;;
esac

python3 - "$probe_path" "$runtime_source" <<'PY'
from __future__ import annotations

import fcntl
import os
import stat
import sys

probe_path, runtime_root = sys.argv[1:]
probe_flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
fd = os.open(probe_path, probe_flags, 0o660)
try:
    root_stat = os.stat(runtime_root, follow_symlinks=False)
    fd_stat = os.fstat(fd)
    path_stat = os.stat(probe_path, follow_symlinks=False)
    for label, candidate in (("fd", fd_stat), ("path", path_stat)):
        if not stat.S_ISREG(candidate.st_mode):
            raise OSError(f"bootstrap probe {label} is not a regular file")
        if candidate.st_dev != root_stat.st_dev:
            raise OSError(f"bootstrap probe {label} is on a different device")
        if candidate.st_ino <= 0:
            raise OSError(f"bootstrap probe {label} has no valid inode")
        if stat.S_IMODE(candidate.st_mode) != 0o660:
            raise OSError(f"bootstrap probe {label} mode is not 0660")
    if (fd_stat.st_dev, fd_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino):
        raise OSError("bootstrap probe path identity differs from opened fd")
    probe_data = b"agent-canon-shared-runtime-probe/v5\\n"
    view = memoryview(probe_data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("bootstrap probe write made no progress")
        view = view[written:]
    os.fsync(fd)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(fd, fcntl.LOCK_UN)
finally:
    os.close(fd)
PY

python3 - "$agent_canon_root" "$provision_receipt" "$runtime_source" "$runtime_target" "$host_uid" "$host_gid" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import sys

source_root, receipt_path, runtime_source, runtime_target, raw_uid, raw_gid = sys.argv[1:]
sys.path.insert(0, source_root)

from tools.experiments.execution_resource_plan import (  # noqa: E402
    write_runtime_receipt_atomic,
)

host_uid = int(raw_uid)
host_gid = int(raw_gid)
source_stat = os.stat(runtime_source, follow_symlinks=False)
payload = {
    "schema_version": "shared-runtime-provision/v1",
    "runtime_route": "MANAGED_CONTAINER",
    "host_uid": host_uid,
    "host_gid": host_gid,
    # The Compose contract carries only the primary project identity. Keep
    # the established receipt field for managed-run consumers, with no
    # supplementary-group projection or host group mutation.
    "host_supplementary_gids": (host_gid,),
    "host_umask": 0o0007,
    "bind_source_path": runtime_source,
    "bind_source_dev": source_stat.st_dev,
    "bind_source_ino": source_stat.st_ino,
}

def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")

payload["provision_fingerprint"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
write_runtime_receipt_atomic(receipt_path, payload)
PY

[ -f "$provision_receipt" ] || fail "runtime provision receipt was not published"

devcontainer_dir="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cleanup_required=0

read_profile_project_name() {
  local project_name=""
  [ -f "$profile_compose" ] || return 1
  project_name="$(awk '/^name: / {print $2; exit}' "$profile_compose")"
  [[ "$project_name" =~ ^[a-z0-9][a-z0-9_-]*-gpu-admission$ ]] || return 1
  printf '%s\n' "$project_name"
}

cleanup_profile() {
  local original_rc="$1"
  local project_name=""
  local cleanup_rc=0
  if [ ! -f "$profile_compose" ]; then
    printf 'GPU_ADMISSION_CLEANUP=skipped original_rc=%s reason=compose-missing path=%s\n' \
      "$original_rc" "$profile_compose" >&2
    return 0
  fi
  project_name="$(read_profile_project_name)" || {
    printf 'GPU_ADMISSION_CLEANUP=failed original_rc=%s reason=project-name-invalid path=%s\n' \
      "$original_rc" "$profile_compose" >&2
    return 1
  }
  if ! command -v docker >/dev/null 2>&1; then
    printf 'GPU_ADMISSION_CLEANUP=failed original_rc=%s reason=docker-cli-unavailable project=%s\n' \
      "$original_rc" "$project_name" >&2
    return 1
  fi
  docker compose \
    --project-name "$project_name" \
    --file "$profile_compose" \
    down --remove-orphans || cleanup_rc=$?
  if [ "$cleanup_rc" -ne 0 ]; then
    printf 'GPU_ADMISSION_CLEANUP=failed original_rc=%s cleanup_rc=%s project=%s compose=%s\n' \
      "$original_rc" "$cleanup_rc" "$project_name" "$profile_compose" >&2
    return "$cleanup_rc"
  fi
  printf 'GPU_ADMISSION_CLEANUP=pass original_rc=%s project=%s compose=%s\n' \
    "$original_rc" "$project_name" "$profile_compose" >&2
}

on_exit() {
  local original_rc=$?
  local cleanup_rc=0
  trap - EXIT
  set +e
  if [ "$original_rc" -ne 0 ] && [ "$cleanup_required" -eq 1 ]; then
    cleanup_profile "$original_rc" || cleanup_rc=$?
    if [ "$cleanup_rc" -ne 0 ]; then
      printf 'GPU_ADMISSION_CLEANUP_RESULT=failed original_rc=%s cleanup_rc=%s\n' \
        "$original_rc" "$cleanup_rc" >&2
    fi
  fi
  exit "$original_rc"
}
trap on_exit EXIT

export AGENT_CANON_GPU_ADMISSION_PROFILE=gpu-admission
export AGENT_CANON_RUNTIME_ROUTE=MANAGED_CONTAINER
export AGENT_CANON_SHARED_RUNTIME_SOURCE="$runtime_source"
export AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE="$runtime_source"
export AGENT_CANON_SHARED_RUNTIME_TARGET="$runtime_target"
export AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT="$provision_receipt"
export AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT="${runtime_source}/shared-runtime-readback.json"

printf 'GPU_ADMISSION_RUNTIME_PROVISION=pass source=%s target=%s provision=%s uid=%s gid=%s\n' \
  "$runtime_source" "$runtime_target" "$provision_receipt" "$host_uid" "$host_gid"

cleanup_required=1
devcontainer up \
  --workspace-folder "$repository_root" \
  --config "$profile_config"

container_repository_root="/workspace/$(basename "$repository_root")"
devcontainer exec \
  --workspace-folder "$repository_root" \
  --config "$profile_config" \
  python3 "$container_repository_root/tools/agent-canon/agent_tools/agent_canon_source_root.py" \
  exec .devcontainer/finalize-shared-runtime.sh
cleanup_required=0

printf 'GPU_ADMISSION_PROFILE=pass selector=%s compose_project_suffix=-gpu-admission runtime=%s\n' \
  "$profile_config" "$runtime_target"
