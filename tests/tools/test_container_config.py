"""Tests for container configuration validation."""

# @dependency-start
# contract test
# responsibility Tests Dockerfile, runtime pack, and devcontainer config validation.
# upstream implementation ../../tools/ci/container_config.py validates container config
# upstream implementation ../../tools/ci/container_runtime.py defines runtime pack fields
# upstream environment ../../.devcontainer/post-create.sh installs shared devcontainer tools
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "container_config.py"
POST_CREATE_TEX_SNIPPETS = (
    "install_tex_tooling",
    "latexmk",
    "texlive-latex-recommended",
    "texlive-latex-extra",
    "texlive-fonts-recommended",
    "texlive-pictures",
    "texlive-xetex",
    "texlive-extra-utils",
    "dvisvgm",
    "ghostscript",
    "poppler-utils",
    "latexmk --version",
    "pdflatex --version",
    "xelatex --version",
    "dvisvgm --version",
    "pdfcrop --version",
)
POST_CREATE_LEAN_SNIPPETS = (
    "AGENT_CANON_LEAN_TOOLCHAIN",
    "leanprover/lean4:v4.30.0",
    "AGENT_CANON_ELAN_VERSION",
    "v4.2.3",
    "AGENT_CANON_ELAN_X86_64_SHA256",
    "AGENT_CANON_ELAN_AARCH64_SHA256",
    "install_lean_toolchain",
    "leanprover/elan/releases/download",
    "elan-x86_64-unknown-linux-gnu.tar.gz",
    "elan-aarch64-unknown-linux-gnu.tar.gz",
    "sha256sum -c -",
    "elan-init",
    "elan toolchain install",
    "elan default",
    "for tool in elan lean lake",
    "/usr/local/bin/${tool}",
    "elan --version",
    "lean --version",
    "lake --version",
)
POST_CREATE_CODEX_SNIPPETS = (
    "codex --version >/dev/null",
    "npm install -g @openai/codex",
)


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


def write_valid_vscode_files(root: Path, relative: str = ".vscode") -> None:
    """Write valid shared VS Code fixture files."""
    write_file(root, f"{relative}/c_cpp_properties.json", "{}\n")
    write_file(root, f"{relative}/extensions.json", "{}\n")
    write_file(root, f"{relative}/settings.json", "{}\n")
    write_file(root, f"{relative}/tasks.json", "{}\n")


def write_vscode_surface_manifest(
    root: Path,
    relative: str = "documents/shared-runtime-surfaces.toml",
) -> None:
    """Write a minimal shared surface manifest with .vscode ownership."""
    write_file(
        root,
        relative,
        "\n".join(
            [
                'prefix = "vendor/agent-canon"',
                "",
                "[[group]]",
                'mode = "symlink"',
                'owner = "agent-canon"',
                'class = "runtime_surface"',
                'paths = [".vscode"]',
                "",
            ]
        ),
    )


def write_valid_runtime(root: Path) -> None:
    """Write a minimal valid Docker/devcontainer runtime fixture."""
    write_valid_docker_runtime(root)
    write_valid_runtime_pack(root)
    write_valid_devcontainer_files(root)


def write_valid_docker_runtime(root: Path) -> None:
    """Write valid Dockerfile and dependency fixture files."""
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
                "    rsync openssh-client graphviz python3.11 python3.11-dev python3.11-venv",
                "COPY docker/register_safe_directories.sh /usr/local/bin/register_safe_directories",
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
        ".dockerignore",
        "\n".join(
            [
                ".git",
                ".state",
                "*.gguf",
                "*.safetensors",
                "pytorch_model*.bin",
                "model-*.bin",
                ".cache/huggingface",
                ".cache/llama.cpp",
                "vendor/local-llm-server/llama-cpp/models",
                "vendor/local-llm-server/llama-cpp/cache",
                "vendor/local-llm-server/llama-cpp/runtime",
                "vendor/agent-canon",
                "",
            ]
        ),
    )


def write_valid_runtime_pack(root: Path) -> None:
    """Write a valid runtime pack fixture."""
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


def write_valid_devcontainer_files(root: Path) -> None:
    """Write valid shared devcontainer fixture files."""
    write_file(
        root,
        ".devcontainer/devcontainer.json",
        "\n".join(
            [
                "{",
                '  "name": "${localWorkspaceFolderBasename}-devcontainer",',
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
                *POST_CREATE_CODEX_SNIPPETS,
                "rustup toolchain install",
                "rustfmt",
                "clippy",
                "rust-analyzer",
                "cargo build --release",
                "AGENT_CANON_TOOLS_HOME",
                "${tools_home}/agent-canon/bin/agent-canon",
                "/usr/local/bin/agent-canon",
                "install_llama_cpp",
                "tools/install_llama_cpp.sh",
                "ggml-org/SmolLM3-3B-GGUF:Q4_K_M",
                "${tools_home}/bin/llama-cli",
                "install_secret_scanners",
                "gitleaks",
                "trufflehog",
                "detect-secrets",
                "apt_install jq",
                "jq --version",
                *POST_CREATE_TEX_SNIPPETS,
                *POST_CREATE_LEAN_SNIPPETS,
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
                "default_project_name=fixture-devcontainer",
                'DEVCONTAINER_PROJECT_NAME="${DEVCONTAINER_PROJECT_NAME:-$default_project_name}"',
                "compose_mode=agent-canon-source-only",
                "image=mcr.microsoft.com/devcontainers/base:ubuntu-22.04",
                "AGENT_CANON_SECRET_DIR",
                "AGENT_CANON_SECRET_MOUNT",
                "AGENT_CANON_SECRET_DIR_MODE",
                "printf '%s\\n' \"$pack\" \"$output\" \"$DEVCONTAINER_PROJECT_NAME\"",
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
                '  "name": "${localWorkspaceFolderBasename}-devcontainer",',
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
                *POST_CREATE_CODEX_SNIPPETS,
                "rustup toolchain install",
                "rustfmt",
                "clippy",
                "rust-analyzer",
                "cargo build --release",
                "AGENT_CANON_TOOLS_HOME",
                "${tools_home}/agent-canon/bin/agent-canon",
                "/usr/local/bin/agent-canon",
                "install_llama_cpp",
                "tools/install_llama_cpp.sh",
                "ggml-org/SmolLM3-3B-GGUF:Q4_K_M",
                "${tools_home}/bin/llama-cli",
                "install_secret_scanners",
                "gitleaks",
                "trufflehog",
                "detect-secrets",
                "apt_install jq",
                "jq --version",
                *POST_CREATE_TEX_SNIPPETS,
                *POST_CREATE_LEAN_SNIPPETS,
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
                "default_project_name=fixture-devcontainer",
                'DEVCONTAINER_PROJECT_NAME="${DEVCONTAINER_PROJECT_NAME:-$default_project_name}"',
                "compose_mode=agent-canon-source-only",
                "image=mcr.microsoft.com/devcontainers/base:ubuntu-22.04",
                "AGENT_CANON_SECRET_DIR",
                "AGENT_CANON_SECRET_MOUNT",
                "AGENT_CANON_SECRET_DIR_MODE",
                "printf '%s\\n' \"$pack\" \"$output\" \"$DEVCONTAINER_PROJECT_NAME\" \"$compose_mode\" \"$image\"",
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


def test_vscode_source_checkout_passes(tmp_path: Path) -> None:
    """Standalone AgentCanon source owns the shared VS Code workspace defaults."""
    write_vscode_surface_manifest(tmp_path)
    write_valid_vscode_files(tmp_path)

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=pass" in result.stdout
    assert "CONTAINER_CONFIG_CHECKED=.vscode" in result.stdout


def test_template_vscode_shared_view_passes(tmp_path: Path) -> None:
    """Template roots expose .vscode as a shared view into AgentCanon."""
    write_vscode_surface_manifest(
        tmp_path,
        "vendor/agent-canon/documents/shared-runtime-surfaces.toml",
    )
    write_valid_vscode_files(tmp_path, "vendor/agent-canon/.vscode")
    (tmp_path / ".vscode").symlink_to("vendor/agent-canon/.vscode", target_is_directory=True)

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=pass" in result.stdout
    assert "CONTAINER_CONFIG_CHECKED=.vscode" in result.stdout


def test_template_vscode_local_directory_fails(tmp_path: Path) -> None:
    """Template roots keep the root .vscode path as the AgentCanon shared view."""
    write_vscode_surface_manifest(
        tmp_path,
        "vendor/agent-canon/documents/shared-runtime-surfaces.toml",
    )
    write_valid_vscode_files(tmp_path, "vendor/agent-canon/.vscode")
    write_valid_vscode_files(tmp_path)

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=fail" in result.stdout
    assert "inconsistency:.vscode:expected-shared-view:vendor/agent-canon/.vscode" in result.stdout


def test_devcontainer_only_source_checkout_passes(tmp_path: Path) -> None:
    """Standalone AgentCanon source can validate shared devcontainer without docker/."""
    write_valid_devcontainer_only(tmp_path)

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=pass" in result.stdout
    assert "CONTAINER_CONFIG_CHECKED=.devcontainer" in result.stdout


def test_devcontainer_only_requires_source_route(tmp_path: Path) -> None:
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


def test_devcontainer_generator_rejects_fixed_ipam(tmp_path: Path) -> None:
    """Devcontainer generator should rely on Docker Compose automatic network selection."""
    write_valid_devcontainer_only(tmp_path)
    script = tmp_path / ".devcontainer" / "generate-runtime-compose.sh"
    script.write_text(
        script.read_text(encoding="utf-8")
        + "\nDEVCONTAINER_SUBNET=192.168.248.16/28\n"
        + "printf '    ipam:\\n'\n",
        encoding="utf-8",
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "forbidden:DEVCONTAINER_SUBNET" in result.stdout
    assert "forbidden:ipam:" in result.stdout


def test_shared_generator_mounts_configured_secret_directory(tmp_path: Path) -> None:
    """Generated compose should mount the optional host secret directory when configured."""
    write_valid_runtime_pack(tmp_path)
    script = tmp_path / ".devcontainer" / "generate-runtime-compose.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        (PROJECT_ROOT / ".devcontainer" / "generate-runtime-compose.sh").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    secret_dir = tmp_path / "private-git"
    secret_dir.mkdir()
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    env = {
        **os.environ,
        "HOME": str(home_dir),
        "AGENT_CANON_SECRET_DIR": str(secret_dir),
        "AGENT_CANON_SECRET_MOUNT": "/mnt/private-git",
        "AGENT_CANON_SECRET_DIR_MODE": "rw",
    }
    env.pop("SSH_AUTH_SOCK", None)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (tmp_path / ".devcontainer" / "docker-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert "secret_mount=enabled" in result.stdout
    assert f"source: {json.dumps(str(secret_dir))}" in compose
    assert 'target: "/mnt/private-git"' in compose
    assert "read_only: false" in compose
    assert 'AGENT_CANON_SECRET_MOUNT: "/mnt/private-git"' in compose
    assert 'AGENT_CANON_SECRET_DIR_MODE: "rw"' in compose


def test_shared_generator_warns_instead_of_requiring_missing_gpu_runtime(
    tmp_path: Path,
) -> None:
    """A host GPU without Docker NVIDIA runtime should not make compose require GPUs."""
    write_valid_runtime_pack(tmp_path)
    script = tmp_path / ".devcontainer" / "generate-runtime-compose.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        (PROJECT_ROOT / ".devcontainer" / "generate-runtime-compose.sh").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    nvidia_smi = fake_bin / "nvidia-smi"
    nvidia_smi.write_text("#!/usr/bin/env bash\nprintf 'GPU 0: fixture\\n'\n", encoding="utf-8")
    nvidia_smi.chmod(0o755)
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = info ]; then printf '%s\\n' '{\"runc\":{}}'; exit 0; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
    }
    env.pop("SSH_AUTH_SOCK", None)
    Path(env["HOME"]).mkdir()

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (tmp_path / ".devcontainer" / "docker-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert "gpus: all" not in compose
    assert 'DEVCONTAINER_GPU_MODE: "unavailable"' in compose
    assert 'DEVCONTAINER_GPU_NOTICE: "docker-nvidia-runtime-unavailable"' in compose
    assert "devcontainer gpu unavailable: docker-nvidia-runtime-unavailable" in result.stderr


def test_shared_generator_requires_gpu_only_when_runtime_is_available(
    tmp_path: Path,
) -> None:
    """Generated compose should request GPUs only when Docker can satisfy it."""
    write_valid_runtime_pack(tmp_path)
    script = tmp_path / ".devcontainer" / "generate-runtime-compose.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        (PROJECT_ROOT / ".devcontainer" / "generate-runtime-compose.sh").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    nvidia_smi = fake_bin / "nvidia-smi"
    nvidia_smi.write_text("#!/usr/bin/env bash\nprintf 'GPU 0: fixture\\n'\n", encoding="utf-8")
    nvidia_smi.chmod(0o755)
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = info ]; then printf '%s\\n' '{\"nvidia\":{}}'; exit 0; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HOME": str(tmp_path / "home"),
    }
    env.pop("SSH_AUTH_SOCK", None)
    Path(env["HOME"]).mkdir()

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (tmp_path / ".devcontainer" / "docker-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert "gpus: all" in compose
    assert 'DEVCONTAINER_GPU_MODE: "enabled"' in compose
    assert 'DEVCONTAINER_GPU_NOTICE: "docker-nvidia-runtime-available"' in compose


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
                "name: fixture-devcontainer",
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


def test_generated_compose_fixed_ipam_fails(tmp_path: Path) -> None:
    """Generated devcontainer compose should not pin subnet or gateway values."""
    write_valid_runtime(tmp_path)
    write_file(
        tmp_path,
        ".devcontainer/docker-compose.generated.yml",
        "\n".join(
            [
                "name: fixture-devcontainer",
                "services:",
                "  workspace:",
                "    build:",
                "      context: ..",
                "      dockerfile: docker/Dockerfile",
                "    working_dir: /workspace",
                "    volumes:",
                "      - ..:/workspace:cached",
                "networks:",
                "  default:",
                "    ipam:",
                "      config:",
                "        - subnet: 192.168.248.16/28",
                "          gateway: 192.168.248.17",
                "",
            ]
        ),
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "CONTAINER_CONFIG=fail" in result.stdout
    assert "forbidden:ipam:" in result.stdout
    assert "forbidden:subnet:" in result.stdout
    assert "forbidden:gateway:" in result.stdout


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
        + "RUN gh --version && codex --version\n"
        + "RUN curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh\n"
        + "RUN curl -fsSL https://github.com/leanprover/elan/releases/download/v4.2.3/elan-x86_64-unknown-linux-gnu.tar.gz -o /tmp/elan.tar.gz\n"
        + "RUN elan toolchain install leanprover/lean4:v4.30.0\n"
        + "RUN lean --version && lake build\n",
        encoding="utf-8",
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "dockerfile-must-not-configure-github-cli" in result.stdout
    assert "dockerfile-must-not-install-gh" in result.stdout
    assert "dockerfile-must-not-install-codex-cli" in result.stdout
    assert "dockerfile-must-not-install-lean-via-elan" in result.stdout
    assert "dockerfile-must-not-install-elan-release" in result.stdout
    assert "dockerfile-must-not-run-elan" in result.stdout
    assert "dockerfile-must-not-smoke-check-lean" in result.stdout
    assert "dockerfile-must-not-run-lake" in result.stdout


def test_missing_agent_canon_dockerignore_fails(tmp_path: Path) -> None:
    """Docker build context should not include the AgentCanon submodule."""
    write_valid_runtime(tmp_path)
    (tmp_path / ".dockerignore").write_text(".git\n", encoding="utf-8")

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "dependency_contract_violation:.dockerignore:missing-ignore:vendor/agent-canon" in result.stdout


def test_missing_local_model_cache_dockerignore_fails(tmp_path: Path) -> None:
    """Docker build context should not include local LLM model artifacts."""
    write_valid_runtime(tmp_path)
    (tmp_path / ".dockerignore").write_text(".git\nvendor/agent-canon\n", encoding="utf-8")

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "dependency_contract_violation:.dockerignore:missing-ignore:.state" in result.stdout
    assert "dependency_contract_violation:.dockerignore:missing-ignore:*.gguf" in result.stdout
