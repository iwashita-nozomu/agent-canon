#!/usr/bin/env python3
"""Classify post-run numerical performance observations before a JIT handoff.

The input is deliberately a closed, post-run observation record.  The task
supplies ``trajectory_tolerance`` and ``math_oracle``; this tool never invents
a numerical success threshold and never treats a timing-only record as a JIT
authorization.
"""

# @dependency-start
# contract tool
# responsibility Classifies post-run numerical performance evidence into math, systems, unresolved, or non-numeric ownership.
# upstream design ../../agents/skills/computational-optimization.md owns convergence-first numerical performance diagnosis
# upstream design ../../agents/skills/cpp-review.md owns the non-numerical native performance boundary
# downstream implementation ../../tests/agent_tools/test_numeric_performance.py tests observation classification
# @dependency-end

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence

INPUT_SCHEMA = "agent-canon.numeric-performance-observation.v1"
OUTPUT_SCHEMA = "agent-canon.numeric-performance-classification.v1"
SCOPES = frozenset({"numeric_solver", "non_numeric"})
RUN_MODE_VALUES = frozenset({"cold", "warm"})

TOP_LEVEL_FIELDS = frozenset(
    {"schema", "scope", "trajectory_tolerance", "math_oracle", "before", "after"}
)
OBSERVATION_FIELDS = frozenset(
    {
        "total_seconds",
        "compile_jit_seconds",
        "iterations",
        "per_iteration_seconds",
        "eval_seconds",
        "linear_solve_seconds",
        "communication_seconds",
        "transfer_seconds",
        "synchronization_seconds",
        "other_seconds",
        "residual_trajectory",
        "objective_trajectory",
        "kkt_trajectory",
        "step_acceptance",
        "step_sizes",
        "termination",
        "conditioning",
        "inner_solver",
        "inner_solver_work",
        "finite_nonfinite_events",
        "work_counters",
        "mathematical_problem",
        "initial_state",
        "stopping_policy",
        "dtype",
        "workload",
        "run_mode",
        "compile_cache_state",
        "backend",
        "device",
        "compiler",
    }
)
CONTEXT_FIELDS = frozenset(
    {
        "mathematical_problem",
        "initial_state",
        "stopping_policy",
        "dtype",
        "workload",
        "run_mode",
        "compile_cache_state",
        "backend",
        "device",
        "compiler",
    }
)
WORK_COUNTER_FIELDS = frozenset(
    {
        "objective_evaluations",
        "gradient_evaluations",
        "evaluation_count",
        "linear_solve_count",
        "linear_solve_iterations",
        "matvec_count",
        "inner_solver_iterations",
        "inner_solver_acceptance",
    }
)
REQUIRED_COMMON_FIELDS = frozenset({"total_seconds"})
REQUIRED_NUMERICAL_FIELDS = frozenset(
    {
        "compile_jit_seconds",
        "iterations",
        "per_iteration_seconds",
        "eval_seconds",
        "linear_solve_seconds",
        "communication_seconds",
        "transfer_seconds",
        "synchronization_seconds",
        "other_seconds",
        "residual_trajectory",
        "objective_trajectory",
        "kkt_trajectory",
        "step_acceptance",
        "step_sizes",
        "termination",
        "conditioning",
        "inner_solver",
        "inner_solver_work",
        "finite_nonfinite_events",
        "work_counters",
    }
)
REQUIRED_CONTEXT_FIELDS = CONTEXT_FIELDS
TIMING_FIELDS = (
    "compile_jit_seconds",
    "per_iteration_seconds",
    "eval_seconds",
    "linear_solve_seconds",
    "communication_seconds",
    "transfer_seconds",
    "synchronization_seconds",
    "other_seconds",
    "total_seconds",
)
TRAJECTORY_FIELDS = frozenset(
    {"residual_trajectory", "objective_trajectory", "kkt_trajectory"}
)
FORBIDDEN_NON_MATH_WRITES = (
    "architecture",
    "framework",
    "JIT",
    "compiler",
    "backend",
    "runtime",
    "container",
    "routing",
    "environment",
)


class ObservationError(ValueError):
    """Raised when the closed post-run observation shape is invalid."""


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ObservationError(f"{field}:mapping_required")
    unknown = sorted(set(value).difference(OBSERVATION_FIELDS))
    if unknown:
        raise ObservationError(f"{field}:unknown_fields:{','.join(unknown)}")
    return value


def _number(value: object, field: str, *, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationError(f"{field}:number_required")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ObservationError(f"{field}:finite_nonnegative_required")
    return result


def _scalar(value: object, field: str) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationError(f"{field}:number_required")
    result = float(value)
    if not math.isfinite(result):
        raise ObservationError(f"{field}:finite_number_required")
    return result


def _number_list(value: object, field: str) -> list[float]:
    if not isinstance(value, list):
        raise ObservationError(f"{field}:list_required")
    return [_scalar(item, f"{field}[{index}]") for index, item in enumerate(value)]  # type: ignore[list-item]


def _bool_list(value: object, field: str) -> list[bool]:
    if not isinstance(value, list) or any(not isinstance(item, bool) for item in value):
        raise ObservationError(f"{field}:boolean_list_required")
    return list(value)


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ObservationError(f"{field}:list_required")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ObservationError(f"{field}[{index}]:nonempty_string_required")
        result.append(item)
    return result


def _context_value(value: object, field: str) -> object:
    """Normalize one task-owned comparison identity without inventing semantics."""
    if isinstance(value, str):
        if not value.strip():
            raise ObservationError(f"{field}:nonempty_string_required")
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ObservationError(f"{field}:finite_number_required")
        return value
    if isinstance(value, list):
        return [_context_value(item, f"{field}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ObservationError(f"{field}:string_keys_required")
            result[key] = _context_value(item, f"{field}.{key}")
        return result
    raise ObservationError(f"{field}:json_identity_required")


def _work_counters(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ObservationError(f"{field}:mapping_required")
    unknown = sorted(set(value).difference(WORK_COUNTER_FIELDS))
    missing = sorted(WORK_COUNTER_FIELDS.difference(value))
    if unknown:
        raise ObservationError(f"{field}:unknown_fields:{','.join(unknown)}")
    if missing:
        raise ObservationError(f"{field}:missing_fields:{','.join(missing)}")
    result: dict[str, object] = {}
    for name in sorted(WORK_COUNTER_FIELDS):
        item = value[name]
        item_field = f"{field}.{name}"
        if name == "inner_solver_acceptance":
            result[name] = _bool_list(item, item_field)
            continue
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ObservationError(f"{item_field}:nonnegative_integer_required")
        result[name] = item
    return result


def _inner_solver(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ObservationError(f"{field}:mapping_required")
    expected = {"name", "iterations", "work"}
    unknown = sorted(set(value).difference(expected))
    missing = sorted(expected.difference(value))
    if unknown:
        raise ObservationError(f"{field}:unknown_fields:{','.join(unknown)}")
    if missing:
        raise ObservationError(f"{field}:missing_fields:{','.join(missing)}")
    name = value["name"]
    if not isinstance(name, str) or not name.strip():
        raise ObservationError(f"{field}.name:nonempty_string_required")
    iterations = value["iterations"]
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 0:
        raise ObservationError(f"{field}.iterations:nonnegative_integer_required")
    work = _number(value["work"], f"{field}.work")
    return {"name": name, "iterations": iterations, "work": work}


def _normalize_observation(raw: object, field: str) -> dict[str, object]:
    value = _mapping(raw, field)
    missing = sorted(REQUIRED_COMMON_FIELDS.difference(value))
    if missing:
        raise ObservationError(f"{field}:missing_fields:{','.join(missing)}")
    result: dict[str, object] = {
        "total_seconds": _number(value["total_seconds"], f"{field}.total_seconds")
    }
    for name in sorted(set(value).difference(REQUIRED_COMMON_FIELDS)):
        item = value[name]
        item_field = f"{field}.{name}"
        if name.endswith("_seconds"):
            result[name] = _number(item, item_field)
        elif name == "iterations":
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise ObservationError(f"{item_field}:nonnegative_integer_required")
            result[name] = item
        elif name in {
            "residual_trajectory",
            "objective_trajectory",
            "kkt_trajectory",
            "step_sizes",
        }:
            result[name] = _number_list(item, item_field)
        elif name == "step_acceptance":
            result[name] = _bool_list(item, item_field)
        elif name == "finite_nonfinite_events":
            result[name] = _string_list(item, item_field)
        elif name == "termination":
            if not isinstance(item, str) or not item.strip():
                raise ObservationError(f"{item_field}:nonempty_string_required")
            result[name] = item
        elif name == "conditioning":
            result[name] = _number(item, item_field)
        elif name == "inner_solver":
            result[name] = _inner_solver(item, item_field)
        elif name == "inner_solver_work":
            result[name] = _number(item, item_field)
        elif name == "work_counters":
            result[name] = _work_counters(item, item_field)
        elif name in CONTEXT_FIELDS:
            context_value = _context_value(item, item_field)
            if name == "run_mode" and (
                not isinstance(context_value, str)
                or context_value not in RUN_MODE_VALUES
            ):
                raise ObservationError(f"{item_field}:cold_or_warm_required")
            result[name] = context_value
        else:  # pragma: no cover - closed field set makes this unreachable.
            raise ObservationError(f"{item_field}:unsupported")
    return result


def normalize_observation(raw: object) -> dict[str, object]:
    """Validate and normalize one closed post-run observation packet."""
    if not isinstance(raw, Mapping):
        raise ObservationError("input:mapping_required")
    unknown = sorted(set(raw).difference(TOP_LEVEL_FIELDS))
    missing = sorted(TOP_LEVEL_FIELDS.difference(raw))
    if unknown:
        raise ObservationError(f"input:unknown_fields:{','.join(unknown)}")
    if missing:
        raise ObservationError(f"input:missing_fields:{','.join(missing)}")
    if raw["schema"] != INPUT_SCHEMA:
        raise ObservationError("input.schema:mismatch")
    scope = raw["scope"]
    if not isinstance(scope, str) or scope not in SCOPES:
        raise ObservationError("input.scope:unknown")
    tolerance = raw["trajectory_tolerance"]
    if scope == "numeric_solver":
        tolerance_value = _number(tolerance, "input.trajectory_tolerance")
        oracle = raw["math_oracle"]
        if not isinstance(oracle, str) or not oracle.strip():
            raise ObservationError("input.math_oracle:nonempty_string_required")
    else:
        if tolerance is not None or raw["math_oracle"] is not None:
            raise ObservationError("input.non_numeric:math_fields_must_be_null")
        tolerance_value = None
        oracle = None
    return {
        "schema": INPUT_SCHEMA,
        "scope": scope,
        "trajectory_tolerance": tolerance_value,
        "math_oracle": oracle,
        "before": _normalize_observation(raw["before"], "before"),
        "after": _normalize_observation(raw["after"], "after"),
    }


def _equivalent(left: object, right: object, tolerance: float) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=tolerance, abs_tol=tolerance)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _equivalent(item_left, item_right, tolerance)
            for item_left, item_right in zip(left, right)
        )
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(
            _equivalent(left[key], right[key], tolerance) for key in left
        )
    return left == right


def _complete_numerical_observation(observation: Mapping[str, object]) -> bool:
    return REQUIRED_NUMERICAL_FIELDS.issubset(observation) and REQUIRED_CONTEXT_FIELDS.issubset(
        observation
    )


def _cost_decomposition(
    before: Mapping[str, object], after: Mapping[str, object]
) -> dict[str, dict[str, object]]:
    fields = ("iterations", *TIMING_FIELDS)
    return {
        "before": {field: before.get(field) for field in fields},
        "after": {field: after.get(field) for field in fields},
    }


def _result(
    category: str,
    owner_route: str,
    next_action: str,
    forbidden_writes: Sequence[str],
    separate_handoff: Mapping[str, str],
    evidence: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": OUTPUT_SCHEMA,
        "category": category,
        "owner_route": owner_route,
        "next_action": next_action,
        "forbidden_writes": list(forbidden_writes),
        "separate_handoff": dict(separate_handoff),
        "evidence": dict(evidence),
    }


def classify(raw: object) -> dict[str, object]:
    """Classify one validated post-run observation record."""
    packet = normalize_observation(raw)
    before = packet["before"]
    after = packet["after"]
    assert isinstance(before, Mapping)
    assert isinstance(after, Mapping)
    cost = _cost_decomposition(before, after)
    evidence: dict[str, object] = {
        "math_oracle": packet["math_oracle"],
        "trajectory_tolerance": packet["trajectory_tolerance"],
        "cost_decomposition": cost,
    }
    if packet["scope"] == "non_numeric":
        return _result(
            "non_numeric",
            "cpp-review",
            "use the existing native performance review order",
            (),
            {
                "route": "computational-optimization",
                "status": "not_applicable",
                "reason": "the observation does not describe a numerical solver or iterative algorithm",
            },
            evidence,
        )

    missing_before = sorted(
        (REQUIRED_NUMERICAL_FIELDS | REQUIRED_CONTEXT_FIELDS).difference(before)
    )
    missing_after = sorted(
        (REQUIRED_NUMERICAL_FIELDS | REQUIRED_CONTEXT_FIELDS).difference(after)
    )
    evidence["missing_fields"] = {"before": missing_before, "after": missing_after}
    if not _complete_numerical_observation(before) or not _complete_numerical_observation(after):
        return _result(
            "evidence_missing",
            "computational-optimization",
            "collect the missing trajectory and cost-decomposition metrics before proposing a JIT or architecture edit",
            FORBIDDEN_NON_MATH_WRITES,
            {
                "route": "jit-backend-performance",
                "status": "forbidden",
                "reason": "post-run numerical evidence is incomplete",
            },
            evidence,
        )

    context_mismatches = [
        field
        for field in sorted(REQUIRED_CONTEXT_FIELDS)
        if before[field] != after[field]
    ]
    evidence["context_mismatches"] = context_mismatches
    if context_mismatches:
        return _result(
            "evidence_missing",
            "computational-optimization",
            "rerun or align the same mathematical problem, initial state, stopping policy, dtype, workload, run mode, cache, backend, device, and compiler before attributing a cost to JIT",
            FORBIDDEN_NON_MATH_WRITES,
            {
                "route": "jit-backend-performance",
                "status": "forbidden",
                "reason": "before/after comparison context is not identical",
            },
            evidence,
        )

    tolerance = packet["trajectory_tolerance"]
    assert isinstance(tolerance, float)
    semantic_fields = tuple(sorted(REQUIRED_NUMERICAL_FIELDS.difference(TIMING_FIELDS)))
    changed_fields = [
        field
        for field in semantic_fields
        if (
            field in TRAJECTORY_FIELDS
            and not _equivalent(before[field], after[field], tolerance)
        )
        or (field not in TRAJECTORY_FIELDS and before[field] != after[field])
    ]
    evidence["changed_numerical_fields"] = changed_fields
    if changed_fields:
        return _result(
            "convergence_changed",
            "computational-optimization",
            "repair the mathematical or algorithmic mechanism from the first changed iteration; keep JIT and architecture unchanged",
            FORBIDDEN_NON_MATH_WRITES,
            {
                "route": "jit-backend-performance",
                "status": "deferred",
                "reason": "numerical trajectory or iteration behavior changed",
            },
            evidence,
        )

    positive_cost_regressions = [
        field
        for field in TIMING_FIELDS
        if float(after[field]) > float(before[field])
    ]
    evidence["positive_cost_regressions"] = positive_cost_regressions
    if not positive_cost_regressions:
        return _result(
            "evidence_missing",
            "computational-optimization",
            "take no action: the numerical work is equivalent but no positive performance regression was measured",
            FORBIDDEN_NON_MATH_WRITES,
            {
                "route": "jit-backend-performance",
                "status": "forbidden",
                "reason": "identical or non-regressed timing does not justify a systems edit",
            },
            evidence,
        )

    return _result(
        "systems_cost_isolated",
        "jit-backend-performance",
        "handoff the isolated compile/JIT or per-iteration systems cost with the numerical record attached; do not edit math sources",
        ("mathematical algorithm", "tolerance / stopping semantics"),
        {
            "route": "computational-optimization",
            "status": "read_only",
            "reason": "numerical trajectory, iterations, termination, conditioning, and inner-solver work are equivalent under the task tolerance",
        },
        evidence,
    )


def _read_input(path: str | None) -> object:
    if path is None or path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def main(argv: Sequence[str] | None = None) -> int:
    """Read one observation packet and print its JSON classification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="post-run observation JSON path; use - or omit for stdin")
    parser.add_argument("--format", choices=("json",), default="json")
    args = parser.parse_args(argv)
    try:
        result = classify(_read_input(args.input))
    except (OSError, json.JSONDecodeError, ObservationError) as exc:
        result = {
            "schema": OUTPUT_SCHEMA,
            "status": "error",
            "error": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
