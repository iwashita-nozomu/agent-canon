#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates Dockerfile, runtime pack, devcontainer, and shared VS Code surface configuration.
# upstream design ../../documents/coding-conventions-project.md environment configuration policy
# upstream design ../../documents/shared-runtime-surfaces.toml machine-readable shared runtime surface ownership
# upstream design ../../documents/github-first-module-and-devcontainer-policy.md Dockerfile/devcontainer ownership boundary
# upstream design ../../documents/gpu-admission-r5-source-packet.md exact runtime identity validation contract
# upstream design ../../documents/rust-agent-tool-migration.md Rust toolchain devcontainer boundary
# upstream design ../../agents/skills/academic-writing.md Academic Writing TeX tooling boundary
# upstream design ../../documents/tools/lean_proof_env.md Lean proof environment toolchain boundary
# upstream design ../../agents/skills/environment-maintenance.md environment change workflow
# upstream implementation ../agent_tools/surface_manifest.py parses shared runtime surface manifests
# upstream implementation ../docker_dependency_validator.sh validates Docker dependency contents
# upstream implementation ./container_runtime.py loads runtime pack contracts
# upstream implementation ./run_container_pack.py builds and smokes runtime packs
# downstream implementation ./run_all_checks.sh runs container configuration validation
# downstream implementation ../../tests/tools/test_container_config.py tests validator
# @dependency-end
"""Validate Dockerfile, runtime pack, devcontainer, and shared VS Code surfaces."""

from __future__ import annotations

import argparse
import json
import re
import sys

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

from surface_manifest import SurfaceEntry, SurfaceManifest, load_manifest, target_for_entry  # noqa: E402,I001

REQUIRED_REQUIREMENTS = (
    "jupyterlab",
    "notebook",
    "ipykernel",
    "pydeps",
    "snakeviz",
    "pyyaml",
)
REQUIREMENT_RE = re.compile(
    r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?"
    r"(?:\s*(?:==|>=|<=|~=|!=|>|<).+)?$"
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
    workdir: str
    workspace_mount: str


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
        return (), Finding("invalid_manifest", source, f"{section}.{key}-must-be-string-list")
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
        findings.append(Finding("invalid_manifest", source, f"{field}-escapes-repo:{value}"))
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
        return None, [Finding("invalid_manifest", source, "pack-smoke-runtime-required")]

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
        findings.append(Finding("invalid_manifest", source, "pack.target-must-be-string"))

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
    if not isinstance(workdir, str):
        findings.append(Finding("invalid_manifest", source, "runtime.workdir-must-be-string"))
        workdir = ""
    if not isinstance(workspace_mount, str):
        findings.append(
            Finding("invalid_manifest", source, "runtime.workspace_mount-must-be-string")
        )
        workspace_mount = ""

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
            workdir=workdir,
            workspace_mount=workspace_mount,
        ),
        [],
    )


def trim_requirement_line(line: str) -> str:
    """Strip comments and surrounding whitespace from one requirement line."""
    return line.split("#", 1)[0].strip()


def validate_requirements(root: Path) -> list[Finding]:
    """Validate docker/requirements.txt."""
    path = root / "docker" / "requirements.txt"
    relative = "docker/requirements.txt"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    findings: list[Finding] = []
    requirements: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = trim_requirement_line(raw_line)
        if not line:
            continue
        if not REQUIREMENT_RE.fullmatch(line):
            findings.append(
                Finding("dependency_contract_violation", relative, f"invalid-line:{line_number}")
            )
            continue
        name = re.split(r"[\[<>=~!\s]", line, maxsplit=1)[0].lower()
        requirements.add(name)
    for requirement in REQUIRED_REQUIREMENTS:
        if requirement not in requirements:
            findings.append(
                Finding("dependency_contract_violation", relative, f"missing:{requirement}")
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
                Finding("dependency_contract_violation", relative, f"missing-ignore:{ignored_path}")
            )
    return findings


def validate_post_create(root: Path) -> list[Finding]:
    """Require the post-create entrypoint without fixing its shell implementation."""
    path = root / ".devcontainer" / "post-create.sh"
    relative = ".devcontainer/post-create.sh"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    return []


def validate_finalize_shared_runtime_script(devcontainer_dir: Path) -> list[Finding]:
    """Require the shared-runtime finalizer without fixing its shell implementation."""
    path = devcontainer_dir / "finalize-shared-runtime.sh"
    relative = ".devcontainer/finalize-shared-runtime.sh"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    return []


def validate_python_dependency_installer(root: Path) -> list[Finding]:
    """Require the optional dependency installer without fixing shell internals."""
    path = root / "docker" / "install_python_dependencies.sh"
    relative = "docker/install_python_dependencies.sh"
    if not path.is_file():
        return [Finding("missing_file", relative, "missing")]
    return []


def load_devcontainer_json(path: Path) -> tuple[Mapping[str, object] | None, list[Finding]]:
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
        "initializeCommand": "bash .devcontainer/bootstrap-shared-runtime.sh && bash .devcontainer/generate-runtime-compose.sh",
        "dockerComposeFile": "docker-compose.generated.yml",
        "service": "workspace",
        "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",
        "postCreateCommand": "bash .devcontainer/post-create.sh /workspace/${localWorkspaceFolderBasename}",
        "postAttachCommand": "bash .devcontainer/post-attach.sh",
    }
    for key, expected in expected_json.items():
        if config.get(key) != expected:
            findings.append(
                Finding("inconsistency", ".devcontainer/devcontainer.json", f"{key}-expected:{expected}")
            )
    return findings


def validate_devcontainer_workspace(config: Mapping[str, object], pack: PackConfig | None) -> list[Finding]:
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


def validate_generate_runtime_compose_script(devcontainer_dir: Path) -> list[Finding]:
    """Require the generator entrypoint without depending on its implementation text."""
    script_path = devcontainer_dir / "generate-runtime-compose.sh"
    if not script_path.is_file():
        return [Finding("missing_file", ".devcontainer/generate-runtime-compose.sh", "missing")]
    return []


def validate_generated_compose(devcontainer_dir: Path, pack: PackConfig | None) -> list[Finding]:
    """Validate generated Compose meaning rather than generator implementation text."""
    del pack
    compose_path = devcontainer_dir / "docker-compose.generated.yml"
    if not compose_path.exists():
        return []
    relative = ".devcontainer/docker-compose.generated.yml"
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
    root = devcontainer_dir.parent.resolve()
    topic_root = root.parent.resolve()
    repo_target = f"/workspace/{root.name}"
    findings: list[Finding] = []
    if topic_root.parent.name != "workspace":
        findings.append(Finding("dependency_contract_violation", relative, "topic-root-parent"))
    if service.get("working_dir") != repo_target:
        findings.append(Finding("inconsistency", relative, f"working-dir:{service.get('working_dir')}"))
    build = as_mapping(service.get("build"))
    if build is not None and build.get("context") != "..":
        findings.append(Finding("inconsistency", relative, f"build-context:{build.get('context')}"))
    volumes = as_sequence(service.get("volumes"))
    if volumes is None:
        return [*findings, Finding("invalid_manifest", relative, "workspace-volumes-required")]

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

    def source_path(source: str | None) -> Path | None:
        if not source:
            return None
        candidate = Path(source)
        return (candidate if candidate.is_absolute() else devcontainer_dir / candidate).resolve()

    workspace_mounts: list[tuple[str | None, str | None]] = []
    for raw_volume in volumes:
        source, target = volume_fields(raw_volume)
        if target == "/workspace":
            workspace_mounts.append((source, target))
    if len(workspace_mounts) != 1:
        findings.append(Finding("dependency_contract_violation", relative, f"workspace-mount-count:{len(workspace_mounts)}"))
    elif source_path(workspace_mounts[0][0]) != topic_root:
        findings.append(Finding("dependency_contract_violation", relative, "workspace-source"))
    for raw_volume in volumes:
        source, target = volume_fields(raw_volume)
        if source_path(source) == root or target == repo_target:
            findings.append(Finding("dependency_contract_violation", relative, "repository-double-mount"))
    required_environment = {
        "AGENT_CANON_WORKSPACE_ROOT": "/workspace",
        "AGENT_CANON_REPOSITORY_ROOT": repo_target,
    }
    environment = as_mapping(service.get("environment"))
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
                findings.append(Finding("inconsistency", relative, f"{name.lower()}-env"))
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
    findings.extend(validate_finalize_shared_runtime_script(devcontainer_dir))
    post_attach = devcontainer_dir / "post-attach.sh"
    if not post_attach.is_file():
        findings.append(Finding("missing_file", ".devcontainer/post-attach.sh", "missing"))
    findings.extend(validate_generate_runtime_compose_script(devcontainer_dir))
    findings.extend(validate_post_create(root))
    if (root / ".gitmodules").is_file() and not (
        root / "tools" / "agent_tools" / "dependency_module_change.py"
    ).is_file():
        findings.append(
            Finding(
                "missing_file",
                "tools/agent_tools/dependency_module_change.py",
                "required-for-devcontainer-dependency-check",
            )
        )
    return findings


def validate_devcontainer_pack_alignment(root: Path, pack: PackConfig | None) -> list[Finding]:
    """Validate devcontainer paths that depend on the repo-local runtime pack."""
    devcontainer_dir = root / ".devcontainer"
    json_path = devcontainer_dir / "devcontainer.json"
    if not json_path.is_file():
        return []
    config, json_findings = load_devcontainer_json(json_path)
    if config is None:
        return json_findings
    return [
        *json_findings,
        *validate_devcontainer_workspace(config, pack),
        *validate_generated_compose(devcontainer_dir, pack),
    ]


def has_vscode_contract(root: Path) -> bool:
    """Return whether this root declares an AgentCanon VS Code surface."""
    vscode_dir = root / ".vscode"
    vendor_manifest = root / "vendor" / "agent-canon" / "documents" / "shared-runtime-surfaces.toml"
    return (
        (root / "documents" / "shared-runtime-surfaces.toml").is_file()
        or vendor_manifest.is_file()
        or vscode_dir.exists()
        or vscode_dir.is_symlink()
    )


def load_shared_surface_manifest(root: Path) -> tuple[SurfaceManifest | None, list[Finding]]:
    """Load the shared runtime surface manifest through its canonical parser."""
    try:
        return load_manifest(root, "vendor/agent-canon", "documents/shared-runtime-surfaces.toml"), []
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        return None, [
            Finding(
                "invalid_manifest",
                "documents/shared-runtime-surfaces.toml",
                f"load-failed:{exc}",
            )
        ]


def load_vscode_surface(root: Path) -> tuple[SurfaceEntry | None, SurfaceManifest | None, list[Finding]]:
    """Load the .vscode entry from the shared runtime surface manifest."""
    manifest, findings = load_shared_surface_manifest(root)
    if manifest is None:
        return None, None, findings
    entry = next((candidate for candidate in manifest.entries if candidate.path == ".vscode"), None)
    if entry is None:
        return (
            None,
            manifest,
            [
                Finding(
                    "dependency_contract_violation",
                    "documents/shared-runtime-surfaces.toml",
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


def validate_vscode_manifest(entry: SurfaceEntry, manifest: SurfaceManifest) -> list[Finding]:
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
                    "documents/shared-runtime-surfaces.toml",
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
                "documents/shared-runtime-surfaces.toml",
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
                    "documents/shared-runtime-surfaces.toml",
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
    source_checkout = not (root / "vendor" / "agent-canon" / "documents" / "shared-runtime-surfaces.toml").is_file()
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
            findings.append(Finding("missing_file", f"{source_relative}/{name}", "missing"))
        root_file = root / path
        if source_checkout:
            if source_file.is_symlink():
                findings.append(Finding("inconsistency", path, "source-file-must-be-regular"))
        elif path in shared:
            if not root_file.is_symlink():
                findings.append(Finding("inconsistency", path, "expected-individual-symlink"))
                continue
            expected_target = target_for_entry(root, manifest.prefix, shared[path])
            target = root_file.readlink()
            target_path = target if target.is_absolute() else root_file.parent / target
            try:
                matches = target_path.resolve(strict=True) == source_file.resolve(strict=True)
            except FileNotFoundError:
                matches = False
            if target.as_posix() != expected_target and not matches:
                findings.append(Finding("inconsistency", path, "unexpected-individual-symlink-target"))
    if not source_checkout:
        allowed = set(VSCODE_SHARED_FILES)
        for child in (root / ".vscode").iterdir():
            if child.name not in allowed:
                findings.append(Finding("inconsistency", str(child.relative_to(root)), "unexpected-file"))
    return findings

def validate(root: Path) -> ValidationReport:
    """Run all container configuration checks."""
    root = root.resolve()
    docker_dir = root / "docker"
    devcontainer_dir = root / ".devcontainer"
    vscode_configured = has_vscode_contract(root)
    if not docker_dir.exists() and not devcontainer_dir.exists() and not vscode_configured:
        return ValidationReport("skip", (), (), ())

    findings: list[Finding] = []
    checked: list[str] = []
    packs: list[PackConfig] = []
    if docker_dir.exists():
        checked.extend((".dockerignore", "docker/Dockerfile", "docker/requirements.txt", "docker/packs"))
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
                findings.append(Finding("missing_file", "docker/packs", "no-pack-files"))
            for pack_path in pack_paths:
                pack, pack_findings = load_pack(root, pack_path)
                findings.extend(pack_findings)
                if pack is not None:
                    packs.append(pack)

    default_pack = next((pack for pack in packs if pack.path == "docker/packs/default.toml"), None)
    if devcontainer_dir.exists():
        checked.append(".devcontainer")
        findings.extend(validate_devcontainer(root))
        findings.extend(validate_devcontainer_pack_alignment(root, default_pack))
    if vscode_configured:
        checked.append(".vscode")
        findings.extend(validate_vscode(root))

    sorted_findings = tuple(
        sorted(findings, key=lambda finding: (finding.kind, finding.path, finding.detail))
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
            f"workspace_mount={pack.workspace_mount}"
        )
    print(f"CONTAINER_CONFIG_CHECKED={','.join(report.checked) if report.checked else 'none'}")
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
