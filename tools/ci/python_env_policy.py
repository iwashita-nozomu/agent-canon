#!/usr/bin/env python3
# @dependency-start
# @dependency-end

"""Report the repo-local Python environment policy and optionally create `.venv`."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import venv
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
        description="Report whether the current runtime may use a repo-local .venv."
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
        help="Create the canonical .venv when the current runtime policy allows it.",
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
    if os.environ.get("container") or os.environ.get("DEVCONTAINER_RUNTIME_MODE"):
        return "container"
    return "host"


def resolve_policy(runtime_env: str) -> EnvPolicy:
    """Resolve the repo-local venv policy for the runtime."""
    if runtime_env == "container":
        return EnvPolicy(
            runtime_env="container",
            venv_policy="allow",
            reason="container runtime detected; canonical .venv is allowed here",
            next_step="run --create to prepare .venv or use the image-installed Python directly",
        )
    return EnvPolicy(
        runtime_env="host",
        venv_policy="forbid",
        reason="host runtime detected; canonical flow uses container Python instead of repo-local .venv",
        next_step="run inside the canonical container or devcontainer instead of creating host .venv",
    )


def render_create_command(python_bin: str, venv_path: Path) -> str:
    """Render the canonical create command."""
    return " ".join(
        shlex.quote(part)
        for part in (python_bin, "-m", "venv", "--without-pip", "--system-site-packages", str(venv_path))
    )


def create_venv(python_bin: str, venv_path: Path) -> str:
    """Create or reuse the canonical .venv."""
    del python_bin  # The current interpreter already owns the running stdlib venv builder.
    if venv_path.exists():
        return "reuse_existing"
    venv_path.parent.mkdir(parents=True, exist_ok=True)
    venv.EnvBuilder(system_site_packages=True, with_pip=False).create(venv_path)
    return "created"


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
        print_status(policy, venv_path, create_command, "blocked_host_runtime")
        return 2

    action = "not_requested"
    if args.create:
        action = create_venv(args.python_bin, venv_path)
    print_status(policy, venv_path, create_command, action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
