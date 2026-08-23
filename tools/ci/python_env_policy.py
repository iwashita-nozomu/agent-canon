#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides python env policy CI automation.
# upstream design ../README.md shared automation index
# @dependency-end

"""Report the Python policy for the shared AgentCanon tool runtime."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EnvPolicy:
    """Machine-readable environment policy."""

    runtime_env: str
    venv_policy: str
    reason: str
    next_step: str


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Report whether the current runtime may create a repo-local .venv."
    )
    parser.add_argument(
        "--runtime",
        choices=("auto", "host", "container"),
        default="auto",
        help="Override runtime detection for deterministic checks. Default: auto",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root that would own the canonical .venv. Default: current directory",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Compatibility flag; shared AgentCanon runtime never creates a task .venv.",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter used for venv creation. Default: current interpreter",
    )
    return parser


def detect_runtime_env(runtime: str) -> str:
    """Return the effective runtime kind."""
    if runtime != "auto":
        return runtime
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        return "container"
    if os.environ.get("container"):
        return "container"
    return "host"


def resolve_policy(runtime_env: str) -> EnvPolicy:
    """Resolve policy without creating a second mutable tool environment."""
    return EnvPolicy(
        runtime_env=runtime_env,
        venv_policy="forbid",
        reason="shared AgentCanon Python is image-owned; task-local .venv is forbidden",
        next_step="start the shared tool runtime with bootstrap.sh and use its image Python",
    )


def render_create_command(python_bin: str, venv_path: Path) -> str:
    """Render the canonical create command."""
    return " ".join(
        shlex.quote(part)
        for part in (python_bin, "-m", "venv", "--without-pip", "--system-site-packages", str(venv_path))
    )


def print_status(
    policy: EnvPolicy,
    venv_path: Path,
    create_command: str,
    action: str,
) -> None:
    """Emit machine-readable status lines."""
    print(f"RUNTIME_ENV={policy.runtime_env}")
    print(f"REPO_LOCAL_VENV_POLICY={policy.venv_policy}")
    print(f"REPO_LOCAL_VENV_REASON={policy.reason}")
    print(f"REPO_LOCAL_VENV_PATH={venv_path}")
    print(f"REPO_LOCAL_VENV_EXISTS={'yes' if venv_path.exists() else 'no'}")
    print(f"REPO_LOCAL_VENV_CREATE_COMMAND={create_command}")
    print(f"REPO_LOCAL_VENV_ACTION={action}")
    print(f"REPO_LOCAL_VENV_NEXT={policy.next_step}")


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    venv_path = workspace_root / ".venv"
    runtime_env = detect_runtime_env(args.runtime)
    policy = resolve_policy(runtime_env)
    create_command = render_create_command(args.python_bin, venv_path)

    if args.create and policy.venv_policy != "allow":
        print_status(policy, venv_path, create_command, "blocked_shared_runtime_policy")
        return 2

    action = "not_requested"
    if args.create:
        action = "blocked_shared_runtime_policy"
    print_status(policy, venv_path, create_command, action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
