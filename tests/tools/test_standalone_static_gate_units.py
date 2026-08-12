# @dependency-start
# contract test
# responsibility Verifies standalone static-gate execution-unit ownership and workflow toolchain boundaries.
# upstream implementation ../../tools/ci/run_standalone_static_gate_unit.sh unit executor
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh manual full-confidence aggregate
# upstream implementation ../../.github/workflows/agent-canon-static-gates.yml remote unit jobs
# @dependency-end

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "ci" / "run_standalone_static_gate_unit.sh"
FULL_WRAPPER = ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "agent-canon-static-gates.yml"
UNITS = ("rust", "contracts", "eval", "workflow-container")


def test_static_unit_runner_has_four_explicit_units() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    for unit in UNITS:
        assert f"{unit})" in text
    assert "unknown standalone static-gate unit" in text


def test_static_unit_runner_is_shell_syntax_valid() -> None:
    result = subprocess.run(
        ["bash", "-n", str(RUNNER)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_full_wrapper_is_shell_syntax_valid() -> None:
    result = subprocess.run(
        ["bash", "-n", str(FULL_WRAPPER)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_rust_commands_are_confined_to_rust_unit() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    rust_body = text.split("run_rust() {", 1)[1].split("\n}\n\nrun_contracts()", 1)[0]
    remainder = text.replace(rust_body, "")
    for command in (
        "cargo build --manifest-path rust/agent-canon/Cargo.toml",
        "cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check",
        "cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings",
        "cargo test --manifest-path rust/agent-canon/Cargo.toml",
    ):
        assert command in rust_body
        assert command not in remainder


def test_full_wrapper_aggregates_each_unit_once_without_reowning_commands() -> None:
    text = FULL_WRAPPER.read_text(encoding="utf-8")
    body = text.split("run_standalone_static_gate_ci() {", 1)[1].split(
        "\n}\n\ngithub_repo_security_status()", 1
    )[0]

    assert "local units=(rust contracts eval workflow-container)" in body
    assert 'for unit in "${units[@]}"; do' in body
    assert (
        body.count(
            'bash "${SCRIPT_DIR}/run_standalone_static_gate_unit.sh" "${unit}"'
        )
        == 1
    )
    assert 'AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}"' in body
    for command in (
        "cargo build --manifest-path",
        "tool_catalog.py",
        "run_accumulated_agent_evals.py",
        "check_github_workflows.py",
    ):
        assert command not in body


def test_workflow_uses_native_jobs_and_preserves_aggregate_check() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert set(jobs) == {
        "rust-static",
        "contracts-static",
        "eval-static",
        "workflow-container-static",
        "static-gates",
    }
    assert jobs["static-gates"]["needs"] == [
        "rust-static",
        "contracts-static",
        "eval-static",
        "workflow-container-static",
    ]


def test_toolchain_setup_is_bounded_to_owning_jobs() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    rust_text = str(jobs["rust-static"])
    assert "rustup component add rustfmt clippy" in rust_text
    assert "actions/setup-python" not in rust_text
    assert "pip install" not in rust_text

    for job_name in ("contracts-static", "eval-static", "workflow-container-static"):
        text = str(jobs[job_name])
        assert "actions/setup-python@v5" in text
        assert "pip install" in text
        assert "rustup component add" not in text


def test_workflow_full_wrapper_is_manual_only() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["static-gates"]["steps"]
    wrapper = next(
        step for step in steps if "check_agent_canon_pr.sh" in str(step.get("run", ""))
    )
    assert wrapper["if"] == "github.event_name == 'workflow_dispatch'"
    assert wrapper["env"]["AGENT_CANON_PR_READ_TOKEN"] == "${{ github.token }}"
