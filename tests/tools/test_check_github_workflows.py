# @dependency-start
# contract test
# responsibility Tests the standalone AgentCanon GitHub workflow convention checker.
# upstream implementation ../../tools/ci/check_github_workflows.py convention checker
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml standalone gate workflow
# @dependency-end

"""Tests for standalone AgentCanon GitHub workflow conventions."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "tools" / "ci" / "check_github_workflows.py"


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def copy_required_surfaces(root: Path) -> None:
    """Copy only standalone surfaces consumed by the checker."""
    for relative in (
        ".github/AGENTS.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/PULL_REQUEST_TEMPLATE/agent_canon.md",
        "templates/documents/github/pull-request/agent_canon.md",
        "agents/workflows/agent-canon-pr-workflow.md",
        "issues/README.md",
        "issues/closed/AC-20260517-eval-accumulation-gaps.md",
        "issues/closed/AC-20260513-durable-finding-auto-promotion.md",
        "README.md",
    ):
        source = ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def write_workflow(root: Path, text: str) -> None:
    path = root / ".github" / "workflows" / "ci.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


VALID_WORKFLOW = """\
name: CI
on: [push]
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - run: echo standalone
"""


def test_standalone_repository_passes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copy_required_surfaces(root)
        write_workflow(root, VALID_WORKFLOW)
        result = run_checker(root)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "GITHUB_WORKFLOWS=pass" in result.stdout


def test_checker_only_scans_standalone_workflows() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copy_required_surfaces(root)
        write_workflow(root, VALID_WORKFLOW)
        vendor = root / "vendor" / "agent-canon" / ".github" / "workflows"
        vendor.mkdir(parents=True)
        (vendor / "obsolete.yml").write_text("not: yaml\n", encoding="utf-8")
        result = run_checker(root)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "GITHUB_WORKFLOWS_CHECKED=1" in result.stdout


def test_invalid_checkout_settings_fail() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        copy_required_surfaces(root)
        write_workflow(
            root,
            VALID_WORKFLOW.replace("persist-credentials: false", "persist-credentials: true"),
        )
        result = run_checker(root)
        assert result.returncode != 0
        assert "checkout_1_missing_persist_credentials_false" in result.stdout


def test_static_gate_uses_bootstrap_container_units() -> None:
    path = ROOT / ".github" / "workflows" / "agent-canon-static-gates.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    runs = [
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]
    assert not any("check_agent_canon_pr.sh" in run for run in runs)
    assert sum("run_standalone_static_gate_unit.sh" in run for run in runs) == 5


def test_no_submodule_checkout_helper_remains() -> None:
    forbidden = (
        ROOT / ".github" / "scripts" / "checkout_agent_canon_submodule.sh",
        ROOT / "tools" / "ci" / "checkout_agent_canon_submodule.sh",
    )
    assert all(not path.exists() for path in forbidden)
    assert "checkout_agent_canon_submodule" not in CHECKER.read_text(encoding="utf-8")


def test_issue_mirror_resolves_runner_temp_after_job_admission() -> None:
    """The runner context is not valid while GitHub evaluates job-level env."""
    path = ROOT / ".github" / "workflows" / "issue-mirror.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    for job in workflow["jobs"].values():
        assert "runner.temp" not in str(job.get("env", {}))
    sync_steps = workflow["jobs"]["issue-mirror-sync"]["steps"]
    configure = next(
        step for step in sync_steps if step.get("name") == "Configure external runtime root"
    )
    assert "RUNNER_TEMP" in configure["run"]
    assert "GITHUB_ENV" in configure["run"]
