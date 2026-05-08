"""Tests for container configuration validation."""

# @dependency-start
# responsibility Tests Dockerfile, runtime pack, and devcontainer config validation.
# upstream implementation ../../tools/ci/container_config.py validates container config
# upstream implementation ../../tools/ci/render_devcontainer_compose.py renders devcontainer compose
# upstream implementation ../../tools/ci/container_runtime.py defines runtime pack fields
# @dependency-end

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "container_config.py"


def run_validator(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the container configuration validator."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_file(root: Path, relative: str, text: str) -> None:
    """Write one fixture file."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_valid_runtime(root: Path) -> None:
    """Write a minimal valid Docker/devcontainer runtime fixture."""
    write_file(
        root,
        "docker/Dockerfile",
        "\n".join(
            [
                "# @dependency-start",
                "# responsibility Fixture Dockerfile.",
                "# upstream environment README.md fixture",
                "# @dependency-end",
                "FROM ubuntu:22.04",
                "RUN apt-get update && apt-get install -y \\",
                "    rsync openssh-client graphviz python3-venv gh",
                "RUN echo https://cli.github.com/packages",
                "COPY docker/requirements.txt /tmp/requirements.txt",
                "RUN python3 -m pip install -r /tmp/requirements.txt",
                "COPY docker/register_safe_directories.sh /usr/local/bin/register_safe_directories",
                "RUN gh --version",
                "",
            ]
        ),
    )
    write_file(root, "docker/register_safe_directories.sh", "#!/usr/bin/env bash\n")
    write_file(
        root,
        "docker/requirements.txt",
        "\n".join(
            [
                "jupyterlab",
                "notebook",
                "ipykernel",
                "pydeps",
                "snakeviz",
                "pyyaml",
                "",
            ]
        ),
    )
    write_file(
        root,
        "docker/packs/default.toml",
        "\n".join(
            [
                "# @dependency-start",
                "# responsibility Fixture runtime pack.",
                "# upstream environment ../Dockerfile fixture",
                "# @dependency-end",
                "[pack]",
                'name = "default"',
                'dockerfile = "docker/Dockerfile"',
                'context = "."',
                'image_tag = "fixture:runtime"',
                "",
                "[smoke]",
                'shell = "/bin/bash"',
                'commands = ["python3 --version"]',
                "",
                "[runtime]",
                'shell = "/bin/bash"',
                'workdir = "/workspace"',
                'workspace_mount = "/workspace"',
                "",
            ]
        ),
    )
    write_file(
        root,
        ".devcontainer/devcontainer.json",
        "\n".join(
            [
                "{",
                '  "initializeCommand": "bash .devcontainer/generate-runtime-compose.sh",',
                '  "dockerComposeFile": "docker-compose.generated.yml",',
                '  "service": "workspace",',
                '  "workspaceFolder": "/workspace",',
                '  "postCreateCommand": "bash docker/register_safe_directories.sh /workspace"',
                "}",
                "",
            ]
        ),
    )
    write_file(
        root,
        ".devcontainer/generate-runtime-compose.sh",
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "python3 tools/ci/render_devcontainer_compose.py "
                "--pack docker/packs/default.toml "
                "--output .devcontainer/docker-compose.generated.yml",
                "",
            ]
        ),
    )


def test_missing_runtime_config_is_skipped(tmp_path: Path) -> None:
    """A standalone source checkout without docker/devcontainer config should skip."""
    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=skip" in result.stdout
    assert "CONTAINER_CONFIG_CHECKED=none" in result.stdout


def test_valid_runtime_config_passes(tmp_path: Path) -> None:
    """A coherent Dockerfile, pack, and devcontainer entrypoint should pass."""
    write_valid_runtime(tmp_path)

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=pass" in result.stdout
    assert "CONTAINER_CONFIG_PACK=default" in result.stdout


def test_pack_path_escape_fails(tmp_path: Path) -> None:
    """Runtime pack paths must not escape the repository root."""
    write_valid_runtime(tmp_path)
    pack = tmp_path / "docker" / "packs" / "default.toml"
    pack.write_text(
        pack.read_text(encoding="utf-8").replace(
            'dockerfile = "docker/Dockerfile"',
            'dockerfile = "../Dockerfile"',
        ),
        encoding="utf-8",
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=fail" in result.stdout
    assert "invalid_manifest:docker/packs/default.toml:dockerfile-escapes-repo" in result.stdout


def test_generated_compose_mismatch_fails(tmp_path: Path) -> None:
    """Generated devcontainer compose should match the default runtime pack."""
    write_valid_runtime(tmp_path)
    write_file(
        tmp_path,
        ".devcontainer/docker-compose.generated.yml",
        "\n".join(
            [
                "services:",
                "  workspace:",
                "    build:",
                "      context: ..",
                "      dockerfile: docker/Other.Dockerfile",
                "    working_dir: /workspace",
                "    volumes:",
                "      - ..:/workspace:cached",
                "",
            ]
        ),
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=fail" in result.stdout
    assert "missing:dockerfile: docker/Dockerfile" in result.stdout


def test_invalid_requirements_fail(tmp_path: Path) -> None:
    """docker/requirements.txt syntax and required package gaps are reported."""
    write_valid_runtime(tmp_path)
    requirements = tmp_path / "docker" / "requirements.txt"
    requirements.write_text("not valid requirement ???\n", encoding="utf-8")

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=fail" in result.stdout
    assert "dependency_contract_violation:docker/requirements.txt:invalid-line:1" in result.stdout
    assert "dependency_contract_violation:docker/requirements.txt:missing:jupyterlab" in result.stdout
