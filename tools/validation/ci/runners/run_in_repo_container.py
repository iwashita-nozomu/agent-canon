#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs in repo container CI automation.
# upstream design ../../../README.md shared automation index
# @dependency-end

"""Build one repo-defined container pack and run a command inside it."""

from __future__ import annotations

import argparse
import subprocess
import sys

from tools.validation.ci.runners.container_runtime import (
    apply_pack_overrides,
    build_build_command,
    build_run_command,
    load_or_default_pack,
    print_label_and_command,
    resolve_builder,
    should_build_image,
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
    parser.add_argument("--tag", help="Image tag override for the selected runtime pack.")
    parser.add_argument(
        "--pull", action="store_true", help="Pull the latest base image."
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Disable the build cache."
    )
    parser.add_argument(
        "--build-only", action="store_true", help="Build the image and exit."
    )
    parser.add_argument(
        "--skip-build", action="store_true", help="Skip the build step."
    )
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
        help=(
            "Container mount point for the host workspace. Default: pack runtime value"
        ),
    )
    parser.add_argument("--workdir", help="Container working directory override.")
    parser.add_argument(
        "--shell", help="Shell override when opening an interactive session."
    )
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
    parser.add_argument(
        "--port",
        action="append",
        default=[],
        metavar="HOST:CONTAINER",
        help="Publish a container port. Repeatable. Example: --port 8888:8888.",
    )
    parser.add_argument("--gpus", help="GPU setting override, for example 'all'.")
    parser.add_argument("--user", help="User override passed to docker run --user.")
    parser.add_argument(
        "--tty", action="store_true", help="Allocate a TTY for docker run."
    )
    parser.add_argument(
        "--shell-session",
        action="store_true",
        help="Open the configured shell instead of running a command.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help=(
            "Command to run inside the container. Use -- to separate tool args "
            "from the command."
        ),
    )
    return parser


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
        workspace_root = workspace_path(args.workspace_root)
        pack = apply_pack_overrides(
            load_or_default_pack(args.pack, workspace_root=workspace_root),
            dockerfile=args.dockerfile,
            context=args.context,
            target=args.target,
            tag=args.tag,
        )
        builder = resolve_builder(args.builder, print_only=args.print_only)
        command = normalize_command(args.command, shell_session=args.shell_session)
        shell = args.shell or pack.runtime.shell
        run_payload = command if command else [shell]

        build_requested = should_build_image(
            builder,
            pack.image_tag,
            workspace_root=workspace_root,
            skip_build=args.skip_build,
            force_build=args.build_only or args.pull or args.no_cache,
            print_only=args.print_only,
        )

        build_command = build_build_command(
            builder,
            pack,
            workspace_root=workspace_root,
            pull=args.pull,
            no_cache=args.no_cache,
        )
        run_command = build_run_command(
            builder,
            pack,
            workspace_root=workspace_root,
            command=run_payload,
            shell=args.shell,
            workdir=args.workdir,
            container_workspace=args.container_workspace,
            env=tuple(args.env),
            mounts=tuple(args.mount),
            ports=tuple(args.port),
            gpus=args.gpus,
            user=args.user,
            tty=args.tty,
        )

        print_label_and_command("build", build_command)
        if not args.build_only:
            print_label_and_command("run", run_command)

        if args.print_only:
            return 0

        command_exit = 0
        if build_requested:
            command_exit = subprocess.run(build_command, check=False).returncode
        if command_exit == 0 and not args.build_only:
            command_exit = subprocess.run(run_command, check=False).returncode
        return command_exit
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
