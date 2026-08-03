# @dependency-start
# contract reference
# responsibility Owns the reusable case input and typed case-result models.
# upstream design ../../../documents/experiments/experiment-registry.md defines managed case identity.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# @dependency-end

"""
Define the replaceable case and record models for a managed experiment.

責務は case input の invariant と、cases.jsonl に保存する typed record の schema です。
実行、artifact I/O、resource admission は別 module が所有します。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

CaseState = Literal["success", "failed", "blocked"]


@dataclass(frozen=True)
class CaseSpec:
    """
    Describe one reproducible case input and its ownership boundary.

    `case_id` is unique within a run. `parameters` is JSON-serializable and
    carries units or shapes where the domain requires them.

    Args:
        case_id: Stable identifier used in cases.jsonl and failure evidence.
        parameters: Domain input mapping, including units and shapes where needed.

    Raises:
        ValueError: If the identifier is blank or parameters are not JSON-serializable.

    Side effects:
        Construction validates local state only; it does not allocate resources
        or write artifacts.

    Ownership:
        `cases.py` owns instances; this model owns their invariant.
    """

    case_id: str
    parameters: dict[str, object]

    def __post_init__(self) -> None:
        """
        Enforce the case invariant before a worker receives the case.

        Raises:
            ValueError: If the identifier is blank, parameters are not a dict,
                or the parameters cannot be serialized as JSON.

        Side effects:
            Performs validation only and leaves the supplied mapping unchanged.
        """
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("case_id must not be blank")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be a dict")
        try:
            json.dumps(self.parameters, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise ValueError("parameters must be JSON-serializable") from error


@dataclass(frozen=True)
class CaseResult:
    """
    Represent one case execution with a stable JSON-serializable schema.

    The invariant is that `success` carries an observation in `result`, while
    `failed` or `blocked` carries a failure class, message, and evidence name.

    Args:
        case_id: Stable case identity from the corresponding CaseSpec.
        state: Terminal case state selected by the execution boundary.
        result: JSON-compatible observation or preserved input context.
        failure_class: Stable failure-cause classification or not_applicable.
        failure_message: Human-readable failure detail, empty on success.
        failure_evidence: Artifact name or not_applicable.
        started_at: RFC3339 UTC worker start time.
        finished_at: RFC3339 UTC worker finish time.
        duration_seconds: Measured worker duration in seconds.

    Raises:
        ValueError: If a terminal field is blank or duration is negative.

    Side effects:
        The frozen record performs no file, network, or device side effect.

    Ownership:
        `case_execution.py` constructs records; `artifact_io.py` serializes them.
    """

    case_id: str
    state: CaseState
    result: dict[str, object]
    failure_class: str
    failure_message: str
    failure_evidence: str
    started_at: str
    finished_at: str
    duration_seconds: float

    def __post_init__(self) -> None:
        """
        Validate the record schema before it can be written to cases.jsonl.

        Raises:
            ValueError: If identity, timestamps, failure classification, or
                duration violate the record invariant.

        Side effects:
            Performs local validation and does not serialize or publish the record.
        """
        required_text = (
            self.case_id,
            self.failure_class,
            self.failure_evidence,
            self.started_at,
            self.finished_at,
        )
        if not all(isinstance(value, str) and value.strip() for value in required_text):
            raise ValueError("case result identity and provenance fields must be non-empty")
        if not isinstance(self.result, dict):
            raise ValueError("case result must contain a dict result payload")
        if self.duration_seconds < 0:
            raise ValueError("case duration must not be negative")

    def to_dict(self) -> dict[str, object]:
        """
        Project this record to the line-oriented JSON artifact schema.

        Returns:
            A mapping containing every field required for independent readback.

        Side effects:
            Reads the frozen record only; the caller owns serialization and I/O.
        """
        return {
            "case_id": self.case_id,
            "state": self.state,
            "result": self.result,
            "failure_class": self.failure_class,
            "failure_message": self.failure_message,
            "failure_evidence": self.failure_evidence,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
        }
