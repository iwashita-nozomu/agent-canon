# @dependency-start
# contract test
# responsibility Tests one Docker GPU entrypoint, internal CDI/all selection, and exact admitted environment projection.
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
EXACT_CDI_INVENTORY = "\n".join(
    (
        "nvidia.com/gpu=all",
        "nvidia.com/gpu=GPU-aaaa",
        "nvidia.com/gpu=MIG-bbbb",
    )
)


def install_fake_docker(tmp_path: Path) -> Path:
    """Install one Docker executable with read-only inventory and run capture."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "${1-}" == "info" ]]; then\n'
        '  printf \'info\\n\' >> "$DOCKER_CALLS_FILE"\n'
        '  printf \'%s\' "${DOCKER_CDI_INVENTORY-}"\n'
        '  exit "${DOCKER_INFO_EXIT_CODE:-0}"\n'
        "fi\n"
        'printf \'run\\n\' >> "$DOCKER_CALLS_FILE"\n'
        'printf \'%s\\0\' "$@" > "$DOCKER_ARGS_FILE"\n'
        'exit "${DOCKER_RUN_EXIT_CODE:-0}"\n',
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return bin_dir


def run_wrapper(
    tmp_path: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """Run the wrapper with a fake Docker binary and return its evidence files."""
    args_file = tmp_path / "docker-args"
    calls_file = tmp_path / "docker-calls"
    bin_dir = install_fake_docker(tmp_path)
    env = {
        **os.environ,
        **GPU_ENV,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DOCKER_ARGS_FILE": str(args_file),
        "DOCKER_CALLS_FILE": str(calls_file),
        "DOCKER_CDI_INVENTORY": EXACT_CDI_INVENTORY,
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
    return result, args_file, calls_file


def read_args(path: Path) -> list[str]:
    """Decode the fake Docker NUL-separated argv."""
    return [item.decode() for item in path.read_bytes().split(b"\0") if item]


def read_calls(path: Path) -> list[str]:
    """Read Docker preflight/run calls in order."""
    return path.read_text(encoding="utf-8").splitlines()


def expected_environment_args() -> list[str]:
    """Return the exact admitted environment argv shared by both routes."""
    result: list[str] = []
    for name, value in GPU_ENV.items():
        result.extend(("-e", f"{name}={value}"))
    return result


def test_wrapper_selects_exact_individual_cdi_devices(tmp_path: Path) -> None:
    """A complete daemon-discovered UUID mapping selects only those CDI devices."""
    result, args_file, calls_file = run_wrapper(
        tmp_path,
        "--image",
        "gpu-image:current",
        "--name",
        "gpu-job",
        "--",
        "python3",
        "-c",
        "print('gpu')",
    )

    assert result.returncode == 0, result.stderr
    assert read_calls(calls_file) == ["info", "run"]
    assert read_args(args_file) == [
        "run",
        "--rm",
        "--device",
        "nvidia.com/gpu=GPU-aaaa",
        "--device",
        "nvidia.com/gpu=MIG-bbbb",
        "--name",
        "gpu-job",
        *expected_environment_args(),
        "gpu-image:current",
        "python3",
        "-c",
        "print('gpu')",
    ]
    assert "GPU_CONTAINER_INJECTION=individual-cdi" in result.stderr
    assert (
        "GPU_CONTAINER_INJECTION_REASON=exact_uuid_devices_discovered"
        in result.stderr
    )


def test_wrapper_uses_all_when_daemon_only_discovers_all(tmp_path: Path) -> None:
    """The same public invocation falls back when no exact UUID CDI names exist."""
    result, args_file, calls_file = run_wrapper(
        tmp_path,
        "--image",
        "gpu-image:current",
        "--",
        "true",
        environment={"DOCKER_CDI_INVENTORY": "nvidia.com/gpu=all\n"},
    )

    assert result.returncode == 0, result.stderr
    assert read_calls(calls_file) == ["info", "run"]
    assert read_args(args_file) == [
        "run",
        "--rm",
        "--gpus",
        "all",
        *expected_environment_args(),
        "gpu-image:current",
        "true",
    ]
    assert "GPU_CONTAINER_INJECTION=gpus-all" in result.stderr
    assert (
        "GPU_CONTAINER_INJECTION_REASON=exact_uuid_devices_not_discovered"
        in result.stderr
    )


def test_wrapper_uses_all_for_partial_exact_cdi_mapping(tmp_path: Path) -> None:
    """A partial mapping never mixes CDI and all injection in one workload run."""
    result, args_file, calls_file = run_wrapper(
        tmp_path,
        "--image",
        "image",
        "--",
        "true",
        environment={
            "DOCKER_CDI_INVENTORY": "nvidia.com/gpu=all\nnvidia.com/gpu=GPU-aaaa\n"
        },
    )

    assert result.returncode == 0, result.stderr
    assert read_calls(calls_file) == ["info", "run"]
    args = read_args(args_file)
    assert args[0:4] == ["run", "--rm", "--gpus", "all"]
    assert "--device" not in args


def test_wrapper_uses_all_when_docker_cdi_inventory_is_unavailable(
    tmp_path: Path,
) -> None:
    """Older/unsupported Docker info surfaces retain the established all route."""
    result, args_file, calls_file = run_wrapper(
        tmp_path,
        "--image",
        "image",
        "--",
        "true",
        environment={"DOCKER_INFO_EXIT_CODE": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert read_calls(calls_file) == ["info", "run"]
    args = read_args(args_file)
    assert args[0:4] == ["run", "--rm", "--gpus", "all"]
    assert "GPU_CONTAINER_INJECTION_REASON=docker_cdi_inventory_unavailable" in result.stderr


@pytest.mark.parametrize(
    ("environment", "error"),
    (
        ({"NVIDIA_VISIBLE_DEVICES": "GPU-other"}, "visibility_mismatch"),
        ({"JAX_PLATFORMS": "cpu"}, "jax_platform_must_be_cuda"),
        (
            {"CUDA_VISIBLE_DEVICES": "0", "NVIDIA_VISIBLE_DEVICES": "0"},
            "visibility_identity_invalid:0",
        ),
    ),
)
def test_wrapper_rejects_invalid_gpu_policy_before_docker(
    tmp_path: Path,
    environment: dict[str, str],
    error: str,
) -> None:
    """Invalid admission values fail before Docker inventory or workload calls."""
    result, args_file, calls_file = run_wrapper(
        tmp_path,
        "--image",
        "image",
        "--",
        "true",
        environment=environment,
    )

    assert result.returncode == 2
    assert f"GPU_CONTAINER_ERROR={error}" in result.stderr
    assert not args_file.exists()
    assert not calls_file.exists()


def test_wrapper_rejects_caller_selected_injection_mode(tmp_path: Path) -> None:
    """Runtime injection is internal and cannot diverge at the public entrypoint."""
    result, args_file, calls_file = run_wrapper(
        tmp_path,
        "--image",
        "image",
        "--gpus",
        "all",
        "--",
        "true",
    )

    assert result.returncode == 2
    assert "GPU_CONTAINER_ERROR=unknown_argument:--gpus" in result.stderr
    assert not args_file.exists()
    assert not calls_file.exists()


def test_wrapper_requires_every_admitted_environment_value(tmp_path: Path) -> None:
    """Omitting one admitted value fails before Docker starts."""
    args_file = tmp_path / "docker-args"
    calls_file = tmp_path / "docker-calls"
    bin_dir = install_fake_docker(tmp_path)
    env = {
        **os.environ,
        **GPU_ENV,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DOCKER_ARGS_FILE": str(args_file),
        "DOCKER_CALLS_FILE": str(calls_file),
        "DOCKER_CDI_INVENTORY": EXACT_CDI_INVENTORY,
    }
    env.pop("XLA_PYTHON_CLIENT_ALLOCATOR")

    result = subprocess.run(
        ["bash", str(WRAPPER), "--image", "image", "--", "true"],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "environment_missing:XLA_PYTHON_CLIENT_ALLOCATOR" in result.stderr
    assert not args_file.exists()
    assert not calls_file.exists()


def test_wrapper_propagates_one_container_exit_without_retry(tmp_path: Path) -> None:
    """The selected route starts the workload once and preserves its raw exit code."""
    result, _, calls_file = run_wrapper(
        tmp_path,
        "--image",
        "image",
        "--",
        "false",
        environment={"DOCKER_RUN_EXIT_CODE": "23"},
    )

    assert result.returncode == 23
    assert read_calls(calls_file) == ["info", "run"]
