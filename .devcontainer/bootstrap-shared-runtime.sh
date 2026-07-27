#!/usr/bin/env bash
# @dependency-start
# contract environment
# responsibility Provisions the host-side shared AgentCanon runtime namespace before Compose creation.
# upstream design ../CONTAINER_OPERATIONS.md exact shared-runtime identity and namespace contract
# upstream design ../documents/runtime/SHARED_RUNTIME_SURFACES.md shared runtime surface ownership
# upstream design ../documents/experiments/gpu-admission-r5-source-packet.md exact provision receipt path and owner boundary
# upstream implementation ../tools/experiments/execution_resource_plan.py owns atomic runtime receipt publication
# downstream implementation finalize-shared-runtime.sh proves the container readback
# downstream implementation generate-runtime-compose.sh renders the matching bind and identity
# @dependency-end

set -euo pipefail

runtime_root="${AGENT_CANON_SHARED_RUNTIME_SOURCE:-/var/lib/agent-canon/runtime}"
runtime_group="agent-canon-runtime"
provision_receipt="${AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT:-${runtime_root}/shared-runtime-provision.json}"
locks_root="${runtime_root}/locks"
receipts_root="${runtime_root}/receipts"
probe_path="${locks_root}/bootstrap-probe.lock"
runtime_route="MANAGED_CONTAINER"
agent_canon_root="$(cd -P "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"

fail() {
  printf 'shared runtime bootstrap failed: %s\n' "$1" >&2
  exit 1
}

umask 0007
[ "$(umask)" = "0007" ] || fail "process umask is not exactly 0007"

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    fail "root or sudo is required for $*"
  fi
}

case "$runtime_root" in
  /var/lib/agent-canon/runtime) ;;
  *) fail "shared runtime source must be /var/lib/agent-canon/runtime" ;;
esac
[ "$provision_receipt" = "${runtime_root}/shared-runtime-provision.json" ] || fail "provision receipt path is not canonical"
[ -f "${agent_canon_root}/tools/experiments/execution_resource_plan.py" ] || fail "canonical runtime receipt publisher is unavailable"

host_uid="$(id -u)"
host_gid="$(id -g)"
[ "$host_uid" -ne 0 ] || fail "UID 0 is not a valid managed runtime identity"

if ! getent group "$runtime_group" >/dev/null 2>&1; then
  run_as_root groupadd --system "$runtime_group"
fi
runtime_gid="$(getent group "$runtime_group" | cut -d: -f3)"
[ -n "$runtime_gid" ] || fail "runtime group has no numeric GID"
host_supplementary_gids="$(id -G | tr ' ' '\n' | sort -n | uniq | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
case " $host_supplementary_gids " in
  *" $runtime_gid "*) ;;
  *) fail "current session is missing runtime group ${runtime_gid}; refresh the host session and retry" ;;
esac

run_as_root install -d -m 755 /var/lib/agent-canon

ensure_directory() {
  local path="$1"
  [ ! -L "$path" ] || fail "runtime directory must not be a symlink: $path"
  if [ ! -e "$path" ]; then
    run_as_root install -d -m 2770 -o "$host_uid" -g "$runtime_gid" "$path"
    return
  fi
  [ -d "$path" ] || fail "runtime path is not a directory: $path"
  [ "$(stat -c '%a' "$path")" = "2770" ] || fail "runtime directory mode is not 02770: $path"
  [ "$(stat -c '%u' "$path")" = "$host_uid" ] || fail "runtime directory owner differs: $path"
  [ "$(stat -c '%g' "$path")" = "$runtime_gid" ] || fail "runtime directory group differs: $path"
}

ensure_directory "$runtime_root"
ensure_directory "$locks_root"
ensure_directory "$receipts_root"

filesystem_type="$(stat -f -c '%T' "$runtime_root")"
case "$filesystem_type" in
  btrfs|ext4|xfs) ;;
  *) fail "runtime filesystem is not btrfs, ext4, or xfs: $filesystem_type" ;;
esac

python3 - "$probe_path" "$runtime_root" "$runtime_gid" "$host_uid" <<'PY'
from __future__ import annotations

import fcntl
import os
import stat
import sys

probe_path, runtime_root, raw_gid, raw_uid = sys.argv[1:]
runtime_gid = int(raw_gid)
host_uid = int(raw_uid)
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
        if candidate.st_gid != runtime_gid:
            raise OSError(f"bootstrap probe {label} group differs")
        if candidate.st_uid != host_uid:
            raise OSError(f"bootstrap probe {label} owner differs")
    if (fd_stat.st_dev, fd_stat.st_ino) != (path_stat.st_dev, path_stat.st_ino):
        raise OSError("bootstrap probe path identity differs from opened fd")
    probe_data = b"agent-canon-shared-runtime-probe/v4\\n"
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
python3 - "$agent_canon_root" "$provision_receipt" "$runtime_root" "$runtime_route" "$host_uid" "$host_gid" "$host_supplementary_gids" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import sys

(
    source_root,
    receipt_path,
    runtime_root,
    route,
    raw_uid,
    raw_gid,
    raw_groups,
) = sys.argv[1:]
sys.path.insert(0, source_root)

from tools.experiments.execution_resource_plan import (  # noqa: E402
    write_runtime_receipt_atomic,
)

payload = {
    "schema_version": "shared-runtime-provision/v1",
    "runtime_route": route,
    "host_uid": int(raw_uid),
    "host_gid": int(raw_gid),
    "host_supplementary_gids": tuple(int(value) for value in raw_groups.split()),
    "host_umask": 0o0007,
    "bind_source_path": runtime_root,
    "bind_source_dev": os.stat(runtime_root, follow_symlinks=False).st_dev,
    "bind_source_ino": os.stat(runtime_root, follow_symlinks=False).st_ino,
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

printf 'SHARED_RUNTIME_BOOTSTRAP=pass route=%s source=%s provision=%s\n' "$runtime_route" "$runtime_root" "$provision_receipt"
printf 'AGENT_CANON_RUNTIME_GID=%s\n' "$runtime_gid"
printf 'AGENT_CANON_SHARED_RUNTIME_SOURCE=%s\n' "$runtime_root"
printf 'AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT=%s\n' "$provision_receipt"
