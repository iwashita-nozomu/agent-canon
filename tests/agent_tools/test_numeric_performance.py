"""Tests for the strict post-run numerical performance classifier."""

# @dependency-start
# contract test
# responsibility Tests real observation classification and owner/handoff output.
# upstream implementation ../../tools/analysis/numerical/numeric_performance.py owns the closed JSON classifier
# upstream design ../../agents/skills/computational-optimization.md owns numerical performance ownership
# downstream implementation ../../agents/skills/catalog.yaml exposes the classifier command
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = PROJECT_ROOT / "tools" / "analysis" / "numerical" / "numeric_performance.py"
INPUT_SCHEMA = "agent-canon.numeric-performance-observation.v1"


def _observation(
    *,
    after_changes: dict[str, object] | None = None,
    scope: str = "numeric_solver",
) -> dict[str, object]:
    base = {
        "total_seconds": 1.0,
        "compile_jit_seconds": 0.2,
        "iterations": 2,
        "per_iteration_seconds": 0.4,
        "eval_seconds": 0.2,
        "linear_solve_seconds": 0.1,
        "communication_seconds": 0.05,
        "transfer_seconds": 0.03,
        "synchronization_seconds": 0.02,
        "other_seconds": 0.05,
        "residual_trajectory": [1.0, 0.2, 0.01],
        "objective_trajectory": [4.0, 1.0, 0.25],
        "kkt_trajectory": [2.0, 0.4, 0.02],
        "step_acceptance": [True, True],
        "step_sizes": [0.5, 0.25],
        "termination": "converged",
        "conditioning": 10.0,
        "inner_solver": {"name": "cg", "iterations": 3, "work": 3.0},
        "inner_solver_work": 3.0,
        "finite_nonfinite_events": ["all_finite"],
        "work_counters": {
            "objective_evaluations": 3,
            "gradient_evaluations": 3,
            "evaluation_count": 6,
            "linear_solve_count": 2,
            "linear_solve_iterations": 3,
            "matvec_count": 4,
            "inner_solver_iterations": 3,
            "inner_solver_acceptance": [True, True],
        },
        "mathematical_problem": "quadratic-v1",
        "initial_state": "x0=[1,1]",
        "stopping_policy": "residual<=task-tolerance",
        "dtype": "float64",
        "workload": "case-1",
        "run_mode": "warm",
        "compile_cache_state": "cache-hit",
        "backend": "jax",
        "device": "gpu:0",
        "compiler": "xla-2026.08",
    }
    before = deepcopy(base)
    after = deepcopy(base)
    if after_changes:
        after.update(after_changes)
    if scope == "non_numeric":
        return {
            "schema": INPUT_SCHEMA,
            "scope": scope,
            "trajectory_tolerance": None,
            "math_oracle": None,
            "before": {"total_seconds": before["total_seconds"]},
            "after": {"total_seconds": after["total_seconds"]},
        }
    return {
        "schema": INPUT_SCHEMA,
        "scope": scope,
        "trajectory_tolerance": 1e-8,
        "math_oracle": "task-owned residual and objective trajectory equivalence",
        "before": before,
        "after": after,
    }


def _classify(packet: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLASSIFIER), "--input", "-", "--format", "json"],
        cwd=PROJECT_ROOT,
        input=json.dumps(packet),
        capture_output=True,
        check=False,
        text=True,
    )


def _result(packet: dict[str, object]) -> dict[str, object]:
    result = _classify(packet)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_slower_run_with_more_iterations_routes_to_math() -> None:
    """A changed trajectory/iteration count is a mathematical diagnosis."""
    packet = _observation(
        after_changes={
            "total_seconds": 2.0,
            "iterations": 5,
            "residual_trajectory": [1.0, 0.8, 0.6, 0.4, 0.2, 0.1],
            "objective_trajectory": [4.0, 3.0, 2.5, 2.0, 1.5, 1.0],
            "step_acceptance": [True, False, True, False, True],
            "step_sizes": [0.5, 0.1, 0.2, 0.1, 0.05],
        }
    )
    result = _result(packet)
    assert result["category"] == "convergence_changed"
    assert result["owner_route"] == "computational-optimization"
    assert "JIT" in result["forbidden_writes"]
    assert result["evidence"]["changed_numerical_fields"]


def test_same_trajectory_with_compile_and_per_iteration_delta_routes_systems() -> None:
    """Equivalent numerical work permits only a separate systems handoff."""
    result = _result(
        _observation(
            after_changes={
                "total_seconds": 1.8,
                "compile_jit_seconds": 0.8,
                "per_iteration_seconds": 0.55,
                "eval_seconds": 0.3,
                "linear_solve_seconds": 0.15,
                "communication_seconds": 0.07,
            }
        )
    )
    assert result["category"] == "systems_cost_isolated"
    assert result["owner_route"] == "jit-backend-performance"
    assert "mathematical algorithm" in result["forbidden_writes"]
    assert result["separate_handoff"]["route"] == "computational-optimization"


def test_context_mismatch_is_unresolved_and_forbids_jit() -> None:
    """Different problem context cannot establish isolated systems causality."""
    result = _result(
        _observation(after_changes={"mathematical_problem": "different-problem"})
    )
    assert result["category"] == "evidence_missing"
    assert result["owner_route"] == "computational-optimization"
    assert "mathematical_problem" in result["evidence"]["context_mismatches"]
    assert "JIT" in result["forbidden_writes"]


def test_kkt_or_finite_event_change_routes_to_math() -> None:
    """KKT or finite/non-finite behavior is numerical evidence, not JIT evidence."""
    for changes in (
        {"kkt_trajectory": [2.0, 1.5, 1.0]},
        {"finite_nonfinite_events": ["nonfinite_residual"]},
    ):
        with_changes = _result(_observation(after_changes=changes))
        assert with_changes["category"] == "convergence_changed"
        assert with_changes["owner_route"] == "computational-optimization"


def test_work_counter_change_routes_to_math() -> None:
    """Changed objective/linear/inner work is an algorithmic change."""
    counters = deepcopy(_observation()["after"]["work_counters"])
    counters["linear_solve_iterations"] = 8
    result = _result(_observation(after_changes={"work_counters": counters}))
    assert result["category"] == "convergence_changed"
    assert "work_counters" in result["evidence"]["changed_numerical_fields"]


def test_identical_times_are_no_action_not_systems() -> None:
    """Equivalent work with no positive regression cannot create a systems handoff."""
    result = _result(_observation())
    assert result["category"] == "evidence_missing"
    assert result["next_action"].startswith("take no action")
    assert result["owner_route"] == "computational-optimization"
    assert result["separate_handoff"]["status"] == "forbidden"


def test_total_only_regression_is_unattributed_not_systems() -> None:
    """A larger summary time cannot attribute a component or authorize JIT."""
    result = _result(_observation(after_changes={"total_seconds": 2.0}))
    assert result["category"] == "evidence_missing"
    assert result["reason_code"] == "unattributed_total"
    assert result["owner_route"] == "computational-optimization"
    assert "JIT" in result["forbidden_writes"]
    assert result["separate_handoff"]["status"] == "forbidden"


def test_total_time_only_is_missing_evidence_and_forbids_jit() -> None:
    """Timing without numerical observations remains unresolved."""
    packet = _observation()
    packet["before"] = {"total_seconds": 1.0}
    packet["after"] = {"total_seconds": 2.0}
    result = _result(packet)
    assert result["category"] == "evidence_missing"
    assert result["owner_route"] == "computational-optimization"
    assert "JIT" in result["forbidden_writes"]
    assert result["separate_handoff"]["status"] == "forbidden"


def test_nonnumeric_cpp_observation_keeps_cpp_route() -> None:
    """Non-numerical native performance does not enter the math route."""
    result = _result(_observation(scope="non_numeric"))
    assert result["category"] == "non_numeric"
    assert result["owner_route"] == "cpp-review"
    assert result["separate_handoff"]["status"] == "not_applicable"


def test_schema_rejects_unknown_observation_fields() -> None:
    """The CLI fails closed instead of silently accepting a second schema."""
    packet = _observation()
    packet["after"] = {**packet["after"], "jit_guess": 1.0}
    result = _classify(packet)
    assert result.returncode == 2
    error = json.loads(result.stdout)
    assert error["status"] == "error"
    assert "unknown_fields:jit_guess" in error["error"]
