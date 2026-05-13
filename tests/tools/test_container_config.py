"""Tests for container configuration validation."""

# @dependency-start
# responsibility Tests Dockerfile, runtime pack, and devcontainer config validation.
# upstream implementation ../../tools/ci/container_config.py validates container config
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
                "    rsync openssh-client graphviz python3-venv",
                "COPY docker/register_safe_directories.sh /usr/local/bin/register_safe_directories",
                "",
            ]
        ),
    )
    write_file(
        root,
        ".dockerignore",
        "\n".join(
            [
                ".git",
                "vendor/agent-canon",
                "",
            ]
        ),
    )
    write_file(root, "docker/register_safe_directories.sh", "#!/usr/bin/env bash\n")
    write_file(
        root,
        "docker/install_python_dependencies.sh",
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'requirements="${1:-/workspace}/docker/requirements.txt"',
                'sha256sum "$requirements"',
                "python3 -m pip install --upgrade pip",
                'python3 -m pip install --no-cache-dir -r "$requirements"',
                "python3 -m pip check",
                "",
            ]
        ),
    )
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
                'commands = ["bash .devcontainer/post-create.sh /workspace", "python3 --version"]',
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
                '  "postCreateCommand": "bash .devcontainer/post-create.sh /workspace",',
                '  "postAttachCommand": "bash .devcontainer/post-attach.sh"',
                "}",
                "",
            ]
        ),
    )
    write_file(
        root,
        ".devcontainer/post-create.sh",
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "run_as_root",
                "apt_install gh",
                "bash /workspace/docker/register_safe_directories.sh /workspace",
                "bash /workspace/docker/install_python_dependencies.sh /workspace",
                'git config --global --add safe.directory "$workspace"',
                "repo-local Python dependency installer absent",
                "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg",
                "npm install -g @openai/codex",
                "gh --version",
                "codex --version",
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
                "pack=docker/packs/default.toml",
                "output=.devcontainer/docker-compose.generated.yml",
                "compose_mode=agent-canon-source-only",
                "image=mcr.microsoft.com/devcontainers/base:ubuntu-22.04",
                "printf '%s\\n' \"$pack\" \"$output\"",
                "",
            ]
        ),
    )
    write_file(root, ".devcontainer/post-attach.sh", "#!/usr/bin/env bash\n")


def write_valid_devcontainer_only(root: Path) -> None:
    """Write a valid standalone AgentCanon devcontainer-only fixture."""
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
                '  "postCreateCommand": "bash .devcontainer/post-create.sh /workspace",',
                '  "postAttachCommand": "bash .devcontainer/post-attach.sh"',
                "}",
                "",
            ]
        ),
    )
    write_file(
        root,
        ".devcontainer/post-create.sh",
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "run_as_root",
                "apt_install gh",
                "docker/register_safe_directories.sh",
                "docker/install_python_dependencies.sh",
                'git config --global --add safe.directory "$workspace"',
                "repo-local Python dependency installer absent",
                "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg",
                "npm install -g @openai/codex",
                "gh --version",
                "codex --version",
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
                "pack=docker/packs/default.toml",
                "output=.devcontainer/docker-compose.generated.yml",
                "compose_mode=agent-canon-source-only",
                "image=mcr.microsoft.com/devcontainers/base:ubuntu-22.04",
                "printf '%s\\n' \"$pack\" \"$output\" \"$compose_mode\" \"$image\"",
                "",
            ]
        ),
    )
    write_file(root, ".devcontainer/post-attach.sh", "#!/usr/bin/env bash\n")


def test_missing_runtime_config_is_skipped(tmp_path: Path) -> None:
    """A standalone source checkout without docker/devcontainer config should skip."""
    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=skip" in result.stdout
    assert "CONTAINER_CONFIG_CHECKED=none" in result.stdout


def test_devcontainer_only_source_checkout_passes(tmp_path: Path) -> None:
    """Standalone AgentCanon source can validate shared devcontainer without docker/."""
    write_valid_devcontainer_only(tmp_path)

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=pass" in result.stdout
    assert "CONTAINER_CONFIG_CHECKED=.devcontainer" in result.stdout


def test_devcontainer_only_requires_source_fallback(tmp_path: Path) -> None:
    """Devcontainer source must not require repo-local docker/ when docker/ is absent."""
    write_valid_devcontainer_only(tmp_path)
    script = tmp_path / ".devcontainer" / "generate-runtime-compose.sh"
    script.write_text(
        script.read_text(encoding="utf-8").replace(
            "compose_mode=agent-canon-source-only",
            "compose_mode=repo-docker-pack",
        ),
        encoding="utf-8",
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "missing:agent-canon-source-only" in result.stdout


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


def test_dockerfile_python_install_fails(tmp_path: Path) -> None:
    """Python dependencies should be installed after workspace mount, not during image build."""
    write_valid_runtime(tmp_path)
    dockerfile = tmp_path / "docker" / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8")
        + "\nCOPY docker/requirements.txt /tmp/requirements.txt\n"
        + "RUN python3 -m pip install -r /tmp/requirements.txt\n",
        encoding="utf-8",
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "docker-build-must-not-install-python-requirements" in result.stdout
    assert "docker-build-must-not-copy-python-requirements" in result.stdout


def test_dockerfile_agent_tooling_fails(tmp_path: Path) -> None:
    """Agent convenience tools belong in shared devcontainer post-create setup."""
    write_valid_runtime(tmp_path)
    dockerfile = tmp_path / "docker" / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8")
        + "\nRUN echo https://cli.github.com/packages\n"
        + "RUN apt-get install -y gh\n"
        + "RUN npm install -g @openai/codex\n"
        + "RUN gh --version && codex --version\n",
        encoding="utf-8",
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "dockerfile-must-not-configure-github-cli" in result.stdout
    assert "dockerfile-must-not-install-gh" in result.stdout
    assert "dockerfile-must-not-install-codex-cli" in result.stdout


def test_missing_agent_canon_dockerignore_fails(tmp_path: Path) -> None:
    """Docker build context should not include the AgentCanon submodule."""
    write_valid_runtime(tmp_path)
    (tmp_path / ".dockerignore").write_text(".git\n", encoding="utf-8")

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "dependency_contract_violation:.dockerignore:missing-ignore:vendor/agent-canon" in result.stdout
