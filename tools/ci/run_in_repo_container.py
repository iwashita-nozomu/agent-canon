#!/usr/bin/env python3
# @dependency-start
# responsibility Runs in repo container CI automation.
# upstream design ../README.md shared automation index
# @dependency-end

"""Build one repo-defined container pack and run a command inside it."""

from __future__ import annotations

import argparse
import subprocess
import sys

from container_runtime import (
    apply_pack_overrides,
    build_build_command,
    build_run_command,
    load_or_default_pack,
    print_label_and_command,
    resolve_builder,
    workspace_path,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Build one repo-defined container pack and run a command inside "
            "a workspace-mounted container."
        )
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
    parser.add_argument("--pull", action="store_true", help="Pull the latest base image.")
    parser.add_argument("--no-cache", action="store_true", help="Disable the build cache.")
    parser.add_argument("--build-only", action="store_true", help="Build the image and exit.")
    parser.add_argument("--skip-build", action="store_true", help="Skip the build step.")
    parser.add_argument("--keep-image", action="store_true", help="Keep the built image.")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the resolved commands without executing them.",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Host workspace path to mount. Default: repo root",
    )
    parser.add_argument(
        "--container-workspace",
        help="Container mount point for the host workspace. Default: pack runtime value",
    )
    parser.add_argument("--workdir", help="Container working directory override.")
    parser.add_argument("--shell", help="Shell override when opening an interactive session.")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional environment variable for docker run. Repeatable.",
    )
    parser.add_argument(
        "--mount",
        action="append",
        default=[],
        metavar="SRC:DST[:MODE]",
        help="Additional bind mount for docker run. Repeatable.",
    )
    parser.add_argument("--gpus", help="GPU setting override, for example 'all'.")
    parser.add_argument("--user", help="User override passed to docker run --user.")
    parser.add_argument("--tty", action="store_true", help="Allocate a TTY for docker run.")
    parser.add_argument(
        "--shell-session",
        action="store_true",
        help="Open the configured shell instead of running a command.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run inside the container. Use -- to separate tool args from the command.",
    )
    return parser


def cleanup_image(builder: str, image_tag: str) -> None:
    """Remove one image quietly."""
    subprocess.run([builder, "image", "rm", "-f", image_tag], check=False, capture_output=True)


def normalize_command(command: list[str], shell_session: bool) -> list[str]:
    """Normalize the user command tail."""
    normalized = list(command)
    if normalized and normalized[0] == "--":
        normalized = normalized[1:]
    if shell_session:
        return []
    return normalized


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
        command = normalize_command(args.command, shell_session=args.shell_session)

        build_command = build_build_command(builder, pack, pull=args.pull, no_cache=args.no_cache)
        run_command = build_run_command(
            builder,
            pack,
            workspace_root=workspace_root,
            command=command if command else [args.shell or pack.runtime.shell],
            shell=args.shell,
            workdir=args.workdir,
            container_workspace=args.container_workspace,
            env=tuple(args.env),
            mounts=tuple(args.mount),
            gpus=args.gpus,
            user=args.user,
            tty=args.tty,
        )

        print_label_and_command("build", build_command)
        if not args.build_only:
            print_label_and_command("run", run_command)

        if args.print_only:
            return 0

        image_built_here = False
        if not args.skip_build:
            build_result = subprocess.run(build_command, check=False)
            if build_result.returncode != 0:
                return build_result.returncode
            image_built_here = True

        if args.build_only:
            return 0

        try:
            run_result = subprocess.run(run_command, check=False)
            return run_result.returncode
        finally:
            if image_built_here and not args.keep_image:
                cleanup_image(builder, pack.image_tag)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
