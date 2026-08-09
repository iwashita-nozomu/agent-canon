"""Focused semantic checks for the VS Code devcontainer contract."""

# @dependency-start
# contract test
# responsibility Verifies topic-root Compose mounts, selected repo paths, and retired VS Code projections.
# upstream design ../../documents/rule/dependency-module-changes.md topic-root mount policy
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md parent layout and runtime shell contract
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md explicit GPU-admission selector and scenario validation
# upstream implementation ../../tools/ci/container_config.py semantic devcontainer checker
# upstream implementation ../../.devcontainer/devcontainer.json selects the topic-root Compose generator
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "ci" / "container_config.py"
GENERATOR = PROJECT_ROOT / ".devcontainer" / "generate-runtime-compose.sh"
DOCKERFILE = PROJECT_ROOT / ".devcontainer" / "Dockerfile"
POST_CREATE_ENTRYPOINT = PROJECT_ROOT / ".devcontainer" / "post-create-entrypoint.sh"
GPU_ADMISSION_SELECTOR = (
    PROJECT_ROOT / ".devcontainer" / "gpu-admission" / "devcontainer.json"
)
ROOTLESS_SELECTOR = PROJECT_ROOT / ".devcontainer" / "rootless" / "devcontainer.json"
GPU_ADMISSION_ORCHESTRATOR = PROJECT_ROOT / ".devcontainer" / "gpu-admission.sh"
POST_CREATE_COMMAND = (
    "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec "
    ".devcontainer/post-create-entrypoint.sh "
    "/workspace/${localWorkspaceFolderBasename}"
)
PARENT_POST_CREATE_COMMAND = POST_CREATE_COMMAND


def write_fake_docker_probe(bin_dir: Path, *, rootless: bool) -> Path:
    """Create a test-only Docker CLI returning official SecurityOptions."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    docker = bin_dir / "docker"
    security_options = '["name=rootless"]' if rootless else '["name=seccomp"]'
    docker.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = info ]; then\n'
        f"  printf '%s\\n' '{security_options}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return bin_dir


@pytest.fixture(autouse=True)
def rootful_docker_probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep project generator fixtures deterministic on a rootless host."""
    probe_bin = write_fake_docker_probe(tmp_path / "rootful-docker", rootless=False)
    monkeypatch.setenv("PATH", f"{probe_bin}:{os.environ['PATH']}")


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


def write_linked_data_root_symlink(repo: Path, tmp_path: Path) -> tuple[str, Path]:
    """Create one repository symlink and a temporary canonical directory."""
    target = tmp_path / "linked-data-target"
    target.mkdir(parents=True, exist_ok=True)
    link = repo / "link" / "msm_data_root"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)
    return link.relative_to(repo).as_posix(), target


def write_devcontainer(root: Path) -> None:
    """Write only the observable devcontainer entrypoint surface."""
    write_file(
        root,
        ".devcontainer/devcontainer.json",
        json.dumps(
            {
                "name": "${localWorkspaceFolderBasename}-devcontainer",
                "initializeCommand": "AGENT_CANON_RUNTIME_IDENTITY_MODE=project AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/docker-compose.generated.yml python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/generate-runtime-compose.sh",
                "dockerComposeFile": "../.agent-canon/docker-compose.generated.yml",
                "service": "workspace",
                "containerUser": "project",
                "remoteUser": "project",
                "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",
                "postCreateCommand": POST_CREATE_COMMAND,
                "postAttachCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-attach.sh",
            },
            indent=2,
        )
        + "\n",
    )
    for name in (
        "post-create.sh",
        "post-create-entrypoint.sh",
        "post-attach.sh",
    ):
        if name == "post-create-entrypoint.sh":
            content = POST_CREATE_ENTRYPOINT.read_text(encoding="utf-8")
        else:
            content = "#!/usr/bin/env bash\n"
        write_file(root, f".devcontainer/{name}", content)
        (root / ".devcontainer" / name).chmod(0o755)
    write_file(
        root,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    (root / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)
    write_file(
        root,
        ".devcontainer/gpu-admission/devcontainer.json",
        GPU_ADMISSION_SELECTOR.read_text(encoding="utf-8"),
    )
    write_file(
        root,
        ".devcontainer/rootless/devcontainer.json",
        ROOTLESS_SELECTOR.read_text(encoding="utf-8"),
    )
    write_file(
        root,
        ".devcontainer/gpu-admission.sh",
        GPU_ADMISSION_ORCHESTRATOR.read_text(encoding="utf-8"),
    )
    (root / ".devcontainer/gpu-admission.sh").chmod(0o755)


def write_compose(
    root: Path,
    *,
    duplicate_repo_mount: bool = False,
    include_runtime_environment: bool = True,
) -> None:
    """Write a generated Compose projection for the fixture's workspace layout."""
    topic_root = root.parent.resolve()
    direct_repo = topic_root.parent.name != "workspace"
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
            "      AGENT_CANON_RUNTIME_ROUTE: CONTAINER_LOCAL",
            "      AGENT_CANON_CODEX_SESSION_ROOT: /home/project/.codex/sessions",
            "      AGENT_CANON_RUNTIME_IDENTITY_MODE: project",
            "      HOME: /home/project",
            "      SHELL: /bin/bash",
            "      AGENT_CANON_CONTAINER_USER: project",
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
                f"    user: \"{os.getuid()}:{os.getgid()}\"",
                "    build:",
                "      context: ..",
                "      dockerfile: docker/Dockerfile",
                "      args:",
                f"        PROJECT_UID: \"{os.getuid()}\"",
                f"        PROJECT_GID: \"{os.getgid()}\"",
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
        "tools/agent-canon/agent_tools/dependency_module_change.py",
        "#!/usr/bin/env python3\n",
    )
    return repo


def write_vscode_source(root: Path, relative: str = ".vscode") -> None:
    """Write regular files for the four standalone VS Code surfaces."""
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


def test_validator_rejects_missing_dependency_module_change_in_parent_mode(tmp_path: Path) -> None:
    """Parent mode requires the canonical dependency module path when module checks are enabled."""
    repo = write_topic_fixture(tmp_path)
    (repo / "tools" / "agent-canon" / "agent_tools" / "dependency_module_change.py").unlink()

    result = run_validator(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "required-for-devcontainer-dependency-check" in result.stdout


def test_gpu_admission_selector_isolated_from_default_selector() -> None:
    """The opt-in selector owns a distinct config and generated Compose identity."""
    default = json.loads(
        (PROJECT_ROOT / ".devcontainer" / "devcontainer.json").read_text(
            encoding="utf-8"
        )
    )
    profile = json.loads(GPU_ADMISSION_SELECTOR.read_text(encoding="utf-8"))

    assert "gpu-admission" not in default["name"]
    assert "gpu-admission" not in default["dockerComposeFile"]
    assert "gpu-admission" in profile["name"]
    assert profile["dockerComposeFile"] != default["dockerComposeFile"]
    assert "features" not in default
    assert "features" not in profile
    assert load_container_config_module().validate_gpu_admission_selector(PROJECT_ROOT) == []


def test_standalone_image_context_is_explicit_and_source_owned() -> None:
    """The standalone build admits only the dependency manifest and engine."""
    module = load_container_config_module()

    assert module.validate_standalone_docker_context(PROJECT_ROOT) == []
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY . /opt/agent-canon" not in dockerfile
    assert "vendor/agent-canon" not in dockerfile
    assert "--workspace /opt/agent-canon --vendor-root /opt/agent-canon" in " ".join(
        dockerfile.split()
    )


def test_standalone_image_context_rejects_broad_copy_and_leak_allowlist(
    tmp_path: Path,
) -> None:
    """A context fixture cannot admit unrelated source, docs, or test files."""
    module = load_container_config_module()
    root = tmp_path / "standalone"
    write_file(root, "documents/forbidden-secret.txt", "fixture secret\n")
    write_file(
        root,
        ".dockerignore",
        "\n".join(
            (
                "**",
                "!.devcontainer/",
                "!.devcontainer/Dockerfile",
                "!.devcontainer/dependencies.toml",
                "!tools/",
                "!tools/agent_tools/",
                "!tools/agent_tools/devcontainer_dependencies.py",
                "!documents/forbidden-secret.txt",
                "",
            )
        ),
    )
    write_file(
        root,
        ".devcontainer/Dockerfile",
        """FROM ubuntu:22.04
COPY . /opt/agent-canon
RUN image-install --workspace /opt/agent-canon --vendor-root /opt/agent-canon
""",
    )

    details = {
        finding.detail
        for finding in module.validate_standalone_docker_context(root)
    }
    assert "standalone-context-copy-dot-forbidden" in details
    assert "standalone-context-allowlist-mismatch" in details
    assert any(
        detail.startswith("standalone-context-required-copy-missing:")
        for detail in details
    )


def test_post_create_uses_shared_lifecycle() -> None:
    """Both selectors use the shared post-create lifecycle."""
    for config_path in (
        PROJECT_ROOT / ".devcontainer" / "devcontainer.json",
        GPU_ADMISSION_SELECTOR,
        ROOTLESS_SELECTOR,
    ):
        config = json.loads(config_path.read_text(encoding="utf-8"))
        command = config["postCreateCommand"]

        assert command == POST_CREATE_COMMAND
        assert "post-create-entrypoint.sh" in command


def test_lifecycle_scripts_validate_selected_identity_and_workspace_writability() -> None:
    """Lifecycle scripts own the exact identity marker and write probe contract."""
    post_create = (PROJECT_ROOT / ".devcontainer/post-create.sh").read_text(
        encoding="utf-8"
    )
    post_attach = (PROJECT_ROOT / ".devcontainer/post-attach.sh").read_text(
        encoding="utf-8"
    )
    for script in (post_create, post_attach):
        assert 'runtime_identity_mode="${AGENT_CANON_RUNTIME_IDENTITY_MODE:-}"' in script
        assert "rootless-root" in script
        assert 'expected_runtime_home="/root"' in script
        assert "workspace_write_probe" in script
        assert "mktemp" in script
    assert "post-create rootless-root identity must be uid 0" in post_create
    assert "rootless-root-identity-not-uid-0" in post_attach


def test_parent_layout_requires_language_runtime_before_shared_lifecycle(
    tmp_path: Path,
) -> None:
    """Parent selectors require the shared post-create entrypoint."""
    module = load_container_config_module()
    default = json.loads(
        (PROJECT_ROOT / ".devcontainer/devcontainer.json").read_text(
            encoding="utf-8"
        )
    )
    default["postCreateCommand"] = PARENT_POST_CREATE_COMMAND
    assert module.validate_devcontainer_json(default, parent_layout=True) == []
    default["postCreateCommand"] = POST_CREATE_COMMAND
    assert module.validate_devcontainer_json(default, parent_layout=True) == []

    parent = tmp_path / "parent"
    (parent / "vendor/agent-canon").mkdir(parents=True)
    profile = json.loads(GPU_ADMISSION_SELECTOR.read_text(encoding="utf-8"))
    profile["postCreateCommand"] = PARENT_POST_CREATE_COMMAND
    write_file(
        parent,
        ".devcontainer/gpu-admission/devcontainer.json",
        json.dumps(profile),
    )
    gpu_findings = module.validate_gpu_admission_selector(parent)
    assert not any("postCreateCommand-expected" in item.detail for item in gpu_findings)

    profile["postCreateCommand"] = POST_CREATE_COMMAND
    write_file(
        parent,
        ".devcontainer/gpu-admission/devcontainer.json",
        json.dumps(profile),
    )
    gpu_findings = module.validate_gpu_admission_selector(parent)
    assert not any("postCreateCommand-expected" in item.detail for item in gpu_findings)


def test_gpu_admission_selector_is_mandatory(tmp_path: Path) -> None:
    """A parent devcontainer surface cannot silently omit the explicit selector."""
    repo = write_topic_fixture(tmp_path)
    (repo / ".devcontainer/gpu-admission/devcontainer.json").unlink()

    findings = load_container_config_module().validate_gpu_admission_selector(repo)

    assert {finding.detail for finding in findings} == {
        "explicit-profile-selector-required"
    }


def test_default_lifecycle_entrypoints_are_mandatory(tmp_path: Path) -> None:
    """The exact default lifecycle remains required without source-text bans."""
    repo = write_topic_fixture(tmp_path)
    (repo / ".devcontainer/post-attach.sh").unlink()

    findings = load_container_config_module().validate_default_lifecycle_scripts(repo)

    assert {(finding.path, finding.detail) for finding in findings} == {
        (".devcontainer/post-attach.sh", "missing")
    }


def test_missing_generated_compose_is_a_required_scenario_finding(
    tmp_path: Path,
) -> None:
    """A selected generated-Compose scenario never passes by absence."""
    repo = write_topic_fixture(tmp_path)
    missing = repo / ".agent-canon/missing-profile.yml"

    findings = load_container_config_module().validate_generated_compose(
        repo,
        None,
        profile="gpu-admission",
        compose_path=missing,
    )

    assert {finding.detail for finding in findings} == {
        "gpu-admission-scenario-compose-required"
    }


def test_generator_scenarios_require_both_compose_outputs(tmp_path: Path) -> None:
    """A generator that exits successfully without output fails both scenarios."""
    repo = write_topic_fixture(tmp_path)
    (repo / "docker/packs").mkdir(parents=True)
    generator = repo / ".devcontainer/generate-runtime-compose.sh"
    generator.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    generator.chmod(0o755)

    findings = load_container_config_module().validate_generated_compose_scenarios(
        repo, None
    )

    assert {finding.detail for finding in findings} == {
        "default-scenario-compose-required",
        "gpu-admission-scenario-compose-required",
    }


def generate_gpu_admission_compose(tmp_path: Path) -> tuple[Path, Path]:
    """Generate one valid GPU-admission Compose fixture for mutation tests."""
    repo = tmp_path / "workspace" / "topic" / "agent-canon"
    write_devcontainer(repo)
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    write_file(repo, ".devcontainer/Dockerfile", DOCKERFILE.read_text(encoding="utf-8"))
    (repo / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)
    write_gpu_admission_pack(repo)
    output_path = repo / ".agent-canon/gpu-admission-compose.generated.yml"
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(tmp_path / "missing-home"),
            "AGENT_CANON_GPU_ADMISSION_PROFILE": "gpu-admission",
            "AGENT_CANON_SHARED_RUNTIME_SOURCE": str(repo / ".agent-canon/runtime"),
            "AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE": str(repo / ".agent-canon/runtime"),
            "AGENT_CANON_SHARED_RUNTIME_TARGET": "/var/lib/agent-canon/runtime",
            "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT": str(repo / ".agent-canon/runtime/shared-runtime-provision.json"),
            "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT": str(repo / ".agent-canon/runtime/shared-runtime-readback.json"),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/gpu-admission-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return repo, output_path


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
    """The checker rejects a removed legacy workspace-<topic-slug> root."""
    repo = write_topic_fixture(tmp_path, topic_root=tmp_path / "workspace-topic")

    result = run_validator(repo)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "legacy-workspace-root-direct-repo-rejected" in result.stdout


def test_workspace_prefixed_topic_root_is_handled_as_managed_topic(tmp_path: Path) -> None:
    """A canonical workspace/<workspace-*>/<repo> root is treated as managed-topic."""
    repo = write_topic_fixture(
        tmp_path,
        topic_root=tmp_path / "workspace" / "workspace-topic",
    )

    result = run_validator(repo)

    assert result.returncode == 0, result.stdout + result.stderr


def test_noncanonical_checkout_compose_root_is_direct_repo(tmp_path: Path) -> None:
    """The checker treats non-canonical path roots as direct-repo."""
    repo = write_topic_fixture(tmp_path, topic_root=tmp_path / "noncanonical" / "checkout")

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
    assert 'SHELL: "/bin/bash"' in compose
    assert 'command: /bin/bash -lc "sleep infinity"' in compose
    assert "dockerfile: .devcontainer/Dockerfile" in compose
    assert 'PROJECT_UID: "' in compose
    assert 'PROJECT_GID: "' in compose
    assert 'DEVCONTAINER_GPU_MODE: "disabled"' in compose
    assert 'DEPENDENCY_MODULE_CONTAINER_SOURCE:' in compose
    assert 'DEPENDENCY_MODULE_CONTAINER_TARGET: "/workspace"' in compose
    assert "DEVCONTAINER_GPU_REQUEST" not in compose
    assert "AGENT_CANON_RUNTIME_GID" not in compose
    assert "AGENT_CANON_HOST_SUPPLEMENTARY_GIDS" not in compose
    assert "NVIDIA_" not in compose
    assert "gpus: all" not in compose
    assert "group_add:" not in compose
    assert "/var/lib/agent-canon/runtime" not in compose
    assert "\n      target:" not in compose


def test_project_selector_rejects_rootless_docker_security_option(
    tmp_path: Path,
) -> None:
    """The project selector fails closed when Docker reports name=rootless."""
    repo = write_parent_generator_fixture(tmp_path)
    rootless_bin = write_fake_docker_probe(tmp_path / "rootless-docker", rootless=True)
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{rootless_bin}:{os.environ['PATH']}",
            "AGENT_CANON_RUNTIME_IDENTITY_MODE": "project",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "ROOTLESS_DAEMON_REQUIRES_ROOTLESS_SELECTOR" in result.stderr


def test_rootless_selector_projects_root_identity_without_default_mounts(
    tmp_path: Path,
) -> None:
    """The rootless selector uses uid 0 and keeps positive build ids."""
    repo = write_parent_generator_fixture(tmp_path)
    rootless_bin = write_fake_docker_probe(tmp_path / "rootless-docker", rootless=True)
    output_path = repo / ".agent-canon/docker-compose.rootless.generated.yml"
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{rootless_bin}:{os.environ['PATH']}",
            "AGENT_CANON_RUNTIME_IDENTITY_MODE": "rootless-root",
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": str(output_path),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = output_path.read_text(encoding="utf-8")
    assert 'user: "0:0"' in compose
    assert 'HOME: "/root"' in compose
    assert 'AGENT_CANON_CONTAINER_USER: "root"' in compose
    assert 'AGENT_CANON_RUNTIME_IDENTITY_MODE: "rootless-root"' in compose
    assert 'PROJECT_UID: "0"' not in compose
    assert 'PROJECT_GID: "0"' not in compose
    assert 'AGENT_CANON_OPTIONAL_MOUNTS: ""' in compose
    assert "/var/run/docker.sock" not in compose
    assert "/root/.ssh" not in compose
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    assert (
        module.validate_generated_compose(
            repo,
            pack,
            identity_mode="rootless-root",
            compose_path=output_path,
        )
        == []
    )


def test_rootless_selector_projects_selected_home_optional_mounts(
    tmp_path: Path,
) -> None:
    """Rootless zsh and credentials profiles target /root and stay read-only."""
    repo = write_parent_generator_fixture(tmp_path)
    rootless_bin = write_fake_docker_probe(tmp_path / "rootless-docker", rootless=True)
    home = tmp_path / "credentials-home"
    write_host_zshrc(home)
    (home / ".config" / "gh").mkdir(parents=True)
    (home / ".config" / "gh" / "hosts.yml").write_text("github.com:\n", encoding="utf-8")
    (home / ".ssh").mkdir()
    (home / ".ssh" / "known_hosts").write_text("", encoding="utf-8")
    output_path = repo / ".agent-canon/docker-compose.rootless.generated.yml"
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{rootless_bin}:{os.environ['PATH']}",
            "HOME": str(home),
            "AGENT_CANON_OPTIONAL_MOUNTS": "host-zshrc,host-credentials",
            "AGENT_CANON_RUNTIME_IDENTITY_MODE": "rootless-root",
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": str(output_path),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = output_path.read_text(encoding="utf-8")
    assert 'target: "/root/.zshrc"' in compose
    assert ":/root/.config/gh:ro" in compose
    assert ":/root/.ssh:ro" in compose
    assert 'target: "/home/project/.zshrc"' not in compose
    assert ":/home/project/.config/gh:ro" not in compose
    assert ":/home/project/.ssh:ro" not in compose
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack_findings == []
    assert pack is not None
    assert (
        module.validate_generated_compose(
            repo,
            pack,
            identity_mode="rootless-root",
            compose_path=output_path,
        )
        == []
    )


def test_rootless_selector_validator_rejects_project_remote_user(tmp_path: Path) -> None:
    """The static checker rejects a rootless selector that silently becomes project."""
    repo = write_topic_fixture(tmp_path)
    config_path = repo / ".devcontainer/rootless/devcontainer.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["remoteUser"] = "project"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    findings = load_container_config_module().validate_devcontainer(repo)

    assert any(
        finding.path == ".devcontainer/rootless/devcontainer.json"
        and finding.detail == "remoteUser-expected:root"
        for finding in findings
    )


def test_gpu_admission_scenario_projects_runtime_and_preserves_all_host_groups(
    tmp_path: Path,
) -> None:
    """The explicit profile projects the host identity and GPU runtime fields together."""
    repo = write_parent_generator_fixture(tmp_path)
    write_gpu_admission_pack(repo)
    output_path = repo / ".agent-canon/gpu-admission-compose.generated.yml"
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(tmp_path / "missing-home"),
            "AGENT_CANON_GPU_ADMISSION_PROFILE": "gpu-admission",
            "AGENT_CANON_SHARED_RUNTIME_SOURCE": str(repo / ".agent-canon/runtime"),
            "AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE": str(repo / ".agent-canon/runtime"),
            "AGENT_CANON_SHARED_RUNTIME_TARGET": "/var/lib/agent-canon/runtime",
            "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT": str(repo / ".agent-canon/runtime/shared-runtime-provision.json"),
            "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT": str(repo / ".agent-canon/runtime/shared-runtime-readback.json"),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/gpu-admission-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = output_path.read_text(encoding="utf-8")
    assert "name: parent-" in compose
    assert "-gpu-admission" in compose.splitlines()[0]
    assert "    gpus: all" in compose
    assert "\n      target:" not in compose
    assert "AGENT_CANON_PYTHON_EXTRAS" not in compose
    assert '        target: "/var/lib/agent-canon/runtime"' in compose
    assert "    group_add:" not in compose
    assert f'        source: "{repo / ".agent-canon/runtime"}"' in compose
    assert 'DEVCONTAINER_GPU_MODE: "enabled"' in compose
    assert 'DEVCONTAINER_GPU_REQUEST: "all"' in compose
    assert 'AGENT_CANON_RUNTIME_ROUTE: "MANAGED_CONTAINER"' in compose
    assert "AGENT_CANON_RUNTIME_GID" not in compose
    assert "AGENT_CANON_HOST_SUPPLEMENTARY_GIDS" not in compose
    module = load_container_config_module()
    pack, pack_findings = module.load_pack(
        repo, repo / "docker/packs/gpu-admission.toml"
    )
    assert pack_findings == []
    assert pack is not None
    assert (
        module.validate_generated_compose(
            repo,
            pack,
            profile="gpu-admission",
            compose_path=output_path,
    )
    == []
    )


@pytest.mark.parametrize("target", [None, "cpu-runtime"])
def test_gpu_admission_accepts_absent_or_explicit_pack_target(
    tmp_path: Path,
    target: str | None,
) -> None:
    """The GPU profile treats Docker build target as an optional generic pack field."""
    repo = write_parent_generator_fixture(tmp_path)
    write_gpu_admission_pack(repo, target=target)
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(tmp_path / "missing-home"),
            "AGENT_CANON_GPU_ADMISSION_PROFILE": "gpu-admission",
            "AGENT_CANON_SHARED_RUNTIME_SOURCE": str(repo / ".agent-canon/runtime"),
            "AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE": str(repo / ".agent-canon/runtime"),
            "AGENT_CANON_SHARED_RUNTIME_TARGET": "/var/lib/agent-canon/runtime",
            "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT": str(repo / ".agent-canon/runtime/shared-runtime-provision.json"),
            "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT": str(repo / ".agent-canon/runtime/shared-runtime-readback.json"),
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".devcontainer/gpu-admission-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (repo / ".devcontainer/gpu-admission-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert "AGENT_CANON_PYTHON_EXTRAS" not in compose
    if target is None:
        assert "\n      target:" not in compose
    else:
        assert f"      target: {target}" in compose


def test_gpu_admission_rejects_unsafe_pack_target(tmp_path: Path) -> None:
    """An explicit Docker target still follows the generic safe-name contract."""
    repo = write_parent_generator_fixture(tmp_path)
    write_gpu_admission_pack(repo, target="gpu/runtime")
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(tmp_path / "missing-home"),
            "AGENT_CANON_GPU_ADMISSION_PROFILE": "gpu-admission",
            "AGENT_CANON_SHARED_RUNTIME_SOURCE": str(repo / ".agent-canon/runtime"),
            "AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE": str(repo / ".agent-canon/runtime"),
            "AGENT_CANON_SHARED_RUNTIME_TARGET": "/var/lib/agent-canon/runtime",
            "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT": str(repo / ".agent-canon/runtime/shared-runtime-provision.json"),
            "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT": str(repo / ".agent-canon/runtime/shared-runtime-readback.json"),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "safe Docker build stage name" in result.stderr


def test_default_rejects_gpu_runtime_pack_target(tmp_path: Path) -> None:
    """The default profile cannot silently select the GPU build stage."""
    repo = write_parent_generator_fixture(tmp_path)
    default_pack = repo / "docker/packs/default.toml"
    default_pack.write_text(
        default_pack.read_text(encoding="utf-8").replace(
            'platform = "linux/amd64"',
            'platform = "linux/amd64"\ntarget = "gpu-runtime"',
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "HOME": str(tmp_path / "missing-home")},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "default profile rejects GPU build target" in result.stderr
@pytest.mark.parametrize(
    ("mutation", "expected_detail"),
    (
        (
            "source",
            "gpu-admission-runtime-mount-source-must-be-repository-local",
        ),
        (
            "read_only",
            "gpu-admission-runtime-mount-must-be-read-write",
        ),
    ),
)
def test_gpu_admission_validator_rejects_runtime_bind_mutations(
    tmp_path: Path, mutation: str, expected_detail: str
) -> None:
    """GPU admission runtime binds keep the canonical source and RW contract."""
    repo, output_path = generate_gpu_admission_compose(tmp_path)
    compose = output_path.read_text(encoding="utf-8")
    if mutation == "source":
        malformed = compose.replace(
            f'        source: "{repo / ".agent-canon/runtime"}"\n',
            '        source: "/tmp/evil-runtime"\n',
            1,
        )
    else:
        malformed = compose.replace(
            '        target: "/var/lib/agent-canon/runtime"\n',
            '        target: "/var/lib/agent-canon/runtime"\n        read_only: true\n',
            1,
        )
    output_path.write_text(malformed, encoding="utf-8")

    module = load_container_config_module()
    findings = module.validate_generated_compose(
        repo,
        None,
        profile="gpu-admission",
        compose_path=output_path,
    )

    assert expected_detail in {finding.detail for finding in findings}


def test_gpu_admission_validator_rejects_group_add_projection(tmp_path: Path) -> None:
    """GPU admission uses the primary project identity without group_add."""
    repo, output_path = generate_gpu_admission_compose(tmp_path)
    compose = output_path.read_text(encoding="utf-8")
    compose = compose.replace(
        '    gpus: all\n',
        '    gpus: all\n    group_add:\n      - "1234"\n',
        1,
    )
    output_path.write_text(compose, encoding="utf-8")
    findings = load_container_config_module().validate_generated_compose(
        repo, None, profile="gpu-admission", compose_path=output_path
    )
    assert "gpu-admission-group-add-forbidden" in {
        finding.detail for finding in findings
    }


def _docker_host_compose_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Return a GPU Compose fixture with the canonical docker-host bind selected."""
    repo, output_path = generate_gpu_admission_compose(tmp_path)
    compose = output_path.read_text(encoding="utf-8").replace(
        'AGENT_CANON_OPTIONAL_MOUNTS: ""',
        'AGENT_CANON_OPTIONAL_MOUNTS: "docker-host"',
        1,
    )
    compose = compose.replace(
        f'      - type: bind\n        source: "{repo / ".agent-canon/runtime"}"',
        '      - /var/run/docker.sock:/var/run/docker.sock\n'
        f'      - type: bind\n        source: "{repo / ".agent-canon/runtime"}"',
        1,
    )
    output_path.write_text(compose, encoding="utf-8")
    return repo, output_path


def test_docker_host_validator_accepts_canonical_rw_bind(tmp_path: Path) -> None:
    """Selected docker-host accepts exactly one canonical read-write bind."""
    repo, output_path = _docker_host_compose_fixture(tmp_path)
    module = load_container_config_module()
    findings = module.validate_generated_compose(
        repo,
        None,
        profile="gpu-admission",
        compose_path=output_path,
    )
    assert not any(finding.detail.startswith("docker-host-mount-") for finding in findings)


@pytest.mark.parametrize(
    ("mutation", "expected_detail"),
    (
        ("source", "docker-host-mount-source-must-be-canonical"),
        ("read_only", "docker-host-mount-must-be-read-write"),
        ("read_only_ro_z", "docker-host-mount-must-be-read-write"),
        ("read_only_z_ro", "docker-host-mount-must-be-read-write"),
        ("read_only_string", "docker-host-mount-must-be-read-write"),
        ("read_only_numeric", "docker-host-mount-must-be-read-write"),
        ("type", "docker-host-mount-type-must-be-bind"),
        ("duplicate", "docker-host-mount-count:2"),
    ),
)
def test_docker_host_validator_rejects_socket_bind_tampering(
    tmp_path: Path, mutation: str, expected_detail: str
) -> None:
    """Selected docker-host rejects source, type, read-only, and duplicate tampering."""
    repo, output_path = _docker_host_compose_fixture(tmp_path)
    compose = output_path.read_text(encoding="utf-8")
    if mutation == "source":
        compose = compose.replace(
            "      - /var/run/docker.sock:/var/run/docker.sock\n",
            "      - /tmp/evil.sock:/var/run/docker.sock\n",
            1,
        )
    elif mutation in {"read_only", "read_only_ro_z", "read_only_z_ro"}:
        mode = {
            "read_only": "ro",
            "read_only_ro_z": "ro,Z",
            "read_only_z_ro": "Z,ro",
        }[mutation]
        compose = compose.replace(
            "      - /var/run/docker.sock:/var/run/docker.sock\n",
            f"      - /var/run/docker.sock:/var/run/docker.sock:{mode}\n",
            1,
        )
    elif mutation in {"read_only_string", "read_only_numeric"}:
        read_only_value = '"true"' if mutation == "read_only_string" else "1"
        compose = compose.replace(
            "      - /var/run/docker.sock:/var/run/docker.sock\n",
            '      - type: bind\n        source: "/var/run/docker.sock"\n'
            '        target: "/var/run/docker.sock"\n'
            f"        read_only: {read_only_value}\n",
            1,
        )
    elif mutation == "type":
        compose = compose.replace(
            "      - /var/run/docker.sock:/var/run/docker.sock\n",
            '      - type: volume\n        source: "/var/run/docker.sock"\n'
            '        target: "/var/run/docker.sock"\n',
            1,
        )
    else:
        compose = compose.replace(
            "      - /var/run/docker.sock:/var/run/docker.sock\n",
            "      - /var/run/docker.sock:/var/run/docker.sock\n"
            "      - /var/run/docker.sock:/var/run/docker.sock\n",
            1,
        )
    output_path.write_text(compose, encoding="utf-8")
    module = load_container_config_module()
    findings = module.validate_generated_compose(
        repo,
        None,
        profile="gpu-admission",
        compose_path=output_path,
    )
    assert expected_detail in {finding.detail for finding in findings}


def test_generator_docker_host_fails_closed_without_socket(tmp_path: Path) -> None:
    """Selected docker-host fails before output when the host socket is unavailable."""
    repo = write_parent_generator_fixture(tmp_path)
    generator = repo / ".devcontainer/generate-runtime-compose.sh"
    missing_socket = tmp_path / "missing-docker.sock"
    generator.write_text(
        generator.read_text(encoding="utf-8").replace(
            "if [ ! -S /var/run/docker.sock ]; then",
            f"if [ ! -S {missing_socket} ]; then",
            1,
        ),
        encoding="utf-8",
    )
    generator.chmod(0o755)
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "AGENT_CANON_OPTIONAL_MOUNTS": "docker-host",
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "requires an existing Unix socket" in result.stderr


def test_optional_mount_rejects_removed_shared_runtime_selector(
    tmp_path: Path,
) -> None:
    """The default generator cannot be turned into the opt-in profile by a mount alone."""
    repo = tmp_path / "workspace" / "topic" / "agent-canon"
    write_devcontainer(repo)
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    (repo / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(tmp_path / "missing-home"),
            "AGENT_CANON_OPTIONAL_MOUNTS": "shared-runtime",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "optional mount profile is unsupported: shared-runtime" in result.stderr


@pytest.mark.parametrize(
    "reserved_name",
    ("AGENT_CANON_RUNTIME_GID", "AGENT_CANON_HOST_SUPPLEMENTARY_GIDS"),
)
def test_default_generator_rejects_reserved_runtime_identity_env(
    tmp_path: Path, reserved_name: str
) -> None:
    """The default pack cannot reintroduce removed runtime identity environment."""
    repo = write_parent_generator_fixture(tmp_path)
    pack_path = repo / "docker/packs/default.toml"
    pack_path.write_text(
        pack_path.read_text(encoding="utf-8")
        + f'env = ["{reserved_name}=4242"]\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "HOME": str(tmp_path / "missing-home")},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert f"runtime.env cannot override reserved key: {reserved_name}" in result.stderr


@pytest.mark.parametrize(
    "reserved_name",
    ("AGENT_CANON_RUNTIME_GID", "AGENT_CANON_HOST_SUPPLEMENTARY_GIDS"),
)
def test_gpu_generator_rejects_reserved_runtime_identity_env(
    tmp_path: Path, reserved_name: str
) -> None:
    """The GPU pack cannot reintroduce removed runtime identity environment."""
    repo = write_parent_generator_fixture(tmp_path)
    write_gpu_admission_pack(repo)
    pack_path = repo / "docker/packs/gpu-admission.toml"
    pack_path.write_text(
        pack_path.read_text(encoding="utf-8")
        + f'env = ["{reserved_name}=4242"]\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(tmp_path / "missing-home"),
            "AGENT_CANON_GPU_ADMISSION_PROFILE": "gpu-admission",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert f"runtime.env cannot override reserved key: {reserved_name}" in result.stderr


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


@pytest.mark.parametrize(
    ("relative_repo", "expected_layout"),
    [
        ("workspace/topic/agent-canon", "managed-topic"),
        ("home/runner/work/agent-canon/agent-canon", "direct-repo"),
        ("noncanonical/checkout/agent-canon", "direct-repo"),
    ],
    ids=(
        "canonical-managed-topic",
        "github-actions-direct-repo",
        "noncanonical-checkout-direct-repo",
    ),
)
def test_generator_classifies_checkout_layouts(
    tmp_path: Path, relative_repo: str, expected_layout: str
) -> None:
    """Shell and Python classifiers agree on managed and direct repository paths."""
    repo = tmp_path / relative_repo
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
    assert f'AGENT_CANON_WORKSPACE_LAYOUT: "{expected_layout}"' in compose
    if expected_layout == "managed-topic":
        assert f'source: "{repo.parent.resolve()}"' in compose
        assert 'target: "/workspace"' in compose
        assert f'source: "{repo.resolve()}"' not in compose
    else:
        assert f'source: "{repo.resolve()}"' in compose
        assert f'target: "/workspace/{repo.name}"' in compose
        assert f'source: "{repo.parent.resolve()}"' not in compose
    assert compose.count("type: bind") == 1
    assert load_container_config_module().validate_generated_compose(repo, None) == []


def test_generator_standalone_projects_host_zshrc_only_when_profile_selected(
    tmp_path: Path,
) -> None:
    """Standalone layout shares the opt-in host zshrc profile contract."""
    repo = tmp_path / "workspace" / "data_download"
    write_file(
        repo,
        ".devcontainer/generate-runtime-compose.sh",
        GENERATOR.read_text(encoding="utf-8"),
    )
    write_file(repo, ".devcontainer/Dockerfile", DOCKERFILE.read_text(encoding="utf-8"))
    (repo / ".devcontainer/generate-runtime-compose.sh").chmod(0o755)
    home = tmp_path / "home with spaces"
    target = write_host_zshrc_symlink(home)

    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "HOME": str(home),
            "AGENT_CANON_OPTIONAL_MOUNTS": "host-zshrc",
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compose = (repo / ".devcontainer/docker-compose.generated.yml").read_text(
        encoding="utf-8"
    )
    assert f'source: "{target}"' in compose
    assert 'target: "/home/project/.zshrc"' in compose
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


def test_generator_rejects_legacy_topic_root_as_direct_repo(tmp_path: Path) -> None:
    """The generator rejects workspace-<topic-slug> roots."""
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

    assert result.returncode == 1, result.stdout + result.stderr
    assert "legacy workspace root is rejected" in result.stderr


def test_post_attach_script_is_executable_in_git_index() -> None:
    """Source-root resolution can execute post-attach from the Git tree."""
    result = subprocess.run(
        ["git", "ls-files", "--stage", "--", ".devcontainer/post-attach.sh"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    entries = result.stdout.splitlines()
    assert len(entries) == 1
    assert entries[0].split(maxsplit=1)[0] == "100755"


def write_parent_generator_fixture(
    tmp_path: Path,
    *,
    runtime_shell: str = "/bin/zsh",
    runtime_mounts: tuple[str, ...] = (),
    optional_mount_profiles: tuple[str, ...] = (),
    linked_data_roots: tuple[tuple[str, str], ...] = (),
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
    optional_mount_profiles_line = (
        f"optional_mount_profiles = {json.dumps(list(optional_mount_profiles))}"
        if optional_mount_profiles
        else ""
    )
    linked_data_roots_line = (
        "linked_data_roots = ["
        + ", ".join(
            "{link = "
            + json.dumps(link)
            + ", target = "
            + json.dumps(target)
            + "}"
            for link, target in linked_data_roots
        )
        + "]"
        if linked_data_roots
        else ""
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
                optional_mount_profiles_line,
                linked_data_roots_line,
                runtime_mounts_line,
                "",
            ]
        ),
    )
    write_file(repo, "docker/Dockerfile", "FROM scratch\n")
    return repo


def write_gpu_admission_pack(
    repo: Path,
    *,
    target: str | None = None,
    dockerfile: str = "docker/Dockerfile",
) -> None:
    """Write the opt-in pack selected by the GPU generator profile."""
    (repo / ".agent-canon/runtime").mkdir(parents=True, exist_ok=True)
    target_line = f'target = "{target}"' if target is not None else ""
    write_file(
        repo,
        "docker/packs/gpu-admission.toml",
        "\n".join(
            [
                "[pack]",
                'name = "gpu-admission"',
                f'dockerfile = "{dockerfile}"',
                'context = "."',
                'image_tag = "gpu-admission:fixture"',
                'platform = "linux/amd64"',
                target_line,
                "",
                "[smoke]",
                'shell = "/bin/bash"',
                "commands = []",
                "",
                "[runtime]",
                'shell = "/bin/bash"',
                'workdir = "/workspace"',
                'workspace_mount = "/workspace"',
                "",
            ]
        ),
    )


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
                "",
            ]
        ),
        encoding="utf-8",
    )
    explicit, explicit_findings = module.load_pack(repo, explicit_pack)
    assert explicit_findings == []
    assert explicit is not None
    assert explicit.platform == "linux/amd64"


def test_load_pack_rejects_invalid_optional_profiles(tmp_path: Path) -> None:
    """Pack optional profiles are typed, known, non-empty, and unique."""
    cases = (("unknown",), ("",), ("host-git", "host-git"))
    module = load_container_config_module()
    for index, profiles in enumerate(cases):
        repo = write_parent_generator_fixture(
            tmp_path / str(index), optional_mount_profiles=profiles
        )
        pack, findings = module.load_pack(repo, repo / "docker/packs/default.toml")
        assert pack is None
        assert findings

    repo = write_parent_generator_fixture(tmp_path / "wrong-type")
    pack_path = repo / "docker/packs/default.toml"
    pack_path.write_text(
        pack_path.read_text(encoding="utf-8")
        + 'optional_mount_profiles = "host-git"\n',
        encoding="utf-8",
    )
    pack, findings = module.load_pack(repo, pack_path)
    assert pack is None
    assert any("optional_mount_profiles" in finding.detail for finding in findings)


def test_load_pack_requires_linked_data_profile_and_list_pair(tmp_path: Path) -> None:
    """Linked data roots require the matching profile in either direction."""
    module = load_container_config_module()
    repo = write_parent_generator_fixture(
        tmp_path / "profile-only", optional_mount_profiles=("linked-data-roots",)
    )
    pack, findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack is None
    assert any("profile-and-list" in finding.detail for finding in findings)

    repo = write_parent_generator_fixture(
        tmp_path / "empty-list", optional_mount_profiles=("linked-data-roots",)
    )
    empty_pack_path = repo / "docker/packs/default.toml"
    empty_pack_path.write_text(
        empty_pack_path.read_text(encoding="utf-8")
        + "linked_data_roots = []\n",
        encoding="utf-8",
    )
    pack, findings = module.load_pack(repo, empty_pack_path)
    assert pack is None
    assert any("must-be-non-empty" in finding.detail for finding in findings)

    repo = write_parent_generator_fixture(tmp_path / "list-only")
    link, target = write_linked_data_root_symlink(repo, tmp_path / "list-only")
    pack_path = repo / "docker/packs/default.toml"
    pack_path.write_text(
        pack_path.read_text(encoding="utf-8")
        + f'linked_data_roots = [{{link = {json.dumps(link)}, target = "/mnt/l/list-only"}}]\n',
        encoding="utf-8",
    )
    try:
        pack, findings = module.load_pack(repo, pack_path)
        assert pack is None
        assert any("profile-and-list" in finding.detail for finding in findings)
    finally:
        shutil.rmtree(target)


def test_load_pack_rejects_invalid_linked_data_root_entries(tmp_path: Path) -> None:
    """Linked root links and targets reject path escapes, broad roots, and duplicates."""
    module = load_container_config_module()
    cases = (
        "absolute-link",
        "dotdot-link",
        "regular-file",
        "broad-target",
        "punctuated-target",
        "duplicate",
    )
    for case in cases:
        repo = write_parent_generator_fixture(
            tmp_path / case, optional_mount_profiles=("linked-data-roots",)
        )
        link, target = write_linked_data_root_symlink(repo, tmp_path / case)
        pack_path = repo / "docker/packs/default.toml"
        if case == "absolute-link":
            configured_link = str(repo / link)
            configured_target = "/mnt/l/absolute"
            entries = [(configured_link, configured_target)]
        elif case == "dotdot-link":
            entries = [("../escape", "/mnt/l/escape")]
        elif case == "regular-file":
            (repo / link).unlink()
            (repo / link).write_text("not a symlink\n", encoding="utf-8")
            entries = [(link, "/mnt/l/regular")]
        elif case == "broad-target":
            entries = [(link, "/mnt/l")]
        elif case == "punctuated-target":
            entries = [(link, "/mnt/l/data,part")]
        else:
            entries = [(link, "/mnt/l/duplicate"), (link, "/mnt/l/duplicate")]
        entries_toml = ", ".join(
            "{link = "
            + json.dumps(entry_link)
            + ", target = "
            + json.dumps(entry_target)
            + "}"
            for entry_link, entry_target in entries
        )
        pack_path.write_text(
            pack_path.read_text(encoding="utf-8")
            + f"linked_data_roots = [{entries_toml}]\n",
            encoding="utf-8",
        )
        try:
            pack, findings = module.load_pack(repo, pack_path)
            assert pack is None
            assert findings
        finally:
            shutil.rmtree(target)


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
    assert "AGENT_CANON_PYTHON_EXTRAS" not in compose
    assert 'AGENT_CANON_CODEX_SESSION_ROOT: "/home/project/.codex/sessions"' in compose
    assert f'user: "{os.getuid()}:{os.getgid()}"' in compose
    assert 'PROJECT_USER:' not in compose
    assert f'PROJECT_UID: "{os.getuid()}"' in compose
    assert f'PROJECT_GID: "{os.getgid()}"' in compose
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


def test_parent_generator_rejects_linked_data_roots_target_failures(
    tmp_path: Path,
) -> None:
    """Generator fails closed for missing, file, and canonical-target mismatches."""
    cases = ("missing", "file", "mismatch")
    for case in cases:
        case_root = tmp_path / case
        repo = write_parent_generator_fixture(
            case_root,
            optional_mount_profiles=("linked-data-roots",),
        )
        (repo / ".agent-canon").mkdir()
        link, target = write_linked_data_root_symlink(repo, case_root)
        if case == "missing":
            target.rmdir()
            configured_target = "/mnt/l/missing"
        elif case == "file":
            target.rmdir()
            target.write_text("not a directory\n", encoding="utf-8")
            configured_target = "/mnt/l/file"
        else:
            configured_target = "/mnt/l/mismatch"
        pack_path = repo / "docker/packs/default.toml"
        pack_path.write_text(
            pack_path.read_text(encoding="utf-8")
            + "linked_data_roots = [{link = "
            + json.dumps(link)
            + ", target = "
            + json.dumps(configured_target)
            + "}]\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            ["bash", ".devcontainer/generate-runtime-compose.sh"],
            cwd=repo,
            env={
                **os.environ,
                "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
            },
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, result.stdout + result.stderr
        if case == "missing":
            assert "must resolve to an existing directory" in result.stderr
        elif case == "file":
            assert "must resolve to an existing directory" in result.stderr
        else:
            assert "does not match resolved source" in result.stderr


def test_generator_rejects_invalid_optional_mount_environment(tmp_path: Path) -> None:
    """Environment profile input rejects empty, whitespace, unknown, and duplicates."""
    for index, raw_profiles in enumerate(
        ("", " ", "host-zshrc,", "host-zshrc, host-git", "unknown", "host-git,host-git")
    ):
        repo = write_parent_generator_fixture(tmp_path / str(index))
        result = subprocess.run(
            ["bash", ".devcontainer/generate-runtime-compose.sh"],
            cwd=repo,
            env={
                **os.environ,
                "AGENT_CANON_OPTIONAL_MOUNTS": raw_profiles,
            },
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, result.stdout + result.stderr


def test_generator_rejects_empty_selected_linked_data_roots(tmp_path: Path) -> None:
    """Generator fails closed when linked-data-roots is selected with an empty list."""
    repo = write_parent_generator_fixture(
        tmp_path, optional_mount_profiles=("linked-data-roots",)
    )
    pack_path = repo / "docker/packs/default.toml"
    pack_path.write_text(
        pack_path.read_text(encoding="utf-8") + "linked_data_roots = []\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ, "AGENT_CANON_OPTIONAL_MOUNTS": "linked-data-roots"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "non-empty linked_data_roots" in result.stderr


def test_validator_requires_pack_for_selected_linked_data_profile(tmp_path: Path) -> None:
    """A generated linked profile cannot validate without its source pack."""
    repo = write_parent_generator_fixture(tmp_path)
    (repo / ".agent-canon").mkdir()
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={
            **os.environ,
            "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": ".agent-canon/docker-compose.generated.yml",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    compose_path = repo / ".agent-canon/docker-compose.generated.yml"
    compose = compose_path.read_text(encoding="utf-8")
    compose_path.write_text(
        compose.replace(
            'AGENT_CANON_OPTIONAL_MOUNTS: ""',
            'AGENT_CANON_OPTIONAL_MOUNTS: "linked-data-roots"',
        ),
        encoding="utf-8",
    )
    module = load_container_config_module()
    findings = module.validate_generated_compose(repo, None)
    assert any("linked-data-roots-pack-required" in finding.detail for finding in findings)


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


def test_generator_rejects_project_uid_or_gid_override(tmp_path: Path) -> None:
    """The generator derives host IDs and rejects caller-provided overrides."""
    for field in ("PROJECT_UID", "PROJECT_GID"):
        case_root = tmp_path / field
        repo = write_parent_generator_fixture(case_root)
        (repo / ".agent-canon").mkdir()
        result = subprocess.run(
            ["bash", ".devcontainer/generate-runtime-compose.sh"],
            cwd=repo,
            env={**os.environ, field: "1234"},
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "DEVCONTAINER_IDENTITY_ERROR=PROJECT_IDS_OVERRIDE_FORBIDDEN" in result.stderr


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
            valid.replace(
                f'user: "{os.getuid()}:{os.getgid()}"',
                f'user: "0:{os.getgid()}"',
            ).replace(
                f'PROJECT_UID: "{os.getuid()}"', 'PROJECT_UID: "0"'
            ),
            {"default-user-must-have-positive-uid-gid", "build-arg-PROJECT_UID-must-be-positive-integer"},
        ),
        (
            valid.replace(
                f'user: "{os.getuid()}:{os.getgid()}"',
                f'user: "{os.getuid()}:0"',
            ).replace(
                f'PROJECT_GID: "{os.getgid()}"', 'PROJECT_GID: "0"'
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
        env={**os.environ},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert (
        "runtime.env cannot override reserved key: AGENT_CANON_RUNTIME_ROUTE"
        in result.stderr
    )


@pytest.mark.parametrize("identity_key", ["PROJECT_UID", "PROJECT_GID", "PROJECT_USER"])
def test_generator_rejects_pack_override_of_host_identity(
    tmp_path: Path,
    identity_key: str,
) -> None:
    """Pack environment cannot introduce a second source of host identity."""
    repo = write_parent_generator_fixture(tmp_path)
    pack = repo / "docker/packs/default.toml"
    pack.write_text(
        pack.read_text(encoding="utf-8")
        + f'\nenv = ["{identity_key}=pack-value"]\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env={**os.environ},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert f"runtime.env cannot override reserved key: {identity_key}" in result.stderr


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
    for marker in (
        ".zshrc",
        "/home/project/.zsh",
        "/mnt/git",
        ".config/gh",
        "/.ssh",
        "/ssh-agent",
        "/mnt/agent-canon-secrets",
    ):
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
        env={**os.environ},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "rejects raw runtime.mounts" in result.stderr


def test_validator_rejects_raw_runtime_mounts(tmp_path: Path) -> None:
    """The static pack validator rejects raw runtime.mounts as a contract finding."""
    repo = write_parent_generator_fixture(
        tmp_path,
        runtime_mounts=("/var/run/docker.sock:/var/run/docker.sock",),
    )
    module = load_container_config_module()
    pack, findings = module.load_pack(repo, repo / "docker/packs/default.toml")
    assert pack is None
    assert any("runtime.mounts-unsupported-use-optional-profile" in finding.detail for finding in findings)


def test_generator_rejects_delimiter_linked_target(tmp_path: Path) -> None:
    """Generator linked targets reject delimiters unsafe for short Docker binds."""
    repo = write_parent_generator_fixture(
        tmp_path,
        optional_mount_profiles=("linked-data-roots",),
    )
    link, _target = write_linked_data_root_symlink(repo, tmp_path)
    pack_path = repo / "docker/packs/default.toml"
    pack_path.write_text(
        pack_path.read_text(encoding="utf-8")
        + "linked_data_roots = [{link = "
        + json.dumps(link)
        + ', target = "/mnt/l/data,part"}]\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", ".devcontainer/generate-runtime-compose.sh"],
        cwd=repo,
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "narrow /mnt/<letter> path" in result.stderr


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


def test_source_vscode_surface_and_shared_files_pass(tmp_path: Path) -> None:
    """Standalone source validates four files without a shared-surface manifest."""
    write_file(tmp_path, "ROOT_AGENTS.md", "# standalone\n")
    write_file(tmp_path, "agent-canon-environment.toml", "version = 1\n")
    write_vscode_source(tmp_path)

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "documents/runtime/shared-runtime-surfaces.toml" not in result.stdout


def test_derived_vscode_surface_allows_regular_project_content_and_extra_files(
    tmp_path: Path,
) -> None:
    """Derived parent content is regular, unconstrained, and need not mirror AgentCanon."""
    write_file(tmp_path, "vendor/agent-canon/README.md", "project dependency\n")
    (tmp_path / ".vscode").mkdir()
    write_file(tmp_path, ".vscode/settings.json", "{}\n")
    write_file(tmp_path, ".vscode/project-specific.json", "{}\n")

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_legacy_vscode_directory_symlink_is_rejected(tmp_path: Path) -> None:
    """The checker rejects the removed whole-directory topology."""
    write_vscode_source(tmp_path, "vendor/agent-canon/.vscode")
    (tmp_path / ".vscode").symlink_to(
        "vendor/agent-canon/.vscode", target_is_directory=True
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "expected-real-directory" in result.stdout


def test_legacy_vscode_individual_symlink_is_rejected(tmp_path: Path) -> None:
    """The checker rejects an individual link into the retired AgentCanon surface."""
    write_vscode_source(tmp_path, "vendor/agent-canon/.vscode")
    (tmp_path / ".vscode").mkdir()
    (tmp_path / ".vscode" / "settings.json").symlink_to(
        "../vendor/agent-canon/.vscode/settings.json"
    )

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "legacy-agent-canon-symlink" in result.stdout


def test_missing_parent_vscode_surface_is_not_forced(tmp_path: Path) -> None:
    """A derived parent without editor content remains valid and unconfigured."""
    write_file(tmp_path, "vendor/agent-canon/README.md", "project dependency\n")

    result = run_validator(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTAINER_CONFIG_FINDINGS=0" in result.stdout


def test_standalone_vscode_missing_file_is_rejected(tmp_path: Path) -> None:
    """Standalone source still requires each of its four regular files."""
    write_file(tmp_path, "ROOT_AGENTS.md", "# standalone\n")
    write_file(tmp_path, "agent-canon-environment.toml", "version = 1\n")
    write_vscode_source(tmp_path)
    (tmp_path / ".vscode" / "tasks.json").unlink()

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    assert ".vscode/tasks.json:missing" in result.stdout


def test_standalone_vscode_directory_missing_reports_all_source_files(
    tmp_path: Path,
) -> None:
    """Standalone markers keep source-file checks active when .vscode is absent."""
    write_file(tmp_path, "ROOT_AGENTS.md", "# standalone\n")
    write_file(tmp_path, "agent-canon-environment.toml", "version = 1\n")

    result = run_validator(tmp_path)

    assert result.returncode == 1, result.stdout + result.stderr
    for name in (
        "c_cpp_properties.json",
        "extensions.json",
        "settings.json",
        "tasks.json",
    ):
        assert f".vscode/{name}:missing" in result.stdout


def test_load_pack_rejects_image_owned_project_extras(tmp_path: Path) -> None:
    """Runtime packs cannot route workspace extras into startup runners."""
    module = load_container_config_module()
    repo = write_parent_generator_fixture(tmp_path)
    pack_path = repo / "docker/packs/default.toml"
    pack_path.write_text(
        pack_path.read_text(encoding="utf-8") + 'dependency_extras = ["dev", "cuda12"]\n',
        encoding="utf-8",
    )
    pack, findings = module.load_pack(repo, pack_path)
    assert pack is None
    assert any("dependency_extras-forbidden-image-owned" in finding.detail for finding in findings)
