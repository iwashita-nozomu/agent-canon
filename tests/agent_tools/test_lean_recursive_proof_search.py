# @dependency-start
# contract test
# responsibility Tests recursive Lean proof-search CLI output and process behavior.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/lean_recursive_proof_search.rs owns the native CLI
# @dependency-end
"""Black-box regressions for configured Lean proof search."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


def make_config(tmp_path: Path) -> Path:
    fake_lean = tmp_path / "fake-lean"
    fake_lean.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "import time\n"
        "source = sys.stdin.read()\n"
        "if 'by\\n  sorry' in source:\n"
        " print('warning: declaration uses `sorry`')\n"
        "elif 'by\\n  slow' in source:\n"
        " time.sleep(2)\n"
        "elif 'by\\n  fail' in source:\n"
        " print('error: tactic failed\\n⊢ False', file=sys.stderr)\n"
        " sys.exit(1)\n",
        encoding="utf-8",
    )
    fake_lean.chmod(0o755)
    config = tmp_path / "targets.json"
    config.write_text(
        json.dumps(
            {
                "target_theorem": "sample theorem",
                "command": [sys.executable, str(fake_lean)],
                "targets": [
                    {"name": "first", "statement": "True", "tactic": "trivial", "next_targets": ["second"]},
                    {"name": "second", "statement": "False", "tactic": "fail"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return config


def run_tool(config: Path, *args: str) -> subprocess.CompletedProcess[str]:
    if not AGENT_CANON_CLI:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return subprocess.run(
        [AGENT_CANON_CLI, "lean-recursive-proof-search", "--config", str(config), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_records_verified_and_failed_targets_as_json(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    result = run_tool(config, "--format", "json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "lean_recursive_proof_search_complete"
    assert [row["status"] for row in payload["results"]] == [
        "verified",
        "unverified_with_next_goals",
    ]
    assert payload["results"][0]["next_targets"] == ["second"]
    assert payload["results"][1]["unresolved_goals"] == [
        "error: tactic failed\n⊢ False"
    ]


def test_filters_targets_and_writes_markdown(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    report = tmp_path / "result.md"
    result = run_tool(
        config,
        "--target-name-regex",
        "second$",
        "--format",
        "markdown",
        "--out",
        str(report),
    )
    assert result.returncode == 1
    assert result.stdout == ""
    text = report.read_text(encoding="utf-8")
    assert "`second`" in text
    assert "Recursive Lean Proof Search" in text


def test_tactic_matrix_reports_per_target_coverage(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    result = run_tool(config, "--format", "json", "--tactic-matrix", "fail,trivial")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["matrix_target_statuses"] == {
        "first": "verified_by_some_tactic",
        "second": "verified_by_some_tactic",
    }


def test_config_shape_errors_fail_before_attempts(tmp_path: Path) -> None:
    config = tmp_path / "invalid.json"
    config.write_text("[]", encoding="utf-8")
    result = run_tool(config)
    assert result.returncode == 2
    assert "config must be a JSON object" in result.stderr


def test_batch_mode_preserves_single_process_failure_shape(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    result = run_tool(config, "--batch", "--format", "json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert len(payload["results"]) == 1
    assert payload["results"][0]["name"] == "_batch"
    assert payload["results"][0]["tactic"] == "batch"


def test_attempt_timeout_uses_timeout_status_and_return_code(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["targets"] = [
        {"name": "slow", "statement": "True", "tactic": "slow"}
    ]
    config.write_text(json.dumps(payload), encoding="utf-8")
    result = run_tool(config, "--format", "json", "--attempt-timeout-sec", "0.02")
    assert result.returncode == 1
    attempt = json.loads(result.stdout)["results"][0]
    assert attempt["status"] == "timeout"
    assert attempt["returncode"] == 124
