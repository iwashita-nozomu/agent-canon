# @dependency-start
# contract reference
# responsibility Owns run-summary and artifact-manifest schemas.
# upstream design ../../../documents/experiments/experiment-registry.md defines reproducibility artifacts.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# @dependency-end

"""
Define the stable schemas for run summaries and artifact manifests.

責務は artifact の型と invariant を宣言することです。JSON serialization、atomic replace、
filesystem traversal は `artifact_io.py` が所有します。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CaseState = Literal["success", "failed", "blocked"]

RESULT_SUMMARY_NAME = "summary.json"
RESULT_CASES_NAME = "cases.jsonl"
RESULT_MANIFEST_NAME = "artifact-manifest.json"
CONFIG_SNAPSHOT_NAME = "config_snapshot.json"
ENVIRONMENT_SNAPSHOT_NAME = "environment.json"
FAILURE_EVIDENCE_NAME = "failure-evidence.json"
VISUALIZATION_STATUS_NAME = "visualization-status.json"
VISUALIZE_NOTEBOOK_NAME = "visualize.ipynb"
EXECUTED_NOTEBOOK_NAME = "visualize_executed.ipynb"


@dataclass(frozen=True)
class ArtifactEntry:
    """
    Describe one materialized file in the artifact manifest.

    Args:
        path: Run-relative artifact filename.
        sha256: Lowercase digest of the complete file bytes.
        size_bytes: Byte size observed after atomic publication.

    Raises:
        ValueError: If the path or digest is blank, or size is negative.

    Side effects:
        The immutable schema record performs no filesystem read.

    Ownership:
        `artifact_io.py` measures and constructs entries; readers verify them.
    """

    path: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        """
        Enforce the manifest-entry invariant before serialization.

        Raises:
            ValueError: If identity is blank or the observed size is negative.
        """
        if not self.path.strip() or not self.sha256.strip():
            raise ValueError("artifact entry identity must be non-empty")
        if self.size_bytes < 0:
            raise ValueError("artifact entry size must not be negative")

    def to_dict(self) -> dict[str, object]:
        """
        Return the JSON object for one manifest entry.

        Returns:
            A mapping with path, SHA-256 digest, and byte size.
        """
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class ArtifactManifest:
    """
    Represent the complete run-relative artifact digest manifest.

    Args:
        run_id: Result directory identity shared with RunSummary.
        state: Terminal run state at manifest publication time.
        artifacts: Entries for every materialized file except this manifest.

    Raises:
        ValueError: If run identity is blank or an entry path is duplicated.

    Side effects:
        Schema construction performs no file I/O.

    Ownership:
        `artifact_io.py` owns publication after summary and case artifacts exist.
    """

    run_id: str
    state: CaseState
    artifacts: tuple[ArtifactEntry, ...]

    def __post_init__(self) -> None:
        """
        Enforce unique run-relative artifact paths.

        Raises:
            ValueError: If run identity is blank or paths are duplicated.
        """
        if not self.run_id.strip():
            raise ValueError("manifest run_id must not be blank")
        paths = [entry.path for entry in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest artifact paths must be unique")

    def to_dict(self) -> dict[str, object]:
        """
        Return the complete JSON manifest projection.

        Returns:
            A JSON-compatible mapping with schema version, state, and digests.
        """
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "state": self.state,
            "artifacts": [entry.to_dict() for entry in self.artifacts],
            "readback": "hash every materialized file except this manifest",
        }


@dataclass(frozen=True)
class RunSummary:
    """
    Aggregate all case records into the run-level acceptance state.

    The invariant is that `status` is derived only from materialized case
    states and post-case infrastructure evidence; no success is inferred from
    an empty or partially written result file.

    Args:
        run_id: Result directory identity.
        status: Terminal run state.
        started_at: RFC3339 UTC run start time.
        finished_at: RFC3339 UTC run finish time.
        exit_status: Process status represented by the run state.
        case_count: Number of materialized case records.
        success_count: Number of successful records.
        failed_count: Number of failed records.
        blocked_count: Number of blocked records.
        failure_class: Stable failure-cause classification.
        failure_evidence: Evidence filename or not_applicable.
        preserved_artifacts: Required artifact filenames for readback.
        close_condition: Human action required before a non-success rerun closes.
        validation_oracle: Necessary-and-sufficient run acceptance oracle.
        visualization_status: Visualization consumer state.

    Raises:
        ValueError: If identity, counts, or exit status violate the schema.

    Side effects:
        Schema construction performs no file I/O.

    Ownership:
        `run.py` derives the fields; `artifact_io.py` serializes the summary.
    """

    run_id: str
    status: CaseState
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

    def __post_init__(self) -> None:
        """
        Enforce count and identity invariants before summary publication.

        Raises:
            ValueError: If counts are negative, inconsistent, or required text
                fields are blank.
        """
        if not self.run_id.strip() or not self.started_at.strip() or not self.finished_at.strip():
            raise ValueError("summary identity and timestamps must be non-empty")
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

    def to_dict(self) -> dict[str, object]:
        """
        Return the complete summary.json projection for this run.

        Returns:
            A JSON-compatible mapping with counts, status, oracle, and artifacts.
        """
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "state": self.status,
            "status": self.status,
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
            "result_files": [
                RESULT_SUMMARY_NAME,
                RESULT_CASES_NAME,
                RESULT_MANIFEST_NAME,
            ],
            "provenance_files": [
                CONFIG_SNAPSHOT_NAME,
                ENVIRONMENT_SNAPSHOT_NAME,
            ],
        }
