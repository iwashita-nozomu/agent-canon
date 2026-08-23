# @dependency-start
# contract test
# responsibility Tests test python env policy behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Tests for the repo-local Python environment policy helper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "ci" / "python_env_policy.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the helper CLI and capture the output."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def parse_output(stdout: str) -> dict[str, str]:
    """Parse KEY=value output."""
    return dict(
        line.split("=", 1)
        for line in stdout.splitlines()
        if "=" in line
    )


def test_host_runtime_blocks_repo_local_venv_creation(tmp_path: Path) -> None:
    """Host runtime should refuse repo-local .venv creation."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    result = run_cli("--runtime", "host", "--workspace-root", str(workspace_root), "--create")

    assert result.returncode == 2, result.stderr
    parsed = parse_output(result.stdout)
    assert parsed["RUNTIME_ENV"] == "host"
    assert parsed["REPO_LOCAL_VENV_POLICY"] == "forbid"
    assert parsed["REPO_LOCAL_VENV_ACTION"] == "blocked_shared_runtime_policy"
    assert not (workspace_root / ".venv").exists()


def test_container_runtime_forbids_task_venv_creation(tmp_path: Path) -> None:
    """Shared container runtime must not create a second mutable tool environment."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    result = run_cli("--runtime", "container", "--workspace-root", str(workspace_root), "--create")

    assert result.returncode == 2, result.stderr
    parsed = parse_output(result.stdout)
    assert parsed["RUNTIME_ENV"] == "container"
    assert parsed["REPO_LOCAL_VENV_POLICY"] == "forbid"
    assert parsed["REPO_LOCAL_VENV_ACTION"] == "blocked_shared_runtime_policy"
    assert not (workspace_root / ".venv").exists()


def test_container_runtime_status_is_machine_readable_without_creation(tmp_path: Path) -> None:
    """Status mode should stay machine-readable and side-effect free."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    result = run_cli("--runtime", "container", "--workspace-root", str(workspace_root))

    assert result.returncode == 0, result.stderr
    parsed = parse_output(result.stdout)
    assert parsed["RUNTIME_ENV"] == "container"
    assert parsed["REPO_LOCAL_VENV_POLICY"] == "forbid"
    assert parsed["REPO_LOCAL_VENV_ACTION"] == "not_requested"
    assert parsed["REPO_LOCAL_VENV_EXISTS"] == "no"
    assert "python" in parsed["REPO_LOCAL_VENV_CREATE_COMMAND"]
    assert not (workspace_root / ".venv").exists()
