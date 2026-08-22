"""Regression tests for tools that publish only to the explicit runtime root."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
REVIEW_SCAN = PROJECT_ROOT / "tools" / "agent_tools" / "review_backlog_scan.sh"
DEPENDENCY_REVIEW = PROJECT_ROOT / "tools" / "agent_tools" / "run_repo_dependency_review.sh"

from tools.ci import container_runtime


def clean_runtime_environment() -> dict[str, str]:
    """Return an environment without legacy source-output selectors."""
    environment = os.environ.copy()
    for key in (
        "AGENT_CANON_RUNTIME_ROOT",
        "AGENT_CANON_CONTROL_PARENT_ROOT",
        "AGENT_CANON_PARENT_ROOT",
        "AGENT_CANON_CONTAINER_LIFECYCLE_RECEIPT",
    ):
        environment.pop(key, None)
    return environment


@pytest.mark.parametrize(
    ("script", "arguments", "marker"),
    (
        (
            REVIEW_SCAN,
            ("--root", str(PROJECT_ROOT), "--check", "stale"),
            "control_root_missing",
        ),
        (
            DEPENDENCY_REVIEW,
            ("--root", str(PROJECT_ROOT), "--header-scan-only"),
            "runtime_root_required",
        ),
    ),
)
def test_shell_tools_fail_without_explicit_runtime_root(
    script: Path, arguments: tuple[str, ...], marker: str
) -> None:
    """Legacy source-local execution is rejected before any write."""
    result = subprocess.run(
        ["bash", str(script), *arguments],
        cwd=PROJECT_ROOT,
        env=clean_runtime_environment(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert marker in result.stderr


def test_review_scan_publishes_external_report(tmp_path: Path) -> None:
    """The scan report and status are outside the source checkout."""
    control = tmp_path / "control"
    repo = control / "repo"
    runtime = tmp_path / "runtime"
    repo.mkdir(parents=True)
    environment = clean_runtime_environment()
    environment.update(
        AGENT_CANON_RUNTIME_ROOT=str(runtime),
        AGENT_CANON_CONTROL_PARENT_ROOT=str(control),
    )
    result = subprocess.run(
        ["bash", str(REVIEW_SCAN), "--root", str(repo), "--check", "stale"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not list(repo.rglob("*"))
    assert list(runtime.rglob("review_backlog_scan.md"))


def test_search_index_requires_and_uses_external_runtime(tmp_path: Path) -> None:
    """Search cards never fall back to a source-local directory."""
    source = tmp_path / "source"
    runtime = tmp_path / "runtime"
    source.mkdir()
    (source / "README.md").write_text("# fixture\n", encoding="utf-8")
    environment = clean_runtime_environment()
    environment["AGENT_CANON_RUNTIME_ROOT"] = str(runtime)
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "tools" / "agent_tools" / "search_index.py"),
            "build",
            "--root",
            str(source),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not (source / ".agent-canon").exists()
    assert list(runtime.rglob("semantic-cards.jsonl"))


def test_container_lifecycle_receipt_is_external(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Container receipts do not use a source checkout fallback."""
    control = tmp_path / "control"
    source = control / "repo"
    runtime = tmp_path / "runtime"
    source.mkdir(parents=True)
    monkeypatch.setenv("AGENT_CANON_CONTROL_PARENT_ROOT", str(control))
    monkeypatch.setenv("AGENT_CANON_RUNTIME_ROOT", str(runtime))
    receipt = container_runtime.ContainerLifecycleReceipt(
        container_runtime.LifecycleContext("task", "repo"),
        container_runtime.DaemonSnapshot("docker", {}, "not-created"),
    )
    target = container_runtime.write_lifecycle_receipt(source, receipt)
    assert target.is_file()
    assert target.is_relative_to(runtime)
    assert not list(source.rglob("*"))
