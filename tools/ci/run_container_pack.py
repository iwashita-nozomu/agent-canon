#!/usr/bin/env python3
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
    join_shell_lines,
    load_or_default_pack,
    print_label_and_command,
    resolve_builder,
    workspace_path,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Build and smoke-test a container runtime pack.")
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
    parser.add_argument("--pull", action="store_true", help="Pull the latest base image.")
    parser.add_argument("--no-cache", action="store_true", help="Disable the build cache.")
    parser.add_argument("--skip-run", action="store_true", help="Skip the smoke test.")
    parser.add_argument("--keep-image", action="store_true", help="Keep the built image.")
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


def cleanup_image(builder: str, image_tag: str) -> None:
    """Remove one image quietly."""
    subprocess.run([builder, "image", "rm", "-f", image_tag], check=False, capture_output=True)


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

        build_command = build_build_command(builder, pack, pull=args.pull, no_cache=args.no_cache)
        print_label_and_command("build", build_command)
        if args.skip_run:
            if args.print_only:
                return 0
            build_result = subprocess.run(build_command, check=False)
            return build_result.returncode

        smoke_command = build_run_command(
            builder,
            pack,
            workspace_root=workspace_root,
            command=build_smoke_command(pack),
        )
        print_label_and_command("smoke", smoke_command)

        if args.print_only:
            return 0

        build_result = subprocess.run(build_command, check=False)
        if build_result.returncode != 0:
            return build_result.returncode

        try:
            smoke_result = subprocess.run(smoke_command, check=False)
            return smoke_result.returncode
        finally:
            if not args.keep_image:
                cleanup_image(builder, pack.image_tag)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
