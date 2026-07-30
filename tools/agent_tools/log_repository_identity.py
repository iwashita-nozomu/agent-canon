#!/usr/bin/env python3
# @dependency-start
# contract implementation
# responsibility Resolves stable source-repository identities for runtime log branches.
# upstream design ../../documents/runtime/runtime-log-archive.md stable source identity and branch contract
# downstream implementation ./runtime_log_paths.py derives runtime archive paths from stable identity
# downstream implementation ./runtime_log_archive_git.py publishes archive data through runtime paths
# downstream implementation ../../tests/agent_tools/test_log_repository_lifecycle.py verifies identity lifecycle behavior
# @dependency-end
"""Thin AgentCanon adapter for the agent-canon-log stable-branch protocol."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

SOURCE_REMOTE_ENV = "AGENT_CANON_SOURCE_REPOSITORY_REMOTE"
SOURCE_REMOTE_NAME_ENV = "AGENT_CANON_SOURCE_REPOSITORY_REMOTE_NAME"
STABLE_ID_ENV = "AGENT_CANON_SOURCE_REPOSITORY_ID"
STABLE_ID_LENGTH = 96


class SourceRepositoryIdentityError(ValueError):
    """Raised when a stable source identity cannot be resolved."""

    code = "source_repository_identity_unavailable"


def normalize_remote(remote: str) -> str:
    """Apply the agent-canon-log v1 network remote normalization protocol."""
    value = remote.strip()
    if not value or value.startswith(("/", ".", "file:")):
        raise SourceRepositoryIdentityError("source_remote_must_be_network_identity")
    if re.match(r"^[^/@:]+@[^:]+:.+$", value):
        user_host, path = value.split(":", 1)
        host = user_host.rsplit("@", 1)[-1]
    else:
        parsed = urlsplit(value)
        if not parsed.hostname:
            raise SourceRepositoryIdentityError("source_remote_invalid")
        host = parsed.hostname
        path = parsed.path
    normalized_path = "/".join(part for part in path.split("/") if part)
    if normalized_path.casefold().endswith(".git"):
        normalized_path = normalized_path[:-4]
    normalized_path = normalized_path.strip("/")
    if not normalized_path:
        raise SourceRepositoryIdentityError("source_remote_missing_repository")
    return f"{host.casefold().rstrip('.')}/{normalized_path.casefold()}"


def stable_source_repository_id(remote: str) -> str:
    """Return the stable source ID defined by the log repository policy."""
    identity = normalize_remote(remote)
    readable = re.sub(r"[^a-z0-9.-]+", "-", identity).strip("-.")
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    prefix = readable[: max(1, STABLE_ID_LENGTH - len(digest) - 1)].rstrip("-.")
    return f"{prefix}-{digest}"


def _validated_override(value: str) -> str:
    """Validate the explicit id syntax before comparing it with Git provenance."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,95}", value):
        raise SourceRepositoryIdentityError("source_repository_id_invalid")
    return value


def _identity_from_remote(remote: str, override: str = "") -> str:
    """Resolve one identity only after the remote/override relationship is proven."""
    derived = stable_source_repository_id(remote)
    if not override:
        return derived
    validated = _validated_override(override)
    if validated != derived:
        raise SourceRepositoryIdentityError("source_repository_id_mismatch")
    return validated


def source_remote(root: Path) -> str:
    """Read the source remote, with an explicit remote override for adapters."""
    override = os.environ.get(SOURCE_REMOTE_ENV, "").strip()
    if override:
        return override
    remote_name = os.environ.get(SOURCE_REMOTE_NAME_ENV, "origin").strip() or "origin"
    result = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", remote_name],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise SourceRepositoryIdentityError("source_remote_required")
    return result.stdout.strip()


def _remote_from_git_config(root: Path, remote_name: str = "origin") -> str:
    """Read one remote from Git config without starting Git on hook hot paths."""
    git_entry = root.resolve() / ".git"
    if git_entry.is_file():
        marker = git_entry.read_text(encoding="utf-8").strip()
        prefix = "gitdir:"
        if not marker.casefold().startswith(prefix):
            return ""
        git_dir = (git_entry.parent / marker[len(prefix) :].strip()).resolve()
    else:
        git_dir = git_entry
    config = git_dir / "config"
    if not config.is_file():
        return ""
    section = f'[remote "{remote_name}"]'
    in_remote = False
    for raw_line in config.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("["):
            in_remote = line.casefold() == section.casefold()
            continue
        if in_remote and "=" in line:
            key, value = line.split("=", 1)
            if key.strip().casefold() == "url":
                return value.strip()
    return ""


def stable_source_id(root: Path) -> str:
    """Return a write-authorized identity proven by the source repository remote."""
    return source_repository_id_for_write(root)


def source_repository_id_for_write(root: Path) -> str:
    """Resolve the source id required before any archive publication begins."""
    remote = source_remote(root)
    override = os.environ.get(STABLE_ID_ENV, "").strip()
    return _identity_from_remote(remote, override)


def stable_source_id_from_runtime_env(root: Path | None = None) -> str:
    """Return a hot-path identity without starting Git or using the network."""
    remote = os.environ.get(SOURCE_REMOTE_ENV, "").strip()
    if not remote and root is not None:
        remote_name = os.environ.get(SOURCE_REMOTE_NAME_ENV, "origin").strip() or "origin"
        remote = _remote_from_git_config(root, remote_name)
    if remote:
        override = os.environ.get(STABLE_ID_ENV, "").strip()
        return _identity_from_remote(remote, override)
    return "unidentified-source"


def stable_log_branch(root: Path) -> str:
    """Return the only permitted source runtime branch."""
    return f"logs/{stable_source_id(root)}"
