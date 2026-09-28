"""Behavioral coverage for the catalog-owned bounded execution route."""

# @dependency-start
# contract test
# responsibility Checks bounded route admission, sparse output, escalation, and unavailable validation.
# upstream design ../../agents/task_catalog.yaml execution route policy
# upstream implementation ../../tools/agent/orchestration/route.py route selection and CLI
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tools.agent.orchestration.route import RISK_VALUES, decide_execution

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "tools/agent/orchestration/route.py"


@pytest.fixture
def context() -> dict[str, object]:
    return {
        "roots": 1,
        "owners": 1,
        "writers": 1,
        "scope_resolved": True,
        "contract_resolved": True,
        "validation": "python -m pytest tests/unit/test_example.py -q",
        "coordination": [],
    }


@pytest.mark.parametrize("oracle", ["git diff --check", "python -m pytest tests/unit/test_example.py -q"])
def test_document_and_code_tasks_have_only_three_states(context, oracle):
    result = decide_execution(ROOT, {**context, "validation": oracle})
    assert result == {
        "execution_route": "bounded_fast_path",
        "states": ["route", "execute", "verify_close"],
        "next_action": "report_selected_results_and_publication_readback",
        "commands": [],
        "selected_validation": oracle,
        "verification_status": "pending",
    }


@pytest.mark.parametrize("reason", ["dependency", "collision", "publication", "resumption"])
def test_real_edge_or_resumption_selects_existing_coordination(context, reason):
    result = decide_execution(ROOT, {**context, "coordination": [reason]})
    catalog = yaml.safe_load((ROOT / "agents/task_catalog.yaml").read_text())
    assert result["execution_route"] == "coordination"
    assert result["commands"] == ["python3 tools/runtime/lifecycle/task_close.py --run-id <run-id>"]
    assert result["execution_time_policy"] == catalog["execution_time_policy"]
    assert len(result["execution_time_policy"]["executable_fields"]) == 13


@pytest.mark.parametrize("count", ["roots", "owners", "writers"])
def test_multiple_roots_owners_or_writers_require_coordination(context, count):
    assert decide_execution(ROOT, {**context, count: 2})["execution_route"] == "coordination"


@pytest.mark.parametrize("value, expected", [("unavailable", "need verification"), ("failed", "failed"), ("pass", "pass")])
def test_validation_outcome_is_preserved_without_fallback(context, value, expected):
    result = decide_execution(ROOT, {**context, "validation_status": value})
    assert result["verification_status"] == expected
    assert result["selected_validation"] == context["validation"]
    assert result["commands"] == []
    assert "execution_time_policy" not in result
    assert "completion" not in result


@pytest.mark.parametrize("key,value", [
    ("roots", True), ("roots", 0), ("writers", -1), ("owners", "1"),
    ("scope_resolved", False), ("contract_resolved", None),
    ("validation", " "), ("coordination", ["large_diff"]),
    ("coordination", "dependency"), ("validation_status", "skipped"),
    ("global_gate_not_applicable", True),
])
def test_unknown_or_invalid_facts_do_not_admit_execution(context, key, value):
    with pytest.raises(ValueError):
        decide_execution(ROOT, {**context, key: value})


def test_missing_owner_fact_is_not_an_implicit_single_owner(context):
    del context["owners"]
    with pytest.raises(ValueError):
        decide_execution(ROOT, context)


@pytest.mark.parametrize("risk", RISK_VALUES)
def test_cli_is_artifact_free_and_does_not_route_by_risk(context, tmp_path, risk):
    # Commands in the oracle are data, not executable authority for this router.
    context["validation"] = "touch must-not-exist"
    result = subprocess.run(
        [sys.executable, str(ROUTER), "--root", str(ROOT), "--area", "closeout",
         "--execution-context", "-", "--risk", risk, "--format", "json"],
        input=json.dumps(context), text=True, capture_output=True, cwd=tmp_path,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["execution_route"] == "bounded_fast_path"
    assert list(tmp_path.iterdir()) == []


def test_closeout_without_context_does_not_advertise_a_run_bundle(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROUTER), "--root", str(ROOT), "--area", "closeout", "--format", "json"],
        capture_output=True, text=True, cwd=tmp_path, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["commands"] == []
    assert "task_close.py" not in result.stdout


def test_non_closeout_selector_rejects_execution_context(context, tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROUTER), "--root", str(ROOT), "--area", "checks",
         "--execution-context", json.dumps(context)],
        capture_output=True, text=True, cwd=tmp_path, check=False,
    )
    assert result.returncode == 2
    assert "requires --area closeout" in result.stderr


def test_unselected_gate_count_does_not_expand_bounded_output(context, tmp_path):
    expected = decide_execution(ROOT, context)
    catalog = yaml.safe_load((ROOT / "agents/task_catalog.yaml").read_text())
    catalog["execution_time_policy"]["unselected_gates"] = [f"gate-{index}" for index in range(1000)]
    catalog["execution_route_policy"]["routes"]["bounded_fast_path"]["inactive_not_applicable"] = True
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents/task_catalog.yaml").write_text(yaml.safe_dump(catalog))
    assert decide_execution(tmp_path, context) == expected
