#!/usr/bin/env python3
# @dependency-start
# contract implementation
# responsibility Owns the typed declarative devcontainer dependency model, merge, plan, and receipt installer.
# upstream design ../../documents/design/devcontainer/parent-dependency-manifest-followup.md parent-first merge and lifecycle order
# upstream design ../../documents/design/devcontainer/parent-devcontainer-policy.md typed project-extra ownership
# upstream design ../../CONTAINER_OPERATIONS.md image versus mounted tool boundary
# downstream environment ../../.devcontainer/dependencies.toml AgentCanon shared developer/agent records
# downstream implementation ../../.devcontainer/post-create.sh read-only image verification
# downstream implementation ../../tools/docker_dependency_validator.sh no-install validation route
# downstream implementation ../../tests/agent_tools/test_devcontainer_dependencies.py focused model and security tests
# @dependency-end
"""Declarative, typed devcontainer dependency planning and installation.

The image owns fixed Python and manifest-selected Agent/Codex capabilities. The
legacy editable project-extra API remains available to explicit callers, while
the active post-create and runner lifecycle performs read-only image verification.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

try:
    from .parent_root_side_effects import (
        ParentRootAttestationReceipt,
        ParentRootAttestationRequest,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
        child_environment,
        ensure_parent_owned_directory,
        resolve_parent_owned_path,
    )
except ImportError:  # direct script execution
    from parent_root_side_effects import (  # type: ignore[no-redef]
        ParentRootAttestationReceipt,
        ParentRootAttestationRequest,
        ParentRootSideEffectBoundary,
        ParentRootSideEffectError,
        attest_parent_root,
        child_environment,
        ensure_parent_owned_directory,
        resolve_parent_owned_path,
    )

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

try:  # pragma: no cover - the branch depends on the interpreter image.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - covered with a subprocess test.
    import tomli as tomllib  # type: ignore[no-redef]


SCHEMA = "agent-canon.devcontainer-dependencies"
SCHEMA_VERSION = 2
METHODS = frozenset(
    {
        "apt-package",
        "apt-repository",
        "npm-global",
        "pipx",
        "release-asset",
        "rust-toolchain",
        "lean-toolchain",
        "cargo-source-build",
        "browser-install",
    }
)
FAILURE_POLICIES = frozenset({"fail", "warn"})
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
ACTIVE_SOURCE_IDENTITY = "active-source"
CANONICAL_SNAPSHOT_IDENTITY = "canonical-snapshot"
RUSTUP_INIT_VERSION = "1.28.2"
RUSTUP_INIT_URL = (
    "https://static.rust-lang.org/rustup/archive/1.28.2/"
    "x86_64-unknown-linux-gnu/rustup-init"
)
RUSTUP_INIT_SHA256 = "20a06e644b0d9bd2fbdbfd52d42540bdde820ea7df86e92e533c073da0cdd43c"
CANONICAL_RUST_SOURCE_FILES = (
    "Cargo.lock", "Cargo.toml", "src/dependency_manifest.rs", "src/docs.rs",
    "src/graph.rs", "src/jit_ir_to_lean.rs", "src/main.rs", "src/memory.rs",
    "src/migration_audit.rs", "src/python_algorithm_contract.rs",
    "src/python_module_groups.rs", "src/python_structure_hash.rs",
    "src/python_structure_hash_impact.rs", "src/python_structure_hash_report.rs",
    "src/python_structure_hash_scope_plan.rs", "src/rust_migration_plan.rs",
    "src/semantic_index/args.rs", "src/semantic_index/cli.rs",
    "src/semantic_index/embedding.rs", "src/semantic_index/eval.rs",
    "src/semantic_index/mod.rs", "src/semantic_index/model.rs",
    "src/semantic_index/pipeline.rs", "src/semantic_index/query.rs",
    "src/semantic_index/relations.rs", "src/semantic_index/report.rs",
    "src/semantic_index/source.rs", "src/semantic_index/storage.rs",
    "src/semantic_index/tests.rs", "src/structured_analysis.rs",
    "src/test_design.rs", "tests/python_algorithm_contract_cli.rs",
)
CANONICAL_RUST_SOURCE_SHA256 = "6084cc155d0166cb06e661a07cae7a0630c34df21ee7e9d4c6816d875ec5d15c"
CANONICAL_CARGO_LOCK_SHA256 = "060b8825843b14b12bebb9da095503f4ec7f68a77934e595c082957cb1f72638"
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
APT_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
NPM_PACKAGE_RE = re.compile(r"^(?:@[a-z0-9._~-]+/[a-z0-9._~-]+|[a-z0-9._~-]+)$")
PYTHON_PACKAGE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
SEMVER_RE = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
VERSION_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$")
PLATFORM_RE = re.compile(r"^linux/(?:amd64|arm64)$")
SAFE_MEMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PYTHON_EXTRA_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TRAVERSAL_RE = re.compile(r"(?:^|[/\\])\.\.(?:[/\\]|$)")
SHELL_EXECUTABLES = frozenset(
    {"bash", "dash", "fish", "ksh", "sh", "tcsh", "zsh", "eval"}
)
BASE_CAPABILITIES = frozenset(
    {
        "build-essential",
        "ca-certificates",
        "curl",
        "git",
        "gnupg",
        "ninja-build",
        "node",
        "npm",
        "pipx",
        "python3",
        "python3-packaging",
        "tar",
        "tomli",
        "tomllib",
        "rustup-init",
        "xz-utils",
    }
)
NPM_GLOBAL_PREFIX = "/usr/local"
NPM_ENV_EXECUTABLE = "/usr/bin/env"
NPM_SYSTEM_BIN_DIRS = (
    "/usr/local/bin",
    "/usr/local/sbin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
)
NPM_TRUSTED_BIN_DIRS = NPM_SYSTEM_BIN_DIRS
NPM_TRUSTED_BIN_ROOTS = {
    "/usr/local/sbin": "/usr/local",
    "/usr/local/bin": "/usr/local",
    "/usr/sbin": "/usr",
    "/usr/bin": "/usr",
    "/sbin": "/usr",
    "/bin": "/usr",
}
STRUCTURAL_BINDING_OUTPUT_PREFIX = "agent-canon.executable-binding.structural.v1"
IMAGE_DEPENDENCIES_ROOT = Path("/usr/local/share/agent-canon/image-dependencies")
IMAGE_PLAN_SCHEMA = "agent-canon.devcontainer-image-dependencies"
IMAGE_PLAN_SCHEMA_VERSION = 1
IMAGE_INSTALL_METHODS = frozenset(
    {
        "apt-package",
        "apt-repository",
        "npm-global",
        "release-asset",
        "rust-toolchain",
        "cargo-source-build",
    }
)
IMAGE_DIRECTORY_MODE = 0o555
IMAGE_FILE_MODE = 0o444


def _parent_attestation(workspace: Path, purpose: str) -> ParentRootAttestationReceipt:
    """Authenticate the selected parent before dependency side effects."""
    try:
        return attest_parent_root(
            ParentRootAttestationRequest(
                cwd=workspace, explicit_root=workspace, purpose=purpose
            )
        )
    except ParentRootSideEffectError as exc:
        raise DependencyError(
            f"parent-root-attestation:{exc.reject.value}:{exc.detail}"
        ) from exc


def _parent_temp_root(workspace: Path, purpose: str) -> Path:
    """Return a parent-owned temporary directory for one dependency operation."""
    # A few pure installer adapters are exercised with a lexical workspace
    # placeholder by their unit fixtures.  Keep that fixture write parent-local
    # without manufacturing a repository outside the selected boundary.
    if not workspace.exists():
        workspace = workspace.parent
    attestation = _parent_attestation(workspace, f"dependency-{purpose}")
    try:
        receipt = resolve_parent_owned_path(
            attestation, Path(".agent-canon") / "tmp" / "devcontainer" / purpose,
            f"dependency-{purpose}", create=False,
        )
    except ParentRootSideEffectError as exc:
        raise DependencyError(
            f"parent-root-path:{exc.reject.value}:{exc.detail}"
        ) from exc
    return ensure_parent_owned_directory(
        attestation, receipt.physical_path, f"dependency-{purpose}"
    ).physical_path


class DependencyError(ValueError):
    """Base error for schema, merge, plan, and execution failures."""


class CommandCapability(str, Enum):  # noqa: UP042
    """Capabilities reachable from one typed command graph."""

    ARGV = "argv"
    SHELL_EVALUATION = "shell-evaluation"
    DYNAMIC_INTERPRETER = "dynamic-interpreter"
    PACKAGE_INSTALL = "package-install"
    NETWORK_FETCH = "network-fetch"
    PRIVILEGE_ESCALATION = "privilege-escalation"
    READ_ONLY_QUERY = "read-only-query"
    EXECUTABLE_VERIFICATION = "executable-verification"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CommandBoundaryFinding:
    """Stable structural command-boundary finding."""

    capability: CommandCapability
    detail: str
    argv_prefix: tuple[str, ...]
    phase: str

    def render(self) -> str:
        """Render the machine-readable failure prefix used by callers."""
        return f"command-boundary-{self.capability.value}: {self.detail}"


@dataclass(frozen=True)
class CommandProvenance:
    """Authenticated owner and phase provenance for one command edge."""

    phase: str
    owner: str
    operation: str
    method: str | None = None
    record_id: str | None = None
    privileged_requested: bool = False
    owner_root: str | None = None


@dataclass(frozen=True)
class NetworkOperation:
    """Typed manifest-owned network edge for image installation."""

    phase: str
    owner: str
    operation: str
    method: str
    record_id: str
    url: str
    allow_network: bool


_COMMAND_PHASES = frozenset({"image-install", "image-verify", "post-create"})
_COMMAND_OWNERS = frozenset(
    {"image-installer", "typed-verifier", "shared-post-create", "parent-hook"}
)
_COMMAND_SHELLS = frozenset(
    {"bash", "dash", "fish", "ksh", "sh", "tcsh", "zsh"}
)
_COMMAND_INTERPRETERS = {
    "python": {"--version", "-V", "--help"},
    "python3": {"--version", "-V", "--help"},
    "pypy": {"--version", "-V", "--help"},
    "node": {"--version", "-v", "--help"},
    "nodejs": {"--version", "-v", "--help"},
    "perl": {"--version", "-v", "--help"},
    "ruby": {"--version", "-v", "--help"},
}
_COMMAND_OPERATION_METHODS = {
    "verify-apt-package": frozenset({"apt-package"}),
    "verify-apt-executable-owner": frozenset({"apt-package", "apt-repository"}),
    "verify-apt-repository-key": frozenset({"apt-repository"}),
    "verify-npm-package": frozenset({"npm-global"}),
    "verify-pipx-package": frozenset({"pipx"}),
    "verify-rust-active": frozenset({"rust-toolchain"}),
    "verify-rust-installed": frozenset({"rust-toolchain"}),
    "verify-rust-components": frozenset({"rust-toolchain"}),
    "verify-rust-tool-version": frozenset({"rust-toolchain"}),
    "verify-lean-active": frozenset({"lean-toolchain"}),
    "verify-lean-installed": frozenset({"lean-toolchain"}),
    "verify-lean-tool-version": frozenset({"lean-toolchain"}),
    "verify-cargo-source-identity": frozenset({"cargo-source-build"}),
    "install-apt-package": frozenset({"apt-package"}),
    "install-apt-repository": frozenset({"apt-repository"}),
    "install-npm-global": frozenset({"npm-global"}),
    "install-pipx": frozenset({"pipx"}),
    "install-release-asset": frozenset({"release-asset"}),
    "install-rust-toolchain": frozenset({"rust-toolchain"}),
    "install-lean-toolchain": frozenset({"lean-toolchain"}),
    "install-cargo-source-build": frozenset({"cargo-source-build"}),
    "install-browser": frozenset({"browser-install"}),
}
_NETWORK_OPERATION_METHODS = {
    "download-apt-key": "apt-repository",
    "download-apt-package": "apt-repository",
    "download-release-asset": "release-asset",
    "download-packages-index": "apt-repository",
}


def _command_owner_root(context: CommandProvenance) -> Path:
    """Resolve the canonical source root used for owner-path checks."""
    root = Path(context.owner_root) if context.owner_root is not None else Path(__file__).resolve().parents[2]
    try:
        resolved = root.resolve(strict=True)
        if not resolved.is_dir():
            raise NotADirectoryError(str(resolved))
        return resolved
    except OSError as exc:
        raise _command_failure(
            CommandCapability.UNKNOWN,
            "command owner root is not a resolved directory",
            (),
            context,
        ) from exc


def _require_canonical_owned_file(
    path_value: str,
    *,
    owner_root: Path,
    relative: str,
    context: CommandProvenance,
) -> None:
    """Require an exact canonical, non-symlink regular file under owner root."""
    path = Path(path_value)
    expected = owner_root / relative
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise _command_failure(
            CommandCapability.UNKNOWN,
            f"owned command path is not a non-symlink regular file: {path}",
            (path_value,),
            context,
        )
    try:
        resolved = path.resolve(strict=True)
        expected_resolved = expected.resolve(strict=True)
        resolved.relative_to(owner_root)
    except (OSError, ValueError) as exc:
        raise _command_failure(
            CommandCapability.UNKNOWN,
            f"owned command path is outside its canonical owner root: {path}",
            (path_value,),
            context,
        ) from exc
    if resolved != expected_resolved:
        raise _command_failure(
            CommandCapability.UNKNOWN,
            f"owned command path is not canonical: {path}",
            (path_value,),
            context,
        )


def _command_failure(
    capability: CommandCapability,
    detail: str,
    argv: Sequence[str],
    context: CommandProvenance,
) -> DependencyError:
    finding = CommandBoundaryFinding(
        capability,
        detail,
        tuple(str(item) for item in argv[:4]),
        context.phase,
    )
    return DependencyError(finding.render())


def _command_basename(token: str) -> str:
    """Resolve only basename spelling; classification never resolves PATH."""
    return Path(token).name


def _command_is_identity_probe(argv: Sequence[str], executable: str) -> bool:
    return len(argv) == 2 and argv[1] in _COMMAND_INTERPRETERS[executable]


def _command_shape_capabilities(
    argv: Sequence[str], context: CommandProvenance
) -> set[CommandCapability]:
    """Classify the final command using the closed owner operation matrix."""
    executable = _command_basename(argv[0])
    args = list(argv[1:])
    capabilities: set[CommandCapability] = {CommandCapability.ARGV}

    if (
        executable == "bash"
        and context.owner in {"shared-post-create", "parent-hook"}
    ):
        if context.owner == "shared-post-create" and len(argv) == 2:
            _require_canonical_owned_file(
                argv[1],
                owner_root=_command_owner_root(context),
                relative=".devcontainer/post-create.sh",
                context=context,
            )
        else:
            raise _command_failure(
                CommandCapability.SHELL_EVALUATION,
                "parent hook shell dispatch is a separate owner edge",
                argv,
                context,
            )
        capabilities.add(CommandCapability.READ_ONLY_QUERY)
        return capabilities
    if executable in _COMMAND_SHELLS:
        raise _command_failure(
            CommandCapability.SHELL_EVALUATION,
            "shell executable is an execution boundary",
            argv,
            context,
        )
    if executable in {"sudo", "doas", "su", "runuser"}:
        raise _command_failure(
            CommandCapability.PRIVILEGE_ESCALATION,
            "explicit privilege wrapper is not an owned verification command",
            argv,
            context,
        )
    if executable == "eval":
        raise _command_failure(
            CommandCapability.DYNAMIC_INTERPRETER,
            "eval is a dynamic child-command edge",
            argv,
            context,
        )
    if executable in _COMMAND_INTERPRETERS:
        if (
            executable in {"python", "python3"}
            and context.owner == "shared-post-create"
            and len(argv) >= 3
            and Path(argv[1]).name == "devcontainer_dependencies.py"
            and argv[2] == "image-verify"
        ):
            _require_canonical_owned_file(
                argv[1],
                owner_root=_command_owner_root(context),
                relative="tools/agent_tools/devcontainer_dependencies.py",
                context=context,
            )
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
            return capabilities
        if not _command_is_identity_probe(argv, executable):
            capability = (
                CommandCapability.DYNAMIC_INTERPRETER
                if any(item in {"-c", "-e", "-E", "-m", "-p", "--eval", "--print", "-"} for item in args)
                else CommandCapability.UNKNOWN
            )
            raise _command_failure(
                capability,
                "interpreter command graph is not a fixed identity probe",
                argv,
                context,
            )
        capabilities.add(CommandCapability.READ_ONLY_QUERY)
        return capabilities
    if executable in {"xargs"} or executable == "find" and any(
        item in {"-exec", "-execdir"} for item in args
    ):
        raise _command_failure(
            CommandCapability.DYNAMIC_INTERPRETER,
            "child-command selector is dynamic",
            argv,
            context,
        )
    if executable in {"timeout", "nice", "stdbuf"}:
        raise _command_failure(
            CommandCapability.UNKNOWN,
            "wrapper grammar is not declared by the owner operation",
            argv,
            context,
        )

    if executable in {"apt", "apt-get", "aptitude", "pip", "pipx", "cargo", "playwright"}:
        mutation_words = {
            "install", "update", "upgrade", "remove", "uninstall", "purge",
            "add", "default", "build", "fetch", "sync", "download", "init",
        }
        if executable == "pipx" and args[:1] == ["runpip"] and len(args) >= 4 and args[2] == "show":
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
            return capabilities
        if executable == "cargo" and args[:1] == ["build"]:
            capabilities.update({CommandCapability.PACKAGE_INSTALL, CommandCapability.NETWORK_FETCH})
        elif any(item in mutation_words for item in args):
            capabilities.add(CommandCapability.PACKAGE_INSTALL)
            if executable in {"apt", "apt-get", "aptitude", "pip", "pipx", "cargo", "playwright"}:
                capabilities.add(CommandCapability.NETWORK_FETCH)
        else:
            raise _command_failure(
                CommandCapability.UNKNOWN,
                "package-manager command shape is not owner-declared",
                argv,
                context,
            )
    elif executable == "npm":
        if args[:2] == ["ls", "--global"] and "--json" in args and "--depth=0" in args:
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
        elif args and args[0] in {"install", "update", "uninstall", "exec", "publish"}:
            capabilities.update({CommandCapability.PACKAGE_INSTALL, CommandCapability.NETWORK_FETCH})
        elif args == ["--version"]:
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
        else:
            raise _command_failure(
                CommandCapability.UNKNOWN,
                "npm command shape is not owner-declared",
                argv,
                context,
            )
    elif executable in {"rustup", "elan"}:
        if executable == "rustup" and (
            args[:3] == ["show", "active-toolchain"]
            or args[:2] == ["toolchain", "list"]
            or args[:2] == ["component", "list"]
            or (
                args[:1] == ["run"]
                and len(args) == 4
                and args[-1] == "--version"
            )
        ):
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
        elif executable == "elan" and (
            args[:1] in (["show"], ["toolchain"])
            or (args[:1] == ["run"] and len(args) == 4 and args[-1] == "--version")
        ):
            if args[:1] == ["toolchain"] and args[1:2] not in (["list"],):
                capabilities.update({CommandCapability.PACKAGE_INSTALL, CommandCapability.NETWORK_FETCH})
            else:
                capabilities.add(CommandCapability.READ_ONLY_QUERY)
        elif any(item in {"install", "uninstall", "add", "default"} for item in args):
            capabilities.update({CommandCapability.PACKAGE_INSTALL, CommandCapability.NETWORK_FETCH})
        else:
            raise _command_failure(
                CommandCapability.UNKNOWN,
                "toolchain command shape is not owner-declared",
                argv,
                context,
            )
    elif executable == "git":
        if args[:2] == ["-C", args[1] if len(args) > 1 else ""] and args[2:] == ["rev-parse", "--verify", "HEAD"]:
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
        elif args == ["--version"]:
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
        elif any(item in {"clone", "fetch", "pull", "push", "checkout", "reset"} for item in args):
            capabilities.add(CommandCapability.PACKAGE_INSTALL)
        else:
            raise _command_failure(CommandCapability.UNKNOWN, "git command shape is not owner-declared", argv, context)
    elif executable == "dpkg-query":
        if args[:1] in (["--show"], ["--listfiles"]):
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
        else:
            raise _command_failure(
                CommandCapability.UNKNOWN,
                "dpkg-query command shape is not owner-declared",
                argv,
                context,
            )
    elif executable == "gpg":
        if args[:2] == ["--show-keys", "--with-colons"]:
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
        else:
            capabilities.add(CommandCapability.PACKAGE_INSTALL)
    elif executable in {"curl", "wget", "aria2c"}:
        if args in (["--version"], ["-V"], ["--help"]):
            capabilities.add(CommandCapability.READ_ONLY_QUERY)
        else:
            capabilities.add(CommandCapability.NETWORK_FETCH)
    elif executable == "install":
        capabilities.add(CommandCapability.PACKAGE_INSTALL)
    elif executable in {"id", "mktemp", "cat", "rm", "command", "printf", "test", "source", "cd"}:
        capabilities.add(CommandCapability.READ_ONLY_QUERY)
    else:
        capabilities.add(CommandCapability.EXECUTABLE_VERIFICATION)

    return capabilities


def classify_command(
    argv: Sequence[str], *, context: CommandProvenance
) -> frozenset[CommandCapability]:
    """Validate and classify one complete command graph under its owner phase."""
    if context.phase not in _COMMAND_PHASES or context.owner not in _COMMAND_OWNERS or not context.operation:
        raise _command_failure(CommandCapability.UNKNOWN, "invalid command provenance", argv, context)
    if context.phase == "image-install" and context.owner != "image-installer":
        raise _command_failure(CommandCapability.UNKNOWN, "image-install requires image-installer ownership", argv, context)
    if context.phase == "image-verify" and context.owner != "typed-verifier":
        raise _command_failure(CommandCapability.UNKNOWN, "image-verify requires typed-verifier ownership", argv, context)
    if context.phase == "post-create" and context.owner not in {"shared-post-create", "parent-hook"}:
        raise _command_failure(CommandCapability.UNKNOWN, "post-create requires shared or parent-hook ownership", argv, context)
    if context.method is not None and context.method not in {item.value for item in Method}:
        raise _command_failure(CommandCapability.UNKNOWN, "method is not a closed dependency method", argv, context)
    expected_methods = _COMMAND_OPERATION_METHODS.get(context.operation)
    if expected_methods is not None and context.method not in expected_methods:
        raise _command_failure(CommandCapability.UNKNOWN, "operation and method provenance disagree", argv, context)
    if context.phase == "image-verify" and not context.operation.startswith("verify-"):
        raise _command_failure(CommandCapability.UNKNOWN, "image verification operation is not a verifier operation", argv, context)
    if context.phase == "image-install" and not (
        context.operation.startswith("install-") or context.operation.startswith("verify-")
    ):
        raise _command_failure(CommandCapability.UNKNOWN, "image install operation is not owner-declared", argv, context)
    if not hasattr(argv, "__iter__") or type(argv) in (str, bytes) or not argv:
        raise _command_failure(CommandCapability.UNKNOWN, "argv must be a non-empty string sequence", (), context)
    normalized = tuple(argv)
    if any(type(item) is not str or not item for item in normalized):
        raise _command_failure(CommandCapability.UNKNOWN, "argv contains an empty or non-string token", normalized, context)
    if any(CONTROL_RE.search(item) for item in normalized):
        raise _command_failure(CommandCapability.UNKNOWN, "argv contains an empty or control-character token", normalized, context)

    # Unwrap only the finite env grammar.  env -S and an absent target would
    # require a second parser and therefore fail closed.
    if _command_basename(normalized[0]) == "env":
        index = 1
        while index < len(normalized) and "=" in normalized[index] and not normalized[index].startswith("-"):
            index += 1
        if index >= len(normalized) or normalized[index] == "-S":
            raise _command_failure(CommandCapability.UNKNOWN, "env child selection is dynamic", normalized, context)
        if normalized[index] == "--":
            index += 1
        if index >= len(normalized):
            raise _command_failure(CommandCapability.UNKNOWN, "env has no command target", normalized, context)
        nested = classify_command(normalized[index:], context=context)
        capabilities = set(nested)
    else:
        capabilities = _command_shape_capabilities(normalized, context)

    if context.privileged_requested:
        capabilities.add(CommandCapability.PRIVILEGE_ESCALATION)
    if context.phase in {"image-verify", "post-create"}:
        denied = capabilities & {
            CommandCapability.SHELL_EVALUATION,
            CommandCapability.DYNAMIC_INTERPRETER,
            CommandCapability.UNKNOWN,
            CommandCapability.PACKAGE_INSTALL,
            CommandCapability.NETWORK_FETCH,
            CommandCapability.PRIVILEGE_ESCALATION,
        }
        if denied:
            capability = next(
                item
                for item in (
                    CommandCapability.SHELL_EVALUATION,
                    CommandCapability.DYNAMIC_INTERPRETER,
                    CommandCapability.PACKAGE_INSTALL,
                    CommandCapability.NETWORK_FETCH,
                    CommandCapability.PRIVILEGE_ESCALATION,
                    CommandCapability.UNKNOWN,
                )
                if item in denied
            )
            raise _command_failure(capability, f"{capability.value} is not allowed in {context.phase}", normalized, context)
    elif CommandCapability.SHELL_EVALUATION in capabilities or CommandCapability.DYNAMIC_INTERPRETER in capabilities or CommandCapability.UNKNOWN in capabilities:
        capability = next(
            item for item in (
                CommandCapability.SHELL_EVALUATION,
                CommandCapability.DYNAMIC_INTERPRETER,
                CommandCapability.UNKNOWN,
            ) if item in capabilities
        )
        raise _command_failure(capability, f"{capability.value} is not allowed in image-install", normalized, context)
    return frozenset(capabilities)


@dataclass(frozen=True)
class PostCreateGraphNode:
    """One observed shared post-create graph edge."""

    kind: str
    value: tuple[str, ...]
    owner: str = "shared-post-create"
    operation: str = "post-create-readback"


@dataclass(frozen=True)
class PostCreateExecutionGraph:
    """Typed execution graph recorded by the post-create shell harness."""

    nodes: tuple[PostCreateGraphNode, ...]
    parent_hook_path: str | None = None
    parent_hook_exit_status: int | None = None

    def external_commands(self) -> tuple[PostCreateGraphNode, ...]:
        """Return external command edges in observation order."""
        return tuple(node for node in self.nodes if node.kind == "external")


def build_post_create_execution_graph(
    commands: Sequence[Sequence[str]],
    *,
    builtins: Sequence[str] = (),
    redirections: Sequence[str] = (),
    owner_root: Path | str | None = None,
    parent_root: Path | str | None = None,
    parent_hook_path: str | None = None,
    parent_hook_exit_status: int | None = None,
) -> PostCreateExecutionGraph:
    """Classify a recorded shell trace without inspecting shell source text."""
    nodes: list[PostCreateGraphNode] = []
    for argv in commands:
        normalized = tuple(argv)
        classify_command(
            normalized,
            context=CommandProvenance(
                phase="post-create",
                owner="shared-post-create",
                operation="post-create-readback",
                method=None,
                privileged_requested=False,
                owner_root=str(owner_root) if owner_root is not None else None,
            ),
        )
        nodes.append(PostCreateGraphNode("external", normalized))
    nodes.extend(
        PostCreateGraphNode("builtin", (name,)) for name in builtins
    )
    nodes.extend(
        PostCreateGraphNode("redirection", (value,)) for value in redirections
    )
    if parent_hook_path is not None:
        hook = Path(parent_hook_path)
        selected_parent_root = (
            Path(parent_root)
            if parent_root is not None
            else Path(owner_root)
            if owner_root is not None
            else Path(__file__).resolve().parents[2]
        )
        try:
            selected_parent_root = selected_parent_root.resolve(strict=True)
            expected_hook = selected_parent_root / ".devcontainer" / "post-create-parent.sh"
            expected_hook_resolved = expected_hook.resolve(strict=True)
            hook_resolved = hook.resolve(strict=True)
            hook_resolved.relative_to(selected_parent_root)
        except (OSError, ValueError) as exc:
            raise DependencyError(
                "command-boundary-unknown: parent hook path is outside its owner root"
            ) from exc
        if (
            not hook.is_absolute()
            or hook.is_symlink()
            or not hook.is_file()
            or hook_resolved != expected_hook_resolved
        ):
            raise DependencyError(
                "command-boundary-unknown: parent hook path is not the canonical non-symlink regular file"
            )
        nodes.append(
            PostCreateGraphNode(
                "parent-hook",
                (parent_hook_path, str(parent_hook_exit_status or 0)),
                owner="parent-hook",
                operation="parent-hook-dispatch",
            )
        )
    return PostCreateExecutionGraph(
        tuple(nodes),
        parent_hook_path=parent_hook_path,
        parent_hook_exit_status=parent_hook_exit_status,
    )


def check_python_source_safety(source: str | Path) -> tuple[CommandBoundaryFinding, ...]:
    """Find unsafe Python subprocess/eval structure without lexical matching."""
    text = Path(source).read_text(encoding="utf-8") if isinstance(source, Path) else source
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise DependencyError(f"command-boundary-ast-parse: {exc}") from exc
    subprocess_aliases: set[str] = {"subprocess"}
    process_functions: dict[str, str] = {}
    findings: list[CommandBoundaryFinding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    subprocess_aliases.add(alias.asname or "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in {"run", "Popen", "call", "check_call", "check_output"}:
                    process_functions[alias.asname or alias.name] = alias.name
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        process_call = False
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            process_call = node.func.value.id in subprocess_aliases and node.func.attr in {
                "run", "Popen", "call", "check_call", "check_output"
            }
        elif isinstance(node.func, ast.Name):
            process_call = node.func.id in process_functions
        if process_call:
            shell = next((keyword.value for keyword in node.keywords if keyword.arg == "shell"), None)
            if shell is not None and not (isinstance(shell, ast.Constant) and shell.value is False):
                findings.append(CommandBoundaryFinding(CommandCapability.SHELL_EVALUATION, "subprocess shell value is not literal False", (), "image-install"))
        if isinstance(node.func, ast.Name) and node.func.id == "eval":
            findings.append(CommandBoundaryFinding(CommandCapability.DYNAMIC_INTERPRETER, "direct builtin eval call", (), "image-install"))
    return tuple(findings)


def validate_python_source_safety(source: str | Path) -> None:
    """Raise a stable typed failure when Python source contains unsafe calls."""
    findings = check_python_source_safety(source)
    if findings:
        raise DependencyError(findings[0].render())


@dataclass(frozen=True)
class NpmToolchain:
    """Validated Node/npm paths and the minimal PATH used for npm commands."""

    node: Path
    npm: Path
    path: str


def resolve_npm_toolchain(workspace: Path) -> NpmToolchain:
    """Resolve OCI image/system Node tools without accepting ambient PATH entries."""
    env_executable = Path(NPM_ENV_EXECUTABLE)
    if not env_executable.is_file() or not os.access(env_executable, os.X_OK):
        raise DependencyError(
            f"npm-global requires executable launcher: {NPM_ENV_EXECUTABLE}"
        )
    trusted_path = os.pathsep.join(NPM_TRUSTED_BIN_DIRS)
    trusted_dirs = {Path(directory) for directory in NPM_TRUSTED_BIN_DIRS}
    workspace_root = workspace.resolve()
    resolved: dict[str, Path] = {}
    for executable in ("node", "npm"):
        candidate_text = shutil.which(executable, path=trusted_path)
        if candidate_text is None:
            raise DependencyError(
                f"npm-global requires a trusted {executable} executable"
            )
        candidate = Path(candidate_text)
        if not candidate.is_absolute():
            raise DependencyError(
                f"npm-global {executable} executable is not absolute: {candidate}"
            )
        try:
            resolved_candidate = candidate.resolve(strict=False)
        except OSError as exc:
            raise DependencyError(
                f"npm-global {executable} executable cannot be resolved: {candidate}"
            ) from exc
        try:
            resolved_candidate.relative_to(workspace_root)
        except ValueError:
            pass
        else:
            raise DependencyError(
                f"npm-global {executable} executable is inside workspace: {candidate}"
            )
        if Path(os.path.normpath(str(candidate.parent))) not in trusted_dirs:
            raise DependencyError(
                f"npm-global {executable} executable is outside trusted Node/system directories: "
                f"{candidate}"
            )
        allowed_root_text = NPM_TRUSTED_BIN_ROOTS.get(str(candidate.parent))
        if allowed_root_text is None:  # pragma: no cover - mappings are source-owned.
            raise DependencyError(
                f"npm-global {executable} executable has no trusted root: {candidate}"
            )
        allowed_root = Path(allowed_root_text).resolve()
        try:
            resolved_candidate.relative_to(allowed_root)
        except ValueError as exc:
            raise DependencyError(
                f"npm-global {executable} resolved path escapes trusted Node/system root: "
                f"{resolved_candidate}"
            ) from exc
        if not resolved_candidate.is_absolute():
            raise DependencyError(
                f"npm-global {executable} executable resolved path is not absolute: "
                f"{resolved_candidate}"
            )
        resolved[executable] = candidate
    return NpmToolchain(
        node=resolved["node"],
        npm=resolved["npm"],
        path=trusted_path,
    )


def parse_python_extras(raw: str | Sequence[str]) -> tuple[str, ...]:
    """Parse ordered comma-separated or sequence-form Python extras."""
    values = raw.split(",") if isinstance(raw, str) else list(raw)
    extras: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value or value != value.strip():
            raise DependencyError(
                "Python extras must be non-empty names without surrounding whitespace"
            )
        if PYTHON_EXTRA_RE.fullmatch(value) is None:
            raise DependencyError(f"invalid Python extra name: {value}")
        canonical = canonicalize_name(value)
        if canonical in seen:
            raise DependencyError(f"duplicate Python extra: {value}")
        seen.add(canonical)
        extras.append(value)
    return tuple(extras)


def validate_project_extras(
    workspace: Path, extras: Sequence[str]
) -> tuple[str, ...]:
    """Validate requested extras against ``project.optional-dependencies``."""
    validated = parse_python_extras(extras)
    pyproject = workspace / "pyproject.toml"
    if not pyproject.is_file():
        raise DependencyError(f"project packaging manifest is missing: {pyproject}")
    try:
        with pyproject.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DependencyError(f"cannot parse project packaging manifest: {pyproject}") from exc
    project = document.get("project") if isinstance(document, dict) else None
    optional = project.get("optional-dependencies") if isinstance(project, dict) else None
    if not isinstance(optional, dict):
        raise DependencyError(
            f"project.optional-dependencies is missing: {pyproject}"
        )
    available = {
        canonicalize_name(name)
        for name in optional
        if isinstance(name, str) and PYTHON_EXTRA_RE.fullmatch(name)
    }
    missing = [extra for extra in validated if canonicalize_name(extra) not in available]
    if missing:
        raise DependencyError(
            "project extras are not declared in pyproject.toml: " + ", ".join(missing)
        )
    return validated


def install_project_extras(
    workspace: Path,
    extras: Sequence[str],
    *,
    runner: CommandRunner | None = None,
) -> tuple[str, ...]:
    """Install one project editable with validated extras, then run pip check."""
    validated = validate_project_extras(workspace, extras)
    command_runner = runner or SubprocessRunner()
    requirement = f"{workspace}[{','.join(validated)}]"
    command_runner.run(
        [sys.executable, "-m", "pip", "install", "--editable", requirement],
        cwd=workspace,
    )
    command_runner.run([sys.executable, "-m", "pip", "check"], cwd=workspace)
    return validated


@dataclass(frozen=True)
class RuntimeIdentity:
    """Runtime OS and architecture identity required by the canonical installer."""

    os_id: str
    version_id: str
    platform: str


def read_runtime_identity(
    os_release: Path = Path("/etc/os-release"),
    *,
    machine: str | None = None,
) -> RuntimeIdentity:
    """Read the typed Ubuntu/Jammy and Linux platform identity before installs."""
    values: dict[str, str] = {}
    try:
        for raw_line in os_release.read_text(encoding="utf-8").splitlines():
            name, separator, raw_value = raw_line.partition("=")
            if separator and name in {"ID", "VERSION_ID"}:
                values[name] = raw_value.strip().strip('"').strip("'")
    except OSError as exc:
        raise DependencyError(f"runtime identity cannot read {os_release}: {exc}") from exc
    os_id = values.get("ID", "")
    version_id = values.get("VERSION_ID", "")
    machine_name = (machine or platform.machine()).lower()
    machine_alias = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    runtime_platform = f"linux/{machine_alias.get(machine_name, machine_name)}"
    if not os_id or not version_id or runtime_platform == "linux/":
        raise DependencyError(
            f"runtime identity is incomplete: ID={os_id!r} VERSION_ID={version_id!r} "
            f"platform={runtime_platform!r}"
        )
    return RuntimeIdentity(os_id, version_id, runtime_platform)


def validate_runtime_identity(
    plan: DependencyPlan,
    identity: RuntimeIdentity | None = None,
) -> RuntimeIdentity:
    """Fail closed on non-Ubuntu22/amd64 before any installer side effect."""
    resolved = identity or read_runtime_identity()
    if resolved.os_id != "ubuntu" or resolved.version_id != "22.04":
        raise DependencyError(
            "runtime identity requires Ubuntu 22.04: "
            f"ID={resolved.os_id} VERSION_ID={resolved.version_id}"
        )
    if resolved.platform != "linux/amd64":
        raise DependencyError(
            f"runtime identity requires linux/amd64: platform={resolved.platform}"
        )
    for record in plan.records:
        if record.platform is not None and record.platform != resolved.platform:
            raise DependencyError(
                f"dependency record {record.id} requires {record.platform}, "
                f"but runtime platform is {resolved.platform}; no compatibility fallback is defined"
            )
        if record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY} \
            and record.source.startswith("ubuntu:") \
            and record.source != "ubuntu:22.04":
            raise DependencyError(
                f"dependency record {record.id} requires canonical source ubuntu:22.04, "
                f"got {record.source}"
            )
    return resolved


# StrEnum is unavailable on supported tomli/Python <3.11 runtimes.
class ManifestRole(str, Enum):  # noqa: UP042
    """Closed set of manifest roles used during source resolution."""

    PARENT_OVERLAY = "parent-overlay"
    CANONICAL = "canonical"


@dataclass(frozen=True)
class ManifestSource:
    """A resolved manifest path with its structural role."""

    path: Path
    role: ManifestRole

    def __post_init__(self) -> None:
        """Normalize the source path for stable comparisons and projections."""
        object.__setattr__(self, "path", self.path.resolve())


class Method(str, Enum):
    """Closed set of supported dependency installation mechanisms."""

    APT_PACKAGE = "apt-package"
    APT_REPOSITORY = "apt-repository"
    NPM_GLOBAL = "npm-global"
    PIPX = "pipx"
    RELEASE_ASSET = "release-asset"
    RUST_TOOLCHAIN = "rust-toolchain"
    LEAN_TOOLCHAIN = "lean-toolchain"
    CARGO_SOURCE_BUILD = "cargo-source-build"
    BROWSER_INSTALL = "browser-install"


class VerificationKind(str, Enum):
    """Closed set of owner-specific live verification mechanisms."""

    APT_PACKAGE = "apt-package"
    APT_REPOSITORY = "apt-repository"
    NPM_PACKAGE = "npm-package"
    PIPX_PACKAGE = "pipx-package"
    ABSOLUTE_EXECUTABLE = "absolute-executable"
    RUST_TOOLCHAIN = "rust-toolchain"
    LEAN_TOOLCHAIN = "lean-toolchain"
    CARGO_BINARY = "cargo-binary"
    BROWSER_EXECUTABLE = "browser-executable"


@dataclass(frozen=True)
class VerificationSpec:
    """Frozen typed owner-specific verification identity."""

    kind: VerificationKind
    executable: str | None = None
    path: str | None = None
    args: tuple[str, ...] = ()
    output_contains: str | None = None
    executable_globs: tuple[str, ...] = ()

    def payload(self) -> dict[str, Any]:
        """Return the manifest-safe JSON representation."""
        return {
            "kind": self.kind.value,
            "executable": self.executable,
            "path": self.path,
            "args": list(self.args),
            "output_contains": self.output_contains,
            "executable_globs": list(self.executable_globs),
        }


@dataclass(frozen=True)
class DependencyRecord:
    """One fully typed dependency record."""

    id: str
    package: str
    method: Method
    version: str
    source: str
    verification: VerificationSpec
    deps: tuple[str, ...]
    provides: tuple[str, ...]
    failure_policy: str
    platform: str | None = None
    key_fingerprint: str | None = None
    key_url: str | None = None
    repository_suite: str | None = None
    repository_components: tuple[str, ...] = ()
    repository_packages_sha256: str | None = None
    repository_package_url: str | None = None
    repository_package_sha256: str | None = None
    checksum: str | None = None
    checksums: tuple[tuple[str, str], ...] = ()
    asset: str | None = None
    assets: tuple[tuple[str, str], ...] = ()
    archive_format: str | None = None
    extract: str | None = None
    destination: str | None = None
    executable_owner_packages: tuple[str, ...] = ()
    repo: str | None = None
    commit: str | None = None
    source_identity: str | None = None
    source_tree_sha256: str | None = None
    cargo_lock_sha256: str | None = None
    locked: bool | None = None
    browser: str | None = None
    browser_cache_path: str | None = None
    components: tuple[str, ...] = ()

    def payload(self) -> dict[str, Any]:
        """Return a canonical JSON-compatible representation."""
        return dataclasses.asdict(self) | {
            "method": self.method.value,
            "verification": self.verification.payload(),
        }

    def fingerprint(self) -> str:
        """Return the stable identity hash used by receipts."""
        encoded = canonical_json(self.payload()).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class LoadedManifest:
    """A manifest and its structured source."""

    source: ManifestSource
    records: tuple[DependencyRecord, ...]

    @property
    def path(self) -> Path:
        """Return the source path for diagnostics and plan projections."""
        return self.source.path


@dataclass(frozen=True)
class DependencyPlan:
    """Validated merged records and deterministic execution order."""

    records: tuple[DependencyRecord, ...]
    order: tuple[str, ...]
    sources: tuple[Path, ...]
    dependency_providers: tuple[tuple[str, tuple[str, ...]], ...]
    fingerprint: str
    source_roles: tuple[str, ...] = ()

    def by_id(self) -> dict[str, DependencyRecord]:
        """Return records indexed by their stable IDs."""
        return {record.id: record for record in self.records}

    def providers_for(self, record_id: str) -> tuple[str, ...]:
        """Return the record providers required by one record."""
        return dict(self.dependency_providers).get(record_id, ())


@dataclass(frozen=True)
class VerifiedExecutable:
    """A manifest-pinned executable whose receipt and live state agree."""

    record_id: str
    manifest_version: str
    executable: str
    absolute_path: str
    record_fingerprint: str
    plan_fingerprint: str
    verification_output: str


class CommandRunner(Protocol):
    """Protocol used by the installer and dry-run tests."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        privileged: bool = False,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one argv list without a shell."""
        ...


class SubprocessRunner:
    """Production command runner with explicit argv-only semantics."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        privileged: bool = False,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute argv, adding sudo only for explicitly privileged actions."""
        command = [str(item) for item in argv]
        if not command or any(not item for item in command):
            raise DependencyError("command argv must contain non-empty strings")
        if privileged and os.geteuid() != 0:
            if shutil.which("sudo") is None:
                raise DependencyError(
                    "privileged dependency action requires root or sudo"
                )
            command.insert(0, "sudo")
        process_environment = None
        if env is not None:
            process_environment = os.environ.copy()
            process_environment.update(env)
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            check=True,
            shell=False,
            text=True,
            capture_output=capture_output,
            env=process_environment,
        )


def canonical_json(value: object) -> str:
    """Serialize JSON deterministically for plan and receipt fingerprints."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DependencyError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if CONTROL_RE.search(normalized):
        raise DependencyError(f"{field} must not contain control characters")
    if normalized.startswith("-"):
        raise DependencyError(f"{field} must not be an option")
    return normalized


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field)


def _string_list(
    value: object, field: str, *, allow_empty: bool = True
) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DependencyError(f"{field} must be an array of strings")
    result = tuple(item.strip() for item in value)
    if any(not item for item in result):
        raise DependencyError(f"{field} cannot contain empty strings")
    if not allow_empty and not result:
        raise DependencyError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise DependencyError(f"{field} must not contain duplicates")
    return result


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise DependencyError(f"{field} must be a boolean")
    return value


def _argv_args(value: object, field: str) -> tuple[str, ...]:
    """Validate non-empty argv arguments without allowing control data."""
    if not isinstance(value, list) or not value:
        raise DependencyError(f"{field} must be a non-empty argv array")
    result = tuple(value)
    if any(
        not isinstance(item, str)
        or not item
        or item != item.strip()
        or CONTROL_RE.search(item)
        for item in result
    ):
        raise DependencyError(f"{field} must contain non-empty argv-safe strings")
    return result


def _validate_safe_glob(value: str, field: str) -> None:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or str(path) != value
        or not value
        or TRAVERSAL_RE.search(value)
        or any(
            not part
            or CONTROL_RE.search(part)
            or not re.fullmatch(r"[A-Za-z0-9._*?\[\]-]+", part)
            for part in path.parts
        )
    ):
        raise DependencyError(f"{field} must be a safe relative cache glob")


def _checksums(value: object) -> tuple[tuple[str, str], ...]:
    if isinstance(value, str):
        if SHA256_RE.fullmatch(value) is None:
            raise DependencyError("checksum must be a 64-character SHA256")
        return (("default", value.lower()),)
    if not isinstance(value, dict) or not value:
        raise DependencyError("checksum must be a SHA256 string or architecture map")
    result: list[tuple[str, str]] = []
    for arch, checksum in value.items():
        arch_name = _string(arch, "checksum architecture")
        checksum_value = _string(checksum, f"checksum[{arch_name}]")
        if SHA256_RE.fullmatch(checksum_value) is None:
            raise DependencyError(
                f"checksum[{arch_name}] must be a 64-character SHA256"
            )
        result.append((arch_name, checksum_value.lower()))
    return tuple(sorted(result))


def _string_map(value: object, field: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict) or not value:
        raise DependencyError(f"{field} must be a non-empty string map")
    result = []
    for key, item in value.items():
        key_value = _string(key, f"{field} key")
        item_value = _string(item, f"{field}[{key_value}]")
        result.append((key_value, item_value))
    return tuple(sorted(result))


def _validate_url(value: str, field: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if (
        parsed.scheme not in {"https", "file"}
        or (not parsed.netloc and parsed.scheme == "https")
        or parsed.query
        or parsed.fragment
        or TRAVERSAL_RE.search(parsed.path)
    ):
        raise DependencyError(f"{field} must be an https or file URL")


def _validate_https_url(value: str, field: str) -> None:
    _validate_url(value, field)
    if not value.startswith("https://"):
        raise DependencyError(f"{field} must be an https URL")


def _validate_safe_member(value: str, field: str) -> None:
    if value == "none":
        return
    if "/" in value or "\\" in value or TRAVERSAL_RE.search(value):
        raise DependencyError(f"{field} must be one safe archive member name")
    if SAFE_MEMBER_RE.fullmatch(value) is None:
        raise DependencyError(f"{field} has an unsupported archive member name")


def _validate_safe_asset_path(value: str, field: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or TRAVERSAL_RE.search(value):
        raise DependencyError(f"{field} must be a safe relative asset path")
    if any(SAFE_MEMBER_RE.fullmatch(part) is None for part in path.parts):
        raise DependencyError(f"{field} has an unsupported asset path")


def _validate_absolute_path(value: str, field: str, *, prefix: str) -> None:
    if not value.startswith("/") or TRAVERSAL_RE.search(value):
        raise DependencyError(f"{field} must be an absolute path below {prefix}")
    path = PurePosixPath(value)
    if str(path) != value or not str(path).startswith(f"{prefix}/"):
        raise DependencyError(f"{field} must be an absolute path below {prefix}")


def _validate_absolute_executable_path(value: str, field: str) -> None:
    path = PurePosixPath(value)
    if (
        not value.startswith("/")
        or path.is_absolute() is False
        or str(path) != value
        or TRAVERSAL_RE.search(value)
    ):
        raise DependencyError(f"{field} must be a normalized absolute executable path")


VERIFICATION_KIND_BY_METHOD = {
    Method.APT_PACKAGE: VerificationKind.APT_PACKAGE,
    Method.APT_REPOSITORY: VerificationKind.APT_REPOSITORY,
    Method.NPM_GLOBAL: VerificationKind.NPM_PACKAGE,
    Method.PIPX: VerificationKind.PIPX_PACKAGE,
    Method.RELEASE_ASSET: VerificationKind.ABSOLUTE_EXECUTABLE,
    Method.RUST_TOOLCHAIN: VerificationKind.RUST_TOOLCHAIN,
    Method.LEAN_TOOLCHAIN: VerificationKind.LEAN_TOOLCHAIN,
    Method.CARGO_SOURCE_BUILD: VerificationKind.CARGO_BINARY,
    Method.BROWSER_INSTALL: VerificationKind.BROWSER_EXECUTABLE,
}


def _parse_verification(
    value: object, *, record_id: str, method: Method
) -> VerificationSpec:
    if not isinstance(value, dict) or not value:
        raise DependencyError(f"{record_id}.verification must be a non-empty table")
    allowed_by_kind: dict[VerificationKind, set[str]] = {
        VerificationKind.APT_PACKAGE: {
            "executable",
            "args",
            "output_contains",
        },
        VerificationKind.APT_REPOSITORY: {
            "executable",
            "args",
            "output_contains",
        },
        VerificationKind.NPM_PACKAGE: {
            "executable",
            "args",
            "output_contains",
        },
        VerificationKind.PIPX_PACKAGE: {
            "executable",
            "args",
            "output_contains",
        },
        VerificationKind.ABSOLUTE_EXECUTABLE: {"path", "args", "output_contains"},
        VerificationKind.RUST_TOOLCHAIN: set(),
        VerificationKind.LEAN_TOOLCHAIN: set(),
        VerificationKind.CARGO_BINARY: {"path", "args", "output_contains"},
        VerificationKind.BROWSER_EXECUTABLE: {
            "args",
            "output_contains",
            "executable_globs",
        },
    }
    if "kind" not in value:
        raise DependencyError(f"{record_id}.verification missing fields: kind")
    kind_value = _string(value["kind"], f"{record_id}.verification.kind")
    try:
        kind = VerificationKind(kind_value)
    except ValueError as exc:
        raise DependencyError(
            f"{record_id}.verification: unsupported kind {kind_value}"
        ) from exc
    expected = VERIFICATION_KIND_BY_METHOD[method]
    if kind is not expected:
        raise DependencyError(
            f"{record_id}.verification.kind {kind.value} is incompatible with "
            f"method {method.value}; expected {expected.value}"
        )
    unsupported = sorted(set(value) - {"kind"} - allowed_by_kind[kind])
    if unsupported:
        raise DependencyError(
            f"{record_id}.verification: unsupported fields: {', '.join(unsupported)}"
        )
    executable = _optional_string(
        value.get("executable"), f"{record_id}.verification.executable"
    )
    path = _optional_string(value.get("path"), f"{record_id}.verification.path")
    output_contains = _optional_string(
        value.get("output_contains"), f"{record_id}.verification.output_contains"
    )
    args = (
        _argv_args(value["args"], f"{record_id}.verification.args")
        if "args" in value
        else ()
    )
    executable_globs = (
        _string_list(
            value["executable_globs"],
            f"{record_id}.verification.executable_globs",
            allow_empty=False,
        )
        if "executable_globs" in value
        else ()
    )
    if kind in {VerificationKind.APT_PACKAGE, VerificationKind.APT_REPOSITORY}:
        record_owned_fields = {"executable", "args", "output_contains"}
        provided_record_owned_fields = record_owned_fields & value.keys()
        if provided_record_owned_fields not in (set(), record_owned_fields):
            raise DependencyError(
                f"{record_id}.verification requires executable, args, and output_contains"
            )
        if provided_record_owned_fields and (
            executable is None or not args or output_contains is None
        ):
            raise DependencyError(
                f"{record_id}.verification requires executable, args, and output_contains"
            )
        if executable is not None and (
            Path(executable).name != executable or executable in SHELL_EXECUTABLES
        ):
            raise DependencyError(
                f"{record_id}.verification.executable must be one command name"
            )
    elif kind in {
        VerificationKind.NPM_PACKAGE,
        VerificationKind.PIPX_PACKAGE,
    }:
        if executable is None or not args or output_contains is None:
            raise DependencyError(
                f"{record_id}.verification requires executable, args, and output_contains"
            )
        if Path(executable).name != executable or executable in SHELL_EXECUTABLES:
            raise DependencyError(
                f"{record_id}.verification.executable must be one command name"
            )
    elif kind is VerificationKind.ABSOLUTE_EXECUTABLE:
        if path is None or not args or output_contains is None:
            raise DependencyError(
                f"{record_id}.verification requires path, args, and output_contains"
            )
        _validate_absolute_executable_path(path, f"{record_id}.verification.path")
    elif kind is VerificationKind.CARGO_BINARY:
        if path is None or not args or output_contains is None:
            raise DependencyError(
                f"{record_id}.verification requires path, args, and output_contains"
            )
        if (
            PurePosixPath(path).is_absolute()
            or str(PurePosixPath(path)) != path
            or any(part in {"", "."} for part in PurePosixPath(path).parts)
            or TRAVERSAL_RE.search(path)
        ):
            raise DependencyError(
                f"{record_id}.verification.path must be a safe relative cargo binary path"
            )
    elif kind is VerificationKind.BROWSER_EXECUTABLE:
        if not executable_globs or not args or output_contains is None:
            raise DependencyError(
                f"{record_id}.verification requires executable_globs, args, and output_contains"
            )
        for glob in executable_globs:
            _validate_safe_glob(glob, f"{record_id}.verification.executable_globs")
    elif (
        executable is not None
        or path is not None
        or args
        or output_contains is not None
        or executable_globs
    ):
        raise DependencyError(
            f"{record_id}.verification does not permit executable fields for {kind.value}"
        )
    return VerificationSpec(
        kind=kind,
        executable=executable,
        path=path,
        args=args,
        output_contains=output_contains,
        executable_globs=executable_globs,
    )


def _validate_package(record: DependencyRecord) -> None:
    if record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY}:
        if APT_PACKAGE_RE.fullmatch(record.package) is None:
            raise DependencyError(f"{record.id}.package is not an apt package name")
    elif record.method in {Method.NPM_GLOBAL, Method.PIPX}:
        pattern = (
            NPM_PACKAGE_RE if record.method is Method.NPM_GLOBAL else PYTHON_PACKAGE_RE
        )
        if pattern.fullmatch(record.package) is None:
            raise DependencyError(
                f"{record.id}.package has an unsupported registry name"
            )
    elif record.method is Method.BROWSER_INSTALL:
        if record.package not in {"chromium", "firefox", "webkit"}:
            raise DependencyError(f"{record.id}.package has an unsupported browser")
    elif VERSION_TOKEN_RE.fullmatch(record.package) is None:
        raise DependencyError(f"{record.id}.package has an unsupported value")


def _validate_method_fields(
    record: DependencyRecord, raw: Mapping[str, object]
) -> None:
    common = {
        "id",
        "package",
        "method",
        "version",
        "source",
        "platform",
        "verification",
        "deps",
        "provides",
        "failure_policy",
    }
    method_fields = {
        Method.APT_PACKAGE: {"executable_owner_packages"},
        Method.APT_REPOSITORY: {
            "key_fingerprint",
            "key_url",
            "repository_suite",
            "repository_components",
            "repository_packages_sha256",
            "repository_package_url",
            "repository_package_sha256",
            "executable_owner_packages",
        },
        Method.NPM_GLOBAL: set(),
        Method.PIPX: set(),
        Method.RELEASE_ASSET: {
            "checksum",
            "checksums",
            "asset",
            "assets",
            "archive_format",
            "extract",
            "destination",
        },
        Method.RUST_TOOLCHAIN: {"components"},
        Method.LEAN_TOOLCHAIN: set(),
        Method.CARGO_SOURCE_BUILD: {
            "repo",
            "commit",
            "source_identity",
            "locked",
            "source_tree_sha256",
            "cargo_lock_sha256",
        },
        Method.BROWSER_INSTALL: {"browser", "browser_cache_path"},
    }
    unsupported = sorted(set(raw) - common - method_fields[record.method])
    if unsupported:
        raise DependencyError(
            f"{record.id}: unsupported fields for {record.method.value}: "
            + ", ".join(unsupported)
        )


def _validate_method_values(record: DependencyRecord) -> None:
    """Validate all method-owned values before any executor argv is built."""
    if record.platform is not None and PLATFORM_RE.fullmatch(record.platform) is None:
        raise DependencyError(
            f"{record.id}.platform must be one of linux/amd64 or linux/arm64"
        )
    _validate_package(record)
    if record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY}:
        if not record.executable_owner_packages:
            raise DependencyError(f"{record.id}.executable_owner_packages is required")
        for owner_package in record.executable_owner_packages:
            if APT_PACKAGE_RE.fullmatch(owner_package) is None:
                raise DependencyError(
                    f"{record.id}.executable_owner_packages has unsupported package: "
                    f"{owner_package}"
                )
        if VERSION_TOKEN_RE.fullmatch(record.version) is None:
            raise DependencyError(f"{record.id}.version has an unsupported apt value")
        if record.method is Method.APT_REPOSITORY:
            _validate_https_url(record.source, f"{record.id}.source")
            if record.repository_suite is None:
                raise DependencyError(
                    f"{record.id}.repository_suite must be declared"
                )
            if re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9.+_-]*", record.repository_suite
            ) is None:
                raise DependencyError(
                    f"{record.id}.repository_suite has an unsupported value"
                )
            if not record.repository_components:
                raise DependencyError(
                    f"{record.id}.repository_components must not be empty"
                )
            for component in record.repository_components:
                if re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9.+_-]*", component
                ) is None:
                    raise DependencyError(
                        f"{record.id}.repository_components has an unsupported value"
                    )
            if record.repository_packages_sha256 is not None:
                if SHA256_RE.fullmatch(record.repository_packages_sha256) is None:
                    raise DependencyError(
                        f"{record.id}.repository_packages_sha256 must be a 64-character SHA256"
                    )
                if record.platform is None:
                    raise DependencyError(
                        f"{record.id}: repository_packages_sha256 requires platform"
                    )
                if len(record.repository_components) != 1:
                    raise DependencyError(
                        f"{record.id}: repository_packages_sha256 requires exactly one repository component"
                    )
            if (record.repository_package_url is None) != (
                record.repository_package_sha256 is None
            ):
                raise DependencyError(
                    f"{record.id}: repository_package_url and repository_package_sha256 must be provided together"
                )
            if record.repository_package_url is not None:
                _validate_https_url(
                    record.repository_package_url,
                    f"{record.id}.repository_package_url",
                )
                if not record.repository_package_url.lower().endswith(".deb"):
                    raise DependencyError(
                        f"{record.id}.repository_package_url must name a .deb artifact"
                    )
                assert record.repository_package_sha256 is not None
                if SHA256_RE.fullmatch(record.repository_package_sha256) is None:
                    raise DependencyError(
                        f"{record.id}.repository_package_sha256 must be a 64-character SHA256"
                    )
                _repository_package_filename(record)
        elif VERSION_TOKEN_RE.fullmatch(
            record.source
        ) is None and not record.source.startswith("https://"):
            raise DependencyError(f"{record.id}.source has an unsupported apt value")
    elif record.method is Method.NPM_GLOBAL:
        if SEMVER_RE.fullmatch(record.version) is None:
            raise DependencyError(f"{record.id}.version must be an exact version")
        _validate_https_url(record.source, f"{record.id}.source")
    elif record.method is Method.PIPX:
        try:
            Version(record.version)
        except InvalidVersion as exc:
            raise DependencyError(
                f"{record.id}.version must be an exact PEP 440 version"
            ) from exc
        _validate_https_url(record.source, f"{record.id}.source")
    elif record.method is Method.RELEASE_ASSET:
        if VERSION_TOKEN_RE.fullmatch(record.version) is None:
            raise DependencyError(
                f"{record.id}.version has an unsupported release value"
            )
        _validate_https_url(record.source, f"{record.id}.source")
        for asset in (record.asset, *[value for _, value in record.assets]):
            if asset is not None:
                _validate_safe_asset_path(asset, f"{record.id}.asset")
        for arch, _ in record.assets:
            if arch not in {"x86_64", "aarch64"}:
                raise DependencyError(
                    f"{record.id}.assets has an unsupported architecture"
                )
        assert record.archive_format is not None
        if record.archive_format not in {"binary", "tar.gz", "tar.xz", "tar"}:
            raise DependencyError(f"{record.id}.archive_format is unsupported")
        assert record.extract is not None
        _validate_safe_member(record.extract, f"{record.id}.extract")
        if (record.archive_format == "binary") != (record.extract == "none"):
            raise DependencyError(
                f"{record.id}: binary release assets require extract=none"
            )
        assert record.destination is not None
        _validate_absolute_path(
            record.destination, f"{record.id}.destination", prefix="/usr/local/bin"
        )
    elif record.method is Method.RUST_TOOLCHAIN:
        if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", record.version) is None:
            raise DependencyError(f"{record.id}.version must be an exact Rust version")
        _validate_https_url(record.source, f"{record.id}.source")
        if any(
            component not in {"rust-src", "rustfmt", "clippy", "rust-analyzer"}
            for component in record.components
        ):
            raise DependencyError(
                f"{record.id}.components contains an unsupported component"
            )
    elif record.method is Method.LEAN_TOOLCHAIN:
        if (
            re.fullmatch(r"leanprover/lean4:v[0-9]+\.[0-9]+\.[0-9]+", record.version)
            is None
        ):
            raise DependencyError(
                f"{record.id}.version must be an exact Lean toolchain"
            )
        _validate_https_url(record.source, f"{record.id}.source")
    elif record.method is Method.CARGO_SOURCE_BUILD:
        if record.source.startswith("/") or TRAVERSAL_RE.search(record.source):
            raise DependencyError(f"{record.id}.source must stay within the workspace")
        if PurePosixPath(record.source).is_absolute() or any(
            part in {"", "."} for part in PurePosixPath(record.source).parts
        ):
            raise DependencyError(
                f"{record.id}.source must be a normalized relative path"
            )
        assert record.repo is not None
        _validate_https_url(record.repo, f"{record.id}.repo")
        if record.source_identity is not None and record.source_identity not in {
            ACTIVE_SOURCE_IDENTITY,
            CANONICAL_SNAPSHOT_IDENTITY,
        }:
            raise DependencyError(
                f"{record.id}.source_identity must be one of active-source or canonical-snapshot"
            )
        if record.source_identity == CANONICAL_SNAPSHOT_IDENTITY:
            for field_name, value in (
                ("source_tree_sha256", record.source_tree_sha256),
                ("cargo_lock_sha256", record.cargo_lock_sha256),
            ):
                if value is None or SHA256_RE.fullmatch(value) is None:
                    raise DependencyError(
                        f"{record.id}.{field_name} is required for canonical-snapshot"
                    )
        elif record.source_tree_sha256 is not None or record.cargo_lock_sha256 is not None:
            raise DependencyError(
                f"{record.id}: source snapshot digests require canonical-snapshot"
            )
        if record.commit is not None and COMMIT_RE.fullmatch(record.commit) is None:
            raise DependencyError(f"{record.id}.commit must be a full 40-hex commit")
    elif record.method is Method.BROWSER_INSTALL:
        if record.browser not in {"chromium", "firefox", "webkit"}:
            raise DependencyError(f"{record.id}.browser is unsupported")
        if SEMVER_RE.fullmatch(record.version) is None:
            raise DependencyError(
                f"{record.id}.version must be an exact Playwright version"
            )
        _validate_https_url(record.source, f"{record.id}.source")
        assert record.browser_cache_path is not None
        _validate_absolute_path(
            record.browser_cache_path,
            f"{record.id}.browser_cache_path",
            prefix="/usr/local/share",
        )
    verification = record.verification
    if record.method is Method.RELEASE_ASSET:
        assert record.destination is not None
        if verification.path != record.destination:
            raise DependencyError(
                f"{record.id}: release verification path must equal destination"
            )
    elif record.method is Method.CARGO_SOURCE_BUILD:
        if verification.path is None:
            raise DependencyError(f"{record.id}: cargo verification path is required")
    elif record.method is Method.BROWSER_INSTALL:
        if not verification.executable_globs:
            raise DependencyError(f"{record.id}: browser executable glob is required")


def parse_record(raw: object, *, path: Path, index: int) -> DependencyRecord:
    """Parse and validate one TOML record into the closed typed model."""
    if not isinstance(raw, dict):
        raise DependencyError(f"{path}: records[{index}] must be a table")
    allowed = {
        "id",
        "package",
        "method",
        "version",
        "source",
        "platform",
        "verification",
        "deps",
        "provides",
        "failure_policy",
        "key_fingerprint",
        "key_url",
        "repository_suite",
        "repository_components",
        "repository_packages_sha256",
        "repository_package_url",
        "repository_package_sha256",
        "checksum",
        "checksums",
        "asset",
        "assets",
        "archive_format",
        "extract",
        "destination",
        "repo",
        "commit",
        "source_identity",
        "source_tree_sha256",
        "cargo_lock_sha256",
        "locked",
        "browser",
        "browser_cache_path",
        "components",
        "executable_owner_packages",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise DependencyError(
            f"{path}: records[{index}] unknown fields: {', '.join(unknown)}"
        )
    required = (
        "id",
        "package",
        "method",
        "version",
        "source",
        "verification",
        "deps",
        "provides",
        "failure_policy",
    )
    missing = [field for field in required if field not in raw]
    if missing:
        raise DependencyError(
            f"{path}: records[{index}] missing fields: {', '.join(missing)}"
        )
    record_id = _string(raw["id"], "id")
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]*", record_id) is None:
        raise DependencyError(f"{path}: {record_id}: invalid id")
    method_value = _string(raw["method"], f"{record_id}.method")
    if method_value not in METHODS:
        raise DependencyError(f"{path}: {record_id}: unsupported method {method_value}")
    record_package = _string(raw["package"], f"{record_id}.package")
    failure_policy = _string(raw["failure_policy"], f"{record_id}.failure_policy")
    if failure_policy not in FAILURE_POLICIES:
        raise DependencyError(
            f"{path}: {record_id}: unsupported failure policy {failure_policy}"
        )
    is_apt_method = method_value in {
        Method.APT_PACKAGE.value,
        Method.APT_REPOSITORY.value,
    }
    record = DependencyRecord(
        id=record_id,
        package=record_package,
        method=Method(method_value),
        version=_string(raw["version"], f"{record_id}.version"),
        source=_string(raw["source"], f"{record_id}.source"),
        platform=_optional_string(raw.get("platform"), f"{record_id}.platform"),
        verification=_parse_verification(
            raw["verification"], record_id=record_id, method=Method(method_value)
        ),
        deps=_string_list(raw["deps"], f"{record_id}.deps"),
        provides=_string_list(
            raw["provides"], f"{record_id}.provides", allow_empty=False
        ),
        failure_policy=failure_policy,
        key_fingerprint=_optional_string(
            raw.get("key_fingerprint"), f"{record_id}.key_fingerprint"
        ),
        key_url=_optional_string(raw.get("key_url"), f"{record_id}.key_url"),
        repository_suite=(
            _optional_string(
                raw.get("repository_suite"), f"{record_id}.repository_suite"
            )
            or ("stable" if method_value == Method.APT_REPOSITORY.value else None)
        ),
        repository_components=_string_list(
            raw.get(
                "repository_components",
                ["main"] if method_value == Method.APT_REPOSITORY.value else [],
            ),
            f"{record_id}.repository_components",
            allow_empty=method_value != Method.APT_REPOSITORY.value,
        ),
        repository_packages_sha256=_optional_string(
            raw.get("repository_packages_sha256"),
            f"{record_id}.repository_packages_sha256",
        ),
        repository_package_url=_optional_string(
            raw.get("repository_package_url"),
            f"{record_id}.repository_package_url",
        ),
        repository_package_sha256=_optional_string(
            raw.get("repository_package_sha256"),
            f"{record_id}.repository_package_sha256",
        ),
        checksum=_optional_string(raw.get("checksum"), f"{record_id}.checksum"),
        checksums=_checksums(raw["checksums"]) if "checksums" in raw else (),
        asset=_optional_string(raw.get("asset"), f"{record_id}.asset"),
        assets=_string_map(raw["assets"], f"{record_id}.assets")
        if "assets" in raw
        else (),
        archive_format=_optional_string(
            raw.get("archive_format"), f"{record_id}.archive_format"
        ),
        extract=_optional_string(raw.get("extract"), f"{record_id}.extract"),
        destination=_optional_string(
            raw.get("destination"), f"{record_id}.destination"
        ),
        executable_owner_packages=_string_list(
            raw.get(
                "executable_owner_packages",
                [record_package] if is_apt_method else [],
            ),
            f"{record_id}.executable_owner_packages",
            allow_empty=not is_apt_method,
        ),
        repo=_optional_string(raw.get("repo"), f"{record_id}.repo"),
        commit=_optional_string(raw.get("commit"), f"{record_id}.commit"),
        source_identity=_optional_string(
            raw.get("source_identity"), f"{record_id}.source_identity"
        ),
        source_tree_sha256=_optional_string(
            raw.get("source_tree_sha256"), f"{record_id}.source_tree_sha256"
        ),
        cargo_lock_sha256=_optional_string(
            raw.get("cargo_lock_sha256"), f"{record_id}.cargo_lock_sha256"
        ),
        locked=raw.get("locked") if "locked" in raw else None,
        browser=_optional_string(raw.get("browser"), f"{record_id}.browser"),
        browser_cache_path=_optional_string(
            raw.get("browser_cache_path"), f"{record_id}.browser_cache_path"
        ),
        components=_string_list(raw.get("components", []), f"{record_id}.components"),
    )
    if record.locked is not None:
        _bool(record.locked, f"{record.id}.locked")
    if record.key_fingerprint is not None:
        normalized = re.sub(r"[\s:]", "", record.key_fingerprint).upper()
        if len(normalized) != 40 or HEX_RE.fullmatch(normalized) is None:
            raise DependencyError(
                f"{record.id}.key_fingerprint must be a full 40-digit hex fingerprint"
            )
        record = dataclasses.replace(record, key_fingerprint=normalized)
    if record.key_url is not None:
        _validate_url(record.key_url, f"{record.id}.key_url")
    if record.checksum is not None and SHA256_RE.fullmatch(record.checksum) is None:
        raise DependencyError(f"{record.id}.checksum must be a 64-character SHA256")
    if record.repository_packages_sha256 is not None:
        if SHA256_RE.fullmatch(record.repository_packages_sha256) is None:
            raise DependencyError(
                f"{record.id}.repository_packages_sha256 must be a 64-character SHA256"
            )
        record = dataclasses.replace(
            record,
            repository_packages_sha256=record.repository_packages_sha256.lower(),
        )
    if record.repository_package_sha256 is not None:
        if SHA256_RE.fullmatch(record.repository_package_sha256) is None:
            raise DependencyError(
                f"{record.id}.repository_package_sha256 must be a 64-character SHA256"
            )
        record = dataclasses.replace(
            record,
            repository_package_sha256=record.repository_package_sha256.lower(),
        )
    if record.method is Method.APT_REPOSITORY and (
        record.key_fingerprint is None or record.key_url is None
    ):
        raise DependencyError(
            f"{record.id}: apt-repository requires key_url and key_fingerprint"
        )
    if record.method is Method.RELEASE_ASSET:
        if record.checksum is None and not record.checksums:
            raise DependencyError(f"{record.id}: release-asset requires checksum")
        if record.asset is None and not record.assets:
            raise DependencyError(
                f"{record.id}: release-asset requires asset or architecture assets"
            )
        if record.destination is None or record.extract is None:
            raise DependencyError(
                f"{record.id}: release-asset requires extract and destination"
            )
        _validate_url(record.source, f"{record.id}.source")
    if record.method is Method.CARGO_SOURCE_BUILD:
        if (
            record.repo is None
            or record.locked is not True
            or (record.commit is None) == (record.source_identity is None)
        ):
            raise DependencyError(
                f"{record.id}: cargo-source-build requires repo, exactly one of commit or source_identity, and locked=true"
            )
        if record.commit is not None and COMMIT_RE.fullmatch(record.commit) is None:
            raise DependencyError(f"{record.id}.commit must be a full 40-hex commit")
    if record.method is Method.BROWSER_INSTALL and (
        record.browser is None or record.browser_cache_path is None
    ):
        raise DependencyError(
            f"{record.id}: browser-install requires browser and browser_cache_path"
        )
    _validate_method_fields(record, raw)
    _validate_method_values(record)
    return record


def load_manifest(source: ManifestSource) -> LoadedManifest:
    """Load one manifest with tomllib/tomli and validate every record."""
    path = source.path
    try:
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
    except FileNotFoundError as exc:
        raise DependencyError(f"manifest not found: {path}") from exc
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise DependencyError(f"cannot parse manifest {path}: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) - {"schema", "schema_version", "records"}:
        unknown = (
            sorted(set(raw) - {"schema", "schema_version", "records"})
            if isinstance(raw, dict)
            else []
        )
        raise DependencyError(f"{path}: unknown top-level fields: {', '.join(unknown)}")
    if raw.get("schema") != SCHEMA or raw.get("schema_version") != SCHEMA_VERSION:
        raise DependencyError(
            f"{path}: schema must be {SCHEMA!r} version {SCHEMA_VERSION}"
        )
    records = raw.get("records")
    if not isinstance(records, list):
        raise DependencyError(f"{path}: records must be an array of tables")
    if not records and source.role is not ManifestRole.PARENT_OVERLAY:
        raise DependencyError(f"{path}: records must be a non-empty array of tables")
    parsed = tuple(
        parse_record(item, path=path, index=index) for index, item in enumerate(records)
    )
    ids = [record.id for record in parsed]
    if len(set(ids)) != len(ids):
        raise DependencyError(f"{path}: record ids must be unique")
    return LoadedManifest(source=source, records=parsed)


def _require_file_candidate_agreement(
    candidates: Sequence[Path], *, description: str
) -> None:
    """Reject active file candidates that are not the same filesystem entity."""
    if len(candidates) < 2:
        return
    reference = candidates[0]
    for candidate in candidates[1:]:
        try:
            if reference.samefile(candidate):
                continue
        except OSError as exc:
            raise DependencyError(
                f"cannot compare {description}: {reference} and {candidate}: {exc}"
            ) from exc
        raise DependencyError(
            f"ambiguous {description}: {reference} and {candidate} are distinct files"
        )


def manifest_sources(
    workspace: Path, vendor_root: Path | None = None
) -> tuple[ManifestSource, ...]:
    """Resolve parent-first manifest sources with structural roles."""
    workspace = workspace.resolve()
    vendor = (vendor_root or workspace / "vendor" / "agent-canon").resolve()
    parent_path = workspace / ".devcontainer" / "dependencies.toml"
    vendor_path = vendor / ".devcontainer" / "dependencies.toml"
    if vendor_root is None and not vendor_path.is_file() and parent_path.is_file():
        # A standalone source root has the canonical manifest at its workspace
        # path.  Preserve that role when resolving receipts from a fresh root.
        vendor = workspace
        vendor_path = parent_path
    if vendor == workspace and parent_path == vendor_path:
        return (
            (ManifestSource(vendor_path, ManifestRole.CANONICAL),)
            if vendor_path.is_file()
            else ()
        )
    sources: list[ManifestSource] = []
    if parent_path.is_file():
        sources.append(ManifestSource(parent_path, ManifestRole.PARENT_OVERLAY))
    if vendor_path.is_file():
        projection_path = (
            workspace / "tools" / "agent-canon" / ".devcontainer" / "dependencies.toml"
        )
        duplicate_candidates = tuple(
            path for path in (vendor_path, projection_path) if path.is_file()
        )
        _require_file_candidate_agreement(
            duplicate_candidates,
            description="canonical AgentCanon dependency manifest sources",
        )
    if vendor_path.is_file() and vendor_path.resolve() not in {
        source.path for source in sources
    }:
        sources.append(ManifestSource(vendor_path, ManifestRole.CANONICAL))
    return tuple(sources)


def _merge_optional_scalar(
    left: object, right: object, *, field: str, record_id: str
) -> object:
    if left is None:
        return right
    if right is None or left == right:
        return left
    raise DependencyError(f"incompatible duplicate {record_id}: {field}")


def merge_records(manifests: Sequence[LoadedManifest]) -> tuple[DependencyRecord, ...]:
    """Merge parent-first records while preserving parent values and order."""
    merged: OrderedDict[str, DependencyRecord] = OrderedDict()
    for manifest in manifests:
        for incoming in manifest.records:
            current = merged.get(incoming.id)
            if current is None:
                merged[incoming.id] = incoming
                continue
            scalar_fields = (
                "package",
                "method",
                "version",
                "source",
                "platform",
                "verification",
                "failure_policy",
                "key_fingerprint",
                "key_url",
                "repository_suite",
                "repository_components",
                "repository_packages_sha256",
                "repository_package_url",
                "repository_package_sha256",
                "checksum",
                "executable_owner_packages",
                "asset",
                "archive_format",
                "extract",
                "destination",
                "repo",
                "commit",
                "locked",
                "source_identity",
                "source_tree_sha256",
                "cargo_lock_sha256",
                "browser",
                "browser_cache_path",
            )
            values: dict[str, Any] = {}
            for field in scalar_fields:
                values[field] = _merge_optional_scalar(
                    getattr(current, field),
                    getattr(incoming, field),
                    field=field,
                    record_id=current.id,
                )
            checksum_union = dict(current.checksums)
            for arch, checksum in incoming.checksums:
                previous = checksum_union.get(arch)
                if previous is not None and previous != checksum:
                    raise DependencyError(
                        f"incompatible duplicate {current.id}: checksums[{arch}]"
                    )
                checksum_union[arch] = checksum
            asset_union = dict(current.assets)
            for arch, asset in incoming.assets:
                previous = asset_union.get(arch)
                if previous is not None and previous != asset:
                    raise DependencyError(
                        f"incompatible duplicate {current.id}: assets[{arch}]"
                    )
                asset_union[arch] = asset
            merged[current.id] = dataclasses.replace(
                current,
                **values,
                deps=_union(current.deps, incoming.deps),
                provides=_union(current.provides, incoming.provides),
                checksums=tuple(sorted(checksum_union.items())),
                assets=tuple(sorted(asset_union.items())),
                components=_union(current.components, incoming.components),
            )
    return tuple(merged.values())


def _union(left: Sequence[Any], right: Sequence[Any]) -> tuple[Any, ...]:
    result: list[Any] = list(left)
    for value in right:
        if value not in result:
            result.append(value)
    return tuple(result)


def build_plan(
    manifests: Sequence[LoadedManifest],
    *,
    base_capabilities: Iterable[str] = BASE_CAPABILITIES,
) -> DependencyPlan:
    """Validate providers, dependencies, and cycles before any side effect."""
    records = merge_records(manifests)
    if not records:
        raise DependencyError("merged dependency plan must contain at least one record")
    machine = platform.machine().lower()
    machine_alias = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    runtime_platform = f"linux/{machine_alias.get(machine, machine)}"
    for record in records:
        if record.platform is not None and record.platform != runtime_platform:
            raise DependencyError(
                f"dependency record {record.id} requires {record.platform}, "
                f"but runtime platform is {runtime_platform}; "
                "no compatibility fallback is defined"
            )
    by_id = {record.id: record for record in records}
    providers: dict[str, list[str]] = {}
    for record in records:
        for capability in record.provides:
            providers.setdefault(capability, []).append(record.id)
    ambiguous = sorted(
        capability for capability, ids in providers.items() if len(ids) > 1
    )
    if ambiguous:
        details = ", ".join(
            f"{capability}={providers[capability]}" for capability in ambiguous
        )
        raise DependencyError(f"provider ambiguity: {details}")
    base = set(base_capabilities)
    graph: dict[str, set[str]] = {record.id: set() for record in records}
    indegree = {record.id: 0 for record in records}
    dependency_providers: dict[str, list[str]] = {record.id: [] for record in records}
    for record in records:
        for dependency in record.deps:
            if dependency in by_id:
                provider = dependency
            elif dependency in base:
                continue
            else:
                candidates = providers.get(dependency, [])
                if not candidates:
                    raise DependencyError(
                        f"missing dependency: {record.id} -> {dependency}"
                    )
                if len(candidates) != 1:
                    raise DependencyError(
                        f"provider ambiguity: {record.id} -> {dependency}"
                    )
                provider = candidates[0]
            if provider == record.id:
                raise DependencyError(f"dependency cycle: {record.id} -> {provider}")
            if provider not in dependency_providers[record.id]:
                dependency_providers[record.id].append(provider)
            if record.id not in graph[provider]:
                graph[provider].add(record.id)
                indegree[record.id] += 1
    order_index = {record.id: index for index, record in enumerate(records)}
    ready = deque(record.id for record in records if indegree[record.id] == 0)
    ordered: list[str] = []
    while ready:
        current = ready.popleft()
        ordered.append(current)
        for dependent in sorted(graph[current], key=order_index.__getitem__):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
    if len(ordered) != len(records):
        remaining = sorted(set(by_id) - set(ordered), key=order_index.__getitem__)
        raise DependencyError(f"dependency cycle: {', '.join(remaining)}")
    sources = tuple(manifest.path for manifest in manifests)
    source_roles = tuple(manifest.source.role.value for manifest in manifests)
    payload = {
        # Absolute manifest paths are diagnostic data only.  Role identity keeps
        # the plan stable across standalone roots, fresh clones, and image builds.
        "source_roles": list(source_roles),
        "records": [record.payload() for record in records],
        "order": ordered,
        "dependency_providers": [
            [record_id, providers]
            for record_id, providers in dependency_providers.items()
        ],
    }
    fingerprint = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return DependencyPlan(
        records=records,
        order=tuple(ordered),
        sources=sources,
        dependency_providers=tuple(
            (record_id, tuple(providers))
            for record_id, providers in dependency_providers.items()
        ),
        fingerprint=fingerprint,
        source_roles=source_roles,
    )


def load_plan(workspace: Path, vendor_root: Path | None = None) -> DependencyPlan:
    """Load, merge, and fully validate the plan for a workspace."""
    sources = manifest_sources(workspace, vendor_root)
    if not sources:
        raise DependencyError("no devcontainer dependency manifest found")
    return build_plan(tuple(load_manifest(source) for source in sources))


def select_record_ids(
    plan: DependencyPlan, requested: Sequence[str] | str | None = None
) -> tuple[str, ...]:
    """Return a deterministic record selection closed over its providers."""
    if requested is None:
        return plan.order
    raw_values = [requested] if isinstance(requested, str) else list(requested)
    if not raw_values:
        raise DependencyError("--records must select at least one record")
    requested_ids: list[str] = []
    for raw_value in raw_values:
        if not isinstance(raw_value, str):
            raise DependencyError("--records values must be strings")
        for value in raw_value.split(","):
            record_id = value.strip()
            if not record_id:
                raise DependencyError("--records must not contain empty record IDs")
            if record_id not in plan.by_id():
                raise DependencyError(f"unknown dependency record: {record_id}")
            if record_id not in requested_ids:
                requested_ids.append(record_id)
    selected = set(requested_ids)
    pending = deque(requested_ids)
    while pending:
        record_id = pending.popleft()
        for provider in plan.providers_for(record_id):
            if provider not in selected:
                selected.add(provider)
                pending.append(provider)
    return tuple(record_id for record_id in plan.order if record_id in selected)


def _image_plan_payload(
    plan: DependencyPlan, selected_ids: Sequence[str]
) -> dict[str, Any]:
    """Return the immutable, path-independent image plan projection."""
    selected = tuple(selected_ids)
    by_id = plan.by_id()
    return {
        "schema": IMAGE_PLAN_SCHEMA,
        "schema_version": IMAGE_PLAN_SCHEMA_VERSION,
        "owner": "image-installer",
        "phase": "image-install",
        "plan_fingerprint": plan.fingerprint,
        "source_roles": list(plan.source_roles),
        "order": list(selected),
        "records": [by_id[record_id].payload() for record_id in selected],
        "provider_closure": [
            [record_id, list(plan.providers_for(record_id))]
            for record_id in selected
        ],
        "receipts": [f"receipts/{record_id}.json" for record_id in selected],
    }


def _image_target(
    test_root: Path | None, *, require_root: bool = False
) -> tuple[Path, bool]:
    """Resolve the canonical image target or the private test-only seam."""
    production = test_root is None
    if production:
        if require_root and os.geteuid() != 0:
            raise DependencyError("image-install requires euid=0")
        return IMAGE_DEPENDENCIES_ROOT, True
    return test_root.absolute(), False


def _image_owner(production: bool) -> tuple[int, int]:
    """Return the ownership contract for a production or test image tree."""
    if production:
        return 0, 0
    return os.geteuid(), os.getegid()


def _image_record_is_safe(record: DependencyRecord) -> bool:
    """Return whether one validated record is immutable enough for an image."""
    if record.method.value not in IMAGE_INSTALL_METHODS:
        return False
    if record.method is Method.CARGO_SOURCE_BUILD:
        return (
            record.locked is True
            and record.source_identity == CANONICAL_SNAPSHOT_IDENTITY
            and record.source_tree_sha256 is not None
            and SHA256_RE.fullmatch(record.source_tree_sha256) is not None
            and record.cargo_lock_sha256 is not None
            and SHA256_RE.fullmatch(record.cargo_lock_sha256) is not None
        )
    return True


def _lstat_image_path(path: Path, *, description: str) -> os.stat_result:
    """Read one image path without following symlinks."""
    try:
        observed = path.lstat()
    except OSError as exc:
        raise DependencyError(f"{description} is unreadable: {path}: {exc}") from exc
    if stat.S_ISLNK(observed.st_mode):
        raise DependencyError(f"{description} must not be a symlink: {path}")
    return observed


def _validate_image_parent_chain(
    target: Path,
    *,
    production: bool,
    owner_uid: int,
    owner_gid: int,
    create: bool,
) -> None:
    """Validate canonical parent components before image publication."""
    parent = target.parent
    if production and not str(parent).startswith("/usr/local/"):
        raise DependencyError(f"image target escaped canonical root: {target}")
    if production:
        root_observed = _lstat_image_path(Path("/"), description="image parent")
        if not stat.S_ISDIR(root_observed.st_mode) or (
            root_observed.st_uid != owner_uid
            or root_observed.st_gid != owner_gid
            or stat.S_IMODE(root_observed.st_mode) & 0o022
        ):
            raise DependencyError("image parent ownership or mode is unsafe: /")
    current = Path(parent.anchor or "/")
    for component in parent.parts[1:]:
        current /= component
        try:
            observed = _lstat_image_path(current, description="image parent")
        except DependencyError as exc:
            if not create or "is unreadable" not in str(exc):
                raise
            try:
                current.mkdir(mode=0o755)
                os.chown(current, owner_uid, owner_gid)
                os.chmod(current, 0o755)
            except OSError as create_exc:
                raise DependencyError(
                    f"image parent cannot be created safely: {current}: {create_exc}"
                ) from create_exc
            observed = _lstat_image_path(current, description="image parent")
        if not stat.S_ISDIR(observed.st_mode):
            raise DependencyError(f"image parent must be a directory: {current}")
        if production and (
            observed.st_uid != owner_uid
            or observed.st_gid != owner_gid
            or stat.S_IMODE(observed.st_mode) & 0o022
        ):
            raise DependencyError(
                f"image parent ownership or mode is unsafe: {current}"
            )


def _freeze_image_tree(
    staging: Path, *, owner_uid: int, owner_gid: int
) -> None:
    """Freeze every staging node to the immutable image ownership contract."""
    pending = [staging]
    nodes: list[tuple[Path, os.stat_result]] = []
    while pending:
        path = pending.pop()
        observed = _lstat_image_path(path, description="image staging path")
        if stat.S_ISDIR(observed.st_mode):
            try:
                pending.extend(path.iterdir())
            except OSError as exc:
                raise DependencyError(
                    f"image staging directory is unreadable: {path}: {exc}"
                ) from exc
        elif not stat.S_ISREG(observed.st_mode):
            raise DependencyError(f"image staging node is not regular: {path}")
        nodes.append((path, observed))
    for path, observed in sorted(
        nodes, key=lambda item: len(item[0].parts), reverse=True
    ):
        mode = IMAGE_DIRECTORY_MODE if stat.S_ISDIR(observed.st_mode) else IMAGE_FILE_MODE
        try:
            os.chown(path, owner_uid, owner_gid)
            os.chmod(path, mode)
        except OSError as exc:
            raise DependencyError(
                f"image staging freeze failed: {path}: {exc}"
            ) from exc


def _assert_frozen_image_node(
    path: Path,
    *,
    directory: bool,
    owner_uid: int,
    owner_gid: int,
    description: str,
) -> None:
    """Require one exact regular, owned, non-writable image node."""
    observed = _lstat_image_path(path, description=description)
    expected_kind = stat.S_ISDIR(observed.st_mode) if directory else stat.S_ISREG(observed.st_mode)
    expected_mode = IMAGE_DIRECTORY_MODE if directory else IMAGE_FILE_MODE
    if not expected_kind:
        raise DependencyError(f"{description} has the wrong type: {path}")
    if (
        observed.st_uid != owner_uid
        or observed.st_gid != owner_gid
        or stat.S_IMODE(observed.st_mode) != expected_mode
    ):
        raise DependencyError(f"{description} ownership or mode is unsafe: {path}")


def _verify_frozen_image_layout(
    target: Path,
    selected_ids: Sequence[str] | None,
    *,
    production: bool,
    owner_uid: int,
    owner_gid: int,
) -> tuple[Path, Path]:
    """Read-only verify the exact frozen image tree layout."""
    try:
        _validate_image_parent_chain(
            target,
            production=production,
            owner_uid=owner_uid,
            owner_gid=owner_gid,
            create=False,
        )
        _assert_frozen_image_node(
            target,
            directory=True,
            owner_uid=owner_uid,
            owner_gid=owner_gid,
            description="image dependency root",
        )
        entries = list(target.iterdir())
        if {entry.name for entry in entries} != {"plan.json", "receipts"}:
            raise DependencyError("image root contents mismatch")
        plan_path = target / "plan.json"
        receipts = target / "receipts"
        _assert_frozen_image_node(
            plan_path,
            directory=False,
            owner_uid=owner_uid,
            owner_gid=owner_gid,
            description="image plan",
        )
        _assert_frozen_image_node(
            receipts,
            directory=True,
            owner_uid=owner_uid,
            owner_gid=owner_gid,
            description="image receipts",
        )
        receipt_entries = list(receipts.iterdir())
        if selected_ids is not None:
            expected_receipts = {f"{record_id}.json" for record_id in selected_ids}
            if {entry.name for entry in receipt_entries} != expected_receipts:
                raise DependencyError("receipt set mismatch")
        for entry in receipt_entries:
            if entry.relative_to(target).parts[0] != "receipts":
                raise DependencyError("image receipt escaped its root")
            _assert_frozen_image_node(
                entry,
                directory=False,
                owner_uid=owner_uid,
                owner_gid=owner_gid,
                description="image receipt",
            )
        return plan_path, receipts
    except (DependencyError, OSError) as exc:
        if "image-verify rebuild-required" in str(exc):
            raise
        raise DependencyError(f"image-verify rebuild-required: {exc}") from exc


def image_install_plan(
    plan: DependencyPlan,
    *,
    workspace: Path,
    records: Sequence[str] | str | None = None,
    runner: CommandRunner | None = None,
    identity: RuntimeIdentity | None = None,
    final_binary_dir: Path | None = None,
    _test_image_root: Path | None = None,
) -> tuple[str, ...]:
    """Build and publish an immutable image dependency plan and receipts."""
    target, production = _image_target(_test_image_root, require_root=True)
    if (
        production
        and final_binary_dir is not None
        and final_binary_dir.resolve() != Path("/usr/local/bin")
    ):
        raise DependencyError("image final binary directory is not /usr/local/bin")
    if os.path.lexists(target):
        raise DependencyError(
            f"image dependency root already exists; rebuild-required: {target}"
        )
    selected_ids = select_record_ids(plan, records)
    by_id = plan.by_id()
    image_unsafe = [
        record_id
        for record_id in selected_ids
        if not _image_record_is_safe(by_id[record_id])
    ]
    if image_unsafe:
        raise DependencyError(
            "image-install contains methods outside the image-safe whitelist: "
            + ", ".join(image_unsafe)
        )
    validate_runtime_identity(plan, identity)
    owner_uid, owner_gid = _image_owner(production)
    if production:
        _validate_image_parent_chain(
            target,
            production=True,
            owner_uid=owner_uid,
            owner_gid=owner_gid,
            create=True,
        )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        _validate_image_parent_chain(
            target,
            production=False,
            owner_uid=owner_uid,
            owner_gid=owner_gid,
            create=False,
        )
    with tempfile.TemporaryDirectory(
        prefix=".agent-canon-image-", dir=target.parent
    ) as temporary:
        staging = Path(temporary)
        receipts = staging / "receipts"
        completed = Installer(
            runner,
            image_owned=production,
            image_owned_root=target.parent if production else None,
        ).install(
            plan,
            workspace=workspace,
            receipts=receipts,
            records=selected_ids,
            final_binary_dir=(
                (final_binary_dir or Path("/usr/local/bin"))
                if production
                else None
            ),
        )
        expected = set(selected_ids)
        if set(completed) != expected:
            raise DependencyError(
                "image-install did not complete the selected record closure: "
                f"expected={sorted(expected)} completed={sorted(completed)}"
            )
        missing_receipts = [
            record_id
            for record_id in selected_ids
            if not _receipt_path(receipts, record_id).is_file()
        ]
        if missing_receipts:
            raise DependencyError(
                "image-install requires immutable receipts for: "
                + ", ".join(missing_receipts)
            )
        if {path.name for path in staging.iterdir()} != {"receipts"}:
            raise DependencyError("image-install staging contents are unexpected")
        (staging / "plan.json").write_text(
            json.dumps(_image_plan_payload(plan, selected_ids), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        _freeze_image_tree(
            staging,
            owner_uid=owner_uid,
            owner_gid=owner_gid,
        )
        if os.path.lexists(target):
            raise DependencyError(
                f"image dependency root already exists; rebuild-required: {target}"
            )
        os.replace(staging, target)
    return tuple(completed)


def image_verify_plan(
    plan: DependencyPlan,
    *,
    workspace: Path,
    records: Sequence[str] | str | None = None,
    runner: CommandRunner | None = None,
    _test_image_root: Path | None = None,
) -> tuple[str, ...]:
    """Read and verify an image plan without writes, network, or repair."""
    target, production = _image_target(_test_image_root)
    owner_uid, owner_gid = _image_owner(production)
    try:
        # Read the stored order only after validating the frozen tree layout.
        plan_path, receipts = _verify_frozen_image_layout(
            target,
            None,
            production=production,
            owner_uid=owner_uid,
            owner_gid=owner_gid,
        )
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DependencyError(f"image-verify rebuild-required: unreadable plan: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or plan_path.is_symlink()
        or not plan_path.is_file()
    ):
        raise DependencyError("image-verify rebuild-required: image plan is malformed")
    requested = payload.get("order") if records is None else records
    if requested is None or not isinstance(requested, (str, Sequence)):
        raise DependencyError("image-verify rebuild-required: image selection is malformed")
    try:
        selected_ids = select_record_ids(plan, requested)
    except DependencyError as exc:
        raise DependencyError(
            f"image-verify rebuild-required: image selection is invalid: {exc}"
        ) from exc
    expected_plan = json.loads(
        canonical_json(_image_plan_payload(plan, selected_ids))
    )
    if payload != expected_plan:
        raise DependencyError("image-verify rebuild-required: image plan mismatch")
    # Re-check the exact receipt set after the stored order has been read.
    _verify_frozen_image_layout(
        target,
        selected_ids,
        production=production,
        owner_uid=owner_uid,
        owner_gid=owner_gid,
    )
    by_id = plan.by_id()
    installer = Installer(runner)
    for record_id in selected_ids:
        receipt = _receipt_path(receipts, record_id)
        record = by_id[record_id]
        try:
            receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DependencyError(
                f"image-verify rebuild-required: unreadable receipt: {record_id}"
            ) from exc
        if not Installer._receipt_matches(receipt, plan, record):
            raise DependencyError(
                f"image-verify rebuild-required: stale receipt: {record_id}"
            )
        try:
            if production and record.method is Method.CARGO_SOURCE_BUILD:
                installer._verify_final_binary_receipt(receipt_payload, record)
            else:
                installer.verify(
                    record,
                    workspace=workspace,
                    expected_source_identity=Installer._receipt_source_identity(receipt),
                    strict_executables=True,
                    allow_network=False,
                )
            bindings = receipt_payload.get("executable_bindings")
            if bindings and (
                installer._executable_bindings(record, workspace=workspace) != bindings
            ):
                raise DependencyError(
                    f"image-verify rebuild-required: executable drift: {record_id}"
                )
        except (DependencyError, OSError, subprocess.CalledProcessError) as exc:
            if "rebuild-required" in str(exc):
                raise
            raise DependencyError(
                f"image-verify rebuild-required: live verification failed: "
                f"{record_id}: {exc}"
            ) from exc
    return selected_ids


@dataclass(frozen=True)
class BoundaryFinding:
    """One typed Docker/parent/devcontainer ownership finding."""

    category: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one stable machine-readable finding."""
        return (
            f"DEVCONTAINER_BOUNDARY_FINDING={self.category}:{self.path}:{self.detail}"
        )


@dataclass(frozen=True)
class EnvironmentBoundaryReport:
    """Result of checking the product-image and mounted-tool boundary."""

    status: str
    findings: tuple[BoundaryFinding, ...]
    checked: tuple[str, ...]


@dataclass(frozen=True)
class EnvironmentBoundaryModel:
    """Typed ownership model for one parent or standalone AgentCanon root."""

    workspace: Path
    vendor_root: Path

    @property
    def standalone(self) -> bool:
        """Return whether the validated root is standalone AgentCanon."""
        return self.workspace.resolve() == self.vendor_root.resolve()

    def _require(
        self,
        findings: list[BoundaryFinding],
        checked: list[str],
        relative: str,
        category: str,
        *,
        executable: bool = False,
    ) -> Path | None:
        path = self.workspace / relative
        checked.append(relative)
        if not path.is_file():
            findings.append(BoundaryFinding(category, relative, "missing-file"))
            return None
        if executable and not os.access(path, os.X_OK):
            findings.append(BoundaryFinding(category, relative, "not-executable"))
        return path

    def _optional(
        self,
        checked: list[str],
        relative: str,
        *,
        executable: bool = False,
    ) -> Path | None:
        """Record an optional parent-owned path when it is present."""
        path = self.workspace / relative
        checked.append(relative)
        if not path.is_file():
            return None
        if executable and not os.access(path, os.X_OK):
            # Optional does not mean unvalidated: a present hook must remain
            # executable before the resolver can dispatch it.
            return path
        return path

    @staticmethod
    def _tokens(path: Path) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Parse Dockerfile instructions without matching install strings."""
        logical: list[str] = []
        pending = ""
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if pending:
                pending += " " + line
            else:
                pending = line
            if pending.endswith("\\"):
                pending = pending[:-1].rstrip()
                continue
            logical.append(pending)
            pending = ""
        if pending:
            logical.append(pending)
        result: list[tuple[str, tuple[str, ...]]] = []
        for line in logical:
            keyword, _, arguments = line.partition(" ")
            try:
                tokens = tuple(shlex.split(arguments, comments=True, posix=True))
            except ValueError as exc:
                raise DependencyError(
                    f"{path}: malformed Dockerfile instruction: {exc}"
                ) from exc
            result.append((keyword.upper(), tokens))
        return tuple(result)

    @staticmethod
    def _installed_apt_packages(
        instructions: Sequence[tuple[str, tuple[str, ...]]],
    ) -> frozenset[str]:
        packages: set[str] = set()
        for keyword, tokens in instructions:
            if keyword != "RUN":
                continue
            for index, token in enumerate(tokens):
                if token not in {"install", "apt-get", "apt"}:
                    continue
                if token in {"apt-get", "apt"}:
                    continue
                start = index + 1
                while start < len(tokens) and tokens[start].startswith("-"):
                    start += 1
                for package in tokens[start:]:
                    if package in {"&&", ";", "\\"} or package.startswith("-"):
                        continue
                    packages.add(package)
                break
        return frozenset(packages)

    def _resolve_agent_canon_root_path(self, relative: str) -> Path:
        """Resolve one source-relative path across active AgentCanon tool roots."""
        relative_path = PurePosixPath(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise DependencyError(
                f"invalid AgentCanon source-relative path: {relative}"
            )
        source_path = self.vendor_root.joinpath(*relative_path.parts)
        candidates = [source_path]
        if (
            not self.standalone
            and relative_path.parts
            and relative_path.parts[0] == "tools"
        ):
            candidates.append(
                self.workspace
                / "tools"
                / "agent-canon"
                / Path(*relative_path.parts[1:])
            )
        active_candidates = tuple(
            candidate for candidate in candidates if candidate.is_file()
        )
        _require_file_candidate_agreement(
            active_candidates,
            description=f"AgentCanon source path {relative}",
        )
        return active_candidates[0] if active_candidates else source_path

    def _check_parent_container(
        self, findings: list[BoundaryFinding], checked: list[str]
    ) -> None:
        self._require(findings, checked, "README.md", "parent")
        self._require(findings, checked, "docker/README.md", "docker")
        dockerfile = self._require(findings, checked, "docker/Dockerfile", "docker")
        self._require(findings, checked, "pyproject.toml", "python")
        dockerignore = self._require(findings, checked, ".dockerignore", "docker")
        gitignore = self._require(findings, checked, ".gitignore", "python")
        if dockerignore is not None:
            ignored = frozenset(
                line.strip()
                for line in dockerignore.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
            for entry in ("vendor/agent-canon", ".git", ".state"):
                if entry not in ignored:
                    findings.append(
                        BoundaryFinding(
                            "docker", str(dockerignore), f"missing-ignore:{entry}"
                        )
                    )
        if gitignore is not None:
            ignored = gitignore.read_text(encoding="utf-8")
            for entry in (".venv/", "venv/"):
                if entry not in ignored:
                    findings.append(
                        BoundaryFinding(
                            "python", str(gitignore), f"missing-ignore:{entry}"
                        )
                    )
        if dockerfile is not None:
            try:
                instructions = self._tokens(dockerfile)
            except DependencyError as exc:
                findings.append(BoundaryFinding("docker", str(dockerfile), str(exc)))
            else:
                for keyword, tokens in instructions:
                    if keyword != "RUN":
                        continue
                    if "pip" in tokens and "-r" in tokens:
                        findings.append(
                            BoundaryFinding(
                                "docker",
                                str(dockerfile),
                                "must-not-install-workspace-requirements",
                            )
                        )
    def _check_parent_devcontainer(
        self, findings: list[BoundaryFinding], checked: list[str]
    ) -> None:
        config = self._require(
            findings, checked, ".devcontainer/devcontainer.json", "parent"
        )
        if config is None:
            return
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(
                BoundaryFinding("parent", str(config), f"invalid-json:{exc}")
            )
            return
        if not isinstance(payload, dict):
            findings.append(
                BoundaryFinding("parent", str(config), "json-root-must-be-object")
            )
            return

    def validate(self) -> EnvironmentBoundaryReport:
        """Validate typed ownership coverage without running project commands."""
        findings: list[BoundaryFinding] = []
        checked: list[str] = []
        vendor_prefix = (
            self.vendor_root.relative_to(self.workspace).as_posix()
            if not self.standalone
            else "."
        )
        for relative in (
            f"{vendor_prefix}/.devcontainer/dependencies.toml"
            if not self.standalone
            else ".devcontainer/dependencies.toml",
            f"{vendor_prefix}/.devcontainer/post-create.sh"
            if not self.standalone
            else ".devcontainer/post-create.sh",
            f"{vendor_prefix}/tools/agent_tools/devcontainer_dependencies.py"
            if not self.standalone
            else "tools/agent_tools/devcontainer_dependencies.py",
            f"{vendor_prefix}/CONTAINER_OPERATIONS.md"
            if not self.standalone
            else "CONTAINER_OPERATIONS.md",
        ):
            category = (
                "environment"
                if relative.endswith("CONTAINER_OPERATIONS.md")
                else "shared-post-create"
            )
            self._require(
                findings,
                checked,
                relative,
                category,
                executable=relative.endswith(".sh"),
            )
        rulebook = self.vendor_root / "CONTAINER_OPERATIONS.md"
        if (
            rulebook.is_file()
            and "Product Image And Mounted Tool Boundary"
            not in rulebook.read_text(encoding="utf-8")
        ):
            findings.append(
                BoundaryFinding(
                    "environment", str(rulebook), "missing-product-mounted-boundary"
                )
            )
        if not self.standalone:
            self._check_parent_devcontainer(findings, checked)
            self._check_parent_container(findings, checked)
        return EnvironmentBoundaryReport(
            status="fail" if findings else "pass",
            findings=tuple(findings),
            checked=tuple(checked),
        )


def architecture() -> str:
    """Normalize the host architecture used by release checksum maps."""
    value = platform.machine().lower()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(value, value)


def _safe_member_path(root: Path, member_name: str) -> Path:
    candidate = (root / member_name).resolve()
    if os.path.commonpath((str(root.resolve()), str(candidate))) != str(root.resolve()):
        raise DependencyError(f"archive member escapes extraction root: {member_name}")
    return candidate


def safe_extract_tar(archive: Path, destination: Path) -> None:
    """Extract regular tar members only, rejecting traversal and links."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:*") as stream:
        members = stream.getmembers()
        for member in members:
            _safe_member_path(destination, member.name)
            if (
                member.issym()
                or member.islnk()
                or not (member.isdir() or member.isfile())
            ):
                raise DependencyError(f"unsafe archive member: {member.name}")
        for member in members:
            target = _safe_member_path(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = stream.extractfile(member)
            if source is None:
                raise DependencyError(f"archive member has no data: {member.name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777)


def _receipt_path(receipts: Path, record_id: str) -> Path:
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]*", record_id) is None:
        raise DependencyError(f"invalid receipt record id: {record_id}")
    return receipts / f"{record_id}.json"


def _executable_binding_names(record: DependencyRecord) -> tuple[str, ...]:
    """Return manifest-provided executable names requiring receipt bindings."""
    if record.method is Method.NPM_GLOBAL:
        names = tuple(
            name
            for name in record.provides
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
        )
        if record.verification.executable and record.verification.executable not in names:
            names = (record.verification.executable, *names)
        return tuple(dict.fromkeys(names))
    if record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY}:
        return (record.verification.executable,) if record.verification.executable else ()
    if record.method is Method.RUST_TOOLCHAIN and "rust-analyzer" in record.components:
        return ("rust-analyzer",)
    return ()


def _configured_executable_path(record: DependencyRecord, executable: str) -> Path:
    """Return the manifest-owned lexical command path, never consulting PATH."""
    if executable not in _executable_binding_names(record):
        raise DependencyError(
            f"{record.id}: executable is not provided by the manifest record: {executable}"
        )
    if record.method is Method.NPM_GLOBAL:
        return Path(NPM_GLOBAL_PREFIX) / "bin" / executable
    elif record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY}:
        candidates = (
            Path("/usr/bin") / executable,
            Path("/usr/local/bin") / executable,
        )
        return next(
            (path for path in candidates if path.is_file() or path.is_symlink()),
            candidates[0],
        )
    elif record.method is Method.RUST_TOOLCHAIN:
        home = Path(os.environ.get("HOME", str(Path.home())))
        cargo_home = Path(os.environ.get("CARGO_HOME", str(home / ".cargo")))
        return cargo_home / "bin" / executable
    raise DependencyError(f"{record.id}: executable binding method is unsupported")


def _current_executable_path(record: DependencyRecord, executable: str) -> Path:
    """Resolve a non-apt executable through its typed install method."""
    if record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY}:
        raise DependencyError(
            f"{record.id}: apt executable resolution requires Installer ownership verification"
        )
    candidate = _configured_executable_path(record, executable)
    if record.method is Method.NPM_GLOBAL:
        allowed_root = Path(NPM_GLOBAL_PREFIX).resolve()
    elif record.method is Method.RUST_TOOLCHAIN:
        home = Path(os.environ.get("HOME", str(Path.home())))
        cargo_home = Path(os.environ.get("CARGO_HOME", str(home / ".cargo")))
        allowed_root = cargo_home.resolve()
    else:  # pragma: no cover - binding names are closed above.
        raise DependencyError(f"{record.id}: executable binding method is unsupported")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DependencyError(
            f"{record.id}: executable is missing: {candidate}"
        ) from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise DependencyError(f"{record.id}: executable is not executable: {candidate}")
    try:
        resolved.relative_to(allowed_root)
    except ValueError as exc:
        raise DependencyError(
            f"{record.id}: executable escapes its method-owned root: {resolved}"
        ) from exc
    return resolved


def _parse_dpkg_owned_paths(output: str, record_id: str) -> frozenset[str]:
    """Parse normalized absolute paths from one package ownership listing."""
    paths: set[str] = set()
    for line in output.splitlines():
        if not line or "\x00" in line or line.startswith("//") or not line.startswith("/"):
            raise DependencyError(
                f"{record_id}: dpkg ownership output contains an unsafe path"
            )
        normalized = os.path.normpath(line)
        if not normalized.startswith("/") or normalized.startswith("//"):
            raise DependencyError(
                f"{record_id}: dpkg ownership output contains a non-normalized absolute path"
            )
        paths.add(normalized)
    if not paths:
        raise DependencyError(f"{record_id}: dpkg ownership listing is empty")
    return frozenset(paths)


def _expected_executable_path(record: DependencyRecord, executable: str) -> Path:
    """Return the deterministic lexical path used by FakeRunner fixtures."""
    if executable not in _executable_binding_names(record):
        raise DependencyError(
            f"{record.id}: executable is not provided by the manifest record: {executable}"
        )
    if record.method is Method.NPM_GLOBAL:
        return Path(NPM_GLOBAL_PREFIX) / "bin" / executable
    if record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY}:
        return Path("/usr/bin") / executable
    if record.method is Method.RUST_TOOLCHAIN:
        home = Path(os.environ.get("HOME", str(Path.home())))
        cargo_home = Path(os.environ.get("CARGO_HOME", str(home / ".cargo")))
        return cargo_home / "bin" / executable
    raise DependencyError(f"{record.id}: executable binding method is unsupported")


class Installer:
    """Execute a validated plan with per-record receipt semantics."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        image_owned: bool = False,
        image_owned_root: Path | None = None,
    ) -> None:
        self.runner = runner or SubprocessRunner()
        self._parent_attestation: ParentRootAttestationReceipt | None = None
        self._image_owned = image_owned
        self._image_owned_root = image_owned_root.resolve() if image_owned_root else None
        self._install_workspace: Path | None = None
        self._active_record: DependencyRecord | None = None
        self._active_phase = "image-install"
        self._active_owner = "image-installer"

    def _operation_for(self, argv: Sequence[str], *, phase: str) -> str:
        """Derive only the closed operation id for an active owner edge."""
        command = tuple(str(item) for item in argv)
        executable = _command_basename(command[0]) if command else ""
        args = command[1:]
        if phase in {"image-verify", "post-create"}:
            if executable == "dpkg-query" and args[:1] == ("--show",):
                return "verify-apt-package"
            if executable == "dpkg-query" and args[:1] == ("--listfiles",):
                return "verify-apt-executable-owner"
            if executable == "gpg" and args[:2] == ("--show-keys", "--with-colons"):
                return "verify-apt-repository-key"
            if executable == "npm":
                return "verify-npm-package"
            if executable == "pipx":
                return "verify-pipx-package"
            if executable == "rustup":
                return (
                    "verify-rust-active"
                    if args[:2] == ("show", "active-toolchain")
                    else "verify-rust-components"
                    if args[:2] == ("component", "list")
                    else "verify-rust-tool-version"
                    if args[:1] == ("run",)
                    else "verify-rust-installed"
                )
            if executable == "elan":
                return (
                    "verify-lean-active"
                    if args[:1] == ("show",)
                    else "verify-lean-tool-version"
                    if args[:1] == ("run",)
                    else "verify-lean-installed"
                )
            if executable == "git":
                return "verify-cargo-source-identity"
            return "verify-declared-executable"
        method = self._active_record.method.value if self._active_record else ""
        if executable == "gpg" and args[:2] == ("--show-keys", "--with-colons"):
            return "verify-apt-repository-key"
        return {
            "apt-package": "install-apt-package",
            "apt-repository": "install-apt-repository",
            "npm-global": "install-npm-global",
            "pipx": "install-pipx",
            "release-asset": "install-release-asset",
            "rust-toolchain": "install-rust-toolchain",
            "lean-toolchain": "install-lean-toolchain",
            "cargo-source-build": "install-cargo-source-build",
            "browser-install": "install-browser",
        }.get(method, "image-install")

    def _command_provenance(
        self,
        argv: Sequence[str],
        *,
        operation: str | None = None,
        method: str | None = None,
        phase: str | None = None,
        owner: str | None = None,
        record_id: str | None = None,
        privileged: bool = False,
    ) -> CommandProvenance:
        active_phase = phase or self._active_phase
        active_record = self._active_record
        return CommandProvenance(
            phase=active_phase,
            owner=owner or self._active_owner,
            operation=operation or self._operation_for(argv, phase=active_phase),
            method=method or (active_record.method.value if active_record else None),
            record_id=record_id or (active_record.id if active_record else None),
            privileged_requested=privileged,
        )

    def _run_command(
        self,
        argv: Sequence[str],
        context: CommandProvenance,
        *,
        workspace: Path | None = None,
        capture_output: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Classify one command graph before the sole runner invocation."""
        classify_command(argv, context=context)
        return self.runner.run(
            argv,
            cwd=workspace,
            privileged=context.privileged_requested,
            capture_output=capture_output,
            env=env,
        )

    def _path_is_regular_executable(self, path: Path) -> bool:
        """Check one resolved target, allowing deterministic runner fixtures."""
        checker = getattr(self.runner, "is_regular_executable", None)
        if callable(checker):
            return bool(checker(path))
        return path.is_file() and os.access(path, os.X_OK)

    def _resolve_apt_executable_binding(
        self,
        record: DependencyRecord,
        executable: str,
        *,
        workspace: Path,
    ) -> tuple[Path, Path]:
        """Resolve apt lexical and real paths through declared package ownership."""
        self._active_record = record
        self._active_phase = "image-verify"
        self._active_owner = "typed-verifier"
        lexical = _configured_executable_path(record, executable)
        owned: set[str] = set()
        owners = record.executable_owner_packages
        for owner_package in owners:
            try:
                result = self._capture(
                    ["/usr/bin/dpkg-query", "--listfiles", owner_package],
                    workspace=workspace,
                    operation="verify-apt-executable-owner",
                    tool_paths=False,
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                raise DependencyError(
                    f"{record.id}: dpkg ownership query failed for {owner_package}"
                ) from exc
            if result.returncode != 0:
                raise DependencyError(
                    f"{record.id}: dpkg ownership query failed for {owner_package}"
                )
            if not isinstance(result.stdout, str):
                raise DependencyError(
                    f"{record.id}: dpkg ownership query returned malformed output"
                )
            owned.update(_parse_dpkg_owned_paths(result.stdout, record.id))
        if not owned:
            raise DependencyError(
                f"{record.id}: executable ownership union is empty for {', '.join(owners)}"
            )
        lexical_text = str(lexical)
        if lexical_text not in owned:
            raise DependencyError(
                f"{record.id}: lexical executable is not owned by declared packages: "
                f"{', '.join(owners)}: "
                f"{lexical_text}"
            )
        try:
            resolved = lexical.resolve(strict=True)
        except OSError as exc:
            resolver = getattr(self.runner, "resolve_executable", None)
            if not callable(resolver):
                raise DependencyError(
                    f"{record.id}: lexical executable target is missing: {lexical}"
                ) from exc
            try:
                resolved = Path(resolver(lexical))
            except (OSError, TypeError, ValueError) as resolver_exc:
                raise DependencyError(
                    f"{record.id}: lexical executable target cannot be resolved: {lexical}"
                ) from resolver_exc
        if (
            not resolved.is_absolute()
            or str(resolved) != os.path.normpath(str(resolved))
        ):
            raise DependencyError(
                f"{record.id}: resolved executable path is not normalized absolute: {resolved}"
            )
        resolved_text = str(resolved)
        if resolved_text not in owned:
            raise DependencyError(
                f"{record.id}: resolved executable is not owned by declared packages: "
                f"{', '.join(owners)}: "
                f"{resolved_text}"
            )
        if not self._path_is_regular_executable(resolved):
            raise DependencyError(
                f"{record.id}: resolved executable is not a regular executable: {resolved}"
            )
        return lexical, resolved

    def _resolve_executable_binding(
        self,
        record: DependencyRecord,
        executable: str,
        *,
        workspace: Path,
    ) -> tuple[Path, Path]:
        """Return lexical and resolved paths for one manifest-owned executable."""
        if record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY}:
            return self._resolve_apt_executable_binding(
                record, executable, workspace=workspace
            )
        path = _current_executable_path(record, executable)
        return path, path

    def _cargo_binary_path(
        self,
        record: DependencyRecord,
        *,
        source: Path | None = None,
        workspace: Path | None = None,
    ) -> Path:
        """Resolve a Cargo verification binary in the configured build target."""
        spec = record.verification
        if spec.path is None:
            raise DependencyError(f"{record.id}: cargo verification path is missing")
        relative = Path(spec.path)
        if (
            relative.is_absolute()
            or len(relative.parts) < 2
            or relative.parts[0] != "target"
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise DependencyError(f"{record.id}: cargo binary path is unsafe")
        if source is None:
            if workspace is None:
                raise DependencyError(f"{record.id}: Cargo source workspace is missing")
            source = self._cargo_source(record, workspace)
        target_root = (
            os.environ.get("AGENT_CANON_CARGO_TARGET_DIR")
            if self._image_owned
            else None
        )
        if target_root:
            return (Path(target_root) / Path(*relative.parts[1:])).resolve()
        return (source / relative).resolve()

    def _publish_final_binary(
        self,
        record: DependencyRecord,
        *,
        workspace: Path,
        final_binary_dir: Path,
    ) -> Path:
        """Install a verified Cargo binary into the immutable image PATH."""
        if not self._image_owned or record.method is not Method.CARGO_SOURCE_BUILD:
            raise DependencyError(
                f"{record.id}: final binary publication is image Cargo-only"
            )
        final_dir = final_binary_dir.resolve()
        if final_dir != Path("/usr/local/bin"):
            raise DependencyError(
                f"{record.id}: final binary directory is not the image PATH"
            )
        source = self._cargo_source(record, workspace)
        binary = self._cargo_binary_path(record, source=source)
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise DependencyError(f"{record.id}: Cargo build binary is missing: {binary}")
        name = Path(record.verification.path or "").name
        if not name or name in {".", ".."}:
            raise DependencyError(f"{record.id}: final binary name is unsafe")
        final_binary = final_dir / name
        self._run(
            ["install", "-m", "0555", str(binary), str(final_binary)],
            workspace=workspace,
            privileged=True,
            operation="install-cargo-source-build",
            method=record.method.value,
            phase="image-install",
            owner="image-installer",
            record_id=record.id,
        )
        return final_binary

    @staticmethod
    def _verify_final_binary_receipt(
        payload: Mapping[str, Any], record: DependencyRecord
    ) -> None:
        """Verify the image-owned final binary bound by a Cargo receipt."""
        spec_path = record.verification.path
        if spec_path is None:
            raise DependencyError(f"{record.id}: Cargo verification path is missing")
        expected = Path("/usr/local/bin") / Path(spec_path).name
        final_value = payload.get("binary_path")
        digest = payload.get("binary_sha256")
        if final_value != str(expected) or not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise DependencyError(f"{record.id}: final binary receipt binding is malformed")
        final_binary = Path(final_value)
        if final_binary.is_symlink() or not final_binary.is_file() or not os.access(final_binary, os.X_OK):
            raise DependencyError(f"{record.id}: final image binary is missing: {final_binary}")
        observed = hashlib.sha256(final_binary.read_bytes()).hexdigest()
        if observed != digest:
            raise DependencyError(
                f"{record.id}: final image binary digest mismatch {observed}!={digest}"
            )

    def dry_run(self, plan: DependencyPlan) -> dict[str, Any]:
        """Return planned actions without network, package, or filesystem installs."""
        by_id = plan.by_id()
        return {
            "schema": "agent-canon.devcontainer-dependency-dry-run",
            "plan_fingerprint": plan.fingerprint,
            "order": list(plan.order),
            "actions": [
                {
                    "id": record.id,
                    "method": record.method.value,
                    "verification": record.verification.payload(),
                    "environment": (
                        {"PLAYWRIGHT_BROWSERS_PATH": record.browser_cache_path}
                        if record.method is Method.BROWSER_INSTALL
                        else {}
                    ),
                }
                for record in (by_id[record_id] for record_id in plan.order)
            ],
        }

    def install(
        self,
        plan: DependencyPlan,
        *,
        workspace: Path,
        receipts: Path,
        records: Sequence[str] | None = None,
        final_binary_dir: Path | None = None,
    ) -> tuple[str, ...]:
        """Install records in order, resuming only after live receipt verification."""
        self._install_workspace = workspace.resolve()
        if self._image_owned:
            if self._image_owned_root is None:
                raise DependencyError("image-owned install requires an image root")
            image_root = self._image_owned_root
            try:
                receipts = receipts.resolve()
                receipts.relative_to(image_root)
            except (OSError, ValueError) as exc:
                raise DependencyError(
                    "image-owned receipts must remain under the image root"
                ) from exc
            receipts.mkdir(parents=True, exist_ok=True)
            self._parent_attestation = None
        else:
            self._parent_attestation = _parent_attestation(workspace, "dependency-install")
            try:
                receipts = resolve_parent_owned_path(
                    self._parent_attestation, receipts, "dependency-receipts", create=False
                ).physical_path
            except ParentRootSideEffectError as exc:
                raise DependencyError(
                    f"parent-root-path:{exc.reject.value}:{exc.detail}"
                ) from exc
            receipts = ensure_parent_owned_directory(
                self._parent_attestation, receipts, "dependency-receipts"
            ).physical_path
        completed: list[str] = []
        by_id = plan.by_id()
        order = tuple(records) if records is not None else plan.order
        unknown = sorted(set(order) - set(by_id))
        if unknown:
            raise DependencyError(
                "selected dependency records are not in the plan: "
                + ", ".join(unknown)
            )
        if self._image_owned and final_binary_dir is None and any(
            by_id[record_id].method is Method.CARGO_SOURCE_BUILD for record_id in order
        ):
            raise DependencyError(
                "image-owned Cargo install requires a final binary directory"
            )
        unavailable: set[str] = set()
        for record_id in order:
            record = by_id[record_id]
            receipt = _receipt_path(receipts, record.id)
            active_source = (
                record.method is Method.CARGO_SOURCE_BUILD
                and record.source_identity == ACTIVE_SOURCE_IDENTITY
            )
            blockers = tuple(
                provider
                for provider in plan.providers_for(record.id)
                if provider in unavailable
            )
            if blockers:
                error = DependencyError(
                    f"dependency unavailable: {record.id} depends on "
                    + ", ".join(blockers)
                )
                receipt.unlink(missing_ok=True)
                unavailable.add(record.id)
                if record.failure_policy == "warn":
                    print(
                        f"DEPENDENCY_RECORD_WARN={record.id}:{error}", file=sys.stderr
                    )
                    continue
                raise error
            # Active-source builds are intentionally non-cacheable at this
            # layer.  Cargo owns incremental change detection for the mounted
            # source tree, so a dependency receipt must never suppress the
            # build or carry a source identity derived from Git.
            receipt_matches = not active_source and self._receipt_matches(
                receipt, plan, record
            )
            repair = receipt.exists()
            if receipt_matches:
                try:
                    self.verify(
                        record,
                        workspace=workspace,
                        expected_source_identity=self._receipt_source_identity(receipt),
                        strict_executables=True,
                    )
                    if _executable_binding_names(record):
                        if self._executable_bindings(
                            record, workspace=workspace
                        ) != self._receipt_bindings(receipt):
                            raise DependencyError(
                                f"{record.id}: executable receipt path or output drift"
                            )
                except Exception:
                    receipt.unlink(missing_ok=True)
                    repair = True
                else:
                    completed.append(record.id)
                    continue
            else:
                receipt.unlink(missing_ok=True)
            try:
                self.install_record(record, workspace=workspace, repair=repair)
                source_identity = self.verify(
                    record, workspace=workspace, strict_executables=True
                )
                if active_source:
                    # There is no reusable receipt for an active mounted
                    # source.  Keep the next startup on the Cargo build path.
                    receipt.unlink(missing_ok=True)
                else:
                    executable_bindings = self._executable_bindings(
                        record, workspace=workspace
                    )
                    final_binary_path = None
                    if (
                        final_binary_dir is not None
                        and record.method is Method.CARGO_SOURCE_BUILD
                    ):
                        final_binary_path = self._publish_final_binary(
                            record,
                            workspace=workspace,
                            final_binary_dir=final_binary_dir,
                        )
                    self._write_receipt(
                        receipt,
                        plan,
                        record,
                        source_identity,
                        executable_bindings,
                        final_binary_path=final_binary_path,
                    )
            except Exception as exc:
                receipt.unlink(missing_ok=True)
                unavailable.add(record.id)
                if record.failure_policy == "warn":
                    print(f"DEPENDENCY_RECORD_WARN={record.id}:{exc}", file=sys.stderr)
                    continue
                raise DependencyError(
                    f"dependency record failed: {record.id}: {exc}"
                ) from exc
            completed.append(record.id)
        return tuple(completed)

    @staticmethod
    def _receipt_matches(
        path: Path, plan: DependencyPlan, record: DependencyRecord
    ) -> bool:
        if (
            record.method is Method.CARGO_SOURCE_BUILD
            and record.source_identity == ACTIVE_SOURCE_IDENTITY
        ):
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return False
        bindings = payload.get("executable_bindings")
        if not isinstance(bindings, dict):
            return False
        expected_bindings = set(_executable_binding_names(record))
        if set(bindings) != expected_bindings or any(
            not isinstance(value, dict)
            or value.get("provided") != name
            or not isinstance(value.get("lexical_path"), str)
            or not Path(value["lexical_path"]).is_absolute()
            or value["lexical_path"] != os.path.normpath(value["lexical_path"])
            or not isinstance(value.get("absolute_path"), str)
            or not Path(value["absolute_path"]).is_absolute()
            or value["absolute_path"] != os.path.normpath(value["absolute_path"])
            or not isinstance(value.get("verification_output"), str)
            or not value.get("verification_output")
            for name, value in bindings.items()
        ):
            return False
        return (
            payload.get("schema") == "agent-canon.devcontainer-dependency-receipt"
            and payload.get("record_id") == record.id
            and payload.get("status") == "pass"
            and payload.get("owner") == "image-installer"
            and payload.get("phase") == "image-install"
            and payload.get("manifest_version") == record.version
            and payload.get("plan_fingerprint") == plan.fingerprint
            and payload.get("record_fingerprint") == record.fingerprint()
            and payload.get("verification") == record.verification.payload()
            and set(bindings) == expected_bindings
            and payload.get("repository_packages")
            == _repository_packages_payload(record)
            and payload.get("repository_package")
            == _repository_package_payload(record)
            and payload.get("source_tree_sha256") == record.source_tree_sha256
            and payload.get("cargo_lock_sha256") == record.cargo_lock_sha256
            and (
                record.method is not Method.CARGO_SOURCE_BUILD
                or isinstance(payload.get("source_identity"), str)
            )
        )

    def _executable_bindings(
        self, record: DependencyRecord, *, workspace: Path
    ) -> dict[str, dict[str, str]]:
        """Capture primary probe output and structural secondary bindings."""
        self._active_record = record
        self._active_phase = "image-verify"
        self._active_owner = "typed-verifier"
        bindings: dict[str, dict[str, str]] = {}
        for executable in _executable_binding_names(record):
            lexical_path, path = self._resolve_executable_binding(
                record, executable, workspace=workspace
            )
            if executable == record.verification.executable:
                result = self._capture(
                    [str(path), *record.verification.args], workspace=workspace
                )
                output = self._verification_output(result, record.id)
                if record.verification.output_contains is not None:
                    self._require_output(
                        result, record.verification.output_contains, record.id
                    )
            else:
                output = (
                    f"{STRUCTURAL_BINDING_OUTPUT_PREFIX}:"
                    f"{record.method.value}:{executable}"
                )
            bindings[executable] = {
                "provided": executable,
                "lexical_path": str(lexical_path),
                "absolute_path": str(path),
                "verification_output": output,
            }
        return bindings

    @staticmethod
    def _receipt_bindings(path: Path) -> dict[str, dict[str, str]]:
        """Read validated executable bindings from one receipt."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DependencyError("executable receipt is unreadable") from exc
        bindings = payload.get("executable_bindings")
        if not isinstance(bindings, dict):
            raise DependencyError("executable receipt bindings are malformed")
        return bindings

    @staticmethod
    def _verification_output(
        result: subprocess.CompletedProcess[str], record_id: str
    ) -> str:
        """Normalize live executable output for atomic receipt identity."""
        output = f"{result.stdout}\n{result.stderr}".strip()
        if not output:
            raise DependencyError(f"{record_id}: executable verification output is empty")
        return output

    @staticmethod
    def _receipt_source_identity(path: Path) -> str | None:
        """Read the selected source identity recorded with a Cargo receipt."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
            return None
        value = payload.get("source_identity")
        return value if isinstance(value, str) else None

    def _write_receipt(
        self,
        path: Path,
        plan: DependencyPlan,
        record: DependencyRecord,
        source_identity: str | None = None,
        executable_bindings: Mapping[str, Mapping[str, str]] | None = None,
        *,
        final_binary_path: Path | None = None,
    ) -> None:
        if (
            source_identity is None
            and record.method is Method.CARGO_SOURCE_BUILD
            and record.source_identity == CANONICAL_SNAPSHOT_IDENTITY
        ):
            source_identity = record.source_identity
        payload = {
            "schema": "agent-canon.devcontainer-dependency-receipt",
            "status": "pass",
            "owner": "image-installer",
            "phase": "image-install",
            "record_id": record.id,
            "manifest_version": record.version,
            "record_fingerprint": record.fingerprint(),
            "plan_fingerprint": plan.fingerprint,
            "verification": record.verification.payload(),
            "source_identity": source_identity,
            "executable_bindings": {
                key: dict(value)
                for key, value in (executable_bindings or {}).items()
            },
        }
        repository_packages = _repository_packages_payload(record)
        if repository_packages is not None:
            payload["repository_packages"] = repository_packages
        repository_package = _repository_package_payload(record)
        if repository_package is not None:
            payload["repository_package"] = repository_package
        if record.method is Method.CARGO_SOURCE_BUILD and record.source_identity == CANONICAL_SNAPSHOT_IDENTITY:
            source = self._cargo_source(
                record,
                self._install_workspace
                or (
                    self._parent_attestation.parent_root
                    if self._parent_attestation
                    else Path.cwd()
                ),
            )
            source_digest, lock_digest = self._cargo_snapshot(source)
            assert record.verification.path is not None
            binary = self._cargo_binary_path(record, source=source)
            binary_path = final_binary_path or binary
            payload.update(
                {
                    "source_tree_sha256": source_digest,
                    "cargo_lock_sha256": lock_digest,
                    "binary_path": str(binary_path),
                    "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                    "rustup_init_version": RUSTUP_INIT_VERSION,
                    "rustup_init_sha256": RUSTUP_INIT_SHA256,
                }
            )
            if final_binary_path is not None:
                payload["build_binary_path"] = str(binary)
        content = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        if self._image_owned:
            if self._image_owned_root is None:
                raise DependencyError("image-owned receipt publication lacks an image root")
            try:
                path = path.resolve()
                path.relative_to(self._image_owned_root)
            except (OSError, ValueError) as exc:
                raise DependencyError(
                    "image-owned receipt escaped the image root"
                ) from exc
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", dir=path.parent
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                temporary.write_bytes(content)
                temporary.chmod(0o600)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return
        if self._parent_attestation is None:
            raise DependencyError(
                "parent-root-attestation is required before receipt publication"
            )
        try:
            ensure_parent_owned_directory(
                self._parent_attestation, path.parent, "dependency-receipts"
            )
            receipt = resolve_parent_owned_path(
                self._parent_attestation, path, "dependency-receipt", create=False
            )
            ParentRootSideEffectBoundary().atomic_publish(
                receipt,
                content,
            )
        except ParentRootSideEffectError as exc:
            raise DependencyError(
                f"parent-root-receipt:{exc.reject.value}:{exc.detail}"
            ) from exc

    def _run(
        self,
        argv: Sequence[str],
        *,
        workspace: Path,
        privileged: bool = False,
        env: Mapping[str, str] | None = None,
        operation: str | None = None,
        method: str | None = None,
        phase: str | None = None,
        owner: str | None = None,
        record_id: str | None = None,
    ) -> None:
        context = self._command_provenance(
            argv,
            operation=operation,
            method=method,
            phase=phase,
            owner=owner,
            record_id=record_id,
            privileged=privileged,
        )
        self._run_command(
            argv,
            context,
            workspace=workspace,
            env=env,
        )

    def _with_tool_paths(self, command_env: Mapping[str, str] | None) -> dict[str, str]:
        """Publish deterministic Python, Rust, and Lean tool paths."""
        if self._parent_attestation is not None:
            merged = child_environment(self._parent_attestation, os.environ)
        else:
            merged = dict(os.environ)
        merged.pop("CARGO_TARGET_DIR", None)
        merged.update(command_env or {})
        home = Path(merged.get("HOME", str(Path.home())))
        parent_root = (
            self._parent_attestation.parent_root
            if self._parent_attestation is not None
            else None
        )
        home_is_parent_owned = parent_root is not None and (
            home == parent_root or parent_root in home.parents
        )
        cargo_home = merged.get(
            "CARGO_HOME",
            str(parent_root / ".agent-canon" / "cargo-home")
            if parent_root is not None
            else str(home / ".cargo"),
        )
        rustup_home = merged.get(
            "RUSTUP_HOME",
            str(home / ".rustup") if home_is_parent_owned
            else str(parent_root / ".agent-canon" / "rustup-home")
            if parent_root is not None
            else str(home / ".rustup"),
        )
        elan_home = merged.get(
            "ELAN_HOME",
            str(home / ".elan") if home_is_parent_owned
            else str(parent_root / ".agent-canon" / "elan-home")
            if parent_root is not None
            else str(home / ".elan"),
        )
        path_entries = list(filter(None, merged.get("PATH", "").split(os.pathsep)))
        tool_paths = (
            str(home / ".cargo" / "bin") if home_is_parent_owned else f"{cargo_home}/bin",
            f"{elan_home}/bin",
            str(home / ".local" / "bin") if home_is_parent_owned
            else str(parent_root / ".agent-canon" / "local-bin")
            if parent_root is not None
            else str(home / ".local" / "bin"),
        )
        merged["CARGO_HOME"] = cargo_home
        merged["RUSTUP_HOME"] = rustup_home
        merged["ELAN_HOME"] = elan_home
        merged.pop("RUSTUP_TOOLCHAIN", None)
        merged.pop("ELAN_TOOLCHAIN", None)
        missing_tool_paths = [item for item in tool_paths if item not in path_entries]
        merged["PATH"] = os.pathsep.join([*missing_tool_paths, *path_entries])
        return merged

    def install_record(
        self, record: DependencyRecord, *, workspace: Path, repair: bool = False
    ) -> None:
        self._active_record = record
        self._active_phase = "image-install"
        self._active_owner = "image-installer"
        method = record.method
        if method is Method.APT_PACKAGE:
            command = [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "--no-remove",
                f"{record.package}={record.version}",
            ]
            if repair:
                command.insert(2, "--reinstall")
            self._run(
                command,
                workspace=workspace,
                privileged=True,
            )
        elif method is Method.APT_REPOSITORY:
            self._install_apt_repository(record, workspace, repair=repair)
            if record.repository_package_url is not None:
                return
            command = [
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "--no-remove",
                f"{record.package}={record.version}",
            ]
            if repair:
                command.insert(2, "--reinstall")
            self._run(
                command,
                workspace=workspace,
                privileged=True,
            )
        elif method is Method.NPM_GLOBAL:
            toolchain = resolve_npm_toolchain(workspace)
            npm_args = [
                "install",
                "--global",
                "--prefix",
                NPM_GLOBAL_PREFIX,
                f"{record.package}@{record.version}",
            ]
            if repair:
                npm_args.insert(1, "--force")
            command = [
                NPM_ENV_EXECUTABLE,
                f"PATH={toolchain.path}",
                str(toolchain.npm),
                *npm_args,
            ]
            self._run(
                command,
                workspace=workspace,
                privileged=True,
            )
        elif method is Method.PIPX:
            command = [
                "pipx",
                "install",
                "--index-url",
                record.source,
                f"{record.package}=={record.version}",
            ]
            if repair:
                command.insert(2, "--force")
            self._run(
                command,
                workspace=workspace,
                env=self._with_tool_paths(None),
            )
        elif method is Method.RELEASE_ASSET:
            self._install_release_asset(record, workspace=workspace)
        elif method is Method.RUST_TOOLCHAIN:
            tool_env = self._with_tool_paths(None)
            self._run(
                [
                    "/usr/local/bin/rustup-init",
                    "-y",
                    "--default-toolchain",
                    "none",
                    "--profile",
                    "minimal",
                    "--no-modify-path",
                ],
                workspace=workspace,
                env=tool_env,
            )
            if repair:
                installed = self._capture(
                    ["rustup", "toolchain", "list"],
                    workspace=workspace,
                    env=tool_env,
                ).stdout
                if any(
                    self._rust_toolchain_matches(line, record.version)
                    for line in installed.splitlines()
                    if line.strip()
                ):
                    self._run(
                        ["rustup", "toolchain", "uninstall", record.version],
                        workspace=workspace,
                        env=tool_env,
                    )
            self._run(
                [
                    "rustup",
                    "toolchain",
                    "install",
                    record.version,
                    "--profile",
                    "minimal",
                ],
                workspace=workspace,
                env=tool_env,
            )
            if record.components:
                self._run(
                    [
                        "rustup",
                        "component",
                        "add",
                        *record.components,
                        "--toolchain",
                        record.version,
                    ],
                    workspace=workspace,
                    env=tool_env,
                )
            self._run(
                ["rustup", "default", record.version],
                workspace=workspace,
                env=tool_env,
            )
        elif method is Method.LEAN_TOOLCHAIN:
            tool_env = self._with_tool_paths(None)
            self._run(
                [
                    "/usr/local/bin/elan-init",
                    "-y",
                    "--default-toolchain",
                    record.version,
                    "--no-modify-path",
                ],
                workspace=workspace,
                env=tool_env,
            )
            installed = self._capture(
                ["elan", "toolchain", "list"],
                workspace=workspace,
                env=tool_env,
            ).stdout
            has_exact_toolchain = any(
                line.split()[0] == record.version
                for line in installed.splitlines()
                if line.strip()
            )
            if repair and has_exact_toolchain:
                # A receipt-triggered repair is the explicit contract that
                # permits replacing an already-installed exact toolchain.
                # Fresh retries with no receipt preserve a usable live install.
                self._run(
                    ["elan", "toolchain", "uninstall", record.version],
                    workspace=workspace,
                    env=tool_env,
                )
                has_exact_toolchain = False
            if not has_exact_toolchain:
                self._run(
                    ["elan", "toolchain", "install", record.version],
                    workspace=workspace,
                    env=tool_env,
                )
            self._run(
                ["elan", "default", record.version],
                workspace=workspace,
                env=tool_env,
            )
        elif method is Method.CARGO_SOURCE_BUILD:
            source = self._cargo_source(record, workspace)
            if record.source_identity == CANONICAL_SNAPSHOT_IDENTITY:
                self._verify_canonical_snapshot(record, workspace)
            source_identity_before = None
            if record.commit is not None:
                source_identity_before = self._cargo_source_identity(
                    record, workspace, source=source
                )
            self._run(
                [
                    "cargo",
                    "build",
                    "--release",
                    "--locked",
                    "--manifest-path",
                    str(source / "Cargo.toml"),
                ],
                workspace=workspace,
                env=self._with_tool_paths(
                    {
                        "CARGO_TARGET_DIR": (
                            os.environ.get("AGENT_CANON_CARGO_TARGET_DIR")
                            if self._image_owned
                            else None
                        )
                        or str(source / "target")
                    }
                ),
            )
            if source_identity_before is not None:
                source_identity_after = self._cargo_source_identity(
                    record, workspace, source=source
                )
                if source_identity_before != source_identity_after:
                    raise DependencyError(
                        f"{record.id}: source identity changed during build "
                        f"{source_identity_before}!={source_identity_after}"
                    )
            if record.source_identity == CANONICAL_SNAPSHOT_IDENTITY:
                self._verify_canonical_snapshot(record, workspace)
        elif method is Method.BROWSER_INSTALL:
            assert record.browser is not None
            assert record.browser_cache_path is not None
            cache = Path(record.browser_cache_path)
            if cache.exists() and (cache.is_symlink() or not cache.is_dir()):
                raise DependencyError(
                    f"{record.id}: browser cache path is not a directory"
                )
            self._run(
                ["install", "-d", "-m", "0775", str(cache)],
                workspace=workspace,
                privileged=True,
            )
            self._run(
                [
                    "env",
                    f"PLAYWRIGHT_BROWSERS_PATH={record.browser_cache_path}",
                    "playwright",
                    "install",
                    "--with-deps",
                    record.browser,
                ],
                workspace=workspace,
                privileged=True,
            )
        else:  # pragma: no cover - Method is a closed enum.
            raise DependencyError(f"unsupported installation method: {method}")

    def verify(
        self,
        record: DependencyRecord,
        *,
        workspace: Path,
        expected_source_identity: str | None = None,
        strict_executables: bool = False,
        allow_network: bool = True,
    ) -> str | None:
        """Dispatch the record's typed owner-specific live verifier."""
        self._active_record = record
        self._active_phase = "image-verify"
        self._active_owner = "typed-verifier"
        source_identity = None
        if record.method is Method.CARGO_SOURCE_BUILD and record.commit is not None:
            source_identity = self._cargo_source_identity(record, workspace)
            if (
                expected_source_identity is not None
                and source_identity != expected_source_identity
            ):
                raise DependencyError(
                    f"{record.id}: binary source identity mismatch "
                    f"{source_identity}!={expected_source_identity}"
                )
        verifiers = {
            VerificationKind.APT_PACKAGE: lambda item, *, workspace: self._verify_apt_package(
                item, workspace=workspace, strict_executable=strict_executables
            ),
            VerificationKind.APT_REPOSITORY: lambda item, *, workspace: self._verify_apt_repository(
                item,
                workspace=workspace,
                strict_executable=strict_executables,
                allow_network=allow_network,
            ),
            VerificationKind.NPM_PACKAGE: lambda item, *, workspace: self._verify_npm_package(
                item, workspace=workspace, strict_executable=strict_executables
            ),
            VerificationKind.PIPX_PACKAGE: self._verify_pipx_package,
            VerificationKind.ABSOLUTE_EXECUTABLE: self._verify_absolute_executable,
            VerificationKind.RUST_TOOLCHAIN: self._verify_rust_toolchain,
            VerificationKind.LEAN_TOOLCHAIN: self._verify_lean_toolchain,
            VerificationKind.CARGO_BINARY: self._verify_cargo_binary,
            VerificationKind.BROWSER_EXECUTABLE: self._verify_browser_executable,
        }
        verifier = verifiers.get(record.verification.kind)
        if verifier is None:  # pragma: no cover - VerificationKind is closed.
            raise DependencyError(
                f"unsupported verification kind: {record.verification.kind}"
            )
        verifier(record, workspace=workspace)
        return source_identity

    def _capture(
        self,
        argv: Sequence[str],
        *,
        workspace: Path,
        env: Mapping[str, str] | None = None,
        operation: str | None = None,
        method: str | None = None,
        phase: str | None = None,
        owner: str | None = None,
        record_id: str | None = None,
        tool_paths: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        context = self._command_provenance(
            argv,
            operation=operation,
            method=method,
            phase=phase,
            owner=owner,
            record_id=record_id,
        )
        command_env = self._with_tool_paths(env) if tool_paths else env
        return self._run_command(
            argv,
            context,
            workspace=workspace,
            capture_output=True,
            env=command_env,
        )

    @staticmethod
    def _require_output(
        result: subprocess.CompletedProcess[str], token: str, record_id: str
    ) -> None:
        output = f"{result.stdout}\n{result.stderr}"
        if token not in output:
            raise DependencyError(
                f"{record_id}: verification output lacks required token {token!r}"
            )

    def _verify_apt_package(
        self,
        record: DependencyRecord,
        *,
        workspace: Path,
        strict_executable: bool = False,
    ) -> None:
        """Verify the dpkg database and any record-owned executable contract.

        The installed dpkg database is the container trust boundary. Official
        Ubuntu images may exclude documentation and manpage payloads, so raw
        ``dpkg --verify`` output is not a blocking receipt oracle.
        """
        result = self._capture(
            [
                "/usr/bin/dpkg-query",
                "--show",
                "--showformat=${Status}\\t${Version}\\t${Package}\\\\n",
                record.package,
            ],
            workspace=workspace,
        )
        fields = result.stdout.strip().split("\t")
        if fields != ["install ok installed", record.version, record.package]:
            raise DependencyError(
                f"{record.id}: dpkg package/version/owned state mismatch"
            )
        executable = record.verification.executable
        if executable is not None:
            assert record.verification.output_contains is not None
            command = [executable, *record.verification.args]
            if strict_executable:
                _, resolved = self._resolve_executable_binding(
                    record, executable, workspace=workspace
                )
                command[0] = str(resolved)
            result = self._capture(
                command,
                workspace=workspace,
            )
            self._require_output(
                result,
                record.verification.output_contains,
                record.id,
            )

    def _verify_apt_repository(
        self,
        record: DependencyRecord,
        *,
        workspace: Path,
        strict_executable: bool = False,
        allow_network: bool = True,
    ) -> None:
        self._verify_apt_package(
            record, workspace=workspace, strict_executable=strict_executable
        )
        assert record.key_fingerprint is not None
        keyring = Path("/etc/apt/keyrings") / f"{record.id}.gpg"
        source_list = Path("/etc/apt/sources.list.d") / f"{record.id}.list"
        if (
            keyring.is_symlink()
            or not keyring.is_file()
            or source_list.is_symlink()
            or not source_list.is_file()
        ):
            raise DependencyError(f"{record.id}: apt repository artifact is missing")
        fingerprint = self._capture(
            ["gpg", "--show-keys", "--with-colons", str(keyring)],
            workspace=workspace,
        ).stdout
        observed = {
            line.split(":")[9].upper()
            for line in fingerprint.splitlines()
            if line.startswith("fpr:") and len(line.split(":")) > 9
        }
        if record.key_fingerprint not in observed:
            raise DependencyError(f"{record.id}: apt repository key is stale")
        expected_source = self._apt_repository_line(record, keyring)
        try:
            observed_source = source_list.read_text(encoding="utf-8")
        except OSError as exc:
            raise DependencyError(
                f"{record.id}: apt repository source is unreadable"
            ) from exc
        if observed_source != expected_source:
            raise DependencyError(f"{record.id}: apt repository source is stale")
        if allow_network:
            if self._active_phase != "image-install":
                raise DependencyError(
                    "command-boundary-network-fetch: image verification cannot fetch"
                )
            self._verify_repository_packages_digest(record, workspace=workspace)

    @staticmethod
    def _apt_repository_line(record: DependencyRecord, keyring: Path) -> str:
        """Render the exact signed apt source line owned by one record."""
        if record.repository_suite is None:
            raise DependencyError(f"{record.id}: repository suite is not declared")
        components = " ".join(record.repository_components)
        return (
            f"deb [signed-by={keyring}] {record.source} "
            f"{record.repository_suite} {components}\n"
        )

    @staticmethod
    def _verify_repository_packages_digest(
        record: DependencyRecord, *, workspace: Path | None = None
    ) -> None:
        """Verify a pinned Packages index before accepting an apt repository."""
        expected = record.repository_packages_sha256
        if expected is None:
            return
        url = _repository_packages_url(record)
        with tempfile.NamedTemporaryFile(
            prefix=f"agent-canon-{record.id}-packages-",
            dir=_parent_temp_root(workspace or Path.cwd(), "apt-packages"),
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        try:
            try:
                _download(
                    url,
                    temporary,
                    operation=NetworkOperation(
                        phase="image-install",
                        owner="image-installer",
                        operation="download-packages-index",
                        method=record.method.value,
                        record_id=record.id,
                        url=url,
                        allow_network=True,
                    ),
                )
            except Exception as exc:
                raise DependencyError(
                    f"{record.id}: Packages index download failed: {url}: {exc}"
                ) from exc
            observed = hashlib.sha256(temporary.read_bytes()).hexdigest()
        except OSError as exc:
            raise DependencyError(
                f"{record.id}: Packages index read failed: {url}: {exc}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)
        if observed != expected:
            raise DependencyError(
                f"{record.id}: Packages index SHA256 mismatch "
                f"{observed}!={expected} ({url})"
            )

    def _verify_npm_package(
        self,
        record: DependencyRecord,
        *,
        workspace: Path,
        strict_executable: bool = False,
    ) -> None:
        toolchain = resolve_npm_toolchain(workspace)
        npm_env = {"PATH": toolchain.path}
        result = self._capture(
            [
                str(toolchain.npm),
                "ls",
                "--global",
                "--prefix",
                NPM_GLOBAL_PREFIX,
                "--json",
                "--depth=0",
                record.package,
            ],
            workspace=workspace,
            env=npm_env,
            operation="verify-npm-package",
            tool_paths=False,
        )
        try:
            payload = json.loads(result.stdout)
            observed = payload["dependencies"][record.package]["version"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise DependencyError(
                f"{record.id}: npm global JSON is missing package"
            ) from exc
        if observed != record.version:
            raise DependencyError(
                f"{record.id}: npm version mismatch {observed!r}!={record.version!r}"
            )
        spec = record.verification
        assert spec.executable is not None and spec.output_contains is not None
        executable = spec.executable
        command = [executable, *spec.args]
        if strict_executable:
            _, resolved = self._resolve_executable_binding(
                record, executable, workspace=workspace
            )
            command[0] = str(resolved)
        executable = self._capture(
            command,
            workspace=workspace,
            env=npm_env,
            operation="verify-declared-executable",
            tool_paths=False,
        )
        self._require_output(executable, spec.output_contains, record.id)

    def _verify_pipx_package(
        self, record: DependencyRecord, *, workspace: Path
    ) -> None:
        result = self._capture(
            ["pipx", "runpip", record.package, "show", record.package],
            workspace=workspace,
        )
        observed_name: str | None = None
        observed_version: str | None = None
        for line in result.stdout.splitlines():
            key, separator, value = line.partition(":")
            if separator and key == "Name":
                observed_name = canonicalize_name(value.strip())
            elif separator and key == "Version":
                observed_version = value.strip()
        if (
            observed_name != canonicalize_name(record.package)
            or observed_version != record.version
        ):
            raise DependencyError(f"{record.id}: pipx package/version mismatch")
        spec = record.verification
        assert spec.executable is not None and spec.output_contains is not None
        executable = self._capture(
            [spec.executable, *spec.args],
            workspace=workspace,
        )
        self._require_output(executable, spec.output_contains, record.id)

    def _verify_absolute_executable(
        self, record: DependencyRecord, *, workspace: Path
    ) -> None:
        spec = record.verification
        assert spec.path is not None and spec.output_contains is not None
        path = Path(spec.path)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise DependencyError(
                f"{record.id}: executable is missing or not executable: {path}"
            )
        result = self._capture([str(path), *spec.args], workspace=workspace)
        self._require_output(result, spec.output_contains, record.id)

    def _verify_rust_toolchain(
        self, record: DependencyRecord, *, workspace: Path
    ) -> None:
        active = self._capture(
            ["rustup", "show", "active-toolchain"], workspace=workspace
        )
        if not active.stdout.strip().startswith(record.version):
            raise DependencyError(f"{record.id}: Rust default toolchain is stale")
        installed = self._capture(["rustup", "toolchain", "list"], workspace=workspace)
        if not any(
            self._rust_toolchain_matches(line, record.version)
            for line in installed.stdout.splitlines()
            if line.strip()
        ):
            raise DependencyError(f"{record.id}: Rust toolchain is not installed")
        components = self._capture(
            ["rustup", "component", "list", "--toolchain", record.version],
            workspace=workspace,
        ).stdout
        for component in record.components:
            if not any(
                line.startswith(component) and "(installed)" in line
                for line in components.splitlines()
            ):
                raise DependencyError(
                    f"{record.id}: Rust component is stale: {component}"
                )
        component_tools = {
            "rustfmt": "rustfmt",
            "clippy": "clippy-driver",
            "rust-analyzer": "rust-analyzer",
        }
        tools = (
            "rustc",
            "cargo",
            *(
                component_tools[component]
                for component in record.components
                if component in component_tools
            ),
        )
        for tool in tools:
            result = self._capture(
                ["rustup", "run", record.version, tool, "--version"],
                workspace=workspace,
            )
            if tool == "rust-analyzer":
                self._require_output(result, f"rust-analyzer {record.version}", record.id)

    @staticmethod
    def _rust_toolchain_matches(line: str, version: str) -> bool:
        """Match rustup's optional host-triple suffix for one exact version."""
        installed = line.split()[0]
        return installed == version or installed.startswith(f"{version}-")

    def _verify_lean_toolchain(
        self, record: DependencyRecord, *, workspace: Path
    ) -> None:
        active = self._capture(["elan", "show"], workspace=workspace)
        installed = self._capture(["elan", "toolchain", "list"], workspace=workspace)
        if record.version not in active.stdout or not any(
            line.split()[0] == record.version
            for line in installed.stdout.splitlines()
            if line.strip()
        ):
            raise DependencyError(f"{record.id}: Lean toolchain is stale")
        for tool in ("lean", "lake"):
            self._capture(
                ["elan", "run", record.version, tool, "--version"],
                workspace=workspace,
            )

    def _cargo_source(self, record: DependencyRecord, workspace: Path) -> Path:
        workspace_root = workspace.resolve()
        standalone_source = workspace_root / record.source
        vendor_root = workspace_root / "vendor" / "agent-canon"
        # A vendored AgentCanon checkout is the canonical source in a derived
        # parent. Resolve it before considering the standalone layout so a
        # stale parent-root copy cannot win merely because it exists.
        source_projection = workspace_root.parent / "agent-canon-source" / record.source
        source_projection_is_dir = source_projection.is_dir()
        if source_projection_is_dir:
            source = source_projection.resolve()
        elif vendor_root.is_dir():
            source = (vendor_root / record.source).resolve()
        else:
            source = standalone_source.resolve()
        allowed_roots = [workspace_root]
        if source_projection_is_dir:
            allowed_roots.append(source_projection.parent.parent.resolve())
        if not any(
            os.path.commonpath((str(root), str(source))) == str(root)
            for root in allowed_roots
        ):
            raise DependencyError(f"{record.id}: cargo source escapes workspace")
        if not source.is_dir():
            raise DependencyError(f"{record.id}: cargo source is missing: {source}")
        return source

    @staticmethod
    def _cargo_snapshot(source: Path) -> tuple[str, str]:
        """Verify the closed canonical source inventory and return its digests."""
        expected: set[str] = set(CANONICAL_RUST_SOURCE_FILES)
        for relative in CANONICAL_RUST_SOURCE_FILES:
            path = source / relative
            if path.is_symlink() or not path.is_file():
                raise DependencyError(f"cargo source snapshot file is missing: {relative}")
        actual = {
            path.relative_to(source).as_posix()
            for path in source.rglob("*")
            if path.is_file() and not path.is_symlink()
            and "target" not in path.relative_to(source).parts
            and ".git" not in path.relative_to(source).parts
        }
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise DependencyError(
                f"cargo source snapshot inventory mismatch: missing={missing} extra={extra}"
            )
        digest = hashlib.sha256()
        for relative in sorted(CANONICAL_RUST_SOURCE_FILES):
            blob = hashlib.sha256((source / relative).read_bytes()).hexdigest()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(blob.encode("ascii"))
            digest.update(b"\0")
        cargo_lock = hashlib.sha256((source / "Cargo.lock").read_bytes()).hexdigest()
        return digest.hexdigest(), cargo_lock

    def _verify_canonical_snapshot(
        self, record: DependencyRecord, workspace: Path
    ) -> tuple[str, str]:
        source = self._cargo_source(record, workspace)
        source_digest, lock_digest = self._cargo_snapshot(source)
        if (
            source_digest != record.source_tree_sha256
            or lock_digest != record.cargo_lock_sha256
        ):
            raise DependencyError(
                f"{record.id}: immutable source snapshot mismatch "
                f"{source_digest}!={record.source_tree_sha256} or "
                f"{lock_digest}!={record.cargo_lock_sha256}"
            )
        return source_digest, lock_digest

    def _cargo_source_identity(
        self,
        record: DependencyRecord,
        workspace: Path,
        *,
        source: Path | None = None,
    ) -> str:
        """Validate and return the Git identity for an explicit commit record."""
        resolved_source = source or self._cargo_source(record, workspace)
        if record.commit is None:
            raise DependencyError(
                f"{record.id}: active-source records have no Git source identity"
            )
        try:
            result = self._capture(
                [
                    "git",
                    "-C",
                    str(resolved_source),
                    "rev-parse",
                    "--verify",
                    "HEAD",
                ],
                workspace=workspace,
                operation="verify-cargo-source-identity",
                tool_paths=False,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise DependencyError(
                f"{record.id}: cannot read cargo source commit from {resolved_source}: {exc}"
            ) from exc
        observed_commit = result.stdout.strip()
        if observed_commit:
            if COMMIT_RE.fullmatch(observed_commit) is None:
                raise DependencyError(
                    f"{record.id}: cargo source identity is not a full commit: "
                    f"{observed_commit!r}"
                )
            if observed_commit.lower() != record.commit.lower():
                raise DependencyError(
                    f"{record.id}: cargo source commit mismatch "
                    f"{observed_commit}!={record.commit}"
                )
            return observed_commit.lower()
        return record.commit.lower()

    def _verify_cargo_binary(
        self, record: DependencyRecord, *, workspace: Path
    ) -> None:
        spec = record.verification
        assert spec.path is not None and spec.output_contains is not None
        source = self._cargo_source(record, workspace)
        if record.source_identity == CANONICAL_SNAPSHOT_IDENTITY:
            self._verify_canonical_snapshot(record, workspace)
        if record.commit is not None:
            self._cargo_source_identity(record, workspace, source=source)
        binary = self._cargo_binary_path(record, source=source)
        configured_target = (
            os.environ.get("AGENT_CANON_CARGO_TARGET_DIR")
            if self._image_owned
            else None
        )
        allowed_root = Path(configured_target or source / "target").resolve()
        if os.path.commonpath((str(allowed_root), str(binary))) != str(allowed_root):
            raise DependencyError(f"{record.id}: cargo binary escapes its target")
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise DependencyError(f"{record.id}: cargo binary is missing: {binary}")
        result = self._capture([str(binary), *spec.args], workspace=workspace)
        self._require_output(result, spec.output_contains, record.id)

    def _verify_browser_executable(
        self, record: DependencyRecord, *, workspace: Path
    ) -> None:
        assert record.browser_cache_path is not None
        spec = record.verification
        assert spec.output_contains is not None
        cache_path = Path(record.browser_cache_path)
        if cache_path.is_symlink() or not cache_path.is_dir():
            raise DependencyError(f"{record.id}: browser cache is missing")
        cache = cache_path.resolve()
        matches: list[Path] = []
        for pattern in spec.executable_globs:
            for candidate in sorted(cache.glob(pattern)):
                resolved = candidate.resolve()
                if (
                    not candidate.is_symlink()
                    and candidate.is_file()
                    and os.access(candidate, os.X_OK)
                    and os.path.commonpath((str(cache), str(resolved))) == str(cache)
                ):
                    matches.append(candidate)
        if not matches:
            raise DependencyError(
                f"{record.id}: browser executable is missing from cache"
            )
        result = self._capture(
            [str(matches[0]), *spec.args],
            workspace=workspace,
            env={"PLAYWRIGHT_BROWSERS_PATH": record.browser_cache_path},
        )
        self._require_output(result, spec.output_contains, record.id)

    def _install_apt_repository(
        self, record: DependencyRecord, workspace: Path, *, repair: bool = False
    ) -> None:
        self._active_record = record
        self._active_phase = "image-install"
        self._active_owner = "image-installer"
        assert record.key_url is not None
        assert record.key_fingerprint is not None
        with tempfile.TemporaryDirectory(
            prefix=f"agent-canon-{record.id}-",
            dir=_parent_temp_root(workspace, "apt-repository"),
        ) as temporary:
            root = Path(temporary)
            raw_key = root / "key.raw"
            keyring = root / f"{record.id}.gpg"
            _download(
                record.key_url,
                raw_key,
                operation=NetworkOperation(
                    phase="image-install",
                    owner="image-installer",
                    operation="download-apt-key",
                    method=record.method.value,
                    record_id=record.id,
                    url=record.key_url,
                    allow_network=True,
                ),
            )
            fingerprint = self._capture(
                ["gpg", "--show-keys", "--with-colons", str(raw_key)],
                workspace=workspace,
                operation="verify-apt-repository-key",
                tool_paths=False,
            ).stdout
            expected = record.key_fingerprint
            observed = {
                line.split(":")[9].upper()
                for line in fingerprint.splitlines()
                if line.startswith("fpr:") and len(line.split(":")) > 9
            }
            if expected not in observed:
                raise DependencyError(f"{record.id}: apt key fingerprint mismatch")
            self._run(
                ["gpg", "--dearmor", "--output", str(keyring), str(raw_key)],
                workspace=workspace,
            )
            key_destination = Path("/etc/apt/keyrings") / f"{record.id}.gpg"
            self._run(
                [
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    str(keyring),
                    str(key_destination),
                ],
                workspace=workspace,
                privileged=True,
            )
            repo_line = root / "repository.list"
            repo_line.write_text(
                self._apt_repository_line(record, key_destination), encoding="utf-8"
            )
            self._verify_repository_packages_digest(record, workspace=workspace)
            self._run(
                [
                    "install",
                    "-D",
                    "-m",
                    "0644",
                    str(repo_line),
                    f"/etc/apt/sources.list.d/{record.id}.list",
                ],
                workspace=workspace,
                privileged=True,
            )
            self._run(["apt-get", "update"], workspace=workspace, privileged=True)
            if record.repository_package_url is not None:
                package_path = root / _repository_package_filename(record)
                _download(
                    record.repository_package_url,
                    package_path,
                    operation=NetworkOperation(
                        phase="image-install",
                        owner="image-installer",
                        operation="download-apt-package",
                        method=record.method.value,
                        record_id=record.id,
                        url=record.repository_package_url,
                        allow_network=True,
                    ),
                )
                assert record.repository_package_sha256 is not None
                observed = hashlib.sha256(package_path.read_bytes()).hexdigest()
                if observed != record.repository_package_sha256:
                    raise DependencyError(
                        f"{record.id}: immutable apt package SHA256 mismatch "
                        f"{observed}!={record.repository_package_sha256}"
                    )
                command = [
                    "apt-get",
                    "install",
                    "-y",
                    "--no-install-recommends",
                    "--no-remove",
                    str(package_path),
                ]
                if repair:
                    command.insert(2, "--reinstall")
                self._run(command, workspace=workspace, privileged=True)

    def _install_release_asset(
        self, record: DependencyRecord, *, workspace: Path
    ) -> None:
        assert record.destination is not None
        asset_map = dict(record.assets)
        if asset_map:
            asset = asset_map.get(architecture())
            if asset is None:
                raise DependencyError(
                    f"{record.id}: no release asset for architecture {architecture()}"
                )
        else:
            assert record.asset is not None
            asset = record.asset
        source = (
            record.source.rstrip("/") + "/" + asset
            if not record.source.endswith(asset)
            else record.source
        )
        with tempfile.TemporaryDirectory(
            prefix=f"agent-canon-{record.id}-",
            dir=_parent_temp_root(workspace or Path.cwd(), "release-asset"),
        ) as temporary:
            root = Path(temporary)
            archive = root / asset
            archive.parent.mkdir(parents=True, exist_ok=True)
            _download(
                source,
                archive,
                operation=NetworkOperation(
                    phase="image-install",
                    owner="image-installer",
                    operation="download-release-asset",
                    method=record.method.value,
                    record_id=record.id,
                    url=source,
                    allow_network=True,
                ),
            )
            checksum_map = dict(record.checksums)
            if checksum_map:
                expected = checksum_map.get(architecture())
                if expected is None:
                    raise DependencyError(
                        f"{record.id}: no release checksum for architecture {architecture()}"
                    )
            else:
                if record.checksum is None:
                    raise DependencyError(f"{record.id}: release checksum is missing")
                expected = record.checksum
            observed = hashlib.sha256(archive.read_bytes()).hexdigest()
            if observed != expected:
                raise DependencyError(f"{record.id}: release checksum mismatch")
            extracted = root / "extract"
            if record.extract != "none":
                safe_extract_tar(archive, extracted)
                candidate = extracted / record.destination.lstrip("/")
            else:
                candidate = archive
            if not candidate.is_file():
                matches = (
                    list(extracted.rglob(Path(record.destination).name))
                    if extracted.exists()
                    else []
                )
                if len(matches) != 1:
                    raise DependencyError(
                        f"{record.id}: extracted destination not found"
                    )
                candidate = matches[0]
            self._run_install_file(candidate, Path(record.destination), workspace=workspace)

    def _run_install_file(self, source: Path, destination: Path, *, workspace: Path) -> None:
        self._run_command(
            ["install", "-D", "-m", "0755", str(source), str(destination)],
            self._command_provenance(
                ["install", "-D", "-m", "0755", str(source), str(destination)],
                operation="install-release-asset",
                method="release-asset",
                phase="image-install",
                owner="image-installer",
                privileged=True,
            ),
            workspace=workspace,
        )


def _download(
    url: str,
    destination: Path,
    *,
    operation: NetworkOperation | None = None,
) -> None:
    """Download only a manifest-owned image-install network operation."""
    if operation is None:
        raise DependencyError(
            "command-boundary-network-fetch: unowned network operation"
        )
    if (
        operation.phase != "image-install"
        or operation.owner != "image-installer"
        or not operation.allow_network
        or not operation.record_id
        or operation.operation not in _NETWORK_OPERATION_METHODS
        or operation.method != _NETWORK_OPERATION_METHODS[operation.operation]
        or operation.url != url
    ):
        raise DependencyError(
            "command-boundary-network-fetch: network operation is not image-owned"
        )
    with urllib.request.urlopen(url) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _repository_packages_url(record: DependencyRecord) -> str:
    """Derive the canonical uncompressed Packages index URL for one record."""
    if record.method is not Method.APT_REPOSITORY:
        raise DependencyError(
            f"{record.id}: Packages index URL requires apt-repository method"
        )
    if record.platform is None:
        raise DependencyError(f"{record.id}: Packages index URL requires platform")
    if record.repository_suite is None:
        raise DependencyError(f"{record.id}: Packages index URL requires repository suite")
    if len(record.repository_components) != 1:
        raise DependencyError(
            f"{record.id}: Packages index URL requires exactly one repository component"
        )
    architecture_name = record.platform.split("/", 1)[1]
    component = record.repository_components[0]
    return (
        f"{record.source.rstrip('/')}/dists/{record.repository_suite}/"
        f"{component}/binary-{architecture_name}/Packages"
    )


def _repository_package_payload(
    record: DependencyRecord,
) -> dict[str, str] | None:
    """Return the immutable apt artifact identity owned by one record."""
    if record.repository_package_url is None:
        return None
    if record.repository_package_sha256 is None:  # pragma: no cover - parser closes this.
        raise DependencyError(
            f"{record.id}: repository package URL/SHA pair is incomplete"
        )
    return {
        "url": record.repository_package_url,
        "sha256": record.repository_package_sha256,
    }


def _repository_packages_payload(
    record: DependencyRecord,
) -> dict[str, str] | None:
    """Return the rolling Packages index identity owned by one record."""
    if record.repository_packages_sha256 is None:
        return None
    return {
        "url": _repository_packages_url(record),
        "sha256": record.repository_packages_sha256,
    }


def _repository_package_filename(record: DependencyRecord) -> str:
    """Return the safe `.deb` filename carried by an immutable apt URL."""
    url = record.repository_package_url
    if url is None:
        raise DependencyError(f"{record.id}: immutable apt package URL is not declared")
    filename = PurePosixPath(urllib.parse.urlparse(url).path).name
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_~-]*\.deb", filename) is None:
        raise DependencyError(
            f"{record.id}: immutable apt package URL has an unsafe filename"
        )
    return filename


def resolve_verified_executable(
    workspace: Path,
    vendor_root: Path | None,
    receipts: Path,
    record_id: str,
    executable: str,
) -> VerifiedExecutable:
    """Resolve a receipt-bound executable after strict live verification."""
    if not executable or Path(executable).name != executable:
        raise DependencyError(f"requested executable must be one command name: {executable!r}")
    plan = load_plan(workspace, vendor_root)
    record = plan.by_id().get(record_id)
    if record is None:
        raise DependencyError(f"dependency record is not present: {record_id}")
    if executable not in _executable_binding_names(record):
        raise DependencyError(
            f"{record_id}: requested executable is not manifest-provided: {executable}"
        )
    receipt = _receipt_path(receipts, record_id)
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise DependencyError(f"{record_id}: executable receipt is unreadable") from exc
    bindings = payload.get("executable_bindings")
    binding = bindings.get(executable) if isinstance(bindings, dict) else None
    expected_bindings = set(_executable_binding_names(record))
    if (
        payload.get("schema") != "agent-canon.devcontainer-dependency-receipt"
        or payload.get("status") != "pass"
        or payload.get("record_id") != record_id
        or payload.get("manifest_version") != record.version
        or payload.get("plan_fingerprint") != plan.fingerprint
        or payload.get("record_fingerprint") != record.fingerprint()
        or payload.get("verification") != record.verification.payload()
        or not isinstance(bindings, dict)
        or set(bindings) != expected_bindings
        or any(
            not isinstance(item, dict)
            or item.get("provided") != name
            or not isinstance(item.get("lexical_path"), str)
            or not Path(item["lexical_path"]).is_absolute()
            or item["lexical_path"] != os.path.normpath(item["lexical_path"])
            or not isinstance(item.get("absolute_path"), str)
            or not Path(item["absolute_path"]).is_absolute()
            or item["absolute_path"] != os.path.normpath(item["absolute_path"])
            or not isinstance(item.get("verification_output"), str)
            or not item.get("verification_output")
            for name, item in bindings.items()
        )
        or not isinstance(binding, dict)
        or binding.get("provided") != executable
        or not isinstance(binding.get("lexical_path"), str)
        or not Path(binding["lexical_path"]).is_absolute()
        or binding["lexical_path"] != os.path.normpath(binding["lexical_path"])
        or not isinstance(binding.get("absolute_path"), str)
        or not Path(binding["absolute_path"]).is_absolute()
        or binding["absolute_path"] != os.path.normpath(binding["absolute_path"])
        or not isinstance(binding.get("verification_output"), str)
        or not binding.get("verification_output")
        or payload.get("repository_packages") != _repository_packages_payload(record)
        or payload.get("repository_package") != _repository_package_payload(record)
    ):
        raise DependencyError(f"{record_id}: executable receipt binding is stale")
    installer = Installer()
    installer.verify(
        record,
        workspace=workspace,
        strict_executables=True,
        allow_network=False,
    )
    live_bindings = installer._executable_bindings(record, workspace=workspace)
    live = live_bindings.get(executable)
    if live is None:
        raise DependencyError(f"{record_id}: executable binding is unavailable: {executable}")
    if (
        live["lexical_path"] != binding["lexical_path"]
        or live["absolute_path"] != binding["absolute_path"]
        or live["verification_output"] != binding["verification_output"]
    ):
        raise DependencyError(f"{record_id}: executable receipt path or output drift")
    return VerifiedExecutable(
        record_id=record.id,
        manifest_version=record.version,
        executable=executable,
        absolute_path=live["absolute_path"],
        record_fingerprint=record.fingerprint(),
        plan_fingerprint=plan.fingerprint,
        verification_output=live["verification_output"],
    )


def _cli_plan(args: argparse.Namespace) -> DependencyPlan:
    workspace = Path(args.workspace).resolve()
    vendor_root = Path(args.vendor_root).resolve() if args.vendor_root else None
    return load_plan(workspace, vendor_root)


def install_plan(
    plan: DependencyPlan,
    *,
    workspace: Path,
    receipts: Path,
    runner: CommandRunner | None = None,
    identity: RuntimeIdentity | None = None,
) -> tuple[str, ...]:
    """Validate runtime identity, then begin installation with no earlier side effect."""
    validate_runtime_identity(plan, identity)
    return Installer(runner).install(plan, workspace=workspace, receipts=receipts)


def build_parser() -> argparse.ArgumentParser:
    """Build the dependency model CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "dry-run",
            "install",
            "boundary",
            "project-install",
            "image-install",
            "image-verify",
        ),
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--vendor-root")
    parser.add_argument("--receipts")
    parser.add_argument(
        "--final-binary-dir",
        help="image-owned destination directory for built Cargo binaries",
    )
    parser.add_argument("--extras", default="")
    parser.add_argument(
        "--records",
        action="append",
        nargs="+",
        default=None,
        help="record IDs (comma-separated or repeated) for image commands",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run validation, dry-run, or installation with typed failure output."""
    args = build_parser().parse_args(argv)
    exit_status = 0
    payload: dict[str, Any]
    try:
        if args.command not in {"image-install", "image-verify"} and args.records:
            raise DependencyError(
                "--records is only supported by image-install and image-verify"
            )
        if args.command == "project-install":
            workspace = Path(args.workspace).resolve()
            extras = parse_python_extras(args.extras)
            installed = install_project_extras(workspace, extras)
            payload = {"status": "pass", "extras": list(installed)}
        elif args.command == "boundary":
            workspace = Path(args.workspace).resolve()
            vendor_root = (
                Path(args.vendor_root).resolve()
                if args.vendor_root
                else workspace / "vendor" / "agent-canon"
            )
            report = EnvironmentBoundaryModel(workspace, vendor_root).validate()
            payload = {
                "status": report.status,
                "checked": list(report.checked),
                "findings": [
                    dataclasses.asdict(finding) for finding in report.findings
                ],
            }
            exit_status = 0 if not report.findings else 1
        else:
            plan = _cli_plan(args)
            if args.command in {"image-install", "image-verify"}:
                workspace = Path(args.workspace).resolve()
                selected_records = (
                    None
                    if args.records is None
                    else [value for group in args.records for value in group]
                )
                if args.command == "image-install":
                    completed = image_install_plan(
                        plan,
                        workspace=workspace,
                        records=selected_records,
                        final_binary_dir=(
                            Path(args.final_binary_dir).resolve()
                            if args.final_binary_dir
                            else None
                        ),
                    )
                    payload = {
                        "status": "pass",
                        "completed": list(completed),
                        "image_root": str(IMAGE_DEPENDENCIES_ROOT),
                        "plan_fingerprint": plan.fingerprint,
                    }
                else:
                    verified = image_verify_plan(
                        plan,
                        workspace=workspace,
                        records=selected_records,
                    )
                    payload = {
                        "status": "pass",
                        "verified": list(verified),
                        "image_root": str(IMAGE_DEPENDENCIES_ROOT),
                        "plan_fingerprint": plan.fingerprint,
                    }
            elif args.command == "validate":
                payload = {
                    "status": "pass",
                    "sources": [str(path) for path in plan.sources],
                    "order": list(plan.order),
                    "plan_fingerprint": plan.fingerprint,
                }
            elif args.command == "dry-run":
                payload = Installer().dry_run(plan)
            else:
                receipts = (
                    Path(args.receipts).resolve()
                    if args.receipts
                    else Path(args.workspace).resolve()
                    / ".agent-canon"
                    / "dependency-receipts"
                )
                completed = install_plan(
                    plan,
                    workspace=Path(args.workspace).resolve(),
                    receipts=receipts,
                )
                payload = {
                    "status": "pass",
                    "completed": list(completed),
                    "plan_fingerprint": plan.fingerprint,
                }
    except (
        DependencyError,
        OSError,
        urllib.error.URLError,
        subprocess.CalledProcessError,
    ) as exc:
        if args.command == "image-verify":
            if args.format == "json":
                print(
                    json.dumps(
                        {"status": "rebuild-required", "error": str(exc)},
                        sort_keys=True,
                    )
                )
            else:
                print("DEVCONTAINER_IMAGE_VERIFY=rebuild-required", file=sys.stderr)
        print(f"DEVCONTAINER_DEPENDENCY_ERROR={exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"DEVCONTAINER_DEPENDENCY={payload.get('status', 'pass')}")
        if args.command == "image-install":
            print("DEVCONTAINER_IMAGE_INSTALL=pass")
        if args.command == "image-verify":
            print("DEVCONTAINER_IMAGE_VERIFY=pass")
        if args.command == "boundary":
            for finding in payload.get("findings", []):
                print(
                    "DEVCONTAINER_BOUNDARY_FINDING="
                    f"{finding['category']}:{finding['path']}:{finding['detail']}"
                )
        if "sources" in payload:
            print("DEVCONTAINER_DEPENDENCY_SOURCES=" + ",".join(payload["sources"]))
        if "order" in payload:
            print("DEVCONTAINER_DEPENDENCY_ORDER=" + ",".join(payload["order"]))
        if "completed" in payload:
            print("DEVCONTAINER_DEPENDENCY_COMPLETED=" + ",".join(payload["completed"]))
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
