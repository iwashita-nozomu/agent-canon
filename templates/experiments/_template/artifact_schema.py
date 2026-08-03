# @dependency-start
# contract reference
# responsibility Owns run-summary and artifact-manifest schemas.
# upstream design ../../../documents/experiments/experiment-registry.md defines reproducibility artifacts.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# @dependency-end

"""
Run summary と artifact manifest の安定 schema を定義します.

責務は artifact の型と invariant を宣言することです。JSON serialization、atomic replace、
filesystem traversal は `artifact_io.py` が所有します。
"""

from __future__ import annotations

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
CONFIG_SNAPSHOT_NAME = "config_snapshot.json"
ENVIRONMENT_SNAPSHOT_NAME = "environment.json"
PROVENANCE_SNAPSHOT_NAME = "provenance_snapshot.toml"
FAILURE_EVIDENCE_NAME = "failure-evidence.json"
VISUALIZATION_STATUS_NAME = "visualization-status.json"
VISUALIZE_NOTEBOOK_NAME = "visualize.ipynb"
EXECUTED_NOTEBOOK_NAME = "visualize_executed.ipynb"

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
        artifact_io.py が source を読み、run.py が acceptance に利用します。
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
        `artifact_io.py` が計測と entry 構築を行い、reader が検証します。
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
        summary と case artifact の存在後の publication は `artifact_io.py` が所有します。
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
        field は `run.py` が導出し、summary の serialization は `artifact_io.py` が行います。
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
            RESULT_SUMMARY_NAME,
            RESULT_CASES_NAME,
            RESULT_MANIFEST_NAME,
            CONFIG_SNAPSHOT_NAME,
            ENVIRONMENT_SNAPSHOT_NAME,
            PROVENANCE_SNAPSHOT_NAME,
            VISUALIZATION_STATUS_NAME,
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
                RESULT_SUMMARY_NAME,
                RESULT_CASES_NAME,
                RESULT_MANIFEST_NAME,
            ],
            "provenance_files": [
                CONFIG_SNAPSHOT_NAME,
                ENVIRONMENT_SNAPSHOT_NAME,
                PROVENANCE_SNAPSHOT_NAME,
            ],
        }
