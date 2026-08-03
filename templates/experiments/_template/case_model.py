# @dependency-start
# contract reference
# responsibility Owns the reusable case input and typed case-result models.
# upstream design ../../../documents/experiments/experiment-registry.md defines managed case identity.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# @dependency-end

"""
managed experiment 用の replaceable case と record model を定義します。

責務は case input の invariant と、cases.jsonl に保存する typed record の schema です。
実行、artifact I/O、resource admission は別 module が所有します。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Literal

CaseState = Literal["success", "failed", "blocked"]


@dataclass(frozen=True)
class CaseSpec:
    """
    再現可能な case input 一件と、その ownership boundary を記述します。

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
        worker が case を受け取る前に case invariant を強制します。

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
    一件の case execution を安定した JSON-serializable schema で表します。

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
        record は `case_execution.py` が構築し、serialization は `artifact_io.py` が行います。
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
        cases.jsonl へ書く前に record schema を検証します。

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
        この record を line-oriented JSON artifact schema へ projection します。

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
