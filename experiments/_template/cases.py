"""Minimal case definitions for one experiment topic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExperimentCase:
    """One case for the template experiment."""

    case_id: str
    value: int


def build_cases(limit: int = 8) -> list[ExperimentCase]:
    """Build a small deterministic case list."""
    return [
        ExperimentCase(case_id=f"case_{index:03d}", value=index)
        for index in range(limit)
    ]
