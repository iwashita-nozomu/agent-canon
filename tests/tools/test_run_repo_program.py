# @dependency-start
# responsibility Tests test run repo program behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Tests for the generic repo-program container runner."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


def resolve_project_root() -> Path:
    """Return a project root with the repo-program runner and runtime pack files."""
    for candidate in Path(__file__).resolve().parents:
        script = candidate / "tools" / "ci" / "run_repo_program.py"
        default_pack = candidate / "docker" / "packs" / "default.toml"
        rules = candidate / "docker" / "python-execution-rules.toml"
        if script.exists() and default_pack.exists() and rules.exists():
            return candidate
    raise unittest.SkipTest("repo-program runner tests require template docker runtime files")


PROJECT_ROOT = resolve_project_root()
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "run_repo_program.py"


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
