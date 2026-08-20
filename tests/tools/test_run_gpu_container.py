# @dependency-start
# contract test
# responsibility Tests the sole Docker --gpus all wrapper and exact admitted environment projection.
# upstream design ../../documents/experiments/gpu-direct-command.md Docker injection contract
# upstream implementation ../../tools/ci/run_gpu_container.sh shell adapter under test
# @dependency-end

"""Focused tests for the Docker GPU shell adapter."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = PROJECT_ROOT / "tools" / "ci" / "run_gpu_container.sh"
GPU_ENV = {
    "CUDA_VISIBLE_DEVICES": "GPU-aaaa,MIG-bbbb",
    "NVIDIA_VISIBLE_DEVICES": "GPU-aaaa,MIG-bbbb",
    "JAX_PLATFORMS": "cuda",
    "XLA_PYTHON_CLIENT_PREALLOCATE": "false",
    "XLA_PYTHON_CLIENT_ALLOCATOR": "platform",
    "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR": "false",
}


def install_fake_docker(tmp_path: Path) -> Path:
    """Install one argv-capturing Docker executable."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'%s\\0\' "$@" > "$DOCKER_ARGS_FILE"\n'
        'exit "${DOCKER_EXIT_CODE:-0}"\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return bin_dir


def run_wrapper(
    tmp_path: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the wrapper with a fake Docker binary and return its argv capture."""
    args_file = tmp_path / "docker-args"
    bin_dir = install_fake_docker(tmp_path)
    env = {
        **os.environ,
        **GPU_ENV,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DOCKER_ARGS_FILE": str(args_file),
    }
    if environment:
        env.update(environment)
    result = subprocess.run(
        ["bash", str(WRAPPER), *arguments],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, args_file


def read_args(path: Path) -> list[str]:
    """Decode the fake Docker NUL-separated argv."""
    return [item.decode() for item in path.read_bytes().split(b"\0") if item]


def test_wrapper_passes_all_and_exact_environment_values(tmp_path: Path) -> None:
    """The one Docker route binds injection and admitted visibility in one argv."""
    result, args_file = run_wrapper(
        tmp_path,
        "--image",
        "gpu-image:current",
        "--gpus",
        "all",
        "--name",
        "gpu-job",
        "--",
        "python3",
        "-c",
        "print('gpu')",
    )

    assert result.returncode == 0, result.stderr
    assert read_args(args_file) == [
        "run",
        "--rm",
        "--gpus",
        "all",
        "--name",
        "gpu-job",
        "-e",
        "CUDA_VISIBLE_DEVICES=GPU-aaaa,MIG-bbbb",
        "-e",
        "NVIDIA_VISIBLE_DEVICES=GPU-aaaa,MIG-bbbb",
        "-e",
        "JAX_PLATFORMS=cuda",
        "-e",
        "XLA_PYTHON_CLIENT_PREALLOCATE=false",
        "-e",
        "XLA_PYTHON_CLIENT_ALLOCATOR=platform",
        "-e",
        "XLA_PYTHON_CLIENT_USE_CUDA_HOST_ALLOCATOR=false",
        "gpu-image:current",
        "python3",
        "-c",
        "print('gpu')",
    ]


@pytest.mark.parametrize(
    ("arguments", "environment", "error"),
    (
        (("--image", "image", "--gpus", "0", "--", "true"), {}, "gpus_must_be_all"),
        (
            ("--image", "image", "--gpus", "all", "--", "true"),
            {"NVIDIA_VISIBLE_DEVICES": "GPU-other"},
            "visibility_mismatch",
        ),
        (
            ("--image", "image", "--gpus", "all", "--", "true"),
            {"JAX_PLATFORMS": "cpu"},
            "jax_platform_must_be_cuda",
        ),
        (
            ("--image", "image", "--gpus", "all", "--", "true"),
            {"CUDA_VISIBLE_DEVICES": "0", "NVIDIA_VISIBLE_DEVICES": "0"},
            "visibility_identity_invalid:0",
        ),
    ),
)
def test_wrapper_rejects_noncanonical_gpu_inputs_before_docker(
    tmp_path: Path,
    arguments: tuple[str, ...],
    environment: dict[str, str],
    error: str,
) -> None:
    """Alternate GPU routes and invalid policy values fail before Docker starts."""
    result, args_file = run_wrapper(tmp_path, *arguments, environment=environment)

    assert result.returncode == 2
    assert f"GPU_CONTAINER_ERROR={error}" in result.stderr
    assert not args_file.exists()


def test_wrapper_requires_every_admitted_environment_value(tmp_path: Path) -> None:
    """Omitting one admitted value fails before Docker starts."""
    args_file = tmp_path / "docker-args"
    bin_dir = install_fake_docker(tmp_path)
    env = {
        **os.environ,
        **GPU_ENV,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DOCKER_ARGS_FILE": str(args_file),
    }
    env.pop("XLA_PYTHON_CLIENT_ALLOCATOR")

    result = subprocess.run(
        [
            "bash",
            str(WRAPPER),
            "--image",
            "image",
            "--gpus",
            "all",
            "--",
            "true",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "environment_missing:XLA_PYTHON_CLIENT_ALLOCATOR" in result.stderr
    assert not args_file.exists()


def test_wrapper_propagates_container_exit_code(tmp_path: Path) -> None:
    """The shell adapter does not translate Docker child failures."""
    result, _ = run_wrapper(
        tmp_path,
        "--image",
        "image",
        "--gpus",
        "all",
        "--",
        "false",
        environment={"DOCKER_EXIT_CODE": "23"},
    )

    assert result.returncode == 23
