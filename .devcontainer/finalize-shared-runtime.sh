#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Reads back the container shared AgentCanon runtime namespace after Compose bind.
# upstream design ../CONTAINER_OPERATIONS.md exact shared-runtime identity and namespace contract
# upstream design ../documents/runtime/SHARED_RUNTIME_SURFACES.md shared runtime surface ownership
# upstream design ../documents/design/devcontainer/parent-devcontainer-policy.md explicit GPU-admission profile boundary
# upstream design ../documents/experiments/gpu-admission-r5-source-packet.md exact readback receipt path and owner boundary
# upstream implementation gpu-admission.sh publishes the host provision receipt
# upstream implementation ../tools/experiments/execution_resource_plan.py owns exact receipt parsing and atomic publication
# downstream implementation post-attach.sh reports the readback receipt observationally
# downstream implementation gpu-admission.sh owns the explicit container finalize lifecycle
# @dependency-end

set -euo pipefail

runtime_root="${AGENT_CANON_SHARED_RUNTIME_SOURCE:-/var/lib/agent-canon/runtime}"
host_runtime_source="${AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE:-}"
runtime_route="${AGENT_CANON_RUNTIME_ROUTE:-MANAGED_CONTAINER}"
gpu_profile="${AGENT_CANON_GPU_ADMISSION_PROFILE:-}"
provision_receipt="${AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT:-${runtime_root}/shared-runtime-provision.json}"
readback_receipt="${AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT:-${runtime_root}/shared-runtime-readback.json}"
locks_root="${runtime_root}/locks"
receipts_root="${runtime_root}/receipts"
probe_path="${locks_root}/bootstrap-probe.lock"
agent_canon_root="$(cd -P "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

fail() {
  printf 'shared runtime finalize failed: %s\n' "$1" >&2
  exit 1
}

[ "$runtime_route" = "MANAGED_CONTAINER" ] || fail "runtime route is not MANAGED_CONTAINER"
[ "$gpu_profile" = "gpu-admission" ] || fail "shared runtime finalize requires the gpu-admission entrypoint"
[ "$runtime_root" = "/var/lib/agent-canon/runtime" ] || fail "shared runtime target is not canonical"
[ -n "$host_runtime_source" ] || fail "host runtime source is missing from the profile environment"
[ "$provision_receipt" = "${runtime_root}/shared-runtime-provision.json" ] || fail "provision receipt path is not canonical"
[ "$readback_receipt" = "${runtime_root}/shared-runtime-readback.json" ] || fail "readback receipt path is not canonical"
[ -f "${agent_canon_root}/tools/experiments/execution_resource_plan.py" ] || fail "canonical runtime receipt owner is unavailable"

container_uid="$(id -u)"
container_gid="$(id -g)"
[[ "$container_uid" =~ ^[1-9][0-9]*$ ]] || fail "container UID must be a nonzero decimal"
[[ "$container_gid" =~ ^[0-9]+$ ]] || fail "container GID must be a nonnegative decimal"
container_groups="$(id -G | tr ' ' '\n' | sort -n | uniq | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
[ "$container_groups" = "$container_gid" ] || fail "container session has unexpected supplementary groups"

for directory in "$runtime_root" "$locks_root" "$receipts_root"; do
  [ ! -L "$directory" ] || fail "runtime directory must not be a symlink: $directory"
  [ -d "$directory" ] || fail "runtime directory is missing: $directory"
  [ "$(stat -c '%a' "$directory")" = "2770" ] || fail "runtime directory mode is not 02770: $directory"
done

python3 - "$agent_canon_root" "$provision_receipt" "$readback_receipt" "$runtime_root" "$probe_path" "$runtime_route" "$host_runtime_source" "$container_uid" "$container_gid" "$container_groups" <<'PY'
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import sys
import tempfile

(
    source_root,
    provision_path,
    readback_path,
    runtime_root,
    probe_path,
    runtime_route,
    host_runtime_source,
    raw_container_uid,
    raw_container_gid,
    raw_container_groups,
) = sys.argv[1:]
sys.path.insert(0, source_root)

from tools.experiments.execution_resource_plan import (  # noqa: E402
    read_shared_runtime_provision,
    write_runtime_receipt_atomic,
)

container_uid = int(raw_container_uid)
container_gid = int(raw_container_gid)
container_groups = tuple(int(value) for value in raw_container_groups.split())


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


provision = read_shared_runtime_provision(provision_path)
if provision.runtime_route != runtime_route:
    raise OSError("provision receipt route differs")
if provision.host_supplementary_gids != (provision.host_gid,):
    raise OSError("provision receipt contains non-primary group identity")
if container_groups != (container_gid,):
    raise OSError("Compose session contains supplementary groups")
if provision.host_umask != 0o0007:
    raise OSError("host provision umask is not 0007")

if provision.bind_source_path != host_runtime_source:
    raise OSError("provision source differs from the repository-local runtime source")
source_parts = tuple(part for part in host_runtime_source.split("/") if part)
if len(source_parts) < 2 or source_parts[-2:] != (".agent-canon", "runtime"):
    raise OSError("provision source is not repository-local .agent-canon/runtime")

root_stat = os.stat(runtime_root, follow_symlinks=False)
if provision.bind_source_dev != root_stat.st_dev or provision.bind_source_ino != root_stat.st_ino:
    raise OSError("provision bind source identity differs")

mount_record: tuple[int, int, str] | None = None
with open("/proc/self/mountinfo", encoding="utf-8") as mountinfo:
    for line in mountinfo:
        before_separator, _, _ = line.rstrip("\n").partition(" - ")
        fields = before_separator.split()
        if len(fields) >= 5 and fields[4] == runtime_root:
            mount_record = (int(fields[0]), int(fields[1]), fields[3])
            break
if mount_record is None:
    raise OSError("shared runtime bind target is absent from mountinfo")
mount_id, mount_parent_id, mount_root = mount_record
if mount_root != "/":
    raise OSError("shared runtime bind target mount root is not /")
namespace_inode = os.stat("/proc/self/ns/mnt", follow_symlinks=False).st_ino
if namespace_inode <= 0 or mount_id <= 0 or mount_parent_id <= 0:
    raise OSError("shared runtime namespace or mount identity is invalid")

usability_fd, usability_probe_path = tempfile.mkstemp(
    prefix=".container-usability-",
    dir=runtime_root,
)
try:
    os.fchmod(usability_fd, 0o660)
    usability_payload = b"agent-canon-shared-runtime-usability/v1\n"
    offset = 0
    while offset < len(usability_payload):
        written = os.write(usability_fd, usability_payload[offset:])
        if written <= 0:
            raise OSError("shared runtime usability probe write made no progress")
        offset += written
    os.fsync(usability_fd)
    os.lseek(usability_fd, 0, os.SEEK_SET)
    observed = os.read(usability_fd, len(usability_payload))
    if observed != usability_payload:
        raise OSError("shared runtime usability probe readback differs")
    usability_stat = os.fstat(usability_fd)
    usability_path_stat = os.stat(usability_probe_path, follow_symlinks=False)
    for label, candidate in (("fd", usability_stat), ("path", usability_path_stat)):
        if not stat.S_ISREG(candidate.st_mode):
            raise OSError(f"shared runtime usability probe {label} is not regular")
        if candidate.st_dev != root_stat.st_dev:
            raise OSError(f"shared runtime usability probe {label} is on a different device")
        if candidate.st_ino <= 0:
            raise OSError(f"shared runtime usability probe {label} has no valid inode")
        if stat.S_IMODE(candidate.st_mode) != 0o660:
            raise OSError(f"shared runtime usability probe {label} mode is not 0660")
    if (usability_stat.st_dev, usability_stat.st_ino) != (
        usability_path_stat.st_dev,
        usability_path_stat.st_ino,
    ):
        raise OSError("shared runtime usability probe path identity differs from fd")
    os.unlink(usability_probe_path)
    usability_probe_path = ""
finally:
    os.close(usability_fd)
    if usability_probe_path:
        try:
            os.unlink(usability_probe_path)
        except FileNotFoundError:
            pass

probe_fd = os.open(probe_path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
try:
    probe_descriptor = os.fstat(probe_fd)
    probe_path_stat = os.stat(probe_path, follow_symlinks=False)
    for label, candidate in (("fd", probe_descriptor), ("path", probe_path_stat)):
        if not stat.S_ISREG(candidate.st_mode):
            raise OSError(f"probe {label} is not a regular file")
        if candidate.st_dev != root_stat.st_dev:
            raise OSError(f"probe {label} is on a different device")
        if candidate.st_ino <= 0:
            raise OSError(f"probe {label} has no valid inode")
        if stat.S_IMODE(candidate.st_mode) != 0o660:
            raise OSError(f"probe {label} mode is not 0660")
    if (probe_descriptor.st_dev, probe_descriptor.st_ino) != (
        probe_path_stat.st_dev,
        probe_path_stat.st_ino,
    ):
        raise OSError("probe path identity differs from opened fd")
    fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(probe_fd, fcntl.LOCK_UN)
finally:
    os.close(probe_fd)

with open("/proc/self/status", encoding="ascii") as status_file:
    status_umask = next(
        line.split(":", 1)[1].strip()
        for line in status_file
        if line.startswith("Umask:")
    )
container_umask = int(status_umask, 8)
if container_umask != 0o0007:
    raise OSError("container umask is not 0007")

readback = {
    "schema_version": "shared-runtime-readback/v1",
    "runtime_route": runtime_route,
    "container_uid": container_uid,
    "container_gid": container_gid,
    "container_supplementary_gids": container_groups,
    "container_umask": container_umask,
    "bind_target_path": runtime_root,
    "bind_target_dev": root_stat.st_dev,
    "bind_target_ino": root_stat.st_ino,
    "namespace_inode": namespace_inode,
    "mount_id": mount_id,
    "mount_parent_id": mount_parent_id,
    "mount_root": mount_root,
    "probe_fd_disposition": "closed",
}
readback["readback_fingerprint"] = hashlib.sha256(canonical_bytes(readback)).hexdigest()
write_runtime_receipt_atomic(readback_path, readback)

published = os.stat(readback_path, follow_symlinks=False)
if not stat.S_ISREG(published.st_mode):
    raise OSError("published readback receipt is not a regular file")
if published.st_dev != root_stat.st_dev or published.st_ino <= 0:
    raise OSError("published readback receipt identity is invalid")
if stat.S_IMODE(published.st_mode) != 0o660:
    raise OSError("published readback receipt mode differs")
PY

printf 'SHARED_RUNTIME_FINALIZE=pass route=%s target=%s readback=%s uid=%s gid=%s\n' \
  "$runtime_route" "$runtime_root" "$readback_receipt" "$container_uid" "$container_gid"
printf 'AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT=%s\n' "$readback_receipt"
