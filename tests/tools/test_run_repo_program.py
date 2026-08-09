# @dependency-start
# contract test
# responsibility Tests test run repo program behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Tests for the generic repo-program container runner."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_root() -> Path:
    """Return a project root with the repo-program runner and runtime pack files."""
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents, *Path(__file__).resolve().parents):
        default_pack = candidate / "docker" / "packs" / "default.toml"
        rules = candidate / "docker" / "python-execution-rules.toml"
        if default_pack.exists() and rules.exists():
            return candidate
    raise unittest.SkipTest(
        "repo-program runner tests require template docker runtime files"
    )


PROJECT_ROOT = resolve_project_root()
SCRIPT = SOURCE_ROOT / "tools" / "ci" / "run_repo_program.py"
RUN_CONTAINER_SCRIPT = SOURCE_ROOT / "tools" / "ci" / "run_in_repo_container.py"
RUN_PYTHON_SCRIPT = SOURCE_ROOT / "tools" / "ci" / "run_python_in_dockerfile.py"
RUN_PACK_SCRIPT = SOURCE_ROOT / "tools" / "ci" / "run_container_pack.py"
GENERIC_PYTHON_FIXTURE = "tools/agent-canon/__init__.py"
GENERIC_SHELL_FIXTURE = "tools/agent-canon/ci/check_docker_build.sh"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the wrapper CLI and capture the output."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def run_container_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the container wrapper CLI and capture the output."""
    return subprocess.run(
        [sys.executable, str(RUN_CONTAINER_SCRIPT), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_pack(tmp_path: Path, *, gpus: str | None) -> Path:
    """Write one image-owned runtime pack fixture."""
    pack_name = "gpu" if gpus else "default"
    pack = tmp_path / f"{pack_name}.toml"
    gpu_line = f'gpus = "{gpus}"' if gpus is not None else ""
    pack.write_text(
        "\n".join(
            [
                "[pack]",
                f'name = "{pack_name}"',
                'dockerfile = "docker/Dockerfile"',
                'context = "."',
                f'image_tag = "fixture:{pack_name}"',
                "",
                "[smoke]",
                'shell = "/bin/bash"',
                'commands = ["python3 --version"]',
                "",
                "[runtime]",
                'shell = "/bin/bash"',
                'workdir = "/workspace"',
                'workspace_mount = "/workspace"',
                gpu_line,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return pack


def test_print_only_python_file_uses_python_runner_and_env_check() -> None:
    """Python files should resolve to python3 and include env-check by default."""
    result = run_cli("--print-only", GENERIC_PYTHON_FIXTURE)

    assert result.returncode == 0, result.stderr
    assert "env-check:" in result.stdout
    assert "project-install --workspace" not in result.stdout
    assert "AGENT_CANON_PYTHON_EXTRAS" not in result.stdout
    assert f"python3 /workspace/{GENERIC_PYTHON_FIXTURE}" in result.stdout


def test_print_only_shell_script_uses_bash() -> None:
    """Shell scripts should resolve through bash."""
    result = run_cli(
        "--print-only",
        GENERIC_SHELL_FIXTURE,
        "--",
        "--pack",
        "docker/packs/default.toml",
    )

    assert result.returncode == 0, result.stderr
    assert (
        f"/bin/bash /workspace/{GENERIC_SHELL_FIXTURE} "
        "--pack docker/packs/default.toml"
        in result.stdout
    )


def test_print_only_command_without_workspace_file_runs_directly() -> None:
    """Plain commands should run directly inside the container."""
    result = run_cli("--print-only", "--skip-env-check", "python3", "--", "--version")

    assert result.returncode == 0, result.stderr
    assert "run:" in result.stdout
    assert "project-install --workspace" not in result.stdout
    assert "python3 --version" in result.stdout


def test_run_in_repo_container_print_only_publishes_ports() -> None:
    """The generic container runner should expose requested host ports."""
    result = run_container_cli(
        "--print-only",
        "--port",
        "8888:8888",
        "--skip-build",
        "python3",
        "--",
        "--version",
    )

    assert result.returncode == 0, result.stderr
    assert "-p 8888:8888" in result.stdout
    assert "project-install --workspace" not in result.stdout


def test_gpu_profile_reaches_every_runtime_entrypoint(tmp_path: Path) -> None:
    """GPU profile and runtime allocation survive every shared CLI route."""
    pack = write_pack(tmp_path, gpus="all")
    commands = (
        (
            RUN_CONTAINER_SCRIPT,
            ("--pack", str(pack), "--print-only", "python3", "--", "--version"),
        ),
        (
            SCRIPT,
            (
                "--pack",
                str(pack),
                "--print-only",
                "--skip-env-check",
                "python3",
                "--",
                "--version",
            ),
        ),
        (
            RUN_PYTHON_SCRIPT,
            (
                "docker/Dockerfile",
                GENERIC_PYTHON_FIXTURE,
                "--pack",
                str(pack),
                "--print-only",
            ),
        ),
        (RUN_PACK_SCRIPT, ("--pack", str(pack), "--print-only")),
    )

    for script, args in commands:
        result = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "--gpus all" in result.stdout
        assert "project-install --workspace" not in result.stdout
        assert "AGENT_CANON_PYTHON_EXTRAS" not in result.stdout
