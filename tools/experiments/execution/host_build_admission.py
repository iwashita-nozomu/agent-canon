#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Admits host compiler/linker work through one bound Docker daemon, a shared host lease, effective cgroup limits, and durable lifecycle evidence.
# upstream design ../../../documents/experiments/host-build-admission.md host build admission and interruption contract
# upstream implementation ./execution_resource_plan.py canonical shared host runtime and lock namespace
# downstream implementation ../../../tests/tools/test_host_build_admission.py fixture-only admission and failure validation
# @dependency-end

"""Host build admission; Docker owns the process tree and kernel resource limits.

This is not a model/build implementation or a replacement GPU/experiment runner.
The image and build argv belong to the consumer. No daemon is started, no image
is built or pulled, and there is no unbounded host or alternate-daemon fallback.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


class AdmissionError(RuntimeError):
    """A failed observation or precondition, never permission to change route."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BuildRequest:
    image: str
    docker_host: str
    daemon_id: str
    source_root: str
    argv: tuple[str, ...]
    jobs: int
    compiler_peak_bytes: int
    linker_peak_bytes: int
    overhead_bytes: int
    memory_bytes: int
    cpu_count: int
    pids_limit: int
    host_reserve_bytes: int
    timeout_seconds: int
    rerun_authorized: bool
    estimate_basis: str

    def validate(self) -> tuple[str, ...]:
        if self.rerun_authorized is not True:
            raise AdmissionError("workload_execution_not_authorized")
        if not isinstance(self.estimate_basis, str) or not self.estimate_basis.strip():
            raise AdmissionError("documented_estimate_basis_required")
        for name in ("jobs", "compiler_peak_bytes", "linker_peak_bytes", "overhead_bytes",
                     "memory_bytes", "cpu_count", "pids_limit", "host_reserve_bytes",
                     "timeout_seconds"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise AdmissionError(f"invalid_{name}")
        if not all(isinstance(v, str) and v and "\x00" not in v
                   for v in (self.image, self.docker_host, self.daemon_id, self.source_root)):
            raise AdmissionError("invalid_environment_identity")
        if not re.fullmatch(r".+@sha256:[0-9a-f]{64}|sha256:[0-9a-f]{64}", self.image):
            raise AdmissionError("immutable_image_required")
        if not self.docker_host.startswith("unix:///"):
            raise AdmissionError("local_designated_daemon_required")
        if self.jobs > self.pids_limit or self.jobs > self.cpu_count:
            raise AdmissionError("parallelism_exceeds_cpu_or_pids_budget")
        if self.overhead_bytes + self.jobs * max(self.compiler_peak_bytes, self.linker_peak_bytes) > self.memory_bytes:
            raise AdmissionError("parallelism_exceeds_memory_budget")
        if type(self.argv) is not tuple or not self.argv or not all(isinstance(v, str) and v and "\x00" not in v for v in self.argv):
            raise AdmissionError("build_argv_required")
        command = Path(self.argv[0]).name
        # The request's jobs field is the only outer-build parallelism setting.
        if any(re.match(r"^(?:-j|--jobs(?:=|$)|--parallel(?:=|$))", arg) for arg in self.argv[1:]):
            raise AdmissionError("parallelism_must_come_from_plan")
        if command == "cmake":
            if len(self.argv) < 3 or self.argv[1] != "--build" or "--" in self.argv[2:]:
                raise AdmissionError("cmake_build_argv_required")
            return (*self.argv, "--parallel", str(self.jobs))
        if command in {"make", "gmake", "ninja"}:
            return (*self.argv, "-j", str(self.jobs))
        if re.fullmatch(r"(?:clang(?:\+\+)?|gcc|g\+\+|cc|c\+\+|ld(?:\.lld)?|lld)(?:-[0-9]+)?", command):
            if self.jobs != 1:
                raise AdmissionError("direct_compiler_requires_one_job")
            return tuple(self.argv)
        raise AdmissionError("unsupported_build_entrypoint")


@dataclass(frozen=True)
class HostPaths:
    runtime: Path
    locks: Path
    proc: Path = Path("/proc")
    cgroup: Path = Path("/sys/fs/cgroup")


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_new(path: Path, data: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _sync_directory(path.parent)


def _mount(path: Path, proc: Path) -> tuple[str, str]:
    matches = []
    for line in (proc / "self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        fields = left.split()
        mountpoint = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4]))
        if path == mountpoint or mountpoint in path.parents:
            matches.append((len(mountpoint.parts), right.split()[0], fields[3]))
    if not matches:
        raise AdmissionError("mount_identity_unreadable")
    _, filesystem, root = max(matches)
    return filesystem, root


def _persistent_directory(path: Path, proc: Path) -> None:
    if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_dir():
        raise AdmissionError("canonical_host_directory_required")
    if path.stat().st_mode & stat.S_IWOTH:
        raise AdmissionError("unsafe_host_directory")
    # Local durable filesystems only: neither tmpfs nor a container overlay is
    # evidence that the directory survives host/container restart.
    if _mount(path, proc)[0] not in {"ext4", "xfs", "btrfs", "zfs"}:
        raise AdmissionError("persistent_host_filesystem_required")


class HostLease:
    """One stable flock plus an unresolved-run marker across all build sessions.

    Serial admission avoids a second resource allocator. The marker is retained
    if the observer dies: flock auto-release alone cannot prove child quiescence.
    The lock inode is never unlinked.
    """

    def __init__(self, root: Path):
        self.root = root
        self.fd: int | None = None
        self.marker = root / "host-build-active.json"

    def __enter__(self) -> HostLease:
        self.fd = os.open(self.root / "host-build.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise AdmissionError("host_build_busy") from error
            if self.marker.exists() or self.marker.is_symlink():
                raise AdmissionError("unresolved_host_build_lease")
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise
        return self

    def reserve(self, record: dict[str, Any]) -> None:
        _write_new(self.marker, json.dumps(record, sort_keys=True) + "\n")

    def release_proven_quiescent(self) -> None:
        self.marker.unlink()
        _sync_directory(self.root)

    def __exit__(self, *_: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class Journal:
    """Append-only host events, made durable before each control transition."""

    def __init__(self, directory: Path):
        self.path = directory / "events.jsonl"
        self.handle = self.path.open("x", encoding="utf-8")
        os.chmod(self.path, 0o600)
        _sync_directory(directory)

    def emit(self, event: str, **fields: Any) -> None:
        row = {"event": event, "time": datetime.now(timezone.utc).isoformat(), **fields}
        self.handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def close(self) -> None:
        self.handle.close()


def read_result(path: Path) -> dict[str, Any]:
    """Post-run readback: a missing or torn terminal event proves no outcome."""
    try:
        first = terminal = None
        end_count = 0
        # Bound memory by one event, not the length of a long-lived run log.
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.endswith("\n"):
                    raise ValueError("torn event")
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("invalid event")
                if first is None:
                    first = row
                terminal = row
                end_count += row.get("event") == "end"
        if (first is None or terminal is None or first.get("event") != "start"
                or terminal.get("event") != "end" or end_count != 1):
            raise ValueError("no complete terminal record")
        if (not isinstance(first.get("run_id"), str)
                or terminal.get("run_id") != first["run_id"]
                or terminal.get("status") not in {"ok", "failed"}
                or not isinstance(terminal.get("reason"), str)
                or "exit_code" not in terminal
                or (terminal["exit_code"] is not None and type(terminal["exit_code"]) is not int)
                or (terminal["status"] == "ok" and
                    (terminal["exit_code"] != 0 or terminal["reason"] != "completed"))):
            raise ValueError("invalid terminal record")
        return terminal
    except (OSError, ValueError, AttributeError, TypeError):
        return {"status": "interrupted", "exit_code": None, "oom": "unknown"}


def host_observation(paths: HostPaths) -> dict[str, Any]:
    memory = {}
    for line in (paths.proc / "meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            number, unit = value.split()
            if unit != "kB" or not number.isdecimal():
                raise AdmissionError("host_memory_unreadable")
            memory[key] = int(number) * 1024
    if set(memory) != {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
        raise AdmissionError("host_memory_unreadable")
    if not (0 <= memory["MemAvailable"] <= memory["MemTotal"] and 0 <= memory["SwapFree"] <= memory["SwapTotal"]):
        raise AdmissionError("host_memory_invalid")
    pressure = (paths.proc / "pressure/memory").read_text().strip()
    if not pressure:
        raise AdmissionError("host_pressure_unreadable")
    kinds = set()
    for line in pressure.splitlines():
        kind, *fields = line.split()
        values = dict(field.split("=", 1) for field in fields)
        if kind in kinds or kind not in {"some", "full"} or len(fields) != 4 or set(values) != {"avg10", "avg60", "avg300", "total"}:
            raise AdmissionError("host_pressure_unreadable")
        if (not values["total"].isdecimal() or
                any(not math.isfinite(float(values[k])) or not 0 <= float(values[k]) <= 100
                    for k in ("avg10", "avg60", "avg300"))):
            raise AdmissionError("host_pressure_unreadable")
        kinds.add(kind)
    if kinds != {"some", "full"}:
        raise AdmissionError("host_pressure_unreadable")
    return {"memory_bytes": memory, "memory_pressure": pressure}


def _finite_limit(value: str, code: str) -> int:
    if not value.isdecimal() or int(value) <= 0:
        raise AdmissionError(code)
    return int(value)


def effective_limits(paths: HostPaths, pid: int, request: BuildRequest) -> dict[str, Any]:
    if type(pid) is not int or pid <= 0:
        raise AdmissionError("container_pid_unreadable")
    if _mount(paths.cgroup, paths.proc) != ("cgroup2", "/"):
        raise AdmissionError("host_cgroup_v2_mount_required")
    lines = (paths.proc / str(pid) / "cgroup").read_text().splitlines()
    unified = [line[3:] for line in lines if line.startswith("0::")]
    if len(unified) != 1 or not unified[0].startswith("/"):
        raise AdmissionError("container_cgroup_unreadable")
    group = paths.cgroup / unified[0].lstrip("/")
    if group == paths.cgroup or group.resolve(strict=True) != group or paths.cgroup not in group.parents:
        raise AdmissionError("dedicated_container_cgroup_required")
    controllers = set((group / "cgroup.controllers").read_text().split())
    if not {"cpu", "memory", "pids"} <= controllers:
        raise AdmissionError("controllers_not_delegated")
    if pid not in map(int, (group / "cgroup.procs").read_text().split()):
        raise AdmissionError("container_cgroup_membership_changed")
    memory = _finite_limit((group / "memory.max").read_text().strip(), "finite_memory_limit_required")
    pids = _finite_limit((group / "pids.max").read_text().strip(), "finite_pids_limit_required")
    quota, period = (group / "cpu.max").read_text().split()
    cpu = _finite_limit(quota, "finite_cpu_limit_required") / _finite_limit(period, "invalid_cpu_period")
    swap = (group / "memory.swap.max").read_text().strip()
    if memory > request.memory_bytes or pids > request.pids_limit or cpu > request.cpu_count or swap != "0":
        raise AdmissionError("effective_limits_exceed_plan")
    required = request.overhead_bytes + request.jobs * max(request.compiler_peak_bytes, request.linker_peak_bytes)
    # Ancestors may only tighten limits, but a tighter memory ancestor can make
    # the declared build budget infeasible. Never confuse the leaf request with
    # the amount available to this subtree.
    ancestor = group.parent
    effective_memory = memory
    while ancestor != paths.cgroup:
        limit = (ancestor / "memory.max").read_text().strip()
        if limit != "max":
            effective_memory = min(effective_memory, _finite_limit(limit, "invalid_ancestor_memory_limit"))
        ancestor = ancestor.parent
    if required > effective_memory:
        raise AdmissionError("effective_memory_below_build_budget")
    current = {}
    for key, filename in (("memory_current", "memory.current"), ("swap_current", "memory.swap.current")):
        value = (group / filename).read_text().strip()
        if not value.isdecimal():
            raise AdmissionError("cgroup_usage_unreadable")
        current[key] = int(value)
    # PID plus start time is an identity; a recycled integer PID is not.
    process_stat = (paths.proc / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
    start_time = _finite_limit(process_stat[19], "container_start_identity_unreadable")
    identity = group.stat()
    return {"cgroup": str(group), "device": identity.st_dev, "inode": identity.st_ino,
            "memory_max": memory, "effective_memory_max": effective_memory,
            "cpu_count": cpu, "pids_max": pids, "swap_max": 0,
            "pid": pid, "process_start_time": start_time, **current}


class Docker:
    """Bounded requests to the one designated, already-running local daemon."""

    def __init__(self, request: BuildRequest):
        self.request = request

    def call(self, *argv: str) -> str:
        env = {key: value for key, value in os.environ.items() if not key.startswith("DOCKER_")}
        result = subprocess.run(["docker", "--host", self.request.docker_host, *argv],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=5, check=False, env=env)
        if result.returncode:
            raise AdmissionError(f"docker_{argv[0]}_failed")
        return result.stdout.strip()

    def verify(self) -> None:
        info = json.loads(self.call("info", "--format", "{{json .}}"))
        if info.get("ID") != self.request.daemon_id:
            raise AdmissionError("designated_daemon_changed")
        if info.get("CgroupDriver") not in {"systemd", "cgroupfs"} or str(info.get("CgroupVersion")) != "2":
            raise AdmissionError("effective_cgroup_driver_required")

    def inspect(self, identity: str, run_id: str) -> dict[str, Any]:
        rows = json.loads(self.call("container", "inspect", identity))
        if len(rows) != 1 or rows[0]["Config"].get("Labels", {}).get("agent-canon.host-build") != run_id:
            raise AdmissionError("container_ownership_mismatch")
        row = rows[0]
        if (not re.fullmatch(r"[0-9a-f]{64}", row["Id"])
                or (re.fullmatch(r"[0-9a-f]{64}", identity) and row["Id"] != identity)):
            raise AdmissionError("container_identity_unreadable")
        if (type(row["State"].get("Running")) is not bool
                or type(row["State"].get("OOMKilled")) is not bool):
            raise AdmissionError("container_state_unreadable")
        return row


# timeout is PID 1, outside the build process tree. It remains present when the
# host observer or interactive client disappears. A PID-namespace teardown
# contains descendants even if a build starts a new process group/session.
_GATE = 'while [ ! -f /agent-canon-gate/GO ]; do sleep 0.1; done; exec "$@" > /agent-canon-output/stdout.log 2> /agent-canon-output/stderr.log'


def container_argv(request: BuildRequest, run_id: str, directory: Path, argv: tuple[str, ...]) -> tuple[str, ...]:
    return ("create", "--pull=never", "--name", f"agent-canon-host-build-{run_id}",
            "--label", f"agent-canon.host-build={run_id}", "--network=none",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cgroupns=private",
            "--memory", str(request.memory_bytes), "--memory-swap", str(request.memory_bytes),
            "--cpus", str(request.cpu_count), "--pids-limit", str(request.pids_limit),
            "--mount", f"type=bind,src={request.source_root},dst=/workspace",
            "--mount", f"type=bind,src={directory / 'gate'},dst=/agent-canon-gate,readonly",
            "--mount", f"type=bind,src={directory / 'output'},dst=/agent-canon-output",
            "--workdir", "/workspace", "--env", "MAKEFLAGS=", "--env", "MFLAGS=",
            "--env", f"CMAKE_BUILD_PARALLEL_LEVEL={request.jobs}",
            "--entrypoint", "timeout", request.image, "--signal=TERM", "--kill-after=5s",
            f"{request.timeout_seconds}s", "sh", "-c", _GATE, "agent-canon-host-build", *argv)


def _cgroup_quiescent(paths: HostPaths, limits: dict[str, Any]) -> bool:
    if (_mount(paths.cgroup, paths.proc) != ("cgroup2", "/")
            or paths.cgroup.stat().st_dev != limits["device"]):
        raise AdmissionError("quiescence_cgroup_mount_unreadable")
    group = Path(limits["cgroup"])
    try:
        identity = group.stat()
    except FileNotFoundError:
        # A kernel cgroup can be removed only after its live processes leave.
        return True
    if (identity.st_dev, identity.st_ino) != (limits["device"], limits["inode"]):
        raise AdmissionError("quiescence_cgroup_identity_changed")
    events = dict(line.split() for line in (group / "cgroup.events").read_text().splitlines())
    if events.get("populated") not in {"0", "1"}:
        raise AdmissionError("cgroup_quiescence_unreadable")
    return events["populated"] == "0"


def _sync_outputs(directory: Path) -> None:
    for output in (directory / "output").iterdir():
        if output.name in {"stdout.log", "stderr.log"}:
            fd = os.open(output, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    _sync_directory(directory / "output")


def execute(request: BuildRequest, paths: HostPaths) -> dict[str, Any]:
    argv = request.validate()
    _persistent_directory(paths.runtime, paths.proc)
    _persistent_directory(paths.locks, paths.proc)
    source = Path(request.source_root)
    if (not source.is_absolute() or source.resolve(strict=True) != source or not source.is_dir()
            or not (source / ".git").exists() or "," in str(source)
            or source == paths.runtime or source in paths.runtime.parents or paths.runtime in source.parents):
        raise AdmissionError("exact_consumer_checkout_required")
    run_id = uuid.uuid4().hex
    runs = paths.runtime / "host-builds"
    runs.mkdir(mode=0o700, exist_ok=True)
    _persistent_directory(runs, paths.proc)
    directory = runs / run_id
    directory.mkdir(mode=0o700)
    for child in ("gate", "output"):
        (directory / child).mkdir(mode=0o700)
    _sync_directory(runs)
    journal = Journal(directory)
    docker = Docker(request)
    try:
        journal.emit("start", run_id=run_id, request=asdict(request), argv=argv)
        with HostLease(paths.locks) as lease:
            lease.reserve({"run_id": run_id, "events": str(journal.path),
                           "docker_host": request.docker_host, "daemon_id": request.daemon_id,
                           "container_name": f"agent-canon-host-build-{run_id}"})
            cid: str | None = None
            container_attempted = False
            reason = "completed"
            exit_code: int | None = None
            state: dict[str, Any] = {}
            quiescent = True
            frozen: dict[str, Any] | None = None
            try:
                docker.verify()
                host = host_observation(paths)
                if host["memory_bytes"]["MemAvailable"] < request.memory_bytes + request.host_reserve_bytes:
                    raise AdmissionError("host_memory_budget_unavailable")
                journal.emit("admission", host=host, reserved_memory=request.memory_bytes)
                container_attempted = True
                quiescent = False
                created = docker.call(*container_argv(request, run_id, directory, argv))
                if not re.fullmatch(r"[0-9a-f]{64}", created):
                    raise AdmissionError("container_identity_unreadable")
                cid = created
                journal.emit("container_created", container_id=cid)
                started = time.monotonic()
                docker.call("start", cid)
                row = docker.inspect(cid, run_id)
                if not row["State"]["Running"]:
                    raise AdmissionError("bounded_environment_start_failed")
                if "GNU coreutils" not in docker.call("exec", cid, "timeout", "--version"):
                    raise AdmissionError("independent_timeout_unverified")
                limits = effective_limits(paths, row["State"]["Pid"], request)
                frozen = {key: limits[key] for key in ("cgroup", "device", "inode", "memory_max", "effective_memory_max", "cpu_count", "pids_max", "swap_max", "pid", "process_start_time")}
                docker.verify()
                host = host_observation(paths)
                if host["memory_bytes"]["MemAvailable"] < request.memory_bytes + request.host_reserve_bytes:
                    raise AdmissionError("host_memory_changed_before_launch")
                row = docker.inspect(cid, run_id)
                limits = effective_limits(paths, row["State"]["Pid"], request)
                if not row["State"]["Running"] or any(limits[key] != value for key, value in frozen.items()):
                    raise AdmissionError("bounded_environment_changed_before_launch")
                if time.monotonic() - started >= request.timeout_seconds:
                    raise AdmissionError("timeout_before_launch")
                journal.emit("admitted", container_id=cid, pid=row["State"]["Pid"], effective_limits=limits, host=host)
                _write_new(directory / "gate/GO", "admitted\n")
                while True:
                    row = docker.inspect(cid, run_id)
                    state = row["State"]
                    if not state["Running"]:
                        quiescent = True
                        exit_code = state.get("ExitCode")
                        if type(exit_code) is not int:
                            raise AdmissionError("exit_code_unreadable")
                        break
                    if time.monotonic() - started >= request.timeout_seconds:
                        raise AdmissionError("timeout")
                    docker.verify()
                    limits = effective_limits(paths, state["Pid"], request)
                    if any(limits[key] != value for key, value in frozen.items()):
                        raise AdmissionError("effective_limits_changed")
                    host = host_observation(paths)
                    journal.emit("sample", pid=state["Pid"], effective_limits=limits, host=host)
                    _sync_outputs(directory)
                    if host["memory_bytes"]["MemAvailable"] < request.host_reserve_bytes:
                        raise AdmissionError("host_reserve_exhausted")
                    time.sleep(0.2)
            except (Exception, KeyboardInterrupt) as error:
                reason = error.code if isinstance(error, AdmissionError) else type(error).__name__
                if container_attempted:
                    # A create/start timeout is ambiguous. Resolve ONLY our
                    # unique name and ownership label on the designated daemon.
                    try:
                        docker.verify()
                        row = docker.inspect(cid or f"agent-canon-host-build-{run_id}", run_id)
                        cid = row["Id"]
                        if row["State"]["Running"]:
                            try:
                                docker.call("kill", "--signal=KILL", cid)
                            finally:
                                row = docker.inspect(cid, run_id)
                        state = row["State"]
                        quiescent = not state["Running"]
                        exit_code = state.get("ExitCode") if quiescent else None
                    except Exception:
                        quiescent = False
                journal.emit("stop", reason=reason, container_id=cid, quiescent=quiescent, exit_code=exit_code)
            if quiescent and frozen is not None:
                quiescent = _cgroup_quiescent(paths, frozen)
            if not quiescent:
                journal.emit("stop", reason="container_quiescence_unverified", container_id=cid,
                             quiescent=False, exit_code=exit_code)
                # No terminal event and no lease removal: recovery must prove
                # exact-container quiescence, not infer it from observer death.
                raise AdmissionError("container_quiescence_unverified")
            _sync_outputs(directory)
            if cid is not None:
                docker.call("rm", cid)
            if reason == "completed" and state.get("OOMKilled") is True:
                reason = "container_oom_reported"
            status = "ok" if reason == "completed" and exit_code == 0 else "failed"
            result = {"status": status, "reason": reason, "exit_code": exit_code,
                      "container_oom_reported": state.get("OOMKilled"), "run_id": run_id,
                      "events": str(journal.path)}
            journal.emit("end", **result)
            lease.release_proven_quiescent()
            return result
    except AdmissionError as error:
        if error.code not in {"host_build_busy", "unresolved_host_build_lease"}:
            raise
        result = {"status": "failed", "reason": error.code, "exit_code": None,
                  "run_id": run_id, "events": str(journal.path)}
        journal.emit("end", **result)
        return result
    finally:
        journal.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--request", type=Path, help="consumer-owned JSON build request")
    group.add_argument("--result", type=Path, help="read-only post-run events.jsonl readback")
    args = parser.parse_args(argv)
    if args.result is not None:
        result = read_result(args.result)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("status") == "ok" else 125
    # Reuse the existing resource owner's namespace, never a per-task, /tmp,
    # environment-variable, HOME, or alternate-daemon fallback.
    if __package__ in {None, ""}:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from tools.experiments.execution.execution_resource_plan import HOST_RUNTIME_ROOT, LOCK_ROOT

    def interrupted(_signum: int, _frame: object) -> None:
        raise InterruptedError("observer_interrupted")

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        data = json.loads(args.request.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("argv"), list):
            raise AdmissionError("invalid_build_request")
        data["argv"] = tuple(data["argv"])
        result = execute(BuildRequest(**data), HostPaths(Path(HOST_RUNTIME_ROOT), Path(LOCK_ROOT)))
        print(json.dumps(result, sort_keys=True))
        if result["status"] == "ok":
            return 0
        code = result["exit_code"]
        return code if type(code) is int and 0 < code < 256 else 125
    except (Exception, KeyboardInterrupt) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}), file=sys.stderr)
        return 125
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
