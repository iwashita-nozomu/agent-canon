#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Reads the current checkout identity at bounded workflow boundaries.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md checkout identity readback
# downstream implementation ./manifest_rendering.py projects the identity contract into handoffs
# downstream implementation ./implementation_dispatch.py carries the observed identity to workers
# downstream implementation ../../tests/agent_tools/test_checkout_identity.py verifies branch, detached, and cwd transitions
# @dependency-end
"""Read one repository-qualified checkout identity without changing Git state.

The identity is deliberately observational.  It is a small read-only block for
workflow transitions, not an authorization token and not a branch/worktree
registry.  Unknown fields are represented explicitly so callers can decide
whether the operation they are about to perform requires a resolved identity.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

UNKNOWN = "unknown"
_SCPLIKE_REMOTE = re.compile(r"^[^/@:]+@[^:]+:(?P<path>.+)$")


@dataclass(frozen=True, slots=True)
class CheckoutIdentity:
    """The minimum checkout state carried by a workflow handoff."""

    cwd: str
    git_root: str
    branch: str
    head: str
    remote: str

    @property
    def remote_owner_repository(self) -> str:
        """Return the normalized remote owner/repository value."""
        return self.remote

    def as_dict(self) -> dict[str, str]:
        """Return the stable five-field projection used by handoffs."""
        return asdict(self)

    def render(self) -> str:
        """Render one compact, human-readable handoff block."""
        return "\n".join(
            (
                f"cwd={self.cwd}",
                f"git_root={self.git_root}",
                f"branch={self.branch}",
                f"head={self.head}",
                f"remote={self.remote}",
            )
        )


def _run_git(cwd: Path, *args: str) -> str | None:
    """Return stdout for one read-only Git query, or ``None`` on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def _normalize_remote_owner_repository(remote: str | None) -> str:
    """Extract a case-normalized ``owner/repository`` from a Git remote."""
    if not remote:
        return UNKNOWN
    value = remote.strip()
    match = _SCPLIKE_REMOTE.match(value)
    if match:
        path = match.group("path")
    else:
        parsed = urlsplit(value)
        if not parsed.hostname:
            return UNKNOWN
        path = parsed.path
    parts = [part for part in path.split("/") if part]
    if parts and parts[-1].casefold().endswith(".git"):
        parts[-1] = parts[-1][:-4]
    if len(parts) < 2 or not all(parts[-2:]):
        return UNKNOWN
    return "/".join(part.casefold() for part in parts[-2:])


def resolve_checkout_identity(cwd: Path | str = ".") -> CheckoutIdentity:
    """Read checkout identity from an absolute cwd using read-only Git calls."""
    absolute_cwd = Path(cwd).expanduser().resolve(strict=False)
    git_root_value = _run_git(absolute_cwd, "rev-parse", "--show-toplevel")
    if git_root_value is None:
        return CheckoutIdentity(
            cwd=str(absolute_cwd),
            git_root=UNKNOWN,
            branch=UNKNOWN,
            head=UNKNOWN,
            remote=UNKNOWN,
        )
    git_root = Path(git_root_value).resolve(strict=False)
    branch = _run_git(git_root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = _run_git(git_root, "rev-parse", "--verify", "HEAD")
    remote = _run_git(git_root, "remote", "get-url", "origin")
    return CheckoutIdentity(
        cwd=str(absolute_cwd),
        git_root=str(git_root),
        branch=branch or "detached",
        head=head or UNKNOWN,
        remote=_normalize_remote_owner_repository(remote),
    )


# Short alias for callers that name the operation as a read rather than a resolve.
read_checkout_identity = resolve_checkout_identity


def main(argv: list[str] | None = None) -> int:
    """Print the identity as JSON or a line-oriented block."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=".", help="Directory whose checkout is inspected.")
    parser.add_argument("--format", choices=("json", "lines"), default="lines")
    args = parser.parse_args(argv)
    identity = resolve_checkout_identity(args.cwd)
    if args.format == "json":
        print(json.dumps(identity.as_dict(), ensure_ascii=False, sort_keys=True))
    else:
        print(identity.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
