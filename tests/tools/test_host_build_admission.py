# @dependency-start
# contract test
# responsibility Exercises host build admission using only synthetic procfs/cgroup files, fake Docker, and tiny lock holders; never runs a compiler, build, daemon, or GPU.
# upstream implementation ../../tools/experiments/execution/host_build_admission.py host admission owner
# upstream design ../../documents/experiments/host-build-admission.md fixture-only acceptance boundary
# @dependency-end

from __future__ import annotations

import json
import multiprocessing
from multiprocessing.connection import Connection
import os
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.experiments.execution import host_build_admission as admission


MIB = 1024**2
CID = "a" * 64


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def lock_attempt(root: str, connection: Connection) -> None:
    try:
        with admission.HostLease(Path(root)):
            connection.send("acquired")
    except admission.AdmissionError as error:
        connection.send(error.code)
    finally:
        connection.close()


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.paths = admission.HostPaths(self.root / "runtime", self.root / "runtime/locks",
                                        self.root / "proc", self.root / "cgroup")
        self.paths.locks.mkdir(parents=True)
        self.source = self.root / "source"
        (self.source / ".git").mkdir(parents=True)
        self.request = admission.BuildRequest(
            image="compiler@sha256:" + "b" * 64, docker_host="unix:///designated.sock",
            daemon_id="designated-daemon", source_root=str(self.source),
            argv=("cmake", "--build", "build", "--target", "unit"), jobs=2,
            compiler_peak_bytes=64*MIB, linker_peak_bytes=96*MIB, overhead_bytes=32*MIB,
            memory_bytes=256*MIB, cpu_count=2, pids_limit=64, host_reserve_bytes=256*MIB,
            timeout_seconds=30, rerun_authorized=True, estimate_basis="synthetic fixture only")
        # These are ordinary fixture files, NOT the executing host's procfs or cgroups.
        write(self.paths.proc / "self/mountinfo",
              f"1 0 8:1 / / rw - ext4 /dev/fixture rw\n"
              f"2 1 0:1 / {self.paths.cgroup} rw - cgroup2 cgroup rw\n")
        write(self.paths.proc / "meminfo", "MemTotal: 2097152 kB\nMemAvailable: 1048576 kB\n"
              "SwapTotal: 262144 kB\nSwapFree: 131072 kB\n")
        write(self.paths.proc / "pressure/memory", "some avg10=0.00 avg60=0.00 avg300=0.00 total=10\n"
              "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
        self.group = self.paths.cgroup / "delegated/build"
        write(self.paths.proc / "42/cgroup", "0::/delegated/build\n")
        # Fields following comm start at stat field 3; starttime is field 22.
        write(self.paths.proc / "42/stat", "42 (fixture timeout) " + " ".join(["S"] + ["0"]*18 + ["1234"]) + "\n")
        write(self.group.parent / "memory.max", "max\n")
        for name, content in {
            "cgroup.controllers": "cpu memory pids\n", "cgroup.procs": "42\n", "cgroup.events": "populated 1\n",
            "memory.max": str(self.request.memory_bytes), "memory.swap.max": "0",
            "cpu.max": "200000 100000", "pids.max": "64", "memory.current": "1024",
            "memory.swap.current": "0"}.items():
            write(self.group / name, content)

    def events(self) -> list[Path]:
        return sorted(self.paths.runtime.glob("host-builds/*/events.jsonl"))


class RequestTests(Fixture):
    def test_parallelism_is_single_plan_value(self) -> None:
        self.assertEqual(self.request.validate()[-2:], ("--parallel", "2"))
        for command in ("make", "gmake", "ninja"):
            self.assertEqual(replace(self.request, argv=(command, "unit")).validate(), (command, "unit", "-j", "2"))
        self.assertEqual(replace(self.request, argv=("clang++-19", "-c", "fixture.cc"), jobs=1).validate()[0], "clang++-19")

    def test_invalid_plans_never_construct_docker(self) -> None:
        mutations = [dict(rerun_authorized=False), dict(rerun_authorized=1), dict(estimate_basis=""),
                     dict(jobs=0), dict(jobs=True), dict(memory_bytes=-1), dict(timeout_seconds=float("inf")),
                     dict(timeout_seconds=0), dict(jobs=3), dict(cpu_count=0), dict(pids_limit=1),
                     dict(image="compiler:latest"), dict(docker_host="tcp://remote:2375"),
                     dict(argv=("sh", "-c", "make")), dict(argv=("cmake", "--build", "build", "--", "-j9")),
                     dict(argv=("make", "-j")), dict(argv=("ninja", "-j4")), dict(argv=("make", "--jobs=4")),
                     dict(argv=("cmake", "--build", "build", "--parallel")), dict(argv=["make"])]
        for values in mutations:
            with self.subTest(values=values), patch.object(admission, "Docker") as docker:
                with self.assertRaises(admission.AdmissionError):
                    admission.execute(replace(self.request, **values), self.paths)
                docker.assert_not_called()

    def test_mixed_compiler_linker_concurrency_budget(self) -> None:
        # max() is deliberately conservative; no assumption of sequential phases.
        replace(self.request, memory_bytes=224*MIB).validate()
        with self.assertRaisesRegex(admission.AdmissionError, "parallelism_exceeds_memory_budget"):
            replace(self.request, memory_bytes=224*MIB-1).validate()


class ObservationTests(Fixture):
    def test_effective_limits_and_host_observation(self) -> None:
        result = admission.effective_limits(self.paths, 42, self.request)
        self.assertEqual(result["memory_max"], 256*MIB)
        self.assertEqual(result["process_start_time"], 1234)
        self.assertEqual(result["cpu_count"], 2)
        self.assertEqual(admission.host_observation(self.paths)["memory_bytes"]["MemAvailable"], 1024*MIB)

    def test_unlimited_missing_or_malformed_cgroup_refused(self) -> None:
        cases = {"memory.max": ["max", "", "0", str(300*MIB)], "memory.swap.max": ["max", "1"],
                 "cpu.max": ["max 100000", "200000 0", "300000 100000"],
                 "pids.max": ["max", "65"], "cgroup.controllers": ["memory pids"],
                 "cgroup.procs": ["43"], "memory.current": ["-1"]}
        for name, values in cases.items():
            path = self.group / name
            original = path.read_text()
            for value in values:
                with self.subTest(name=name, value=value):
                    path.write_text(value)
                    with self.assertRaises((admission.AdmissionError, ValueError)):
                        admission.effective_limits(self.paths, 42, self.request)
            path.unlink()
            with self.subTest(name=name, missing=True), self.assertRaises(OSError):
                admission.effective_limits(self.paths, 42, self.request)
            path.write_text(original)

    def test_tighter_ancestor_can_reject_budget(self) -> None:
        (self.group.parent / "memory.max").write_text(str(128*MIB))
        with self.assertRaisesRegex(admission.AdmissionError, "below_build_budget"):
            admission.effective_limits(self.paths, 42, self.request)

    def test_unknown_host_memory_pressure_and_mount_refused(self) -> None:
        pressure = self.paths.proc / "pressure/memory"
        for text in ("", "some avg10=nan avg60=0 avg300=0 total=0\nfull avg10=0 avg60=0 avg300=0 total=0",
                     "some avg10=0 avg60=0 avg300=0 total=0", "some avg10=200 avg60=0 avg300=0 total=0"):
            with self.subTest(text=text):
                pressure.write_text(text)
                with self.assertRaises(admission.AdmissionError):
                    admission.host_observation(self.paths)
        mount = self.paths.proc / "self/mountinfo"
        mount.write_text(mount.read_text().replace("ext4", "tmpfs"))
        with self.assertRaisesRegex(admission.AdmissionError, "persistent_host_filesystem"):
            admission._persistent_directory(self.paths.runtime, self.paths.proc)

    def test_output_sync_and_quiescence_read_fail_closed(self) -> None:
        directory = self.root / "log-fixture"
        write(directory / "output/stdout.log", "fixture bytes\n")
        write(directory / "output/stderr.log", "")
        admission._sync_outputs(directory)
        (directory / "output/stdout.log").unlink()
        (directory / "output/stdout.log").symlink_to(directory / "output/stderr.log")
        with self.assertRaises(OSError):
            admission._sync_outputs(directory)
        limits = admission.effective_limits(self.paths, 42, self.request)
        (self.group / "cgroup.events").unlink()
        with self.assertRaises(OSError):
            admission._cgroup_quiescent(self.paths, limits)

    def test_missing_mount_is_not_proof_of_container_quiescence(self) -> None:
        limits = admission.effective_limits(self.paths, 42, self.request)
        mount = self.paths.proc / "self/mountinfo"
        mount.write_text(mount.read_text().splitlines()[0]+"\n")
        with self.assertRaisesRegex(admission.AdmissionError, "quiescence_cgroup_mount_unreadable"):
            admission._cgroup_quiescent(self.paths, limits)

    def test_pid_reuse_changes_identity(self) -> None:
        before = admission.effective_limits(self.paths, 42, self.request)
        path = self.paths.proc / "42/stat"
        path.write_text(path.read_text().replace("1234", "1235"))
        after = admission.effective_limits(self.paths, 42, self.request)
        self.assertNotEqual(before["process_start_time"], after["process_start_time"])


class LeaseTests(Fixture):
    def test_cross_process_admission_race_and_unresolved_marker(self) -> None:
        context = multiprocessing.get_context("spawn")
        with admission.HostLease(self.paths.locks) as first:
            first.reserve({"run_id": "synthetic"})
            parent, child = context.Pipe()
            process = context.Process(target=lock_attempt, args=(str(self.paths.locks), child))
            process.start()
            child.close()
            try:
                self.assertTrue(parent.poll(5), "tiny lock fixture timed out")
                self.assertEqual(parent.recv(), "host_build_busy")
            finally:
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                parent.close()
            self.assertEqual(process.exitcode, 0)
        # Closing the observer's fd never asserts quiescence of its old child.
        with self.assertRaisesRegex(admission.AdmissionError, "unresolved_host_build_lease"):
            with admission.HostLease(self.paths.locks):
                pass

    def test_proven_release_keeps_stable_lock_inode(self) -> None:
        with admission.HostLease(self.paths.locks) as first:
            inode = os.fstat(first.fd).st_ino
            first.reserve({"run_id": "synthetic"})
            first.release_proven_quiescent()
        with admission.HostLease(self.paths.locks) as second:
            self.assertEqual(os.fstat(second.fd).st_ino, inode)


class DockerTests(Fixture):
    def test_daemon_identity_and_effective_driver_not_flags(self) -> None:
        docker = admission.Docker(self.request)
        cases = [dict(ID="designated-daemon", CgroupDriver="none", CgroupVersion="2"),
                 dict(ID="different-daemon", CgroupDriver="systemd", CgroupVersion="2"),
                 dict(ID="designated-daemon", CgroupDriver="systemd", CgroupVersion="1"), {}]
        for info in cases:
            with self.subTest(info=info), patch.object(docker, "call", return_value=json.dumps(info)):
                with self.assertRaises(admission.AdmissionError):
                    docker.verify()
        with patch.object(docker, "call", return_value=json.dumps(dict(ID="designated-daemon", CgroupDriver="systemd", CgroupVersion="2"))):
            docker.verify()

    def test_docker_requests_are_pinned_and_time_bounded(self) -> None:
        docker = admission.Docker(self.request)
        with patch.object(admission.subprocess, "run") as run, patch.dict(os.environ, {"DOCKER_HOST": "tcp://bypass", "DOCKER_CONTEXT": "bypass"}):
            run.return_value.returncode = 0
            run.return_value.stdout = "ok"
            docker.call("info")
            args, kwargs = run.call_args
            self.assertEqual(args[0], ["docker", "--host", "unix:///designated.sock", "info"])
            self.assertEqual(kwargs["timeout"], 5)
            self.assertFalse(any(key.startswith("DOCKER_") for key in kwargs["env"]))
            self.assertNotIn("shell", kwargs)

    def test_independent_deadline_and_hard_limits_are_in_create_not_agent_poll(self) -> None:
        argv = admission.container_argv(self.request, "fixture", self.root, self.request.validate())
        self.assertEqual(argv[0], "create")
        self.assertIn("--pull=never", argv)
        self.assertEqual(argv[argv.index("--entrypoint")+1], "timeout")
        self.assertIn("--kill-after=5s", argv)
        self.assertIn("30s", argv)
        self.assertEqual(argv[argv.index("--memory")+1], str(256*MIB))
        self.assertEqual(argv[argv.index("--memory-swap")+1], str(256*MIB))
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("--pid=host", argv)
        self.assertNotIn("--gpus", argv)
        self.assertIn("/agent-canon-gate/GO", argv[argv.index("-c")+1])

    def test_container_id_and_ownership_mismatch_rejected(self) -> None:
        docker = admission.Docker(self.request)
        for identifier, label in (("b"*64, "fixture"), (CID, "other-run")):
            row = {"Id": identifier, "Config": {"Labels": {"agent-canon.host-build": label}}, "State": {"Running": True, "OOMKilled": False}}
            with patch.object(docker, "call", return_value=json.dumps([row])):
                with self.assertRaises(admission.AdmissionError):
                    docker.inspect(CID, "fixture")


class FakeDocker:
    """Records control operations; does not start any process or daemon."""

    def __init__(self, fixture: Fixture, failure: str | None = None, exit_code: int = 0):
        self.fixture, self.failure, self.exit_code = fixture, failure, exit_code
        self.calls: list[tuple[str, ...]] = []
        self.running = False
        self.run_id = ""
        self.inspections = 0
        self.gated_samples = 0

    def verify(self) -> None:
        self.calls.append(("verify",))
        if self.failure == "daemon":
            raise admission.AdmissionError("effective_cgroup_driver_required")

    def call(self, *args: str) -> str:
        self.calls.append(args)
        if args[0] == "create":
            self.run_id = args[args.index("--name")+1].removeprefix("agent-canon-host-build-")
            if self.failure == "create_ambiguous":
                raise TimeoutError("synthetic create response loss")
            return CID
        if args[0] == "start":
            if self.failure == "start":
                raise admission.AdmissionError("docker_start_failed")
            self.running = True
            return CID
        if args[0] == "exec":
            return "timeout (GNU coreutils) fixture" if self.failure != "timeout_owner" else "unknown timeout"
        if args[0] == "kill":
            self.running = False
            self.exit_code = 137
        return ""

    def inspect(self, identity: str, run_id: str) -> dict:
        self.calls.append(("inspect", identity))
        self.inspections += 1
        gate = self.fixture.paths.runtime / "host-builds" / run_id / "gate/GO"
        if gate.exists():
            self.gated_samples += 1
            if self.failure == "observer_loss":
                raise SystemExit("synthetic abrupt observer loss")
            if self.failure == "monitor":
                self.failure = "forever"
                raise OSError("synthetic monitor read failure")
            if self.failure == "drift":
                (self.fixture.group / "memory.max").write_text("max")
                self.failure = "forever"
            if self.failure != "forever" and self.gated_samples >= 2:
                self.running = False
        (self.fixture.group / "cgroup.events").write_text(
            "populated 1\n" if self.running or self.failure == "stale_children" else "populated 0\n")
        return {"Id": CID, "State": {"Running": self.running, "Pid": 42, "ExitCode": self.exit_code, "OOMKilled": self.failure == "oom_reported"}}


class LifecycleTests(Fixture):
    def run_fixture(self, failure: str | None = None, exit_code: int = 0):
        fake = FakeDocker(self, failure, exit_code)
        with patch.object(admission, "Docker", return_value=fake), patch.object(admission.time, "sleep"):
            result = admission.execute(self.request, self.paths)
        return fake, result

    def test_success_is_gated_and_terminal_is_durable(self) -> None:
        fake, result = self.run_fixture()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(admission.read_result(Path(result["events"]))["status"], "ok")
        rows = [json.loads(line) for line in Path(result["events"]).read_text().splitlines()]
        self.assertEqual([row["event"] for row in rows], ["start", "admission", "container_created", "admitted", "sample", "end"])
        self.assertEqual(sum(call[0] == "create" for call in fake.calls), 1)
        self.assertFalse((self.paths.locks / "host-build-active.json").exists())
        self.assertFalse(any(call[0] == "kill" for call in fake.calls))

    def test_daemon_and_environment_start_failure_never_open_gate(self) -> None:
        for failure in ("daemon", "start", "timeout_owner"):
            with self.subTest(failure=failure):
                fake, result = self.run_fixture(failure)
                self.assertEqual(result["status"], "failed")
                self.assertFalse((Path(result["events"]).parent / "gate/GO").exists())
                self.assertLessEqual(sum(call[0] == "create" for call in fake.calls), 1)
                self.assertFalse(any(call[0] in {"pull", "build", "restart"} for call in fake.calls))

    def test_ineffective_cgroup_never_releases_workload(self) -> None:
        (self.group / "memory.max").write_text("max")
        fake, result = self.run_fixture()
        self.assertEqual(result["reason"], "finite_memory_limit_required")
        self.assertFalse((Path(result["events"]).parent / "gate/GO").exists())
        self.assertIn(("kill", "--signal=KILL", CID), fake.calls)

    def test_monitor_failure_or_limit_drift_stops_only_owned_container(self) -> None:
        for failure in ("monitor", "drift"):
            with self.subTest(failure=failure):
                (self.group / "memory.max").write_text(str(self.request.memory_bytes))
                fake, result = self.run_fixture(failure)
                self.assertEqual(result["status"], "failed")
                self.assertIn(("kill", "--signal=KILL", CID), fake.calls)
                self.assertEqual(result["exit_code"], 137)
                self.assertIs(result["container_oom_reported"], False)

    def test_host_memory_refusal_is_pre_create(self) -> None:
        path = self.paths.proc / "meminfo"
        path.write_text(path.read_text().replace("1048576", "300000"))
        fake, result = self.run_fixture()
        self.assertEqual(result["reason"], "host_memory_budget_unavailable")
        self.assertFalse(any(call[0] == "create" for call in fake.calls))

    def test_host_reserve_exhaustion_after_launch_stops_owned_container(self) -> None:
        observation = admission.host_observation(self.paths)
        low = {**observation, "memory_bytes": {**observation["memory_bytes"], "MemAvailable": 1}}
        with patch.object(admission, "host_observation", side_effect=[observation, observation, low]):
            fake, result = self.run_fixture("forever")
        self.assertEqual(result["reason"], "host_reserve_exhausted")
        self.assertIn(("kill", "--signal=KILL", CID), fake.calls)

    def test_post_lock_host_change_never_opens_gate(self) -> None:
        observation = admission.host_observation(self.paths)
        low = {**observation, "memory_bytes": {**observation["memory_bytes"], "MemAvailable": 1}}
        with patch.object(admission, "host_observation", side_effect=[observation, low]):
            fake, result = self.run_fixture("forever")
        self.assertEqual(result["reason"], "host_memory_changed_before_launch")
        self.assertFalse((Path(result["events"]).parent / "gate/GO").exists())
        self.assertIn(("kill", "--signal=KILL", CID), fake.calls)

    def test_changed_pid_identity_before_gate_is_rejected(self) -> None:
        limits = admission.effective_limits(self.paths, 42, self.request)
        changed = {**limits, "process_start_time": limits["process_start_time"] + 1}
        with patch.object(admission, "effective_limits", side_effect=[limits, changed]):
            fake, result = self.run_fixture("forever")
        self.assertEqual(result["reason"], "bounded_environment_changed_before_launch")
        self.assertFalse((Path(result["events"]).parent / "gate/GO").exists())
        self.assertIn(("kill", "--signal=KILL", CID), fake.calls)

    def test_second_session_does_not_use_different_daemon_or_host(self) -> None:
        with admission.HostLease(self.paths.locks) as first:
            first.reserve({"run_id": "other-session"})
            fake, result = self.run_fixture()
            self.assertEqual(result["reason"], "host_build_busy")
            self.assertEqual(fake.calls, [])
            self.assertEqual(admission.read_result(Path(result["events"]))["status"], "failed")
            first.release_proven_quiescent()

    def test_host_deadline_stops_owned_container(self) -> None:
        with patch.object(admission.time, "monotonic", side_effect=[0, 0, 31]):
            fake, result = self.run_fixture("forever")
        self.assertEqual(result["reason"], "timeout")
        self.assertIn(("kill", "--signal=KILL", CID), fake.calls)

    def test_ambiguous_create_resolves_only_own_name_and_label(self) -> None:
        fake, result = self.run_fixture("create_ambiguous")
        self.assertEqual(result["status"], "failed")
        lookups = [call[1] for call in fake.calls if call[0] == "inspect"]
        self.assertTrue(lookups[0].startswith("agent-canon-host-build-"))
        self.assertFalse((Path(result["events"]).parent / "gate/GO").exists())

    def test_observer_loss_retains_marker_and_independent_deadline(self) -> None:
        fake = FakeDocker(self, "observer_loss")
        with patch.object(admission, "Docker", return_value=fake), self.assertRaises(SystemExit):
            admission.execute(self.request, self.paths)
        self.assertEqual(admission.read_result(self.events()[0])["status"], "interrupted")
        self.assertTrue((self.paths.locks / "host-build-active.json").exists())
        create = next(call for call in fake.calls if call[0] == "create")
        self.assertIn("--kill-after=5s", create)
        with self.assertRaisesRegex(admission.AdmissionError, "unresolved_host_build_lease"):
            with admission.HostLease(self.paths.locks):
                pass

    def test_log_failure_is_not_success_and_retains_unresolved_evidence(self) -> None:
        emit = admission.Journal.emit
        broken = False
        def fail_after_launch(journal, event, **fields):
            nonlocal broken
            if event == "sample":
                broken = True
            if broken:
                raise OSError("synthetic fsync failure")
            return emit(journal, event, **fields)
        fake = FakeDocker(self, "forever")
        with patch.object(admission, "Docker", return_value=fake), patch.object(admission.Journal, "emit", fail_after_launch):
            with self.assertRaises(OSError):
                admission.execute(self.request, self.paths)
        self.assertIn(("kill", "--signal=KILL", CID), fake.calls)
        self.assertEqual(admission.read_result(self.events()[0])["status"], "interrupted")
        self.assertTrue((self.paths.locks / "host-build-active.json").exists())

    def test_root_exit_does_not_release_still_populated_cgroup(self) -> None:
        fake = FakeDocker(self, "stale_children")
        with patch.object(admission, "Docker", return_value=fake), patch.object(admission.time, "sleep"):
            with self.assertRaisesRegex(admission.AdmissionError, "container_quiescence_unverified"):
                admission.execute(self.request, self.paths)
        self.assertFalse(any(call[0] == "rm" for call in fake.calls))
        self.assertEqual(admission.read_result(self.events()[0])["status"], "interrupted")
        self.assertTrue((self.paths.locks / "host-build-active.json").exists())

    def test_explicit_container_oom_report_is_separate_from_raw_exit(self) -> None:
        _, result = self.run_fixture("oom_reported", exit_code=0)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["reason"], "container_oom_reported")
        self.assertEqual(result["exit_code"], 0)
        self.assertIs(result["container_oom_reported"], True)

    def test_nonzero_exit_never_becomes_oom_or_success(self) -> None:
        _, result = self.run_fixture(exit_code=137)
        self.assertEqual(result["status"], "failed")
        self.assertIs(result["container_oom_reported"], False)


class ResultTests(Fixture):
    def test_missing_torn_and_contradictory_end_are_interrupted(self) -> None:
        start = {"event": "start", "run_id": "fixture"}
        end = {"event": "end", "run_id": "fixture", "status": "ok", "reason": "completed", "exit_code": 0}
        path = self.root / "events.jsonl"
        self.assertEqual(admission.read_result(path)["status"], "interrupted")
        examples = [[], [start], [start, {"event": "sample", "exit_code": 0}], [start, end, end],
                    [start, {**end, "exit_code": 137}], [start, {**end, "run_id": "other"}], [start, []]]
        for rows in examples:
            path.write_text("".join(json.dumps(row)+"\n" for row in rows))
            self.assertEqual(admission.read_result(path), {"status": "interrupted", "exit_code": None, "oom": "unknown"})
        path.write_text(json.dumps(start)+"\n"+json.dumps(end))
        self.assertEqual(admission.read_result(path)["status"], "interrupted")
        path.write_text(path.read_text()+"\n")
        self.assertEqual(admission.read_result(path)["status"], "ok")


if __name__ == "__main__":
    unittest.main()
