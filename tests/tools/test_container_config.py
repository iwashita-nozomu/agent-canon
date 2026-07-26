"""Focused semantic checks for the VS Code devcontainer contract."""

# @dependency-start
# contract test
# responsibility Verifies topic-root Compose mounts, selected repo paths, and VS Code surfaces.
# upstream design ../../documents/rule/dependency-module-changes.md topic-root mount policy
# upstream design ../../documents/shared-runtime-surfaces.toml shared VS Code surface ownership
# upstream implementation ../../tools/ci/container_config.py semantic devcontainer checker
# upstream implementation ../../.devcontainer/generate-runtime-compose.sh topic-root Compose generator
# @dependency-end

from __future__ import annotations

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
                "initializeCommand": "bash .devcontainer/bootstrap-shared-runtime.sh && bash .devcontainer/generate-runtime-compose.sh",
                "dockerComposeFile": "docker-compose.generated.yml",
                "service": "workspace",
                "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",
                "postCreateCommand": "bash .devcontainer/post-create.sh /workspace/${localWorkspaceFolderBasename}",
                "postAttachCommand": "bash .devcontainer/post-attach.sh",
            },
            indent=2,
        )
        + "\n",
    )
    for name in ("finalize-shared-runtime.sh", "post-create.sh", "post-attach.sh"):
        write_file(root, f".devcontainer/{name}", "#!/usr/bin/env bash\n")
    write_file(root, ".devcontainer/generate-runtime-compose.sh", "#!/usr/bin/env bash\n")


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
        volumes.append({"type": "bind", "source": str(root.resolve()), "target": repo_target})
    environment_lines = [
        "    environment:",
        "      AGENT_CANON_WORKSPACE_ROOT: /workspace",
        f"      AGENT_CANON_REPOSITORY_ROOT: {repo_target}",
    ] if include_runtime_environment else []
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
) -> Path:
    """Create a parent repo inside one isolated topic workspace."""
    topic_root = tmp_path / "workspace-dependency-module-change"
    repo = topic_root / "agent-canon"
    write_devcontainer(repo)
    write_compose(
        repo,
        duplicate_repo_mount=duplicate_repo_mount,
        include_runtime_environment=include_runtime_environment,
    )
    write_file(repo, ".gitmodules", '[submodule "dependency"]\n\tpath = vendor/dependency\n\turl = https://example.invalid/dependency.git\n')
    write_file(repo, "tools/agent_tools/dependency_module_change.py", "#!/usr/bin/env python3\n")
    return repo


def write_surface_manifest(root: Path, prefix: str = "") -> None:
    """Write the real-container/four-individual-symlink manifest."""
    manifest = "\n".join(
        [
            'version = 1',
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
    path = root / ("documents/shared-runtime-surfaces.toml" if not prefix else f"{prefix}/documents/shared-runtime-surfaces.toml")
    write_file(root, str(path.relative_to(root)), manifest)


def write_vscode_source(root: Path, relative: str = ".vscode") -> None:
    """Write regular source files for the four shared VS Code surfaces."""
    for name in ("c_cpp_properties.json", "extensions.json", "settings.json", "tasks.json"):
        write_file(root, f"{relative}/{name}", "{}\n")


def test_topic_compose_semantics_pass(tmp_path: Path) -> None:
    """A topic-root mount exposes the selected repository one level below it."""
    repo = write_topic_fixture(tmp_path)

    result = run_validator(repo)

    assert result.returncode == 0, result.stdout + result.stderr


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
    repo = tmp_path / "workspace-topic" / "agent-canon"
    write_devcontainer(repo)
    write_file(repo, ".devcontainer/generate-runtime-compose.sh", GENERATOR.read_text(encoding="utf-8"))
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
    compose = (repo / ".devcontainer/docker-compose.generated.yml").read_text(encoding="utf-8")
    assert compose.count('target: "/workspace"') == 1
    assert str(repo.parent.resolve()) in compose
    assert "/workspace/agent-canon" in compose


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
    for name in ("c_cpp_properties.json", "extensions.json", "settings.json", "tasks.json"):
        (tmp_path / ".vscode" / name).symlink_to(f"../vendor/agent-canon/.vscode/{name}")

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_vscode_directory_symlink_is_rejected(tmp_path: Path) -> None:
    """The checker rejects the removed whole-directory topology."""
    write_surface_manifest(tmp_path, "vendor/agent-canon")
    write_vscode_source(tmp_path, "vendor/agent-canon/.vscode")
    (tmp_path / ".vscode").symlink_to("vendor/agent-canon/.vscode", target_is_directory=True)

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
