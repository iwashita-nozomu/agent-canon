#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates Dockerfile, runtime pack, devcontainer, and shared VS Code surface configuration.
# upstream design ../../documents/conventions/coding-conventions-project.md environment configuration policy
# upstream design ../../documents/runtime/shared-runtime-surfaces.toml machine-readable shared runtime surface ownership
# upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md Dockerfile/devcontainer ownership boundary
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md parent layout and runtime shell boundary
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md default startup profile boundary
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md explicit GPU-admission selector and scenario validation
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md opt-in GPU runtime identity contract
# upstream design ../../documents/design/rust-agent-tool-migration.md Rust toolchain devcontainer boundary
# upstream design ../../agents/skills/academic-writing.md Academic Writing TeX tooling boundary
# upstream design ../../documents/tools/lean_proof_env.md Lean proof environment toolchain boundary
# upstream design ../../agents/skills/environment-maintenance.md environment change workflow
# upstream implementation ../agent_tools/surface_manifest.py parses shared runtime surface manifests
# upstream implementation ../agent_tools/requirements_lock.py canonical requirements lock parser and result/error model
# upstream implementation ../docker_dependency_validator.sh validates Docker dependency contents
# upstream implementation ./container_runtime.py loads runtime pack contracts
# upstream implementation ./run_container_pack.py builds and smokes runtime packs
# downstream implementation ./run_all_checks.sh runs container configuration validation
# downstream implementation ../../tests/tools/test_container_config.py tests validator
# downstream implementation ../../.devcontainer/gpu-admission/devcontainer.json selects the opt-in Compose scenario
# downstream implementation ../../.devcontainer/gpu-admission.sh owns the opt-in lifecycle scenario
# @dependency-end
"""Validate Dockerfile, runtime pack, devcontainer, and shared VS Code surfaces."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]
try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency is in runtime requirements.
    yaml = None
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

AGENT_TOOLS_DIR = Path(__file__).resolve().parents[1] / "agent_tools"
if str(AGENT_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_TOOLS_DIR))

from requirements_lock import (  # noqa: E402,I001  # pyright: ignore[reportMissingTypeStubs]
    parse_requirements,
)
from surface_manifest import (  # noqa: E402,I001
    SurfaceEntry,
    SurfaceManifest,
    load_manifest,
    target_for_entry,
)

REQUIRED_REQUIREMENTS = (
    "jupyterlab",
    "notebook",
    "ipykernel",
    "pydeps",
    "snakeviz",
    "pyyaml",
)

PARENT_ENVIRONMENT_SCRIPT = ".devcontainer/parent-environment.sh"
PARENT_ENVIRONMENT_MANIFEST = ".devcontainer/parent-environment.toml"
ENVIRONMENT_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
RUNTIME_SHELL_RE = re.compile(r"/[A-Za-z0-9._/-]+\Z")
DEPENDENCY_PROFILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
DEFAULT_DEPENDENCY_PROFILE = "full"
OPTIONAL_MOUNT_PROFILES = frozenset(
    {
        "host-zshrc",
        "host-git",
        "host-secrets",
        "host-credentials",
        "ssh-agent",
        "docker-host",
        "shared-runtime",
    }
)


@dataclass(frozen=True)
class Finding:
    """One container configuration finding."""

    kind: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"CONTAINER_CONFIG_FINDING={self.kind}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class PackConfig:
    """One runtime pack config loaded from TOML."""

    path: str
    name: str
    dockerfile: str
    context: str
    image_tag: str
    target: str | None
    shell: str
    workdir: str
    workspace_mount: str
    platform: str | None
    dependency_profile: str


@dataclass(frozen=True)
class ValidationReport:
    """Container configuration validation result."""

    status: str
    findings: tuple[Finding, ...]
    packs: tuple[PackConfig, ...]
    checked: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def as_mapping(value: object) -> Mapping[str, object] | None:
    """Return value as a string-keyed mapping when possible."""
    if not isinstance(value, Mapping):
        return None
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return None
    return cast(Mapping[str, object], mapping)


def as_sequence(value: object) -> Sequence[object] | None:
    """Return value as a sequence, excluding strings."""
    if isinstance(value, str):
        return None
    if isinstance(value, Sequence):
        return cast(Sequence[object], value)
    return None


def require_string(
    table: Mapping[str, object],
    key: str,
    source: str,
    section: str,
) -> tuple[str, Finding | None]:
    """Read one required non-empty string field."""
    value = table.get(key)
    if isinstance(value, str) and value:
        return value, None
    return "", Finding("invalid_manifest", source, f"{section}.{key}-must-be-string")


def require_string_list(
    table: Mapping[str, object],
    key: str,
    source: str,
    section: str,
) -> tuple[tuple[str, ...], Finding | None]:
    """Read one optional list of strings."""
    value = table.get(key)
    if value is None:
        return (), None
    sequence = as_sequence(value)
    if sequence is None or not all(isinstance(item, str) for item in sequence):
        return (), Finding(
            "invalid_manifest", source, f"{section}.{key}-must-be-string-list"
        )
    return tuple(cast(Sequence[str], sequence)), None


def is_safe_repo_relative(path_text: str) -> bool:
    """Return whether a configured path stays inside the repository."""
    path = Path(path_text)
    return not path.is_absolute() and ".." not in path.parts


def validate_repo_path(
    root: Path,
    source: str,
    field: str,
    value: str,
    findings: list[Finding],
) -> None:
    """Validate that one path is safe and exists under root."""
    if not value:
        return
    if not is_safe_repo_relative(value):
        findings.append(
            Finding("invalid_manifest", source, f"{field}-escapes-repo:{value}")
        )
        return
    if not (root / value).exists():
        findings.append(Finding("missing_file", source, f"{field}-missing:{value}"))


def load_pack(root: Path, path: Path) -> tuple[PackConfig | None, list[Finding]]:
    """Load and validate one runtime pack TOML file."""
    source = path.relative_to(root).as_posix()
    findings: list[Finding] = []
    try:
        with path.open("rb") as handle:
            data = cast(Mapping[str, object], tomllib.load(handle))
    except tomllib.TOMLDecodeError as exc:
        return None, [Finding("invalid_manifest", source, f"toml-decode:{exc}")]

    pack = as_mapping(data.get("pack"))
    smoke = as_mapping(data.get("smoke"))
    runtime = as_mapping(data.get("runtime"))
    if pack is None or smoke is None or runtime is None:
        return None, [
            Finding("invalid_manifest", source, "pack-smoke-runtime-required")
        ]

    required_pack_fields = {
        "name": "",
        "dockerfile": "",
        "context": "",
        "image_tag": "",
    }
    for field_name in required_pack_fields:
        value, finding = require_string(pack, field_name, source, "pack")
        required_pack_fields[field_name] = value
        if finding is not None:
            findings.append(finding)
    name = required_pack_fields["name"]
    dockerfile = required_pack_fields["dockerfile"]
    context = required_pack_fields["context"]
    image_tag = required_pack_fields["image_tag"]
    target_value = pack.get("target")
    target = target_value if isinstance(target_value, str) else None
    if target_value is not None and target is None:
        findings.append(
            Finding("invalid_manifest", source, "pack.target-must-be-string")
        )
    platform_value = pack.get("platform")
    platform = platform_value if isinstance(platform_value, str) else None
    if platform_value is not None and platform is None:
        findings.append(
            Finding("invalid_manifest", source, "pack.platform-must-be-string")
        )

    for table, key, section in (
        (smoke, "commands", "smoke"),
        (runtime, "env", "runtime"),
        (runtime, "mounts", "runtime"),
    ):
        _, finding = require_string_list(table, key, source, section)
        if finding is not None:
            findings.append(finding)
    workdir = runtime.get("workdir", "/workspace")
    workspace_mount = runtime.get("workspace_mount", "/workspace")
    shell = runtime.get("shell", "/bin/bash")
    dependency_profile = runtime.get("dependency_profile", DEFAULT_DEPENDENCY_PROFILE)
    if not isinstance(shell, str) or RUNTIME_SHELL_RE.fullmatch(shell) is None:
        findings.append(
            Finding(
                "invalid_manifest",
                source,
                "runtime.shell-must-be-absolute-executable-path",
            )
        )
    elif platform != "linux/amd64":
        findings.append(
            Finding(
                "dependency_contract_violation",
                source,
                "pack.platform-must-be-linux/amd64",
            )
        )
        shell = "/bin/bash"
    if not isinstance(workdir, str):
        findings.append(
            Finding("invalid_manifest", source, "runtime.workdir-must-be-string")
        )
        workdir = ""
    if not isinstance(workspace_mount, str):
        findings.append(
            Finding(
                "invalid_manifest", source, "runtime.workspace_mount-must-be-string"
            )
        )
        workspace_mount = ""
    if (
        not isinstance(dependency_profile, str)
        or DEPENDENCY_PROFILE_RE.fullmatch(dependency_profile) is None
    ):
        findings.append(
            Finding(
                "invalid_manifest",
                source,
                "runtime.dependency_profile-must-be-profile-name",
            )
        )
        dependency_profile = DEFAULT_DEPENDENCY_PROFILE

    validate_repo_path(root, source, "dockerfile", dockerfile, findings)
    validate_repo_path(root, source, "context", context, findings)
    if findings:
        return None, findings
    return (
        PackConfig(
            path=source,
            name=name,
            dockerfile=dockerfile,
            context=context,
            image_tag=image_tag,
            target=target,
            shell=shell,
            workdir=workdir,
            workspace_mount=workspace_mount,
            platform=platform,
            dependency_profile=dependency_profile,
        ),
        [],
    )


def validate_requirements(root: Path) -> list[Finding]:
    """Validate docker/requirements.txt."""
    path = root / "docker" / "requirements.txt"
    relative = "docker/requirements.txt"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    findings: list[Finding] = []
    parsed = parse_requirements(path)
    for error in parsed.errors:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                f"invalid-line:{error.line_number}",
            )
        )
    if parsed.valid:
        requirements = {
            record.normalized_name for record in parsed.records if record.is_active()
        }
        for requirement in REQUIRED_REQUIREMENTS:
            if requirement not in requirements:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"missing:{requirement}",
                    )
                )
    return findings


def validate_dockerfile(root: Path) -> list[Finding]:
    """Require the Dockerfile path without fixing its implementation text."""
    path = root / "docker" / "Dockerfile"
    relative = "docker/Dockerfile"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    return []


def validate_dockerignore(root: Path) -> list[Finding]:
    """Validate Docker build context exclusions."""
    path = root / ".dockerignore"
    relative = ".dockerignore"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    text = path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    for ignored_path in (".git", ".state", "vendor/agent-canon"):
        if not re.search(rf"(^|\n){re.escape(ignored_path)}(\n|$)", text):
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    f"missing-ignore:{ignored_path}",
                )
            )
    return findings


def shared_devcontainer_dir(root: Path) -> Path:
    """Return the shared devcontainer source for a parent or source checkout."""
    vendored = root / "vendor" / "agent-canon" / ".devcontainer"
    if vendored.is_dir():
        return vendored
    return root / ".devcontainer"


def validate_post_create(root: Path) -> list[Finding]:
    """Require executable shared-first post-create sources at their owner paths."""
    shared_dir = shared_devcontainer_dir(root)
    findings: list[Finding] = []
    for name in ("post-create.sh", "post-create-entrypoint.sh"):
        path = shared_dir / name
        relative = f"{path.relative_to(root)}"
        if not path.is_file():
            findings.append(Finding("missing_file", relative, "missing"))
        elif not (path.stat().st_mode & 0o111):
            findings.append(
                Finding("dependency_contract_violation", relative, "not-executable")
            )
    entrypoint = shared_dir / "post-create-entrypoint.sh"
    if entrypoint.is_file():
        text = entrypoint.read_text(encoding="utf-8")
        required_markers = (
            'bash "$entrypoint_dir/post-create.sh" "$workspace"',
            'parent_hook="$workspace/.devcontainer/post-create-parent.sh"',
            'bash "$parent_hook" "$workspace"',
        )
        for marker in required_markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        str(entrypoint.relative_to(root)),
                        f"resolver-entrypoint-missing:{marker}",
                    )
                )
    return findings


def validate_python_dependency_installer(root: Path) -> list[Finding]:
    """Require the optional dependency installer without fixing shell internals."""
    path = root / "docker" / "install_python_dependencies.sh"
    relative = "docker/install_python_dependencies.sh"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    return []


def load_devcontainer_json(
    path: Path,
) -> tuple[Mapping[str, object] | None, list[Finding]]:
    """Load .devcontainer/devcontainer.json."""
    relative = ".devcontainer/devcontainer.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [Finding("invalid_manifest", relative, f"json-decode:{exc}")]
    mapping = as_mapping(data)
    if mapping is None:
        return None, [Finding("invalid_manifest", relative, "must-be-object")]
    return mapping, []


def validate_devcontainer_json(config: Mapping[str, object]) -> list[Finding]:
    """Validate required devcontainer JSON fields."""
    findings: list[Finding] = []
    expected_json = {
        "name": "${localWorkspaceFolderBasename}-devcontainer",
        "initializeCommand": "AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/docker-compose.generated.yml python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/generate-runtime-compose.sh",
        "dockerComposeFile": "../.agent-canon/docker-compose.generated.yml",
        "service": "workspace",
        "containerUser": "project",
        "remoteUser": "project",
        "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",
        "postCreateCommand": "bash .devcontainer/bootstrap-dependencies.sh --install && python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-create-entrypoint.sh /workspace/${localWorkspaceFolderBasename}",
        "postAttachCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-attach.sh",
    }
    for key, expected in expected_json.items():
        if config.get(key) != expected:
            findings.append(
                Finding(
                    "inconsistency",
                    ".devcontainer/devcontainer.json",
                    f"{key}-expected:{expected}",
                )
            )
    if "remoteUser" in config and config.get("remoteUser") != "project":
        findings.append(
            Finding(
                "dependency_contract_violation",
                ".devcontainer/devcontainer.json",
                "remoteUser-expected:project",
            )
        )
    if "updateRemoteUserUID" in config:
        findings.append(
            Finding(
                "dependency_contract_violation",
                ".devcontainer/devcontainer.json",
                "default-devcontainer-field-forbidden:updateRemoteUserUID",
            )
        )
    if "containerEnv" in config:
        findings.append(
            Finding(
                "dependency_contract_violation",
                ".devcontainer/devcontainer.json",
                "static-containerEnv-forbidden-generated-compose-owns-runtime-env",
            )
        )
    return findings


def validate_devcontainer_workspace(
    config: Mapping[str, object], pack: PackConfig | None
) -> list[Finding]:
    """Validate the selected repository folder below the topic mount."""
    del pack
    if config.get("workspaceFolder") == "/workspace/${localWorkspaceFolderBasename}":
        return []
    return [
        Finding(
            "inconsistency",
            ".devcontainer/devcontainer.json",
            "workspaceFolder-expected:/workspace/${localWorkspaceFolderBasename}",
        )
    ]


def validate_generate_runtime_compose_script(root: Path) -> list[Finding]:
    """Require the shared generator executable used by both runtime scenarios."""
    script_path = shared_devcontainer_dir(root) / "generate-runtime-compose.sh"
    if not script_path.is_file():
        return [Finding("missing_file", f"{script_path.relative_to(root)}", "missing")]
    if script_path.stat().st_mode & 0o111 == 0:
        return [
            Finding(
                "dependency_contract_violation",
                f"{script_path.relative_to(root)}",
                "not-executable",
            )
        ]
    return []


def validate_default_lifecycle_scripts(root: Path) -> list[Finding]:
    """Require the default lifecycle entrypoints selected by devcontainer.json."""
    shared_dir = shared_devcontainer_dir(root)
    findings: list[Finding] = []
    for name in ("post-create.sh", "post-attach.sh"):
        path = shared_dir / name
        relative = path.relative_to(root).as_posix()
        if not path.is_file():
            findings.append(Finding("missing_file", relative, "missing"))
        elif path.stat().st_mode & 0o111 == 0:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "not-executable",
                )
            )
    return findings


def validate_gpu_admission_selector(root: Path) -> list[Finding]:
    """Validate the explicit GPU-admission selector without inspecting script text."""
    selector_path = root / ".devcontainer" / "gpu-admission" / "devcontainer.json"
    if not selector_path.is_file():
        return [
            Finding(
                "missing_file",
                ".devcontainer/gpu-admission/devcontainer.json",
                "explicit-profile-selector-required",
            )
        ]
    config, findings = load_devcontainer_json(selector_path)
    if config is None:
        return findings
    expected = {
        "name": "${localWorkspaceFolderBasename}-gpu-admission-devcontainer",
        "initializeCommand": "AGENT_CANON_GPU_ADMISSION_PROFILE=gpu-admission AGENT_CANON_OPTIONAL_MOUNTS=shared-runtime AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/gpu-admission-compose.generated.yml python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/generate-runtime-compose.sh",
        "dockerComposeFile": "../../.agent-canon/gpu-admission-compose.generated.yml",
        "service": "workspace",
        "containerUser": "project",
        "remoteUser": "project",
        "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",
        "postCreateCommand": "bash .devcontainer/bootstrap-dependencies.sh --install && python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-create-entrypoint.sh /workspace/${localWorkspaceFolderBasename}",
        "postAttachCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-attach.sh",
    }
    for key, expected_value in expected.items():
        if config.get(key) != expected_value:
            findings.append(
                Finding(
                    "inconsistency",
                    ".devcontainer/gpu-admission/devcontainer.json",
                    f"{key}-expected:{expected_value}",
                )
            )
    if config.get("shutdownAction") != "stopCompose" or config.get("overrideCommand") is not False:
        findings.append(
            Finding(
                "dependency_contract_violation",
                ".devcontainer/gpu-admission/devcontainer.json",
                "profile-lifecycle-fields",
            )
        )
    orchestrator = shared_devcontainer_dir(root) / "gpu-admission.sh"
    bootstrap = shared_devcontainer_dir(root) / "bootstrap-shared-runtime.sh"
    orchestrator_relative = orchestrator.relative_to(root).as_posix()
    if not orchestrator.is_file() or orchestrator.stat().st_mode & 0o111 == 0:
        findings.append(
            Finding(
                "missing_file" if not orchestrator.is_file() else "dependency_contract_violation",
                orchestrator_relative,
                "executable-profile-orchestrator-required",
            )
        )
    bootstrap_mode = git_index_mode(root, bootstrap)
    if bootstrap_mode is not None and bootstrap_mode != "100755":
        findings.append(
            Finding(
                "dependency_contract_violation",
                bootstrap.relative_to(root).as_posix(),
                f"bootstrap-shared-runtime-git-mode:{bootstrap_mode}",
            )
        )
    return findings


def parse_parent_environment_exports(path: Path) -> tuple[tuple[str, ...], list[str]]:
    """Parse allowed parent-environment export lines without executing shell."""
    names: list[str] = []
    findings: list[str] = []
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line, comments=True, posix=True)
        except ValueError:
            findings.append(f"invalid-export-line:{line_number}")
            continue
        if len(tokens) != 2 or tokens[0] != "export":
            findings.append(f"invalid-export-line:{line_number}")
            continue
        name, separator, _value = tokens[1].partition("=")
        if not separator or ENVIRONMENT_NAME_RE.fullmatch(name) is None:
            findings.append(f"invalid-export-line:{line_number}")
            continue
        if name in names:
            findings.append(f"duplicate-export:{name}")
            continue
        names.append(name)
    return tuple(names), findings


def parse_parent_environment_manifest(path: Path) -> tuple[tuple[str, ...], list[str]]:
    """Read the ordered parent-environment variable-name manifest."""
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return (), [f"toml-decode:{exc}"]
    if set(data) != {"variables"}:
        return (), ["toml-keys-must-be-variables-only"]
    variables = data.get("variables")
    if not isinstance(variables, list) or not all(
        isinstance(item, str) for item in variables
    ):
        return (), ["variables-must-be-string-list"]
    names = cast(list[str], variables)
    findings: list[str] = []
    seen: set[str] = set()
    for name in names:
        if ENVIRONMENT_NAME_RE.fullmatch(name) is None:
            findings.append(f"invalid-variable-name:{name}")
        elif name in seen:
            findings.append(f"duplicate-variable:{name}")
        seen.add(name)
    return tuple(names), findings


def validate_parent_environment(root: Path) -> list[Finding]:
    """Validate parent environment sources and their ordered-name agreement."""
    if not (root / "vendor" / "agent-canon").is_dir():
        return []
    findings: list[Finding] = []
    script_path = root / PARENT_ENVIRONMENT_SCRIPT
    manifest_path = root / PARENT_ENVIRONMENT_MANIFEST
    declared = tuple(
        path.exists() or path.is_symlink() for path in (script_path, manifest_path)
    )
    if not any(declared):
        return []
    for path, relative in (
        (script_path, PARENT_ENVIRONMENT_SCRIPT),
        (manifest_path, PARENT_ENVIRONMENT_MANIFEST),
    ):
        if not path.is_file():
            detail = "missing-target" if path.is_symlink() else "missing"
            findings.append(Finding("missing_file", relative, detail))
    if findings:
        return findings

    export_names, export_findings = parse_parent_environment_exports(script_path)
    findings.extend(
        Finding("invalid_manifest", PARENT_ENVIRONMENT_SCRIPT, detail)
        for detail in export_findings
    )
    manifest_names, manifest_findings = parse_parent_environment_manifest(manifest_path)
    findings.extend(
        Finding("invalid_manifest", PARENT_ENVIRONMENT_MANIFEST, detail)
        for detail in manifest_findings
    )
    if not export_findings and not manifest_findings and export_names != manifest_names:
        findings.append(
            Finding(
                "inconsistency",
                PARENT_ENVIRONMENT_MANIFEST,
                f"ordered-variable-names-mismatch:manifest={list(manifest_names)}:exports={list(export_names)}",
            )
        )
    return findings


def parent_environment_enabled(root: Path) -> bool:
    """Return whether both optional parent environment sources resolve to files."""
    return (root / PARENT_ENVIRONMENT_SCRIPT).is_file() and (
        root / PARENT_ENVIRONMENT_MANIFEST
    ).is_file()


def is_managed_topic_root(root: Path) -> bool:
    """Return True when the repo is mounted as a managed topic layout."""
    topic_root = root.parent
    return topic_root.parent.name == "workspace"


def is_removed_legacy_topic_root(root: Path) -> bool:
    """Return True when the immediate parent directory is a removed legacy workspace root."""
    return (
        root.parent.name.startswith("workspace-") and root.parent.parent.name != "workspace"
    )


def git_index_mode(root: Path, path: Path) -> str | None:
    """Return the git-index mode for one path if it is tracked."""
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-s", "--", relative],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.split(None, 1)[0] or None


def validate_generated_compose(
    root: Path,
    pack: PackConfig | None,
    *,
    profile: str = "default",
    compose_path: Path | None = None,
) -> list[Finding]:
    """Validate generated Compose meaning rather than generator implementation text."""
    if compose_path is None:
        if (root / "vendor" / "agent-canon").is_dir():
            compose_path = root / ".agent-canon" / "docker-compose.generated.yml"
            relative = ".agent-canon/docker-compose.generated.yml"
        else:
            compose_path = root / ".devcontainer" / "docker-compose.generated.yml"
            relative = ".devcontainer/docker-compose.generated.yml"
    else:
        compose_path = compose_path.resolve()
        try:
            relative = compose_path.relative_to(root.resolve()).as_posix()
        except ValueError:
            relative = f"<generated-compose:{profile}>"
    if not compose_path.exists():
        return [Finding("missing_file", relative, f"{profile}-scenario-compose-required")]
    if yaml is None:
        return [Finding("invalid_manifest", relative, "yaml-parser-unavailable")]
    try:
        document = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - parser errors are user-facing findings.
        return [Finding("invalid_manifest", relative, f"yaml-decode:{exc}")]
    compose = as_mapping(document)
    if compose is None:
        return [Finding("invalid_manifest", relative, "compose-must-be-object")]
    services = as_mapping(compose.get("services"))
    service = as_mapping(services.get("workspace")) if services is not None else None
    if service is None:
        return [Finding("invalid_manifest", relative, "workspace-service-required")]
    root = root.resolve()
    topic_root = root.parent
    repo_target = f"/workspace/{root.name}"
    expected_workspace_layout = (
        "managed-topic" if is_managed_topic_root(root) else "direct-repo"
    )
    if is_removed_legacy_topic_root(root) and expected_workspace_layout != "managed-topic":
        return [
            Finding(
                "dependency_contract_violation",
                relative,
                "legacy-workspace-root-direct-repo-rejected",
            )
        ]
    parent_layout = (root / "vendor" / "agent-canon").is_dir()
    findings: list[Finding] = []
    if profile not in {"default", "gpu-admission"}:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                f"profile-unsupported:{profile}",
            )
        )
    if profile == "gpu-admission":
        compose_name = compose.get("name")
        if not isinstance(compose_name, str) or not compose_name.endswith(
            "-gpu-admission"
        ):
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "gpu-admission-project-name-suffix-required",
                )
            )
    if service.get("working_dir") != repo_target:
        findings.append(
            Finding(
                "inconsistency", relative, f"working-dir:{service.get('working_dir')}"
            )
        )
    expected_platform = pack.platform if pack is not None and pack.platform else "linux/amd64"
    if service.get("platform") != expected_platform:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                f"compose-platform-expected:{expected_platform}",
            )
        )
    build = as_mapping(service.get("build"))
    if build is not None and build.get("context") != "..":
        findings.append(
            Finding("inconsistency", relative, f"build-context:{build.get('context')}")
        )
    standalone_dockerfile = root / ".devcontainer" / "Dockerfile"
    if not parent_layout and standalone_dockerfile.is_file():
        if build is None:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "standalone-build-required",
                )
            )
        else:
            if build.get("dockerfile") != ".devcontainer/Dockerfile":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "standalone-dockerfile-required:.devcontainer/Dockerfile",
                    )
                )
            standalone_args = as_mapping(build.get("args"))
            if standalone_args is None:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "standalone-build-args-required:PROJECT_UID,PROJECT_GID",
                    )
                )
            else:
                for name in ("PROJECT_UID", "PROJECT_GID"):
                    value = standalone_args.get(name)
                    if not isinstance(value, str) or re.fullmatch(
                        r"[1-9][0-9]*", value
                    ) is None:
                        findings.append(
                            Finding(
                                "dependency_contract_violation",
                                relative,
                                f"standalone-build-arg-{name}-must-be-positive-integer",
                            )
                        )
    volumes = as_sequence(service.get("volumes"))
    if volumes is None:
        return [
            *findings,
            Finding("invalid_manifest", relative, "workspace-volumes-required"),
        ]

    def volume_fields(raw_volume: object) -> tuple[str | None, str | None]:
        volume = as_mapping(raw_volume)
        if volume is not None:
            source = volume.get("source")
            target = volume.get("target")
            return (
                source if isinstance(source, str) else None,
                target if isinstance(target, str) else None,
            )
        if isinstance(raw_volume, str) and ":" in raw_volume:
            source, target, *_ = raw_volume.split(":", 2)
            return source, target
        return None, None

    def volume_is_read_only(raw_volume: object) -> bool:
        volume = as_mapping(raw_volume)
        if volume is not None:
            return volume.get("read_only") is True
        if isinstance(raw_volume, str):
            return raw_volume.rsplit(":", 1)[-1] == "ro"
        return False

    def volume_type(raw_volume: object) -> str | None:
        volume = as_mapping(raw_volume)
        if volume is None:
            return None
        value = volume.get("type")
        return value if isinstance(value, str) else None

    def source_path(source: str | None) -> Path | None:
        if not source:
            return None
        candidate = Path(source)
        return (candidate if candidate.is_absolute() else root / candidate).resolve()

    environment = as_mapping(service.get("environment"))
    optional_mounts_value = (
        environment.get("AGENT_CANON_OPTIONAL_MOUNTS", "")
        if environment is not None
        else ""
    )
    optional_mounts = (
        optional_mounts_value if isinstance(optional_mounts_value, str) else ""
    )
    optional_tokens_list = [
        token.strip() for token in optional_mounts.split(",") if token.strip()
    ]
    optional_tokens = set(optional_tokens_list)
    supported_optional_mounts = OPTIONAL_MOUNT_PROFILES
    if profile != "gpu-admission":
        supported_optional_mounts = supported_optional_mounts - {"shared-runtime"}
    for token in sorted(optional_tokens - supported_optional_mounts):
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                f"optional-mount-profile-unsupported:{token}",
            )
        )
    if len(optional_tokens_list) != len(optional_tokens):
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "optional-mount-profile-duplicate",
            )
        )
    workspace_layout = (
        environment.get("AGENT_CANON_WORKSPACE_LAYOUT")
        if environment is not None
        else None
    )
    if not isinstance(workspace_layout, str) or workspace_layout not in {
        "managed-topic",
        "direct-repo",
    }:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "workspace-layout-environment-required",
            )
        )
    elif expected_workspace_layout is not None and (
        workspace_layout != expected_workspace_layout
    ):
        findings.append(
            Finding(
                "inconsistency",
                relative,
                f"workspace-layout:{workspace_layout}",
            )
        )

    workspace_mounts: list[tuple[str | None, str | None]] = []
    for raw_volume in volumes:
        source, target = volume_fields(raw_volume)
        if target == "/workspace":
            workspace_mounts.append((source, target))
    if expected_workspace_layout == "managed-topic":
        if len(workspace_mounts) != 1:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    f"workspace-mount-count:{len(workspace_mounts)}",
                )
            )
        elif source_path(workspace_mounts[0][0]) != topic_root:
            findings.append(
                Finding("dependency_contract_violation", relative, "workspace-source")
            )
        for raw_volume in volumes:
            source, target = volume_fields(raw_volume)
            if source_path(source) == root or target == repo_target:
                findings.append(
                    Finding(
                        "dependency_contract_violation", relative, "repository-double-mount"
                    )
                )
    elif expected_workspace_layout == "direct-repo":
        direct_mounts = [
            raw_volume
            for raw_volume in volumes
            if volume_fields(raw_volume)[1] == repo_target
        ]
        if len(direct_mounts) != 1:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    f"direct-repo-mount-count:{len(direct_mounts)}",
                )
            )
        elif source_path(volume_fields(direct_mounts[0])[0]) != root:
            findings.append(
                Finding("dependency_contract_violation", relative, "direct-repo-source")
            )
        for raw_volume in volumes:
            source, target = volume_fields(raw_volume)
            if source_path(source) == topic_root or target == "/workspace":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "direct-repo-workspace-leak",
                    )
                )
    expected_shell = pack.shell if pack is not None else "/bin/bash"
    if service.get("command") != f'{expected_shell} -lc "sleep infinity"':
        findings.append(
            Finding(
                "inconsistency",
                relative,
                f"runtime-shell-command:{expected_shell}",
            )
        )
    service_user = service.get("user")
    if service_user is not None and (
        not isinstance(service_user, str)
        or re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", service_user) is None
    ):
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "default-user-must-have-positive-uid-gid",
            )
        )
    if not parent_layout and "tmpfs" in service:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "default-home-tmpfs-forbidden",
            )
        )
    if profile == "default":
        if "group_add" in service:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "default-shared-runtime-field-forbidden:group_add",
                )
            )
        if "gpus" in service:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "default-gpu-field-forbidden:gpus",
                )
            )
    else:
        group_add = as_sequence(service.get("group_add"))
        if group_add is None or not group_add:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "gpu-admission-group-add-required",
                )
            )
        else:
            group_values = tuple(str(value) for value in group_add)
            if any(re.fullmatch(r"[1-9][0-9]*", value) is None for value in group_values):
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "gpu-admission-group-add-must-be-positive-integers",
                    )
                )
            host_groups = (
                environment.get("AGENT_CANON_HOST_SUPPLEMENTARY_GIDS", "")
                if environment is not None
                else ""
            )
            expected_groups = tuple(str(host_groups).split())
            if group_values != expected_groups:
                findings.append(
                    Finding(
                        "inconsistency",
                        relative,
                        "gpu-admission-group-add-must-preserve-host-groups",
                    )
                )
        if service.get("gpus") != "all":
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "gpu-admission-gpus-all-required",
                )
            )
    for raw_volume in volumes:
        _source, target = volume_fields(raw_volume)
        if profile == "default" and target == "/var/lib/agent-canon/runtime":
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "default-shared-runtime-field-forbidden:runtime-bind",
                )
            )
    runtime_mounts = [
        raw_volume
        for raw_volume in volumes
        if volume_fields(raw_volume)[1] == "/var/lib/agent-canon/runtime"
    ]
    if profile == "gpu-admission":
        if len(runtime_mounts) != 1:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    f"gpu-admission-runtime-mount-count:{len(runtime_mounts)}",
                )
            )
        elif volume_type(runtime_mounts[0]) != "bind":
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "gpu-admission-runtime-mount-type-must-be-bind",
                )
            )
    if parent_layout or "host-zshrc" in optional_tokens:
        zshrc_matches = [
            raw_volume
            for raw_volume in volumes
            if volume_fields(raw_volume)[1] in {
                "/home/project/.zshrc",
                "/etc/project-template/zsh/.zshrc",
            }
        ]
        for host_zshrc in zshrc_matches:
            _, target = volume_fields(host_zshrc)
            if target != "/home/project/.zshrc":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "host-zshrc-target-must-be-/home/project/.zshrc",
                    )
                )
            if volume_type(host_zshrc) != "bind":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "host-zshrc-mount-type-must-be-bind",
                    )
                )
            source, _ = volume_fields(host_zshrc)
            if not isinstance(source, str) or (
                source != "${HOME}/.zshrc"
                and (not source.startswith("/") or not source.endswith("/.zshrc"))
            ):
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "host-zshrc-source-must-be-absolute-zshrc",
                    )
                )
            if not volume_is_read_only(host_zshrc):
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "host-zshrc-mount-read-only",
                    )
                )
        if not isinstance(service_user, str) or re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", service_user) is None:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "default-user-must-have-positive-uid-gid",
                )
            )
        build = as_mapping(service.get("build"))
        build_args = as_mapping(build.get("args")) if build is not None else None
        if build_args is None:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "build-args-required:PROJECT_UID,PROJECT_GID",
                )
            )
        else:
            if "PROJECT_USER" in build_args:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "build-arg-PROJECT_USER-forbidden-canonical-project",
                    )
                )
            for name in ("PROJECT_UID", "PROJECT_GID"):
                value = build_args.get(name)
                if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]*", value) is None:
                    findings.append(
                        Finding(
                            "dependency_contract_violation",
                            relative,
                            f"build-arg-{name}-must-be-positive-integer",
                        )
                    )
            if (
                isinstance(service_user, str)
                and isinstance(build_args.get("PROJECT_UID"), str)
                and isinstance(build_args.get("PROJECT_GID"), str)
                and service_user
                != f'{build_args["PROJECT_UID"]}:{build_args["PROJECT_GID"]}'
            ):
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "runtime-user-must-match-project-uid-gid-build-args",
                    )
                )
        for raw_volume in volumes:
            source, target = volume_fields(raw_volume)
            if (source and "/root/" in source) or (target and target.startswith("/root/")):
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "root-home-mount-forbidden",
                    )
                )
    allowed_targets = {"/workspace", repo_target}
    if "host-zshrc" in optional_tokens:
        allowed_targets.add("/home/project/.zshrc")
    if profile == "gpu-admission":
        allowed_targets.add("/var/lib/agent-canon/runtime")
    if "host-git" in optional_tokens:
        allowed_targets.add("/mnt/git")
    if "host-secrets" in optional_tokens:
        allowed_targets.add("/mnt/agent-canon-secrets")
    if "host-credentials" in optional_tokens:
        allowed_targets.update({"/home/project/.config/gh", "/home/project/.ssh"})
    if "ssh-agent" in optional_tokens:
        allowed_targets.add("/ssh-agent")
    if "docker-host" in optional_tokens:
        allowed_targets.add("/var/run/docker.sock")
    for raw_volume in volumes:
        source, target = volume_fields(raw_volume)
        if target not in allowed_targets:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    f"host-mount-target-forbidden-by-default:{target}",
                )
            )
        if (source and "/root/" in source) or (target and target.startswith("/root/")):
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "root-home-mount-forbidden",
                )
            )
    required_environment = {
        "AGENT_CANON_DEPENDENCY_PROFILE": (
            pack.dependency_profile if pack is not None else DEFAULT_DEPENDENCY_PROFILE
        ),
        "AGENT_CANON_WORKSPACE_LAYOUT": expected_workspace_layout or "<invalid>",
        "AGENT_CANON_WORKSPACE_ROOT": "/workspace",
        "AGENT_CANON_REPOSITORY_ROOT": repo_target,
        "DEPENDENCY_MODULE_CONTAINER_SOURCE": str(
            root if expected_workspace_layout == "direct-repo" else topic_root
        ),
        "DEPENDENCY_MODULE_CONTAINER_TARGET": (
            repo_target if expected_workspace_layout == "direct-repo" else "/workspace"
        ),
        "AGENT_CANON_RUNTIME_ROUTE": (
            "MANAGED_CONTAINER" if profile == "gpu-admission" else "CONTAINER_LOCAL"
        ),
        "AGENT_CANON_CODEX_SESSION_ROOT": "/home/project/.codex/sessions",
        "AGENT_CANON_SECRET_MOUNT": "/mnt/agent-canon-secrets",
    }
    if parent_layout:
        required_environment.update(
            {
                "HOME": "/home/project",
                "SHELL": pack.shell if pack is not None else "/bin/bash",
                "AGENT_CANON_CONTAINER_USER": "project",
            }
        )
    if environment is None:
        for name in required_environment:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    f"runtime-environment-required:{name}",
                )
            )
    else:
        expected_gpu_mode = "enabled" if profile == "gpu-admission" else "disabled"
        if environment.get("DEVCONTAINER_GPU_MODE") != expected_gpu_mode:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    f"{profile}-gpu-mode-mismatch",
                )
            )
        if profile == "default":
            forbidden_environment = (
                "DEVCONTAINER_GPU_REQUEST",
                "NVIDIA_VISIBLE_DEVICES",
                "NVIDIA_DRIVER_CAPABILITIES",
                "AGENT_CANON_RUNTIME_GID",
                "AGENT_CANON_HOST_SUPPLEMENTARY_GIDS",
                "ZDOTDIR",
                "AGENT_CANON_SHARED_RUNTIME_SOURCE",
                "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT",
                "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT",
            )
            for name in forbidden_environment:
                if name in environment:
                    category = (
                        "default-gpu-field-forbidden"
                        if name.startswith(("DEVCONTAINER_GPU", "NVIDIA_"))
                        else "default-shared-runtime-field-forbidden"
                    )
                    findings.append(
                        Finding(
                            "dependency_contract_violation",
                            relative,
                            f"{category}:{name}",
                        )
                    )
        else:
            required_profile_environment = {
                "DEVCONTAINER_GPU_REQUEST": "all",
                "AGENT_CANON_GPU_ADMISSION_PROFILE": "gpu-admission",
                "AGENT_CANON_RUNTIME_GID": None,
                "AGENT_CANON_HOST_SUPPLEMENTARY_GIDS": None,
                "AGENT_CANON_SHARED_RUNTIME_SOURCE": "/var/lib/agent-canon/runtime",
                "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT": "/var/lib/agent-canon/runtime/shared-runtime-provision.json",
                "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT": "/var/lib/agent-canon/runtime/shared-runtime-readback.json",
            }
            for name, expected in required_profile_environment.items():
                if name not in environment:
                    findings.append(
                        Finding(
                            "dependency_contract_violation",
                            relative,
                            f"gpu-admission-environment-required:{name}",
                        )
                    )
                elif expected is not None and environment.get(name) != expected:
                    findings.append(
                        Finding(
                            "inconsistency",
                            relative,
                            f"gpu-admission-environment:{name}",
                        )
                    )
        for name, expected in required_environment.items():
            if name not in environment:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"runtime-environment-required:{name}",
                    )
                )
            elif environment.get(name) != expected:
                findings.append(
                    Finding("inconsistency", relative, f"{name.lower()}-env")
                )
        if parent_layout:
            manifest_names, manifest_findings = parse_parent_environment_manifest(
                root / PARENT_ENVIRONMENT_MANIFEST
            )
            if not manifest_findings:
                for name in manifest_names:
                    if name in environment:
                        findings.append(
                            Finding(
                                "dependency_contract_violation",
                                relative,
                                f"parent-variable-in-compose:{name}",
                            )
                        )
    return findings


def validate_generated_compose_scenarios(
    root: Path, pack: PackConfig | None
) -> list[Finding]:
    """Generate and validate the mandatory default and GPU-admission scenarios."""
    script_path = shared_devcontainer_dir(root) / "generate-runtime-compose.sh"
    if not script_path.is_file() or script_path.stat().st_mode & 0o111 == 0:
        return []
    findings: list[Finding] = []
    with tempfile.TemporaryDirectory(prefix="agent-canon-container-config-") as tmp_dir:
        temporary_root = Path(tmp_dir)
        base_environment = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith(
                ("AGENT_CANON_", "DEVCONTAINER_", "NVIDIA_", "PROJECT_")
            )
        }
        base_environment.update(
            {
                "HOME": str(temporary_root / "home-without-host-state"),
                "PROJECT_UID": "1000",
                "PROJECT_GID": "1000",
                "AGENT_CANON_DEVCONTAINER_REPO_ROOT": str(root.resolve()),
            }
        )
        scenarios = (
            ("default", {}),
            (
                "gpu-admission",
                {
                    "AGENT_CANON_GPU_ADMISSION_PROFILE": "gpu-admission",
                    "AGENT_CANON_OPTIONAL_MOUNTS": "shared-runtime",
                    "AGENT_CANON_RUNTIME_GID": "4242",
                    "AGENT_CANON_HOST_SUPPLEMENTARY_GIDS": "1000 4242 5000",
                    "AGENT_CANON_SHARED_RUNTIME_SOURCE": "/var/lib/agent-canon/runtime",
                    "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT": "/var/lib/agent-canon/runtime/shared-runtime-provision.json",
                    "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT": "/var/lib/agent-canon/runtime/shared-runtime-readback.json",
                },
            ),
        )
        for profile, additions in scenarios:
            compose_path = temporary_root / f"{profile}.yml"
            environment = {
                **base_environment,
                **additions,
                "AGENT_CANON_DOCKER_COMPOSE_OUTPUT": str(compose_path),
            }
            result = subprocess.run(
                ["bash", str(script_path)],
                cwd=root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                stderr_lines = result.stderr.strip().splitlines()
                detail = stderr_lines[-1] if stderr_lines else "no-stderr"
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        script_path.relative_to(root).as_posix(),
                        f"{profile}-scenario-generation-failed:rc={result.returncode}:{detail}",
                    )
                )
                continue
            findings.extend(
                validate_generated_compose(
                    root,
                    pack,
                    profile=profile,
                    compose_path=compose_path,
                )
            )
    return findings


def validate_devcontainer(root: Path) -> list[Finding]:
    """Validate shared devcontainer entrypoint configuration."""
    devcontainer_dir = root / ".devcontainer"
    if not devcontainer_dir.exists():
        return []
    findings: list[Finding] = []
    json_path = devcontainer_dir / "devcontainer.json"
    if not json_path.is_file():
        return [Finding("missing_file", ".devcontainer/devcontainer.json", "missing")]
    config, json_findings = load_devcontainer_json(json_path)
    findings.extend(json_findings)
    if config is None:
        return findings

    findings.extend(validate_devcontainer_json(config))
    findings.extend(validate_generate_runtime_compose_script(root))
    findings.extend(validate_post_create(root))
    findings.extend(validate_default_lifecycle_scripts(root))
    findings.extend(validate_gpu_admission_selector(root))
    dependency_module_change = (
        shared_agent_tools_dir(root) / "dependency_module_change.py"
    )
    if (root / ".gitmodules").is_file() and not dependency_module_change.is_file():
        findings.append(
            Finding(
                "missing_file",
                dependency_module_change.relative_to(root).as_posix(),
                "required-for-devcontainer-dependency-check",
            )
        )
    return findings


def shared_agent_tools_dir(root: Path) -> Path:
    """Locate shared agent tools in standalone or parent-projected layouts."""
    direct = root / "tools" / "agent_tools"
    if direct.is_dir():
        return direct
    return root / "tools" / "agent-canon" / "agent_tools"


def validate_devcontainer_pack_alignment(
    root: Path, pack: PackConfig | None
) -> list[Finding]:
    """Validate devcontainer paths that depend on the repo-local runtime pack."""
    devcontainer_dir = root / ".devcontainer"
    json_path = devcontainer_dir / "devcontainer.json"
    if not json_path.is_file():
        return []
    config, json_findings = load_devcontainer_json(json_path)
    if config is None:
        return json_findings
    findings = [
        *json_findings,
        *validate_devcontainer_workspace(config, pack),
        *validate_generated_compose_scenarios(root, pack),
    ]
    persisted_compose = (
        root / ".agent-canon" / "docker-compose.generated.yml"
        if (root / "vendor" / "agent-canon").is_dir()
        else root / ".devcontainer" / "docker-compose.generated.yml"
    )
    if persisted_compose.exists():
        findings.extend(
            validate_generated_compose(root, pack, compose_path=persisted_compose)
        )
    profile_compose = root / ".agent-canon" / "gpu-admission-compose.generated.yml"
    if profile_compose.exists():
        findings.extend(
            validate_generated_compose(
                root,
                pack,
                profile="gpu-admission",
                compose_path=profile_compose,
            )
        )
    return findings


def has_vscode_contract(root: Path) -> bool:
    """Return whether this root declares an AgentCanon VS Code surface."""
    vscode_dir = root / ".vscode"
    vendor_manifest = (
        root / "vendor" / "agent-canon" / "documents" / "shared-runtime-surfaces.toml"
    )
    return (
        (root / "documents" / "shared-runtime-surfaces.toml").is_file()
        or vendor_manifest.is_file()
        or vscode_dir.exists()
        or vscode_dir.is_symlink()
    )


def load_shared_surface_manifest(
    root: Path,
) -> tuple[SurfaceManifest | None, list[Finding]]:
    """Load the shared runtime surface manifest through its canonical parser."""
    try:
        return load_manifest(
            root, "vendor/agent-canon", "documents/runtime/shared-runtime-surfaces.toml"
        ), []
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        return None, [
            Finding(
                "invalid_manifest",
                "documents/runtime/shared-runtime-surfaces.toml",
                f"load-failed:{exc}",
            )
        ]


def load_vscode_surface(
    root: Path,
) -> tuple[SurfaceEntry | None, SurfaceManifest | None, list[Finding]]:
    """Load the .vscode entry from the shared runtime surface manifest."""
    manifest, findings = load_shared_surface_manifest(root)
    if manifest is None:
        return None, None, findings
    entry = next(
        (candidate for candidate in manifest.entries if candidate.path == ".vscode"),
        None,
    )
    if entry is None:
        return (
            None,
            manifest,
            [
                Finding(
                    "dependency_contract_violation",
                    "documents/runtime/shared-runtime-surfaces.toml",
                    "missing-surface:.vscode",
                )
            ],
        )
    return entry, manifest, []


VSCODE_SHARED_FILES = (
    "c_cpp_properties.json",
    "extensions.json",
    "settings.json",
    "tasks.json",
)


def validate_vscode_manifest(
    entry: SurfaceEntry, manifest: SurfaceManifest
) -> list[Finding]:
    """Validate the real .vscode container and exact shared-file coverage."""
    findings: list[Finding] = []
    expected = {
        "mode": "regular",
        "owner": "template-or-derived-repo",
        "surface_class": "active_contract",
    }
    actual = {
        "mode": entry.mode,
        "owner": entry.owner,
        "surface_class": entry.surface_class,
    }
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    "documents/runtime/shared-runtime-surfaces.toml",
                    f".vscode-{field}-expected:{expected_value}",
                )
            )
    shared = {
        candidate.path: candidate
        for candidate in manifest.entries
        if candidate.path.startswith(".vscode/")
    }
    expected_paths = {f".vscode/{name}" for name in VSCODE_SHARED_FILES}
    if set(shared) != expected_paths:
        findings.append(
            Finding(
                "dependency_contract_violation",
                "documents/runtime/shared-runtime-surfaces.toml",
                "vscode-source-coverage",
            )
        )
    for path in expected_paths:
        candidate = shared.get(path)
        if candidate is None:
            continue
        if (
            candidate.mode != "symlink"
            or candidate.owner != "agent-canon"
            or candidate.surface_class != "runtime_surface"
        ):
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    "documents/runtime/shared-runtime-surfaces.toml",
                    f"vscode-file-surface:{path}",
                )
            )
    return findings


def validate_vscode(root: Path) -> list[Finding]:
    """Validate shared VS Code surface ownership."""
    entry, manifest, findings = load_vscode_surface(root)
    if entry is None or manifest is None:
        return findings
    findings.extend(validate_vscode_manifest(entry, manifest))
    root_vscode = root / ".vscode"
    if root_vscode.is_symlink():
        findings.append(Finding("inconsistency", ".vscode", "expected-real-directory"))
        return findings
    source_checkout = not (
        root
        / "vendor"
        / "agent-canon"
        / "documents"
        / "runtime"
        / "shared-runtime-surfaces.toml"
    ).is_file()
    source_relative = ".vscode" if source_checkout else f"{manifest.prefix}/.vscode"
    source_dir = root / source_relative
    if source_dir.is_symlink() or not source_dir.is_dir():
        findings.append(Finding("inconsistency", ".vscode", "expected-real-directory"))
        return findings
    shared = {
        candidate.path: candidate
        for candidate in manifest.entries
        if candidate.path.startswith(".vscode/")
    }
    for name in VSCODE_SHARED_FILES:
        path = f".vscode/{name}"
        source_file = source_dir / name
        if not source_file.is_file():
            findings.append(
                Finding("missing_file", f"{source_relative}/{name}", "missing")
            )
        root_file = root / path
        if source_checkout:
            if source_file.is_symlink():
                findings.append(
                    Finding("inconsistency", path, "source-file-must-be-regular")
                )
        elif path in shared:
            if not root_file.is_symlink():
                findings.append(
                    Finding("inconsistency", path, "expected-individual-symlink")
                )
                continue
            expected_target = target_for_entry(root, manifest.prefix, shared[path])
            target = root_file.readlink()
            target_path = target if target.is_absolute() else root_file.parent / target
            try:
                matches = target_path.resolve(strict=True) == source_file.resolve(
                    strict=True
                )
            except FileNotFoundError:
                matches = False
            if target.as_posix() != expected_target and not matches:
                findings.append(
                    Finding(
                        "inconsistency", path, "unexpected-individual-symlink-target"
                    )
                )
    if not source_checkout:
        allowed = set(VSCODE_SHARED_FILES)
        for child in (root / ".vscode").iterdir():
            if child.name not in allowed:
                findings.append(
                    Finding(
                        "inconsistency", str(child.relative_to(root)), "unexpected-file"
                    )
                )
    return findings


def validate(root: Path) -> ValidationReport:
    """Run all container configuration checks."""
    root = root.resolve()
    docker_dir = root / "docker"
    devcontainer_dir = root / ".devcontainer"
    vscode_configured = has_vscode_contract(root)
    if (
        not docker_dir.exists()
        and not devcontainer_dir.exists()
        and not vscode_configured
    ):
        return ValidationReport("skip", (), (), ())

    findings: list[Finding] = []
    checked: list[str] = []
    packs: list[PackConfig] = []
    if docker_dir.exists():
        checked.extend(
            (
                ".dockerignore",
                "docker/Dockerfile",
                "docker/requirements.txt",
                "docker/packs",
            )
        )
        findings.extend(validate_dockerignore(root))
        findings.extend(validate_dockerfile(root))
        findings.extend(validate_python_dependency_installer(root))
        findings.extend(validate_requirements(root))
        packs_dir = docker_dir / "packs"
        if not packs_dir.is_dir():
            findings.append(Finding("missing_file", "docker/packs", "missing"))
        else:
            pack_paths = sorted(packs_dir.glob("*.toml"))
            if not pack_paths:
                findings.append(
                    Finding("missing_file", "docker/packs", "no-pack-files")
                )
            for pack_path in pack_paths:
                pack, pack_findings = load_pack(root, pack_path)
                findings.extend(pack_findings)
                if pack is not None:
                    packs.append(pack)

    default_pack = next(
        (pack for pack in packs if pack.path == "docker/packs/default.toml"), None
    )
    if devcontainer_dir.exists():
        checked.append(".devcontainer")
        findings.extend(validate_devcontainer(root))
        findings.extend(validate_devcontainer_pack_alignment(root, default_pack))
    if vscode_configured:
        checked.append(".vscode")
        findings.extend(validate_vscode(root))

    sorted_findings = tuple(
        sorted(
            findings, key=lambda finding: (finding.kind, finding.path, finding.detail)
        )
    )
    return ValidationReport(
        "fail" if sorted_findings else "pass",
        sorted_findings,
        tuple(packs),
        tuple(checked),
    )


def render_json(report: ValidationReport) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": report.status,
            "findings": [asdict(finding) for finding in report.findings],
            "packs": [asdict(pack) for pack in report.packs],
            "checked": list(report.checked),
        },
        indent=2,
        sort_keys=True,
    )


def render_text(report: ValidationReport) -> None:
    """Render text output."""
    for finding in report.findings:
        print(finding.render())
    for pack in report.packs:
        print(
            "CONTAINER_CONFIG_PACK="
            f"{pack.name}\tpath={pack.path}\tdockerfile={pack.dockerfile}\t"
            f"context={pack.context}\tworkdir={pack.workdir}\t"
            f"workspace_mount={pack.workspace_mount}\tplatform={pack.platform}\t"
            f"dependency_profile={pack.dependency_profile}"
        )
    print(
        f"CONTAINER_CONFIG_CHECKED={','.join(report.checked) if report.checked else 'none'}"
    )
    print(f"CONTAINER_CONFIG_FINDINGS={len(report.findings)}")
    print(f"CONTAINER_CONFIG={report.status}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the validator."""
    args = build_parser().parse_args(argv)
    report = validate(Path(args.root))
    if args.format == "json":
        print(render_json(report))
    else:
        render_text(report)
    if report.status == "fail":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
