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
    emit_not_created_lifecycle_receipt,
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
        pack = apply_pack_overrides(
            load_or_default_pack(args.pack),
            dockerfile=args.dockerfile,
            context=args.context,
            target=args.target,
            tag=args.tag,
        )
        builder = resolve_builder(args.builder, print_only=args.print_only)
        workspace_root = workspace_path(args.workspace_root)
        lifecycle = lifecycle_context(workspace_root, builder, "repo-container")
        if not args.skip_build:
            pack = scope_pack_image_tag(pack, lifecycle)
        lifecycle = lifecycle.bind_image_tag(pack.image_tag)
        command = normalize_command(args.command, shell_session=args.shell_session)
        shell = args.shell or pack.runtime.shell
        run_payload = command if command else [shell]

        build_command = build_build_command(
            builder,
            pack,
            pull=args.pull,
            no_cache=args.no_cache,
            labels=lifecycle.labels(),
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
            labels=lifecycle.labels(),
        )

        print_label_and_command("build", build_command)
        if not args.build_only:
            print_label_and_command("run", run_command)

        if args.print_only:
            emit_not_created_lifecycle_receipt(workspace_root, lifecycle)
            return 0

        lifecycle_run = start_container_lifecycle(
            workspace_root, builder, "repo-container", context=lifecycle
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
            if not args.skip_build:
                command_exit = subprocess.run(build_command, check=False).returncode
            if command_exit == 0 and not args.build_only:
                command_exit = subprocess.run(run_command, check=False).returncode
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
