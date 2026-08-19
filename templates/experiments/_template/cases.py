# @dependency-start
# contract template
# responsibility Owns topic case definitions, typed case records, worker execution, and failure classification.
# upstream design ../../../documents/design/experiment-topic-template.md defines the single case owner.
# downstream implementation run.py owns run-level aggregation and atomic artifact publication.
# @dependency-end

"""Topic-owned case model, registry, execution seam, and failure semantics."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Literal

CaseState = Literal["success", "failed", "blocked"]


@dataclass(frozen=True)
class CaseSpec:
    """
    再現可能な case input 一件と、その ownership boundary を記述します.

    `case_id` は run 内で一意です。`parameters` は JSON-serializable で、domain が必要とする
    unit や shape を保持します。

    Args:
        case_id: cases.jsonl と failure evidence で使う安定した identifier。
        parameters: 必要な unit と shape を含む domain input mapping。

    Raises:
        ValueError: identifier が空、または parameters が JSON-serializable でない場合。

    Side effects:
        構築は local state だけを検証し、resource allocation や artifact write を行いません。

    Ownership:
        instance は `cases.py` が所有し、invariant はこの model が所有します。
    """

    case_id: str
    parameters: dict[str, object]

    def __post_init__(self) -> None:
        """
        Worker が case を受け取る前に case invariant を強制します.

        Raises:
            ValueError: identifier が空、parameters が dict でない、または JSON serialize
                できない場合。

        Side effects:
            検証だけを行い、渡された mapping は変更しません。
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
    一件の case execution を安定した JSON-serializable schema で表します.

    invariant は `success` が `result` に observation を持ち、`failed` または `blocked` が
    failure class、message、evidence name を持つことです。

    Args:
        case_id: 対応する CaseSpec からの安定した case identity。
        state: execution boundary が選択する terminal case state。
        result: JSON-compatible observation または保持した input context。
        failure_class: 安定した failure-cause classification または not_applicable。
        failure_message: 人間向け failure detail。success では空。
        failure_evidence: artifact name または not_applicable。
        started_at: RFC3339 UTC worker start time。
        finished_at: RFC3339 UTC worker finish time。
        duration_seconds: worker が計測した秒単位の duration。

    Raises:
        ValueError: terminal field が空、または duration が不正な場合。

    Side effects:
        frozen record は file、network、device の side effect を行いません。

    Ownership:
        record は `cases.py` が構築し、serialization は `run.py` が行います。
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
        cases.jsonl へ書く前に record schema を検証します.

        Raises:
            ValueError: identity、timestamp、failure classification、duration が record
                invariant に違反する場合。

        Side effects:
            local validation だけを行い、record の serialize/publication は行いません。
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
        if self.state not in {"success", "failed", "blocked"}:
            raise ValueError("case state must be terminal success, failed, or blocked")
        if not isinstance(self.result, dict):
            raise ValueError("case result must contain a dict result payload")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise ValueError("case duration must be finite and non-negative")
        if self.state == "success":
            if not self.result:
                raise ValueError("successful case must publish an observation")
            if (
                self.failure_class != "not_applicable"
                or self.failure_message
                or self.failure_evidence != "not_applicable"
            ):
                raise ValueError("successful case cannot carry failure fields")
        elif (
            self.failure_class == "not_applicable"
            or not self.failure_message.strip()
            or self.failure_evidence == "not_applicable"
        ):
            raise ValueError("failed or blocked case requires failure fields")

    def to_dict(self) -> dict[str, object]:
        """
        この record を line-oriented JSON artifact schema へ projection します.

        Returns:
            独立 readback に必要な全 field を含む mapping。

        Side effects:
            frozen record だけを読み、serialization と I/O は caller が所有します。
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

from datetime import UTC, datetime
import subprocess
import time

FAILURE_EVIDENCE_NAME = "failure-evidence.json"

def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")

import subprocess
import time



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


def run_case_worker(case: CaseSpec, run_dir_text: str) -> CaseResult:
    """
    実行可能な domain case worker を実行し、typed success record を返します.

    Args:
        case: case identity と JSON-serializable parameter mapping。
        run_dir_text: topic artifact ownership 用の absolute run directory。

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
    Case 一件を実行・計測し、failure semantics を保持します.

    Args:
        case: registry が選択した検証済み case specification。
        run_dir_text: domain worker に渡す absolute run directory。

    Returns:
        計測 duration を持つ terminal success または failed record。

    Side effects:
        replaceable worker を呼び、artifact は直接保持しません。
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

# The default registry is intentionally small; topics replace it with their domain cases.
CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        case_id="example",
        parameters={
            "values": [1.0, 2.0, 3.0],
            "unit": "unitless",
            "shape": [3],
        },
    ),
)
