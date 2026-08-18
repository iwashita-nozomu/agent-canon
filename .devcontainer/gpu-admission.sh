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

cleanup_required=0

lifecycle_id="${AGENT_CANON_LIFECYCLE_ID:-$(python3 - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
)}"
task_id="${AGENT_CANON_TASK_ID:-gpu-admission-${host_uid}-${BASHPID}-${lifecycle_id}}"
default_project_base_name="$(python3 - "$repository_root" <<'PY'
import hashlib
import re
import sys
from pathlib import Path
root = sys.argv[1]
name = Path(root).name.casefold()
slug = re.sub(r"[^a-z0-9_-]+", "-", name).strip("-_" ) or "workspace"
digest = hashlib.sha1(root.encode("utf-8")).hexdigest()[:8]
print(f"{slug}-{digest}-devcontainer")
PY
)"
compose_project_base_name="${DEVCONTAINER_PROJECT_NAME:-$default_project_base_name}"
compose_project_name="${compose_project_base_name}-${lifecycle_id}-gpu-admission"
expected_image_tag="${AGENT_CANON_EXPECTED_IMAGE_TAG:-${compose_project_name}:task-${lifecycle_id}}"
export AGENT_CANON_LIFECYCLE_ID="$lifecycle_id"
export AGENT_CANON_TASK_ID="$task_id"
export AGENT_CANON_EXPECTED_IMAGE_TAG="$expected_image_tag"
export DEVCONTAINER_PROJECT_NAME="$compose_project_base_name"
export AGENT_CANON_EXPECTED_COMPOSE_PROJECT="$compose_project_name"
lifecycle_receipt="$repository_root/.agent-canon/container-lifecycle/gpu-admission-${lifecycle_id}.json"
export AGENT_CANON_CONTAINER_LIFECYCLE_RECEIPT="$lifecycle_receipt"

lifecycle_phase() {
  local phase="$1"
  python3 - "$agent_canon_root" "$repository_root" "$lifecycle_receipt" "$phase" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

agent_root, repository_root, receipt_path, phase = sys.argv[1:]
sys.path.insert(0, str(Path(agent_root) / "tools" / "ci"))
from container_runtime import (  # noqa: E402
    CommandDaemonClient,
    ContainerLifecycleBoundary,
    lifecycle_context,
    lifecycle_receipt_from_json,
    start_container_lifecycle,
    write_lifecycle_receipt,
)

root = Path(repository_root)
target = Path(receipt_path)
if phase == "capture":
    run = start_container_lifecycle(root, "docker", "gpu-admission")
    write_lifecycle_receipt(root, run.receipt)
    if run.receipt.state != "snapshot":
        print(f"GPU_ADMISSION_LIFECYCLE=blocked state={run.receipt.state}", file=sys.stderr)
        raise SystemExit(2)
    print(f"GPU_ADMISSION_LIFECYCLE=captured receipt={target}")
    raise SystemExit(0)

payload = json.loads(target.read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit("GPU admission lifecycle receipt is malformed")
receipt = lifecycle_receipt_from_json(payload)
boundary = ContainerLifecycleBoundary(
    receipt.context, CommandDaemonClient(receipt.context.builder, cwd=root)
)
after = boundary.snapshot()
receipt = boundary.record_create_or_pull(receipt, after, "gpu-admission")
if phase == "finish":
    if receipt.state not in {"created", "not-created"}:
        write_lifecycle_receipt(root, receipt)
        print(f"GPU_ADMISSION_LIFECYCLE=finish-blocked state={receipt.state} receipt={target}", file=sys.stderr)
        raise SystemExit(2)
    write_lifecycle_receipt(root, receipt)
    print(f"GPU_ADMISSION_LIFECYCLE=ready state={receipt.state} receipt={target}")
    raise SystemExit(0)
result = boundary.cleanup(receipt)
write_lifecycle_receipt(root, receipt)
print(
    f"GPU_ADMISSION_LIFECYCLE=cleanup state={result.state} receipt={target}",
    file=sys.stderr,
)
raise SystemExit(0 if result.state in {"cleaned", "not-created"} else 2)
PY
}

cleanup_profile() {
  local original_rc="$1"
  local cleanup_rc=0
  if [ ! -f "$lifecycle_receipt" ]; then
    printf 'GPU_ADMISSION_CLEANUP=skipped original_rc=%s reason=receipt-missing path=%s\n' \
      "$original_rc" "$lifecycle_receipt" >&2
    return 0
  fi
  lifecycle_phase cleanup || cleanup_rc=$?
  if [ "$cleanup_rc" -ne 0 ]; then
    printf 'GPU_ADMISSION_CLEANUP=failed original_rc=%s cleanup_rc=%s receipt=%s\n' \
      "$original_rc" "$cleanup_rc" "$lifecycle_receipt" >&2
    return "$cleanup_rc"
  fi
  printf 'GPU_ADMISSION_CLEANUP=pass original_rc=%s receipt=%s\n' \
    "$original_rc" "$lifecycle_receipt" >&2
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

lifecycle_phase capture
cleanup_required=1
devcontainer up \
  --workspace-folder "$repository_root" \
  --config "$profile_config"
[ -f "$profile_compose" ] || fail "GPU-admission Compose output is missing: $profile_compose"
grep -Fqx "name: $compose_project_name" "$profile_compose" \
  || fail "GPU-admission Compose project identity does not match lifecycle"
grep -Fqx "    image: \"$expected_image_tag\"" "$profile_compose" \
  || fail "GPU-admission Compose image tag does not match lifecycle"

container_repository_root="/workspace/$(basename "$repository_root")"
devcontainer exec \
  --workspace-folder "$repository_root" \
  --config "$profile_config" \
  python3 "$container_repository_root/tools/agent-canon/agent_tools/agent_canon_source_root.py" \
  exec .devcontainer/finalize-shared-runtime.sh
finish_rc=0
lifecycle_phase finish || finish_rc=$?
cleanup_rc=0
cleanup_profile "$finish_rc" || cleanup_rc=$?
if [ "$cleanup_rc" -eq 0 ]; then
  cleanup_required=0
fi
if [ "$finish_rc" -ne 0 ]; then
  exit "$finish_rc"
fi
if [ "$cleanup_rc" -ne 0 ]; then
  printf 'GPU_ADMISSION_CLEANUP_RESULT=blocked original_rc=0 cleanup_rc=%s receipt=%s\n' \
    "$cleanup_rc" "$lifecycle_receipt" >&2
fi

printf 'GPU_ADMISSION_PROFILE=pass selector=%s compose_project_suffix=-gpu-admission runtime=%s\n' \
  "$profile_config" "$runtime_target"
