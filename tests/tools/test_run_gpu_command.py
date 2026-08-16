# @dependency-start
# contract test
# responsibility Verifies provider-independent direct GPU admission, conservative selection, post-lock race rejection, exact environment, shell-free execution, and descendant-safe release.
# upstream implementation ../../tools/experiments/gpu_command_admission.py direct admission owner
# upstream implementation ../../tools/experiments/run_gpu_command.py CLI adapter
# upstream implementation ../../tools/experiments/execution_resource_plan.py strict NVIDIA, occupancy, and reservation evidence types
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping, Sequence

import pytest

from tools.experiments import gpu_command_admission as direct
from tools.experiments import run_gpu_command as direct_cli
from tools.experiments.execution_resource_plan import (
    FdReleaseEvidence,
    GPUDevice,
    LockReadback,
    NvidiaInventory,
    NvidiaTopologyJoin,
    ProcessIdentity,
    ReservationEvidence,
    ResourceObservation,
    TypedPreflightFailure,
)

GPU_A = "GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
GPU_B = "GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
GPU_C = "GPU-cccccccc-cccc-cccc-cccc-cccccccccccc"
MIG_C = "MIG-cccccccc-cccc-cccc-cccc-cccccccccccc"


def _inventory(gpu_ids: Sequence[str]) -> NvidiaInventory:
    return NvidiaInventory(
        schema_version="nvidia-inventory/v1",
        physical_uuids=tuple(gpu_ids),
        mig_uuids=(),
        joins=(),
        driver_version=None,
        evidence_fingerprint="inventory-" + "-".join(gpu_ids),
    )


def _observation(
    event_id: str,
    *,
    gpu_ids: Sequence[str],
    free_memory: Mapping[str, int],
    busy_ids: Sequence[str] = (),
    unknown_ids: Sequence[str] = (),
) -> ResourceObservation:
    namespace = f"pid:[{os.stat('/proc/self/ns/pid').st_ino}]"
    processes = tuple(
        ProcessIdentity(
            pid=10_000 + index,
            process_start_identity=f"start-{index}",
            gpu_uuid=uuid,
            kind="compute",
            relationship="external",
            container_namespace_identity=namespace,
            pid_namespace=namespace,
            cgroup="0::/test",
        )
        for index, uuid in enumerate(busy_ids)
    )
    devices = tuple(
        GPUDevice(
            uuid=uuid,
            free_memory_bytes=free_memory[uuid],
            memory_bytes=max(free_memory[uuid], 1),
        )
        for uuid in gpu_ids
    )
    return ResourceObservation(
        caller_allocated_ids=frozenset(gpu_ids),
        process_identities=processes,
        gpu_devices=devices,
        free_memory_bytes=dict(free_memory),
        boot_id="boot-test",
        container_visible_ids=frozenset(gpu_ids),
        observed_at=f"observed-{event_id}",
        fingerprint=f"observation-{event_id}",
        observation_event_id=event_id,
        nvidia_inventory=_inventory(gpu_ids),
        unknown_gpu_ids=frozenset(unknown_ids),
    )


class _Probe:
    def __init__(self, observation: ResourceObservation) -> None:
        self._observation = observation

    def observe(self) -> ResourceObservation:
        return self._observation


class _ProbeFactory:
    def __init__(self, observations: Sequence[ResourceObservation]) -> None:
        self._observations = list(observations)
        self.environments: list[Mapping[str, str]] = []

    def __call__(
        self,
        environment: Mapping[str, str],
        gpu_count: int,
        runtime_root: Path,
    ) -> _Probe:
        del gpu_count, runtime_root
        self.environments.append(dict(environment))
        return _Probe(self._observations.pop(0))


class _Transaction:
    def __init__(
        self,
        selected_ids: Sequence[str],
        *,
        close_failure: BaseException | None = None,
        release_error_kind: str | None = None,
    ) -> None:
        self._selected_ids = tuple(selected_ids)
        self._close_failure = close_failure
        self._release_error_kind = release_error_kind
        self.closed = False
        self.close_calls = 0
        self.candidates: tuple[str, ...] | None = None
        self.occupied: tuple[str, ...] | None = None

    @property
    def reservation_ids(self) -> tuple[str, ...]:
        return tuple(f"reservation-{uuid}" for uuid in self._selected_ids)

    def try_reserve(
        self,
        candidate_uuids: Sequence[str],
        *,
        occupied_uuids: Sequence[str] = (),
        requested_count: int = 1,
    ) -> ReservationEvidence:
        self.candidates = tuple(candidate_uuids)
        self.occupied = tuple(occupied_uuids)
        selected = tuple(candidate_uuids[:requested_count])
        self._selected_ids = selected
        locks = tuple(
            LockReadback(
                runtime_root="/var/lib/agent-canon/runtime",
                filesystem_type="ext4",
                device=11,
                inode=22 + index,
                selected=(),
                fingerprint=f"lock-readback-{index}",
            )
            for index, _uuid in enumerate(selected)
        )
        return ReservationEvidence(
            schema_version="gpu-reservation/v1",
            selected_uuids=selected,
            locks=locks,
            disposition=(
                "ACQUIRED"
                if len(selected) == requested_count
                else "BUSY_CANDIDATE"
            ),
            evidence_fingerprint="reservation-evidence",
        )

    def close(self) -> tuple[FdReleaseEvidence, ...]:
        self.close_calls += 1
        if self._close_failure is not None:
            raise self._close_failure
        self.closed = True
        return tuple(
            FdReleaseEvidence(
                component="gpu-reservation-lock",
                uuid=uuid,
                disposition=(
                    "close_ambiguous"
                    if self._release_error_kind is not None
                    else "released"
                ),
                close_attempts=1,
                error_kind=self._release_error_kind,
                fingerprint=f"released-{uuid}",
            )
            for uuid in self._selected_ids
        )


@dataclass
class _Executor:
    returncode: int = 7
    called: bool = False
    environment: Mapping[str, str] | None = None
    plan_seen_after_write: bool = False

    def execute(
        self,
        plan: direct.FrozenDirectGpuCommandPlan,
        environment: Mapping[str, str],
        *,
        stdout_path: Path,
        stderr_path: Path,
        poll_seconds: float,
    ) -> direct.DirectCommandExecution:
        del poll_seconds
        self.called = True
        self.environment = dict(environment)
        self.plan_seen_after_write = (
            stdout_path.parent / "gpu_command_plan.json"
        ).is_file()
        stdout_path.write_bytes(b"stdout-bytes\n")
        stderr_path.write_bytes(b"stderr-bytes\n")
        lifecycle = direct.DirectCommandLifecycle(
            child_pid=1234,
            child_starttime="456",
            process_group_id=1234,
            session_id=1234,
            observed_descendant_identities=((1235, "457"),),
            descendant_quiescence="PROVEN",
            subreaper_enabled=True,
            started_at_utc="2026-08-16T00:00:00+00:00",
            finished_at_utc="2026-08-16T00:00:01+00:00",
            started_at_monotonic=1.0,
            finished_at_monotonic=2.0,
        )
        return direct.DirectCommandExecution(
            returncode=self.returncode,
            lifecycle=lifecycle,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )


class _PostLaunchFailingExecutor(_Executor):
    def execute(
        self,
        plan: direct.FrozenDirectGpuCommandPlan,
        environment: Mapping[str, str],
        *,
        stdout_path: Path,
        stderr_path: Path,
        poll_seconds: float,
    ) -> direct.DirectCommandExecution:
        execution = super().execute(
            plan,
            environment,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            poll_seconds=poll_seconds,
        )
        raise direct.DirectCommandPostLaunchFailure(
            RuntimeError("post-launch diagnostics failed"),
            execution,
        )


@pytest.fixture
def canonical_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    runtime_root = tmp_path / "runtime"
    lock_root = runtime_root / "locks"
    lock_root.mkdir(parents=True)
    monkeypatch.setattr(direct, "HOST_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setattr(direct, "LOCK_ROOT", lock_root)
    return runtime_root, lock_root


def _request(
    tmp_path: Path,
    canonical_runtime: tuple[Path, Path],
    *,
    candidates: Sequence[str],
    gpu_count: int = 1,
    minimum_memory: int = 100,
) -> direct.DirectGpuCommandRequest:
    runtime_root, lock_root = canonical_runtime
    allocation = direct.CandidateAllocation(
        candidate_ids=tuple(sorted(candidates)),
        source="cli",
        inventory_fingerprint="candidate-inventory",
        physical_uuids=tuple(sorted(candidates)),
        mig_uuids=(),
        mig_parent_by_uuid={},
    )
    return direct.DirectGpuCommandRequest(
        argv=(sys.executable, "-c", "raise SystemExit(7)"),
        cwd=tmp_path,
        environment={"PATH": os.environ.get("PATH", "")},
        candidate_allocation=allocation,
        gpu_count=gpu_count,
        minimum_free_memory_bytes=minimum_memory,
        output_dir=tmp_path / "evidence",
        runtime_root=runtime_root,
        lock_root=lock_root,
    )


def test_candidate_resolution_uses_executable_physical_or_mig_leaves() -> None:
    output = (
        f"GPU 0: Test A (UUID: {GPU_A})\n"
        f"GPU 1: Test B (UUID: {GPU_B})\n"
        f"  MIG 1g.10gb  Device  0: (UUID: {MIG_C})\n"
    ).encode()

    def command(
        argv: Sequence[str],
        *,
        check: bool,
        capture_output: bool,
        timeout: float,
        shell: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        assert tuple(argv) == ("/usr/bin/nvidia-smi", "-L")
        assert check is False
        assert capture_output is True
        assert timeout == 30.0
        assert shell is False
        return subprocess.CompletedProcess(argv, 0, output, b"")

    allocation = direct.resolve_candidate_allocation(
        {},
        nvidia_smi="/usr/bin/nvidia-smi",
        command=command,
    )

    assert allocation.candidate_ids == (GPU_A, MIG_C)
    assert GPU_B not in allocation.candidate_ids
    assert allocation.mig_parent_by_uuid == {MIG_C: GPU_B}
    assert allocation.source == "strict_nvidia_inventory"


def test_direct_runner_excludes_busy_and_unknown_then_materializes_exact_environment(
    tmp_path: Path,
    canonical_runtime: tuple[Path, Path],
) -> None:
    free = {GPU_A: 1_000, GPU_B: 1_000, GPU_C: 1_000}
    initial = _observation(
        "initial",
        gpu_ids=(GPU_A, GPU_B, GPU_C),
        free_memory=free,
        busy_ids=(GPU_B,),
        unknown_ids=(GPU_C,),
    )
    final = _observation(
        "final",
        gpu_ids=(GPU_A, GPU_B, GPU_C),
        free_memory=free,
        busy_ids=(GPU_B,),
        unknown_ids=(GPU_C,),
    )
    probes = _ProbeFactory((initial, final))
    transaction = _Transaction((GPU_A,))
    executor = _Executor()
    request = _request(
        tmp_path,
        canonical_runtime,
        candidates=(GPU_A, GPU_B, GPU_C),
    )

    result = direct.DirectGpuCommandRunner(
        probe_factory=probes,
        reservation_factory=lambda _root: transaction,
        executor=executor,
    ).run(request)

    assert transaction.candidates == (GPU_A,)
    assert set(transaction.occupied or ()) == {GPU_B, GPU_C}
    assert transaction.closed is True
    assert transaction.close_calls == 1
    assert executor.called is True
    assert executor.plan_seen_after_write is True
    assert executor.environment is not None
    assert executor.environment["CUDA_VISIBLE_DEVICES"] == GPU_A
    assert executor.environment["NVIDIA_VISIBLE_DEVICES"] == GPU_A
    assert executor.environment["JAX_PLATFORMS"] == "cuda"
    assert executor.environment["XLA_PYTHON_CLIENT_PREALLOCATE"] == "false"
    assert executor.environment["XLA_PYTHON_CLIENT_ALLOCATOR"] == "platform"
    assert (
        executor.environment["XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR"]
        == "false"
    )
    assert result.returncode == 7
    assert result.execution.stdout_path.read_bytes() == b"stdout-bytes\n"
    assert result.execution.stderr_path.read_bytes() == b"stderr-bytes\n"
    persisted = json.loads(result.result_path.read_text())
    assert persisted["managed_provider_required"] is False
    assert persisted["shell"] is False
    assert persisted["selected_gpu_ids"] == [GPU_A]
    assert persisted["selected_free_memory_bytes"] == {GPU_A: 1_000}
    assert persisted["reservation_ids"] == [f"reservation-{GPU_A}"]
    assert persisted["lock_identities"] == [[11, 22]]
    assert persisted["lifecycle"]["started_at"]
    assert persisted["lifecycle"]["finished_at"]
    assert persisted["raw_returncode"] == 7
    plan = json.loads(
        (tmp_path / "evidence" / "gpu_command_plan.json").read_text()
    )
    assert plan["candidate_inventory_fingerprint"] == "candidate-inventory"
    assert plan["final_unit_states"][GPU_A] == "FREE"


def test_post_lock_busy_race_stops_before_child(
    tmp_path: Path,
    canonical_runtime: tuple[Path, Path],
) -> None:
    initial = _observation(
        "initial",
        gpu_ids=(GPU_A,),
        free_memory={GPU_A: 1_000},
    )
    final = _observation(
        "final",
        gpu_ids=(GPU_A,),
        free_memory={GPU_A: 1_000},
        busy_ids=(GPU_A,),
    )
    transaction = _Transaction((GPU_A,))
    executor = _Executor()
    runner = direct.DirectGpuCommandRunner(
        probe_factory=_ProbeFactory((initial, final)),
        reservation_factory=lambda _root: transaction,
        executor=executor,
    )

    with pytest.raises(TypedPreflightFailure) as raised:
        runner.run(
            _request(tmp_path, canonical_runtime, candidates=(GPU_A,))
        )

    assert raised.value.code == "gpu_run_admission_raced"
    assert executor.called is False
    assert transaction.closed is True
    assert transaction.close_calls == 1
    failure = json.loads(
        (tmp_path / "evidence" / "gpu_command_failure.json").read_text()
    )
    assert failure["failure_code"] == "gpu_run_admission_raced"
    assert failure["child_started"] is False


def test_unknown_candidate_is_never_reserved(
    tmp_path: Path,
    canonical_runtime: tuple[Path, Path],
) -> None:
    initial = _observation(
        "initial",
        gpu_ids=(GPU_A,),
        free_memory={GPU_A: 1_000},
        unknown_ids=(GPU_A,),
    )
    factory_called = False

    def reservation_factory(_root: Path) -> _Transaction:
        nonlocal factory_called
        factory_called = True
        return _Transaction(())

    executor = _Executor()
    runner = direct.DirectGpuCommandRunner(
        probe_factory=_ProbeFactory((initial,)),
        reservation_factory=reservation_factory,
        executor=executor,
    )

    with pytest.raises(TypedPreflightFailure) as raised:
        runner.run(
            _request(tmp_path, canonical_runtime, candidates=(GPU_A,))
        )

    assert raised.value.code == "gpu_candidate_unavailable"
    assert factory_called is False
    assert executor.called is False


def test_candidate_resolution_rejects_integer_and_uuid_prefix() -> None:
    output = f"GPU 0: Test A (UUID: {GPU_A})\n".encode()

    def command(
        argv: Sequence[str],
        *,
        check: bool,
        capture_output: bool,
        timeout: float,
        shell: bool,
    ) -> subprocess.CompletedProcess[bytes]:
        del check, capture_output, timeout
        assert shell is False
        return subprocess.CompletedProcess(argv, 0, output, b"")

    with pytest.raises(TypedPreflightFailure) as integer_failure:
        direct.resolve_candidate_allocation(
            {},
            explicit_candidates=("0",),
            nvidia_smi="/usr/bin/nvidia-smi",
            command=command,
        )
    assert integer_failure.value.code == "gpu_candidate_uuid_invalid"

    with pytest.raises(TypedPreflightFailure) as prefix_failure:
        direct.resolve_candidate_allocation(
            {},
            explicit_candidates=("GPU-aaaaaaaa",),
            nvidia_smi="/usr/bin/nvidia-smi",
            command=command,
        )
    assert prefix_failure.value.code == "gpu_candidate_uuid_not_executable_leaf"

    with pytest.raises(TypedPreflightFailure) as environment_failure:
        direct.resolve_candidate_allocation(
            {"CUDA_VISIBLE_DEVICES": "0"},
            nvidia_smi="/usr/bin/nvidia-smi",
            command=command,
        )
    assert environment_failure.value.code == "gpu_candidate_uuid_invalid"


def test_topology_change_after_candidate_discovery_stops_before_lock(
    tmp_path: Path,
    canonical_runtime: tuple[Path, Path],
) -> None:
    initial = _observation(
        "initial",
        gpu_ids=(GPU_A,),
        free_memory={GPU_A: 1_000},
    )
    changed_inventory = NvidiaInventory(
        schema_version="nvidia-inventory/v1",
        physical_uuids=(GPU_A,),
        mig_uuids=(MIG_C,),
        joins=(NvidiaTopologyJoin(GPU_A, 0, MIG_C),),
        driver_version=None,
        evidence_fingerprint="changed-topology",
    )
    changed_initial = replace(initial, nvidia_inventory=changed_inventory)
    factory_called = False

    def reservation_factory(_root: Path) -> _Transaction:
        nonlocal factory_called
        factory_called = True
        return _Transaction((GPU_A,))

    with pytest.raises(TypedPreflightFailure) as raised:
        direct.DirectGpuCommandRunner(
            probe_factory=_ProbeFactory((changed_initial,)),
            reservation_factory=reservation_factory,
            executor=_Executor(),
        ).run(_request(tmp_path, canonical_runtime, candidates=(GPU_A,)))

    assert raised.value.code == "gpu_candidate_topology_raced"
    assert factory_called is False


def test_multi_gpu_plan_binds_every_lock_and_exact_visibility(
    tmp_path: Path,
    canonical_runtime: tuple[Path, Path],
) -> None:
    observations = (
        _observation(
            "initial",
            gpu_ids=(GPU_A, GPU_B),
            free_memory={GPU_A: 1_000, GPU_B: 2_000},
        ),
        _observation(
            "final",
            gpu_ids=(GPU_A, GPU_B),
            free_memory={GPU_A: 900, GPU_B: 1_900},
        ),
    )
    transaction = _Transaction((GPU_A, GPU_B))
    executor = _Executor(returncode=0)
    result = direct.DirectGpuCommandRunner(
        probe_factory=_ProbeFactory(observations),
        reservation_factory=lambda _root: transaction,
        executor=executor,
    ).run(
        _request(
            tmp_path,
            canonical_runtime,
            candidates=(GPU_A, GPU_B),
            gpu_count=2,
        )
    )

    assert executor.environment is not None
    exact = f"{GPU_A},{GPU_B}"
    assert executor.environment["CUDA_VISIBLE_DEVICES"] == exact
    assert executor.environment["NVIDIA_VISIBLE_DEVICES"] == exact
    assert result.plan.lock_identities == ((11, 22), (11, 23))
    assert result.plan.reservation_ids == (
        f"reservation-{GPU_A}",
        f"reservation-{GPU_B}",
    )
    assert result.plan.selected_free_memory_bytes == {
        GPU_A: 900,
        GPU_B: 1_900,
    }
    assert transaction.close_calls == 1


def test_post_launch_failure_releases_only_after_quiescence_evidence(
    tmp_path: Path,
    canonical_runtime: tuple[Path, Path],
) -> None:
    observations = (
        _observation(
            "initial",
            gpu_ids=(GPU_A,),
            free_memory={GPU_A: 1_000},
        ),
        _observation(
            "final",
            gpu_ids=(GPU_A,),
            free_memory={GPU_A: 1_000},
        ),
    )
    transaction = _Transaction((GPU_A,))

    with pytest.raises(RuntimeError, match="post-launch diagnostics failed"):
        direct.DirectGpuCommandRunner(
            probe_factory=_ProbeFactory(observations),
            reservation_factory=lambda _root: transaction,
            executor=_PostLaunchFailingExecutor(),
        ).run(_request(tmp_path, canonical_runtime, candidates=(GPU_A,)))

    assert transaction.closed is True
    assert transaction.close_calls == 1
    failure = json.loads(
        (tmp_path / "evidence" / "gpu_command_failure.json").read_text()
    )
    assert failure["child_started"] is True
    assert failure["descendant_quiescence_proven"] is True
    assert failure["release_blocked"] is False
    assert failure["release_dispositions"][0]["disposition"] == "released"


def test_release_exception_is_not_retried(
    tmp_path: Path,
    canonical_runtime: tuple[Path, Path],
) -> None:
    observations = (
        _observation(
            "initial",
            gpu_ids=(GPU_A,),
            free_memory={GPU_A: 1_000},
        ),
        _observation(
            "final",
            gpu_ids=(GPU_A,),
            free_memory={GPU_A: 1_000},
        ),
    )
    transaction = _Transaction(
        (GPU_A,),
        close_failure=OSError("close failed"),
    )

    with pytest.raises(TypedPreflightFailure) as raised:
        direct.DirectGpuCommandRunner(
            probe_factory=_ProbeFactory(observations),
            reservation_factory=lambda _root: transaction,
            executor=_Executor(returncode=0),
        ).run(_request(tmp_path, canonical_runtime, candidates=(GPU_A,)))

    assert raised.value.code == "gpu_reservation_release_failed"
    assert transaction.close_calls == 1
    failure = json.loads(
        (tmp_path / "evidence" / "gpu_command_failure.json").read_text()
    )
    assert failure["release_close_failure"]["type"] == "OSError"
    assert failure["release_blocked"] is False


def test_cli_does_not_require_managed_provider_executable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    allocation = direct.CandidateAllocation(
        candidate_ids=(GPU_A,),
        source="cli",
        inventory_fingerprint="candidate-inventory",
        physical_uuids=(GPU_A,),
        mig_uuids=(),
        mig_parent_by_uuid={},
    )
    captured_request: direct.DirectGpuCommandRequest | None = None

    class FakeRunner:
        def run(
            self,
            request: direct.DirectGpuCommandRequest,
        ) -> object:
            nonlocal captured_request
            captured_request = request
            return type("Result", (), {"returncode": 0})()

    monkeypatch.setenv("PATH", str(tmp_path / "provider-free-bin"))
    monkeypatch.setattr(
        direct_cli,
        "resolve_candidate_allocation",
        lambda _environment, explicit_candidates=(): allocation,
    )
    monkeypatch.setattr(direct_cli, "DirectGpuCommandRunner", FakeRunner)
    monkeypatch.setattr(direct_cli, "forward_command_output", lambda _result: None)

    code = direct_cli.main(
        [
            "--candidate-gpu",
            GPU_A,
            "--cwd",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "output"),
            "--",
            sys.executable,
            "-c",
            "print('ok')",
        ]
    )

    assert code == 0
    assert captured_request is not None
    assert captured_request.argv[0] == sys.executable
    assert "experiment-runner-admitted" not in os.environ["PATH"]


def test_direct_adapter_has_no_managed_provider_dependency() -> None:
    source = Path(direct.__file__).read_text(encoding="utf-8")
    assert "experiment-runner-admitted" not in source
    assert "run_managed_experiment" not in source
    assert "shell=False" in source
    assert "shell=True" not in source


@pytest.mark.skipif(sys.platform != "linux", reason="subreaper contract is Linux-only")
def test_linux_executor_preserves_exit_and_waits_for_descendants(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    helper = tmp_path / "executor_helper.py"
    result_path = tmp_path / "executor_result.json"
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    helper.write_text(
        textwrap.dedent(
            f"""
            import json
            import os
            import sys
            from pathlib import Path
            from types import SimpleNamespace

            sys.path.insert(0, {str(repo_root)!r})
            from tools.experiments.gpu_command_admission import LinuxSubreaperCommandExecutor

            child_code = (
                "import subprocess,sys; "
                "subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(0.2); print(\\\"grandchild\\\")']); "
                "print('parent'); print('parent-err', file=sys.stderr); "
                "raise SystemExit(9)"
            )
            plan = SimpleNamespace(
                argv=(sys.executable, '-c', child_code),
                cwd={str(tmp_path)!r},
            )
            execution = LinuxSubreaperCommandExecutor().execute(
                plan,
                dict(os.environ),
                stdout_path=Path({str(stdout_path)!r}),
                stderr_path=Path({str(stderr_path)!r}),
                poll_seconds=0.01,
            )
            Path({str(result_path)!r}).write_text(json.dumps({{
                'returncode': execution.returncode,
                'descendants': execution.lifecycle.observed_descendant_identities,
                'duration': (
                    execution.lifecycle.finished_at_monotonic
                    - execution.lifecycle.started_at_monotonic
                ),
            }}))
            """
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(helper)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text())
    assert result["returncode"] == 9
    assert result["duration"] >= 0.15
    assert result["descendants"]
    assert b"parent\n" in stdout_path.read_bytes()
    assert b"grandchild\n" in stdout_path.read_bytes()
    assert stderr_path.read_bytes() == b"parent-err\n"


@pytest.mark.skipif(sys.platform != "linux", reason="subreaper contract is Linux-only")
def test_linux_executor_does_not_wait_for_preexisting_runner_child(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    helper = tmp_path / "executor_baseline_helper.py"
    result_path = tmp_path / "executor_baseline_result.json"
    stdout_path = tmp_path / "baseline_stdout.log"
    stderr_path = tmp_path / "baseline_stderr.log"
    helper.write_text(
        textwrap.dedent(
            f"""
            import json
            import os
            import subprocess
            import sys
            import time
            from pathlib import Path
            from types import SimpleNamespace

            sys.path.insert(0, {str(repo_root)!r})
            from tools.experiments.gpu_command_admission import LinuxSubreaperCommandExecutor

            unrelated = subprocess.Popen([
                sys.executable,
                '-c',
                'import time; time.sleep(0.8)',
            ])
            plan = SimpleNamespace(
                argv=(sys.executable, '-c', 'print("owned")'),
                cwd={str(tmp_path)!r},
            )
            started = time.monotonic()
            execution = LinuxSubreaperCommandExecutor().execute(
                plan,
                dict(os.environ),
                stdout_path=Path({str(stdout_path)!r}),
                stderr_path=Path({str(stderr_path)!r}),
                poll_seconds=0.01,
            )
            duration = time.monotonic() - started
            unrelated_alive = unrelated.poll() is None
            unrelated.wait(timeout=5)
            Path({str(result_path)!r}).write_text(json.dumps({{
                'returncode': execution.returncode,
                'duration': duration,
                'unrelated_alive': unrelated_alive,
            }}))
            """
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(helper)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text())
    assert result["returncode"] == 0
    assert result["unrelated_alive"] is True


def test_busy_candidate_close_is_a_complete_release_disposition() -> None:
    dispositions = (
        FdReleaseEvidence(
            component="gpu-reservation-lock",
            uuid=GPU_A,
            disposition="busy_candidate",
            close_attempts=1,
            error_kind=None,
            fingerprint="busy-candidate-closed",
        ),
        FdReleaseEvidence(
            component="gpu-reservation-lock",
            uuid=GPU_B,
            disposition="released",
            close_attempts=1,
            error_kind=None,
            fingerprint="selected-candidate-released",
        ),
    )

    assert direct._release_dispositions_complete(dispositions) is True
