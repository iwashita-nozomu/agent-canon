#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates Dockerfile, runtime pack, host-identity devcontainer, and retired VS Code projection paths.
# upstream design ../../documents/conventions/coding-conventions-project.md environment configuration policy
# upstream design ../../documents/contracts/github-first-module-and-devcontainer-policy.md Dockerfile/devcontainer ownership boundary
# upstream design ../../CONTAINER_OPERATIONS.md standalone public Docker test route
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md parent layout and runtime shell boundary
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md default startup profile boundary
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md explicit GPU-admission selector and scenario validation
# upstream design ../../documents/experiments/gpu-admission-r5-source-packet.md opt-in GPU runtime identity contract
# upstream design ../../documents/design/rust-agent-tool-migration.md Rust toolchain devcontainer boundary
# upstream design ../../agents/skills/academic-writing.md Academic Writing TeX tooling boundary
# upstream design ../../documents/tools/lean_proof_env.md Lean proof environment toolchain boundary
# upstream design ../../agents/skills/environment-maintenance.md environment change workflow
# upstream implementation ../agent_tools/devcontainer_dependencies.py typed project-extra validation and install owner
# upstream implementation ../docker_dependency_validator.sh validates Docker dependency contents
# upstream implementation ./container_runtime.py loads runtime pack contracts
# upstream implementation ./run_container_pack.py builds and smokes runtime packs
# downstream implementation ./run_all_checks.sh runs container configuration validation
# downstream implementation ../../tests/tools/test_container_config.py tests validator
# downstream implementation ../../docker/Dockerfile public source test image
# downstream implementation ../../test/testrunner.sh public source test runner
# downstream implementation ../../.devcontainer/gpu-admission/devcontainer.json selects the opt-in Compose scenario
# downstream implementation ../../.devcontainer/gpu-admission.sh owns the opt-in lifecycle scenario
# @dependency-end
"""Validate Dockerfile, runtime pack, devcontainer, and retired VS Code projections."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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

from parent_root_side_effects import (  # noqa: E402
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
    resolve_parent_writer_attestation,
)

PARENT_ENVIRONMENT_MANIFEST = ".devcontainer/parent-environment.toml"
ENVIRONMENT_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
RUNTIME_SHELL_RE = re.compile(r"/[A-Za-z0-9._/-]+\Z")
BUILD_TARGET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
OPTIONAL_MOUNT_PROFILES = frozenset(
    {
        "host-zshrc",
        "host-git",
        "host-secrets",
        "host-credentials",
        "ssh-agent",
        "docker-host",
        "linked-data-roots",
    }
)
LINKED_DATA_TARGET_RE = re.compile(r"/mnt/[a-z]/[^/].*\Z")
STANDALONE_DOCKER_CONTEXT_ALLOWLIST = (
    ".devcontainer/",
    ".devcontainer/Dockerfile",
    ".devcontainer/dependencies.toml",
    "tools/",
    "tools/agent_tools/",
    "tools/agent_tools/devcontainer_dependencies.py",
    "tools/agent_tools/parent_root_side_effects.py",
    "rust/",
    "rust/agent-canon/",
    "rust/agent-canon/src/",
    "rust/agent-canon/src/semantic_index/",
    "rust/agent-canon/tests/",
    "rust/agent-canon/Cargo.lock",
    "rust/agent-canon/Cargo.toml",
    "rust/agent-canon/src/dependency_manifest.rs",
    "rust/agent-canon/src/docs.rs",
    "rust/agent-canon/src/graph.rs",
    "rust/agent-canon/src/jit_ir_to_lean.rs",
    "rust/agent-canon/src/main.rs",
    "rust/agent-canon/src/memory.rs",
    "rust/agent-canon/src/migration_audit.rs",
    "rust/agent-canon/src/python_algorithm_contract.rs",
    "rust/agent-canon/src/python_module_groups.rs",
    "rust/agent-canon/src/python_structure_hash.rs",
    "rust/agent-canon/src/python_structure_hash_impact.rs",
    "rust/agent-canon/src/python_structure_hash_report.rs",
    "rust/agent-canon/src/python_structure_hash_scope_plan.rs",
    "rust/agent-canon/src/rust_migration_plan.rs",
    "rust/agent-canon/src/semantic_index/args.rs",
    "rust/agent-canon/src/semantic_index/cli.rs",
    "rust/agent-canon/src/semantic_index/embedding.rs",
    "rust/agent-canon/src/semantic_index/eval.rs",
    "rust/agent-canon/src/semantic_index/mod.rs",
    "rust/agent-canon/src/semantic_index/model.rs",
    "rust/agent-canon/src/semantic_index/pipeline.rs",
    "rust/agent-canon/src/semantic_index/query.rs",
    "rust/agent-canon/src/semantic_index/relations.rs",
    "rust/agent-canon/src/semantic_index/report.rs",
    "rust/agent-canon/src/semantic_index/source.rs",
    "rust/agent-canon/src/semantic_index/storage.rs",
    "rust/agent-canon/src/semantic_index/tests.rs",
    "rust/agent-canon/src/structured_analysis.rs",
    "rust/agent-canon/src/test_design.rs",
    "rust/agent-canon/tests/python_algorithm_contract_cli.rs",
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
    optional_mount_profiles: tuple[str, ...]
    linked_data_roots: tuple[LinkedDataRoot, ...]
    linked_data_roots_declared: bool


@dataclass(frozen=True)
class LinkedDataRoot:
    """One repository symlink projected to its declared host data directory."""

    link: str
    target: str


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


def is_normalized_repo_relative_link(value: str) -> bool:
    """Return whether a configured link is a normalized repository-relative path."""
    path = Path(value)
    return (
        bool(value)
        and not any(ord(char) < 32 for char in value)
        and not path.is_absolute()
        and value != "."
        and value == path.as_posix()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def is_valid_linked_data_target(value: str) -> bool:
    """Return whether a linked-data target is a narrow, non-root mount path."""
    path = Path(value)
    return bool(
        LINKED_DATA_TARGET_RE.fullmatch(value)
        and not any(ord(char) < 32 for char in value)
        and ":" not in value
        and "," not in value
        and value == path.as_posix()
        and all(part not in {"", ".", ".."} for part in path.parts)
        and value not in {"/mnt", "/mnt/l"}
    )


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
    if target_value is not None and (
        target is None or BUILD_TARGET_RE.fullmatch(target) is None
    ):
        findings.append(
            Finding("invalid_manifest", source, "pack.target-must-be-safe-build-stage")
        )
    platform_value = pack.get("platform")
    platform = platform_value if isinstance(platform_value, str) else None
    if platform_value is not None and platform is None:
        findings.append(
            Finding("invalid_manifest", source, "pack.platform-must-be-string")
        )

    optional_mount_profiles_value = runtime.get("optional_mount_profiles", ())
    optional_mount_profiles: tuple[str, ...] = ()
    if "optional_mount_profiles" in runtime:
        profile_sequence = as_sequence(optional_mount_profiles_value)
        if profile_sequence is None or not all(
            isinstance(item, str) for item in profile_sequence
        ):
            findings.append(
                Finding(
                    "invalid_manifest",
                    source,
                    "runtime.optional_mount_profiles-must-be-string-list",
                )
            )
        else:
            profiles = tuple(cast(Sequence[str], profile_sequence))
            seen_profiles: set[str] = set()
            for profile in profiles:
                if not profile or profile != profile.strip():
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            "runtime.optional_mount_profiles-empty-or-whitespace",
                        )
                    )
                elif profile not in OPTIONAL_MOUNT_PROFILES:
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            f"runtime.optional_mount_profiles-unknown:{profile}",
                        )
                    )
                if profile in seen_profiles:
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            f"runtime.optional_mount_profiles-duplicate:{profile}",
                        )
                    )
                seen_profiles.add(profile)
            optional_mount_profiles = profiles

    linked_data_roots_value = runtime.get("linked_data_roots")
    linked_data_roots: tuple[LinkedDataRoot, ...] = ()
    linked_data_roots_present = "linked_data_roots" in runtime
    if linked_data_roots_present:
        root_sequence = as_sequence(linked_data_roots_value)
        if root_sequence is None:
            findings.append(
                Finding(
                    "invalid_manifest",
                    source,
                    "runtime.linked_data_roots-must-be-inline-table-array",
                )
            )
        else:
            parsed_roots: list[LinkedDataRoot] = []
            seen_links: set[str] = set()
            seen_targets: set[str] = set()
            for index, raw_root in enumerate(root_sequence):
                root_table = as_mapping(raw_root)
                if root_table is None or set(root_table) != {"link", "target"}:
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            f"runtime.linked_data_roots-entry-{index}-must-have-link-target",
                        )
                    )
                    continue
                link = root_table.get("link")
                linked_target = root_table.get("target")
                if not isinstance(link, str) or not isinstance(linked_target, str):
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            f"runtime.linked_data_roots-entry-{index}-strings-required",
                        )
                    )
                    continue
                if not is_normalized_repo_relative_link(link):
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            f"runtime.linked_data_roots-link-invalid:{link}",
                        )
                    )
                elif not (root / link).is_symlink():
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            f"runtime.linked_data_roots-link-must-be-symlink:{link}",
                        )
                    )
                if not is_valid_linked_data_target(linked_target):
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            f"runtime.linked_data_roots-target-invalid:{linked_target}",
                        )
                    )
                if link in seen_links:
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            f"runtime.linked_data_roots-link-duplicate:{link}",
                        )
                    )
                if linked_target in seen_targets:
                    findings.append(
                        Finding(
                            "invalid_manifest",
                            source,
                            f"runtime.linked_data_roots-target-duplicate:{linked_target}",
                        )
                    )
                seen_links.add(link)
                seen_targets.add(linked_target)
                parsed_roots.append(LinkedDataRoot(link=link, target=linked_target))
            linked_data_roots = tuple(parsed_roots)
    if ("linked-data-roots" in optional_mount_profiles) != linked_data_roots_present:
        findings.append(
            Finding(
                "invalid_manifest",
                source,
                "runtime.linked-data-roots-profile-and-list-must-match",
            )
        )
    if "linked-data-roots" in optional_mount_profiles and not linked_data_roots:
        findings.append(
            Finding(
                "invalid_manifest",
                source,
                "runtime.linked_data_roots-must-be-non-empty-when-selected",
            )
        )

    runtime_env: tuple[str, ...] = ()
    for table, key, section in (
        (smoke, "commands", "smoke"),
        (runtime, "env", "runtime"),
    ):
        values, finding = require_string_list(table, key, source, section)
        if finding is not None:
            findings.append(finding)
        elif section == "runtime":
            runtime_env = values
    if any(item.partition("=")[0] == "AGENT_CANON_PYTHON_EXTRAS" for item in runtime_env):
        findings.append(
            Finding(
                "dependency_contract_violation",
                source,
                "runtime.env-cannot-override:AGENT_CANON_PYTHON_EXTRAS",
            )
        )
    runtime_mounts, mounts_finding = require_string_list(
        runtime, "mounts", source, "runtime"
    )
    if mounts_finding is not None:
        findings.append(mounts_finding)
    elif runtime_mounts:
        findings.append(
            Finding(
                "dependency_contract_violation",
                source,
                "runtime.mounts-unsupported-use-optional-profile",
            )
        )
    workdir = runtime.get("workdir", "/workspace")
    workspace_mount = runtime.get("workspace_mount", "/workspace")
    shell = runtime.get("shell", "/bin/bash")
    if "dependency_extras" in runtime:
        findings.append(
            Finding(
                "dependency_contract_violation",
                source,
                "runtime.dependency_extras-forbidden-image-owned",
            )
        )
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
    pack_shell = shell if isinstance(shell, str) else "/bin/bash"

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
            shell=pack_shell,
            workdir=workdir,
            workspace_mount=workspace_mount,
            platform=platform,
            optional_mount_profiles=optional_mount_profiles,
            linked_data_roots=linked_data_roots,
            linked_data_roots_declared=linked_data_roots_present,
        ),
        [],
    )


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
    public_test_image = all(
        (root / relative).is_file()
        for relative in (
            "docker/Dockerfile",
            "test/testrunner.sh",
            "test/testlist.toml",
        )
    )
    ignored_paths = (".state", "vendor/agent-canon")
    if not public_test_image:
        ignored_paths = (".git", *ignored_paths)
    for ignored_path in ignored_paths:
        if not re.search(rf"(^|\n){re.escape(ignored_path)}(\n|$)", text):
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    f"missing-ignore:{ignored_path}",
                )
            )
    if public_test_image:
        findings.extend(validate_public_test_git_context(root))
    return findings


def validate_public_test_git_context(root: Path) -> list[Finding]:
    """Admit Git history while excluding host identity and mutable Git state."""
    dockerignore = root / ".dockerignore"
    dockerfile = root / "docker" / "Dockerfile"
    findings: list[Finding] = []
    if not dockerignore.is_file():
        return [Finding("missing_file", ".dockerignore", "missing")]
    if not dockerfile.is_file():
        return [Finding("missing_file", "docker/Dockerfile", "missing")]

    patterns = tuple(
        line.strip()
        for line in dockerignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    required_sequence = (
        ".git/*",
        "!.git/HEAD",
        "!.git/objects/",
        "!.git/objects/**",
        ".git/objects/info/",
        ".git/objects/info/**",
        "!.git/refs/",
        ".git/refs/*",
        "!.git/refs/heads/",
        "!.git/refs/heads/**",
        "!.git/packed-refs",
        ".git/config",
        ".git/index",
        ".git/logs/",
        ".git/logs/**",
        ".git/hooks/",
        ".git/hooks/**",
        ".git/worktrees/",
        ".git/worktrees/**",
    )
    previous = -1
    for pattern in required_sequence:
        try:
            position = patterns.index(pattern)
        except ValueError:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    ".dockerignore",
                    f"public-git-context-rule-missing:{pattern}",
                )
            )
            continue
        if position <= previous:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    ".dockerignore",
                    f"public-git-context-rule-order:{pattern}",
                )
            )
        previous = position

    allowed_git_negations = frozenset(
        {
            "!.git/HEAD",
            "!.git/objects/",
            "!.git/objects/**",
            "!.git/refs/",
            "!.git/refs/heads/",
            "!.git/refs/heads/**",
            "!.git/packed-refs",
        }
    )
    for pattern in patterns:
        if pattern.startswith("!.git") and pattern not in allowed_git_negations:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    ".dockerignore",
                    f"public-git-context-unsafe-allow:{pattern}",
                )
            )

    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    logical_lines = re.sub(r"\\\r?\n", " ", dockerfile_text)
    normalized = re.sub(r"\s+", " ", logical_lines)
    # Keep this static oracle aligned with the immutable Git state read back
    # by docker/Dockerfile.  Each positive rule is intentionally paired with
    # one command shape so a removed readback cannot hide behind the setup
    # command that created the state.
    dockerfile_rules = {
        "history-head-required": r"rev-parse --verify HEAD\^\{commit\}",
        "ref-normalization-required": r"for-each-ref .* refs .*update-ref -d",
        "main-head-readback-required": (
            r'test "\$\(git -C "\$\{source_root\}" symbolic-ref HEAD\)" '
            r'= "refs/heads/main"'
        ),
        "main-commit-readback-required": (
            r'test "\$\(git -C "\$\{source_root\}" rev-parse HEAD\)" '
            r'= "\$\(git -C "\$\{source_root\}" rev-parse refs/heads/main\)"'
        ),
        "source-origin-name-readback-required": r'git -C "\$\{source_root\}" remote\)" = "origin"',
        "parent-origin-name-readback-required": r'git -C "\$\{parent_root\}" remote\)" = "origin"',
        "source-origin-url-readback-required": (
            r'test "\$\(git -C "\$\{source_root\}" remote get-url origin\)" '
            r"= 'https://github\.com/iwashita-nozomu/agent-canon\.git'"
        ),
        "parent-origin-url-readback-required": (
            r'test "\$\(git -C "\$\{parent_root\}" remote get-url origin\)" '
            r"= 'https://github\.com/iwashita-nozomu/project_template\.git'"
        ),
        "remote-ref-readback-required": r'git -C "\$\{source_root\}" for-each-ref .* refs/remotes.*git -C "\$\{parent_root\}" for-each-ref .* refs/remotes',
        "credential-readback-required": r'git -C "\$\{source_root\}" config --get-regexp.*credential.*git -C "\$\{parent_root\}" config --get-regexp.*credential',
        "non-local-bare-clone-readback-required": (
            r'git clone --bare --no-local "\$\{source_root\}" '
            r'"\$\{clone_probe\}/agent-canon\.git"'
        ),
        "canonical-graph-build-required": (
            r'"\$\{runtime_root\}/tools/agent-canon/bin/agent-canon" graph build '
            r'--root "\$\{source_root\}" --profile default --format json'
        ),
        "canonical-graph-artifact-readback-required": (
            r'test -s "\$\{source_root\}/\.agent-canon/knowledge-graph/graph\.sqlite"'
        ),
        "canonical-graph-status-readback-required": (
            r'"\$\{runtime_root\}/tools/agent-canon/bin/agent-canon" graph status '
            r'--root "\$\{source_root\}" --profile default --format json'
        ),
    }
    for detail, pattern in dockerfile_rules.items():
        if re.search(pattern, normalized) is None:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    "docker/Dockerfile",
                    detail,
                )
            )
    return findings


def validate_standalone_docker_context(root: Path) -> list[Finding]:
    """Keep the standalone image context limited to its build-time engine files."""
    dockerfile = root / ".devcontainer" / "Dockerfile"
    dockerignore = root / ".dockerignore"
    findings: list[Finding] = []
    if not dockerignore.is_file():
        findings.append(Finding("missing_file", ".dockerignore", "missing"))
    else:
        patterns = tuple(
            line.strip()
            for line in dockerignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        if not patterns or patterns[0] != "**":
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    ".dockerignore",
                    "standalone-context-deny-all-required",
                )
            )
        expected_patterns = ("**",) + tuple(
            f"!{path}" for path in STANDALONE_DOCKER_CONTEXT_ALLOWLIST
        )
        if patterns != expected_patterns:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    ".dockerignore",
                    "standalone-context-allowlist-mismatch",
                )
            )
    if dockerfile.is_file():
        dockerfile_text = dockerfile.read_text(encoding="utf-8")
        normalized_dockerfile = re.sub(r"\s+", " ", dockerfile_text)
        if re.search(r"^\s*COPY\s+\.\s", dockerfile_text, flags=re.MULTILINE):
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    ".devcontainer/Dockerfile",
                    "standalone-context-copy-dot-forbidden",
                )
            )
        if "image_vendor_root" in dockerfile_text or "vendor/agent-canon" in dockerfile_text:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    ".devcontainer/Dockerfile",
                    "standalone-context-conditional-vendor-root-forbidden",
                )
            )
        required_copies = (
            "COPY .devcontainer/dependencies.toml /opt/agent-canon/.devcontainer/dependencies.toml",
            "COPY tools/agent_tools/devcontainer_dependencies.py /opt/agent-canon/tools/agent_tools/devcontainer_dependencies.py",
            "COPY tools/agent_tools/parent_root_side_effects.py /opt/agent-canon/tools/agent_tools/parent_root_side_effects.py",
        )
        for required_copy in required_copies:
            if required_copy not in dockerfile_text:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        ".devcontainer/Dockerfile",
                        f"standalone-context-required-copy-missing:{required_copy}",
                    )
                )
        if (
            "image-install --workspace /opt/agent-canon --vendor-root /opt/agent-canon"
            not in normalized_dockerfile
        ):
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    ".devcontainer/Dockerfile",
                    "standalone-context-fixed-vendor-root-required",
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


def load_devcontainer_json(
    path: Path,
    *,
    relative: str = ".devcontainer/devcontainer.json",
) -> tuple[Mapping[str, object] | None, list[Finding]]:
    """Load .devcontainer/devcontainer.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [Finding("invalid_manifest", relative, f"json-decode:{exc}")]
    mapping = as_mapping(data)
    if mapping is None:
        return None, [Finding("invalid_manifest", relative, "must-be-object")]
    return mapping, []


def expected_post_create_command(*, parent_layout: bool) -> str:
    """Return the lifecycle command for standalone or parent-projected layouts."""
    resolver = (
        "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec"
    )
    entrypoint = (
        f"{resolver} .devcontainer/post-create-entrypoint.sh "
        "/workspace/${localWorkspaceFolderBasename}"
    )
    return entrypoint


def validate_devcontainer_json(
    config: Mapping[str, object],
    *,
    parent_layout: bool = False,
    config_path: str = ".devcontainer/devcontainer.json",
) -> list[Finding]:
    """Validate required devcontainer JSON fields."""
    findings: list[Finding] = []
    if parent_layout:
        return findings
    compose_output = ".agent-canon/docker-compose.generated.yml"
    expected_name = "${localWorkspaceFolderBasename}-devcontainer"
    expected_json: dict[str, object] = {
        "name": expected_name,
        "initializeCommand": f"AGENT_CANON_DOCKER_COMPOSE_OUTPUT={compose_output} python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/generate-runtime-compose.sh",
        "dockerComposeFile": "../.agent-canon/docker-compose.generated.yml",
        "service": "workspace",
        "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",
        "postCreateCommand": expected_post_create_command(parent_layout=parent_layout),
        "postAttachCommand": "python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/post-attach.sh",
        "updateRemoteUserUID": False,
    }
    for key, expected in expected_json.items():
        if config.get(key) != expected:
            findings.append(
                Finding(
                    "inconsistency",
                    config_path,
                    f"{key}-expected:{expected}",
                )
            )
    if "features" in config:
        findings.append(
            Finding(
                "dependency_contract_violation",
                config_path,
                "node-feature-forbidden-image-owned",
            )
        )
    if "containerUser" in config:
        findings.append(
            Finding(
                "dependency_contract_violation",
                config_path,
                "default-containerUser-forbidden-compose-owned-project-identity",
            )
        )
    if "remoteUser" in config:
        findings.append(
            Finding(
                "dependency_contract_violation",
                config_path,
                "default-remoteUser-forbidden-compose-owned-project-identity",
            )
        )
    if "containerEnv" in config:
        findings.append(
            Finding(
                "dependency_contract_violation",
                config_path,
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
        "initializeCommand": "AGENT_CANON_GPU_ADMISSION_PROFILE=gpu-admission AGENT_CANON_DOCKER_COMPOSE_OUTPUT=.agent-canon/gpu-admission-compose.generated.yml python3 tools/agent-canon/agent_tools/agent_canon_source_root.py exec .devcontainer/generate-runtime-compose.sh",
        "dockerComposeFile": "../../.agent-canon/gpu-admission-compose.generated.yml",
        "service": "workspace",
        "containerUser": "project",
        "remoteUser": "project",
        "workspaceFolder": "/workspace/${localWorkspaceFolderBasename}",
        "postCreateCommand": expected_post_create_command(
            parent_layout=(root / "vendor" / "agent-canon").is_dir()
        ),
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
    orchestrator_relative = orchestrator.relative_to(root).as_posix()
    if not orchestrator.is_file() or orchestrator.stat().st_mode & 0o111 == 0:
        findings.append(
            Finding(
                "missing_file" if not orchestrator.is_file() else "dependency_contract_violation",
                orchestrator_relative,
                "executable-profile-orchestrator-required",
            )
        )
    return findings


def parse_parent_environment_manifest(path: Path) -> tuple[tuple[str, ...], list[str]]:
    """Read the ordered parent-environment variable-name manifest."""
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return (), ["toml-decode:invalid-or-unreadable-file"]
    if set(data) != {"variables"}:
        return (), ["toml-keys-must-be-variables-only"]
    variables = data.get("variables")
    if not isinstance(variables, list):
        return (), ["variables-must-be-string-list"]
    variable_values = cast(list[object], variables)
    if not all(isinstance(item, str) for item in variable_values):
        return (), ["variables-must-be-string-list"]
    names = cast(list[str], variable_values)
    findings: list[str] = []
    seen: set[str] = set()
    for name in names:
        if ENVIRONMENT_NAME_RE.fullmatch(name) is None:
            findings.append(f"invalid-variable-name:{name}")
        elif name in seen:
            findings.append(f"duplicate-variable:{name}")
        seen.add(name)
    return tuple(names), findings


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
    runtime_source: Path | None = None,
) -> list[Finding]:
    """Validate generated Compose meaning rather than generator implementation text."""
    runtime_source = runtime_source or (root / ".agent-canon/runtime")
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
    home_target = "/home/project"
    expected_runtime_user = "project"
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
    build_target = build.get("target") if build is not None else None
    if profile == "default" and build_target == "gpu-runtime":
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "default-gpu-build-target-forbidden:gpu-runtime",
            )
        )
    if pack is not None and build_target != pack.target:
        expected_target = pack.target if pack.target is not None else "absent"
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                f"compose-build-target-expected:{expected_target}",
            )
        )
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
                    pattern = r"[1-9][0-9]*" if name == "PROJECT_UID" else r"[0-9]+"
                    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
                        findings.append(
                            Finding(
                                "dependency_contract_violation",
                                relative,
                                f"standalone-build-arg-{name}-must-be-{'nonzero' if name == 'PROJECT_UID' else 'nonnegative'}-decimal",
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
            options = raw_volume.rsplit(":", 1)[-1].split(",")
            return "ro" in options
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
    optional_mounts = optional_mounts_value if isinstance(optional_mounts_value, str) else ""
    optional_tokens_list: list[str] = []
    if not isinstance(optional_mounts_value, str):
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "optional-mount-profile-source-must-be-string",
            )
        )
    elif optional_mounts:
        optional_tokens_list = optional_mounts.split(",")
        if any(not token or token != token.strip() or re.search(r"\s", token) for token in optional_tokens_list):
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "optional-mount-profile-empty-or-whitespace",
                )
            )
    optional_tokens = set(optional_tokens_list)
    supported_optional_mounts = OPTIONAL_MOUNT_PROFILES
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
    if pack is not None:
        expected_profiles = list(pack.optional_mount_profiles)
        expected_profiles.extend(
            token for token in optional_tokens_list if token not in expected_profiles
        )
        if optional_tokens_list != expected_profiles:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "optional-mount-profile-canonical-union",
                )
            )
    linked_profile_selected = "linked-data-roots" in optional_tokens
    if pack is not None and linked_profile_selected != pack.linked_data_roots_declared:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "linked-data-roots-profile-and-list-must-match",
            )
        )
    elif pack is None and linked_profile_selected:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "linked-data-roots-pack-required",
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
    elif workspace_layout != expected_workspace_layout:
        findings.append(
            Finding(
                "inconsistency",
                relative,
                f"workspace-layout:{workspace_layout}",
            )
        )

    repository_mounts = [
        raw_volume for raw_volume in volumes if volume_fields(raw_volume)[1] == repo_target
    ]
    if len(repository_mounts) != 1:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                f"repository-mount-count:{len(repository_mounts)}",
            )
        )
    elif source_path(volume_fields(repository_mounts[0])[0]) != root:
        findings.append(
            Finding("dependency_contract_violation", relative, "repository-mount-source")
        )
    for raw_volume in volumes:
        source, target = volume_fields(raw_volume)
        if source_path(source) == topic_root or target == "/workspace":
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "workspace-scope-leak",
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
    service_user_valid = isinstance(service_user, str) and re.fullmatch(
        r"[1-9][0-9]*:[0-9]+", service_user
    ) is not None
    if not service_user_valid:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "project-user-must-have-nonzero-uid-nonnegative-gid",
            )
        )
    build_args: Mapping[str, object] | None = None
    if build is None:
        findings.append(
            Finding(
                "dependency_contract_violation",
                relative,
                "build-required-for-project-uid-gid",
            )
        )
    else:
        build_args = as_mapping(build.get("args"))
        if build_args is None:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "build-args-required:PROJECT_UID,PROJECT_GID",
                )
            )
        else:
            for name in ("PROJECT_UID", "PROJECT_GID"):
                value = build_args.get(name)
                pattern = r"[1-9][0-9]*" if name == "PROJECT_UID" else r"[0-9]+"
                if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
                    findings.append(
                        Finding(
                            "dependency_contract_violation",
                            relative,
                            f"build-arg-{name}-must-be-{'nonzero' if name == 'PROJECT_UID' else 'nonnegative'}-decimal",
                        )
                    )
    if service_user_valid and build_args is not None:
        project_uid = build_args.get("PROJECT_UID")
        project_gid = build_args.get("PROJECT_GID")
        if (
            isinstance(project_uid, str)
            and re.fullmatch(r"[1-9][0-9]*", project_uid) is not None
            and isinstance(project_gid, str)
            and re.fullmatch(r"[0-9]+", project_gid) is not None
            and service_user != f"{project_uid}:{project_gid}"
        ):
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "project-user-must-match-build-args",
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
        if "group_add" in service:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "gpu-admission-group-add-forbidden",
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
        else:
            actual_runtime_source, runtime_target = volume_fields(runtime_mounts[0])
            if actual_runtime_source != str(runtime_source):
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "gpu-admission-runtime-mount-source-must-be-repository-local",
                    )
                )
            if runtime_target != "/var/lib/agent-canon/runtime":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "gpu-admission-runtime-mount-target-must-be-canonical",
                    )
                )
            runtime_volume = as_mapping(runtime_mounts[0])
            if runtime_volume is not None:
                if (
                    "read_only" in runtime_volume
                    and runtime_volume.get("read_only") is not False
                ):
                    findings.append(
                        Finding(
                            "dependency_contract_violation",
                            relative,
                            "gpu-admission-runtime-mount-must-be-read-write",
                        )
                    )
            elif volume_is_read_only(runtime_mounts[0]):
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "gpu-admission-runtime-mount-must-be-read-write",
                    )
                )
    if parent_layout or "host-zshrc" in optional_tokens:
        zshrc_matches = [
            raw_volume
            for raw_volume in volumes
            if volume_fields(raw_volume)[1] in {
                f"{home_target}/.zshrc",
                "/etc/project-template/zsh/.zshrc",
            }
        ]
        for host_zshrc in zshrc_matches:
            _, target = volume_fields(host_zshrc)
            if target != f"{home_target}/.zshrc":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"host-zshrc-target-must-be-{home_target}/.zshrc",
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
            if not isinstance(source, str) or not Path(source).is_absolute():
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "host-zshrc-source-must-be-resolved-absolute-file",
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
        zsh_matches = [
            raw_volume
            for raw_volume in volumes
            if volume_fields(raw_volume)[1] == f"{home_target}/.zsh"
        ]
        for host_zsh in zsh_matches:
            source, target = volume_fields(host_zsh)
            if target != f"{home_target}/.zsh":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"host-zsh-target-must-be-{home_target}/.zsh",
                    )
                )
            if volume_type(host_zsh) != "bind":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "host-zsh-mount-type-must-be-bind",
                    )
                )
            if not isinstance(source, str) or not Path(source).is_absolute():
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "host-zsh-source-must-be-resolved-absolute-directory",
                    )
                )
            if not volume_is_read_only(host_zsh):
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "host-zsh-mount-read-only",
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
    linked_targets: set[str] = set()
    if pack is not None:
        linked_targets = {linked_root.target for linked_root in pack.linked_data_roots}
    if linked_profile_selected and pack is not None:
        linked_mounts = [
            raw_volume
            for raw_volume in volumes
            if volume_fields(raw_volume)[1] in linked_targets
        ]
        seen_linked_sources: set[str] = set()
        seen_linked_targets: set[str] = set()
        for linked_root in pack.linked_data_roots:
            matches = [
                raw_volume
                for raw_volume in linked_mounts
                if volume_fields(raw_volume)[1] == linked_root.target
            ]
            if len(matches) != 1:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"linked-data-root-mount-count:{linked_root.target}",
                    )
                )
                continue
            linked_mount = matches[0]
            source, target = volume_fields(linked_mount)
            if source != linked_root.target or target != linked_root.target:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"linked-data-root-source-target-mismatch:{linked_root.target}",
                    )
                )
            if volume_type(linked_mount) != "bind":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"linked-data-root-mount-type-must-be-bind:{linked_root.target}",
                    )
                )
            volume = as_mapping(linked_mount)
            if volume is None or volume.get("read_only") is not False:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"linked-data-root-mount-must-be-read-write:{linked_root.target}",
                    )
                )
            if isinstance(source, str) and source in seen_linked_sources:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"linked-data-root-source-duplicate:{source}",
                    )
                )
            if isinstance(target, str) and target in seen_linked_targets:
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        f"linked-data-root-target-duplicate:{target}",
                    )
                )
            if isinstance(source, str):
                seen_linked_sources.add(source)
            if isinstance(target, str):
                seen_linked_targets.add(target)
    docker_host_mounts = [
        raw_volume
        for raw_volume in volumes
        if volume_fields(raw_volume)[1] == "/var/run/docker.sock"
    ]
    if "docker-host" in optional_tokens:
        if len(docker_host_mounts) != 1:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    f"docker-host-mount-count:{len(docker_host_mounts)}",
                )
            )
        else:
            docker_host_mount = docker_host_mounts[0]
            docker_source, docker_target = volume_fields(docker_host_mount)
            if docker_source != "/var/run/docker.sock":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "docker-host-mount-source-must-be-canonical",
                    )
                )
            if docker_target != "/var/run/docker.sock":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "docker-host-mount-target-must-be-canonical",
                    )
                )
            docker_volume = as_mapping(docker_host_mount)
            if docker_volume is not None and volume_type(docker_host_mount) != "bind":
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "docker-host-mount-type-must-be-bind",
                    )
                )
            malformed_read_only = (
                docker_volume is not None
                and "read_only" in docker_volume
                and docker_volume.get("read_only") is not False
            )
            if malformed_read_only or (
                docker_volume is None and volume_is_read_only(docker_host_mount)
            ):
                findings.append(
                    Finding(
                        "dependency_contract_violation",
                        relative,
                        "docker-host-mount-must-be-read-write",
                    )
                )
    allowed_targets = {repo_target}
    if "host-zshrc" in optional_tokens:
        allowed_targets.add(f"{home_target}/.zshrc")
        allowed_targets.add(f"{home_target}/.zsh")
    if profile == "gpu-admission":
        allowed_targets.add("/var/lib/agent-canon/runtime")
    if "host-git" in optional_tokens:
        allowed_targets.add("/mnt/git")
    if "host-secrets" in optional_tokens:
        allowed_targets.add("/mnt/agent-canon-secrets")
    if "host-credentials" in optional_tokens:
        allowed_targets.update({f"{home_target}/.config/gh", f"{home_target}/.ssh"})
    if "ssh-agent" in optional_tokens:
        allowed_targets.add("/ssh-agent")
    if "docker-host" in optional_tokens:
        allowed_targets.add("/var/run/docker.sock")
    if linked_profile_selected:
        allowed_targets.update(linked_targets)
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
        "AGENT_CANON_WORKSPACE_LAYOUT": expected_workspace_layout or "<invalid>",
        "AGENT_CANON_WORKSPACE_ROOT": "/workspace",
        "AGENT_CANON_REPOSITORY_ROOT": repo_target,
        "DEPENDENCY_MODULE_CONTAINER_SOURCE": str(root),
        "DEPENDENCY_MODULE_CONTAINER_TARGET": repo_target,
        "AGENT_CANON_RUNTIME_ROUTE": (
            "MANAGED_CONTAINER" if profile == "gpu-admission" else "CONTAINER_LOCAL"
        ),
        "AGENT_CANON_CODEX_SESSION_ROOT": f"{home_target}/.codex/sessions",
        "AGENT_CANON_SECRET_MOUNT": "/mnt/agent-canon-secrets",
        "HOME": home_target,
        "SHELL": expected_shell,
        "AGENT_CANON_CONTAINER_USER": expected_runtime_user,
    }
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
        if "AGENT_CANON_RUNTIME_IDENTITY_MODE" in environment:
            findings.append(
                Finding(
                    "dependency_contract_violation",
                    relative,
                    "daemon-runtime-identity-mode-env-forbidden",
                )
            )
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
                "AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE",
                "AGENT_CANON_SHARED_RUNTIME_TARGET",
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
                "AGENT_CANON_SHARED_RUNTIME_SOURCE": "/var/lib/agent-canon/runtime",
                "AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE": str(runtime_source),
                "AGENT_CANON_SHARED_RUNTIME_TARGET": "/var/lib/agent-canon/runtime",
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
                elif environment.get(name) != expected:
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
    boundary = ParentRootSideEffectBoundary()
    runtime_source: Path | None = None
    temporary_parent = root / ".agent-canon" / "tmp"
    agent_canon_dir = root / ".agent-canon"
    temporary_parent_existed = temporary_parent.is_dir()
    agent_canon_dir_existed = agent_canon_dir.is_dir()
    try:
        attestation = resolve_parent_writer_attestation(purpose="container-config-runtime")
        temporary = boundary.create_parent_owned_temp_directory(
            attestation,
            temporary_parent,
            "container-config-runtime",
            "container-config",
        )
    except ParentRootSideEffectError as exc:
        return [
            Finding(
                "dependency_contract_violation",
                script_path.relative_to(root).as_posix(),
                f"container-config-runtime-boundary:{exc}",
            )
        ]
    temporary_root = temporary.physical_path
    try:
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
                "AGENT_CANON_DEVCONTAINER_REPO_ROOT": str(root.resolve()),
            }
        )
        scenarios: list[tuple[str, dict[str, str]]] = [("default", {})]
        packs_dir = root / "docker" / "packs"
        if packs_dir.is_dir():
            runtime_source = boundary.ensure_parent_owned_directory(
                attestation,
                temporary_root / "runtime",
                "container-config-runtime-source",
            ).physical_path
            scenarios.append(
                (
                    "gpu-admission",
                    {
                        "AGENT_CANON_GPU_ADMISSION_PROFILE": "gpu-admission",
                        "AGENT_CANON_SHARED_RUNTIME_SOURCE": str(runtime_source),
                        "AGENT_CANON_SHARED_RUNTIME_HOST_SOURCE": str(runtime_source),
                        "AGENT_CANON_SHARED_RUNTIME_TARGET": "/var/lib/agent-canon/runtime",
                        "AGENT_CANON_SHARED_RUNTIME_PROVISION_RECEIPT": str(runtime_source / "shared-runtime-provision.json"),
                        "AGENT_CANON_SHARED_RUNTIME_READBACK_RECEIPT": str(runtime_source / "shared-runtime-readback.json"),
                    },
                )
            )
        for profile, additions in scenarios:
            compose_path = temporary_root / f"{profile}.yml"
            scenario_pack = pack
            if profile == "gpu-admission":
                gpu_pack_path = packs_dir / "gpu-admission.toml"
                if gpu_pack_path.is_file():
                    scenario_pack, gpu_pack_findings = load_pack(
                        root, gpu_pack_path
                    )
                    findings.extend(gpu_pack_findings)
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
                    scenario_pack,
                    profile=profile,
                    compose_path=compose_path,
                    runtime_source=(runtime_source if profile == "gpu-admission" else None),
                )
            )
    finally:
        boundary.remove_parent_owned_tree(
            attestation, temporary, "container-config-runtime-cleanup"
        )
        if not temporary_parent_existed and temporary_parent.is_dir():
            parent_receipt = boundary.resolve_parent_owned_path(
                attestation, temporary_parent, "container-config-runtime-base-cleanup", create=False
            )
            boundary.remove_empty_parent_owned_directory(
                attestation, parent_receipt, "container-config-runtime-base-cleanup"
            )
        if not agent_canon_dir_existed and agent_canon_dir.is_dir():
            root_receipt = boundary.resolve_parent_owned_path(
                attestation, agent_canon_dir, "container-config-agent-base-cleanup", create=False
            )
            boundary.remove_empty_parent_owned_directory(
                attestation, root_receipt, "container-config-agent-base-cleanup"
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

    findings.extend(
        validate_devcontainer_json(
            config,
            parent_layout=(root / "vendor" / "agent-canon").is_dir(),
            config_path=".devcontainer/devcontainer.json",
        )
    )
    parent_layout = (root / "vendor" / "agent-canon").is_dir()
    if not parent_layout:
        findings.extend(validate_generate_runtime_compose_script(root))
        findings.extend(validate_post_create(root))
        findings.extend(validate_default_lifecycle_scripts(root))
        findings.extend(validate_gpu_admission_selector(root))
    if not parent_layout:
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
    if (root / "vendor" / "agent-canon").is_dir():
        return root / "tools" / "agent-canon" / "agent_tools"
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
            validate_generated_compose(
                root, pack, compose_path=persisted_compose
            )
        )
    profile_compose = root / ".agent-canon" / "gpu-admission-compose.generated.yml"
    if profile_compose.exists():
        profile_pack = pack
        gpu_pack_path = root / "docker" / "packs" / "gpu-admission.toml"
        if gpu_pack_path.is_file():
            profile_pack, gpu_pack_findings = load_pack(root, gpu_pack_path)
            findings.extend(gpu_pack_findings)
        findings.extend(
            validate_generated_compose(
                root,
                profile_pack,
                profile="gpu-admission",
                compose_path=profile_compose,
            )
        )
    return findings


def is_standalone_source(root: Path) -> bool:
    """Return whether root carries the standalone AgentCanon source markers."""
    return all(
        (root / marker).is_file() and not (root / marker).is_symlink()
        for marker in ("ROOT_AGENTS.md", "agent-canon-environment.toml")
    )


def has_vscode_contract(root: Path) -> bool:
    """Return whether this root has a VS Code contract to inspect."""
    vscode_dir = root / ".vscode"
    return is_standalone_source(root) or vscode_dir.exists() or vscode_dir.is_symlink()


VSCODE_SHARED_FILES = (
    "c_cpp_properties.json",
    "extensions.json",
    "settings.json",
    "tasks.json",
)


def is_agent_canon_vscode_symlink(path: Path, root: Path) -> bool:
    """Return whether a parent editor file still links into AgentCanon."""
    if not path.is_symlink():
        return False
    source_dir = root / "vendor" / "agent-canon" / ".vscode"
    try:
        target = path.readlink()
        target_path = target if target.is_absolute() else path.parent / target
        return target_path.resolve(strict=False).is_relative_to(
            source_dir.resolve(strict=False)
        )
    except (OSError, RuntimeError):
        return False


def validate_vscode(root: Path) -> list[Finding]:
    """Validate standalone files and reject retired parent projections."""
    findings: list[Finding] = []
    root_vscode = root / ".vscode"
    source_checkout = is_standalone_source(root)
    if root_vscode.is_symlink():
        findings.append(Finding("inconsistency", ".vscode", "expected-real-directory"))
        return findings
    if source_checkout:
        for name in VSCODE_SHARED_FILES:
            source_file = root_vscode / name
            path = f".vscode/{name}"
            if not source_file.is_file():
                findings.append(Finding("missing_file", path, "missing"))
            elif source_file.is_symlink():
                findings.append(
                    Finding(
                        "inconsistency", path, "source-file-must-be-regular"
                    )
                )
        return findings
    if not root_vscode.is_dir():
        findings.append(Finding("inconsistency", ".vscode", "expected-real-directory"))
        return findings
    for child in root_vscode.iterdir():
        if is_agent_canon_vscode_symlink(child, root):
            findings.append(
                Finding(
                    "inconsistency",
                    str(child.relative_to(root)),
                    "legacy-agent-canon-symlink",
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
    parent_layout = (root / "vendor" / "agent-canon").is_dir()
    if docker_dir.exists():
        checked.extend((".dockerignore", "docker/Dockerfile"))
        findings.extend(validate_dockerignore(root))
        findings.extend(validate_dockerfile(root))
        packs_dir = docker_dir / "packs"
        if packs_dir.is_dir():
            checked.append("docker/packs")
            pack_paths = sorted(packs_dir.glob("*.toml"))
            if not pack_paths and not parent_layout:
                findings.append(
                    Finding("missing_file", "docker/packs", "no-pack-files")
                )
            for pack_path in pack_paths:
                pack, pack_findings = load_pack(root, pack_path)
                findings.extend(pack_findings)
                if pack is not None:
                    packs.append(pack)
        elif not parent_layout and not (docker_dir / "Dockerfile").is_file():
            checked.append("docker/packs")
            findings.append(Finding("missing_file", "docker/packs", "missing"))

    default_pack = next(
        (pack for pack in packs if pack.path == "docker/packs/default.toml"), None
    )
    if devcontainer_dir.exists():
        checked.append(".devcontainer")
        findings.extend(validate_devcontainer(root))
        if (
            is_standalone_source(root)
            and (devcontainer_dir / "Dockerfile").is_file()
            and not (docker_dir / "Dockerfile").is_file()
        ):
            checked.append(".dockerignore")
            findings.extend(validate_standalone_docker_context(root))
        if not parent_layout:
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
            f"workspace_mount={pack.workspace_mount}\tplatform={pack.platform}"
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
