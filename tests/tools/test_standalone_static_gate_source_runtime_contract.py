"""Static ownership checks for source/runtime validation routing."""

# @dependency-start
# contract test
# responsibility Verifies standalone static unit source/runtime routing and eval failure evidence retention.
# upstream implementation ../../tools/validation/ci/runners/run_standalone_static_gate_unit.sh owns contract and eval unit commands
# upstream implementation ../../eval/producers/run_accumulated_agent_evals.py runs the selected eval producer collection
# upstream design ../../documents/design/source-owned-dependency-validation.md source and persisted graph authority split
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml runs selected unit owners
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    ROOT
    / "tools"
    / "validation"
    / "ci"
    / "runners"
    / "run_standalone_static_gate_unit.sh"
)

SOURCE_REGRESSION_MODULES = (
    "tests.agent_tools.test_graph_client_source_projection",
    "tests.tools.test_agent_canon_pr_dependency_source_gate",
    "tests.tools.test_agent_canon_pr_graph_gate_integration",
    "tests.agent_tools.test_check_dependency_headers",
    "tests.agent_tools.test_check_design_doc_claims",
    "tests.agent_tools.test_tool_drift",
    "tests.agent_tools.test_vector_search",
    "tests/agent_tools/test_dependency_*.py",
)


def function_body(text: str, name: str, next_name: str) -> str:
    """Return one shell function body using adjacent owner declarations."""
    return text.split(f"{name}() {{", 1)[1].split(f"\n}}\n\n{next_name}", 1)[0]


def test_contract_unit_runs_all_source_runtime_regressions() -> None:
    """Every affected source consumer is validated by the contract unit."""
    text = RUNNER.read_text(encoding="utf-8")
    body = function_body(text, "run_contracts", "run_eval() (")
    remainder = text.replace(body, "", 1)

    for module in SOURCE_REGRESSION_MODULES:
        assert module in body
        assert module not in remainder


def test_all_source_gate_entrypoints_require_distinct_control_and_runtime_roots() -> (
    None
):
    """A source checkout cannot become either the control or runtime owner."""
    source = (
        ROOT
        / "tools"
        / "validation"
        / "ci"
        / "runners"
        / "run_standalone_static_gate_unit.sh"
    ).read_text(encoding="utf-8")
    run_all = (
        ROOT / "tools" / "validation" / "ci" / "runners" / "run_all_checks.sh"
    ).read_text(encoding="utf-8")
    pr = (
        ROOT / "tools" / "validation" / "ci" / "checks" / "check_agent_canon_pr.sh"
    ).read_text(encoding="utf-8")
    for text in (run_all, pr):
        assert "control_parent_root_required" in text
        assert "runtime_root_required" in text
        assert "control_parent_root_is_source" in text
        assert 'AGENT_CANON_PARENT_ROOT="${AGENT_CANON_CONTROL_PARENT_ROOT}"' in text
        assert "${RUNNER_TEMP:-${TMPDIR:-/tmp}}" not in text
    assert "AGENT_CANON_TARGET_ROOT:?AGENT_CANON_TARGET_ROOT is required" in source
    assert 'AGENT_CANON_STATIC_RUNTIME_ROOT="${AGENT_CANON_RUNTIME_ROOT}"' in source
    assert "control_parent_root_required" not in source


@pytest.mark.parametrize(
    ("producer_status", "checker_status", "smoke_status", "expected_names"),
    [
        (0, 0, 0, ["producer", "checker", "smoke"]),
        (7, 0, 0, ["producer"]),
        (0, 9, 0, ["producer", "checker"]),
        (0, 0, 11, ["producer", "checker", "smoke"]),
    ],
)
def test_eval_preserves_failed_producer_logs_until_ci_capture(
    tmp_path: Path,
    producer_status: int,
    checker_status: int,
    smoke_status: int,
    expected_names: list[str],
) -> None:
    """Failed producer logs survive; successful temporary output is still cleaned."""
    source = tmp_path / "source"
    runtime = tmp_path / "runtime with spaces"
    runtime.mkdir()
    calls = tmp_path / "calls.jsonl"
    paths = (
        ("eval/producers/run_accumulated_agent_evals.py", "producer", producer_status),
        ("eval/checkers/eval_accumulation_check.py", "checker", checker_status),
        (
            "eval/checkers/smoke_test_research_perspective_pack.py",
            "smoke",
            smoke_status,
        ),
    )
    for relative, name, status in paths:
        script = source / relative
        script.parent.mkdir(parents=True, exist_ok=True)
        producer_logs = (
            "log_dir = Path(sys.argv[sys.argv.index('--log-dir') + 1])\n"
            "log_dir.mkdir(parents=True, exist_ok=True)\n"
            "stdout = ''.join(f'producer stdout line {index + 1}\\n' for index in range(161))\n"
            "stderr = ''.join(f'producer stderr line {index + 1}\\n' for index in range(161))\n"
            "(log_dir / '02-workflow-selection.stdout.txt').write_text(stdout, encoding='utf-8')\n"
            "(log_dir / '02-workflow-selection.stderr.txt').write_text(stderr, encoding='utf-8')\n"
            "report_dir = Path(os.environ['AGENT_CANON_HOOK_ARCHIVE_DIR']) / 'eval-results' / 'workflow-selection'\n"
            "report_dir.mkdir(parents=True, exist_ok=True)\n"
            "(report_dir / 'agent-canon-pr-gate-pass.md').write_text('synthetic report\\n', encoding='utf-8')\n"
            if name == "producer"
            else (
                "report = Path(os.environ['AGENT_CANON_HOOK_ARCHIVE_DIR']) / "
                "'eval-results/workflow-selection/agent-canon-pr-gate-pass.md'\n"
                "if not report.is_file():\n"
                "    raise SystemExit(87)\n"
                if name == "checker"
                else ""
            )
        )
        script.write_text(
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "with Path(os.environ['CALLS']).open('a') as stream:\n"
            f"    stream.write(json.dumps([{name!r}, "
            "os.environ.get('AGENT_CANON_HOOK_ARCHIVE_DIR'), "
            "os.environ.get('AGENT_CANON_LOG_ROOT')]) + '\\n')\n"
            + producer_logs
            + f"raise SystemExit({status})\n",
            encoding="utf-8",
        )
    text = RUNNER.read_text(encoding="utf-8")
    body = (
        "run_eval() ("
        + text.split("run_eval() (", 1)[1].split("\n)\n\nrun_workflow_container()", 1)[
            0
        ]
        + "\n)\n"
    )
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", body + "run_eval"],
        cwd=source,
        env={
            **os.environ,
            "ROOT": str(source),
            "RUNTIME_ROOT": str(source),
            "AGENT_CANON_STATIC_RUNTIME_ROOT": str(runtime),
            "AGENT_CANON_HOOK_ARCHIVE_DIR": "/var/lib/agent-canon/private-log",
            "AGENT_CANON_LOG_ROOT": "/var/lib/agent-canon/private-log",
            "CALLS": str(calls),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (producer_status or checker_status or smoke_status), (
        result.stdout + result.stderr
    )
    records = [json.loads(line) for line in calls.read_text().splitlines()]
    assert [record[0] for record in records] == expected_names
    archive = str(runtime)
    assert all(
        record[1:] == [archive, archive] for record in records if record[0] != "smoke"
    )
    report_path = (
        runtime / "eval-results" / "workflow-selection" / "agent-canon-pr-gate-pass.md"
    )
    assert report_path.is_file()
    temporary_logs = (
        runtime / "eval/agent-canon-pr-gate/agent-eval-runs/agent-canon-pr-gate"
    )
    if producer_status or checker_status or smoke_status:
        assert temporary_logs.is_dir()
        assert "producer stdout line 161" in (
            temporary_logs / "02-workflow-selection.stdout.txt"
        ).read_text(encoding="utf-8")
        assert "producer stderr line 161" in (
            temporary_logs / "02-workflow-selection.stderr.txt"
        ).read_text(encoding="utf-8")
    else:
        assert not temporary_logs.exists()
