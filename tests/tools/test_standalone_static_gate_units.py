# @dependency-start
# contract test
# responsibility Verifies standalone static-gate unit ownership, canonical selection, workflow activation, and full-confidence parity.
# upstream implementation ../../tools/validation/semantic/path/classify_path_risk.py canonical selector and unit mapping
# upstream implementation ../../tools/validation/ci/runners/run_standalone_static_gate_unit.sh unit executor
# upstream implementation ../../tools/validation/ci/checks/check_agent_canon_pr.sh manual full-confidence aggregate
# upstream implementation ../../.github/workflows/agent-canon-static-gates.yml remote selected-unit shared runtime
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SELECTOR = ROOT / "tools" / "validation" / "semantic" / "path" / "classify_path_risk.py"
RUNNER = ROOT / "tools" / "validation" / "ci" / "runners" / "run_standalone_static_gate_unit.sh"
FULL_WRAPPER = ROOT / "tools" / "validation" / "ci" / "checks" / "check_agent_canon_pr.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "agent-canon-static-gates.yml"
UNITS = ("rust", "contracts", "eval", "workflow-container")


def selected_units(*paths: str) -> tuple[str, ...]:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as handle:
        handle.write("\n".join(paths) + "\n")
        handle.flush()
        result = subprocess.run(
            ["python3", str(SELECTOR), "--paths-file", handle.name, "--format", "json"],
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


def test_static_unit_runner_requires_shared_tool_container() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert "/usr/local/share/agent-canon/.agent-canon-tool-container" in text
    assert "shared_tool_runtime_required" in text
    assert "AGENT_CANON_TARGET_ROOT" in text
    assert "exec-parent-bound" not in text
    assert '"${CARGO_TARGET_DIR:?}/debug/agent-canon"' in text
    assert "trap cleanup_eval EXIT" in text
    assert "trap cleanup_eval RETURN" not in text
    assert "mktemp" not in text
    assert 'rm -rf -- "${temp_root}"' in text
    assert 'rm -rf -- "${ROOT}"' not in text


def test_eval_unit_surfaces_cleanup_failure_without_masking_primary_status(
    tmp_path: Path,
) -> None:
    """The Host-facing runner rejects execution outside the shared tool image."""
    if Path("/usr/local/share/agent-canon/.agent-canon-tool-container").is_file():
        pytest.skip("Host rejection route is not applicable inside the tool image")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "case \"$*\" in\n"
        "  *' verify-child '*) exit 0 ;;\n"
        "  *' temp-dir '*) mkdir -p \"$FAKE_TEMP_ROOT\"; printf '%s\\n' \"$FAKE_TEMP_ROOT\"; exit 0 ;;\n"
        "  *' ensure-dir '*)\n"
        "    candidate=''\n"
        "    while [ \"$#\" -gt 0 ]; do\n"
        "      if [ \"$1\" = '--candidate' ]; then candidate=\"$2\"; break; fi\n"
        "      shift\n"
        "    done\n"
        "    mkdir -p \"$candidate\"; printf '%s\\n' \"$candidate\"; exit 0 ;;\n"
        "  *' remove-tree '*) exit \"${FAKE_REMOVE_STATUS:?}\" ;;\n"
            "  *'run_accumulated_agent_evals.py'*) exit \"${FAKE_EVAL_STATUS:?}\" ;;\n"
            "  -*) candidate=\"${@: -1}\"; mkdir -p \"$candidate\"; printf '%s\\n' \"$candidate\"; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    def run(eval_status: int) -> subprocess.CompletedProcess[str]:
            case_root = tmp_path / f"case-{eval_status}"
            runtime_root = case_root / "runtime"
            return subprocess.run(
            ["bash", str(RUNNER), "eval"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "AGENT_CANON_CHILD_HANDOFF": "fixture-single-use-token",
                "AGENT_CANON_HANDOFF_AUDIENCE": "standalone-static-gate-unit",
                    "AGENT_CANON_CHILD_PURPOSE": "standalone-static-gate-unit",
                    "AGENT_CANON_CONTROL_PARENT_ROOT": str(ROOT.parents[3]),
                    "AGENT_CANON_RUNTIME_ROOT": str(runtime_root),
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": str(runtime_root / "hook-archive"),
                    "FAKE_TEMP_ROOT": str(case_root / "temp-root"),
                    "FAKE_EVAL_STATUS": str(eval_status),
                },
            )

    for status in (0, 23):
        result = run(status)
        assert result.returncode == 2
        assert "shared_tool_runtime_required" in result.stderr


def test_static_unit_runner_and_full_wrapper_are_shell_syntax_valid() -> None:
    for path in (RUNNER, FULL_WRAPPER):
        result = subprocess.run(
            ["bash", "-n", str(path)], check=False, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr


def test_canonical_selector_maps_representative_surfaces_to_units() -> None:
    assert selected_units("documents/design/example.md") == ("contracts",)
    assert selected_units("tools/agent_tools/example.py") == ("contracts",)
    assert selected_units("tools/runtime/dispatch/agent-canon/src/main.rs") == ("rust",)
    assert selected_units("eval/definitions/skill-workflow-prompt.toml") == ("eval",)
    assert selected_units("agents/skills/catalog.yaml") == ("contracts",)
    assert selected_units(".github/PULL_REQUEST_TEMPLATE.md") == (
        "contracts",
        "workflow-container",
    )
    assert selected_units("docker/Dockerfile") == ("workflow-container",)
    assert selected_units("documents/notes/knowledge/example.yaml") == ("contracts",)


def test_selector_boundary_change_uses_full_confidence_unit_set() -> None:
    assert selected_units("tools/validation/semantic/path/classify_path_risk.py") == UNITS
    assert selected_units(".github/workflows/agent-canon-static-gates.yml") == UNITS


def test_mixed_surfaces_select_union_without_unrelated_units() -> None:
    assert selected_units(
        "documents/design/example.md", "tools/runtime/dispatch/agent-canon/src/main.rs"
    ) == ("rust", "contracts")


def test_rust_commands_are_confined_to_rust_unit() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    rust_body = text.split("run_rust() {", 1)[1].split("\n}\n\nrun_contracts()", 1)[0]
    remainder = text.replace(rust_body, "", 1)
    for command in (
        "cargo build --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml",
        "cargo fmt --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml -- --check",
        "cargo clippy --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml --all-targets -- -D warnings",
    ):
        assert command in rust_body
        assert command not in remainder
    assert "env -u AGENT_CANON_RUNTIME_ROOT" in rust_body
    assert "cargo test --manifest-path tools/runtime/dispatch/agent-canon/Cargo.toml" in rust_body


def test_focused_regression_is_owned_by_workflow_container_unit() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    workflow_body = text.split("run_workflow_container() {", 1)[1].split(
        "\n}\n\ncase ", 1
    )[0]
    remainder = text.replace(workflow_body, "", 1)
    test_path = "tests/tools/test_standalone_static_gate_units.py"
    assert test_path in workflow_body
    assert "-p no:cacheprovider" in workflow_body
    executable_remainder = "\n".join(
        line for line in remainder.splitlines() if not line.lstrip().startswith("#")
    )
    assert test_path not in executable_remainder


def test_full_wrapper_aggregates_each_unit_once_without_reowning_commands() -> None:
    text = FULL_WRAPPER.read_text(encoding="utf-8")
    body = text.split("run_standalone_static_gate_ci() {", 1)[1].split(
        "\n}\n\ngithub_repo_security_status()", 1
    )[0]
    assert "owned_by_bootstrap_container_workflow" in body
    for command in (
        "cargo build --manifest-path",
        "tool_catalog.py",
        "run_accumulated_agent_evals.py",
        "check_github_workflows.py",
    ):
        assert command not in body


def test_workflow_uses_one_selector_and_one_shared_runtime_job() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    assert set(jobs) == {"select-static-units", "static-gates"}
    selector_text = str(jobs["select-static-units"])
    assert "classify_path_risk.py" in selector_text
    assert "git diff --name-only" in selector_text
    assert jobs["static-gates"]["needs"] == "select-static-units"


def test_toolchain_setup_occurs_once_in_required_shared_job() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    text = str(workflow["jobs"]["static-gates"])
    assert "bootstrap.sh" in text
    assert "run_standalone_static_gate_unit.sh" in text
    assert "actions/setup-python" not in text
    assert "pip install" not in text
    assert "rustup component add" not in text
    assert WORKFLOW.read_text(encoding="utf-8").count(" install\n") == 1


def test_required_check_runs_selected_units_sequentially() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    required = workflow["jobs"]["static-gates"]
    run = "\n".join(str(step.get("run", "")) for step in required["steps"])
    assert 'for unit in "${units[@]}"' in run
    assert '"${unit}"' in run
    assert "selected_units=none" in run


def test_workflow_manual_full_gate_uses_bootstrap_units_without_retry_ledger() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    text = WORKFLOW.read_text(encoding="utf-8")
    steps = workflow["jobs"]["static-gates"]["steps"]
    wrapper = next(
        step for step in steps if "for unit in" in str(step.get("run", ""))
    )
    assert "bootstrap.sh" in wrapper["run"]
    assert "rust,contracts,eval,workflow-container" in text
    for forbidden in ("retry-ledger", "validation-ledger", "cache-manifest", "receipt-schema"):
        assert forbidden not in text
