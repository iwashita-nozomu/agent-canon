#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs container pack CI automation.
# upstream design ../../../README.md shared automation index
# @dependency-end

"""Build and smoke-test a container runtime pack."""

from __future__ import annotations

import argparse
import subprocess
import sys

from tools.validation.ci.runners.container_runtime import (
    ContainerPack,
    apply_pack_overrides,
    build_build_command,
    build_run_command,
    build_shell_invocation,
    join_shell_lines,
    load_or_default_pack,
    print_label_and_command,
    resolve_builder,
    should_build_image,
    workspace_path,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Build and smoke-test a container runtime pack."
    )
    parser.add_argument("--pack", help="Path to a TOML runtime pack definition.")
    parser.add_argument(
        "--builder",
        default="auto",
        choices=("auto", "docker", "podman"),
        help="Container builder to use. Default: auto",
    )
    parser.add_argument("--dockerfile", help="Dockerfile path override.")
    parser.add_argument("--context", help="Build context override.")
    parser.add_argument("--target", help="Build target override.")
    parser.add_argument("--tag", help="Image tag override for the selected runtime pack.")
    parser.add_argument(
        "--pull", action="store_true", help="Pull the latest base image."
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Disable the build cache."
    )
    parser.add_argument("--skip-run", action="store_true", help="Skip the smoke test.")
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root to mount during the smoke test. Default: current repo root",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the resolved commands without executing them.",
    )
    return parser


def build_smoke_command(pack: ContainerPack) -> list[str]:
    """Return the smoke-test command for one pack."""
    script = join_shell_lines(["set -euo pipefail", *pack.smoke.commands])
    return build_shell_invocation(pack.smoke.shell, script)


def main() -> int:
    """Run the CLI."""
    try:
        args = build_parser().parse_args()
        workspace_root = workspace_path(args.workspace_root)
        pack = apply_pack_overrides(
            load_or_default_pack(args.pack, workspace_root=workspace_root),
            dockerfile=args.dockerfile,
            context=args.context,
            target=args.target,
            tag=args.tag,
        )
        builder = resolve_builder(args.builder, print_only=args.print_only)
        # This entrypoint is the explicit pack build/update route.  It keeps
        # the configured stable tag and uses the builder's normal cache.
        build_requested = should_build_image(
            builder,
            pack.image_tag,
            workspace_root=workspace_root,
            force_build=True,
            print_only=args.print_only,
        )

        build_command = build_build_command(
            builder,
            pack,
            workspace_root=workspace_root,
            pull=args.pull,
            no_cache=args.no_cache,
        )
        print_label_and_command("build", build_command)
        smoke_command = build_run_command(
            builder,
            pack,
            workspace_root=workspace_root,
            command=build_smoke_command(pack),
        )
        print_label_and_command("smoke", smoke_command)

        if args.print_only:
            return 0

        command_exit = 0
        if build_requested:
            command_exit = subprocess.run(build_command, check=False).returncode
        if command_exit == 0 and not args.skip_run:
            command_exit = subprocess.run(smoke_command, check=False).returncode
        return command_exit
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
