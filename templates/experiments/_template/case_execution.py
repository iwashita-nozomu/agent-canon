# @dependency-start
# contract reference
# responsibility Owns one-case execution, domain extension seam, and failure-cause classification.
# upstream design ../../../documents/experiments/experiment-registry.md defines case reproducibility.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# upstream implementation case_model.py defines CaseSpec and CaseResult invariants.
# @dependency-end

"""
Execute one case and convert its outcome into a complete typed record.

責務は case worker の replaceable domain seam、実行時間、failure-cause classification です。
artifact serialization と run-level acceptance は別 module が所有します。
"""

from __future__ import annotations

import json
import subprocess
import time

from artifact_io import FAILURE_EVIDENCE_NAME, utc_now
from case_model import CaseResult, CaseSpec


def failure_class(error: BaseException) -> str:
    """
    Classify an exception without hiding its original message.

    Args:
        error: Observed exception from case or visualization execution.

    Returns:
        One stable failure class consumed by README and provenance readers.

    Side effects:
        Performs type inspection only.
    """
    if isinstance(error, (OSError, TimeoutError, subprocess.SubprocessError)):
        return "infrastructure_environment"
    if isinstance(error, ValueError):
        return "expected_contract"
    return "implementation_algorithm"


def registry_failure(error: BaseException, started_at: str) -> CaseResult:
    """
    Preserve a case-registry import or shape failure as a typed record.

    Args:
        error: Registry error observed at the orchestration boundary.
        started_at: Run start timestamp used as the registry record start.

    Returns:
        A failed `case_registry` record with explicit evidence and classification.

    Side effects:
        Constructs an in-memory record only.
    """
    return CaseResult(
        case_id="case_registry",
        state="failed",
        result={"registry": "unavailable"},
        failure_class=failure_class(error),
        failure_message=f"{type(error).__name__}: {error}",
        failure_evidence=FAILURE_EVIDENCE_NAME,
        started_at=started_at,
        finished_at=utc_now(),
        duration_seconds=0.0,
    )


def run_case_worker(case: CaseSpec, run_dir_text: str) -> CaseResult:
    """
    Execute the replaceable domain case worker and return a typed success record.

    Args:
        case: Case identity and JSON-serializable parameter mapping.
        run_dir_text: Absolute run directory for topic artifact ownership.

    Returns:
        A concrete numeric observation that users can replace with domain logic.

    Raises:
        ValueError: If parameters lack a non-empty numeric values list.
        TypeError: If parameters cease to be JSON-serializable.

    Side effects:
        The scaffold has no domain side effect. Adapted workers must record any
        file, network, device, or mutable-state effect in the result contract.

    Ownership:
        This function is the intended extension point for one domain algorithm;
        it does not own run aggregation or artifact publication.
    """
    json.dumps(case.parameters, ensure_ascii=False, sort_keys=True)
    raw_values = case.parameters.get("values", [])
    if not isinstance(raw_values, list) or not raw_values:
        raise ValueError("case parameters require a non-empty values list")
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in raw_values
    ):
        raise ValueError("case values must be numeric")
    numeric_values = tuple(float(value) for value in raw_values)
    unit = str(case.parameters.get("unit", "unitless"))
    total = sum(numeric_values)
    started_at = utc_now()
    return CaseResult(
        case_id=case.case_id,
        state="success",
        result={
            "case_id": case.case_id,
            "status": "success",
            "run_dir": run_dir_text,
            "case_parameters": dict(case.parameters),
            "observation": {
                "count": len(numeric_values),
                "sum": total,
                "mean": total / len(numeric_values),
                "unit": unit,
                "shape": [len(numeric_values)],
            },
        },
        failure_class="not_applicable",
        failure_message="",
        failure_evidence="not_applicable",
        started_at=started_at,
        finished_at=utc_now(),
        duration_seconds=0.0,
    )


def execute_case(case: CaseSpec, run_dir_text: str) -> CaseResult:
    """
    Execute one case, measure it, and preserve failure semantics.

    Args:
        case: Validated case specification selected by the registry.
        run_dir_text: Absolute run directory passed to the domain worker.

    Returns:
        A terminal success or failed record with measured duration.

    Side effects:
        Invokes the replaceable worker and preserves no artifact directly.
    """
    started_at = utc_now()
    start_clock = time.perf_counter()
    try:
        record = run_case_worker(case, run_dir_text)
        return CaseResult(
            case_id=record.case_id,
            state=record.state,
            result=record.result,
            failure_class=record.failure_class,
            failure_message=record.failure_message,
            failure_evidence=record.failure_evidence,
            started_at=started_at,
            finished_at=record.finished_at,
            duration_seconds=round(time.perf_counter() - start_clock, 6),
        )
    except Exception as error:
        return CaseResult(
            case_id=case.case_id,
            state="failed",
            result={"case_parameters": dict(case.parameters)},
            failure_class=failure_class(error),
            failure_message=f"{type(error).__name__}: {error}",
            failure_evidence=FAILURE_EVIDENCE_NAME,
            started_at=started_at,
            finished_at=utc_now(),
            duration_seconds=round(time.perf_counter() - start_clock, 6),
        )
