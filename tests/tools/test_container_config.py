"""Focused semantic checks for the VS Code devcontainer contract."""

# @dependency-start
# contract test
# responsibility Verifies topic-root Compose mounts, selected repo paths, and VS Code surfaces.
# upstream design ../../documents/rule/dependency-module-changes.md topic-root mount policy
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml shared VS Code surface ownership
# upstream implementation ../../tools/ci/container_config.py semantic devcontainer checker
# upstream implementation ../../.devcontainer/devcontainer.json selects the topic-root Compose generator
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "container_config.py"
GENERATOR = PROJECT_ROOT / ".devcontainer" / "generate-runtime-compose.sh"


def run_validator(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the semantic container configuration checker."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_file(root: Path, relative: str, content: str) -> None:
    """Write one fixture file."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_devcontainer(root: Path) -> None:
    """Write only the observable devcontainer entrypoint surface."""
    write_file(
        root,
        ".devcontainer/devcontainer.json",
        json.dumps(
            {
                "name": "${localWorkspaceFolderBasename}-devcontainer",
                "initializeCommand": "bash vendor/agent-canon/.devcontainer/bootstrap-shared-runtime.sh && AGENT_CANON_DEVCONTAINER_REPO_ROOT=. AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/docker-compose.generated.yml bash vendor/agent-canon/.devcontainer/generate-runtime-compose.sh",
                "dockerComposeFile": "../.agent-canon/docker-compose.generated.yml",
                "service": "workspace",
                "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",
                "postCreateCommand": "bash vendor/agent-canon/.devcontainer/post-create.sh /workspace/${localWorkspaceFolderBasename} && bash .devcontainer/post-create-parent.sh /workspace/${localWorkspaceFolderBasename}",
                "postAttachCommand": "bash vendor/agent-canon/.devcontainer/post-attach.sh",
            },
            indent=2,
        )
        + "\n",
    )
    for name in ("post-create.sh", "post-attach.sh"):
        write_file(root, f".devcontainer/{name}", "#!/usr/bin/env bash\n")
    write_file(
        root, ".devcontainer/generate-runtime-compose.sh", "#!/usr/bin/env bash\n"
    )


def write_compose(
    root: Path,
    *,
    duplicate_repo_mount: bool = False,
    include_runtime_environment: bool = True,
) -> None:
    """Write a generated Compose projection with a topic-root bind mount."""
    topic_root = root.parent.resolve()
    repo_target = f"/workspace/{root.name}"
    volumes: list[dict[str, str]] = [
        {"type": "bind", "source": str(topic_root), "target": "/workspace"},
    ]
    if duplicate_repo_mount:
        volumes.append(
            {"type": "bind", "source": str(root.resolve()), "target": repo_target}
        )
    environment_lines = (
        [
            "    environment:",
            "      AGENT_CANON_WORKSPACE_ROOT: /workspace",
            f"      AGENT_CANON_REPOSITORY_ROOT: {repo_target}",
        ]
        if include_runtime_environment
        else []
    )
    write_file(
        root,
        ".devcontainer/docker-compose.generated.yml",
        "\n".join(
            [
                "services:",
                "  workspace:",
                "    build:",
                "      context: ..",
                "      dockerfile: docker/Dockerfile",
                f"    working_dir: {repo_target}",
                "    volumes:",
                *[f"      - {json.dumps(volume)}" for volume in volumes],
                *environment_lines,
                "",
            ]
        ),
    )


def write_topic_fixture(
    tmp_path: Path,
    *,
    duplicate_repo_mount: bool = False,
    include_runtime_environment: bool = True,
    topic_root: Path | None = None,
) -> Path:
    """Create a parent repo inside one isolated topic workspace."""
    topic_root = topic_root or tmp_path / "workspace" / "dependency-module-change"
    repo = topic_root / "agent-canon"
    write_devcontainer(repo)
    write_compose(
        repo,
        duplicate_repo_mount=duplicate_repo_mount,
        include_runtime_environment=include_runtime_environment,
    )
    write_file(
        repo,
        ".gitmodules",
        '[submodule "dependency"]\n\tpath = vendor/dependency\n\turl = https://example.invalid/dependency.git\n',
    )
    write_file(
        repo,
        "tools/agent_tools/dependency_module_change.py",
        "#!/usr/bin/env python3\n",
    )
    return repo


def write_surface_manifest(root: Path, prefix: str = "") -> None:
    """Write the real-container/four-individual-symlink manifest."""
    manifest = "\n".join(
        [
            "version = 1",
            f'prefix = "{prefix or "vendor/agent-canon"}"',
            "",
            "[[surface]]",
            'path = ".vscode"',
            'mode = "regular"',
            'owner = "template-or-derived-repo"',
            'class = "active_contract"',
            'source = ".vscode"',
            "",
            "[[group]]",
            'mode = "symlink"',
            'owner = "agent-canon"',
            'class = "runtime_surface"',
            'source_prefix = ""',
            'paths = [".vscode/c_cpp_properties.json", ".vscode/extensions.json", ".vscode/settings.json", ".vscode/tasks.json"]',
            "",
        ]
    )
    path = root / (
        "documents/runtime/shared-runtime-surfaces.toml"
        if not prefix
        else f"{prefix}/documents/runtime/shared-runtime-surfaces.toml"
    )
    write_file(root, str(path.relative_to(root)), manifest)


def write_vscode_source(root: Path, relative: str = ".vscode") -> None:
    """Write regular source files for the four shared VS Code surfaces."""
    for name in (
        "c_cpp_properties.json",
        "extensions.json",
        "settings.json",
        "tasks.json",
    ):
        write_file(root, f"{relative}/{name}", "{}\n")


def load_container_config_module():
    """Load container_config as a test module."""
    module_name = "agent_canon_container_config"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PROJECT_ROOT / "tools" / "ci" / "container_config.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_topic_compose_semantics_pass(tmp_path: Path) -> None:
    """A topic-root mount exposes the selected repository one level below it."""
    repo = write_topic_fixture(tmp_path)

    result = run_validator(repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_topic_compose_root_is_rejected(tmp_path: Path) -> None:
    """The checker rejects the removed workspace-<topic-slug> root."""
    repo = write_topic_fixture(tmp_path, topic_root=tmp_path / "workspace-topic")

    result = run_validator(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "legacy-topic-root-name" in result.stdout


def test_compose_repo_double_mount_is_rejected(tmp_path: Path) -> None:
    """The selected repository is not mounted a second time below /workspace."""
    repo = write_topic_fixture(tmp_path, duplicate_repo_mount=True)

    result = run_validator(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "repository-double-mount" in result.stdout


def test_compose_missing_runtime_environment_is_rejected(tmp_path: Path) -> None:
    """Post-attach runtime roots are required in generated Compose semantics."""
    repo = write_topic_fixture(tmp_path, include_runtime_environment=False)

    result = run_validator(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "runtime-environment-required:AGENT_CANON_WORKSPACE_ROOT" in result.stdout


def test_generator_materializes_one_topic_root_mount(tmp_path: Path) -> None:
    """The generator writes the host topic root only into generated Compose."""
    repo = tmp_path / "workspace" / "topic" / "agent-canon"
    write_devcontainer(repo)
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    (repo / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "HOME": str(home)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (repo / ".devcontainer/docker-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert compose.count('target: "/workspace"') == 1
    assert str(repo.parent.resolve()) in compose
    assert "/workspace/agent-canon" in compose


def test_generator_accepts_explicit_output_path(tmp_path: Path) -> None:
    """Generator writes compose output to an explicit caller-provided destination."""
    repo = tmp_path / "workspace" / "topic" / "agent-canon"
    write_devcontainer(repo)
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    (repo / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)
    home = tmp_path / "home"
    output_path = repo / ".devcontainer/custom-compose.generated.yml"
    home.mkdir()
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": str(output_path),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output_path.is_file(), "explicit compose output must be written"
    default_output = repo / ".devcontainer/docker-compose.generated.yml"
    assert not default_output.exists()
    compose = output_path.read_text(encoding="utf-8")
    assert compose.count('target: "/workspace"') == 1
    assert str(repo.parent.resolve()) in compose
    assert "/workspace/agent-canon" in compose

    relative_output = ".devcontainer/custom-compose-relative.generated.yml"
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": relative_output,
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    relative_path = repo / relative_output
    assert relative_path.is_file(), (
        "relative compose output path must resolve from repo root"
    )
    relative_compose = relative_path.read_text(encoding="utf-8")
    assert relative_compose.count('target: "/workspace"') == 1


def test_generator_rejects_legacy_topic_root(tmp_path: Path) -> None:
    """The generator rejects the removed workspace-<topic-slug> root."""
    repo = tmp_path / "workspace-topic" / "agent-canon"
    write_devcontainer(repo)
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    (repo / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "HOME": str(home)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "legacy workspace-<topic-slug> root" in result.stderr


def test_source_vscode_surface_and_shared_files_pass(tmp_path: Path) -> None:
    """Standalone source owns a real .vscode directory and four shared files."""
    write_surface_manifest(tmp_path)
    write_vscode_source(tmp_path)

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_template_vscode_surface_uses_individual_symlinks(tmp_path: Path) -> None:
    """A template root keeps the container real and links exactly four files."""
    write_surface_manifest(tmp_path, "vendor/agent-canon")
    write_vscode_source(tmp_path, "vendor/agent-canon/.vscode")
    (tmp_path / ".vscode").mkdir()
    for name in (
        "c_cpp_properties.json",
        "extensions.json",
        "settings.json",
        "tasks.json",
    ):
        (tmp_path / ".vscode" / name).symlink_to(
            f"../vendor/agent-canon/.vscode/{name}"
        )

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_vscode_directory_symlink_is_rejected(tmp_path: Path) -> None:
    """The checker rejects the removed whole-directory topology."""
    write_surface_manifest(tmp_path, "vendor/agent-canon")
    write_vscode_source(tmp_path, "vendor/agent-canon/.vscode")
    (tmp_path / ".vscode").symlink_to(
        "vendor/agent-canon/.vscode", target_is_directory=True
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "expected-real-directory" in result.stdout


def test_missing_individual_symlink_is_rejected(tmp_path: Path) -> None:
    """The checker rejects a regular file replacing a shared-file symlink."""
    write_surface_manifest(tmp_path, "vendor/agent-canon")
    write_vscode_source(tmp_path, "vendor/agent-canon/.vscode")
    (tmp_path / ".vscode").mkdir()
    write_file(tmp_path, ".vscode/c_cpp_properties.json", "{}\n")

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "expected-individual-symlink" in result.stdout


def test_validate_requirements_accepts_pep508_direct_reference(tmp_path: Path) -> None:
    """Direct references should be accepted while still collecting required package names."""
    module = load_container_config_module()
    write_file(
        tmp_path,
        "docker/requirements.txt",
        "\n".join(
            [
                "jupyterlab",
                "notebook",
                "ipykernel",
                "pydeps",
                "snakeviz",
                "pyyaml",
                "custom-visualizer @ git+ssh://git@github.com/org/custom-visualizer.git@v1.0.0",
                "",
            ]
        ),
    )

    assert module.validate_requirements(tmp_path) == []
