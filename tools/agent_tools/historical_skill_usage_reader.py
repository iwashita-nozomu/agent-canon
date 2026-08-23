#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Reads archived skill_usage.jsonl as immutable historical evidence.
# upstream design ../../documents/design/agentcanon-hook-simplification-wave3.md forbids an active producer.
# downstream implementation ./generate_agent_improvement_guide.py consumes historical readback.
# downstream implementation ./generate_agent_runtime_dashboard.py may consume historical migration evidence.
# downstream implementation ../../tests/agent_tools/test_historical_skill_usage_reader.py validates read-only parsing.
# @dependency-end
"""Historical, read-only parser for the retired skill usage artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HistoricalReadback:
    records: tuple[dict[str, Any], ...] = ()
    accepted_count: int = 0
    malformed_count: int = 0
    ignored_count: int = 0
    malformed_by_reason: dict[str, int] | None = None
    status: str = "missing"


def _result(
    records: list[dict[str, Any]], malformed: int, ignored: int, reasons: dict[str, int], status: str
) -> HistoricalReadback:
    return HistoricalReadback(tuple(records), len(records), malformed, ignored, dict(reasons), status)


def read_skill_usage_history(path: Path) -> HistoricalReadback:
    """Open and parse history without importing, executing, appending, or rewriting it."""
    if not path.exists():
        return HistoricalReadback()
    records: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    malformed = 0
    ignored = 0
    try:
        lines = path.read_bytes().splitlines()
    except OSError:
        return _result([], 1, 0, {"line_encoding": 1}, "malformed")
    for raw in lines:
        if not raw.strip():
            ignored += 1
            continue
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed += 1
            reasons["json"] = reasons.get("json", 0) + 1
            continue
        if not isinstance(value, dict):
            malformed += 1
            reasons["field_type"] = reasons.get("field_type", 0) + 1
            continue
        records.append(value)
    status = "malformed" if malformed else "present"
    return _result(records, malformed, ignored, reasons, status)
