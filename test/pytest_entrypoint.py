#!/usr/bin/env python3
# @dependency-start
# contract test
# responsibility Starts pytest with the physical AgentCanon source import roots and scrubbed child state.
# upstream implementation ./testrunner.sh owns lifecycle receipts and record environment isolation
# downstream implementation ../tests/tools/test_testrunner.py verifies the entrypoint contract
# @dependency-end

"""Start pytest from the physical source root without inherited repository state."""

from __future__ import annotations

import os
import site
import sys
import sysconfig
from collections.abc import Mapping, MutableMapping
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ORIGINS = (
    SOURCE_ROOT,
    SOURCE_ROOT / "tools",
    SOURCE_ROOT / "tools" / "agent_tools",
)
SCRUB_ENVIRONMENT_KEYS = (
    "PYTHONPATH",
    "AGENT_CANON_PARENT_ROOT",
    "AGENT_CANON_PARENT_ROOT_DEV",
    "AGENT_CANON_PARENT_ROOT_INO",
    "AGENT_CANON_ACTIVE_REPOSITORY_ROOT",
    "AGENT_CANON_SOURCE_ROOT",
    "AGENT_CANON_ROOT",
    "AGENT_CANON_CHILD_HANDOFF",
    "AGENT_CANON_CHILD_PURPOSE",
    "AGENT_CANON_HANDOFF_AUDIENCE",
    "AGENT_CANON_FIXTURE_ROLE",
    "AGENT_CANON_DATA_REPOSITORY_ROOT",
    "AGENT_CANON_DATA_REPOSITORY_DEV",
    "AGENT_CANON_DATA_REPOSITORY_INO",
    "AGENT_CANON_DATA_SOURCE_ROOT",
    "AGENT_CANON_DATA_ROOT",
)
RUNNER_OWNED_AMBIENT_KEYS = (
    "AGENT_CANON_TOOLS_HOME",
    "CARGO_HOME",
    "CARGO_TARGET_DIR",
    "AGENT_CANON_CLI_TARGET_DIR",
    "XDG_CACHE_HOME",
    "PYTHONPYCACHEPREFIX",
)


def scrub_runner_owned_environment(
    *, runner_ambient_env: Mapping[str, str]
) -> dict[str, str]:
    """Remove only runner-owned cache/tool paths from inherited ambient state."""
    return {
        key: value
        for key, value in runner_ambient_env.items()
        if key not in RUNNER_OWNED_AMBIENT_KEYS
    }


def _interpreter_origins() -> tuple[Path, ...]:
    """Return physical stdlib/site-package roots owned by this interpreter."""
    candidates: list[str] = []
    paths = sysconfig.get_paths()
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        value = paths.get(key)
        if value is not None:
            candidates.append(value)
    try:
        candidates.extend(site.getsitepackages())
    except (AttributeError, TypeError):
        pass
    try:
        candidates.append(site.getusersitepackages())
    except (AttributeError, TypeError):
        pass
    roots: list[Path] = []
    for candidate in candidates:
        physical = _physical(candidate)
        if physical is not None and physical not in roots:
            roots.append(physical)
    return tuple(roots)


def _physical(value: str) -> Path | None:
    """Resolve one import entry without turning malformed entries into roots."""
    try:
        return Path(value or os.curdir).resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _is_repository_origin(entry: str) -> bool:
    """Return whether a path belongs to any repository rather than Python."""
    physical = _physical(entry)
    if physical is None:
        return False
    if any(physical == root or root in physical.parents for root in _interpreter_origins()):
        return False
    current = physical if physical.is_dir() else physical.parent
    while current != current.parent:
        if (current / ".git").exists():
            return True
        current = current.parent
    return False


def _is_interpreter_origin(entry: str) -> bool:
    """Return whether a path is one of this interpreter's import roots."""
    physical = _physical(entry)
    if physical is None:
        return False
    if any(physical == root or root in physical.parents for root in _interpreter_origins()):
        return True
    # Debian-style installations expose dist-packages outside sysconfig's
    # prefix roots; retain those interpreter-managed site directories too.
    return any(part in {"site-packages", "dist-packages"} for part in physical.parts)


def configure_import_environment(
    environment: MutableMapping[str, str] = os.environ,
) -> None:
    """Keep interpreter paths and install only the exact repository origins."""
    preserved = [
        entry
        for entry in sys.path
        if _is_interpreter_origin(entry) and not _is_repository_origin(entry)
    ]
    repository_origins = tuple(str(path) for path in REPOSITORY_ORIGINS)
    sys.path[:] = [*preserved, *repository_origins]
    if tuple(sys.path[-len(repository_origins):]) != repository_origins:
        raise RuntimeError("pytest repository import suffix is not canonical")
    from tools.agent_tools.parent_root_side_effects import (
        PRIVATE_RECORD_TRANSPORT_ENV_NAMES,
    )

    private_transport_keys = tuple(
        str(key) for key in PRIVATE_RECORD_TRANSPORT_ENV_NAMES
    )
    if any(key in SCRUB_ENVIRONMENT_KEYS for key in private_transport_keys):
        raise RuntimeError("private record transport must remain at the adapter boundary")
    for key in SCRUB_ENVIRONMENT_KEYS:
        environment.pop(key, None)
    scrubbed = scrub_runner_owned_environment(runner_ambient_env=environment)
    environment.clear()
    environment.update(scrubbed)


def main(argv: list[str] | None = None) -> int:
    """Scrub inherited state before importing pytest and delegate its argv."""
    configure_import_environment()
    import pytest

    return int(pytest.main(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
