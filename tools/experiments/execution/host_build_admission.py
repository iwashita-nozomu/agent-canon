#!/usr/bin/env python3
# @dependency-start
# contract implementation
# responsibility Admits and supervises one host compiler/linker tree in the existing shared runtime namespace.
# upstream implementation ./execution_resource_plan.py owns shared runtime provenance and lock placement
# upstream design ../../../documents/experiments/host-build-admission.md host build admission and no-rerun boundary
# downstream design ../../../agents/skills/cpp-review.md routes native builds through host admission
# downstream implementation ../../../tests/tools/test_host_build_admission.py validates refusal, concurrency, supervision and interruption with fixtures
# @dependency-end
"""A bounded host-build adapter, not a scheduler or environment bootstrapper.

The caller supplies an already selected environment and delegated cgroup. This
adapter never starts Docker daemons, enables controllers, or retries a workload.
A single shared flock serializes host-heavy builds; the kernel owns containment.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import select
import stat
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterator, Protocol


MONITOR_TIMEOUT_SECONDS = 10.0


class BuildRefused(RuntimeError):
    """A machine-readable refusal; no alternative execution route is selected."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def require(condition: bool, code: str) -> None:
    if not condition:
        raise BuildRefused(code)


def integer(value: str, *, zero: bool = False) -> int:
    require(bool(re.fullmatch(r"[0-9]+", value)), "host_build_limit_unproven")
    number = int(value)
    require(number >= (0 if zero else 1), "host_build_limit_unproven")
    return number


def read(path: Path) -> str:
    with path.open(encoding="ascii") as stream:
        value = stream.read(65537)
    require(len(value) <= 65536, "host_build_observation_invalid")
    return value.strip()


def no_symlinks(path: Path) -> None:
    require(path.is_absolute() and ".." not in path.parts, "host_build_path_invalid")
    for parent in (*reversed(path.parents), path):
        require(not parent.is_symlink(), "host_build_path_invalid")


@dataclass(frozen=True)
class Budget:
    memory_bytes: int
    workers: int
    worker_memory_bytes: int
    fixed_memory_bytes: int
    reserve_bytes: int
    pids: int
    timeout_seconds: float

    def validate(self) -> None:
        for key in ("memory_bytes", "workers", "worker_memory_bytes", "reserve_bytes", "pids"):
            require(type(getattr(self, key)) is int and getattr(self, key) > 0,
                    "host_build_budget_invalid")
        require(type(self.fixed_memory_bytes) is int and self.fixed_memory_bytes >= 0,
                "host_build_budget_invalid")
        require(type(self.timeout_seconds) in (int, float)
                and math.isfinite(self.timeout_seconds) and self.timeout_seconds > 0,
                "host_build_timeout_invalid")
        require(self.workers * self.worker_memory_bytes + self.fixed_memory_bytes
                <= self.memory_bytes, "host_build_parallel_memory_exceeded")
        require(self.pids >= self.workers + 2, "host_build_pid_budget_invalid")

    def limits(self) -> dict[str, str]:
        return {"memory.max": str(self.memory_bytes), "memory.swap.max": "0",
                "cpu.max": f"{self.workers * 100000} 100000", "pids.max": str(self.pids)}


def validate_daemon(info: dict, expected_id: str) -> None:
    require(bool(expected_id) and info.get("ID") == expected_id,
            "host_build_environment_changed")
    require(info.get("CgroupDriver") in {"systemd", "cgroupfs"}
            and str(info.get("CgroupVersion")) == "2", "host_build_cgroup_disabled")


def daemon_probe(endpoint: str, expected_id: str) -> dict:
    # An explicit, selected local endpoint is mandatory. No context/default fallback.
    require(endpoint.startswith("unix:///"), "host_build_environment_unproven")
    result = subprocess.run(["docker", "--host", endpoint, "info", "--format", "{{json .}}"],
                            check=True, capture_output=True, text=True, timeout=5)
    info = json.loads(result.stdout)
    require(isinstance(info, dict), "host_build_environment_unproven")
    validate_daemon(info, expected_id)
    return {key: info[key] for key in ("ID", "CgroupDriver", "CgroupVersion")}


def pressure(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        kind, *fields = line.split()
        require(kind in {"some", "full"} and kind not in result,
                "host_build_pressure_unproven")
        values = dict(field.split("=", 1) for field in fields)
        require(set(values) == {"avg10", "avg60", "avg300", "total"},
                "host_build_pressure_unproven")
        for key in ("avg10", "avg60", "avg300"):
            number = float(values[key])
            require(math.isfinite(number) and 0 <= number <= 100,
                    "host_build_pressure_unproven")
        integer(values["total"], zero=True)
        result[kind] = values
    require(set(result) == {"some", "full"}, "host_build_pressure_unproven")
    return result


def snapshot(group: Path, proc: Path = Path("/proc")) -> dict:
    fields = {}
    for line in read(proc / "meminfo").splitlines():
        key, _, value = line.partition(":")
        if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            number, unit = value.split()
            require(unit == "kB" and key not in fields, "host_build_memory_unproven")
            fields[key] = integer(number, zero=True) * 1024
    require(set(fields) == {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
            and 0 < fields["MemTotal"] >= fields["MemAvailable"]
            and fields["SwapTotal"] >= fields["SwapFree"], "host_build_memory_unproven")
    limits = {name: read(group / name) for name in
              ("memory.max", "memory.swap.max", "cpu.max", "pids.max")}
    integer(limits["memory.max"])
    integer(limits["memory.swap.max"], zero=True)
    integer(limits["pids.max"])
    quota, period = limits["cpu.max"].split()
    integer(quota)
    integer(period)
    return {"host": fields, "limits": limits,
            "memory_current": integer(read(group / "memory.current"), zero=True),
            "swap_current": integer(read(group / "memory.swap.current"), zero=True),
            "pids_current": integer(read(group / "pids.current"), zero=True),
            "host_pressure": pressure(read(proc / "pressure/memory")),
            "group_pressure": pressure(read(group / "memory.pressure"))}


def admit(budget: Budget, observed: dict, controllers: str) -> None:
    budget.validate()
    require({"memory", "cpu", "pids"} <= set(controllers.split()),
            "host_build_controllers_not_delegated")
    limits = observed["limits"]
    available = min(observed["host"]["MemAvailable"] - budget.reserve_bytes,
                    integer(limits["memory.max"]) - observed["memory_current"])
    require(budget.memory_bytes <= available, "host_build_ram_unavailable")
    quota, period = map(integer, limits["cpu.max"].split())
    require(budget.workers * period <= quota, "host_build_cpu_unavailable")
    require(budget.pids <= integer(limits["pids.max"]) - observed["pids_current"], "host_build_pids_unavailable")


def native_argv(command: tuple[str, ...], workers: int) -> tuple[str, ...]:
    """Own parallelism, not consumer build graphs or compiler configuration."""
    require(bool(command), "host_build_command_missing")
    program = Path(command[0]).name
    require(not any(token in {"-j", "--jobs", "--parallel"}
                    or token.startswith(("-j", "--jobs=", "--parallel="))
                    for token in command[1:]), "host_build_parallelism_conflict")
    if program == "cmake":
        if len(command) >= 3 and command[1] == "--build" and "--" not in command[2:]:
            return (*command, "--parallel", str(workers))
        require(workers == 1 and "-S" in command and "-B" in command,
                "host_build_command_unsupported")
        return command  # Configure/try_compile is also contained, without an invalid --parallel flag.
    if program in {"make", "gmake", "ninja", "ninja-build"}:
        return (*command, f"-j{workers}")
    require(re.fullmatch(r"(?:clang\+\+|clang|g\+\+|gcc|c\+\+|cc|ld|ld.lld)(?:-[0-9]+)?",
                         program) is not None and workers == 1, "host_build_command_unsupported")
    return command


def mount_type(path: Path, mountinfo: str) -> tuple[str, str]:
    matches = []
    for line in mountinfo.splitlines():
        left, right = line.split(" - ", 1)
        fields = left.split()
        decode = lambda text: re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), text)
        target = Path(decode(fields[4]))
        if path == target or target in path.parents:
            matches.append((len(target.parts), right.split()[0], decode(fields[3])))
    require(bool(matches), "host_build_mount_unproven")
    _, filesystem, root = max(matches)
    return filesystem, root


def validate_placement(runtime: Path, parent: Path, mountinfo: str) -> None:
    no_symlinks(runtime)
    no_symlinks(parent)
    runtime_fs, runtime_mount_root = mount_type(runtime, mountinfo)
    require(not any(Path(p) == location or Path(p) in location.parents
                    for location in (runtime, Path(runtime_mount_root))
                    for p in ("/tmp", "/var/tmp", "/run")), "host_build_log_ephemeral")
    require(runtime_fs in {"ext4", "xfs", "btrfs", "zfs"},
            "host_build_log_not_persistent")
    filesystem, root = mount_type(parent, mountinfo)
    require(filesystem == "cgroup2" and root == "/", "host_build_cgroup_mount_unproven")
    require(Path("/sys/fs/cgroup") in parent.parents, "host_build_cgroup_path_invalid")


@contextmanager
def host_slot(runtime: Path) -> Iterator[Path]:
    """One host-wide lease; an interrupted lease is never silently recycled."""
    locks = runtime / "locks"
    no_symlinks(locks)
    descriptor = os.open(locks / "host-build.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o660)
    try:
        require(stat.S_ISREG(os.fstat(descriptor).st_mode), "host_build_lock_invalid")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BuildRefused("host_build_busy") from exc
        marker = locks / "host-build.active"
        require(not marker.exists() and not marker.is_symlink(), "host_build_interrupted")
        yield marker
    finally:
        # The durable active marker also blocks admission after parent death.
        os.close(descriptor)


class EventSink(Protocol):
    def emit(self, event: str, **fields: object) -> None: ...


class Journal:
    """Append-only private host evidence, durable before the execution gate opens."""

    def __init__(self, directory: Path):
        directory.mkdir(mode=0o700)
        self.fd = os.open(directory / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
        self.directory = directory
        sync_directory(directory)
        sync_directory(directory.parent)

    def emit(self, event: str, **fields: object) -> None:
        emit_fd(self.fd, event, **fields)

    def close(self) -> None:
        os.close(self.fd)


def emit_fd(fd: int, event: str, **fields: object) -> None:
    record = {"event": event, "time_ns": time.time_ns(), "monotonic_ns": time.monotonic_ns(), **fields}
    data = (json.dumps(record, sort_keys=True, allow_nan=False) + "\n").encode()
    require(os.write(fd, data) == len(data), "host_build_log_short_write")
    os.fsync(fd)


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def journal_status(path: Path) -> str:
    """No end event (including torn JSON) proves neither success nor OOM."""
    try:
        records = [json.loads(line) for line in path.read_text().splitlines()]
        last = records[-1]
        if last["event"] == "end":
            return "success" if last["reason"] == "exited" and last["exit_code"] == 0 else "failed"
        if last["event"] == "denied":
            return "refused"
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass
    return "interrupted"


def populated(group: Path) -> bool:
    fields = dict(line.split() for line in read(group / "cgroup.events").splitlines())
    require(fields.get("populated") in {"0", "1"}, "host_build_quiescence_unproven")
    return fields["populated"] == "1"


def watchdog(control: int, kill_fd: int, deadline: float, journal: EventSink) -> None:
    """Outlive conversation/parent loss; never perform log I/O before stopping."""
    heartbeat_deadline = time.monotonic() + MONITOR_TIMEOUT_SECONDS
    while True:
        ready, _, _ = select.select([control], [], [],
                                    max(0.0, min(deadline, heartbeat_deadline) - time.monotonic()))
        message = os.read(control, 1) if ready else b""
        if message == b"D":
            return
        if message == b"H" and time.monotonic() < deadline:
            heartbeat_deadline = time.monotonic() + MONITOR_TIMEOUT_SECONDS
            continue
        reason = ("parent_disconnected" if ready and not message else
                  "timeout" if time.monotonic() >= deadline else "monitor_stalled")
        os.write(kill_fd, b"1")  # Only the fresh child cgroup created by this run.
        journal.emit("stop", reason=reason)
        return


_GATE = "import os,sys; f=int(sys.argv[1]); b=os.read(f,1); os.close(f); b==b'1' or sys.exit(125); os.execvpe(sys.argv[2],sys.argv[2:],os.environ)"


def verify_membership(pid: int, group: Path) -> None:
    membership = read(Path(f"/proc/{pid}/cgroup"))
    require(membership == f"0::/{group.relative_to('/sys/fs/cgroup')}",
            "host_build_membership_unproven")


def supervise(command: tuple[str, ...], cwd: Path, budget: Budget, group: Path,
              marker: Path, journal: Journal, observe: Callable[[], dict]) -> int:
    """Start a gated native child, then supervise only its dedicated cgroup."""
    descriptors = []
    process = None
    watcher = None
    gate_write = None
    attached = False
    reason = "exited"
    deadline = time.monotonic() + budget.timeout_seconds
    try:
        kill_fd = os.open(group / "cgroup.kill", os.O_WRONLY | os.O_NOFOLLOW)
        descriptors.append(kill_fd)
        gate_read, gate_write = os.pipe()
        control_read, control_write = os.pipe()
        descriptors.extend((gate_read, gate_write, control_read, control_write))
        outputs = []
        for name in ("stdout.log", "stderr.log"):
            outputs.append(os.open(journal.directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            descriptors.append(outputs[-1])
        sync_directory(journal.directory)
        environment = dict(os.environ)
        for key in ("MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS", "NINJAFLAGS", "CMAKE_BUILD_PARALLEL_LEVEL"):
            environment.pop(key, None)
        environment["CMAKE_BUILD_PARALLEL_LEVEL"] = str(budget.workers)
        process = subprocess.Popen([sys.executable, "-I", "-S", "-c", _GATE, str(gate_read), *command],
                                   cwd=cwd, env=environment, pass_fds=(gate_read,), stdin=subprocess.DEVNULL,
                                   stdout=outputs[0], stderr=outputs[1], start_new_session=True)
        (group / "cgroup.procs").write_text(str(process.pid), encoding="ascii")
        attached = True
        verify_membership(process.pid, group)
        ready_read, ready_write = os.pipe()
        descriptors.extend((ready_read, ready_write))
        watcher = subprocess.Popen(
            [sys.executable, "-I", "-S", str(Path(__file__).resolve()), "--watchdog",
             str(control_read), str(kill_fd), str(deadline), str(journal.fd), str(ready_write)],
            pass_fds=(control_read, kill_fd, journal.fd, ready_write),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for descriptor in (control_read, ready_write):
            os.close(descriptor)
            descriptors.remove(descriptor)
        ready, _, _ = select.select([ready_read], [], [], min(5, max(0, deadline - time.monotonic())))
        require(bool(ready) and os.read(ready_read, 1) == b"R", "host_build_watchdog_unavailable")
        observed = observe()
        require(observed["limits"] == budget.limits(), "host_build_limits_changed")
        require(budget.memory_bytes <= observed["host"]["MemAvailable"] - budget.reserve_bytes,
                "host_build_ram_unavailable")
        require(time.monotonic() < deadline, "host_build_start_timeout")
        journal.emit("start", pid=process.pid, cgroup=str(group), command=command, effective=observed)
        os.write(gate_write, b"1")
        os.close(gate_write)
        descriptors.remove(gate_write)
        gate_write = None
        while True:
            if time.monotonic() >= deadline:
                reason = "timeout"
                break
            if watcher.poll() is not None:
                reason = "watchdog_stopped"
                break
            observed = observe()
            require(observed["limits"] == budget.limits(), "host_build_limits_changed")
            require(observed["host"]["MemAvailable"] >= budget.reserve_bytes,
                    "host_build_host_reserve_exhausted")
            journal.emit("sample", pid=process.pid, **observed)
            for descriptor in outputs:
                os.fsync(descriptor)
            os.write(control_write, b"H")
            if process.poll() is not None and not populated(group):
                break
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    except BaseException as exc:
        reason = exc.code if isinstance(exc, BuildRefused) else "monitor_failed"
    finally:
        try:
            # Release a still-gated child on failed placement, then stop before log I/O.
            if gate_write is not None:
                os.close(gate_write)
                descriptors.remove(gate_write)
            if process is not None:
                if attached:
                    os.write(kill_fd, b"1")
                else:
                    process.kill()  # Only our unreaped, never-released gate child.
                process.wait(timeout=5)
                cleanup_deadline = time.monotonic() + 5
                while populated(group) and time.monotonic() < cleanup_deadline:
                    time.sleep(0.05)
                require(not populated(group), "host_build_quiescence_unproven")
                if watcher is not None:
                    try:
                        os.write(control_write, b"D")
                    except BrokenPipeError:
                        pass
                    watcher.wait(timeout=5)
                for descriptor in outputs:
                    os.fsync(descriptor)
                journal.emit("end", reason=reason, exit_code=process.returncode, pid=process.pid)
                marker.unlink()
                sync_directory(marker.parent)
        finally:
            # A failed quiescence/log proof intentionally leaves the durable marker.
            for descriptor in descriptors:
                os.close(descriptor)
    return process.returncode if process is not None and reason == "exited" else 125


def run_build(*, command: tuple[str, ...], cwd: Path, budget: Budget, runtime: Path,
              parent: Path, endpoint: str, daemon_id: str, execution_allowed: bool,
              rerun_prohibited: bool) -> int:
    # The current request's prohibition wins, including a renamed/reduced command.
    require(execution_allowed is True and rerun_prohibited is False, "host_build_execution_prohibited")
    command = native_argv(command, budget.workers)
    budget.validate()
    validate_placement(runtime, parent, read(Path("/proc/self/mountinfo")))
    with host_slot(runtime) as marker:
        journal = Journal(runtime / f"host-build-{uuid.uuid4().hex}")
        group = parent / journal.directory.name
        try:
            journal.emit("request", command=command, cwd=str(cwd), budget=asdict(budget))
            daemon = daemon_probe(endpoint, daemon_id)
            initial = snapshot(parent)
            require(read(parent / "cgroup.type") == "domain", "host_build_cgroup_type_invalid")
            admit(budget, initial, read(parent / "cgroup.subtree_control"))
            journal.emit("admitted", daemon=daemon, initial=initial)
            # The marker survives parent death and reboot. No automatic stale recovery.
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o660)
            try:
                payload = (str(group) + "\n").encode()
                require(os.write(fd, payload) == len(payload), "host_build_marker_short_write")
                os.fsync(fd)
            finally:
                os.close(fd)
            sync_directory(marker.parent)
            group.mkdir()
            for name, value in budget.limits().items():
                (group / name).write_text(value, encoding="ascii")
            require(snapshot(group)["limits"] == budget.limits(), "host_build_limits_changed")

            def observe() -> dict:
                daemon_probe(endpoint, daemon_id)
                require(snapshot(parent)["limits"] == initial["limits"], "host_build_parent_limits_changed")
                require({"memory", "cpu", "pids"} <= set(read(parent / "cgroup.subtree_control").split()),
                        "host_build_controllers_not_delegated")
                return snapshot(group)

            return supervise(command, cwd, budget, group, marker, journal, observe)
        except BaseException as exc:
            journal.emit("denied" if not marker.exists() else "interrupted",
                         reason=exc.code if isinstance(exc, BuildRefused) else type(exc).__name__)
            raise
        finally:
            journal.close()
            if not marker.exists() and group.exists() and not populated(group):
                group.rmdir()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-cgroup", type=Path, required=True)
    parser.add_argument("--docker-host", required=True)
    parser.add_argument("--daemon-id", required=True)
    parser.add_argument("--provision-receipt", required=True)
    parser.add_argument("--readback-receipt", required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    for field in ("memory-bytes", "workers", "worker-memory-bytes", "fixed-memory-bytes", "reserve-bytes", "pids"):
        parser.add_argument("--" + field, type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--rerun-prohibited", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        require(args.execute and not args.rerun_prohibited, "host_build_execution_prohibited")
        if __package__ in {None, ""}:
            sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from tools.experiments.execution.execution_resource_plan import (
            HOST_RUNTIME_ROOT, RuntimeIdentityReader, read_shared_runtime_provision,
            read_shared_runtime_readback,
        )
        provision = read_shared_runtime_provision(args.provision_receipt)
        readback = read_shared_runtime_readback(args.readback_receipt)
        RuntimeIdentityReader().read(provision, readback)
        runtime = Path(HOST_RUNTIME_ROOT)
        observed = runtime.stat()
        require(provision.bind_source_path == str(runtime) == readback.bind_target_path
                and (observed.st_dev, observed.st_ino) == (readback.bind_target_dev, readback.bind_target_ino),
                "host_build_shared_namespace_unproven")
        budget = Budget(**{key: getattr(args, key) for key in Budget.__dataclass_fields__})
        command = tuple(args.command[1:] if args.command[:1] == ["--"] else args.command)
        return run_build(command=command, cwd=args.cwd, budget=budget, runtime=runtime,
                         parent=args.parent_cgroup, endpoint=args.docker_host, daemon_id=args.daemon_id,
                         execution_allowed=args.execute, rerun_prohibited=args.rerun_prohibited)
    except Exception as exc:
        print(json.dumps({"failure_code": getattr(exc, "code", type(exc).__name__)}), file=sys.stderr)
        return 125


if __name__ == "__main__":
    if len(sys.argv) == 7 and sys.argv[1] == "--watchdog":
        # Private subprocess mode. All descriptors come from this adapter;
        # there is no path-based kill target or arbitrary process-list authority.
        control, kill, deadline, log, ready = sys.argv[2:]
        try:
            os.write(int(ready), b"R")
            os.close(int(ready))
            class InheritedJournal:
                def emit(self, event: str, **fields: object) -> None:
                    emit_fd(int(log), event, **fields)
            watchdog(int(control), int(kill), float(deadline), InheritedJournal())
        except BaseException:
            os.write(int(kill), b"1")
            raise
    else:
        raise SystemExit(main())
