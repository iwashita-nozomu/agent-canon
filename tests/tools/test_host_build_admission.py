# @dependency-start
# contract test
# responsibility Verifies host-build admission and autonomous stop with synthetic proc/cgroup/daemon fixtures only.
# upstream implementation ../../tools/experiments/execution/host_build_admission.py host build owner
# upstream design ../../documents/experiments/host-build-admission.md no workload replay acceptance
# @dependency-end
"""No compiler, Docker daemon, GPU workload, or real cgroup is started here."""
from __future__ import annotations

import copy
import multiprocessing
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from tools.experiments.execution import host_build_admission as h

PSI = "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
BUDGET = h.Budget(4096, 2, 1024, 1024, 2048, 64, 2)
DAEMON = {"ID": "selected", "CgroupDriver": "systemd", "CgroupVersion": "2"}


def fixture(root: Path) -> tuple[Path, Path]:
    group, proc = root / "group", root / "proc"
    group.mkdir()
    (proc / "pressure").mkdir(parents=True)
    (proc / "meminfo").write_text("MemTotal: 32 kB\nMemAvailable: 24 kB\nSwapTotal: 8 kB\nSwapFree: 8 kB\n")
    (proc / "pressure/memory").write_text(PSI)
    fields = {**BUDGET.limits(), "memory.max": "16384", "memory.current": "1024",
              "memory.swap.current": "0", "memory.pressure": PSI, "cgroup.events": "populated 0\n",
              "pids.current": "0", "cgroup.subtree_control": "memory cpu pids", "cgroup.type": "domain", "cgroup.kill": "0"}
    for name, value in fields.items():
        (group / name).write_text(value)
    return group, proc


def contend(root: str, connection) -> None:
    try:
        with h.host_slot(Path(root)):
            connection.send("admitted")
    except h.BuildRefused as exc:
        connection.send(exc.code)
    finally:
        connection.close()


class HostBuildAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.group, self.proc = fixture(self.root)

    def test_finite_snapshot_admission_and_budget_equality(self):
        observed = h.snapshot(self.group, self.proc)
        h.admit(BUDGET, observed, "cpu memory pids")
        h.admit(replace(BUDGET, fixed_memory_bytes=2048), observed, "cpu memory pids")
        self.assertEqual(observed["host"]["SwapFree"], 8192)

    def test_unlimited_missing_malformed_cgroup_and_monitor_fail_closed(self):
        for name, value in (("memory.max", "max"), ("memory.swap.max", "max"),
                            ("cpu.max", "max 100000"), ("pids.max", "max"),
                            ("memory.current", "-1"), ("memory.pressure", "")):
            with self.subTest(name=name):
                path = self.group / name
                saved = path.read_text()
                path.write_text(value)
                with self.assertRaises((h.BuildRefused, ValueError)):
                    h.snapshot(self.group, self.proc)
                path.write_text(saved)
        (self.group / "memory.current").unlink()
        with self.assertRaises(OSError):
            h.snapshot(self.group, self.proc)

    def test_bad_host_memory_and_pressure_are_not_zero_or_unlimited(self):
        (self.proc / "pressure/memory").write_text(PSI.replace("0.00", "nan"))
        with self.assertRaises(h.BuildRefused):
            h.snapshot(self.group, self.proc)
        (self.proc / "pressure/memory").write_text(PSI)
        (self.proc / "meminfo").write_text("MemAvailable: 24 kB\n")
        with self.assertRaises(h.BuildRefused):
            h.snapshot(self.group, self.proc)

    def test_daemon_none_changed_identity_and_v1_refuse(self):
        h.validate_daemon(DAEMON, "selected")
        for change in ({"CgroupDriver": "none"}, {"ID": "alternate"}, {"CgroupVersion": "1"}):
            with self.subTest(change=change), self.assertRaises(h.BuildRefused):
                h.validate_daemon({**DAEMON, **change}, "selected")

    def test_environment_failure_has_one_probe_and_no_fallback_or_workload(self):
        with patch.object(h.subprocess, "run", side_effect=OSError("selected daemon unavailable")) as run, \
             patch.object(h.subprocess, "Popen") as launch:
            with self.assertRaises(OSError):
                h.daemon_probe("unix:///selected.sock", "selected")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][:3], ["docker", "--host", "unix:///selected.sock"])
            self.assertEqual(run.call_args.kwargs["timeout"], 5)
            launch.assert_not_called()

    def test_budget_and_controller_denials(self):
        observed = h.snapshot(self.group, self.proc)
        for budget, sample, controllers, code in (
            (replace(BUDGET, worker_memory_bytes=4096), observed, "memory cpu pids", "host_build_parallel_memory_exceeded"),
            (BUDGET, observed, "cpu pids", "host_build_controllers_not_delegated"),
            (replace(BUDGET, reserve_bytes=24000), observed, "memory cpu pids", "host_build_ram_unavailable"),
            (replace(BUDGET, workers=3, worker_memory_bytes=512), observed, "memory cpu pids", "host_build_cpu_unavailable"),
            (replace(BUDGET, pids=65), observed, "memory cpu pids", "host_build_pids_unavailable"),
        ):
            with self.subTest(code=code), self.assertRaises(h.BuildRefused) as raised:
                h.admit(budget, sample, controllers)
            self.assertEqual(raised.exception.code, code)
        sample = copy.deepcopy(observed)
        sample["memory_current"] = 15000
        with self.assertRaisesRegex(h.BuildRefused, "ram_unavailable"):
            h.admit(BUDGET, sample, "memory cpu pids")

    def test_nonfinite_timeout_refuses(self):
        for timeout in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(timeout=timeout), self.assertRaises(h.BuildRefused):
                replace(BUDGET, timeout_seconds=timeout).validate()

    def test_parallelism_is_explicit_and_daemon_shell_routes_are_rejected(self):
        self.assertEqual(h.native_argv(("cmake", "--build", "build"), 2),
                         ("cmake", "--build", "build", "--parallel", "2"))
        self.assertEqual(h.native_argv(("ninja", "target"), 1), ("ninja", "target", "-j1"))
        for argv in (("cmake", "--build", "x", "--parallel", "4"), ("make", "-j"),
                     ("cmake", "--build", "x", "--", "-j99"), ("bash", "-c", "make"),
                     ("docker", "run", "other"), ("dockerd",), ("ssh", "other", "make")):
            with self.subTest(argv=argv), self.assertRaises(h.BuildRefused):
                h.native_argv(argv, 1)

    def test_configure_try_compile_is_single_worker_and_not_an_unbounded_route(self):
        command = ("cmake", "-S", "source", "-B", "build")
        self.assertEqual(h.native_argv(command, 1), command)
        with self.assertRaises(h.BuildRefused):
            h.native_argv(command, 2)

    def test_no_rerun_wins_before_any_probe_or_spawn_even_for_reduced_command(self):
        for command in (("cmake", "--build", "crashed"), ("cmake", "--build", "reduced")):
            with patch.object(h, "snapshot") as probe, patch.object(h.subprocess, "Popen") as launch, \
                 patch.object(h.subprocess, "run") as docker:
                with self.assertRaisesRegex(h.BuildRefused, "execution_prohibited"):
                    h.run_build(command=command, cwd=self.root, budget=BUDGET, runtime=self.root,
                                parent=self.group, endpoint="unix:///selected.sock", daemon_id="selected",
                                execution_allowed=True, rerun_prohibited=True)
                probe.assert_not_called()
                launch.assert_not_called()
                docker.assert_not_called()

    def test_ephemeral_overlay_and_non_cgroup_mounts_refuse(self):
        runtime, parent = Path("/var/lib/agent-canon/runtime"), Path("/sys/fs/cgroup/builds")
        good = "1 0 8:1 / / rw - ext4 /dev/root rw\n2 1 0:2 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n"
        h.validate_placement(runtime, parent, good)
        for mount in (good.replace("ext4", "tmpfs"), good.replace("ext4", "overlay"),
                      good.replace("cgroup2", "tmpfs")):
            with self.assertRaises(h.BuildRefused):
                h.validate_placement(runtime, parent, mount)

    def test_shared_slot_excludes_a_separate_process_and_preserves_stale_marker(self):
        (self.root / "locks").mkdir()
        context = multiprocessing.get_context("spawn")
        with h.host_slot(self.root) as marker:
            left, right = context.Pipe()
            child = context.Process(target=contend, args=(str(self.root), right))
            child.start()
            self.assertTrue(left.poll(5))
            self.assertEqual(left.recv(), "host_build_busy")
            child.join(5)
            self.assertEqual(child.exitcode, 0)
            left.close()
            right.close()
            marker.write_text("interrupted run")
        with self.assertRaisesRegex(h.BuildRefused, "host_build_interrupted"):
            with h.host_slot(self.root):
                self.fail("must not automatically retry an interrupted run")

    def test_missing_or_torn_end_event_is_interrupted_not_success_or_oom(self):
        journal = h.Journal(self.root / "logs")
        journal.emit("start", pid=123)
        path = journal.directory / "events.jsonl"
        self.assertEqual(h.journal_status(path), "interrupted")
        journal.emit("end", reason="exited", exit_code=0)
        self.assertEqual(h.journal_status(path), "success")
        journal.close()
        with path.open("a") as stream:
            stream.write('{"event":')
        self.assertEqual(h.journal_status(path), "interrupted")

    def test_watchdog_stops_owned_fd_before_attempting_failing_log_on_disconnect(self):
        reader, writer = os.pipe()
        kill = os.open(self.group / "cgroup.kill", os.O_WRONLY)
        journal = Mock()
        journal.emit.side_effect = OSError("log unavailable")
        os.close(writer)
        try:
            with self.assertRaises(OSError):
                h.watchdog(reader, kill, time.monotonic() + 5, journal)
            self.assertEqual((self.group / "cgroup.kill").read_text(), "1")
        finally:
            os.close(reader)
            os.close(kill)

    def test_watchdog_timeout_does_not_need_parent_or_conversation_reply(self):
        reader, writer = os.pipe()
        journal = h.Journal(self.root / "watchdog")
        kill = os.open(self.group / "cgroup.kill", os.O_WRONLY)
        try:
            started = time.monotonic()
            h.watchdog(reader, kill, started + 0.02, journal)
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual((self.group / "cgroup.kill").read_text(), "1")
            self.assertEqual(h.journal_status(journal.directory / "events.jsonl"), "interrupted")
        finally:
            os.close(reader)
            os.close(writer)
            os.close(kill)
            journal.close()

    def test_watchdog_missing_heartbeat_stops_before_total_deadline(self):
        reader, writer = os.pipe()
        journal = h.Journal(self.root / "stalled")
        kill = os.open(self.group / "cgroup.kill", os.O_WRONLY)
        try:
            with patch.object(h, "MONITOR_TIMEOUT_SECONDS", 0.02):
                h.watchdog(reader, kill, time.monotonic() + 60, journal)
            self.assertEqual((self.group / "cgroup.kill").read_text(), "1")
            self.assertIn("monitor_stalled", (journal.directory / "events.jsonl").read_text())
        finally:
            os.close(reader)
            os.close(writer)
            os.close(kill)
            journal.close()

    def supervise_fixture(self, *, failure=None, timeout=False, before_gate=False):
        journal = h.Journal(self.root / "supervise")
        marker = self.root / "active"
        marker.write_text("fixture")
        sample = h.snapshot(self.group, self.proc)
        sample["limits"] = BUDGET.limits()
        observe = Mock(return_value=sample)
        if failure:
            observe.side_effect = [sample, failure]
        if before_gate:
            sample["limits"] = {**sample["limits"], "memory.max": "max"}
        process = Mock(pid=123456, returncode=0)
        process.poll.return_value = None if timeout else 0
        process.wait.return_value = 0
        budget = replace(BUDGET, timeout_seconds=0.3) if timeout else BUDGET
        popen = h.subprocess.Popen
        def launch_fixture(argv, **kwargs):
            return popen(argv, **kwargs) if "--watchdog" in argv else process
        try:
            with patch.object(h.subprocess, "Popen", side_effect=launch_fixture) as launch, \
                 patch.object(h, "verify_membership"):
                result = h.supervise(("fixture-not-executed",), self.root, budget,
                                     self.group, marker, journal, observe)
            self.assertFalse(marker.exists())
            self.assertTrue(launch.call_args.kwargs["start_new_session"])
            self.assertTrue(set((self.group / "cgroup.kill").read_text()) <= {"1"})
            return result, h.journal_status(journal.directory / "events.jsonl")
        finally:
            journal.close()

    def test_gated_supervision_success_uses_synthetic_child_only(self):
        self.assertEqual(self.supervise_fixture(), (0, "success"))

    def test_live_monitor_failure_kills_and_does_not_report_success(self):
        self.assertEqual(self.supervise_fixture(failure=OSError("unreadable")), (125, "failed"))

    def test_changed_limits_during_startup_refuse_before_release(self):
        self.assertEqual(self.supervise_fixture(before_gate=True), (125, "failed"))

    def test_timeout_kills_only_owned_cgroup_fixture(self):
        self.assertEqual(self.supervise_fixture(timeout=True), (125, "failed"))


if __name__ == "__main__":
    unittest.main()
