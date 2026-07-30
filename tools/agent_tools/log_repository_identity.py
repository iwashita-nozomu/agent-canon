#!/usr/bin/env python3
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
    if normalized_path.endswith(".git"):
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
    """Return stable identity without consulting the filesystem path."""
    override = os.environ.get(STABLE_ID_ENV, "").strip()
    if override:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,95}", override):
            raise SourceRepositoryIdentityError("source_repository_id_invalid")
        return override
    return stable_source_repository_id(source_remote(root))


def stable_source_id_from_runtime_env(root: Path | None = None) -> str:
    """Return a hot-path identity without starting Git or using the network."""
    override = os.environ.get(STABLE_ID_ENV, "").strip()
    if override:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,95}", override):
            raise SourceRepositoryIdentityError("source_repository_id_invalid")
        return override
    remote = os.environ.get(SOURCE_REMOTE_ENV, "").strip()
    if remote:
        return stable_source_repository_id(remote)
    if root is not None:
        remote_name = os.environ.get(SOURCE_REMOTE_NAME_ENV, "origin").strip() or "origin"
        remote = _remote_from_git_config(root, remote_name)
        if remote:
            return stable_source_repository_id(remote)
    return "unidentified-source"


def stable_log_branch(root: Path) -> str:
    """Return the only permitted source runtime branch."""
    return f"logs/{stable_source_id(root)}"
