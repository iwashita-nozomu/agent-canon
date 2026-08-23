#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs container pack CI automation.
# upstream design ../README.md shared automation index
# @dependency-end

"""Build and smoke-test a container runtime pack."""

from __future__ import annotations

import argparse
import subprocess
import sys

from container_runtime import (
    ContainerPack,
    apply_pack_overrides,
    build_build_command,
    build_run_command,
    build_shell_invocation,
    emit_not_created_lifecycle_receipt,
    join_shell_lines,
    lifecycle_context,
    load_or_default_pack,
    print_label_and_command,
    resolve_builder,
    scope_pack_image_tag,
    start_container_lifecycle,
    workspace_path,
    write_lifecycle_receipt,
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
    parser.add_argument("--tag", help="Temporary image tag override.")
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
        pack = apply_pack_overrides(
            load_or_default_pack(args.pack),
            dockerfile=args.dockerfile,
            context=args.context,
            target=args.target,
            tag=args.tag,
        )
        builder = resolve_builder(args.builder, print_only=args.print_only)
        workspace_root = workspace_path(args.workspace_root)
        lifecycle = lifecycle_context(workspace_root, builder, "container-pack")
        pack = scope_pack_image_tag(pack, lifecycle)
        lifecycle = lifecycle.bind_image_tag(pack.image_tag)

        build_command = build_build_command(
            builder,
            pack,
            pull=args.pull,
            no_cache=args.no_cache,
            labels=lifecycle.labels(),
        )
        print_label_and_command("build", build_command)
        smoke_command = build_run_command(
            builder,
            pack,
            workspace_root=workspace_root,
            command=build_smoke_command(pack),
            labels=lifecycle.labels(),
        )
        print_label_and_command("smoke", smoke_command)

        if args.print_only:
            emit_not_created_lifecycle_receipt(workspace_root, lifecycle)
            return 0

        lifecycle_run = start_container_lifecycle(
            workspace_root, builder, "container-pack", context=lifecycle
        )
        if lifecycle_run.receipt.state != "snapshot":
            write_lifecycle_receipt(workspace_root, lifecycle_run.receipt)
            print(
                f"container lifecycle unavailable: {lifecycle_run.receipt.failure or lifecycle_run.receipt.before.query_status}",
                file=sys.stderr,
            )
            return 2

        command_exit = 0
        try:
            command_exit = subprocess.run(build_command, check=False).returncode
            if command_exit == 0 and not args.skip_run:
                command_exit = subprocess.run(smoke_command, check=False).returncode
        finally:
            cleanup_result = lifecycle_run.finish(cleanup=True)
        if cleanup_result.state not in {"cleaned", "not-created"}:
            print(
                f"container lifecycle cleanup state={cleanup_result.state}: {cleanup_result.failure}",
                file=sys.stderr,
            )
            if command_exit == 0:
                command_exit = 2
        return command_exit
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
