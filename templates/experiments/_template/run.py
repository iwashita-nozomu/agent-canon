# @dependency-start
# contract template
# responsibility Owns the managed experiment entrypoint, run/raw/summary layout, schemas, atomic publication, and aggregation.
# upstream design ../../../documents/design/experiment-topic-template.md defines the single run owner and artifact layout.
# upstream implementation ../../../tools/experiments/run_managed_experiment.py owns admission and invokes this entrypoint.
# upstream implementation cases.py owns case models and execution.
# downstream implementation visualization.py owns visualization status and renderer extension.
# @dependency-end

"""Managed experiment entrypoint and the complete topic-local artifact boundary."""

from __future__ import annotations

import os
from pathlib import Path

from cases import CaseResult, CaseSpec, execute_case, registry_failure
from visualization import execute_visualization, write_visualization_not_requested_status

def resolve_run_dir() -> Path:
    """
    Resolve the canonical result directory supplied by the producer.

    `EXPERIMENT_RUN_DIR` を producer が必ず供給します。resource admission と GPU
    visibility はここで決めません。

    Returns:
        この invocation が選択した absolute result directory。
    """
    raw_run_dir = os.environ.get("EXPERIMENT_RUN_DIR", "")
    if not raw_run_dir:
        raise RuntimeError("managed_runner_required=explicit EXPERIMENT_RUN_DIR")
    return Path(raw_run_dir).resolve()


def load_cases() -> tuple[CaseSpec, ...]:
    """
    実験の domain dependency を import せず topic-owned case registry を読み込みます.

    Returns:
        `cases.py` が宣言した immutable case specifications。

    Raises:
        ValueError: topic registry が valid case record の tuple でない場合。
    """
    from cases import CASES

    if not isinstance(CASES, tuple):
        raise ValueError("cases.py must expose CASES as a tuple")
    if not all(isinstance(case, CaseSpec) for case in CASES):
        raise ValueError("cases.py CASES must contain CaseSpec records")
    return CASES


def _case_state_counts(records: tuple[CaseResult, ...]) -> tuple[int, int, int]:
    """
    success、failed、blocked の case record 数を数えます.

    Args:
        records: current run が所有する materialized case records。

    Returns:
        success、failed、blocked の順の count。

    Side effects:
        渡された immutable record sequence だけを読みます。
    """
    return (
        sum(record.state == "success" for record in records),
        sum(record.state == "failed" for record in records),
        sum(record.state == "blocked" for record in records),
    )


def _run_acceptance(
    records: tuple[CaseResult, ...],
    completion: CompletionProvenance,
) -> tuple[RunState, str, str]:
    """
    実行 case record から run status、failure class、close condition を導出します.

    Args:
        records: preserved failure を含む complete case execution records。

    Returns:
        導出した state、安定した failure class、required close condition。

    Side effects:
        artifact を書かず、record も変更しません。
    """
    if not completion.is_complete:
        return (
            RunState.INCOMPLETE,
            "expected_contract",
            "実行前に config.yaml と provenance.toml の completion が必要です",
        )
    if not records:
        return RunState.BLOCKED, "expected_contract", "cases.py に少なくとも一つの case を宣言してください"
    failed_records = [record for record in records if record.state == "failed"]
    if failed_records:
        return (
            RunState.FAILED,
            failed_records[0].failure_class,
            "failed case を修復して managed command を再実行してください",
        )
    blocked_records = [record for record in records if record.state == "blocked"]
    if blocked_records:
        return (
            RunState.BLOCKED,
            blocked_records[0].failure_class,
            "blocked case の owner を解決して managed command を再実行してください",
        )
    return (
        RunState.SUCCESS,
        "not_applicable",
        "summary、cases、manifest、validation oracle の readback が完了しました",
    )


def run_experiment(run_dir: Path) -> RunSummary:
    """
    一つの run を orchestration し、result set を atomic に公開します.

    空の `CASES` は `blocked` とし、failed または blocked case があれば成功 record を
    保持したまま failure evidence を書きます。空でない全成功 record と完了した
    visualization status がそろった場合だけ `success` にします。

    Args:
        run_dir: この run identity のために caller が所有する result directory。

    Returns:
        `summary.json` にも書く typed aggregate summary。

    Side effects:
        owning atomic I/O module を通して provenance、case、failure、visualization、summary、
        manifest artifact を生成します。
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = run_dir / "raw"
    summary_dir = run_dir / "summary"
    raw_dir.mkdir(exist_ok=True)
    summary_dir.mkdir(exist_ok=True)
    os.environ["EXPERIMENT_RAW_DIR"] = str(raw_dir.resolve())
    os.environ["EXPERIMENT_SUMMARY_DIR"] = str(summary_dir.resolve())
    started_at = utc_now()
    template_dir = Path(__file__).resolve().parent
    completion = load_completion_provenance(template_dir)
    write_provenance_snapshots(summary_dir, template_dir, completion)
    records_list: list[CaseResult] = []
    if completion.is_complete:
        try:
            cases = load_cases()
        except Exception as error:
            cases = ()
            records_list.append(registry_failure(error, started_at))
        for case in cases:
            records_list.append(execute_case(case, str(raw_dir.resolve())))
    records = tuple(records_list)
    write_case_records(summary_dir, records)
    success_count, failed_count, blocked_count = _case_state_counts(records)
    status, failure_class, close_condition = _run_acceptance(records, completion)
    failure_records = tuple(record for record in records if record.state != "success")
    failure_evidence = "not_applicable"
    if failure_records or not records:
        failure_evidence = f"{SUMMARY_ARTIFACT_PREFIX}{FAILURE_EVIDENCE_NAME}"
        write_failure_evidence(
            summary_dir,
            status=status,
            failure_class=failure_class,
            records=failure_records,
            close_condition=close_condition,
        )
    visualization_status = "not_requested"
    if completion.is_complete:
        try:
            visualization_status = execute_visualization(summary_dir, template_dir)
        except Exception as error:
            visualization_status = "blocked"
            status = RunState.FAILED
            failure_class = "infrastructure_environment"
            close_condition = "visualization runtime を用意して managed command を再実行してください"
            failure_evidence = f"{SUMMARY_ARTIFACT_PREFIX}{FAILURE_EVIDENCE_NAME}"
            write_failure_evidence(
                summary_dir,
                status=status,
                failure_class=failure_class,
                records=failure_records,
                close_condition=close_condition,
                visualization_error=f"{type(error).__name__}: {error}",
            )
    else:
        visualization_status = write_visualization_not_requested_status(summary_dir)
    finished_at = utc_now()
    preserved = [
        f"summary/{RESULT_SUMMARY_NAME}",
        f"summary/{RESULT_CASES_NAME}",
        f"summary/{RESULT_MANIFEST_NAME}",
        f"summary/{CONFIG_SNAPSHOT_NAME}",
        f"summary/{ENVIRONMENT_SNAPSHOT_NAME}",
        f"summary/{PROVENANCE_SNAPSHOT_NAME}",
        f"summary/{VISUALIZATION_STATUS_NAME}",
    ]
    if failure_evidence != "not_applicable":
        preserved.append(f"summary/{FAILURE_EVIDENCE_NAME}")
    summary = RunSummary(
        run_id=run_dir.name,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        exit_status=0 if status is RunState.SUCCESS else 1,
        case_count=len(records),
        success_count=success_count,
        failed_count=failed_count,
        blocked_count=blocked_count,
        failure_class=failure_class,
        failure_evidence=failure_evidence,
        preserved_artifacts=tuple(preserved),
        close_condition=close_condition,
        validation_oracle=(
            "pass: complete provenance、non-empty cases、terminal state invariant、"
            "全 artifact digest の readback"
            if status is RunState.SUCCESS
            else "incomplete: completion provenance が success の条件を満たしていません"
        ),
        visualization_status=visualization_status,
        template_complete=completion.is_complete,
        completion_provenance=completion.to_dict(),
    )
    write_summary(summary_dir, summary)
    write_artifact_manifest(run_dir, summary)
    return summary


def require_managed_runner_route() -> None:
    """
    直接の topic execution 前に managed runner manifest を要求します.

    Raises:
        RuntimeError: managed runner が manifest を提供しない場合。

    Side effects:
        caller environment だけを読み、experiment は開始しません。
    """
    if not os.environ.get("EXPERIMENT_RUN_MANIFEST", ""):
        raise RuntimeError(
            "managed_runner_required=tools/experiments/run_managed_experiment.py"
        )
    if not os.environ.get("EXPERIMENT_VARIANT", ""):
        raise RuntimeError("managed_runner_required=explicit EXPERIMENT_VARIANT")


def main() -> int:
    """
    選択した module を通して一つの managed experiment run を調整します.

    `main()` は引数なしの execution entrypoint です。algorithm、case、schema、serialization、
    visualization、oracle の選択は各 owning contract と replaceable module に残します。

    Returns:
        空でない成功 run では zero、failed または blocked result では one。

    Side effects:
        `run_experiment` が選択した complete run artifact set を公開します。
    """
    require_managed_runner_route()
    run_dir = resolve_run_dir()
    summary = run_experiment(run_dir)
    print(f"run_dir={run_dir}")
    print(f"status={summary.status.value}")
    print(f"summary={run_dir / 'summary' / RESULT_SUMMARY_NAME}")
    return summary.exit_status


from dataclasses import dataclass
from enum import Enum
import re
from collections.abc import Mapping
from typing import Literal


class RunState(str, Enum):
    """実験 run が公開できる終端状態を定義します."""

    INCOMPLETE = "incomplete"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"

CaseState = Literal["success", "failed", "blocked"]

RESULT_SUMMARY_NAME = "summary.json"
RESULT_CASES_NAME = "cases.jsonl"
RESULT_MANIFEST_NAME = "artifact-manifest.json"
SUMMARY_ARTIFACT_PREFIX = "summary/"
CONFIG_SNAPSHOT_NAME = "config_snapshot.json"
ENVIRONMENT_SNAPSHOT_NAME = "environment.json"
PROVENANCE_SNAPSHOT_NAME = "provenance_snapshot.toml"
FAILURE_EVIDENCE_NAME = "failure-evidence.json"
VISUALIZATION_STATUS_NAME = "visualization-status.json"

REQUIRED_CONFIG_FIELDS = (
    "cases",
    "metric",
    "runtime",
    "algorithm_contract",
    "oracle",
    "provenance",
    "failure",
    "lifecycle",
)
REQUIRED_COMPLETION_FIELDS = (
    "experiment.topic",
    "experiment.owner",
    "experiment.question",
    "experiment.hypothesis",
    "experiment.plan_digest",
    "plan.baseline",
    "plan.candidate",
    "plan.cases",
    "plan.metrics",
    "plan.stopping_rule",
    "plan.acceptance_oracle",
    "plan.algorithm_contract.public_entrypoint",
    "plan.algorithm_contract.input_schema",
    "plan.algorithm_contract.state_transition",
    "plan.algorithm_contract.invariants",
    "plan.algorithm_contract.stopping_rule",
    "plan.algorithm_contract.failure_semantics",
    "plan.oracle_boundary.necessary_observations",
    "plan.oracle_boundary.sufficient_observations",
    "plan.oracle_boundary.test_activation",
    "source.repository",
    "source.branch",
    "source.commit",
    "source.dirty_state",
    "resource.admission_owner",
    "resource.request",
    "resource.selection_reason",
    "resource.gpu_visibility",
    "resource.parallelism_policy",
    "resource.environment_limit",
    "resource.allocation_evidence",
    "reproducibility.readback_command",
    "reproducibility.required_artifacts",
    "reproducibility.required_case_artifact",
    "reproducibility.environment_snapshot",
    "reproducibility.retention_owner",
    "reproducibility.cleanup_policy",
    "reproducibility.cleanup_command",
    "reproducibility.reconstructibility_readback",
)
REQUIRED_COMPLETION_STRUCTURES = (
    (
        "plan.options",
        2,
        ("id", "mechanism", "status", "rejected_rationale", "selection_evidence"),
    ),
    (
        "plan.selection",
        1,
        ("selected_option", "rejected_rationale", "selection_evidence"),
    ),
    (
        "review",
        1,
        ("independent_reviewer", "source_snapshot", "selection_evidence", "review_decision"),
    ),
)
PLACEHOLDER_RE = re.compile(r"<[^>\n]+>")
UNRESOLVED_MARKER_RE = re.compile(
    r"\b(?:IMPLEMENT HERE|TODO|TBD|FIXME|REPLACE ME|selected-or-rejected)\b",
    re.IGNORECASE,
)


def unresolved_field_paths(value: object, prefix: str = "") -> tuple[str, ...]:
    """設定値を再帰走査し、未解決 marker の path を返します."""
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(key, str) and (
                PLACEHOLDER_RE.search(key) or UNRESOLVED_MARKER_RE.search(key)
            ):
                findings.append(child_prefix)
            findings.extend(unresolved_field_paths(child, child_prefix))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            findings.extend(unresolved_field_paths(child, f"{prefix}[{index}]"))
    elif isinstance(value, str) and (
        PLACEHOLDER_RE.search(value) or UNRESOLVED_MARKER_RE.search(value)
    ):
        findings.append(prefix or "$")
    return tuple(findings)


@dataclass(frozen=True)
class CompletionProvenance:
    """
    保持 topic scaffold の完成条件と不足項目を表します.

    Args:
        template_complete: config と provenance が完成宣言を持つか。
        completion_status: provenance の completion_status 値。
        provenance_path: readback 対象 provenance の相対 path。
        missing_fields: 未入力または placeholder の canonical field path。

    Raises:
        ValueError: 完成状態や provenance path が不正な場合。

    Side effects:
        immutable な判定 record を作るだけで、file I/O は行いません。

    Ownership:
        `run.py` が source を読み、acceptance に利用します。
    """

    template_complete: bool
    completion_status: str
    provenance_path: str
    missing_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        """完成判定に必要な identity と state を検証します."""
        if not isinstance(self.template_complete, bool):
            raise ValueError("template_complete must be boolean")
        if not self.completion_status.strip() or not self.provenance_path.strip():
            raise ValueError("completion provenance identity must be non-empty")

    @property
    def is_complete(self) -> bool:
        """Required fields が全て埋まり success を許可できるか返します."""
        return (
            self.template_complete
            and self.completion_status == "complete"
            and not self.missing_fields
        )

    def to_dict(self) -> dict[str, object]:
        """独立 readback 用の completion provenance mapping を返します."""
        return {
            "template_complete": self.template_complete,
            "completion_status": self.completion_status,
            "provenance_path": self.provenance_path,
            "missing_fields": list(self.missing_fields),
            "state": "complete" if self.is_complete else "incomplete",
        }

@dataclass(frozen=True)
class ArtifactEntry:
    """
    Artifact manifest 内の materialized file 一件を記述します.

    Args:
        path: run directory からの normalized relative artifact path。
        sha256: 完全な file bytes の lowercase digest。
        size_bytes: atomic publication 後に観測した byte size。

    Raises:
        ValueError: path/digest が空、または size が負の場合。

    Side effects:
        immutable schema record は filesystem read を行いません。

    Ownership:
        `run.py` が計測と entry 構築を行い、reader が検証します。
    """

    path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        """
        Manifest-entry invariant を serialization 前に強制します.

        Raises:
            ValueError: identity が空、または観測 size が負の場合。
        """
        normalized_parts = self.path.split("/")
        if (
            not self.path.strip()
            or not self.sha256.strip()
            or self.path.startswith("/")
            or "." in normalized_parts
            or ".." in normalized_parts
            or "\\" in self.path
        ):
            raise ValueError("artifact entry identity must be non-empty")
        if self.path != "/".join(part for part in normalized_parts if part):
            raise ValueError("artifact entry path must be normalized and relative")
        if self.size_bytes < 0:
            raise ValueError("artifact entry size must not be negative")

    def to_dict(self) -> dict[str, object]:
        """
        Manifest entry 一件の JSON object を返します.

        Returns:
            path、SHA-256 digest、byte size を含む mapping。
        """
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class ArtifactManifest:
    """
    Run-relative artifact digest manifest 全体を表します.

    Args:
        run_id: RunSummary と共有する result directory identity。
        state: manifest publication 時点の terminal run state。
        artifacts: この manifest 自身を除く全 materialized file の entry。

    Raises:
        ValueError: run identity が空、または entry path が重複する場合。

    Side effects:
        schema 構築は file I/O を行いません。

    Ownership:
        summary と case artifact の存在後の publication は `run.py` が所有します。
    """

    run_id: str
    state: RunState
    artifacts: tuple[ArtifactEntry, ...]

    def __post_init__(self) -> None:
        """
        Run-relative artifact path の一意性を強制します.

        Raises:
            ValueError: run identity が空、または path が重複する場合。
        """
        if not self.run_id.strip():
            raise ValueError("manifest run_id must not be blank")
        if not isinstance(self.state, RunState):
            raise ValueError("manifest state must be a RunState enum value")
        paths = [entry.path for entry in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest artifact paths must be unique")

    def to_dict(self) -> dict[str, object]:
        """
        JSON manifest 全体の projection を返します.

        Returns:
            schema version、state、digest を含む JSON-compatible mapping。
        """
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "state": self.state.value,
            "artifacts": [entry.to_dict() for entry in self.artifacts],
            "readback": "hash every materialized file except this manifest",
        }


@dataclass(frozen=True)
class RunSummary:
    """
    全 case record を run-level acceptance state へ集約します.

    invariant は `status` を materialized case state と case 後の infrastructure evidence
    だけから導出することです。空または部分書き込みの result file から success を推測しません。

    Args:
        run_id: result directory identity。
        status: terminal run state。
        started_at: RFC3339 UTC run start time。
        finished_at: RFC3339 UTC run finish time。
        exit_status: run state が表す process status。
        case_count: materialized case record 数。
        success_count: success record 数。
        failed_count: failed record 数。
        blocked_count: blocked record 数。
        failure_class: 安定した failure-cause classification。
        failure_evidence: evidence filename または not_applicable。
        preserved_artifacts: readback 必須 artifact filename。
        close_condition: non-success rerun を閉じる前に必要な人間の action。
        validation_oracle: 必要十分な run acceptance oracle。
        visualization_status: visualization consumer state。
        template_complete: template が完成条件を満たすか。
        completion_provenance: 完成条件の readback mapping。

    Raises:
        ValueError: identity、count、exit status が schema に違反する場合。

    Side effects:
        schema 構築は file I/O を行いません。

    Ownership:
        field と summary serialization は `run.py` が所有します。
    """

    run_id: str
    status: RunState
    started_at: str
    finished_at: str
    exit_status: int
    case_count: int
    success_count: int
    failed_count: int
    blocked_count: int
    failure_class: str
    failure_evidence: str
    preserved_artifacts: tuple[str, ...]
    close_condition: str
    validation_oracle: str
    visualization_status: str
    template_complete: bool
    completion_provenance: dict[str, object]

    def __post_init__(self) -> None:
        """
        Summary publication 前に count と identity invariant を強制します.

        Raises:
            ValueError: count が負/不整合、または必須 text field が空の場合。
        """
        if not self.run_id.strip() or not self.started_at.strip() or not self.finished_at.strip():
            raise ValueError("summary identity and timestamps must be non-empty")
        if not isinstance(self.status, RunState):
            raise ValueError("summary status must be a RunState enum value")
        if not isinstance(self.exit_status, int) or isinstance(self.exit_status, bool):
            raise ValueError("summary exit status must be an integer")
        count_values = (
            self.case_count,
            self.success_count,
            self.failed_count,
            self.blocked_count,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) for value in count_values):
            raise ValueError("summary counts must be integers")
        if min(
            self.exit_status,
            self.case_count,
            self.success_count,
            self.failed_count,
            self.blocked_count,
        ) < 0:
            raise ValueError("summary counts and exit status must not be negative")
        if self.success_count + self.failed_count + self.blocked_count != self.case_count:
            raise ValueError("summary state counts must equal case_count")
        if not self.failure_class.strip() or not self.failure_evidence.strip():
            raise ValueError("summary failure fields must be explicit")
        if not isinstance(self.template_complete, bool):
            raise ValueError("summary template_complete must be boolean")
        if not isinstance(self.completion_provenance, dict):
            raise ValueError("summary completion provenance must be a mapping")
        provenance_template_complete = self.completion_provenance.get("template_complete")
        provenance_path = self.completion_provenance.get("provenance_path")
        provenance_state = self.completion_provenance.get("state")
        provenance_status = self.completion_provenance.get("completion_status")
        missing_fields = self.completion_provenance.get("missing_fields")
        if provenance_template_complete != self.template_complete:
            raise ValueError("summary template completion readback disagrees")
        if not isinstance(provenance_path, str) or not provenance_path.strip():
            raise ValueError("summary completion readback must include provenance_path")
        if not isinstance(missing_fields, list):
            raise ValueError("summary completion readback must include missing_fields")
        if not all(isinstance(field, str) and field.strip() for field in missing_fields):
            raise ValueError("summary completion readback missing_fields must be strings")
        expected_provenance_state = "complete" if self.template_complete else "incomplete"
        if provenance_state != expected_provenance_state:
            raise ValueError("summary completion readback state disagrees")
        if self.template_complete:
            if provenance_status != "complete" or missing_fields:
                raise ValueError("complete summary requires complete provenance readback")
        elif provenance_status == "complete" and not missing_fields:
            raise ValueError("incomplete summary cannot have complete provenance readback")
        required_readback = {
            f"{SUMMARY_ARTIFACT_PREFIX}{RESULT_SUMMARY_NAME}",
            f"{SUMMARY_ARTIFACT_PREFIX}{RESULT_CASES_NAME}",
            f"{SUMMARY_ARTIFACT_PREFIX}{RESULT_MANIFEST_NAME}",
            f"{SUMMARY_ARTIFACT_PREFIX}{CONFIG_SNAPSHOT_NAME}",
            f"{SUMMARY_ARTIFACT_PREFIX}{ENVIRONMENT_SNAPSHOT_NAME}",
            f"{SUMMARY_ARTIFACT_PREFIX}{PROVENANCE_SNAPSHOT_NAME}",
            f"{SUMMARY_ARTIFACT_PREFIX}{VISUALIZATION_STATUS_NAME}",
        }
        if not all(isinstance(path, str) and path.strip() for path in self.preserved_artifacts):
            raise ValueError("summary preserved artifacts must be non-empty paths")
        if not required_readback.issubset(self.preserved_artifacts):
            raise ValueError("summary preserved artifacts must cover required readback")
        if self.status is RunState.SUCCESS:
            if not self.template_complete or self.exit_status != 0 or self.case_count == 0:
                raise ValueError("success requires complete provenance and successful cases")
            if self.failed_count or self.blocked_count:
                raise ValueError("success cannot contain failed or blocked cases")
        elif self.exit_status == 0:
            raise ValueError("non-success run states require non-zero exit status")
        if self.status is RunState.INCOMPLETE and self.template_complete:
            raise ValueError("incomplete state requires incomplete template provenance")

    def to_dict(self) -> dict[str, object]:
        """
        この run の summary.json projection 全体を返します.

        Returns:
            count、status、oracle、artifact を含む JSON-compatible mapping。
        """
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "state": self.status.value,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_status": self.exit_status,
            "case_count": self.case_count,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "blocked_count": self.blocked_count,
            "failure_class": self.failure_class,
            "failure_evidence": self.failure_evidence,
            "accepted_failure": False,
            "accepted_failure_reason": "not_applicable",
            "preserved_artifacts": list(self.preserved_artifacts),
            "close_condition": self.close_condition,
            "validation_oracle": self.validation_oracle,
            "visualization_status": self.visualization_status,
            "template_complete": self.template_complete,
            "completion_provenance": self.completion_provenance,
            "result_files": [
                f"{SUMMARY_ARTIFACT_PREFIX}{RESULT_SUMMARY_NAME}",
                f"{SUMMARY_ARTIFACT_PREFIX}{RESULT_CASES_NAME}",
                f"{SUMMARY_ARTIFACT_PREFIX}{RESULT_MANIFEST_NAME}",
            ],
            "provenance_files": [
                f"{SUMMARY_ARTIFACT_PREFIX}{CONFIG_SNAPSHOT_NAME}",
                f"{SUMMARY_ARTIFACT_PREFIX}{ENVIRONMENT_SNAPSHOT_NAME}",
                f"{SUMMARY_ARTIFACT_PREFIX}{PROVENANCE_SNAPSHOT_NAME}",
            ],
        }

import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

def _completion_value(data: object, path: str) -> object:
    """指定した TOML dotted path の値を取得します."""
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_completed_value(value: object) -> bool:
    """空値または placeholder を completion failure として判定します."""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and not PLACEHOLDER_RE.search(value)
    if isinstance(value, (list, tuple)):
        return bool(value) and all(_is_completed_value(item) for item in value)
    if isinstance(value, dict):
        return bool(value)
    return True


def _missing_completion_structures(provenance: object) -> list[str]:
    """Provenance の必須 table 構造と fields の不足を列挙します."""
    missing: list[str] = []
    for path, minimum_count, fields in REQUIRED_COMPLETION_STRUCTURES:
        value = _completion_value(provenance, path)
        if path == "plan.options":
            records = value if isinstance(value, list) else []
            if len(records) < minimum_count:
                missing.append(
                    f"provenance.{path} requires at least {minimum_count} records"
                )
        else:
            records = [value] if isinstance(value, dict) else []
            if not records:
                missing.append(f"provenance.{path} is required")
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                missing.append(f"provenance.{path}[{index}] must be a mapping")
                continue
            for field in fields:
                if not _is_completed_value(record.get(field)):
                    field_path = (
                        f"provenance.{path}[{index}].{field}"
                        if path == "plan.options"
                        else f"provenance.{path}.{field}"
                    )
                    missing.append(field_path)
    missing.extend(_missing_option_selection_invariants(provenance))
    return missing


def _missing_option_selection_invariants(provenance: object) -> list[str]:
    """plan.options と plan.selection の cross-field invariant を検証します."""
    options = _completion_value(provenance, "plan.options")
    selection = _completion_value(provenance, "plan.selection")
    if not isinstance(options, list) or not all(isinstance(item, dict) for item in options):
        return []
    if not isinstance(selection, dict):
        return []

    records = [item for item in options if isinstance(item, dict)]
    option_ids = [record.get("id") for record in records]
    missing: list[str] = []
    if any(
        option_ids[left] == option_ids[right]
        for left in range(len(option_ids))
        for right in range(left + 1, len(option_ids))
    ):
        missing.append("provenance.plan.options.id must be unique")

    selected_option = selection.get("selected_option")
    if selected_option not in option_ids:
        missing.append(
            "provenance.plan.selection.selected_option must reference an option id"
        )

    selected_records = [record for record in records if record.get("status") == "selected"]
    if len(selected_records) != 1:
        missing.append("provenance.plan.options must contain exactly one selected option")
    elif selected_records[0].get("id") != selected_option:
        missing.append(
            "provenance.plan.selection.selected_option must identify the selected option"
        )

    if selected_option in option_ids:
        if any(
            record.get("id") != selected_option and record.get("status") != "rejected"
            for record in records
        ):
            missing.append(
                "provenance.plan.options must mark every non-selected option as rejected"
            )
    return missing


def load_completion_provenance(template_dir: Path) -> CompletionProvenance:
    """
    Config と provenance の completion contract を読み戻します.

    Args:
        template_dir: config.yaml と provenance.toml を含む materialized topic directory。

    Returns:
        完成状態と不足 field を持つ immutable provenance record。

    Side effects:
        config.yaml と provenance.toml を読みますが、書き込みは行いません。
    """
    config_path = template_dir / "config.yaml"
    provenance_path = template_dir / "provenance.toml"
    config_text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    missing: list[str] = []
    config: object = None
    if not config_path.is_file():
        missing.append("config.yaml")
    else:
        try:
            config = yaml.safe_load(config_text)
        except yaml.YAMLError:
            missing.append("config.yaml.parseable")
    config_mapping = config if isinstance(config, dict) else {}
    config_complete = config_mapping.get("template_complete") is True
    if not config_mapping:
        missing.append("config.yaml.mapping")
    if not config_complete:
        missing.append("config.template_complete=true")
    if PLACEHOLDER_RE.search(config_text) or UNRESOLVED_MARKER_RE.search(config_text):
        missing.append("config.raw unresolved")
    missing.extend(
        f"{path} unresolved"
        for path in unresolved_field_paths(config_mapping, "config")
    )
    for field in REQUIRED_CONFIG_FIELDS:
        if not _is_completed_value(_completion_value(config_mapping, field)):
            missing.append(f"config.{field}")
    if not provenance_path.is_file():
        missing.append("provenance.toml")
        return CompletionProvenance(
            template_complete=False,
            completion_status="incomplete",
            provenance_path="provenance.toml",
            missing_fields=tuple(missing),
        )
    provenance_text = provenance_path.read_text(encoding="utf-8")
    try:
        provenance = tomllib.loads(provenance_text)
    except (OSError, tomllib.TOMLDecodeError):
        missing.append("provenance.toml.parseable")
        return CompletionProvenance(
            template_complete=False,
            completion_status="incomplete",
            provenance_path="provenance.toml",
            missing_fields=tuple(missing),
        )
    template_complete = provenance.get("template_complete") is True
    completion_status = str(provenance.get("completion_status", "incomplete"))
    if not template_complete:
        missing.append("provenance.template_complete=true")
    if completion_status != "complete":
        missing.append("provenance.completion_status=complete")
    if PLACEHOLDER_RE.search(provenance_text) or UNRESOLVED_MARKER_RE.search(provenance_text):
        missing.append("provenance.raw unresolved")
    missing.extend(
        f"{path} unresolved"
        for path in unresolved_field_paths(provenance, "provenance")
    )
    for field in REQUIRED_COMPLETION_FIELDS:
        if not _is_completed_value(_completion_value(provenance, field)):
            missing.append(field)
    missing.extend(_missing_completion_structures(provenance))
    return CompletionProvenance(
        template_complete=config_complete and template_complete,
        completion_status=completion_status,
        provenance_path="provenance.toml",
        missing_fields=tuple(dict.fromkeys(missing)),
    )


def utc_now() -> str:
    """
    Artifact provenance 用の RFC3339 UTC timestamp を返します.

    Returns:
        末尾に `Z` を持つ timezone-aware timestamp string。

    Side effects:
        system clock だけを読みます。
    """
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def atomic_write_text(path: Path, content: str) -> None:
    """
    Temporary sibling を flush した後に artifact 一件を atomic replace します.

    Args:
        path: この run が所有する destination artifact。
        content: 公開する完全な UTF-8 payload。

    Raises:
        OSError: destination directory または atomic replacement に失敗した場合。

    Side effects:
        temporary file を作成・flush し、`path` を atomic に置換します。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """
    JSON object 一件を serialize し、atomic_write_text 経由で公開します.

    Args:
        path: destination JSON artifact。
        payload: producer が所有する JSON-compatible object。

    Raises:
        TypeError: payload に JSON-serializable でない値がある場合。

    Side effects:
        destination file を atomic に作成または置換します。
    """
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def sha256_file(path: Path) -> str:
    """
    Artifact manifest が使う content digest を計算します.

    Args:
        path: bytes を読む既存 file。

    Returns:
        lowercase SHA-256 digest。

    Raises:
        OSError: file を読み出せない場合。

    Side effects:
        file 全体を読み、変更しません。
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_provenance_snapshots(
    run_dir: Path,
    template_dir: Path,
    completion: CompletionProvenance,
) -> tuple[str, str, str]:
    """
    Case execution 前に config、completion、runtime identity を snapshot します.

    Args:
        run_dir: snapshot を受け取る result directory。
        template_dir: config.yaml と provenance.toml を含む materialized experiment directory。

    Returns:
        config、provenance、environment 順の安定した snapshot filename。

    Raises:
        OSError: 必須 snapshot を書けない場合。

    Side effects:
        config_snapshot.json、provenance_snapshot.toml、environment.json を atomic に書きます。
    """
    config_path = template_dir / "config.yaml"
    provenance_path = template_dir / "provenance.toml"
    config_content = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    atomic_write_json(
        run_dir / CONFIG_SNAPSHOT_NAME,
        {
            "path": "config.yaml",
            "state": "present" if config_content else "missing",
            "sha256": hashlib.sha256(config_content.encode("utf-8")).hexdigest(),
            "content": config_content,
            "completion": completion.to_dict(),
        },
    )
    provenance_content = (
        provenance_path.read_text(encoding="utf-8") if provenance_path.is_file() else ""
    )
    atomic_write_text(run_dir / PROVENANCE_SNAPSHOT_NAME, provenance_content)
    atomic_write_json(
        run_dir / ENVIRONMENT_SNAPSHOT_NAME,
        {
            "python": sys.version,
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
            "run_dir": str(run_dir.resolve()),
            "managed_runner_manifest": os.environ.get("EXPERIMENT_RUN_MANIFEST", ""),
            "resource_visibility": os.environ.get("CUDA_VISIBLE_DEVICES", "caller-managed"),
        },
    )
    return CONFIG_SNAPSHOT_NAME, PROVENANCE_SNAPSHOT_NAME, ENVIRONMENT_SNAPSHOT_NAME


def write_case_records(run_dir: Path, records: tuple[CaseResult, ...]) -> None:
    """
    Typed case record 全件を一つの atomic JSONL artifact として serialize します.

    Args:
        run_dir: summary/cases.jsonl を受け取る summary directory。
        records: failure を含む完全な順序付き case record。

    Side effects:
        空の CASES でも空 file を含め、cases.jsonl を atomic replace します。
    """
    content = "".join(
        json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    atomic_write_text(run_dir / RESULT_CASES_NAME, content)


def write_failure_evidence(
    run_dir: Path,
    *,
    status: RunState,
    failure_class: str,
    records: tuple[CaseResult, ...],
    close_condition: str,
    visualization_error: str = "not_applicable",
) -> None:
    """
    Failure-cause classification と rerun closure evidence を保持します.

    Args:
        run_dir: summary/failure-evidence.json を受け取る summary directory。
        status: 現在の run state。
        failure_class: owner boundary が選択した安定した cause category。
        records: failed または blocked の typed case record。
        close_condition: failure を close とみなす前に必要な action。
        visualization_error: 明示的な visualization error または not_applicable。

    Side effects:
        failure-evidence.json を atomic replace します。
    """
    atomic_write_json(
        run_dir / FAILURE_EVIDENCE_NAME,
        {
            "state": status.value,
            "failure_class": failure_class,
            "records": [record.to_dict() for record in records],
            "visualization_error": visualization_error,
            "close_condition": close_condition,
        },
    )


def write_summary(run_dir: Path, summary: RunSummary) -> None:
    """
    Typed RunSummary を summary.json として atomic に公開します.

    Args:
        run_dir: summary/summary.json を受け取る summary directory。
        summary: orchestration が選択した完全な run-level schema。

    Side effects:
        summary.json を atomic replace します。
    """
    atomic_write_json(run_dir / RESULT_SUMMARY_NAME, summary.to_dict())


def write_artifact_manifest(run_dir: Path, summary: RunSummary) -> None:
    """
    Manifest 自身を除く run artifact 全件の digest を公開します.

    Args:
        run_dir: 完全な run snapshot を含む result directory。
        summary: manifest に identity を記録する final run state。

    Raises:
        OSError: materialized artifact を読めない、または manifest の atomic replace に
            失敗した場合。

    Side effects:
        run_dir 内の nested regular file 全件を読み、manifest を atomic に書きます。
    """
    entries = tuple(
        ArtifactEntry(
            path=relative_path,
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(run_dir.rglob("*"))
        if (
            path.is_file()
            and not path.is_symlink()
            and path != run_dir / "summary" / RESULT_MANIFEST_NAME
        )
        for relative_path in (path.relative_to(run_dir).as_posix(),)
    )
    manifest = ArtifactManifest(
        run_id=summary.run_id,
        state=summary.status,
        artifacts=entries,
    )
    atomic_write_json(run_dir / "summary" / RESULT_MANIFEST_NAME, manifest.to_dict())

if __name__ == "__main__":
    raise SystemExit(main())
