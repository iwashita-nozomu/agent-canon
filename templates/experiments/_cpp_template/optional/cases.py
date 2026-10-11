"""Optional native case inputs using the existing CaseSpec field contract."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CaseSpec:
    """One stable case identity and JSON-compatible native parameter mapping."""

    case_id: str
    parameters: dict[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("case_id must not be blank")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.case_id):
            raise ValueError("case_id must be a path-safe segment")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be a dict")
        try:
            json.dumps(self.parameters, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise ValueError("parameters must be JSON-serializable") from error
