#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides run managed experiment experiment workflow tooling.
# upstream design ../README.md shared automation index
# upstream design ../../reports/agents/w1-tool-env-routing-20260716/design_brief.md approved W1-DESIGN-20260716-R3-GPU-COMPLETIONCOVERAGE-REPAIR
# upstream design ../../documents/experiment_runner.md external ExperimentRunner ownership and task boundary
# upstream implementation ./execution_resource_plan.py canonical discovery/planning/prelaunch/terminal owner
# upstream implementation ../../experiment_runner/python/experiment_runner/runner.py StandardRunner integer monitor route (explicitly excluded by W1 binding)
# upstream implementation ../../experiment_runner/python/experiment_runner/resource_scheduler.py StandardFullResourceScheduler integer GPU route (explicitly excluded by W1 binding)
# downstream integration ../../reports/agents/w1-tool-env-routing-20260716/ordered_integration_interface.json ordered W2-W4 interface
# static route evidence: run_cli -> execute_managed_run -> discover_resources -> plan_gpu_allocation -> freeze_resource_plan -> materialize_environment -> ExperimentRunnerPreLaunchAdapter.pre_launch -> execute_with_experiment_runner -> record_terminal -> dispose_resources
# alternate managed GPU launch routes: none; W1UUIDScheduler is the only GPU binding and never enters integer scheduler/monitor paths
# upstream evidence ../../reports/agents/w1-tool-env-routing-20260716/nvidia_primary_process_visibility_review.md NVIDIA process/PID/MIG/UUID visibility gate
# @dependency-end

"""Run one experiment while recording canonical server-side run metadata."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Mapping, cast

from tools.experiments.execution_resource_plan import (
    CALLER_ALLOCATION_PROVENANCE,
    COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
    COMPLETION_COVERAGE_FILENAME,
    ExperimentRunnerExecutionPort,
    ExperimentRunnerPreLaunchAdapter,
    CompletionCoverageAdapter,
    CompletionCoverageInput,
    ResourceRequest,
    ResourcePlanError,
    TypedPreflightFailure,
    discover_resources,
    dispose_resources,
    execute_with_experiment_runner,
    freeze_resource_plan,
    handle_pre_execution_failure,
    managed_run_adapter_integration_contract,
    materialize_environment,
    plan_gpu_allocation,
    release_runner_owned_gpu_leases,
    PlanState,
    record_terminal,
    failure_after_durable_cleanup,
)

DEFAULT_REQUIRED_EVAL_ARTIFACTS = ("summary.json", "cases.jsonl", "config.json")
CONFIG_SOURCE_SNAPSHOT_NAME = "config_source.yaml"
COMMAND_MANIFEST_NAME = "command.json"
ENVIRONMENT_MANIFEST_NAME = "environment.json"
SOURCE_SNAPSHOT_NAME = "source_snapshot.json"
ARTIFACT_MANIFEST_NAME = "artifact_manifest.json"
STARTUP_LOG_NAME = "startup.jsonl"
STDOUT_LOG_NAME = "stdout.log"
STDERR_LOG_NAME = "stderr.log"
MANAGED_RUN_ARTIFACTS = frozenset(
    {
        "run_manifest.json",
        "eval_manifest.json",
        "run.log",
        CONFIG_SOURCE_SNAPSHOT_NAME,
        COMMAND_MANIFEST_NAME,
        ENVIRONMENT_MANIFEST_NAME,
        SOURCE_SNAPSHOT_NAME,
        ARTIFACT_MANIFEST_NAME,
        f"logs/{STARTUP_LOG_NAME}",
        f"logs/{STDOUT_LOG_NAME}",
        f"logs/{STDERR_LOG_NAME}",
    }
)
FILE_READ_CHUNK_BYTES = 1024 * 1024
PREFLIGHT_FAILURE_EXIT_CODE = 2
DURATION_ROUND_DIGITS = 3
REGISTERED_COMMAND_KINDS = ("default", "formal")
REVIEWED_W1_LINEAGE_ARTIFACT = (
    "W1-IMPLEMENTATION-RECHECK-EF2DE34A-20260716-READONLY"
)
REVIEWED_W1_LINEAGE_COMMIT = "b829286c6a1c9de15f260199a44556e4f90be459"
REVIEWED_W1_LINEAGE_TREE = "551abfa0a6e89f4a9218fc4fc0706b3addd2a84e"
REVIEWED_W1_SOURCE_BLOBS = {
    "tools/experiments/execution_resource_plan.py": (
        "0a767491176530ecfe68a18e6b198de5d45f47fe"
    ),
    "tools/experiments/run_managed_experiment.py": (
        "4de18aeb418423ac36152d6e8501b11c16e82e18"
    ),
}
LEGACY_REGISTERED_COMMAND_ALIASES = {"smoke": "default"}
SENSITIVE_ENV_KEY_PARTS = (
    "API_KEY",
    "AUTH",
    "CREDENTIAL",
    "KEY",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)
EXCLUDED_SOURCE_SNAPSHOT_DIRS = frozenset(
    {
        ".git",
        "result",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


@dataclass(frozen=True)
class RegistryContext:
    """Loaded experiment registry data for one topic."""

    path: Path
    entry: dict[str, object]
    defaults: dict[str, object]
    available: bool


@dataclass(frozen=True)
class RunIdentity:
    """Stable identifiers for one managed experiment run."""

    topic: str
    run_name: str
    variant: str


@dataclass(frozen=True)
class RunPaths:
    """Filesystem paths owned by one managed run."""

    result_dir: Path
    log_dir: Path
    report_path: Path
    manifest_path: Path
    eval_manifest_path: Path
    artifact_manifest_path: Path
    command_manifest_path: Path
    environment_manifest_path: Path
    source_snapshot_path: Path
    config_source_path: Path
    config_path: Path
    log_path: Path
    startup_log_path: Path
    stdout_log_path: Path
    stderr_log_path: Path


@dataclass(frozen=True)
class CommandSelection:
    """Selected inner command and its provenance."""

    command: list[str]
    source: str
    registered_match: str | None


@dataclass(frozen=True)
class GitSnapshot:
    """Git state captured for one run manifest."""

    branch: str | None
    commit: str | None
    status_short: list[str]


@dataclass(frozen=True)
class EvalArtifactPatterns:
    """Validated eval artifact patterns for one run."""

    required: list[str]
    optional: list[str]


@dataclass(frozen=True)
class RunContext:
    """Complete immutable setup context for one managed run."""

    repo_root: Path
    identity: RunIdentity
    topic_dir: Path
    paths: RunPaths
    registry: RegistryContext
    command: CommandSelection
    created_at: str
    git: GitSnapshot


@dataclass(frozen=True)
class _W1CPUCapacity:
    """External-runner capacity with no integer GPU capacity or assignment."""

    max_workers: int = 1


@dataclass(frozen=True)
class _W1Completion:
    case: object
    context: Mapping[str, object]
    result: object


@dataclass(frozen=True)
class _W1RunnerResult:
    """Canonical result synthesized after StandardRunner has joined children."""

    status: str
    raw_exit_code: int
    message: str
    source: str = "w1_experiment_runner_binding"


@dataclass(frozen=True)
class _W1ContextInitializer:
    exact_environment: Mapping[str, str]
    initializer: Callable[..., object]
    apply_environment: Callable[..., object]

    def __call__(self, context: dict[str, object]) -> None:
        context["environment_variables"] = dict(self.exact_environment)
        self.apply_environment(context)
        self.initializer(context)


class _W1UUIDScheduler:
    """Structural Scheduler for StandardRunner without GPU-ID scheduling."""

    def __init__(
        self,
        *,
        cases: list[object],
        context_builder: Callable[..., object] | None,
        skip_controller: object | None,
        exact_environment: Mapping[str, str],
        selected_ids: tuple[str, ...],
    ) -> None:
        self._pending = list(cases)
        self._context_builder = context_builder
        self.skip_controller = skip_controller
        self._exact_environment = dict(exact_environment)
        self._selected_ids = tuple(selected_ids)
        self._resource_capacity = _W1CPUCapacity()
        self.completions: list[_W1Completion] = []

    @property
    def resource_capacity(self) -> _W1CPUCapacity:
        return self._resource_capacity

    @property
    def total_case_count(self) -> int:
        return len(self.completions) + len(self._pending)

    def _reject_integer_route_keys(self, context: Mapping[str, object]) -> None:
        environment = context.get("environment_variables", {})
        metadata = context.get("runner_metadata", {})
        forbidden = {
            "gpu_ids",
            "gpu_id",
            "EXPERIMENT_RUNNER_ASSIGNED_GPU_IDS",
            "EXPERIMENT_RUNNER_GPU_SLOT",
        }
        observed = tuple(
            sorted(
                key
                for key in forbidden
                if key in environment or (isinstance(metadata, Mapping) and key in metadata)
            )
        )
        if observed:
            raise TypedPreflightFailure(
                "experiment_runner_integer_gpu_route_forbidden",
                "W1 UUID allocation cannot enter an integer scheduler or monitor route",
                forbidden_keys=observed,
            )

    def next_case(self) -> tuple[object, dict[str, object]] | None:
        if not self._pending:
            return None
        case = self._pending.pop(0)
        raw_context = (
            self._context_builder(case) if self._context_builder is not None else {}
        )
        if not isinstance(raw_context, Mapping):
            raise TypedPreflightFailure(
                "experiment_runner_context_invalid",
                "canonical context builder must return a mapping",
            )
        self._reject_integer_route_keys(raw_context)
        context = dict(raw_context)
        context["environment_variables"] = dict(self._exact_environment)
        context["runner_metadata"] = {
            "w1_uuid_route": True,
            "integer_gpu_scheduler_used": False,
            "integer_gpu_monitor_route_used": False,
            "selected_uuid_count": len(self._selected_ids),
        }
        return case, context

    def on_finish(self, case: object, context: Mapping[str, object], result: object) -> None:
        self.completions.append(
            _W1Completion(case=case, context=dict(context), result=result)
        )
        if self.skip_controller is not None:
            update = getattr(self.skip_controller, "update", None)
            if callable(update):
                update(case, context, result)

    def is_completed(self) -> bool:
        return not self._pending


class CanonicalExperimentRunnerBinding:
    """Concrete W1 UUID binding to StandardRunner without integer GPU routes."""

    def __init__(self, context: RunContext, run_config: Mapping[str, object]) -> None:
        self.context = context
        self.run_config = run_config
        self._runner: object | None = None
        self._runner_finished = False
        self._runner_quiescence: Mapping[str, object] | None = None
        self._lease_cleanup_result: Mapping[str, object] | None = None
        self._exact_environment: Mapping[str, str] = {}
        self._selected_ids: tuple[str, ...] = ()

    def _topic_module(self) -> object:
        entrypoint = self.context.topic_dir / "run.py"
        spec = importlib.util.spec_from_file_location(
            f"agent_canon_topic_{self.context.identity.run_name}",
            entrypoint,
        )
        if spec is None or spec.loader is None:
            raise TypedPreflightFailure(
                "experiment_runner_binding_unavailable",
                "topic entrypoint cannot be bound to the external ExperimentRunner",
                entrypoint=str(entrypoint),
            )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _runner_callable(self, module: object, name: str) -> Callable[..., object]:
        value = getattr(module, name, None)
        if not callable(value):
            raise TypedPreflightFailure(
                "experiment_runner_binding_unavailable",
                "topic entrypoint omitted a documented ExperimentRunner callable",
                callable_name=name,
                entrypoint=str(self.context.topic_dir / "run.py"),
            )
        return cast(Callable[..., object], value)

    def prelaunch_transport(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        """Transport the exact packet without scheduler reselection or rewrite."""
        canonical = cast(Mapping[str, object], payload["canonical_environment"])
        allocation = cast(Mapping[str, object], payload["gpu_allocation"])
        observation = cast(Mapping[str, object], payload["prelaunch_observation"])
        handoff = cast(Mapping[str, object], payload["handoff_metadata"])
        return {
            "accepted": True,
            "canonical_environment": canonical,
            "gpu_allocation": allocation,
            "scheduler_policy": payload["scheduler_policy"],
            "plan_fingerprint": handoff["plan_fingerprint"],
            "readback_fingerprint": handoff["readback_fingerprint"],
            "effective_environment": canonical["exact_env_map"],
            "cwd": canonical["cwd"],
            "argv": canonical["argv"],
            "visible_gpu_ids": allocation["selected_ids"],
            "cpu_set": observation["cpu_set"],
            "container_id": observation["container_id"],
            "runtime_identity": observation["container_id"],
            "allocation_id": allocation["allocation_id"],
            "caller_allocated_ids": allocation["caller_allocated_ids"],
            "reservation_ids": allocation["reservation_ids"],
            "free_memory_bytes": observation["free_memory_bytes"],
            "process_identities": observation["process_identities"],
            "requested_memory_bytes": allocation["requested_memory_bytes"],
            "readback_timestamp": observation["observation_timestamp"],
            "probe_observation_timestamp": observation["observation_timestamp"],
            "probe_observation_fingerprint": observation["observation_fingerprint"],
            "probe_observation_event_id": observation["observation_event_id"],
        }

    def execute(
        self,
        *,
        plan: object,
        task: Callable[..., object],
        cases: list[object],
        context_builder: Callable[..., object],
        initializer: Callable[..., object],
        resource_estimator: Callable[..., object],
        skip_controller: object | None,
    ) -> object:
        try:
            runner_module = importlib.import_module("experiment_runner")
            topic_module = self._topic_module()
            standard_worker = getattr(runner_module, "StandardWorker")
            runner_type = getattr(runner_module, "StandardRunner")
            selected_ids = tuple(getattr(plan.gpu_allocation, "selected_ids", ()))
            exact_environment = dict(
                cast(Mapping[str, str], getattr(plan, "execution")["env"])
            )
            if selected_ids and tuple(
                exact_environment.get("CUDA_VISIBLE_DEVICES", "").split(",")
            ) != selected_ids:
                raise TypedPreflightFailure(
                    "experiment_runner_uuid_environment_mismatch",
                    "frozen UUID allocation is not the exact CUDA_VISIBLE_DEVICES packet",
                    selected_ids=selected_ids,
                )
            if selected_ids and exact_environment.get("NVIDIA_VISIBLE_DEVICES") != ",".join(selected_ids):
                raise TypedPreflightFailure(
                    "experiment_runner_uuid_environment_mismatch",
                    "frozen UUID allocation is not the exact NVIDIA_VISIBLE_DEVICES packet",
                    selected_ids=selected_ids,
                )
            task_value = task if callable(task) else self._runner_callable(topic_module, "task")
            cases_value = cases or list(getattr(topic_module, "cases"))
            context_value = context_builder or self._runner_callable(topic_module, "context_builder")
            initializer_value = initializer or self._runner_callable(topic_module, "initializer")
            estimator_value = resource_estimator or self._runner_callable(topic_module, "resource_estimate")
            skip_value = skip_controller or getattr(topic_module, "skip_controller", None)
            worker = standard_worker(
                task=task_value,
                resource_estimator=estimator_value,
                initializer=_W1ContextInitializer(
                    exact_environment,
                    initializer_value,
                    getattr(runner_module, "apply_environment_variables"),
                ),
            )
            scheduler = _W1UUIDScheduler(
                cases=cases_value,
                context_builder=context_value,
                skip_controller=skip_value,
                exact_environment=exact_environment,
                selected_ids=selected_ids,
            )
            self._exact_environment = exact_environment
            self._selected_ids = selected_ids
            self._runner = runner_type(
                scheduler,
                monitor=None,
                on_case_finished=None,
            )
            try:
                self._runner.run(worker)
            finally:
                self._runner_finished = True
                self._runner_quiescence = self._build_quiescence(plan)
            failed = any(
                getattr(completion.result, "status", "ok") == "failed"
                for completion in scheduler.completions
            )
            return _W1RunnerResult(
                status="failed" if failed else "ok",
                raw_exit_code=1 if failed else 0,
                message="one or more managed cases failed" if failed else "completed",
            )
        except TypedPreflightFailure:
            raise
        except Exception as exc:
            raise TypedPreflightFailure(
                "experiment_runner_binding_unavailable",
                "the canonical W1 UUID ExperimentRunner binding could not be completed",
                failure_type=type(exc).__name__,
                failure_message=str(exc),
            ) from exc

    def _build_quiescence(self, plan: object) -> Mapping[str, object]:
        runner_pid = os.getpid()
        try:
            observation = getattr(plan, "resource_probe").observe()
            stat = Path("/proc/self/stat").read_text(encoding="utf-8")
            start_identity = stat.rsplit(")", 1)[-1].split()[19]
        except Exception as exc:
            return {
                "plan_fingerprint": getattr(plan, "plan_fingerprint", ""),
                "quiescent": False,
                "process_tree_terminal": False,
                "can_create_gpu_context": True,
                "failure_type": type(exc).__name__,
                "failure_message": str(exc),
            }
        return {
            "plan_fingerprint": getattr(plan, "plan_fingerprint", ""),
            "quiescent": True,
            "process_tree_terminal": True,
            "can_create_gpu_context": False,
            "creation_barrier": "runner_process_tree_joined",
            "runner_root_pid": runner_pid,
            "runner_root_process_start_identity": start_identity,
            "observed_at": observation.observed_at,
            "observation_event_id": observation.observation_event_id,
            "observation_fingerprint": observation.fingerprint,
            "process_identities": tuple(_process_records(observation.process_identities)),
            "integer_gpu_scheduler_used": False,
            "integer_gpu_monitor_route_used": False,
        }

    def _dispose_gpu_leases(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        if self._lease_cleanup_result is not None:
            return self._lease_cleanup_result
        if not self._runner_finished or self._runner_quiescence is None:
            raise TypedPreflightFailure(
                "runner_lease_cleanup_not_ready",
                "W1 lease disposal cannot run before the external runner terminally exits",
            )
        plan = payload.get("plan")
        if plan is None:
            raise TypedPreflightFailure(
                "runner_lease_cleanup_plan_missing",
                "W1 lease disposer requires the frozen/terminal plan",
            )
        result = release_runner_owned_gpu_leases(
            plan,
            runner_quiescence_evidence=self._runner_quiescence,
        )
        self._lease_cleanup_result = result
        return result

    def quiescence_evidence(self, *, plan: object) -> Mapping[str, object]:
        if self._runner_quiescence is not None:
            return self._runner_quiescence
        if self._runner is None:
            raise TypedPreflightFailure(
                "runner_quiescence_evidence_unavailable",
                "ExperimentRunner binding has no live runner for quiescence evidence",
                plan_fingerprint=getattr(plan, "plan_fingerprint", ""),
            )
        evidence = getattr(self._runner, "quiescence_evidence", None)
        if not callable(evidence):
            raise TypedPreflightFailure(
                "runner_quiescence_evidence_unavailable",
                "external ExperimentRunner omitted quiescence evidence",
            )
        return cast(Mapping[str, object], evidence(plan=plan))

    def side_effect_disposers(self, *, plan: object) -> Mapping[str, object]:
        del plan
        return {"gpu-leases": self._dispose_gpu_leases}


def repo_root_from_script() -> Path:
    """Return the repository root from this script location."""
    return Path(__file__).absolute().parents[2]


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_timestamp() -> str:
    """Return the compact timestamp used for run names."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Create one managed experiment run directory with manifests, "
            "source/config snapshots, split logs, and an optional report stub."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=str(repo_root_from_script()),
        help="Repository root. Defaults to the path inferred from this script.",
    )
    parser.add_argument(
        "--topic",
        required=True,
        help="Experiment topic name under experiments/.",
    )
    parser.add_argument(
        "--run-name",
        help="Explicit run name. Defaults to <topic>_<variant>_<timestamp>.",
    )
    parser.add_argument(
        "--variant",
        default="formal",
        help="Variant label used when --run-name is omitted.",
    )
    parser.add_argument(
        "--registry",
        help=(
            "Optional registry path. Defaults to <repo-root>/experiments/registry.toml "
            "when present."
        ),
    )
    parser.add_argument(
        "--use-registered-command",
        help="Execute a registered inner command from experiments/registry.toml for this topic.",
    )
    parser.add_argument(
        "--report-path",
        help="Optional report path. Defaults to experiments/report/<run_name>.md.",
    )
    parser.add_argument(
        "--skip-report-init",
        action="store_true",
        help="Do not create a report stub when the report file is absent.",
    )
    parser.add_argument(
        "--config-json",
        help=(
            "Optional JSON object file to merge into result/<run_name>/config.json. "
            "The file must decode to a dictionary."
        ),
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help=(
            "Add one JSON-encoded config value to result/<run_name>/config.json. "
            "Example: --config seed=0 --config enabled=true."
        ),
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help=(
            "Command to run. Tokens may use {run_dir}, {run_name}, {report_path}, "
            "{manifest_path}, {eval_manifest_path}, {config_path}, "
            "{config_source_path}, {startup_log_path}, {stdout_log_path}, "
            "or {stderr_log_path}."
        ),
    )
    return parser.parse_args()


def load_registry(path: Path) -> dict[str, object]:
    """Load one experiment registry TOML file."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError("experiment registry TOML root must be a table")
    return data


def string_list(raw_value: object, key: str) -> list[str]:
    """Return one normalized non-empty string list."""
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise ValueError(f"{key} must be an array of strings")
    for index, item in enumerate(raw_value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{key}[{index}] must be a non-empty string")
    return [item.strip() for item in raw_value]


def find_registry_topic(
    registry: dict[str, object], topic_name: str
) -> dict[str, object] | None:
    """Return one topic entry from the registry."""
    raw_topics = registry.get("topics", [])
    if not isinstance(raw_topics, list):
        raise ValueError("experiment registry must contain [[topics]]")
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, dict):
            continue
        name = raw_topic.get("name")
        if name == topic_name:
            return raw_topic
    return None


def resolve_registry_path(repo_root: Path, registry_arg: str) -> Path:
    """Resolve the registry path requested by the CLI."""
    if registry_arg:
        return Path(registry_arg).resolve()
    return repo_root / "experiments" / "registry.toml"


def load_registry_context(registry_path: Path, topic_name: str) -> RegistryContext:
    """Load one topic registry context when the registry exists."""
    if not registry_path.is_file():
        return RegistryContext(
            path=registry_path,
            entry={},
            defaults={},
            available=False,
        )
    registry = load_registry(registry_path)
    entry = find_registry_topic(registry, topic_name)
    if entry is None:
        raise ValueError(f"topic {topic_name!r} is missing from {registry_path}")
    defaults = registry.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("experiment registry defaults must be a table")
    return RegistryContext(
        path=registry_path,
        entry=entry,
        defaults=defaults,
        available=True,
    )


def load_command_version(name: str) -> str | None:
    """Return one-line version text for a command when available."""
    if shutil.which(name) is None:
        return None
    result = subprocess.run(
        [name, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if not output:
        return None
    return output.splitlines()[0]


def load_config_json(path: Path) -> dict[str, object]:
    """Load one experiment config JSON object."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"--config-json must decode to a JSON object: {path}")
    config: dict[str, object] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"--config-json contains an invalid key: {key!r}")
        config[key] = value
    return config


def parse_config_pairs(pairs: list[str]) -> dict[str, object]:
    """Parse repeated KEY=JSON config arguments."""
    config: dict[str, object] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--config must use KEY=JSON form: {pair}")
        key, raw_value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"--config has an empty key: {pair}")
        try:
            config[key] = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"--config value for {key!r} is not valid JSON: {exc}"
            ) from exc
    return config


def build_registry_config_snapshot(registry: RegistryContext) -> dict[str, object]:
    """Build the registry fragment embedded in run config."""
    if not registry.available:
        return {}
    return {
        "name": registry.entry.get("name"),
        "canonical_entrypoint": registry.entry.get("canonical_entrypoint"),
        "default_variant": registry.entry.get("default_variant"),
        "default_inner_command": registry.entry.get("default_inner_command")
        or registry.entry.get("smoke_inner_command"),
        "formal_inner_command": registry.entry.get("formal_inner_command"),
    }


def build_run_config(
    context: RunContext, explicit_config: dict[str, object]
) -> dict[str, object]:
    """Build one JSON-serializable experiment run configuration dictionary."""
    run_config: dict[str, object] = {
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "variant": context.identity.variant,
        "paths": {
            "result_dir": str(context.paths.result_dir),
            "log_dir": str(context.paths.log_dir),
            "report_path": str(context.paths.report_path),
            "run_manifest": str(context.paths.manifest_path),
            "eval_manifest": str(context.paths.eval_manifest_path),
            "artifact_manifest": str(context.paths.artifact_manifest_path),
            "command_manifest": str(context.paths.command_manifest_path),
            "environment_manifest": str(context.paths.environment_manifest_path),
            "source_snapshot": str(context.paths.source_snapshot_path),
            "source_config": str(context.paths.config_source_path),
            "config": str(context.paths.config_path),
            "startup_log": str(context.paths.startup_log_path),
            "stdout_log": str(context.paths.stdout_log_path),
            "stderr_log": str(context.paths.stderr_log_path),
        },
        "command": context.command.command,
        "command_source": context.command.source,
        "registered_command_match": context.command.registered_match,
        "config": explicit_config,
    }
    registry_config = build_registry_config_snapshot(context.registry)
    if registry_config:
        run_config["registry"] = registry_config
    return run_config


def git_value(repo_root: Path, *args: str) -> str | None:
    """Return one git value or None when unavailable."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def load_git_snapshot(repo_root: Path) -> GitSnapshot:
    """Load the git state recorded in run artifacts."""
    git_dirty = git_value(repo_root, "status", "--short")
    return GitSnapshot(
        branch=git_value(repo_root, "branch", "--show-current"),
        commit=git_value(repo_root, "rev-parse", "HEAD"),
        status_short=git_dirty.splitlines() if git_dirty else [],
    )


def registry_path_text(registry: RegistryContext) -> str:
    """Return the display registry path for reports."""
    if registry.available:
        return str(registry.path)
    return "(none)"


def render_report_stub(context: RunContext) -> str:
    """Render one initial run report."""
    command_text = (
        shlex.join(context.command.command)
        if context.command.command
        else "(no command)"
    )
    branch_text = context.git.branch or "(unknown)"
    commit_text = context.git.commit or "(unknown)"
    return f"""# {context.identity.run_name}

- Topic: {context.identity.topic}
- Created At (UTC): {context.created_at}
- Result Dir: {context.paths.result_dir}
- Log Dir: {context.paths.log_dir}
- Run Manifest: {context.paths.manifest_path}
- Eval Manifest: {context.paths.eval_manifest_path}
- Artifact Manifest: {context.paths.artifact_manifest_path}
- Config: {context.paths.config_path}
- Source Config Snapshot: {context.paths.config_source_path}
- Registry: {registry_path_text(context.registry)}
- Branch: {branch_text}
- Commit: {commit_text}

## Question

<!-- What empirical question does this run answer? -->

## Comparison Target

<!-- main, baseline, previous run, or external reference. -->

## Protocol

- Command: `{command_text}`
- Report Path: `{context.paths.report_path}`

## Results

<!-- Fill in summary.json, cases.jsonl, and the main observations after the run. -->

## Reproducibility Record

- `run_manifest.json`
- `config.json`
- `config_source.yaml`
- `eval_manifest.json`
- `artifact_manifest.json`
- `command.json`
- `environment.json`
- `source_snapshot.json`
- `run.log`
- `logs/`
- `logs/startup.jsonl`
- `logs/stdout.log`
- `logs/stderr.log`
- `summary.json`
- `cases.jsonl`

## Critical Review Notes

<!-- What this run still does not justify. -->
"""


def build_manifest(context: RunContext, status: str) -> dict[str, object]:
    """Build one manifest dictionary."""
    manifest: dict[str, object] = {
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "status": status,
        "created_at_utc": context.created_at,
        "repo_root": str(context.repo_root),
        "topic_dir": str(context.topic_dir),
        "result_dir": str(context.paths.result_dir),
        "log_dir": str(context.paths.log_dir),
        "report_path": str(context.paths.report_path),
        "manifest_path": str(context.paths.manifest_path),
        "eval_manifest_path": str(context.paths.eval_manifest_path),
        "artifact_manifest_path": str(context.paths.artifact_manifest_path),
        "command_manifest_path": str(context.paths.command_manifest_path),
        "environment_manifest_path": str(context.paths.environment_manifest_path),
        "source_snapshot_path": str(context.paths.source_snapshot_path),
        "config_source_path": str(context.paths.config_source_path),
        "startup_log_path": str(context.paths.startup_log_path),
        "stdout_log_path": str(context.paths.stdout_log_path),
        "stderr_log_path": str(context.paths.stderr_log_path),
        "command": context.command.command,
        "server_context": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "cwd": os.getcwd(),
            "user": os.environ.get("USER") or os.environ.get("USERNAME") or "(unknown)",
        },
        "tool_versions": {
            "python": platform.python_version(),
            "codex": load_command_version("codex"),
            "docker": load_command_version("docker"),
        },
        "command_source": context.command.source,
        "registered_command_match": context.command.registered_match,
        "git": {
            "branch": context.git.branch,
            "commit": context.git.commit,
            "dirty": bool(context.git.status_short),
            "status_short": context.git.status_short,
        },
    }
    if context.registry.available:
        registry_snapshot = dict(context.registry.entry)
        registry_snapshot["registry_path"] = str(context.registry.path)
        manifest["registry"] = registry_snapshot
    return manifest


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write one JSON object with canonical formatting."""
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    """Write one manifest JSON file."""
    write_json(path, manifest)


def env_key_is_sensitive(key: str) -> bool:
    """Return whether an environment variable name likely contains a secret."""
    key_upper = key.upper()
    return any(part in key_upper for part in SENSITIVE_ENV_KEY_PARTS)


def captured_environment(env: dict[str, str]) -> dict[str, object]:
    """Return a redacted environment snapshot for reproducibility."""
    values: dict[str, object] = {}
    redacted_keys: list[str] = []
    for key in sorted(env):
        if env_key_is_sensitive(key):
            values[key] = {"present": True, "redacted": True}
            redacted_keys.append(key)
        else:
            values[key] = env[key]
    return {
        "captured_at_utc": utc_now(),
        "policy": "full_environment_with_key_secret_redaction",
        "key_count": len(values),
        "redacted_keys": redacted_keys,
        "values": values,
    }


def file_record(path: Path, base: Path) -> dict[str, object]:
    """Return stable metadata for one file."""
    relative_path = str(path.relative_to(base))
    return {
        "relative_path": relative_path,
        "bytes": path.stat().st_size,
        "sha256": load_file_sha256(path),
    }


def path_is_relative_to(path: Path, base: Path) -> bool:
    """Return whether path is inside base."""
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def external_file_record(path: Path) -> dict[str, object]:
    """Return stable metadata for one source file outside the repo root."""
    return {
        "absolute_path": str(path),
        "bytes": path.stat().st_size,
        "sha256": load_file_sha256(path),
    }


def source_snapshot_candidate_files(path: Path) -> list[Path]:
    """Return source snapshot files under one path."""
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    files: list[Path] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        relative_parts = child.relative_to(path).parts
        if any(part in EXCLUDED_SOURCE_SNAPSHOT_DIRS for part in relative_parts):
            continue
        files.append(child)
    return files


def git_status_path_text(status_line: str) -> str:
    """Return the path portion from one git status --short line."""
    raw_path = status_line[3:].strip()
    if " -> " in raw_path:
        raw_path = raw_path.rsplit(" -> ", 1)[1]
    return raw_path.strip('"')


def dirty_source_files(repo_root: Path, status_short: list[str]) -> tuple[list[Path], list[str]]:
    """Return existing dirty files plus dirty entries without a readable file."""
    files: list[Path] = []
    missing_paths: list[str] = []
    for status_line in status_short:
        path_text = git_status_path_text(status_line)
        if not path_text:
            continue
        candidate = repo_root / path_text
        candidate_files = source_snapshot_candidate_files(candidate)
        if candidate_files:
            files.extend(candidate_files)
        else:
            missing_paths.append(path_text)
    return files, missing_paths


def command_source_files(command: list[str], repo_root: Path) -> list[Path]:
    """Return local source files referenced directly by a command."""
    files: list[Path] = []
    for token in command:
        candidate = Path(token)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        if candidate.is_file():
            files.append(candidate.resolve())
    return files


def unique_paths(paths: list[Path]) -> list[Path]:
    """Return stable unique paths."""
    return sorted(dict.fromkeys(path.resolve() for path in paths), key=lambda path: str(path))


def build_source_snapshot(context: RunContext) -> dict[str, object]:
    """Build the source-file digest snapshot for one managed run."""
    files = source_snapshot_candidate_files(context.topic_dir)
    if context.registry.available and context.registry.path.is_file():
        files.append(context.registry.path)
    files.extend(command_source_files(context.command.command, context.repo_root))
    dirty_files, missing_dirty_paths = dirty_source_files(
        context.repo_root,
        context.git.status_short,
    )
    files.extend(dirty_files)
    runner_path = Path(__file__).resolve()
    if path_is_relative_to(runner_path, context.repo_root):
        files.append(runner_path)
        external_files: list[Path] = []
    else:
        external_files = [runner_path]
    unique_files = unique_paths(files)
    repo_files = [
        path for path in unique_files if path_is_relative_to(path, context.repo_root)
    ]
    external_records = [
        external_file_record(path) for path in unique_paths(external_files)
    ]
    return {
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "base_dir": str(context.repo_root),
        "excluded_topic_dirs": sorted(EXCLUDED_SOURCE_SNAPSHOT_DIRS),
        "git": {
            "branch": context.git.branch,
            "commit": context.git.commit,
            "dirty": bool(context.git.status_short),
            "status_short": context.git.status_short,
            "missing_dirty_paths": missing_dirty_paths,
        },
        "command_source_files": [
            str(path.relative_to(context.repo_root))
            for path in command_source_files(context.command.command, context.repo_root)
            if path_is_relative_to(path, context.repo_root)
        ],
        "dirty_file_count": len(dirty_files),
        "file_count": len(repo_files),
        "external_file_count": len(external_records),
        "files": [file_record(path, context.repo_root) for path in repo_files],
        "external_files": external_records,
    }


def copy_source_config_snapshot(context: RunContext) -> dict[str, object]:
    """Copy the checked-in topic config into the run directory."""
    source_config = context.topic_dir / "config.yaml"
    if not source_config.is_file():
        return {
            "status": "missing",
            "source_path": str(source_config),
            "snapshot_path": str(context.paths.config_source_path),
        }
    shutil.copy2(source_config, context.paths.config_source_path)
    return {
        "status": "copied",
        "source_path": str(source_config),
        "snapshot_path": str(context.paths.config_source_path),
        "sha256": load_file_sha256(context.paths.config_source_path),
        "bytes": context.paths.config_source_path.stat().st_size,
    }


def build_command_manifest(context: RunContext) -> dict[str, object]:
    """Build the resolved-command manifest for one run."""
    return {
        "schema_version": 1,
        "created_at_utc": utc_now(),
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "command": context.command.command,
        "command_text": shlex.join(context.command.command),
        "command_source": context.command.source,
        "registered_command_match": context.command.registered_match,
        "cwd": str(context.repo_root),
        "paths": {
            "result_dir": str(context.paths.result_dir),
            "log_dir": str(context.paths.log_dir),
            "run_log": str(context.paths.log_path),
            "stdout_log": str(context.paths.stdout_log_path),
            "stderr_log": str(context.paths.stderr_log_path),
            "startup_log": str(context.paths.startup_log_path),
        },
    }


def append_startup_event(
    context: RunContext,
    event: str,
    payload: dict[str, object],
) -> None:
    """Append one startup chronology event."""
    context.paths.startup_log_path.parent.mkdir(parents=True, exist_ok=True)
    entry: dict[str, object] = {
        "timestamp_utc": utc_now(),
        "event": event,
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
    }
    entry.update(payload)
    with context.paths.startup_log_path.open("a", encoding="utf-8") as handle:
        json.dump(entry, handle, sort_keys=True, ensure_ascii=True)
        handle.write("\n")


def build_artifact_manifest(context: RunContext) -> dict[str, object]:
    """Build a digest inventory for all current run artifacts."""
    files = [
        path
        for path in sorted(context.paths.result_dir.rglob("*"))
        if path.is_file() and path != context.paths.artifact_manifest_path
    ]
    return {
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "topic": context.identity.topic,
        "run_name": context.identity.run_name,
        "result_dir": str(context.paths.result_dir),
        "self_excluded": str(context.paths.artifact_manifest_path),
        "artifact_count": len(files),
        "artifacts": [file_record(path, context.paths.result_dir) for path in files],
    }


def merge_unique_strings(*groups: list[str]) -> list[str]:
    """Return one deduplicated list preserving first appearance order."""
    return list(dict.fromkeys(value for group in groups for value in group))


def validate_eval_artifact_patterns(patterns: list[str], key: str) -> list[str]:
    """Validate one eval artifact pattern list."""
    for pattern in patterns:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute():
            raise ValueError(
                f"{key} must stay relative to result/<run_name>: {pattern}"
            )
        if ".." in pattern_path.parts:
            raise ValueError(f"{key} must not escape result/<run_name>: {pattern}")
    return patterns


def resolve_eval_artifact_patterns(
    registry_defaults: dict[str, object],
    registry_entry: dict[str, object],
) -> EvalArtifactPatterns:
    """Return required and optional eval artifact patterns for one run."""
    default_required = string_list(
        registry_defaults.get("required_eval_artifacts"),
        "defaults.required_eval_artifacts",
    )
    default_optional = string_list(
        registry_defaults.get("optional_eval_artifacts"),
        "defaults.optional_eval_artifacts",
    )
    entry_required = string_list(
        registry_entry.get("required_eval_artifacts"),
        "topics.required_eval_artifacts",
    )
    entry_optional = string_list(
        registry_entry.get("optional_eval_artifacts"),
        "topics.optional_eval_artifacts",
    )
    required = merge_unique_strings(
        list(DEFAULT_REQUIRED_EVAL_ARTIFACTS),
        default_required,
        entry_required,
    )
    optional = merge_unique_strings(default_optional, entry_optional)
    optional = [pattern for pattern in optional if pattern not in required]
    return EvalArtifactPatterns(
        required=validate_eval_artifact_patterns(required, "required_eval_artifacts"),
        optional=validate_eval_artifact_patterns(optional, "optional_eval_artifacts"),
    )


def load_file_sha256(path: Path) -> str:
    """Return the sha256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(FILE_READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def artifact_kind(path: Path) -> str:
    """Infer one artifact kind from the file suffix."""
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".json":
        return "json"
    if suffix == ".csv":
        return "csv"
    if suffix in {".txt", ".log", ".md"}:
        return "text"
    if suffix in {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".html"}:
        return "rendered"
    return "file"


def load_line_count(path: Path) -> int:
    """Return the number of lines in one file without assuming UTF-8 text."""
    count = 0
    saw_bytes = False
    last_byte = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(FILE_READ_CHUNK_BYTES)
            if not chunk:
                break
            saw_bytes = True
            last_byte = chunk[-1:]
            count += chunk.count(b"\n")
    if saw_bytes and last_byte != b"\n":
        count += 1
    return count


def is_managed_run_artifact(path: Path, result_dir: Path) -> bool:
    """Return whether one path is a reserved managed artifact."""
    return str(path.relative_to(result_dir)) in MANAGED_RUN_ARTIFACTS


def load_eval_artifact(
    path: Path, result_dir: Path, patterns: list[str]
) -> dict[str, object]:
    """Load eval artifact metadata for one collected file."""
    artifact: dict[str, object] = {
        "relative_path": str(path.relative_to(result_dir)),
        "kind": artifact_kind(path),
        "bytes": path.stat().st_size,
        "sha256": load_file_sha256(path),
        "matched_patterns": patterns,
    }
    if artifact["kind"] in {"jsonl", "text", "csv"}:
        artifact["line_count"] = load_line_count(path)
    return artifact


def load_eval_artifacts(
    result_dir: Path,
    *,
    topic: str,
    run_name: str,
    patterns: EvalArtifactPatterns,
) -> dict[str, object]:
    """Collect eval artifact metadata from one result directory."""
    matched_patterns_by_path: dict[Path, list[str]] = {}
    missing_required_patterns: list[str] = []

    for pattern in patterns.required:
        matches = sorted(
            path
            for path in result_dir.glob(pattern)
            if path.is_file() and not is_managed_run_artifact(path, result_dir)
        )
        if not matches:
            missing_required_patterns.append(pattern)
            continue
        for match in matches:
            matched_patterns_by_path.setdefault(match, []).append(pattern)

    for pattern in patterns.optional:
        for match in sorted(
            path
            for path in result_dir.glob(pattern)
            if path.is_file() and not is_managed_run_artifact(path, result_dir)
        ):
            matched_patterns_by_path.setdefault(match, []).append(pattern)

    artifacts: list[dict[str, object]] = []
    for path in sorted(
        matched_patterns_by_path,
        key=lambda item: str(item.relative_to(result_dir)),
    ):
        artifacts.append(
            load_eval_artifact(path, result_dir, matched_patterns_by_path[path])
        )

    return {
        "topic": topic,
        "run_name": run_name,
        "result_dir": str(result_dir),
        "collected_at_utc": utc_now(),
        "required_patterns": patterns.required,
        "optional_patterns": patterns.optional,
        "missing_required_patterns": missing_required_patterns,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def format_command(command: list[str], placeholders: dict[str, str]) -> list[str]:
    """Format command tokens with run placeholders."""
    if command and command[0] == "--":
        command = command[1:]
    return [token.format(**placeholders) for token in command]


def normalize_registered_command_kind(command_kind: str) -> str:
    """Return the canonical registered command kind."""
    normalized = LEGACY_REGISTERED_COMMAND_ALIASES.get(command_kind, command_kind)
    if normalized not in REGISTERED_COMMAND_KINDS:
        allowed = ", ".join(REGISTERED_COMMAND_KINDS)
        raise ValueError(f"unsupported registered command {command_kind!r}; expected {allowed}")
    return normalized


def registered_command_keys(command_kind: str) -> tuple[str, ...]:
    """Return preferred registry keys for one command kind."""
    normalized = normalize_registered_command_kind(command_kind)
    keys = [f"{normalized}_inner_command"]
    if normalized == "default":
        keys.append("smoke_inner_command")
    return tuple(keys)


def command_from_registry(
    registry_entry: dict[str, object],
    command_kind: str,
    placeholders: dict[str, str],
) -> list[str]:
    """Return one formatted command from the registry."""
    checked_keys = registered_command_keys(command_kind)
    raw_command: str | None = None
    for command_key in checked_keys:
        raw_value = registry_entry.get(command_key)
        if isinstance(raw_value, str) and raw_value.strip():
            raw_command = raw_value
            break
    else:
        raise ValueError(f"registry entry is missing one of {', '.join(checked_keys)}")
    assert raw_command is not None
    return [token.format(**placeholders) for token in shlex.split(raw_command)]


def resolve_registered_command_match(
    registry: RegistryContext, command: list[str], placeholders: dict[str, str]
) -> str | None:
    """Return the matching registered command kind when one exists."""
    if not registry.available:
        return None
    for command_kind in REGISTERED_COMMAND_KINDS:
        try:
            registered_command = command_from_registry(
                registry.entry, command_kind, placeholders
            )
        except ValueError:
            continue
        if registered_command == command:
            return command_kind
    return None


def resolve_topic_dir(
    repo_root: Path, identity: RunIdentity, registry: RegistryContext
) -> Path:
    """Resolve the experiment topic directory."""
    if registry.available:
        topic_dir_raw = registry.entry.get("topic_dir")
        if not isinstance(topic_dir_raw, str):
            raise ValueError(
                f"registry entry for {identity.topic!r} is missing topic_dir"
            )
        return repo_root / topic_dir_raw
    return repo_root / "experiments" / identity.topic


def resolve_report_path(
    repo_root: Path, registry: RegistryContext, run_name: str, report_arg: str
) -> Path:
    """Resolve the report path for one run."""
    if report_arg:
        return Path(report_arg).resolve()
    if registry.available:
        registry_report_root = registry.entry.get(
            "report_root"
        ) or registry.defaults.get("report_root")
        if isinstance(registry_report_root, str):
            return (repo_root / registry_report_root / f"{run_name}.md").resolve()
    return (repo_root / "experiments" / "report" / f"{run_name}.md").resolve()


def build_run_paths(topic_dir: Path, run_name: str, report_path: Path) -> RunPaths:
    """Build filesystem paths owned by one run."""
    result_dir = topic_dir / "result" / run_name
    log_dir = result_dir / "logs"
    return RunPaths(
        result_dir=result_dir,
        log_dir=log_dir,
        report_path=report_path,
        manifest_path=result_dir / "run_manifest.json",
        eval_manifest_path=result_dir / "eval_manifest.json",
        artifact_manifest_path=result_dir / ARTIFACT_MANIFEST_NAME,
        command_manifest_path=result_dir / COMMAND_MANIFEST_NAME,
        environment_manifest_path=result_dir / ENVIRONMENT_MANIFEST_NAME,
        source_snapshot_path=result_dir / SOURCE_SNAPSHOT_NAME,
        config_source_path=result_dir / CONFIG_SOURCE_SNAPSHOT_NAME,
        config_path=result_dir / "config.json",
        log_path=result_dir / "run.log",
        startup_log_path=log_dir / STARTUP_LOG_NAME,
        stdout_log_path=log_dir / STDOUT_LOG_NAME,
        stderr_log_path=log_dir / STDERR_LOG_NAME,
    )


def build_placeholders(
    repo_root: Path, identity: RunIdentity, topic_dir: Path, paths: RunPaths
) -> dict[str, str]:
    """Build command placeholder values for one run."""
    return {
        "repo_root": str(repo_root),
        "topic_dir": str(topic_dir),
        "run_name": identity.run_name,
        "run_dir": str(paths.result_dir),
        "log_dir": str(paths.log_dir),
        "report_path": str(paths.report_path),
        "manifest_path": str(paths.manifest_path),
        "eval_manifest_path": str(paths.eval_manifest_path),
        "artifact_manifest_path": str(paths.artifact_manifest_path),
        "command_manifest_path": str(paths.command_manifest_path),
        "environment_manifest_path": str(paths.environment_manifest_path),
        "source_snapshot_path": str(paths.source_snapshot_path),
        "config_source_path": str(paths.config_source_path),
        "config_path": str(paths.config_path),
        "log_path": str(paths.log_path),
        "startup_log_path": str(paths.startup_log_path),
        "stdout_log_path": str(paths.stdout_log_path),
        "stderr_log_path": str(paths.stderr_log_path),
    }


def load_explicit_config(
    config_json_path: str, config_pairs: list[str]
) -> dict[str, object]:
    """Load explicit CLI config values."""
    explicit_config: dict[str, object] = {}
    if config_json_path:
        explicit_config.update(load_config_json(Path(config_json_path).resolve()))
    explicit_config.update(parse_config_pairs(config_pairs))
    return explicit_config


def select_command(
    use_registered_command: str,
    manual_command: list[str],
    registry: RegistryContext,
    placeholders: dict[str, str],
) -> CommandSelection:
    """Select the inner command for one managed run."""
    if use_registered_command and manual_command:
        raise ValueError(
            "do not pass both a manual command and --use-registered-command"
        )
    if use_registered_command:
        if not registry.available:
            raise ValueError(
                "--use-registered-command requires experiments/registry.toml"
            )
        registered_kind = normalize_registered_command_kind(use_registered_command)
        command = command_from_registry(
            registry.entry, registered_kind, placeholders
        )
        return CommandSelection(
            command=command,
            source=f"registered:{registered_kind}",
            registered_match=registered_kind,
        )
    command = format_command(manual_command, placeholders)
    return CommandSelection(
        command=command,
        source="manual",
        registered_match=resolve_registered_command_match(
            registry, command, placeholders
        ),
    )


def build_run_context(args: argparse.Namespace) -> RunContext:
    """Build setup context for one managed run."""
    repo_root = Path(args.repo_root).resolve()
    identity = RunIdentity(
        topic=args.topic,
        run_name=args.run_name or f"{args.topic}_{args.variant}_{compact_timestamp()}",
        variant=args.variant,
    )
    registry = load_registry_context(
        resolve_registry_path(repo_root, args.registry or ""),
        identity.topic,
    )
    topic_dir = resolve_topic_dir(repo_root, identity, registry)
    if not topic_dir.is_dir():
        raise ValueError(f"topic directory does not exist: {topic_dir}")
    report_path = resolve_report_path(
        repo_root,
        registry,
        identity.run_name,
        args.report_path or "",
    )
    paths = build_run_paths(topic_dir, identity.run_name, report_path)
    placeholders = build_placeholders(repo_root, identity, topic_dir, paths)
    command = select_command(
        args.use_registered_command or "",
        args.command,
        registry,
        placeholders,
    )
    return RunContext(
        repo_root=repo_root,
        identity=identity,
        topic_dir=topic_dir,
        paths=paths,
        registry=registry,
        command=command,
        created_at=utc_now(),
        git=load_git_snapshot(repo_root),
    )


def write_initial_artifacts(
    context: RunContext,
    manifest: dict[str, object],
    run_config: dict[str, object],
    skip_report_init: bool,
) -> dict[str, object]:
    """Write run directories, initial JSON files, and optional report stub."""
    context.paths.result_dir.mkdir(parents=True, exist_ok=True)
    context.paths.log_dir.mkdir(parents=True, exist_ok=True)
    context.paths.report_path.parent.mkdir(parents=True, exist_ok=True)
    source_config = copy_source_config_snapshot(context)
    run_config["source_config"] = source_config
    manifest["source_config"] = source_config
    write_json(context.paths.config_path, run_config)
    write_json(context.paths.command_manifest_path, build_command_manifest(context))
    write_json(
        context.paths.environment_manifest_path,
        captured_environment(build_run_environment(context)),
    )
    write_json(context.paths.source_snapshot_path, build_source_snapshot(context))
    write_manifest(context.paths.manifest_path, manifest)
    append_startup_event(
        context,
        "initialized",
        {
            "result_dir": str(context.paths.result_dir),
            "command_manifest": str(context.paths.command_manifest_path),
            "environment_manifest": str(context.paths.environment_manifest_path),
            "source_snapshot": str(context.paths.source_snapshot_path),
        },
    )

    if not skip_report_init and not context.paths.report_path.exists():
        context.paths.report_path.write_text(
            render_report_stub(context),
            encoding="utf-8",
        )
    return source_config


def source_config_error(source_config: dict[str, object]) -> str | None:
    """Return a preflight error when the checked-in config snapshot is missing."""
    if source_config.get("status") == "copied":
        return None
    return (
        "missing required source config.yaml: "
        f"{source_config.get('source_path')}; create the checked-in topic config "
        "before running a managed experiment"
    )


def build_run_environment(context: RunContext) -> dict[str, str]:
    """Build the environment for the inner experiment command."""
    env = dict(os.environ)
    env.update(
        {
            "EXPERIMENT_RUN_NAME": context.identity.run_name,
            "EXPERIMENT_TOPIC": context.identity.topic,
            "EXPERIMENT_RUN_DIR": str(context.paths.result_dir),
            "EXPERIMENT_LOG_DIR": str(context.paths.log_dir),
            "EXPERIMENT_REPORT_PATH": str(context.paths.report_path),
            "EXPERIMENT_RUN_MANIFEST": str(context.paths.manifest_path),
            "EXPERIMENT_EVAL_MANIFEST": str(context.paths.eval_manifest_path),
            "EXPERIMENT_ARTIFACT_MANIFEST": str(context.paths.artifact_manifest_path),
            "EXPERIMENT_COMMAND_MANIFEST": str(context.paths.command_manifest_path),
            "EXPERIMENT_CONFIG_PATH": str(context.paths.config_path),
            "EXPERIMENT_SOURCE_CONFIG_PATH": str(context.paths.config_source_path),
            "EXPERIMENT_SOURCE_SNAPSHOT": str(context.paths.source_snapshot_path),
            "EXPERIMENT_RUN_LOG": str(context.paths.log_path),
            "EXPERIMENT_STARTUP_LOG": str(context.paths.startup_log_path),
            "EXPERIMENT_STDOUT_LOG": str(context.paths.stdout_log_path),
            "EXPERIMENT_STDERR_LOG": str(context.paths.stderr_log_path),
        }
    )
    return env


def finalize_run_manifest(
    context: RunContext,
    manifest: dict[str, object],
    start_monotonic: float,
    exit_code: int,
    patterns: EvalArtifactPatterns,
) -> None:
    """Collect eval artifacts and write the final run manifest."""
    eval_collection = load_eval_artifacts(
        context.paths.result_dir,
        topic=context.identity.topic,
        run_name=context.identity.run_name,
        patterns=patterns,
    )
    write_json(context.paths.eval_manifest_path, eval_collection)
    manifest["finished_at_utc"] = utc_now()
    manifest["duration_seconds"] = round(
        time.monotonic() - start_monotonic, DURATION_ROUND_DIGITS
    )
    manifest["exit_code"] = exit_code
    manifest["status"] = "completed" if exit_code == 0 else "failed"
    manifest["eval_artifacts"] = {
        "eval_manifest_path": str(context.paths.eval_manifest_path),
        "required_patterns": patterns.required,
        "optional_patterns": patterns.optional,
        "collected_artifact_count": eval_collection["artifact_count"],
        "missing_required_patterns": eval_collection["missing_required_patterns"],
    }
    manifest["artifact_manifest"] = {
        "artifact_manifest_path": str(context.paths.artifact_manifest_path),
        "self_excluded": True,
    }
    write_manifest(context.paths.manifest_path, manifest)
    write_json(context.paths.artifact_manifest_path, build_artifact_manifest(context))


def _config_int(config: Mapping[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _config_bool(config: Mapping[str, object], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _config_chunks(config: Mapping[str, object], run_name: str) -> tuple[str, ...]:
    value = config.get("requested_chunks", [run_name])
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError("requested_chunks must be a non-empty array of strings")
    return tuple(value)


def _resource_request_for_managed_run(
    context: RunContext,
    run_config: Mapping[str, object],
) -> ResourceRequest:
    """Translate CLI/config metadata into the one canonical resource request."""
    raw_config = run_config.get("config", {})
    if not isinstance(raw_config, Mapping):
        raise ValueError("managed run config must remain a mapping")
    config = cast(Mapping[str, object], raw_config)
    try:
        cpu_requested_set = tuple(
            sorted(
                os.sched_getaffinity(0)
                if "cpu_requested_set" not in config
                else cast(list[int], config["cpu_requested_set"])
            )
        )
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise TypedPreflightFailure(
            "cpu_capability_discovery_unavailable",
            "managed run cannot declare an authoritative CPU set",
        ) from exc
    if any(isinstance(cpu, bool) or not isinstance(cpu, int) for cpu in cpu_requested_set):
        raise ValueError("cpu_requested_set must contain integers")
    environment = build_run_environment(context)
    gpu_requested_count = _config_int(config, "gpu_requested_count", 0)
    configured_provenance = str(config.get("gpu_allocation_provenance", ""))
    if gpu_requested_count and configured_provenance not in {
        "",
        CALLER_ALLOCATION_PROVENANCE,
    }:
        raise TypedPreflightFailure(
            "gpu_allocation_provenance_conflict",
            "managed GPU execution cannot override canonical scheduler UUID provenance",
            observed_provenance=configured_provenance,
        )
    lock_root_value = config.get("lock_root", "/var/lib/agent-canon/runtime/locks")
    if not isinstance(lock_root_value, str) or not lock_root_value:
        raise ValueError("lock_root must be a non-empty absolute path")
    timeout_value = config.get("maximum_timeout_seconds", 3600.0)
    if isinstance(timeout_value, bool) or not isinstance(timeout_value, (int, float)):
        raise ValueError("maximum_timeout_seconds must be a positive number")
    return ResourceRequest(
        owner_id=str(config.get("owner_id", "worker-luna")),
        parent_id=str(config.get("parent_id", "parent-sol")),
        context_id=str(config.get("context_id", "context-continuation")),
        maximum_timeout_seconds=float(timeout_value),
        argv=tuple(context.command.command),
        cwd=context.repo_root,
        environment=environment,
        integration_contract=managed_run_adapter_integration_contract(),
        plan_id=context.identity.run_name,
        run_id=context.identity.run_name,
        cpu_requested_set=cpu_requested_set,
        gpu_requested_count=gpu_requested_count,
        gpu_requested_memory_bytes=_config_int(
            config, "gpu_requested_memory_bytes", 0
        ),
        gpu_allocation_provenance=(
            CALLER_ALLOCATION_PROVENANCE if gpu_requested_count else ""
        ),
        temp_bytes=_config_int(config, "temp_bytes", 0),
        runtime_root=Path("/var/lib/agent-canon/runtime"),
        source_projection_root=Path(
            f"/workspace/reports/agents/{context.identity.run_name}/runtime"
        ),
        requested_chunks=_config_chunks(config, context.identity.run_name),
        lock_root=Path(lock_root_value),
        lock_namespace_shared_across_schedulers=_config_bool(
            config, "lock_namespace_shared_across_schedulers", False
        ),
        lock_namespace_host_safe=_config_bool(
            config, "lock_namespace_host_safe", False
        ),
        lock_namespace_visibility_witness=str(
            config.get("lock_namespace_visibility_witness", "")
        ),
    )


def _process_records(processes: object) -> tuple[Mapping[str, object], ...]:
    records: list[Mapping[str, object]] = []
    for process in cast(tuple[object, ...], tuple(processes)):
        records.append(
            {
                "pid": getattr(process, "pid"),
                "process_start_identity": getattr(process, "process_start_identity"),
                "gpu_uuid": getattr(process, "gpu_uuid"),
                "kind": getattr(process, "kind"),
                "parent_pid": getattr(process, "parent_pid"),
                "relationship": getattr(process, "relationship"),
                "observation_timestamp": getattr(
                    process, "observation_timestamp", ""
                ),
                "observation_fingerprint": getattr(
                    process, "observation_fingerprint", ""
                ),
                "container_namespace_identity": getattr(
                    process, "container_namespace_identity", ""
                ),
            }
        )
    return tuple(records)


def _runner_quiescence_evidence(
    runner_port: ExperimentRunnerExecutionPort,
    plan: object,
) -> Mapping[str, object]:
    """Require the runner owner to prove its process tree cannot create contexts."""
    plan_fingerprint = str(getattr(plan, "plan_fingerprint"))
    try:
        evidence = runner_port.quiescence_evidence(plan=plan)
    except Exception as exc:
        observation = getattr(plan, "resource_probe").observe()
        payload = {
            "plan_fingerprint": plan_fingerprint,
            "quiescent": False,
            "process_tree_terminal": False,
            "can_create_gpu_context": True,
            "observed_at": observation.observed_at,
            "observation_event_id": observation.observation_event_id,
            "observation_fingerprint": observation.fingerprint,
            "process_identities": _process_records(observation.process_identities),
            "failure_type": type(exc).__name__,
            "failure_message": str(exc),
        }
        return {
            **payload,
            "evidence_fingerprint": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }
    if not isinstance(evidence, Mapping):
        payload = {
            "plan_fingerprint": plan_fingerprint,
            "quiescent": False,
            "process_tree_terminal": False,
            "can_create_gpu_context": True,
            "creation_barrier": "missing",
            "observed_at": utc_now(),
            "observation_event_id": "",
            "process_identities": (),
            "failure_type": "runner_quiescence_evidence_malformed",
        }
        return {
            **payload,
            "evidence_fingerprint": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }
    return dict(evidence)


def execute_managed_run(
    context: RunContext,
    run_config: Mapping[str, object],
    *,
    runner_port: ExperimentRunnerExecutionPort,
    task: Callable[..., object],
    cases: list[object],
    context_builder: Callable[..., object],
    initializer: Callable[..., object],
    resource_estimator: Callable[..., object],
    skip_controller: object | None = None,
) -> object:
    """Execute one managed run through the mandatory plan and runner boundary."""
    request = _resource_request_for_managed_run(context, run_config)
    discovered = discover_resources(request)
    allocation = plan_gpu_allocation(request, discovered)
    frozen_plan = freeze_resource_plan(request, discovered, allocation)
    materialized = materialize_environment(frozen_plan)
    prelaunch = ExperimentRunnerPreLaunchAdapter(
        managed_run_adapter_integration_contract()
    ).pre_launch(
        materialized.plan,
        materialized,
        frozen_plan.gpu_allocation,
        runner_port.prelaunch_transport,
    )
    execution_result: object | None = None
    runner_failure: BaseException | None = None
    terminal = None
    try:
        execution_result = execute_with_experiment_runner(
            prelaunch.plan,
            prelaunch,
            runner_port,
            task=task,
            cases=cases,
            context_builder=context_builder,
            initializer=initializer,
            resource_estimator=resource_estimator,
            skip_controller=skip_controller,
        )
    except BaseException as exc:
        runner_failure = exc
    runner_exit_code = (
        _execution_exit_code(execution_result)
        if execution_result is not None
        else None
    )
    execution_completed = (
        runner_failure is None
        and execution_result is not None
        and runner_exit_code == 0
    )
    if runner_failure is not None:
        no_completion = {
            "failure_type": type(runner_failure).__name__,
            "failure_message": str(runner_failure),
        }
        stop_reason = type(runner_failure).__name__
    elif execution_result is None:
        no_completion = {
            "failure_type": "ExperimentRunnerResultMissing",
            "failure_message": "ExperimentRunner returned no execution result",
        }
        stop_reason = "experiment_runner_result_missing"
    elif not execution_completed:
        no_completion = {
            "failure_type": "ExperimentRunnerNonzeroExit",
            "failure_message": "ExperimentRunner returned a nonzero exit result",
            "raw_exit_code": runner_exit_code,
        }
        stop_reason = "experiment_runner_nonzero_exit"
    else:
        no_completion = None
        stop_reason = None
    try:
        terminal = record_terminal(
            prelaunch.plan,
            execution_result,
            terminal_event_id=f"terminal-{context.identity.run_name}",
            no_completion=no_completion,
            terminal_chunk_ids=(
                request.requested_chunks if execution_completed else ()
            ),
            stop_reason=stop_reason,
            disposition=None if execution_completed else "partial_not_completion",
            stdout_path=str(context.paths.stdout_log_path),
            stderr_path=str(context.paths.stderr_log_path),
            startup_log_path=str(context.paths.startup_log_path),
            run_log_path=str(context.paths.log_path),
            artifact_manifest_path=str(context.paths.artifact_manifest_path),
        )
    except Exception as exc:
        runner_cleanup: Mapping[str, object]
        try:
            raw_disposers = runner_port.side_effect_disposers(plan=materialized.plan)
            disposer = (
                raw_disposers.get("gpu-leases")
                if isinstance(raw_disposers, Mapping)
                else None
            )
            if not callable(disposer):
                raise TypedPreflightFailure(
                    "runner_lease_disposer_unavailable",
                    "terminal persistence failure has no W1 runner-owned lease disposer",
                )
            candidate = disposer(
                {
                    "plan": materialized.plan,
                    "runner_quiescence_evidence": _runner_quiescence_evidence(
                        runner_port,
                        materialized.plan,
                    ),
                    "terminal_persistence_failed": True,
                }
            )
            runner_cleanup = (
                cast(Mapping[str, object], candidate)
                if isinstance(candidate, Mapping)
                else {"disposition": "invalid_runner_cleanup_result"}
            )
        except Exception as cleanup_exc:
            runner_cleanup = {
                "disposition": "retained_or_unknown",
                "failure_type": type(cleanup_exc).__name__,
                "failure_message": str(cleanup_exc),
                "force_kill": False,
            }
        cleanup_failure = TypedPreflightFailure(
            "terminal_persistence_failed",
            "terminal persistence failed after W1 runner-owned cleanup boundary",
            original_failure_type=type(exc).__name__,
            original_failure_message=str(exc),
            runner_owned_cleanup=runner_cleanup,
        )
        cleanup = handle_pre_execution_failure(
            cleanup_failure,
            failed_operation="terminal_persistence",
            source_state=PlanState.ENV_MATERIALIZED,
            plan=materialized.plan,
        )
        raise failure_after_durable_cleanup(exc, cleanup) from exc
    quiescence_evidence = _runner_quiescence_evidence(
        runner_port,
        terminal.plan,
    )
    completion_input = _completion_input_for_managed_run(
        terminal,
        materialized,
        run_config,
    )
    disposer_failure: Mapping[str, object] = {}
    try:
        raw_disposers = runner_port.side_effect_disposers(plan=terminal.plan)
    except Exception as exc:
        raw_disposers = {}
        disposer_failure = {
            "side_effect_disposer_failure": {
                "failure_type": type(exc).__name__,
                "failure_message": str(exc),
                "disposition": "cleanup_without_owner_disposers",
            }
        }
    if disposer_failure:
        quiescence_evidence = {**quiescence_evidence, **disposer_failure}
    side_effect_disposers = (
        cast(Mapping[str, Callable[[Mapping[str, object]], Mapping[str, object]]], raw_disposers)
        if isinstance(raw_disposers, Mapping)
        else {}
    )
    dispose_resources(
        terminal.plan,
        terminal,
        completion_coverage_adapter=CompletionCoverageAdapter(
            Path(cast(str, terminal.plan.container["source_projection_root"]))
            / COMPLETION_COVERAGE_FILENAME
        ),
        completion_coverage_input=completion_input,
        runner_quiescence_evidence=quiescence_evidence,
        side_effect_disposers=side_effect_disposers,
    )
    if runner_failure is not None:
        raise runner_failure
    if execution_result is None:
        raise ResourcePlanError("ExperimentRunner returned no execution result")
    return execution_result


def _completion_input_for_managed_run(
    terminal: object,
    materialized: object,
    run_config: Mapping[str, object],
) -> CompletionCoverageInput:
    plan = getattr(terminal, "plan")
    allocation = plan.gpu_allocation
    observation = plan.resource_probe.observe()
    raw_runtime_config = run_config.get("config", {})
    runtime_config = (
        raw_runtime_config if isinstance(raw_runtime_config, Mapping) else {}
    )
    raw_lineage = runtime_config.get("parent_certified_w1_lineage", {})
    lineage = raw_lineage if isinstance(raw_lineage, Mapping) else {}
    raw_source_blobs = lineage.get("source_blobs", {})
    source_blobs = (
        dict(raw_source_blobs) if isinstance(raw_source_blobs, Mapping) else {}
    )
    lineage_certified = (
        lineage.get("status") == "parent_certified"
        and lineage.get("artifact") == REVIEWED_W1_LINEAGE_ARTIFACT
        and lineage.get("commit") == REVIEWED_W1_LINEAGE_COMMIT
        and lineage.get("tree") == REVIEWED_W1_LINEAGE_TREE
        and source_blobs == REVIEWED_W1_SOURCE_BLOBS
    )
    return CompletionCoverageInput(
        schema_version=COMPLETION_COVERAGE_INPUT_SCHEMA_VERSION,
        plan_fingerprint=terminal.plan_fingerprint,
        terminal_event_id=terminal.terminal_event_id,
        candidate_gpu_ids=allocation.candidate_ids,
        occupied_gpu_ids=_process_records(allocation.occupied_process_identities),
        reserved_gpu_ids=allocation.reserved_ids,
        selected_gpu_ids=allocation.selected_ids,
        eligible_gpu_ids=allocation.eligible_ids,
        lock_readback=allocation.lock_readback,
        effective_env={
            "plan_fingerprint": terminal.plan_fingerprint,
            "certificate": plan.readback.get("environment_certificate", {}),
            "materialized_environment": getattr(materialized, "persisted_env_map"),
        },
        actual_gpu_processes=_process_records(observation.process_identities),
        release_retention_disposition={"lease_retention_owner": "ExecutionResourcePlan"},
        concurrent_run_evidence={
            "planner": "canonical_plan_gpu_allocation",
            "final_observation": {
                "timestamp": observation.observed_at,
                "fingerprint": observation.fingerprint,
                "event_id": observation.observation_event_id,
            },
        },
        mig_evidence={"mapping": plan.resources["gpu"].get("mig_parent_by_uuid", {})},
        container_visible_uuid_mapping={
            "allocated_ids": allocation.caller_allocated_ids,
            "selected_ids": allocation.selected_ids,
        },
        os_safe_lock_placement={"lock_root": str(allocation.lock_root)},
        descendant_retention_evidence={"force_kill": False},
        taxonomy_linked_validation_outcome={
            "taxonomy_owner": "documents/runtime-profiles-and-check-matrix.json",
            "taxonomy_reader_projection": "documents/runtime-profiles-and-check-matrix.md",
            "status": "no_validation_failure",
        },
        planned_chunk_ids=terminal.planned_chunk_ids,
        terminal_chunk_ids=terminal.terminal_chunk_ids,
        terminal_chunk_records=terminal.terminal_chunk_records,
        required_evidence={
            "terminal": True,
            "partial": True,
            "parent_certified_w1_lineage": dict(lineage),
        },
        effective_env_certificate_matches=True,
        cleanup_has_unresolved_leak_or_unknown=False,
        required_review_gates_passed=lineage_certified,
        unresolved_design_issue_blockers=(
            () if lineage_certified else ("parent_certified_w1_lineage_missing",)
        ),
    )


def _execution_exit_code(execution_result: object) -> int:
    raw_exit_code = getattr(execution_result, "raw_exit_code", None)
    if isinstance(raw_exit_code, int):
        return raw_exit_code
    status = getattr(execution_result, "status", None)
    return 0 if status in (None, "ok", "completed", "success") else 1


def run_cli(
    args: argparse.Namespace,
    *,
    runner_port: ExperimentRunnerExecutionPort | None = None,
    task: Callable[..., object] | None = None,
    cases: list[object] | None = None,
    context_builder: Callable[..., object] | None = None,
    initializer: Callable[..., object] | None = None,
    resource_estimator: Callable[..., object] | None = None,
    skip_controller: object | None = None,
) -> int:
    """Run one managed experiment only through an injected ExperimentRunner port."""
    context = build_run_context(args)
    patterns = resolve_eval_artifact_patterns(
        context.registry.defaults,
        context.registry.entry,
    )
    explicit_config = load_explicit_config(args.config_json or "", args.config)

    if not context.command.command:
        raise ValueError("a command is required")

    manifest = build_manifest(context, "running")
    run_config = build_run_config(context, explicit_config)
    if runner_port is None:
        runner_port = CanonicalExperimentRunnerBinding(context, run_config)
    manifest["config_path"] = str(context.paths.config_path)
    manifest["config"] = run_config
    start_monotonic = time.monotonic()
    source_config = write_initial_artifacts(
        context,
        manifest,
        run_config,
        args.skip_report_init,
    )
    preflight_error = source_config_error(source_config)
    if preflight_error:
        print(preflight_error, file=sys.stderr)
        manifest["preflight_error"] = {
            "kind": "missing_source_config",
            "message": preflight_error,
        }
        append_startup_event(
            context,
            "preflight_failed",
            {
                "exit_code": PREFLIGHT_FAILURE_EXIT_CODE,
                "message": preflight_error,
            },
        )
        finalize_run_manifest(
            context,
            manifest,
            start_monotonic,
            PREFLIGHT_FAILURE_EXIT_CODE,
            patterns,
        )
        return PREFLIGHT_FAILURE_EXIT_CODE

    canonical_binding = isinstance(runner_port, CanonicalExperimentRunnerBinding)
    bindings = (task, cases, context_builder, initializer, resource_estimator)
    if not canonical_binding and any(binding is None for binding in bindings):
        message = (
            "managed execution requires the external ExperimentRunner port and "
            "task/cases/context/initializer/resource-estimator bindings; direct command "
            "launch is not an authorized route"
        )
        print(message, file=sys.stderr)
        manifest["preflight_error"] = {
            "kind": "experiment_runner_binding_required",
            "message": message,
            "canonical_owner": "tools/experiments/execution_resource_plan.py",
        }
        append_startup_event(
            context,
            "preflight_failed",
            {
                "exit_code": PREFLIGHT_FAILURE_EXIT_CODE,
                "message": message,
            },
        )
        finalize_run_manifest(
            context,
            manifest,
            start_monotonic,
            PREFLIGHT_FAILURE_EXIT_CODE,
            patterns,
        )
        return PREFLIGHT_FAILURE_EXIT_CODE

    append_startup_event(
        context,
        "command_start",
        {
            "command": context.command.command,
            "command_source": context.command.source,
        },
    )
    execution_result = execute_managed_run(
        context,
        run_config,
        runner_port=cast(ExperimentRunnerExecutionPort, runner_port),
        task=cast(Callable[..., object], task),
        cases=cast(list[object], cases),
        context_builder=cast(Callable[..., object], context_builder),
        initializer=cast(Callable[..., object], initializer),
        resource_estimator=cast(Callable[..., object], resource_estimator),
        skip_controller=skip_controller,
    )
    exit_code = _execution_exit_code(execution_result)
    append_startup_event(context, "command_exit", {"exit_code": exit_code})
    finalize_run_manifest(context, manifest, start_monotonic, exit_code, patterns)
    return exit_code


def main() -> int:
    """Run the CLI."""
    try:
        return run_cli(parse_args())
    except (OSError, ValueError, ResourcePlanError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
