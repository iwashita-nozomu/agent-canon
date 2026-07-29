#!/usr/bin/env python3
# @dependency-start
# contract implementation
# responsibility Owns the typed declarative devcontainer dependency model, merge, plan, and receipt installer.
# upstream design ../../documents/design/devcontainer/parent-dependency-manifest-followup.md parent-first merge and lifecycle order
# upstream design ../../CONTAINER_OPERATIONS.md image versus mounted tool boundary
# downstream environment ../../.devcontainer/dependencies.toml AgentCanon shared developer/agent records
# downstream implementation ../../.devcontainer/post-create.sh shared lifecycle orchestration
# downstream implementation ../../tools/docker_dependency_validator.sh no-install validation route
# downstream implementation ../../tests/agent_tools/test_devcontainer_dependencies.py focused model and security tests
# @dependency-end
"""Declarative, typed devcontainer dependency planning and installation.

The module deliberately has no third-party runtime dependency. Python 3.11+
provide tomllib; older supported images use the already bootstrapped tomli
module instead.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
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

try:  # pragma: no cover - the branch depends on the interpreter image.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - covered with a subprocess test.
    import tomli as tomllib  # type: ignore[no-redef]


SCHEMA = "agent-canon.devcontainer-dependencies"
SCHEMA_VERSION = 1
METHODS = frozenset(
    {
        "apt-package",
        "apt-repository",
        "npm-global",
        "pip-user",
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
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
APT_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
NPM_PACKAGE_RE = re.compile(r"^(?:@[a-z0-9._~-]+/[a-z0-9._~-]+|[a-z0-9._~-]+)$")
SEMVER_RE = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
VERSION_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+:~_-]*$")
SAFE_MEMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
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
        "ninja-build",
        "node",
        "npm",
        "python3",
        "python3-pip",
        "pip",
        "tar",
        "tomli",
        "tomllib",
        "xz-utils",
    }
)


class DependencyError(ValueError):
    """Base error for schema, merge, plan, and execution failures."""


class Method(str, Enum):
    """Closed set of supported dependency installation mechanisms."""

    APT_PACKAGE = "apt-package"
    APT_REPOSITORY = "apt-repository"
    NPM_GLOBAL = "npm-global"
    PIP_USER = "pip-user"
    RELEASE_ASSET = "release-asset"
    RUST_TOOLCHAIN = "rust-toolchain"
    LEAN_TOOLCHAIN = "lean-toolchain"
    CARGO_SOURCE_BUILD = "cargo-source-build"
    BROWSER_INSTALL = "browser-install"


@dataclass(frozen=True)
class DependencyRecord:
    """One fully typed dependency record."""

    id: str
    package: str
    method: Method
    version: str
    source: str
    commands: tuple[tuple[str, ...], ...]
    deps: tuple[str, ...]
    provides: tuple[str, ...]
    failure_policy: str
    key_fingerprint: str | None = None
    key_url: str | None = None
    checksum: str | None = None
    checksums: tuple[tuple[str, str], ...] = ()
    asset: str | None = None
    assets: tuple[tuple[str, str], ...] = ()
    archive_format: str | None = None
    extract: str | None = None
    destination: str | None = None
    repo: str | None = None
    commit: str | None = None
    locked: bool | None = None
    browser: str | None = None
    browser_cache_path: str | None = None
    components: tuple[str, ...] = ()

    def payload(self) -> dict[str, Any]:
        """Return a canonical JSON-compatible representation."""
        return dataclasses.asdict(self) | {"method": self.method.value}

    def fingerprint(self) -> str:
        """Return the stable identity hash used by receipts."""
        encoded = canonical_json(self.payload()).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class LoadedManifest:
    """A manifest and its source location."""

    path: Path
    records: tuple[DependencyRecord, ...]


@dataclass(frozen=True)
class DependencyPlan:
    """Validated merged records and deterministic execution order."""

    records: tuple[DependencyRecord, ...]
    order: tuple[str, ...]
    sources: tuple[Path, ...]
    dependency_providers: tuple[tuple[str, tuple[str, ...]], ...]
    fingerprint: str

    def by_id(self) -> dict[str, DependencyRecord]:
        """Return records indexed by their stable IDs."""
        return {record.id: record for record in self.records}

    def providers_for(self, record_id: str) -> tuple[str, ...]:
        """Return the record providers required by one record."""
        return dict(self.dependency_providers).get(record_id, ())


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
                raise DependencyError("privileged dependency action requires root or sudo")
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


def _commands(value: object) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list) or not value:
        raise DependencyError("commands must be a non-empty array of argv arrays")
    result: list[tuple[str, ...]] = []
    for index, command in enumerate(value):
        if not isinstance(command, list) or not command:
            raise DependencyError(f"commands[{index}] must be a non-empty argv array")
        if any(
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or CONTROL_RE.search(item)
            or TRAVERSAL_RE.search(item)
            for item in command
        ):
            raise DependencyError(f"commands[{index}] must contain non-empty strings")
        executable = Path(command[0]).name
        if command[0].startswith("-") or executable in SHELL_EXECUTABLES:
            raise DependencyError(f"commands[{index}] must not invoke a shell interpreter")
        if executable in {"python", "python3", "node", "perl", "ruby"} and "-c" in command:
            raise DependencyError(f"commands[{index}] must not use code-evaluation flags")
        result.append(tuple(command))
    return tuple(result)


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
            raise DependencyError(f"checksum[{arch_name}] must be a 64-character SHA256")
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
    if parsed.scheme not in {"https", "file"} or (
        not parsed.netloc and parsed.scheme == "https"
    ) or parsed.query or parsed.fragment or TRAVERSAL_RE.search(parsed.path):
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


def _validate_package(record: DependencyRecord) -> None:
    if record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY}:
        if APT_PACKAGE_RE.fullmatch(record.package) is None:
            raise DependencyError(f"{record.id}.package is not an apt package name")
    elif record.method in {Method.NPM_GLOBAL, Method.PIP_USER}:
        pattern = NPM_PACKAGE_RE if record.method is Method.NPM_GLOBAL else APT_PACKAGE_RE
        if pattern.fullmatch(record.package) is None:
            raise DependencyError(f"{record.id}.package has an unsupported registry name")
    elif record.method is Method.BROWSER_INSTALL:
        if record.package not in {"chromium", "firefox", "webkit"}:
            raise DependencyError(f"{record.id}.package has an unsupported browser")
    elif VERSION_TOKEN_RE.fullmatch(record.package) is None:
        raise DependencyError(f"{record.id}.package has an unsupported value")


def _validate_method_fields(record: DependencyRecord, raw: Mapping[str, object]) -> None:
    common = {
        "id", "package", "method", "version", "source", "commands", "deps",
        "provides", "failure_policy",
    }
    method_fields = {
        Method.APT_PACKAGE: set(),
        Method.APT_REPOSITORY: {"key_fingerprint", "key_url"},
        Method.NPM_GLOBAL: set(),
        Method.PIP_USER: set(),
        Method.RELEASE_ASSET: {
            "checksum", "checksums", "asset", "assets", "archive_format",
            "extract", "destination",
        },
        Method.RUST_TOOLCHAIN: {"components"},
        Method.LEAN_TOOLCHAIN: set(),
        Method.CARGO_SOURCE_BUILD: {"repo", "commit", "locked"},
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
    _validate_package(record)
    if record.method in {Method.APT_PACKAGE, Method.APT_REPOSITORY}:
        if VERSION_TOKEN_RE.fullmatch(record.version) is None:
            raise DependencyError(f"{record.id}.version has an unsupported apt value")
        if record.method is Method.APT_REPOSITORY:
            _validate_https_url(record.source, f"{record.id}.source")
        elif VERSION_TOKEN_RE.fullmatch(record.source) is None and not record.source.startswith("https://"):
            raise DependencyError(f"{record.id}.source has an unsupported apt value")
    elif record.method in {Method.NPM_GLOBAL, Method.PIP_USER}:
        if SEMVER_RE.fullmatch(record.version) is None:
            raise DependencyError(f"{record.id}.version must be an exact version")
        _validate_https_url(record.source, f"{record.id}.source")
    elif record.method is Method.RELEASE_ASSET:
        if VERSION_TOKEN_RE.fullmatch(record.version) is None:
            raise DependencyError(f"{record.id}.version has an unsupported release value")
        _validate_https_url(record.source, f"{record.id}.source")
        for asset in (record.asset, *[value for _, value in record.assets]):
            if asset is not None:
                _validate_safe_asset_path(asset, f"{record.id}.asset")
        for arch, _ in record.assets:
            if arch not in {"x86_64", "aarch64"}:
                raise DependencyError(f"{record.id}.assets has an unsupported architecture")
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
        _validate_absolute_path(record.destination, f"{record.id}.destination", prefix="/usr/local/bin")
    elif record.method is Method.RUST_TOOLCHAIN:
        if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", record.version) is None:
            raise DependencyError(f"{record.id}.version must be an exact Rust version")
        _validate_https_url(record.source, f"{record.id}.source")
        if any(component not in {"rustfmt", "clippy", "rust-analyzer"} for component in record.components):
            raise DependencyError(f"{record.id}.components contains an unsupported component")
    elif record.method is Method.LEAN_TOOLCHAIN:
        if re.fullmatch(r"leanprover/lean4:v[0-9]+\.[0-9]+\.[0-9]+", record.version) is None:
            raise DependencyError(f"{record.id}.version must be an exact Lean toolchain")
        _validate_https_url(record.source, f"{record.id}.source")
    elif record.method is Method.CARGO_SOURCE_BUILD:
        if record.source.startswith("/") or TRAVERSAL_RE.search(record.source):
            raise DependencyError(f"{record.id}.source must stay within the workspace")
        if PurePosixPath(record.source).is_absolute() or any(
            part in {"", "."} for part in PurePosixPath(record.source).parts
        ):
            raise DependencyError(f"{record.id}.source must be a normalized relative path")
        assert record.repo is not None
        _validate_https_url(record.repo, f"{record.id}.repo")
        assert record.commit is not None
        if COMMIT_RE.fullmatch(record.commit) is None:
            raise DependencyError(f"{record.id}.commit must be a full 40-hex commit")
    elif record.method is Method.BROWSER_INSTALL:
        if record.browser not in {"chromium", "firefox", "webkit"}:
            raise DependencyError(f"{record.id}.browser is unsupported")
        if SEMVER_RE.fullmatch(record.version) is None:
            raise DependencyError(f"{record.id}.version must be an exact Playwright version")
        _validate_https_url(record.source, f"{record.id}.source")
        assert record.browser_cache_path is not None
        _validate_absolute_path(
            record.browser_cache_path,
            f"{record.id}.browser_cache_path",
            prefix="/usr/local/share",
        )


def _validate_command_contract(record: DependencyRecord) -> None:
    """Keep the method-specific install primitive separate from verification argv."""
    del record


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
        "commands",
        "deps",
        "provides",
        "failure_policy",
        "key_fingerprint",
        "key_url",
        "checksum",
        "checksums",
        "asset",
        "assets",
        "archive_format",
        "extract",
        "destination",
        "repo",
        "commit",
        "locked",
        "browser",
        "browser_cache_path",
        "components",
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
        "commands",
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
    failure_policy = _string(raw["failure_policy"], f"{record_id}.failure_policy")
    if failure_policy not in FAILURE_POLICIES:
        raise DependencyError(
            f"{path}: {record_id}: unsupported failure policy {failure_policy}"
        )
    record = DependencyRecord(
        id=record_id,
        package=_string(raw["package"], f"{record_id}.package"),
        method=Method(method_value),
        version=_string(raw["version"], f"{record_id}.version"),
        source=_string(raw["source"], f"{record_id}.source"),
        commands=_commands(raw["commands"]),
        deps=_string_list(raw["deps"], f"{record_id}.deps"),
        provides=_string_list(
            raw["provides"], f"{record_id}.provides", allow_empty=False
        ),
        failure_policy=failure_policy,
        key_fingerprint=_optional_string(
            raw.get("key_fingerprint"), f"{record_id}.key_fingerprint"
        ),
        key_url=_optional_string(raw.get("key_url"), f"{record_id}.key_url"),
        checksum=_optional_string(raw.get("checksum"), f"{record_id}.checksum"),
        checksums=_checksums(raw["checksums"]) if "checksums" in raw else (),
        asset=_optional_string(raw.get("asset"), f"{record_id}.asset"),
        assets=_string_map(raw["assets"], f"{record_id}.assets") if "assets" in raw else (),
        archive_format=_optional_string(
            raw.get("archive_format"), f"{record_id}.archive_format"
        ),
        extract=_optional_string(raw.get("extract"), f"{record_id}.extract"),
        destination=_optional_string(
            raw.get("destination"), f"{record_id}.destination"
        ),
        repo=_optional_string(raw.get("repo"), f"{record_id}.repo"),
        commit=_optional_string(raw.get("commit"), f"{record_id}.commit"),
        locked=raw.get("locked") if "locked" in raw else None,
        browser=_optional_string(raw.get("browser"), f"{record_id}.browser"),
        browser_cache_path=_optional_string(
            raw.get("browser_cache_path"), f"{record_id}.browser_cache_path"
        ),
        components=_string_list(
            raw.get("components", []), f"{record_id}.components"
        ),
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
        if record.repo is None or record.commit is None or record.locked is not True:
            raise DependencyError(
                f"{record.id}: cargo-source-build requires repo, exact commit, and locked=true"
            )
        if COMMIT_RE.fullmatch(record.commit) is None:
            raise DependencyError(f"{record.id}.commit must be a full 40-hex commit")
    if record.method is Method.BROWSER_INSTALL and (
        record.browser is None or record.browser_cache_path is None
    ):
        raise DependencyError(
            f"{record.id}: browser-install requires browser and browser_cache_path"
        )
    _validate_method_fields(record, raw)
    _validate_method_values(record)
    _validate_command_contract(record)
    return record


def load_manifest(path: Path) -> LoadedManifest:
    """Load one manifest with tomllib/tomli and validate every record."""
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
        raise DependencyError(
            f"{path}: unknown top-level fields: {', '.join(unknown)}"
        )
    if raw.get("schema") != SCHEMA or raw.get("schema_version") != SCHEMA_VERSION:
        raise DependencyError(
            f"{path}: schema must be {SCHEMA!r} version {SCHEMA_VERSION}"
        )
    records = raw.get("records")
    if not isinstance(records, list) or not records:
        raise DependencyError(f"{path}: records must be a non-empty array of tables")
    parsed = tuple(
        parse_record(item, path=path, index=index)
        for index, item in enumerate(records)
    )
    ids = [record.id for record in parsed]
    if len(set(ids)) != len(ids):
        raise DependencyError(f"{path}: record ids must be unique")
    return LoadedManifest(path=path.resolve(), records=parsed)


def manifest_paths(workspace: Path, vendor_root: Path | None = None) -> tuple[Path, ...]:
    """Return parent-first manifest paths, reading standalone AgentCanon once."""
    workspace = workspace.resolve()
    vendor = (vendor_root or workspace / "vendor" / "agent-canon").resolve()
    parent_path = workspace / ".devcontainer" / "dependencies.toml"
    vendor_path = vendor / ".devcontainer" / "dependencies.toml"
    if vendor == workspace and parent_path == vendor_path:
        return (parent_path,) if parent_path.is_file() else ()
    paths: list[Path] = []
    if parent_path.is_file():
        paths.append(parent_path)
    if vendor_path.is_file() and vendor_path.resolve() not in {
        path.resolve() for path in paths
    }:
        paths.append(vendor_path)
    return tuple(paths)


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
                "failure_policy",
                "key_fingerprint",
                "key_url",
                "checksum",
                "asset",
                "archive_format",
                "extract",
                "destination",
                "repo",
                "commit",
                "locked",
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
                commands=_union(current.commands, incoming.commands),
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
                raise DependencyError(
                    f"dependency cycle: {record.id} -> {provider}"
                )
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
        remaining = sorted(
            set(by_id) - set(ordered), key=order_index.__getitem__
        )
        raise DependencyError(f"dependency cycle: {', '.join(remaining)}")
    sources = tuple(manifest.path for manifest in manifests)
    payload = {
        "sources": [str(path) for path in sources],
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
    )


def load_plan(workspace: Path, vendor_root: Path | None = None) -> DependencyPlan:
    """Load, merge, and fully validate the plan for a workspace."""
    paths = manifest_paths(workspace, vendor_root)
    if not paths:
        raise DependencyError("no devcontainer dependency manifest found")
    return build_plan(tuple(load_manifest(path) for path in paths))


@dataclass(frozen=True)
class BoundaryFinding:
    """One typed Docker/parent/devcontainer ownership finding."""

    category: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one stable machine-readable finding."""
        return f"DEVCONTAINER_BOUNDARY_FINDING={self.category}:{self.path}:{self.detail}"


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
                raise DependencyError(f"{path}: malformed Dockerfile instruction: {exc}") from exc
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

    @staticmethod
    def _requirements(path: Path) -> frozenset[str]:
        """Parse pinned or constrained requirement names for ownership checks."""
        names: set[str] = set()
        requirement_re = re.compile(
            r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:[<>=!~].*)?$"
        )
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            match = requirement_re.fullmatch(line)
            if match is None:
                raise DependencyError(f"{path}: unsupported requirement syntax: {line}")
            names.add(match.group(1).lower().replace("_", "-"))
        return frozenset(names)

    def _check_parent_container(
        self, findings: list[BoundaryFinding], checked: list[str]
    ) -> None:
        self._require(findings, checked, "README.md", "parent")
        self._require(findings, checked, "docker/README.md", "docker")
        dockerfile = self._require(findings, checked, "docker/Dockerfile", "docker")
        requirements = self._require(
            findings, checked, "docker/requirements.txt", "python"
        )
        installer = self._require(
            findings,
            checked,
            "docker/install_python_dependencies.sh",
            "python",
            executable=True,
        )
        self._require(findings, checked, "pyproject.toml", "python")
        self._require(
            findings, checked, "tools/requirement_sync_validator.py", "python"
        )
        self._require(findings, checked, "tools/ci/python_env_policy.py", "python")
        dockerignore = self._require(findings, checked, ".dockerignore", "docker")
        gitignore = self._require(findings, checked, ".gitignore", "python")
        if requirements is not None:
            try:
                declared = self._requirements(requirements)
            except DependencyError as exc:
                findings.append(BoundaryFinding("python", str(requirements), str(exc)))
            else:
                required = frozenset(
                    {"jupyterlab", "notebook", "ipykernel", "pydeps", "snakeviz", "pyyaml"}
                )
                for name in sorted(required - declared):
                    findings.append(
                        BoundaryFinding(
                            "python", str(requirements), f"missing-requirement:{name}"
                        )
                    )
        if installer is not None:
            text = installer.read_text(encoding="utf-8")
            if "docker/requirements.txt" not in text or "python3" not in text:
                findings.append(
                    BoundaryFinding(
                        "python",
                        str(installer),
                        "must-own-workspace-python-installation",
                    )
                )
        if dockerignore is not None:
            ignored = frozenset(
                line.strip()
                for line in dockerignore.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            )
            for entry in ("vendor/agent-canon", ".git", ".state"):
                if entry not in ignored:
                    findings.append(
                        BoundaryFinding("docker", str(dockerignore), f"missing-ignore:{entry}")
                    )
        if gitignore is not None:
            ignored = gitignore.read_text(encoding="utf-8")
            for entry in (".venv/", "venv/"):
                if entry not in ignored:
                    findings.append(
                        BoundaryFinding("python", str(gitignore), f"missing-ignore:{entry}")
                    )
        if dockerfile is not None:
            try:
                instructions = self._tokens(dockerfile)
            except DependencyError as exc:
                findings.append(BoundaryFinding("docker", str(dockerfile), str(exc)))
            else:
                packages = self._installed_apt_packages(instructions)
                for package in ("rsync", "openssh-client", "graphviz", "python3.11-venv"):
                    if package not in packages:
                        findings.append(
                            BoundaryFinding("docker", str(dockerfile), f"missing-runtime-package:{package}")
                        )
                for keyword, tokens in instructions:
                    if keyword != "RUN":
                        continue
                    if "pip" in tokens and "-r" in tokens:
                        findings.append(
                            BoundaryFinding("docker", str(dockerfile), "must-not-install-workspace-requirements")
                        )
                for keyword, tokens in instructions:
                    if keyword == "COPY" and any("docker/requirements.txt" in token for token in tokens):
                        findings.append(
                            BoundaryFinding("docker", str(dockerfile), "must-not-copy-workspace-requirements")
                        )

    def _check_parent_devcontainer(
        self, findings: list[BoundaryFinding], checked: list[str]
    ) -> None:
        config = self._require(findings, checked, ".devcontainer/devcontainer.json", "parent")
        self._require(
            findings,
            checked,
            ".devcontainer/post-create-parent.sh",
            "parent",
            executable=True,
        )
        self._require(findings, checked, ".devcontainer/dependencies.toml", "parent")
        if config is None:
            return
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(BoundaryFinding("parent", str(config), f"invalid-json:{exc}"))
            return
        if not isinstance(payload, dict):
            findings.append(BoundaryFinding("parent", str(config), "json-root-must-be-object"))
            return
        post_create = payload.get("postCreateCommand")
        if not isinstance(post_create, (str, list, dict)):
            findings.append(BoundaryFinding("parent", str(config), "missing-post-create-command"))
        else:
            command_text = json.dumps(post_create, sort_keys=True)
            for required in ("vendor/agent-canon/.devcontainer/post-create.sh", "post-create-parent.sh"):
                if required not in command_text:
                    findings.append(BoundaryFinding("parent", str(config), f"missing-command:{required}"))

    def validate(self) -> EnvironmentBoundaryReport:
        """Validate typed ownership coverage without running project commands."""
        findings: list[BoundaryFinding] = []
        checked: list[str] = []
        vendor_prefix = self.vendor_root.relative_to(self.workspace).as_posix() if not self.standalone else "."
        for relative in (
            f"{vendor_prefix}/.devcontainer/bootstrap-dependencies.sh" if not self.standalone else ".devcontainer/bootstrap-dependencies.sh",
            f"{vendor_prefix}/.devcontainer/dependencies.toml" if not self.standalone else ".devcontainer/dependencies.toml",
            f"{vendor_prefix}/.devcontainer/post-create.sh" if not self.standalone else ".devcontainer/post-create.sh",
            f"{vendor_prefix}/tools/agent_tools/devcontainer_dependencies.py" if not self.standalone else "tools/agent_tools/devcontainer_dependencies.py",
            f"{vendor_prefix}/CONTAINER_OPERATIONS.md" if not self.standalone else "CONTAINER_OPERATIONS.md",
        ):
            category = "environment" if relative.endswith("CONTAINER_OPERATIONS.md") else "shared-post-create"
            self._require(findings, checked, relative, category, executable=relative.endswith(".sh"))
        rulebook = self.vendor_root / "CONTAINER_OPERATIONS.md"
        if rulebook.is_file() and "Product Image And Mounted Tool Boundary" not in rulebook.read_text(encoding="utf-8"):
            findings.append(BoundaryFinding("environment", str(rulebook), "missing-product-mounted-boundary"))
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
            if member.issym() or member.islnk() or not (
                member.isdir() or member.isfile()
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


class Installer:
    """Execute a validated plan with per-record receipt semantics."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessRunner()

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
                    "commands": [list(command) for command in record.commands],
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
        self, plan: DependencyPlan, *, workspace: Path, receipts: Path
    ) -> tuple[str, ...]:
        """Install records in order, resuming only after live receipt verification."""
        receipts.mkdir(parents=True, exist_ok=True)
        completed: list[str] = []
        by_id = plan.by_id()
        unavailable: set[str] = set()
        for record_id in plan.order:
            record = by_id[record_id]
            receipt = _receipt_path(receipts, record.id)
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
                    print(f"DEPENDENCY_RECORD_WARN={record.id}:{error}", file=sys.stderr)
                    continue
                raise error
            if self._receipt_matches(receipt, plan, record):
                try:
                    self._verify_record(record, workspace=workspace)
                except Exception:
                    receipt.unlink(missing_ok=True)
                else:
                    completed.append(record.id)
                    continue
            try:
                self._install_record(record, workspace=workspace)
                self._verify_record(record, workspace=workspace)
                self._write_receipt(receipt, plan, record)
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
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return False
        return (
            payload.get("status") == "pass"
            and payload.get("plan_fingerprint") == plan.fingerprint
            and payload.get("record_fingerprint") == record.fingerprint()
        )

    @staticmethod
    def _write_receipt(
        path: Path, plan: DependencyPlan, record: DependencyRecord
    ) -> None:
        payload = {
            "schema": "agent-canon.devcontainer-dependency-receipt",
            "status": "pass",
            "record_id": record.id,
            "record_fingerprint": record.fingerprint(),
            "plan_fingerprint": plan.fingerprint,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
            temporary = Path(stream.name)
        os.replace(temporary, path)

    def _run(
        self,
        argv: Sequence[str],
        *,
        workspace: Path,
        privileged: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> None:
        kwargs: dict[str, object] = {
            "cwd": workspace,
            "privileged": privileged,
        }
        if env is not None:
            kwargs["env"] = env
        self.runner.run(argv, **kwargs)  # type: ignore[arg-type]

    def _pip_user_bin_dir(self) -> str:
        """Return the deterministic pip --user script directory for this interpreter."""
        site_result = self.runner.run(
            [sys.executable, "-c", "import site; print(site.getuserbase())"],
            capture_output=True,
        ).stdout.strip()
        if not site_result:
            raise DependencyError("failed to resolve python user site base")
        return f"{site_result}/bin"

    def _with_tool_paths(self, command_env: Mapping[str, str] | None) -> dict[str, str]:
        """Publish deterministic pip, Rust, and Lean tool paths."""
        pip_user_bin_dir = self._pip_user_bin_dir()
        merged: dict[str, str] = dict(os.environ)
        merged.update(command_env or {})
        home = Path(merged.get("HOME", str(Path.home())))
        cargo_home = merged.get("CARGO_HOME", str(home / ".cargo"))
        rustup_home = merged.get("RUSTUP_HOME", str(home / ".rustup"))
        elan_home = merged.get("ELAN_HOME", str(home / ".elan"))
        path_entries = list(filter(None, merged.get("PATH", "").split(os.pathsep)))
        tool_paths = (f"{cargo_home}/bin", f"{elan_home}/bin", pip_user_bin_dir)
        merged["CARGO_HOME"] = cargo_home
        merged["RUSTUP_HOME"] = rustup_home
        merged["ELAN_HOME"] = elan_home
        missing_tool_paths = [
            item for item in tool_paths if item not in path_entries
        ]
        merged["PATH"] = os.pathsep.join(
            [*missing_tool_paths, *path_entries]
        )
        return merged

    def _install_record(self, record: DependencyRecord, *, workspace: Path) -> None:
        method = record.method
        if method is Method.APT_PACKAGE:
            self._run(
                [
                    "apt-get",
                    "install",
                    "-y",
                    "--no-install-recommends",
                    "--no-remove",
                    f"{record.package}={record.version}",
                ],
                workspace=workspace,
                privileged=True,
            )
        elif method is Method.APT_REPOSITORY:
            self._install_apt_repository(record, workspace)
            self._run(
                [
                    "apt-get",
                    "install",
                    "-y",
                    "--no-install-recommends",
                    "--no-remove",
                    f"{record.package}={record.version}",
                ],
                workspace=workspace,
                privileged=True,
            )
        elif method is Method.NPM_GLOBAL:
            self._run(
                [
                    "npm",
                    "install",
                    "--global",
                    f"{record.package}@{record.version}",
                ],
                workspace=workspace,
                privileged=True,
            )
        elif method is Method.PIP_USER:
            self._run(
                [
                    "python3",
                    "-m",
                    "pip",
                    "install",
                    "--user",
                    f"{record.package}=={record.version}",
                ],
                workspace=workspace,
                env=self._with_tool_paths(None),
            )
        elif method is Method.RELEASE_ASSET:
            self._install_release_asset(record)
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
            source = (workspace / record.source).resolve()
            if not source.is_dir():
                projected = (workspace / "vendor" / "agent-canon" / record.source).resolve()
                if projected.is_dir():
                    source = projected
            if os.path.commonpath(
                (str(workspace.resolve()), str(source))
            ) != str(workspace.resolve()):
                raise DependencyError(f"{record.id}: cargo source escapes workspace")
            if not source.is_dir():
                raise DependencyError(f"{record.id}: cargo source is missing: {source}")
            assert record.commit is not None
            observed_commit = self.runner.run(
                ["git", "-C", str(source), "rev-parse", "HEAD"],
                cwd=workspace,
                capture_output=True,
            ).stdout.strip()
            if observed_commit and observed_commit != record.commit:
                raise DependencyError(
                    f"{record.id}: cargo source commit mismatch "
                    f"{observed_commit}!={record.commit}"
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
                env=self._with_tool_paths(None),
            )
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
                ["playwright", "install", "--with-deps", record.browser],
                workspace=workspace,
                privileged=True,
                env={"PLAYWRIGHT_BROWSERS_PATH": record.browser_cache_path},
            )
        else:  # pragma: no cover - Method is a closed enum.
            raise DependencyError(f"unsupported installation method: {method}")

    def _verify_record(
        self, record: DependencyRecord, *, workspace: Path
    ) -> None:
        """Verify that one record's installed tools are available now."""
        for command in record.commands:
            command_env = self._with_tool_paths(None)
            self._run(command, workspace=workspace, env=command_env)

    def _install_apt_repository(
        self, record: DependencyRecord, workspace: Path
    ) -> None:
        assert record.key_url is not None
        assert record.key_fingerprint is not None
        with tempfile.TemporaryDirectory(prefix=f"agent-canon-{record.id}-") as temporary:
            root = Path(temporary)
            raw_key = root / "key.raw"
            keyring = root / f"{record.id}.gpg"
            _download(record.key_url, raw_key)
            fingerprint = self.runner.run(
                ["gpg", "--show-keys", "--with-colons", str(raw_key)],
                cwd=workspace,
                capture_output=True,
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
                f"deb [signed-by={key_destination}] {record.source} stable main\n",
                encoding="utf-8",
            )
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

    def _install_release_asset(self, record: DependencyRecord) -> None:
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
        with tempfile.TemporaryDirectory(prefix=f"agent-canon-{record.id}-") as temporary:
            root = Path(temporary)
            archive = root / asset
            archive.parent.mkdir(parents=True, exist_ok=True)
            _download(source, archive)
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
                    raise DependencyError(f"{record.id}: extracted destination not found")
                candidate = matches[0]
            self._run_install_file(candidate, Path(record.destination))

    def _run_install_file(self, source: Path, destination: Path) -> None:
        self.runner.run(
            ["install", "-D", "-m", "0755", str(source), str(destination)],
            privileged=True,
        )


def _download(url: str, destination: Path) -> None:
    """Download a pinned HTTPS asset without invoking a shell command."""
    with urllib.request.urlopen(url) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _cli_plan(args: argparse.Namespace) -> DependencyPlan:
    workspace = Path(args.workspace).resolve()
    vendor_root = Path(args.vendor_root).resolve() if args.vendor_root else None
    return load_plan(workspace, vendor_root)


def build_parser() -> argparse.ArgumentParser:
    """Build the dependency model CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "dry-run", "install", "boundary"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--vendor-root")
    parser.add_argument("--receipts")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run validation, dry-run, or installation with typed failure output."""
    args = build_parser().parse_args(argv)
    exit_status = 0
    payload: dict[str, Any]
    try:
        if args.command == "boundary":
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
                "findings": [dataclasses.asdict(finding) for finding in report.findings],
            }
            exit_status = 0 if not report.findings else 1
        else:
            plan = _cli_plan(args)
            if args.command == "validate":
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
                completed = Installer().install(
                    plan, workspace=Path(args.workspace).resolve(), receipts=receipts
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
        print(f"DEVCONTAINER_DEPENDENCY_ERROR={exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"DEVCONTAINER_DEPENDENCY={payload.get('status', 'pass')}")
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
            print(
                "DEVCONTAINER_DEPENDENCY_COMPLETED="
                + ",".join(payload["completed"])
            )
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
