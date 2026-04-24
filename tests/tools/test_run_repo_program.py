"""Tests for the generic repo-program container runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "ci" / "run_repo_program.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the wrapper CLI and capture the output."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_print_only_python_file_uses_python_runner_and_env_check() -> None:
    """Python files should resolve to python3 and include env-check by default."""
    result = run_cli("--print-only", "tools/ci/check_jax_export_stack.py")

    assert result.returncode == 0, result.stderr
    assert "env-check:" in result.stdout
    assert "python3 /workspace/tools/ci/check_jax_export_stack.py" in result.stdout


def test_print_only_shell_script_uses_bash() -> None:
    """Shell scripts should resolve through bash."""
    result = run_cli(
        "--print-only",
        "tools/ci/check_docker_build.sh",
        "--",
        "--pack",
        "docker/packs/default.toml",
    )

    assert result.returncode == 0, result.stderr
    assert (
        "/bin/bash /workspace/tools/ci/check_docker_build.sh --pack docker/packs/default.toml"
        in result.stdout
    )


def test_print_only_command_without_workspace_file_runs_directly() -> None:
    """Plain commands should run directly inside the container."""
    result = run_cli("--print-only", "--skip-env-check", "python3", "--", "--version")

    assert result.returncode == 0, result.stderr
    assert "run:" in result.stdout
    assert "python3 --version" in result.stdout
