# @dependency-start
# contract test
# responsibility Verifies standalone static-gate unit ownership, canonical selection, workflow activation, and full-confidence parity.
# upstream implementation ../../tools/agent_tools/classify_path_risk.py canonical selector and unit mapping
# upstream implementation ../../tools/ci/run_standalone_static_gate_unit.sh unit executor
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh manual full-confidence aggregate
# upstream implementation ../../.github/workflows/agent-canon-static-gates.yml remote selected-unit jobs
# @dependency-end

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SELECTOR = ROOT / "tools" / "agent_tools" / "classify_path_risk.py"
RUNNER = ROOT / "tools" / "ci" / "run_standalone_static_gate_unit.sh"
FULL_WRAPPER = ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "agent-canon-static-gates.yml"
UNITS = ("rust", "contracts", "eval", "workflow-container")


def selected_units(*paths: str) -> tuple[str, ...]:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as handle:
        handle.write("\n".join(paths) + "\n")
        handle.flush()
        result = subprocess.run(
            [
                "python3",
                str(SELECTOR),
                "--paths-file",
                handle.name,
                "--format",
                "json",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stderr
    return tuple(json.loads(result.stdout)["units"])


def test_static_unit_runner_has_four_explicit_units() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    for unit in UNITS:
        assert f"{unit})" in text
    assert "unknown standalone static-gate unit" in text


def test_static_unit_runner_and_full_wrapper_are_shell_syntax_valid() -> None:
    for path in (RUNNER, FULL_WRAPPER):
        result = subprocess.run(
            ["bash", "-n", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_canonical_selector_maps_representative_surfaces_to_units() -> None:
    assert selected_units("documents/design/example.md") == ("contracts",)
    assert selected_units("tools/agent_tools/example.py") == ("contracts",)
    assert selected_units("rust/agent-canon/src/main.rs") == ("rust",)
    assert selected_units("agents/evals/skill-workflow-prompt.yaml") == ("eval",)
    assert selected_units("agents/skills/catalog.yaml") == ("contracts",)
    assert selected_units(".github/PULL_REQUEST_TEMPLATE.md") == ("workflow-container",)
    assert selected_units("docker/Dockerfile") == ("workflow-container",)
    assert selected_units("memory/example.yaml") == ("contracts",)


def test_selector_boundary_change_uses_full_confidence_unit_set() -> None:
    assert selected_units("tools/agent_tools/classify_path_risk.py") == UNITS
    assert selected_units(".github/workflows/agent-canon-static-gates.yml") == UNITS


def test_mixed_surfaces_select_union_without_unrelated_units() -> None:
    assert selected_units(
        "documents/design/example.md", "rust/agent-canon/src/main.rs"
    ) == ("rust", "contracts")


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
    for command in (
        "cargo build --manifest-path",
        "tool_catalog.py",
        "run_accumulated_agent_evals.py",
        "check_github_workflows.py",
    ):
        assert command not in body


def test_workflow_uses_one_selector_and_native_selected_jobs() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert set(jobs) == {
        "select-static-units",
        "rust-static",
        "contracts-static",
        "eval-static",
        "workflow-container-static",
        "static-gates",
    }
    selector_text = str(jobs["select-static-units"])
    assert "classify_path_risk.py" in selector_text
    assert "git diff --name-only" in selector_text
    for job_name, output in (
        ("rust-static", "rust"),
        ("contracts-static", "contracts"),
        ("eval-static", "eval"),
        ("workflow-container-static", "workflow_container"),
    ):
        job = jobs[job_name]
        assert job["needs"] == "select-static-units"
        assert output in str(job["if"])


def test_toolchain_setup_is_bounded_to_selected_owning_jobs() -> None:
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


def test_aggregate_required_check_accepts_only_selected_success_or_unselected_skip() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    aggregate = workflow["jobs"]["static-gates"]
    assert aggregate["needs"] == [
        "select-static-units",
        "rust-static",
        "contracts-static",
        "eval-static",
        "workflow-container-static",
    ]
    text = str(aggregate)
    assert 'test "${result}" = success' in text
    assert 'test "${result}" = skipped' in text


def test_workflow_full_wrapper_is_manual_only_and_no_retry_ledger_exists() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    text = WORKFLOW.read_text(encoding="utf-8")
    steps = workflow["jobs"]["static-gates"]["steps"]
    wrapper = next(
        step for step in steps if "check_agent_canon_pr.sh" in str(step.get("run", ""))
    )
    assert wrapper["if"] == "github.event_name == 'workflow_dispatch'"
    assert wrapper["env"]["AGENT_CANON_PR_READ_TOKEN"] == "${{ github.token }}"
    for forbidden in ("retry-ledger", "validation-ledger", "cache-manifest", "receipt-schema"):
        assert forbidden not in text
