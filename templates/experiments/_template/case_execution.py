# @dependency-start
# contract reference
# responsibility Owns one-case execution, domain extension seam, and failure-cause classification.
# upstream design ../../../documents/experiments/experiment-registry.md defines case reproducibility.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# upstream implementation case_model.py defines CaseSpec and CaseResult invariants.
# @dependency-end

"""
Case 一件を実行し、その outcome を完全な typed record へ変換します.

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
    元の message を隠さず exception を分類します.

    Args:
        error: case または visualization execution で観測した exception。

    Returns:
        README と provenance reader が使う安定した failure class。

    Side effects:
        type inspection だけを行います。
    """
    if isinstance(error, (OSError, TimeoutError, subprocess.SubprocessError)):
        return "infrastructure_environment"
    if isinstance(error, ValueError):
        return "expected_contract"
    return "implementation_algorithm"


def registry_failure(error: BaseException, started_at: str) -> CaseResult:
    """
    Case registry の import または shape failure を typed record として保持します.

    Args:
        error: orchestration boundary で観測した registry error。
        started_at: registry record の start に使う run start timestamp。

    Returns:
        明示的な evidence と classification を持つ failed `case_registry` record。

    Side effects:
        memory 上の record だけを構築します。
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


def run_case_worker(
    case: CaseSpec,
    run_dir_text: str,
    raw_dir_text: str,
) -> CaseResult:
    """
    実行可能な domain case worker を実行し、typed success record を返します.

    Args:
        case: case identity と JSON-serializable parameter mapping。
        run_dir_text: compact review evidence 用の absolute result directory。
        raw_dir_text: bulky artifact 用の absolute raw directory。

    Returns:
        利用者が domain logic に置換できる具体的な numeric observation。

    Raises:
        ValueError: parameters に空でない numeric values list がない場合。
        TypeError: parameters が JSON-serializable でなくなった場合。

    Side effects:
        scaffold に domain side effect はありません。適応した worker は file、network、device、
        mutable-state の effect を result contract に記録します。

    Ownership:
        この function が一つの domain algorithm の extension point です。run aggregation と
        artifact publication は所有しません。
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
            "raw_dir": raw_dir_text,
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


def execute_case(
    case: CaseSpec,
    run_dir_text: str,
    raw_dir_text: str,
) -> CaseResult:
    """
    Case 一件を実行・計測し、failure semantics を保持します.

    Args:
        case: registry が選択した検証済み case specification。
        run_dir_text: domain worker に渡す compact result directory。
        raw_dir_text: domain worker に渡す bulky raw directory。

    Returns:
        計測 duration を持つ terminal success または failed record。

    Side effects:
        replaceable worker を呼び、artifact は直接保持しません。
    """
    started_at = utc_now()
    start_clock = time.perf_counter()
    try:
        record = run_case_worker(case, run_dir_text, raw_dir_text)
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
