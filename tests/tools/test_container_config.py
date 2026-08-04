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
DOCKERFILE = PROJECT_ROOT / ".devcontainer" / "Dockerfile"
POST_CREATE_ENTRYPOINT = PROJECT_ROOT / ".devcontainer" / "post-create-entrypoint.sh"


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


def write_host_zshrc_symlink(home: Path, content: str = "# fixture zshrc\n") -> Path:
    """Write a host zshrc symlink and return its regular canonical target."""
    home.mkdir(parents=True, exist_ok=True)
    target = home / "real-zshrc"
    target.write_text(content, encoding="utf-8")
    (home / ".zshrc").symlink_to(target)
    return target.resolve()


def write_host_zsh_directory_symlink(home: Path) -> Path:
    """Write a host zsh directory symlink and return its canonical target."""
    home.mkdir(parents=True, exist_ok=True)
    target = home / "real zsh"
    target.mkdir()
    (target / "zsh-autosuggestions.zsh").write_text("# fixture\n", encoding="utf-8")
    (target / "zsh-syntax-highlighting.zsh").write_text("# fixture\n", encoding="utf-8")
    (home / ".zsh").symlink_to(target)
    return target.resolve()


def write_devcontainer(root: Path) -> None:
    """Write only the observable devcontainer entrypoint surface."""
    write_file(
        root,
        ".devcontainer/devcontainer.json",
        json.dumps(
            {
                "name": "${localWorkspaceFolderBasename}-devcontainer",
                "initializeCommand": "AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/docker-compose.generated.yml python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/generate-runtime-compose.sh",
                "dockerComposeFile": "../.agent-canon/docker-compose.generated.yml",
                "service": "workspace",
                "containerUser": "project",
                "remoteUser": "project",
                "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",
                "postCreateCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-create-entrypoint.sh /workspace/${localWorkspaceFolderBasename}",
                "postAttachCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-attach.sh",
            },
            indent=2,
        )
        + "\n",
    )
    for name in ("post-create.sh", "post-create-entrypoint.sh", "post-attach.sh"):
        content = (
            POST_CREATE_ENTRYPOINT.read_text(encoding="utf-8")
            if name == "post-create-entrypoint.sh"
            else "#!/usr/bin/env bash\n"
        )
        write_file(root, f".devcontainer/{name}", content)
        (root / ".devcontainer" / name).chmod(0o755)
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
            "      AGENT_CANON_RUNTIME_ROUTE: CONTAINER_LOCAL",
            "      AGENT_CANON_CODEX_SESSION_ROOT: /home/project/.codex/sessions",
            "      AGENT_CANON_SECRET_MOUNT: /mnt/agent-canon-secrets",
            f"      AGENT_CANON_WORKSPACE_LAYOUT: {'direct-repo' if direct_repo else 'managed-topic'}",
            "      DEVCONTAINER_GPU_MODE: disabled",
            "      AGENT_CANON_WORKSPACE_ROOT: /workspace",
            f"      AGENT_CANON_REPOSITORY_ROOT: {repo_target}",
            f"      DEPENDENCY_MODULE_CONTAINER_SOURCE: {json.dumps(str(root.resolve() if direct_repo else topic_root))}",
            f"      DEPENDENCY_MODULE_CONTAINER_TARGET: {json.dumps(repo_target if direct_repo else '/workspace')}",
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
                "    platform: linux/amd64",
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


def test_noncanonical_remote_user_contract_is_rejected(tmp_path: Path) -> None:
    """The devcontainer runtime identity is fixed to the canonical project user."""
    repo = write_topic_fixture(tmp_path)
    config_path = repo / ".devcontainer/devcontainer.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.update({"remoteUser": "vscode"})
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = run_validator(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "remoteUser-expected:project" in result.stdout


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
    write_file(repo, ".devcontainer/Dockerfile", DOCKERFILE.read_text(encoding="utf-8"))
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
    assert 'AGENT_CANON_CODEX_SESSION_ROOT: "/home/project/.codex/sessions"' in compose
    assert "/etc/project-template/parent-environment.sh" not in compose
    assert "/etc/project-template/zsh/.zshrc" not in compose
    assert "    tmpfs:" not in compose
    assert 'HOME: "/tmp/project-template-home"' not in compose
    assert 'ZDOTDIR: "/etc/project-template/zsh"' not in compose
    assert 'SHELL: "/bin/bash"' not in compose
    assert 'command: /bin/bash -lc "sleep infinity"' in compose
    assert "dockerfile: .devcontainer/Dockerfile" in compose
    assert 'PROJECT_UID: "' in compose
    assert 'PROJECT_GID: "' in compose
    assert 'DEVCONTAINER_GPU_MODE: "disabled"' in compose
    assert 'DEPENDENCY_MODULE_CONTAINER_SOURCE:' in compose
    assert 'DEPENDENCY_MODULE_CONTAINER_TARGET: "/workspace"' in compose
    assert "DEVCONTAINER_GPU_REQUEST" not in compose
    assert "NVIDIA_" not in compose
    assert "gpus: all" not in compose
    assert "group_add:" not in compose
    assert "/var/lib/agent-canon/runtime" not in compose


def test_generator_treats_workspace_topic_slug_as_managed(tmp_path: Path) -> None:
    """A managed topic may itself be named workspace without becoming direct-repo."""
    repo = tmp_path / "workspace" / "workspace" / "agent-canon"
    write_devcontainer(repo)
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    write_file(repo, ".devcontainer/Dockerfile", DOCKERFILE.read_text(encoding="utf-8"))
    (repo / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "HOME": str(tmp_path / "missing-home")},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (repo / ".devcontainer/docker-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert 'AGENT_CANON_WORKSPACE_LAYOUT: "managed-topic"' in compose
    assert f'source: "{repo.parent.resolve()}"' in compose
    assert 'target: "/workspace"' in compose
    assert 'target: "/workspace/agent-canon"' not in compose
    assert load_container_config_module().validate_generated_compose(repo, None) == []


def test_generator_direct_repo_mounts_only_repository_root(tmp_path: Path) -> None:
    """A direct repo layout never exposes sibling repositories under /workspace."""
    repo = tmp_path / "workspace" / "data_download"
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    write_file(repo, ".devcontainer/Dockerfile", DOCKERFILE.read_text(encoding="utf-8"))
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
    assert f'DEPENDENCY_MODULE_CONTAINER_SOURCE: "{repo.resolve()}"' in compose
    assert 'DEPENDENCY_MODULE_CONTAINER_TARGET: "/workspace/data_download"' in compose
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
    runtime_mounts: tuple[str, ...] = (),
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
    runtime_mounts_line = (
        f"mounts = {json.dumps(list(runtime_mounts))}" if runtime_mounts else ""
    )
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
                'platform = "linux/amd64"',
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
                runtime_mounts_line,
                "",
            ]
        ),
    )
    write_file(repo, "docker/Dockerfile", "FROM scratch\n")
    return repo


def test_load_pack_reads_optional_platform_when_present_or_omitted(
    tmp_path: Path,
) -> None:
    """Runtime pack can explicitly set the canonical platform."""
    repo = write_parent_generator_fixture(tmp_path)
    module = load_container_config_module()
    implicit, implicit_findings = module.load_pack(
        repo, repo / "docker/packs/default.toml"
    )
    assert implicit_findings == []
    assert implicit is not None
    assert implicit.platform == "linux/amd64"
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
            "PROJECT_UID": "1234",
            "PROJECT_GID": "2345",
            "AGENT_CANON_OPTIONAL_MOUNTS": "host-zshrc",
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
    assert 'target: "/home/project/.zshrc"' in compose
    assert compose.count("read_only: true") == 1
    assert 'HOME: "/home/project"' in compose
    assert "ZDOTDIR:" not in compose
    assert 'SHELL: "/bin/zsh"' in compose
    assert 'AGENT_CANON_DEPENDENCY_PROFILE: "full"' in compose
    assert 'AGENT_CANON_CODEX_SESSION_ROOT: "/home/project/.codex/sessions"' in compose
    assert 'user: "1234:2345"' in compose
    assert 'PROJECT_USER:' not in compose
    assert 'PROJECT_UID: "1234"' in compose
    assert 'PROJECT_GID: "2345"' in compose
    assert 'command: /bin/zsh -lc "sleep infinity"' in compose
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    assert module.validate_generated_compose(repo, pack) == []


def test_parent_generator_resolves_symlink_host_zshrc(tmp_path: Path) -> None:
    """A host zshrc symlink binds its canonical regular target read-only."""
    repo = write_parent_generator_fixture(tmp_path)
    (repo / ".agent-canon").mkdir()
    home = tmp_path / "home with spaces"
    target = write_host_zshrc_symlink(home)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "PROJECT_UID": "1000",
            "PROJECT_GID": "1000",
            "AGENT_CANON_OPTIONAL_MOUNTS": "host-zshrc",
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
    assert f'source: "{target}"' in compose
    assert 'target: "/home/project/.zshrc"' in compose
    assert 'target: "/home/project/.zsh"' not in compose
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    assert module.validate_generated_compose(repo, pack) == []


def test_parent_generator_resolves_symlink_host_zsh_directory(tmp_path: Path) -> None:
    """A host zsh directory symlink binds its canonical directory read-only."""
    repo = write_parent_generator_fixture(tmp_path)
    (repo / ".agent-canon").mkdir()
    home = tmp_path / "home with spaces"
    target = write_host_zsh_directory_symlink(home)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "PROJECT_UID": "1000",
            "PROJECT_GID": "1000",
            "AGENT_CANON_OPTIONAL_MOUNTS": "host-zshrc",
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
    assert f'source: "{target}"' in compose
    assert 'target: "/home/project/.zsh"' in compose
    assert 'target: "/home/project/.zshrc"' not in compose
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    assert module.validate_generated_compose(repo, pack) == []


def test_parent_generator_skips_invalid_optional_host_zsh_paths(
    tmp_path: Path,
) -> None:
    """Missing, broken, and wrong-type optional zsh paths are omitted."""
    cases = ("missing", "broken-symlink", "directory", "regular-file")
    for case in cases:
        case_root = tmp_path / case
        repo = write_parent_generator_fixture(case_root)
        (repo / ".agent-canon").mkdir()
        home = case_root / "home"
        home.mkdir(parents=True)
        if case == "broken-symlink":
            (home / ".zshrc").symlink_to(home / "missing-zshrc")
            (home / ".zsh").symlink_to(home / "missing-zsh")
        elif case == "directory":
            (home / ".zshrc").mkdir()
        elif case == "regular-file":
            (home / ".zsh").write_text("# not a directory\n", encoding="utf-8")

        result = subprocess.run(
            ["bash", ".devcontainer/generate-runtime-compose.sh"],
            cwd=repo,
            env={
                **os.environ,
                "HOME": str(home),
                "PROJECT_UID": "1000",
                "PROJECT_GID": "1000",
                "AGENT_CANON_OPTIONAL_MOUNTS": "host-zshrc",
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
        assert 'target: "/home/project/.zshrc"' not in compose
        assert 'target: "/home/project/.zsh"' not in compose


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
            "PROJECT_UID": "1000",
            "PROJECT_GID": "1000",
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
    assert 'target: "/home/project/.zshrc"' not in compose
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
            "PROJECT_UID": "1000",
            "PROJECT_GID": "1000",
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    module = load_container_config_module()
    assert module.validate_parent_environment(repo) == []


def test_parent_environment_broken_symlink_does_not_block_default_generation(
    tmp_path: Path,
) -> None:
    """Legacy parent environment state is not a default generator dependency."""
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

    assert result.returncode == 0, result.stdout + result.stderr
    module = load_container_config_module()
    findings = module.validate_parent_environment(repo)
    assert any(finding.detail == "missing-target" for finding in findings)


def test_parent_compose_rejects_root_user_and_missing_build_args(tmp_path: Path) -> None:
    """Parent Compose requires a non-root runtime identity and reproducible build args."""
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
    malformed = (
        compose_path.read_text(encoding="utf-8")
        .replace('user: "1000:1000"', 'user: "0:0"')
        .replace('        PROJECT_GID: "1000"\n', "")
    )
    compose_path.write_text(malformed, encoding="utf-8")
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    details = {
        finding.detail for finding in module.validate_generated_compose(repo, pack)
    }
    assert "default-user-must-have-positive-uid-gid" in details
    assert "build-arg-PROJECT_GID-must-be-positive-integer" in details


def test_generator_rejects_public_project_user_override(tmp_path: Path) -> None:
    """The canonical username cannot be overridden through the generator environment."""
    repo = write_parent_generator_fixture(tmp_path)
    (repo / ".agent-canon").mkdir()
    home = tmp_path / "home"
    write_host_zshrc(home)
    environment = {**os.environ, "HOME": str(home), "PROJECT_USER": "alice"}
    environment.pop("AGENT_CANON_RUNTIME_GID", None)
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "DEVCONTAINER_IDENTITY_ERROR=PROJECT_USER_OVERRIDE_FORBIDDEN" in result.stderr


def test_generator_rejects_zero_project_uid_or_gid(tmp_path: Path) -> None:
    """Project UID and GID must both be positive decimal integers."""
    for field, value in (("PROJECT_UID", "0"), ("PROJECT_GID", "0")):
        case_root = tmp_path / field
        repo = write_parent_generator_fixture(case_root)
        (repo / ".agent-canon").mkdir()
        home = case_root / "home"
        write_host_zshrc(home)
        environment = {
            **os.environ,
            "HOME": str(home),
            "PROJECT_UID": "1234",
            "PROJECT_GID": "2345",
            field: value,
        }
        environment.pop("PROJECT_USER", None)
        environment.pop("AGENT_CANON_RUNTIME_GID", None)
        result = subprocess.run(
            ["bash", ".devcontainer/generate-runtime-compose.sh"],
            cwd=repo,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "DEVCONTAINER_IDENTITY_ERROR=PROJECT_IDS_MUST_BE_POSITIVE_DECIMAL" in result.stderr


def test_parent_validator_rejects_zero_uid_or_gid(tmp_path: Path) -> None:
    """Generated Compose readback rejects zero project IDs."""
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
            "PROJECT_UID": "1234",
            "PROJECT_GID": "2345",
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    compose_path = repo / ".agent-canon/docker-compose.generated.yml"
    valid = compose_path.read_text(encoding="utf-8")
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None

    malformed_cases = (
        (
            valid.replace('user: "1234:2345"', 'user: "0:2345"').replace(
                'PROJECT_UID: "1234"', 'PROJECT_UID: "0"'
            ),
            {"default-user-must-have-positive-uid-gid", "build-arg-PROJECT_UID-must-be-positive-integer"},
        ),
        (
            valid.replace('user: "1234:2345"', 'user: "1234:0"').replace(
                'PROJECT_GID: "2345"', 'PROJECT_GID: "0"'
            ),
            {"default-user-must-have-positive-uid-gid", "build-arg-PROJECT_GID-must-be-positive-integer"},
        ),
    )
    for malformed, expected in malformed_cases:
        compose_path.write_text(malformed, encoding="utf-8")
        details = {
            finding.detail for finding in module.validate_generated_compose(repo, pack)
        }
        assert expected.issubset(details)


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


def test_generator_rejects_pack_override_of_runtime_route(tmp_path: Path) -> None:
    """Pack-owned env cannot override the generated container-local route."""
    repo = write_parent_generator_fixture(tmp_path)
    pack = repo / "docker/packs/default.toml"
    pack.write_text(
        pack.read_text(encoding="utf-8")
        + '\nenv = ["AGENT_CANON_RUNTIME_ROUTE=MANAGED_CONTAINER"]\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "PROJECT_UID": "1234", "PROJECT_GID": "2345"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert (
        "runtime.env cannot override reserved key: AGENT_CANON_RUNTIME_ROUTE"
        in result.stderr
    )


def test_container_config_requires_executable_resolver_entrypoint(tmp_path: Path) -> None:
    """The public post-create resolver must remain executable in a fresh checkout."""
    repo = write_topic_fixture(tmp_path)
    entrypoint = repo / ".devcontainer/post-create-entrypoint.sh"
    entrypoint.chmod(0o644)
    module = load_container_config_module()

    findings = module.validate_post_create(repo)

    assert any(
        finding.detail == "not-executable"
        and finding.path.endswith("post-create-entrypoint.sh")
        for finding in findings
    )


def test_container_config_requires_resolver_entrypoint_contract(tmp_path: Path) -> None:
    """The executable entrypoint must dispatch shared setup before parent setup."""
    repo = write_topic_fixture(tmp_path)
    entrypoint = repo / ".devcontainer/post-create-entrypoint.sh"
    entrypoint.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    module = load_container_config_module()

    findings = module.validate_post_create(repo)

    assert any(
        finding.detail.startswith("resolver-entrypoint-missing:")
        for finding in findings
    )


def test_parent_generator_omits_absent_host_zshrc_without_probe(
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
    assert 'source: "${HOME}/.zshrc"' not in compose
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    assert module.validate_generated_compose(repo, pack) == []


def test_default_generator_omits_all_optional_host_files_and_sockets(
    tmp_path: Path,
) -> None:
    """Default generation is independent of host credentials, sockets, and state."""
    repo = write_parent_generator_fixture(tmp_path)
    (repo / ".agent-canon").mkdir()
    home = tmp_path / "home"
    (home / ".config" / "gh").mkdir(parents=True)
    (home / ".ssh").mkdir()
    write_host_zshrc(home)
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "SSH_AUTH_SOCK": "/tmp/not-a-socket",
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
    volume_section = compose.split("    environment:", 1)[0]
    for marker in (".zshrc", "/mnt/git", ".config/gh", "/.ssh", "/ssh-agent", "/mnt/agent-canon-secrets"):
        assert marker not in volume_section
    assert 'AGENT_CANON_RUNTIME_ROUTE: "CONTAINER_LOCAL"' in compose
    assert 'AGENT_CANON_SECRET_MOUNT: "/mnt/agent-canon-secrets"' in compose


def test_generator_rejects_raw_runtime_mounts_before_compose_output(
    tmp_path: Path,
) -> None:
    """The shared generator rejects pack runtime.mounts before emitting host binds."""
    repo = write_parent_generator_fixture(
        tmp_path,
        runtime_mounts=("/tmp/host:/tmp/host",),
    )
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "PROJECT_UID": "1234", "PROJECT_GID": "2345"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "rejects raw runtime.mounts" in result.stderr


def test_generator_rejects_custom_secret_target(tmp_path: Path) -> None:
    """The optional secret profile has one canonical container target."""
    repo = write_parent_generator_fixture(tmp_path)
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir()
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "AGENT_CANON_OPTIONAL_MOUNTS": "host-secrets",
            "AGENT_CANON_SECRET_DIR": str(secret_dir),
            "AGENT_CANON_SECRET_MOUNT": "/custom-secrets",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "secret target is fixed at /mnt/agent-canon-secrets" in result.stderr


def test_generated_compose_platform_is_read_back_exactly(tmp_path: Path) -> None:
    """The runtime platform projection is required to remain linux/amd64."""
    repo = write_parent_generator_fixture(tmp_path)
    (repo / ".agent-canon").mkdir()
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "PROJECT_UID": "1234",
            "PROJECT_GID": "2345",
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    compose_path = repo / ".agent-canon/docker-compose.generated.yml"
    compose_path.write_text(
        compose_path.read_text(encoding="utf-8").replace(
            "    platform: linux/amd64", "    platform: linux/arm64"
        ),
        encoding="utf-8",
    )
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    assert any(
        finding.detail == "compose-platform-expected:linux/amd64"
        for finding in module.validate_generated_compose(repo, pack)
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
