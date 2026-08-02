# @dependency-start
# contract test
# responsibility Tests test run managed experiment behavior.
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md approved AgentCanon GPU admission R5 managed-route test frame
# upstream design ../../documents/design/experiment_runner.md ExperimentRunner owner boundary
# upstream implementation ../../tools/experiments/execution_resource_plan.py canonical resource-plan/admission owner
# upstream implementation ../../tools/experiments/run_managed_experiment.py canonical managed CLI owner
# upstream implementation ./resource_plan_test_evidence.py deterministic test-only injection boundary
# upstream implementation ../../tools/ci/check_experiment_registry.py checker under test
# downstream implementation ../../documents/experiments/gpu-admission-r5-ordered-integration-interface.json W1 public selectors
# @dependency-end

"""Tests for the managed experiment run helper."""

from __future__ import annotations

import os
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]
from pathlib import Path

from tests.tools.resource_plan_test_evidence import (
    SnapshotResourceProbe,
    discover_test_resources,
)

from tools.experiments.execution_resource_plan import (
    GPUDevice,
    LockReadback,
    ProcessIdentity,
    ResourceObservation,
    ResourceRequest,
    RuntimeIdentityReceipt,
    UUIDReservationStore,
    build_lock_bound_admission_receipt,
    managed_run_adapter_integration_contract,
    plan_gpu_allocation,
)

CHECK_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "ci"
    / "check_experiment_registry.py"
)
CREATE_TOPIC_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "create_experiment_topic.py"
)
SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "run_managed_experiment.py"
)
SYNC_CONTEXT_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "sync_experiment_registry_context.py"
)
CANONICAL_ENTRYPOINT = "experiments/demo_topic/run.py"
DEFAULT_INNER_COMMAND = (
    f"python3 {CANONICAL_ENTRYPOINT} --run-dir {{run_dir}} "
    "--config {config_path} --mode default"
)
FORMAL_INNER_COMMAND = (
    f"python3 {CANONICAL_ENTRYPOINT} --run-dir {{run_dir}} "
    "--config {config_path} --mode formal"
)
RECURSIVE_RUNNER_COMMAND = (
    "python3 tools/experiments/run_managed_experiment.py --topic demo_topic"
)


def create_fake_repo_dirs(repo_root: Path) -> None:
    """Create the minimal fake repo directory layout."""
    (
        repo_root
        / "vendor"
        / "agent-canon"
        / "templates"
        / "experiments"
        / "_template"
        / "result"
    ).mkdir(parents=True)
    (repo_root / "experiments" / "demo_topic" / "result").mkdir(parents=True)
    (repo_root / "experiments" / "report").mkdir(parents=True)
    (repo_root / "tools" / "experiments").mkdir(parents=True)


def write_template_topic(repo_root: Path) -> None:
    """Write the fake template experiment topic."""
    template_dir = repo_root / "vendor" / "agent-canon" / "templates" / "experiments" / "_template"
    (template_dir / "README.md").write_text(
        "# Experiment Topic Template\n\n"
        "registered command: `python3 tools/experiments/run_managed_experiment.py "
        "--topic <topic> --use-registered-command <registered-command>`\n",
        encoding="utf-8",
    )
    (template_dir / "cases.py").write_text(
        "from __future__ import annotations\n",
        encoding="utf-8",
    )
    (template_dir / "config.yaml").write_text(
        "mode: template\n",
        encoding="utf-8",
    )
    (template_dir / "run.py").write_text(
        "from __future__ import annotations\n",
        encoding="utf-8",
    )
    (template_dir / "result" / "README.md").write_text(
        "# Result Directory\n",
        encoding="utf-8",
    )
    document_template_dir = (
        repo_root / "vendor" / "agent-canon" / "templates" / "documents" / "experiment"
    )
    document_template_dir.mkdir(parents=True, exist_ok=True)
    (document_template_dir / "README.template.md").write_text(
        "# Experiment Topic Template\n\n<topic>\n",
        encoding="utf-8",
    )
    (document_template_dir / "experiment-provenance.template.toml").write_text(
        "[experiment]\ntopic = \"<topic>\"\n",
        encoding="utf-8",
    )


def write_demo_topic_base(repo_root: Path) -> None:
    """Write non-executable fake demo topic files."""
    (repo_root / "experiments" / "demo_topic" / "README.md").write_text(
        "# Demo Topic\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "demo_topic" / "config.yaml").write_text(
        "mode: demo\n",
        encoding="utf-8",
    )
    (repo_root / "experiments" / "demo_topic" / "cases.py").write_text(
        "from __future__ import annotations\n",
        encoding="utf-8",
    )
    (repo_root / "tools" / "experiments" / "run_managed_experiment.py").write_text(
        "# placeholder\n",
        encoding="utf-8",
    )


def write_demo_runner(repo_root: Path) -> None:
    """Write only the registry entrypoint fixture; execution is out of scope."""
    (repo_root / "experiments" / "demo_topic" / "run.py").write_text(
        "from __future__ import annotations\n",
        encoding="utf-8",
    )


def write_demo_registry(repo_root: Path) -> None:
    """Write the fake experiment registry."""
    (repo_root / "experiments" / "registry.toml").write_text(
        "\n".join(
            [
                "schema_version = 1",
                "",
                "[defaults]",
                'managed_runner = "tools/experiments/run_managed_experiment.py"',
                'report_root = "experiments/report"',
                'integration_branch = "main"',
                'topic_template_dir = "vendor/agent-canon/templates/experiments/_template"',
                'required_eval_artifacts = ["summary.json", "cases.jsonl"]',
                "",
                "[[topics]]",
                'name = "demo_topic"',
                'status = "active"',
                'topic_dir = "experiments/demo_topic"',
                'topic_readme = "experiments/demo_topic/README.md"',
                f'canonical_entrypoint = "{CANONICAL_ENTRYPOINT}"',
                'result_root = "experiments/demo_topic/result"',
                'report_root = "experiments/report"',
                'default_variant = "formal"',
                f'default_inner_command = "{DEFAULT_INNER_COMMAND}"',
                f'formal_inner_command = "{FORMAL_INNER_COMMAND}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def init_fake_git_repo(repo_root: Path) -> None:
    """Initialize git metadata for the fake repo."""
    subprocess.run(
        ["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True
    )


def build_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo layout for the helper."""
    repo_root = tmp_path / "repo"
    create_fake_repo_dirs(repo_root)
    write_template_topic(repo_root)
    write_demo_topic_base(repo_root)
    write_demo_runner(repo_root)
    write_demo_registry(repo_root)
    init_fake_git_repo(repo_root)
    return repo_root


def make_resource_request(
    root: Path,
    probe: SnapshotResourceProbe | None,
    *,
    gpu_requested_count: int = 1,
    environment: dict[str, str] | None = None,
) -> ResourceRequest:
    """Build the public resource request used by managed-run contract fixtures."""
    return ResourceRequest(
        owner_id="worker-luna",
        parent_id="parent-sol",
        context_id="context-continuation",
        maximum_timeout_seconds=3600,
        argv=("python3", "experiments/demo_topic/run.py"),
        cwd=Path("/workspace"),
        environment=environment
        or {
            "CUDA_VISIBLE_DEVICES": "GPU-COMPUTE,GPU-GRAPHICS,GPU-FREE",
            "NVIDIA_VISIBLE_DEVICES": "GPU-COMPUTE,GPU-GRAPHICS,GPU-FREE",
        },
        integration_contract=managed_run_adapter_integration_contract(),
        run_id="managed-resource-contract",
        requested_chunks=("chunk-1",),
        cpu_requested_set=(0,),
        gpu_requested_count=gpu_requested_count,
        gpu_requested_memory_bytes=1024 if gpu_requested_count else 0,
        gpu_allocation_provenance=(
            "caller_scheduler_allocated_uuid_set" if gpu_requested_count else ""
        ),
        runtime_root=root / "runtime",
        source_projection_root=root / "projection",
        lock_root=root / "locks",
        lock_namespace_shared_across_schedulers=True,
        lock_namespace_host_safe=True,
        lock_namespace_visibility_witness="container-local-shared-lock",
        resource_probe=probe,
    )


def make_observation(
    *,
    devices: tuple[GPUDevice, ...],
    processes: tuple[ProcessIdentity, ...],
    event_number: int,
) -> ResourceObservation:
    """Build one coherent deterministic observation event."""
    return ResourceObservation(
        caller_allocated_ids=frozenset(device.uuid for device in devices),
        process_identities=processes,
        gpu_devices=devices,
        free_memory_bytes={
            device.uuid: device.free_memory_bytes for device in devices
        },
        boot_id="boot-contract",
        container_visible_ids=frozenset(device.uuid for device in devices),
        observed_at=f"2026-07-16T00:00:{event_number:02d}Z",
    )


def test_managed_public_route_has_one_canonical_admission_owner() -> None:
    """The managed entrypoint exposes the fixed owner graph and CLI handshake."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "execute_managed_run" in source
    assert "NvidiaSMIResourceProbe.discover" in source
    assert "GpuProcessOccupancyProbe" in source
    assert "GpuReservationTransaction" in source
    assert "freeze_resource_plan" in source
    assert "ManagedGpuOutcomeReducer().reduce_terminal" in source
    assert "CompletionCoverageAdapter(coverage_path).record_once" in source
    assert "PostToolUseProjectionReducer().project" in source
    assert "discover_resources(request)" not in source
    assert "plan_gpu_allocation(request, discovered)" not in source
    assert "UUIDReservationStore" not in source
    assert "ExperimentRunner" + "PreLaunchAdapter" not in source
    assert "execute_with_" + "experiment_runner" not in source
    assert "RunGpuAdmissionContext" in source
    assert "experiment-runner-admitted" in source
    assert "subprocess.Popen" in source
    assert "shell=False" in source
    assert "build_lock_bound_admission_receipt" in source
    assert "StandardFullResourceScheduler.from_worker" not in source
    assert "StandardRunner(" not in source
    assert "Canonical" + "ExperimentRunnerBinding" not in source
    assert "_W1" + "UUIDScheduler" not in source
    assert "materialized.plan" not in source
    assert "side_effect_disposers" not in source
    assert "topic_callable" not in source
    assert "experiment_runner_binding_required" not in source


def _runtime_identity() -> RuntimeIdentityReceipt:
    return RuntimeIdentityReceipt(
        schema_version="runtime-identity/v1",
        runtime_route="MANAGED_CONTAINER",
        namespace_inode=4026531836,
        uid=1000,
        gid=1000,
        supplementary_gids=(1000,),
        umask=0o007,
        bind_source_dev=1,
        bind_source_ino=2,
        bind_target_dev=1,
        bind_target_ino=3,
        provision_fingerprint="a" * 64,
        readback_fingerprint="b" * 64,
        receipt_fingerprint="c" * 64,
    )


def _valid_environment_plan(uuid: str) -> SimpleNamespace:
    lock = LockReadback(
        runtime_root="/var/lib/agent-canon/runtime",
        filesystem_type="ext4",
        device=7,
        inode=11,
        selected=(),
        fingerprint="1" * 64,
    )
    receipt = build_lock_bound_admission_receipt(
        candidate_uuids=(uuid,),
        occupied_uuids=(),
        reserved_uuids=(),
        selected_uuids=(uuid,),
        inventory_fingerprint="2" * 64,
        occupancy_fingerprint="3" * 64,
        reservation_fingerprint="4" * 64,
        runtime_identity_fingerprint="5" * 64,
        lock_readback=lock,
    )
    return SimpleNamespace(
        gpu_allocation=SimpleNamespace(
            selected_ids=(uuid,),
            admission_fingerprint=receipt.admission_fingerprint,
        ),
        resources={"gpu": {"admission_fingerprint": receipt.admission_fingerprint}},
        execution={"env": {"RUN_MODE": "managed"}},
    )


def test_r5_admitted_environment_and_context_are_composition_only() -> None:
    """Composition uses a valid lock-bound composite and materializes UUIDs post-freeze."""
    from tools.experiments.run_managed_experiment import (
        RunGpuAdmissionContext,
        build_admitted_environment,
    )

    uuid = "GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    plan = _valid_environment_plan(uuid)
    env = build_admitted_environment(
        plan,
        _runtime_identity(),
        admission_fingerprint=plan.gpu_allocation.admission_fingerprint,
    )
    assert dict(env.exact_env_map)["CUDA_VISIBLE_DEVICES"] == uuid
    assert env.admission_fingerprint
    request = ResourceRequest(
        owner_id="worker",
        parent_id="parent",
        context_id="context",
        maximum_timeout_seconds=60,
        argv=("python3", "experiments/demo_topic/run.py"),
        cwd=Path("/workspace"),
        environment={},
        integration_contract=managed_run_adapter_integration_contract(),
        requested_chunks=("test",),
    )
    context = RunGpuAdmissionContext.create(request)
    with context:
        assert context.state == "ACTIVE"
    assert context.state == "CLOSED"


def test_r5_admitted_environment_missing_composite_fails_closed() -> None:
    """The post-freeze environment refuses an unbound GPU allocation."""
    from tools.experiments.run_managed_experiment import build_admitted_environment
    uuid = "GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    plan = SimpleNamespace(
        gpu_allocation=SimpleNamespace(selected_ids=(uuid,), admission_fingerprint=None),
        resources={"gpu": {"admission_fingerprint": None}},
        execution={"env": {}},
    )
    with pytest.raises(Exception) as raised:
        build_admitted_environment(
            plan,
            _runtime_identity(),
            admission_fingerprint="",
        )
    assert getattr(raised.value, "code", None) == "admission_fingerprint_missing"


def test_r5_runner_lifecycle_fingerprint_uses_protocol_projection() -> None:
    """The terminal reducer fingerprints the admitted CLI lifecycle projection."""
    import hashlib
    from tools.experiments.execution_resource_plan import ManagedGpuOutcomeReducer
    from tools.experiments.run_managed_experiment import ManagedRunLifecycleEvidence

    lifecycle = ManagedRunLifecycleEvidence(
        run_id="r5-lifecycle",
        terminal_event_id="terminal-1",
        observed_at_ns=1,
        terminal_status="finished",
        total_case_count_at_start=1,
        completion_count_before=0,
        completion_count_after=1,
        scheduler_completed=True,
        admitted_case_count=1,
        terminal_notification_count=1,
        child_process_ids=(),
        process_group_ids=(),
        direct_children_quiescent=True,
        descendant_quiescence="PROVEN",
    )
    outcome = ManagedGpuOutcomeReducer().reduce_terminal(
        run_id="r5-lifecycle",
        planned_chunk_ids=("chunk-1",),
        admission=None,
        source_freeze=None,
        runtime_identity=None,
        runner_lifecycle=lifecycle,
        primary_failure=None,
        secondary_failures=(),
        release_disposition=(),
        context_state="closed",
        exit_code=0,
    )
    expected = hashlib.sha256(
        json.dumps(lifecycle.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert outcome.runner_lifecycle_fingerprint == expected


def test_r5_admitted_runner_fake_cli_protocol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The managed owner invokes a fake admitted CLI with no Python runner import."""
    from tools.experiments.run_managed_experiment import _run_admitted_runner

    fake = tmp_path / "experiment-runner-admitted"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib, json, os, sys\n"
        "if sys.argv[1:] == ['--version']:\n"
        "    print('experiment-runner-admitted/v1')\n"
        "    raise SystemExit(0)\n"
        "request_path = sys.argv[sys.argv.index('--request') + 1]\n"
        "result_path = sys.argv[sys.argv.index('--result') + 1]\n"
        "request = json.loads(open(request_path, encoding='utf-8').read())\n"
        "result = {'schema_version': 'agentcanon-managed-run-result/v1',\n"
        " 'request_fingerprint': request['request_fingerprint'],\n"
        " 'admission_fingerprint': request['admission_fingerprint'],\n"
        " 'worker': {'pid': os.getpid(), 'descendants': [], 'quiescence': 'PROVEN'},\n"
        " 'lifecycle': {'terminal_event_id': 'terminal-1', 'scheduler_completed': True},\n"
        " 'exit': {'code': 0, 'error': None}}\n"
        "result['result_fingerprint'] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()\n"
        "open(result_path, 'w', encoding='utf-8').write(json.dumps(result))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    result_dir = tmp_path / "run"
    snapshot = result_dir / "source_snapshot"
    snapshot.mkdir(parents=True)
    paths = SimpleNamespace(
        result_dir=result_dir,
        stdout_log_path=result_dir / "stdout.log",
        stderr_log_path=result_dir / "stderr.log",
    )
    context = SimpleNamespace(paths=paths)
    monkeypatch.setenv("AGENT_CANON_EXPERIMENT_RUNNER_ADMITTED", str(fake))
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "request_fingerprint": "a" * 64,
                "admission_fingerprint": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    execution, lifecycle, result = _run_admitted_runner(
        context=context,
        request_path=request_path,
        result_path=tmp_path / "result.json",
        lifecycle_path=tmp_path / "lifecycle.json",
        request_payload={
            "run_id": "run-1",
            "request_fingerprint": "a" * 64,
            "admission_fingerprint": "b" * 64,
        },
        environment={"PATH": os.environ["PATH"]},
    )
    assert execution.raw_exit_code == 0
    assert lifecycle.descendant_quiescence == "PROVEN"
    assert result["request_fingerprint"] == "a" * 64
    assert (result_dir / "runtime" / "managed-run-receipt.json").is_file()


def test_r5_runner_lifecycle_capture_is_shell_free_and_import_free() -> None:
    """The composition root uses shell-free subprocess and has no local runner fallback."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "shell=False" in source
    assert "from experiment_runner import" not in source
    assert "PYTHONPATH" not in source
    assert "runpy" not in source


def test_public_alternate_gpu_routes_are_typed_or_managed() -> None:
    """Template and JIT entrypoints cannot launch GPU work beside the managed owner."""
    template_source = (
        Path(__file__).resolve().parents[2] / "templates" / "experiments" / "_template" / "run.py"
    ).read_text(encoding="utf-8")
    jit_source = (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "agent_tools"
        / "jit_canonical_ir.py"
    ).read_text(encoding="utf-8")
    planner_source = (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "experiments"
        / "execution_resource_plan.py"
    ).read_text(encoding="utf-8")
    assert "managed_runner_required=tools/experiments/run_managed_experiment.py" in template_source
    assert "gpu_route_blocked=canonical_managed_experiment_runner_required" in jit_source
    assert "gpu_structured_probe_unavailable" in planner_source
    assert "discover_injected_test_resources" not in planner_source
    assert '    "SnapshotResourceProbe",' not in planner_source


def test_public_gpu_plan_excludes_compute_and_graphics_contexts_with_fresh_readbacks(
    tmp_path: Path,
) -> None:
    """The public planner excludes both process classes and records fresh S_lock/S_final."""
    devices = (
        GPUDevice("GPU-COMPUTE", 8192, 16384),
        GPUDevice("GPU-FREE", 8192, 16384),
        GPUDevice("GPU-GRAPHICS", 8192, 16384),
    )
    processes = (
        ProcessIdentity(
            pid=4101,
            process_start_identity="start-compute",
            gpu_uuid="GPU-COMPUTE",
            kind="compute",
            parent_pid=4001,
            relationship="child",
        ),
        ProcessIdentity(
            pid=4102,
            process_start_identity="start-graphics",
            gpu_uuid="GPU-GRAPHICS",
            kind="graphics",
            parent_pid=4001,
            relationship="child",
        ),
    )
    observations = tuple(
        make_observation(
            devices=devices,
            processes=processes,
            event_number=event_number,
        )
        for event_number in range(4)
    )
    probe = SnapshotResourceProbe(
        allocated=frozenset(device.uuid for device in devices),
        processes=processes,
        memory={device.uuid: device.free_memory_bytes for device in devices},
        current_boot_id="boot-contract",
        visible=frozenset(device.uuid for device in devices),
        observation_sequence=observations,
    )
    request = make_resource_request(tmp_path, probe)
    discovered = discover_test_resources(
        request,
        probe,
        cpu_available_set=(0,),
        gpu_devices=devices,
        container_id="container-contract",
        structure_tool={
            "available": "true",
            "structure_contract_ref": "documents/structure/repo-structure-contract.toml",
        },
        tool_availability={
            "tree": {"available": True},
            "nvidia-smi": {"available": True, "structured": True},
        },
    )
    allocation = plan_gpu_allocation(request, discovered)

    assert allocation.occupied_ids == ("GPU-COMPUTE", "GPU-GRAPHICS")
    assert allocation.selected_ids == ("GPU-FREE",)
    assert allocation.selected_ids == tuple(sorted(allocation.selected_ids))
    assert allocation.lock_readback["initial_observation"]["event"] == "S0"
    assert allocation.lock_readback["final_observation"]["event"] == "S_final"
    attempts = allocation.lock_readback["attempts"]
    assert attempts[0]["observation_event"] == "S_lock"


def test_public_lease_retains_busy_context_then_releases_after_readback(
    tmp_path: Path,
) -> None:
    """The public lease boundary retains a live holder and releases only after it is absent."""
    store = UUIDReservationStore(
        tmp_path / "locks",
        shared_across_schedulers=True,
        host_safe=True,
        visibility_witness="container-local-shared-lock",
    )
    lease = store.acquire(
        "GPU-HELD",
        owner_pid=1,
        owner_process_start_identity="start-owner",
        boot_id="boot-contract",
    )
    assert lease is not None
    process = ProcessIdentity(
        pid=4201,
        process_start_identity="start-holder",
        gpu_uuid="GPU-HELD",
        kind="graphics",
        parent_pid=4001,
        relationship="descendant",
    )
    retained_observation = make_observation(
        devices=(GPUDevice("GPU-HELD", 4096, 8192),),
        processes=(process,),
        event_number=1,
    )
    retained = lease.release(
        observation_supplier=lambda: retained_observation,
    )
    assert retained["result"] == "retained_live_gpu_holder"
    assert lease.active

    released = lease.release(
        observation_supplier=lambda: make_observation(
            devices=(GPUDevice("GPU-HELD", 4096, 8192),),
            processes=(),
            event_number=2,
        ),
    )
    assert released["result"] == "released"
    assert not lease.active


def test_public_gpu_discovery_fails_typed_when_structured_probe_is_missing(
    tmp_path: Path,
) -> None:
    """The production entrypoint never substitutes an empty observation or CPU fallback."""
    from unittest.mock import patch

    from tools.experiments.execution_resource_plan import (
        TypedPreflightFailure,
        discover_resources,
    )

    request = make_resource_request(tmp_path, None)
    with patch(
        "tools.experiments.execution_resource_plan.shutil.which",
        return_value=None,
    ):
        try:
            discover_resources(request)
        except TypedPreflightFailure as exc:
            assert exc.code == "gpu_structured_probe_unavailable"
        else:
            raise AssertionError("GPU discovery unexpectedly succeeded without nvidia-smi")

def test_check_experiment_registry_accepts_valid_registry(tmp_path: Path) -> None:
    """The registry checker should pass for the generated demo registry."""
    repo_root = build_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "OK: experiment registry is valid" in result.stdout


def test_check_experiment_registry_accepts_valid_branch_topic(tmp_path: Path) -> None:
    """The registry checker should accept branch-only topic entries."""
    repo_root = build_repo(tmp_path)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Registry Test",
            "-c",
            "user.email=registry-test@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "initial",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "branch", "experiment/branch-only"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    (repo_root / "notes" / "branches").mkdir(parents=True)
    (repo_root / "notes" / "branches" / "branch_only.md").write_text(
        "# Branch Only\n",
        encoding="utf-8",
    )
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_path.write_text(
        registry_path.read_text(encoding="utf-8")
        + "\n".join(
            [
                "[[branch_topics]]",
                'name = "branch_only"',
                'status = "active"',
                'remote_branch = "experiment/branch-only"',
                'primary_note = "notes/branches/branch_only.md"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "OK: experiment registry is valid" in result.stdout


def test_check_experiment_registry_rejects_duplicate_branch_topic_name(
    tmp_path: Path,
) -> None:
    """The registry checker should reject duplicate names across topic tables."""
    repo_root = build_repo(tmp_path)
    (repo_root / "notes" / "branches").mkdir(parents=True)
    (repo_root / "notes" / "branches" / "demo_topic.md").write_text(
        "# Demo Topic Branch\n",
        encoding="utf-8",
    )
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_path.write_text(
        registry_path.read_text(encoding="utf-8")
        + "\n".join(
            [
                "[[branch_topics]]",
                'name = "demo_topic"',
                'status = "active"',
                'remote_branch = "experiment/demo-topic"',
                'primary_note = "notes/branches/demo_topic.md"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "duplicate topic name: demo_topic" in result.stdout


def test_check_experiment_registry_defaults_to_repo_root_via_symlink(
    tmp_path: Path,
) -> None:
    """The checker should infer the derived repo root from the invoked symlink path."""
    repo_root = build_repo(tmp_path)
    script_path = repo_root / "tools" / "ci" / "check_experiment_registry.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.symlink_to(CHECK_SCRIPT)

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert f"repo_root={repo_root}" in result.stdout
    assert "OK: experiment registry is valid" in result.stdout


def test_check_experiment_registry_rejects_recursive_runner_command(
    tmp_path: Path,
) -> None:
    """The checker should fail when an inner command recursively calls the wrapper."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'default_inner_command = "{DEFAULT_INNER_COMMAND}"',
        f'default_inner_command = "{RECURSIVE_RUNNER_COMMAND}"',
    )
    registry_path.write_text(registry_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "must not call the managed runner recursively" in result.stdout


def test_check_experiment_registry_accepts_command_without_run_dir(
    tmp_path: Path,
) -> None:
    """The registry checker should allow a direct entrypoint command."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'default_inner_command = "{DEFAULT_INNER_COMMAND}"',
        (
            f'default_inner_command = "/usr/bin/python /workspace/'
            f'{CANONICAL_ENTRYPOINT} --config {{config_path}}"'
        ),
    )
    registry_path.write_text(registry_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "OK: experiment registry is valid" in result.stdout


def test_check_experiment_registry_rejects_command_without_config_path(
    tmp_path: Path,
) -> None:
    """The registry checker should require commands to consume config snapshots."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'default_inner_command = "{DEFAULT_INNER_COMMAND}"',
        f'default_inner_command = "/usr/bin/python /workspace/{CANONICAL_ENTRYPOINT}"',
    )
    registry_path.write_text(registry_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "must include {config_path}" in result.stdout


def test_check_experiment_registry_rejects_non_topic_local_entrypoint(
    tmp_path: Path,
) -> None:
    """The registry checker should require experiments/<topic>/run.py entrypoints."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        f'canonical_entrypoint = "{CANONICAL_ENTRYPOINT}"',
        'canonical_entrypoint = "python/package/experiment.py"',
    )
    registry_text = registry_text.replace(
        CANONICAL_ENTRYPOINT, "python/package/experiment.py"
    )
    registry_path.write_text(registry_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "canonical_entrypoint must be the topic-local run.py" in result.stdout


def test_check_experiment_registry_rejects_reserved_eval_artifact_pattern(
    tmp_path: Path,
) -> None:
    """The registry checker should reject reserved managed artifact patterns."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_text = registry_path.read_text(encoding="utf-8").replace(
        'required_eval_artifacts = ["summary.json", "cases.jsonl"]',
        (
            'required_eval_artifacts = ["summary.json", "cases.jsonl", '
            '"run.log", "logs/stdout.log"]'
        ),
    )
    registry_path.write_text(registry_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT),
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "reserved managed artifacts" in result.stdout


def test_create_experiment_topic_scaffolds_directory_and_registry(
    tmp_path: Path,
) -> None:
    """The scaffold script should copy the template and append a registry entry."""
    repo_root = build_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(CREATE_TOPIC_SCRIPT),
            "--repo-root",
            str(repo_root),
            "--active-branch",
            "work/new-topic-20260406",
            "new_topic",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    topic_dir = repo_root / "experiments" / "new_topic"
    assert topic_dir.is_dir()
    readme_text = (topic_dir / "README.md").read_text(encoding="utf-8")
    assert "# new_topic" in readme_text
    assert "<topic>" not in readme_text
    registry_text = (repo_root / "experiments" / "registry.toml").read_text(
        encoding="utf-8"
    )
    assert 'name = "new_topic"' in registry_text
    assert 'active_branch = "work/new-topic-20260406"' in registry_text
    registry_data = tomllib.loads(registry_text)
    new_topic = next(
        topic for topic in registry_data["topics"] if topic["name"] == "new_topic"
    )
    assert "formal_inner_command" not in new_topic
    assert "EXPERIMENT_CONFIG_PATH" not in new_topic["default_inner_command"]


def test_sync_experiment_registry_context_updates_branch_scope_and_worktree(
    tmp_path: Path,
) -> None:
    """The sync script should update branch and worktree metadata for one topic."""
    repo_root = build_repo(tmp_path)
    workspace_root = repo_root / ".worktrees" / "demo-topic"
    workspace_root.mkdir(parents=True)
    (workspace_root / "WORKTREE_SCOPE.md").write_text("# Scope\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SYNC_CONTEXT_SCRIPT),
            "--repo-root",
            str(repo_root),
            "--workspace-root",
            str(workspace_root),
            "--branch",
            "work/demo-topic-20260406",
            "--branch-note",
            "notes/branches/demo_topic.md",
            "--topic",
            "demo_topic",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    registry_text = (repo_root / "experiments" / "registry.toml").read_text(
        encoding="utf-8"
    )
    assert 'active_branch = "work/demo-topic-20260406"' in registry_text
    assert 'active_worktree = ".worktrees/demo-topic"' in registry_text
    assert 'scope_file = ".worktrees/demo-topic/WORKTREE_SCOPE.md"' in registry_text
    assert 'branch_note = "notes/branches/demo_topic.md"' in registry_text
