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
# upstream environment ../../agent-canon-environment.toml audited ExperimentRunner provider identity and runtime item
# @dependency-end

"""Tests for the managed experiment run helper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

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
from tools.experiments.experiment_identity import ExperimentIdentity
from tools.experiments.run_managed_experiment import (
    ReservationReceipt,
    RunContext,
    build_run_paths,
    reserve_run_paths,
    rollback_empty_reservation,
)

from tests.tools.resource_plan_test_evidence import (
    SnapshotResourceProbe,
    discover_test_resources,
)

SYNC_CONTEXT_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "sync_experiment_registry_context.py"
)
SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "experiments" / "run_managed_experiment.py"
CHECK_SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "ci" / "check_experiment_registry.py"
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
    "python3 -m tools.experiments.run_managed_experiment "
    "--topic demo_topic --variant default"
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
        "registered command: `python3 -m tools.experiments.run_managed_experiment "
        "--topic <topic> --variant <variant> "
        "--use-registered-command <registered-command>`\n",
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


def reservation_context(repo_root: Path, run_name: str = "run.a") -> RunContext:
    """Build the smallest real context needed by reservation tests."""
    identity = ExperimentIdentity("demo_topic", "smoke.v1", run_name)
    topic_dir = repo_root / "experiments" / identity.topic
    paths = build_run_paths(
        topic_dir,
        identity,
        repo_root
        / "experiments"
        / "report"
        / identity.topic
        / identity.variant
        / f"{identity.run_name}.md",
    )
    return RunContext(
        repo_root=repo_root,
        identity=identity,
        topic_dir=topic_dir,
        paths=paths,
        registry=SimpleNamespace(  # type: ignore[arg-type]
            path=repo_root / "experiments" / "registry.toml",
            entry={},
            defaults={},
            available=False,
        ),
        command=SimpleNamespace(command=[]),  # type: ignore[arg-type]
        created_at="2026-01-01T00:00:00Z",
        git=SimpleNamespace(branch="main", commit="commit", status_short=[]),  # type: ignore[arg-type]
    )


def init_fake_git_repo(repo_root: Path) -> None:
    """Initialize git metadata for the fake repo."""
    subprocess.run(
        ["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True
    )


def test_managed_runner_requires_variant_at_cli_boundary(tmp_path: Path) -> None:
    """Omitting variant fails before topic or result filesystem mutation."""
    result = subprocess.run(
        [sys.executable, "-m", "tools.experiments.run_managed_experiment", "--topic", "demo_topic", "--", "true"],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--variant" in result.stderr
    assert not (tmp_path / "experiments").exists()


def test_existing_report_fails_before_result_reservation(tmp_path: Path) -> None:
    """An existing report blocks the run without creating a result directory."""
    repo_root = build_repo(tmp_path)
    context = reservation_context(repo_root)
    context.paths.report_path.parent.mkdir(parents=True)
    context.paths.report_path.write_text("existing\n", encoding="utf-8")

    with pytest.raises(ValueError, match="report already exists"):
        reserve_run_paths(context, skip_report_init=False)

    assert not context.paths.result_dir.exists()
    assert context.paths.report_path.read_text(encoding="utf-8") == "existing\n"


def test_owned_empty_reservation_rolls_back_without_residue(tmp_path: Path) -> None:
    """An owned empty reservation removes only its own result and report paths."""
    repo_root = build_repo(tmp_path)
    context = reservation_context(repo_root)
    receipt = reserve_run_paths(context, skip_report_init=False)

    assert context.paths.result_dir.is_dir()
    assert context.paths.report_path.is_file()
    assert rollback_empty_reservation(receipt)
    assert not context.paths.result_dir.exists()
    assert not context.paths.report_path.exists()


def test_skip_report_init_rolls_back_result_without_report_parent(
    tmp_path: Path,
) -> None:
    """An uncreated report parent is neutral during result-only rollback."""
    repo_root = build_repo(tmp_path)
    context = reservation_context(repo_root)
    report_parent = context.paths.report_path.parent
    assert not report_parent.exists()

    receipt = reserve_run_paths(context, skip_report_init=True)

    assert context.paths.result_dir.is_dir()
    assert not report_parent.exists()
    assert rollback_empty_reservation(receipt)
    assert not context.paths.result_dir.exists()
    assert not report_parent.exists()
    assert (repo_root / "experiments" / "report").is_dir()


@pytest.mark.parametrize("escaped_component", ("result", "variant"))
def test_build_run_paths_rejects_symlinked_result_components(
    tmp_path: Path, escaped_component: str
) -> None:
    """Reject a result or variant root that would redirect reservation writes."""
    repo_root = build_repo(tmp_path)
    identity = ExperimentIdentity("demo_topic", "smoke.v1", "run.a")
    topic_dir = repo_root / "experiments" / identity.topic
    result_root = topic_dir / "result"
    outside = tmp_path / "outside"
    outside.mkdir()
    if escaped_component == "result":
        result_root.rename(topic_dir / "result-real")
        result_root.symlink_to(outside, target_is_directory=True)
    else:
        variant_root = result_root / identity.variant
        variant_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        build_run_paths(
            topic_dir,
            identity,
            repo_root
            / "experiments"
            / "report"
            / identity.topic
            / identity.variant
            / f"{identity.run_name}.md",
        )
    assert not list(outside.iterdir())


def test_rollback_rejects_replaced_result_parent_inode(tmp_path: Path) -> None:
    """Do not remove a reservation when its newly-created result parent changed."""
    repo_root = build_repo(tmp_path)
    context = reservation_context(repo_root)
    receipt = reserve_run_paths(context, skip_report_init=False)
    assert not receipt.result_parent_preexisted

    replaced = replace(
        receipt,
        result_parent_inode=receipt.result_parent_inode + 1,
    )
    assert not rollback_empty_reservation(replaced)
    assert context.paths.result_dir.is_dir()
    assert context.paths.report_path.is_file()


def test_rollback_rejects_replaced_report_parent_inode(tmp_path: Path) -> None:
    """Do not remove a reservation when its newly-created report parent changed."""
    repo_root = build_repo(tmp_path)
    context = reservation_context(repo_root)
    receipt = reserve_run_paths(context, skip_report_init=False)
    assert not receipt.report_parent_preexisted
    assert receipt.report_parent_inode is not None

    replaced = replace(
        receipt,
        report_parent_inode=cast(int, receipt.report_parent_inode) + 1,
    )
    assert not rollback_empty_reservation(replaced)
    assert context.paths.result_dir.is_dir()
    assert context.paths.report_path.is_file()


@pytest.mark.parametrize(
    ("script_path", "module_name"),
    (
        (
            "tools/experiments/run_managed_experiment.py",
            "tools.experiments.run_managed_experiment",
        ),
        (
            "tools/experiments/publish_result_branch.py",
            "tools.experiments.publish_result_branch",
        ),
        (
            "tools/experiments/update_latest_result.py",
            "tools.experiments.update_latest_result",
        ),
        (
            "tools/experiments/create_experiment_topic.py",
            "tools.experiments.create_experiment_topic",
        ),
        (
            "tools/ci/check_experiment_registry.py",
            "tools.ci.check_experiment_registry",
        ),
    ),
)
def test_public_experiment_entrypoints_support_direct_and_module_forms(
    script_path: str, module_name: str
) -> None:
    """Both documented invocation forms work without PYTHONPATH setup."""
    repo_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    direct = subprocess.run(
        [sys.executable, script_path, "--help"],
        cwd=repo_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    module = subprocess.run(
        [sys.executable, "-m", module_name, "--help"],
        cwd=repo_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert direct.returncode == 0, direct.stderr
    assert module.returncode == 0, module.stderr
    assert "usage:" in direct.stdout
    assert "usage:" in module.stdout


def test_nonempty_reservation_is_never_rolled_back(tmp_path: Path) -> None:
    """Rollback preserves a result once any artifact has been written."""
    repo_root = build_repo(tmp_path)
    context = reservation_context(repo_root)
    receipt = reserve_run_paths(context, skip_report_init=False)
    artifact = context.paths.result_dir / "partial.json"
    artifact.write_text("{}\n", encoding="utf-8")

    assert not rollback_empty_reservation(receipt)
    assert artifact.is_file()
    assert context.paths.report_path.is_file()


def test_rollback_preserves_same_bytes_replacement(tmp_path: Path) -> None:
    """Rollback does not unlink a replacement report with identical bytes."""
    repo_root = build_repo(tmp_path)
    context = reservation_context(repo_root)
    receipt = reserve_run_paths(context, skip_report_init=False)
    original = context.paths.report_path.read_bytes()
    replacement = context.paths.report_path.with_name("replacement-report.md")
    replacement.write_bytes(original)
    replacement.replace(context.paths.report_path)

    assert context.paths.report_path.stat().st_ino != receipt.report_inode
    assert not rollback_empty_reservation(receipt)
    assert context.paths.result_dir.is_dir()
    assert context.paths.report_path.read_bytes() == original


def test_rollback_preserves_reused_empty_result_directory(tmp_path: Path) -> None:
    """Rollback does not remove a replacement empty directory at the same path."""
    repo_root = build_repo(tmp_path)
    context = reservation_context(repo_root)
    receipt = reserve_run_paths(context, skip_report_init=True)
    receipt.marker_path.unlink()
    receipt.result_dir.rmdir()
    replacement_sibling = receipt.result_dir.with_name("replacement-sibling")
    replacement_sibling.mkdir()
    receipt.result_dir.mkdir()

    assert context.paths.result_dir.stat().st_ino != receipt.result_inode
    assert not rollback_empty_reservation(receipt)
    assert context.paths.result_dir.is_dir()


def test_rollback_preserves_same_bytes_replacement_marker(tmp_path: Path) -> None:
    """Rollback requires the exclusive marker inode, not merely equal bytes."""
    repo_root = build_repo(tmp_path)
    context = reservation_context(repo_root)
    receipt = reserve_run_paths(context, skip_report_init=True)
    marker_bytes = receipt.marker_path.read_bytes()
    replacement = receipt.marker_path.with_name("replacement-marker.json")
    replacement.write_bytes(marker_bytes)
    replacement.replace(receipt.marker_path)

    assert receipt.marker_path.stat().st_ino != receipt.marker_inode
    assert not rollback_empty_reservation(receipt)
    assert context.paths.result_dir.is_dir()


def test_reservation_race_has_one_winner_and_no_loser_residue(tmp_path: Path) -> None:
    """Exclusive result reservation leaves no directory from the losing call."""
    repo_root = build_repo(tmp_path)
    contexts = [reservation_context(repo_root), reservation_context(repo_root)]

    def reserve(context: RunContext) -> tuple[str, ReservationReceipt | None]:
        try:
            return "winner", reserve_run_paths(context, skip_report_init=False)
        except (FileExistsError, ValueError) as exc:
            del exc
            return "loser", None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, contexts))

    assert [kind for kind, _ in outcomes].count("winner") == 1
    assert [kind for kind, _ in outcomes].count("loser") == 1
    winner = cast(
        ReservationReceipt,
        next(value for kind, value in outcomes if kind == "winner"),
    )
    assert rollback_empty_reservation(winner)
    assert not contexts[0].paths.result_dir.exists()
    assert not contexts[0].paths.report_path.exists()


def test_report_reservation_race_has_one_winner_and_no_loser_residue(
    tmp_path: Path,
) -> None:
    """Exclusive report creation cleans the losing result directory only."""
    repo_root = build_repo(tmp_path)
    shared_report = repo_root / "experiments" / "report" / "shared.md"
    contexts = [
        reservation_context(repo_root, "run.a"),
        reservation_context(repo_root, "run.b"),
    ]
    contexts = [
        replace(context, paths=replace(context.paths, report_path=shared_report))
        for context in contexts
    ]

    def reserve(context: RunContext) -> tuple[str, ReservationReceipt | None]:
        try:
            return "winner", reserve_run_paths(context, skip_report_init=False)
        except (FileExistsError, ValueError) as exc:
            del exc
            return "loser", None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, contexts))

    assert [kind for kind, _ in outcomes].count("winner") == 1
    assert [kind for kind, _ in outcomes].count("loser") == 1
    winner = cast(
        ReservationReceipt,
        next(value for kind, value in outcomes if kind == "winner"),
    )
    assert rollback_empty_reservation(winner)
    assert not shared_report.exists()
    assert not contexts[0].paths.result_dir.exists()
    assert not contexts[1].paths.result_dir.exists()


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
        descendant_quiescence="no_child",
        cleanup_failures=(),
        terminal_coverage_complete=True,
        requested_case_coverage_complete=True,
        quiescence_complete=True,
        completion_coverage_complete=True,
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
    """The managed owner invokes the approved provider wire protocol exactly once."""
    from tools.experiments.run_managed_experiment import _run_admitted_runner

    fake = tmp_path / "experiment-runner-admitted"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "request_path = sys.argv[sys.argv.index('--request') + 1]\n"
        "result_path = sys.argv[sys.argv.index('--result') + 1]\n"
        "request = json.loads(open(request_path, encoding='utf-8').read())\n"
        "pid = os.getpid()\n"
        "lifecycle = {'run_id': request['run_id'], 'terminal_event_id': 'terminal-1',\n"
        " 'observed_at_ns': 1, 'terminal_status': 'finished',\n"
        " 'total_case_count_at_start': 1, 'completion_count_before': 0,\n"
        " 'completion_count_after': 1, 'completion_delta': 1,\n"
        " 'scheduler_completed': True, 'admitted_case_count': 1,\n"
        " 'terminal_notification_count': 1, 'child_process_ids': [pid],\n"
        " 'process_group_ids': [pid], 'direct_children_quiescent': True,\n"
        " 'descendant_quiescence': 'proved', 'cleanup_failures': [],\n"
        " 'terminal_coverage_complete': True,\n"
        " 'requested_case_coverage_complete': True, 'quiescence_complete': True,\n"
        " 'completion_coverage_complete': True}\n"
        "result = {'schema': 'agentcanon-managed-run-result/v1',\n"
        " 'identity': request['identity'],\n"
        " 'request_fingerprint': request['fingerprint'], 'run_id': request['run_id'],\n"
        " 'status': 'ok', 'worker_pid': pid, 'worker_pids': [pid],\n"
        " 'lifecycle': lifecycle, 'descendant_quiescence': 'proved',\n"
        " 'quiescence': {'direct_children_quiescent': True,\n"
        " 'descendant_quiescence': 'proved', 'complete': True, 'cleanup_failures': []},\n"
        " 'exit': {'code': 0, 'error': None}, 'exit_code': 0, 'error': None,\n"
        " 'completions': [{'case': {}, 'result': {'status': 'ok'}}]}\n"
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
                "identity": ExperimentIdentity("demo", "smoke", "run-1").to_dict()["identity"],
                "run_id": "run-1",
                "schema": "agentcanon-managed-run/v1",
                "fingerprint": "a" * 64,
                "task": {"module": "experiments.demo_topic.run", "callable": "main"},
                "cases": [{}],
                "capacity": {"max_workers": 1, "host_memory_bytes": 0, "gpu_devices": []},
                "resource_estimate": {
                    "host_memory_bytes": 0,
                    "gpu_count": 0,
                    "gpu_memory_bytes": 0,
                    "gpu_slots": 1,
                },
                "selected_gpu_ids": [],
                "environment": {},
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
            "identity": ExperimentIdentity("demo", "smoke", "run-1").to_dict()["identity"],
            "run_id": "run-1",
            "schema": "agentcanon-managed-run/v1",
            "fingerprint": "a" * 64,
        },
        environment={"PATH": os.environ["PATH"]},
    )
    assert execution.raw_exit_code == 0
    assert lifecycle.descendant_quiescence == "proved"
    assert result["request_fingerprint"] == "a" * 64
    assert (result_dir / "runtime" / "managed-run-receipt.json").is_file()


def test_r5_provider_request_wire_fields_forward_opaque_gpu_identifiers() -> None:
    """The request forwards admission GPU identities without ordinal conversion."""
    from tools.experiments.run_managed_experiment import _provider_gpu_ids

    source = SCRIPT.read_text(encoding="utf-8")
    request_builder = source[
        source.index("def _build_managed_run_request") : source.index("def _resolve_admitted_runner")
    ]
    assert '"schema": MANAGED_RUN_REQUEST_SCHEMA' in request_builder
    assert '"task":' in request_builder
    assert '"resource_estimate":' in request_builder
    assert '"selected_gpu_ids":' in request_builder
    assert '"fingerprint"]' in request_builder
    assert '"module_spec":' not in request_builder
    assert '"schema_version": MANAGED_RUN_REQUEST_SCHEMA' not in request_builder
    selected = (
        "MIG-GPU-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/1/2",
        "GPU-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    assert _provider_gpu_ids(selected) == selected
    assert tuple(
        line.strip()
        for line in request_builder.splitlines()
        if '"gpu_id": gpu_id' in line
    ) == ('"gpu_id": gpu_id,',)
    assert "for uuid, gpu_id in zip(selected_uuids, selected_gpu_ids)" in request_builder


def test_r5_provider_identity_is_bound_to_request_and_environment_audit() -> None:
    """Bind the merged provider contract without changing the UUID ancestry route."""
    source = SCRIPT.read_text(encoding="utf-8")
    request_builder = source[
        source.index("def _build_managed_run_request") : source.index("def _resolve_admitted_runner")
    ]
    identity = (
        "https://github.com/iwashita-nozomu/experiment-runner",
        "71b3630266151703bdf88b11741b7492eca92fb4",
        "documents/experiment-runner-admission.md",
        "2de2b63aac3076e6aacdf1ff10b2c35a0235e835504aeff2db92a7750a720d85",
        "experiment-runner-admitted --request <path> --result <path>",
    )
    assert '"agentcanon_provider_contract": _provider_contract_identity()' in request_builder
    environment = (Path(__file__).resolve().parents[2] / "agent-canon-environment.toml").read_text(
        encoding="utf-8"
    )
    for value in identity:
        assert value in environment


def _valid_provider_result(request_fingerprint: str) -> dict[str, object]:
    """Build one provider-approved result projection for mismatch tests."""
    lifecycle = {
        "run_id": "run-mismatch",
        "terminal_event_id": "terminal-1",
        "observed_at_ns": 1,
        "terminal_status": "finished",
        "total_case_count_at_start": 1,
        "completion_count_before": 0,
        "completion_count_after": 1,
        "completion_delta": 1,
        "scheduler_completed": True,
        "admitted_case_count": 1,
        "terminal_notification_count": 1,
        "child_process_ids": [101],
        "process_group_ids": [101],
        "direct_children_quiescent": True,
        "descendant_quiescence": "proved",
        "cleanup_failures": [],
        "terminal_coverage_complete": True,
        "requested_case_coverage_complete": True,
        "quiescence_complete": True,
        "completion_coverage_complete": True,
    }
    return {
        "schema": "agentcanon-managed-run-result/v1",
        "identity": ExperimentIdentity("demo", "smoke", "run-mismatch").to_dict()["identity"],
        "request_fingerprint": request_fingerprint,
        "run_id": "run-mismatch",
        "status": "ok",
        "worker_pid": 101,
        "worker_pids": [101],
        "lifecycle": lifecycle,
        "descendant_quiescence": "proved",
        "quiescence": {
            "direct_children_quiescent": True,
            "descendant_quiescence": "proved",
            "complete": True,
            "cleanup_failures": [],
        },
        "exit": {"code": 0, "error": None},
        "exit_code": 0,
        "error": None,
        "completions": [{"case": {}, "result": {"status": "ok"}}],
    }


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("schema", "admitted_runner_result_schema_mismatch"),
        ("request_fingerprint", "admitted_runner_result_fingerprint_mismatch"),
        ("quiescence", "admitted_runner_descendant_quiescence_unproven"),
        ("exit", "admitted_runner_exit_mismatch"),
    ),
)
def test_r5_provider_result_mismatches_fail_closed(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    """Provider schema, fingerprint, quiescence, and exit mismatches are typed failures."""
    from tools.experiments.run_managed_experiment import _validate_admitted_result

    request_fingerprint = "a" * 64
    result = _valid_provider_result(request_fingerprint)
    if mutation == "schema":
        result["schema"] = "wrong/v1"
    elif mutation == "request_fingerprint":
        result["request_fingerprint"] = "b" * 64
    elif mutation == "quiescence":
        quiescence = result["quiescence"]
        assert isinstance(quiescence, dict)
        quiescence["complete"] = False
    else:
        exit_record = result["exit"]
        assert isinstance(exit_record, dict)
        exit_record["code"] = 1
        result["exit_code"] = 1
    result_path = tmp_path / "provider-result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(Exception) as raised:
        _validate_admitted_result(
            result_path,
            {
                "identity": ExperimentIdentity("demo", "smoke", "run-mismatch").to_dict()["identity"],
                "schema": "agentcanon-managed-run/v1",
                "run_id": "run-mismatch",
                "fingerprint": request_fingerprint,
            },
            0,
        )
    assert getattr(raised.value, "code", None) == expected_code


@pytest.mark.parametrize("remove_identity", (False, True))
def test_r5_provider_result_identity_is_required_and_matches_request(
    tmp_path: Path,
    remove_identity: bool,
) -> None:
    """Provider results must preserve the request's complete nested identity."""
    from tools.experiments.run_managed_experiment import _validate_admitted_result

    request_identity = ExperimentIdentity("demo", "smoke", "run-mismatch")
    result = _valid_provider_result("a" * 64)
    if remove_identity:
        result.pop("identity")
    else:
        result["identity"] = ExperimentIdentity(
            "demo", "formal", "run-mismatch"
        ).to_dict()["identity"]
    result_path = tmp_path / "provider-result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(Exception) as raised:
        _validate_admitted_result(
            result_path,
            {
                **request_identity.to_dict(),
                "schema": "agentcanon-managed-run/v1",
                "run_id": request_identity.run_name,
                "fingerprint": "a" * 64,
            },
            0,
        )

    assert getattr(raised.value, "code", None) == (
        "admitted_runner_result_identity_invalid"
        if remove_identity
        else "admitted_runner_result_identity_mismatch"
    )


def test_r5_provider_quiescence_and_completion_cover_lock_release() -> None:
    """Lock release requires provider quiescence and completion coverage evidence."""
    from dataclasses import replace

    from tools.experiments.run_managed_experiment import (
        ManagedRunLifecycleEvidence,
        _lifecycle_quiescence_is_proven,
    )

    lifecycle = ManagedRunLifecycleEvidence(
        run_id="r5-release",
        terminal_event_id="terminal-1",
        observed_at_ns=1,
        terminal_status="finished",
        total_case_count_at_start=1,
        completion_count_before=0,
        completion_count_after=1,
        scheduler_completed=True,
        admitted_case_count=1,
        terminal_notification_count=1,
        child_process_ids=(101,),
        process_group_ids=(101,),
        direct_children_quiescent=True,
        descendant_quiescence="proved",
        cleanup_failures=(),
        terminal_coverage_complete=True,
        requested_case_coverage_complete=True,
        quiescence_complete=True,
        completion_coverage_complete=True,
    )
    assert _lifecycle_quiescence_is_proven(lifecycle)
    assert not _lifecycle_quiescence_is_proven(
        replace(lifecycle, completion_coverage_complete=False)
    )
    assert not _lifecycle_quiescence_is_proven(
        replace(lifecycle, direct_children_quiescent=False)
    )


def test_r5_runner_lifecycle_capture_is_shell_free_and_import_free() -> None:
    """The composition root uses shell-free subprocess and has no local runner fallback."""
    source = SCRIPT.read_text(encoding="utf-8")
    admitted_runner_section = source[
        source.index("def _resolve_admitted_runner") : source.index("def repo_root_from_script")
    ]
    assert "shell=False" in source
    assert "--version" not in admitted_runner_section
    assert "_read_admitted_runner_version" not in admitted_runner_section
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
            "-m", "tools.ci.check_experiment_registry",
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "OK: experiment registry is valid" in result.stdout


def test_check_experiment_registry_reports_missing_required_field(
    tmp_path: Path,
) -> None:
    """The checker should retain required-field diagnostics after extraction is split."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_path.write_text(
        registry_path.read_text(encoding="utf-8").replace('status = "active"\n', ""),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m", "tools.ci.check_experiment_registry",
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "demo_topic: missing required string field: status" in result.stdout


def test_check_experiment_registry_reports_invalid_eval_artifact_item(
    tmp_path: Path,
) -> None:
    """The checker should retain optional-list diagnostics after normalization is split."""
    repo_root = build_repo(tmp_path)
    registry_path = repo_root / "experiments" / "registry.toml"
    registry_path.write_text(
        registry_path.read_text(encoding="utf-8").replace(
            'required_eval_artifacts = ["summary.json", "cases.jsonl"]',
            'required_eval_artifacts = ["summary.json", ""]',
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m", "tools.ci.check_experiment_registry",
            "--repo-root",
            str(repo_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "defaults: required_eval_artifacts[1] must be a non-empty string" in result.stdout


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
            "-m", "tools.ci.check_experiment_registry",
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
            "-m", "tools.ci.check_experiment_registry",
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
        env={**os.environ, "PYTHONPATH": str(CHECK_SCRIPT.parents[2])},
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
            "-m", "tools.ci.check_experiment_registry",
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
            "-m", "tools.ci.check_experiment_registry",
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
            "-m", "tools.ci.check_experiment_registry",
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
            "-m", "tools.ci.check_experiment_registry",
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
            "-m", "tools.ci.check_experiment_registry",
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
            "-m", "tools.experiments.create_experiment_topic",
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
