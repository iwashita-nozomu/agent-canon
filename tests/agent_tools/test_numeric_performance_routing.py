"""Tests for convergence-first numerical performance routing."""

# @dependency-start
# contract test
# responsibility Tests post-run numerical performance routing and the non-numerical C++ boundary.
# upstream implementation ../../tools/agent_tools/route.py owns prompt-derived skill routing
# upstream design ../../agents/skills/computational-optimization.md owns convergence-first numerical performance diagnosis
# upstream design ../../agents/skills/cpp-review.md owns the native performance handoff boundary
# upstream design ../../documents/experiments/experiment-critical-review.md owns post-run experiment review
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTE = PROJECT_ROOT / "tools" / "agent_tools" / "route.py"


def _route(prompt: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(ROUTE), "--prompt", prompt, "--format", "json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _active_skills(prompt: str) -> set[str]:
    return set(_route(prompt)["active_skills"])


def test_changed_iterations_routes_math_before_jit() -> None:
    """A changed numerical trajectory stays on the math owner route."""
    skills = _active_skills(
        "修正して。solver residual performance の iteration count と trajectory が変わった。"
    )
    assert "computational-optimization" in skills
    assert "environment-maintenance" not in skills


def test_same_trajectory_compile_cost_keeps_math_as_gate_and_forbids_math_edit() -> None:
    """An isolated compile cost is a sibling handoff after math evidence."""
    skills = _active_skills(
        "修正して。solver residual performance は same trajectory same iterations。"
        "compile JIT cost だけを分離して sibling handoff する。"
    )
    assert "computational-optimization" in skills
    assert "environment-maintenance" not in skills
    text = (PROJECT_ROOT / "agents/skills/computational-optimization.md").read_text(
        encoding="utf-8"
    )
    assert "systems_cost_isolated" in text
    assert "math writer はその surface を編集しない" in text


def test_total_time_only_stays_unresolved_without_jit_edit() -> None:
    """Total-time-only evidence cannot authorize a JIT change."""
    skills = _active_skills(
        "修正して。solver residual performance は total time しかなく、trajectory は未計測。"
    )
    assert "computational-optimization" in skills
    assert "environment-maintenance" not in skills
    text = (PROJECT_ROOT / "agents/skills/computational-optimization.md").read_text(
        encoding="utf-8"
    )
    assert "evidence_missing" in text
    assert "JIT / architecture の修正へ進まず" in text


def test_nonnumeric_cpp_performance_keeps_existing_route() -> None:
    """Nonnumerical native performance does not acquire numerical routing."""
    decision = _route("non-numeric C++ parser performance review")
    matched = set(decision["matched_skills"])
    assert "cpp-review" in matched
    assert "computational-optimization" not in matched


def test_diagnosis_docs_bind_cost_decomposition_and_post_run_order() -> None:
    """The three owners expose one consistent post-run decomposition and order."""
    optimization = (PROJECT_ROOT / "agents/skills/computational-optimization.md").read_text(
        encoding="utf-8"
    )
    cpp = (PROJECT_ROOT / "agents/skills/cpp-review.md").read_text(encoding="utf-8")
    experiment = (
        PROJECT_ROOT / "documents/experiments/experiment-critical-review.md"
    ).read_text(encoding="utf-8")
    for text in (optimization, cpp, experiment):
        assert "trajectory" in text
        assert "iteration count" in text
    assert "T_{compile/JIT}" in optimization
    assert "T_{compile/JIT}" in experiment
    assert "compile/JIT" in cpp
    assert "run 前の" in optimization
    assert "pass / fail" in optimization
    assert "run 前の pass / fail" in experiment
    assert "non_numeric" in optimization
    for field in (
        "mathematical_problem",
        "initial_state",
        "stopping_policy",
        "run_mode",
        "compile_cache_state",
        "backend",
        "device",
        "compiler",
        "kkt_trajectory",
        "finite_nonfinite_events",
        "work_counters",
        "transfer_seconds",
        "synchronization_seconds",
    ):
        assert field in optimization
    assert "正の回帰" in optimization


def test_catalog_exposes_only_narrow_numeric_performance_route() -> None:
    """The classifier is a computational command, not a generic performance trigger."""
    catalog = (PROJECT_ROOT / "agents/skills/catalog.yaml").read_text(encoding="utf-8")
    start = catalog.index("  - id: computational-optimization")
    end = catalog.index("  - id: adaptive-improvement-loop", start)
    computational = catalog[start:end]
    assert "numeric_performance.py --input <post-run-observations.json>" in computational
    assert '["solver", "performance"]' in computational
    assert '["iterative", "algorithm", "performance"]' in computational
    assert '["performance"]' not in computational

    optimization = (PROJECT_ROOT / "agents/skills/computational-optimization.md").read_text(
        encoding="utf-8"
    )
    assert "numeric_performance.py" in optimization


def test_numeric_solver_performance_trigger_is_not_generic() -> None:
    """Only a solver/iterative-algorithm performance phrase selects math routing."""
    assert "computational-optimization" in _active_skills(
        "solver performance の post-run numerical diagnosis"
    )
    assert "computational-optimization" not in _active_skills(
        "generic performance regression review"
    )
