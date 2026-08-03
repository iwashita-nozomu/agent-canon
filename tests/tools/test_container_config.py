"""Focused semantic checks for the VS Code devcontainer contract."""

# @dependency-start
# contract test
# responsibility Verifies topic-root Compose mounts, selected repo paths, and VS Code surfaces.
# upstream design ../../documents/rule/dependency-module-changes.md topic-root mount policy
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml shared VS Code surface ownership
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md parent layout and runtime shell contract
# upstream implementation ../../tools/ci/container_config.py semantic devcontainer checker
# upstream implementation ../../tools/agent_tools/requirements_lock.py canonical requirements lock parser and result/error model
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


def write_host_zshrc(home: Path, content: str = "# fixture zshrc\n") -> None:
    """Write the explicit host zshrc premise used by generator tests."""
    home.mkdir(parents=True, exist_ok=True)
    (home / ".zshrc").write_text(content, encoding="utf-8")


def write_devcontainer(root: Path) -> None:
    """Write only the observable devcontainer entrypoint surface."""
    write_file(
        root,
        ".devcontainer/devcontainer.json",
        json.dumps(
            {
                "name": "${localWorkspaceFolderBasename}-devcontainer",
                "initializeCommand": "AGENT_CANON_DEVCONTAINER_REPO_ROOT=. AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/docker-compose.generated.yml bash vendor/agent-canon/.devcontainer/generate-runtime-compose.sh",
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
    """Write a generated Compose projection for the fixture's workspace layout."""
    topic_root = root.parent.resolve()
    direct_repo = topic_root.name == "workspace"
    repo_target = f"/workspace/{root.name}"
    volumes: list[dict[str, str]] = [
        {
            "type": "bind",
            "source": str(root.resolve() if direct_repo else topic_root),
            "target": repo_target if direct_repo else "/workspace",
        },
    ]
    if duplicate_repo_mount:
        volumes.append(
            {"type": "bind", "source": str(root.resolve()), "target": repo_target}
        )
    environment_lines = (
        [
            "    environment:",
            "      AGENT_CANON_DEPENDENCY_PROFILE: full",
            f"      AGENT_CANON_WORKSPACE_LAYOUT: {'direct-repo' if direct_repo else 'managed-topic'}",
            "      DEVCONTAINER_GPU_MODE: disabled",
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
                '    command: /bin/bash -lc "sleep infinity"',
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


def test_removed_remote_user_contract_is_rejected(tmp_path: Path) -> None:
    """The default devcontainer does not carry a remote-user contract."""
    repo = write_topic_fixture(tmp_path)
    config_path = repo / ".devcontainer/devcontainer.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.update({"remoteUser": "vscode", "updateRemoteUserUID": True})
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_validator(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "default-devcontainer-field-forbidden:remoteUser" in result.stdout
    assert "default-devcontainer-field-forbidden:updateRemoteUserUID" in result.stdout


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
    missing_home = tmp_path / "missing-home"
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "HOME": str(missing_home)},
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
    assert "/etc/project-template/parent-environment.sh" not in compose
    assert "/etc/project-template/zsh/.zshrc" not in compose
    assert "    tmpfs:" not in compose
    assert 'HOME: "/tmp/project-template-home"' not in compose
    assert 'ZDOTDIR: "/etc/project-template/zsh"' not in compose
    assert 'SHELL: "/bin/bash"' not in compose
    assert 'command: /bin/bash -lc "sleep infinity"' in compose
    assert "image: ubuntu:22.04" in compose
    assert 'DEVCONTAINER_GPU_MODE: "disabled"' in compose
    assert "DEVCONTAINER_GPU_REQUEST" not in compose
    assert "NVIDIA_" not in compose
    assert "gpus: all" not in compose
    assert "group_add:" not in compose
    assert "/var/lib/agent-canon/runtime" not in compose


def test_generator_direct_repo_mounts_only_repository_root(tmp_path: Path) -> None:
    """A direct repo layout never exposes sibling repositories under /workspace."""
    repo = tmp_path / "workspace" / "data_download"
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    (repo / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)
    home = tmp_path / "home"
    write_host_zshrc(home)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={"HOME": str(home), **os.environ},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (repo / ".devcontainer/docker-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert f'source: "{repo.resolve()}"' in compose
    assert 'target: "/workspace/data_download"' in compose
    assert f'source: "{repo.parent.resolve()}"' not in compose
    assert 'AGENT_CANON_WORKSPACE_LAYOUT: "direct-repo"' in compose
    assert 'AGENT_CANON_REPOSITORY_ROOT: "/workspace/data_download"' in compose
    assert compose.count("type: bind") == 1
    assert load_container_config_module().validate_generated_compose(repo, None) == []


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
    write_host_zshrc(home)
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
    write_host_zshrc(home)
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


def write_parent_generator_fixture(
    tmp_path: Path,
    *,
    runtime_shell: str = "/bin/zsh",
    dependency_profile: str = "full",
    environment_script: str = "",
    environment_variables: tuple[str, ...] = (),
) -> Path:
    """Create a parent-shaped generator fixture with the zsh contract inputs."""
    repo = tmp_path / "workspace" / "topic" / "parent"
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    (repo / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)
    write_file(repo, ".devcontainer/parent-environment.sh", environment_script)
    variables = ", ".join(json.dumps(item) for item in environment_variables)
    write_file(
        repo,
        ".devcontainer/parent-environment.toml",
        f"variables = [{variables}]\n",
    )
    write_file(repo, "vendor/agent-canon/.keep", "\n")
    write_file(
        repo,
        "docker/packs/default.toml",
        "\n".join(
            [
                "[pack]",
                'name = "parent"',
                'dockerfile = "docker/Dockerfile"',
                'context = "."',
                'image_tag = "parent:fixture"',
                "",
                "[smoke]",
                'shell = "/bin/bash"',
                "commands = []",
                "",
                "[runtime]",
                f'shell = "{runtime_shell}"',
                'workdir = "/workspace"',
                'workspace_mount = "/workspace"',
                f'dependency_profile = "{dependency_profile}"',
                "",
            ]
        ),
    )
    write_file(repo, "docker/Dockerfile", "FROM scratch\n")
    return repo


def test_load_pack_reads_optional_platform_when_present_or_omitted(
    tmp_path: Path,
) -> None:
    """Runtime pack can explicitly set platform or omit it."""
    repo = write_parent_generator_fixture(tmp_path)
    module = load_container_config_module()
    implicit, implicit_findings = module.load_pack(
        repo, repo / "docker/packs/default.toml"
    )
    assert implicit_findings == []
    assert implicit is not None
    assert implicit.platform is None
    assert implicit.dependency_profile == "full"

    explicit_pack = repo / "docker/packs/explicit-platform.toml"
    explicit_pack.write_text(
        "\n".join(
            [
                "[pack]",
                'name = "explicit"',
                'dockerfile = "docker/Dockerfile"',
                'context = "."',
                'image_tag = "explicit:fixture"',
                'platform = "linux/amd64"',
                "",
                "[smoke]",
                "commands = []",
                "",
                "[runtime]",
                'shell = "/bin/bash"',
                'workdir = "/workspace"',
                'workspace_mount = "/workspace"',
                'dependency_profile = "gpu"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    explicit, explicit_findings = module.load_pack(repo, explicit_pack)
    assert explicit_findings == []
    assert explicit is not None
    assert explicit.platform == "linux/amd64"
    assert explicit.dependency_profile == "gpu"


def test_parent_generator_projects_read_only_zsh_contract(tmp_path: Path) -> None:
    """Fresh parent generation creates output state and projects its zsh contract."""
    repo = write_parent_generator_fixture(
        tmp_path,
        environment_script='export PROJECT_REGION="tokyo"\n',
        environment_variables=("PROJECT_REGION",),
    )
    home = tmp_path / "home"
    write_host_zshrc(home)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (repo / ".agent-canon/docker-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert 'target: "/etc/project-template/parent-environment.sh"' in compose
    assert 'target: "/etc/project-template/zsh/.zshrc"' in compose
    assert compose.count("read_only: true") >= 2
    assert 'HOME: "/tmp/project-template-home"' not in compose
    assert 'ZDOTDIR: "/etc/project-template/zsh"' in compose
    assert 'SHELL: "/bin/zsh"' in compose
    assert 'AGENT_CANON_DEPENDENCY_PROFILE: "full"' in compose
    assert "user:" not in compose
    assert "tmpfs:" not in compose
    assert 'command: /bin/zsh -lc "sleep infinity"' in compose
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    assert module.validate_generated_compose(repo, pack) == []


def test_parent_generator_disables_unconfigured_parent_environment(
    tmp_path: Path,
) -> None:
    """A parent with neither optional environment source omits only that mount."""
    repo = write_parent_generator_fixture(tmp_path)
    (repo / ".devcontainer/parent-environment.sh").unlink()
    (repo / ".devcontainer/parent-environment.toml").unlink()
    (repo / ".agent-canon").mkdir()
    home = tmp_path / "home"
    write_host_zshrc(home)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (repo / ".agent-canon/docker-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert 'target: "/etc/project-template/parent-environment.sh"' not in compose
    assert 'target: "/etc/project-template/zsh/.zshrc"' in compose
    module = load_container_config_module()
    assert module.validate_parent_environment(repo) == []


def test_parent_environment_symlinks_to_existing_sources_pass(tmp_path: Path) -> None:
    """File reconstructibility, not the root-view inode type, enables the contract."""
    repo = write_parent_generator_fixture(
        tmp_path,
        environment_script="export PROJECT_REGION=tokyo\n",
        environment_variables=("PROJECT_REGION",),
    )
    source_dir = repo / "parent-config"
    write_file(source_dir, "parent-environment.sh", "export PROJECT_REGION=tokyo\n")
    write_file(source_dir, "parent-environment.toml", 'variables = ["PROJECT_REGION"]\n')
    for name in ("parent-environment.sh", "parent-environment.toml"):
        view = repo / ".devcontainer" / name
        view.unlink()
        view.symlink_to(Path("..") / "parent-config" / name)
    (repo / ".agent-canon").mkdir()
    home = tmp_path / "home"
    write_host_zshrc(home)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    module = load_container_config_module()
    assert module.validate_parent_environment(repo) == []


def test_parent_environment_broken_symlink_fails(tmp_path: Path) -> None:
    """A declared parent environment view must resolve to an actual source file."""
    repo = write_parent_generator_fixture(tmp_path)
    script = repo / ".devcontainer/parent-environment.sh"
    script.unlink()
    script.symlink_to(Path("..") / "parent-config" / "missing.sh")
    home = tmp_path / "home"
    write_host_zshrc(home)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "HOME": str(home)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "parent environment source does not resolve to a file" in result.stderr
    module = load_container_config_module()
    findings = module.validate_parent_environment(repo)
    assert any(finding.detail == "missing-target" for finding in findings)


def test_parent_compose_rejects_service_user_and_home_tmpfs(tmp_path: Path) -> None:
    """Parent Compose keeps the default root runtime free of custom identity mapping."""
    repo = write_parent_generator_fixture(tmp_path)
    (repo / ".agent-canon").mkdir()
    home = tmp_path / "home"
    write_host_zshrc(home)
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    compose_path = repo / ".agent-canon/docker-compose.generated.yml"
    malformed = compose_path.read_text(encoding="utf-8").replace(
        "    build:\n",
        '    user: "1000:1000"\n'
        "    tmpfs:\n"
        "      - /tmp/project-template-home:uid=1000,gid=1000,mode=700\n"
        "    build:\n",
        1,
    )
    compose_path.write_text(malformed, encoding="utf-8")
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    details = {
        finding.detail for finding in module.validate_generated_compose(repo, pack)
    }
    assert "default-service-user-forbidden" in details
    assert "default-home-tmpfs-forbidden" in details


def test_generator_rejects_runtime_shell_arguments(tmp_path: Path) -> None:
    """Runtime shell values with arguments fail before Compose interpolation."""
    repo = write_parent_generator_fixture(tmp_path, runtime_shell="/bin/zsh -l")
    home = tmp_path / "home"
    write_host_zshrc(home)
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "HOME": str(home)},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "runtime.shell must be one absolute executable path" in result.stderr
    module = load_container_config_module()
    pack, findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack is None
    assert any(
        finding.detail == "runtime.shell-must-be-absolute-executable-path"
        for finding in findings
    )


def test_parent_generator_uses_host_zshrc_expression_without_host_probe(
    tmp_path: Path,
) -> None:
    """Fresh-clone generation checks the host mount contract, not host state."""
    repo = write_parent_generator_fixture(tmp_path)
    (repo / ".agent-canon").mkdir()
    home = tmp_path / "home"
    home.mkdir()

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    compose_path = repo / ".agent-canon/docker-compose.generated.yml"
    compose = compose_path.read_text(encoding="utf-8")
    assert 'source: "${HOME}/.zshrc"' in compose
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    assert module.validate_generated_compose(repo, pack) == []

    malformed = compose.replace(
        "      - type: bind\n"
        '        source: "${HOME}/.zshrc"\n'
        '        target: "/etc/project-template/zsh/.zshrc"\n'
        "        read_only: true",
        "      - type: volume\n"
        '        source: "/tmp/guessed-zshrc"\n'
        '        target: "/etc/project-template/zsh/.zshrc"\n'
        "        read_only: false",
    )
    compose_path.write_text(malformed, encoding="utf-8")
    details = {
        finding.detail for finding in module.validate_generated_compose(repo, pack)
    }
    assert "host-zshrc-mount-type-must-be-bind" in details
    assert "host-zshrc-source-must-be-${HOME}/.zshrc" in details
    assert (
        "parent-environment-mount-read-only:/etc/project-template/zsh/.zshrc" in details
    )


def test_parent_environment_validator_is_static_and_ordered(tmp_path: Path) -> None:
    """Parent environment validation never executes shell lines and preserves order."""
    module = load_container_config_module()
    (tmp_path / "vendor" / "agent-canon").mkdir(parents=True)
    write_file(
        tmp_path,
        ".devcontainer/parent-environment.sh",
        'export PROJECT_REGION="tokyo"\nexport PROJECT_TOKEN=value\n',
    )
    write_file(
        tmp_path,
        ".devcontainer/parent-environment.toml",
        'variables = ["PROJECT_REGION", "PROJECT_TOKEN"]\n',
    )
    assert module.validate_parent_environment(tmp_path) == []

    marker = tmp_path / "executed"
    write_file(
        tmp_path,
        ".devcontainer/parent-environment.sh",
        f"touch {marker}\n",
    )
    findings = module.validate_parent_environment(tmp_path)
    assert not marker.exists()
    assert any("invalid-export-line" in finding.detail for finding in findings)


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
                'custom-visualizer @ https://example.invalid/custom-visualizer.whl#sha256=abc123 ; python_version >= "3.11"',
                "",
            ]
        ),
    )

    assert module.validate_requirements(tmp_path) == []


def test_validate_requirements_rejects_invalid_direct_reference_boundaries(
    tmp_path: Path,
) -> None:
    """URL references cannot also carry version specifiers or malformed syntax."""
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
                "custom-visualizer @ https://example.invalid/custom-visualizer.whl ==1",
                "custom-visualizer @ https://example.invalid/custom-visualizer.whl#sha256=abc123 ==1",
                "not a requirement",
                "",
            ]
        ),
    )

    findings = module.validate_requirements(tmp_path)

    assert [finding.detail for finding in findings] == [
        "invalid-line:7",
        "invalid-line:8",
        "invalid-line:9",
    ]


def test_validate_requirements_projects_every_parse_error_to_line_only(
    tmp_path: Path,
) -> None:
    """All canonical parser errors retain only the legacy line finding detail."""
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
                "--index-url https://pypi.org/simple",
                "--hash=sha256:" + "a" * 64,
                "package==1.0 \\",
                "    --hash=sha256:short",
                "package==1.0 \\",
                "    not-a-hash",
                "not a requirement",
                "package==1.0 \\",
                "",
            ]
        ),
    )

    findings = module.validate_requirements(tmp_path)

    assert [finding.detail for finding in findings] == [
        "invalid-line:7",
        "invalid-line:8",
        "invalid-line:10",
        "invalid-line:12",
        "invalid-line:13",
        "invalid-line:14",
    ]
    assert all("requirement" not in finding.detail for finding in findings)
