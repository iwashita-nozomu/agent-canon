#!/usr/bin/env python3
# @dependency-start
# @dependency-end

"""Run one repo program inside the repo-defined container runtime."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from container_runtime import (
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
from run_python_in_dockerfile import load_rules, resolve_rule


@dataclass(frozen=True)
class ProgramResolution:
    """Describe how one program should run in the container."""

    pack_path: str
    command: list[str]
    workdir: str | None


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Build one repo-defined container image, run one preflight environment check, "
            "then execute one Python file, shell script, workspace binary, or command."
        )
    )
    parser.add_argument(
        "--dockerfile",
        default="docker/Dockerfile",
        help="Dockerfile used for rule resolution. Default: docker/Dockerfile",
    )
    parser.add_argument(
        "--rules",
        default="docker/python-execution-rules.toml",
        help="Python execution rule file. Default: docker/python-execution-rules.toml",
    )
    parser.add_argument("--pack", help="Pack override. Skip rule resolution when set.")
    parser.add_argument(
        "--builder",
        default="auto",
        choices=("auto", "docker", "podman"),
        help="Container builder to use. Default: auto",
    )
    parser.add_argument("--skip-build", action="store_true", help="Skip the build step.")
    parser.add_argument("--keep-image", action="store_true", help="Keep the built image.")
    parser.add_argument("--print-only", action="store_true", help="Print commands without executing.")
    parser.add_argument(
        "--skip-env-check",
        action="store_true",
        help="Skip the preflight environment check inside the container.",
    )
    parser.add_argument("--workdir", help="Container workdir override.")
    parser.add_argument("--shell", help="Shell used for shell-script execution. Default: /bin/bash")
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
    parser.add_argument("program", help="Python file, shell script, workspace binary, or command.")
    parser.add_argument(
        "program_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the target program. Use -- to separate them.",
    )
    return parser


def cleanup_image(builder: str, image_tag: str) -> None:
    """Remove one image quietly."""
    subprocess.run([builder, "image", "rm", "-f", image_tag], check=False, capture_output=True)


def normalize_program_args(program_args: list[str]) -> list[str]:
    """Normalize the command tail."""
    normalized = list(program_args)
    if normalized and normalized[0] == "--":
        normalized = normalized[1:]
    return normalized


def workspace_relative(program_path: Path) -> str:
    """Return a workspace-relative path in POSIX form."""
    return program_path.relative_to(workspace_path(".")).as_posix()


def resolve_program(
    *,
    dockerfile: str,
    rules_path: str,
    pack_override: str | None,
    program: str,
    program_args: list[str],
    shell: str | None,
    workdir_override: str | None,
) -> ProgramResolution:
    """Resolve how one program should run."""
    workspace_root = workspace_path(".")
    program_candidate = workspace_root / program
    normalized_args = normalize_program_args(program_args)

    if program_candidate.exists() and program_candidate.is_file():
        relative_program = workspace_relative(program_candidate)
        container_program = f"/workspace/{relative_program}"

        if program_candidate.suffix == ".py":
            _, rules = load_rules(rules_path)
            resolved_rule = resolve_rule(
                dockerfile=dockerfile,
                python_file=program_candidate,
                rules=rules,
            )
            pack_path = pack_override or (
                resolved_rule.pack if resolved_rule is not None else "docker/packs/default.toml"
            )
            python_bin = resolved_rule.python_bin if resolved_rule is not None else "python3"
            workdir = workdir_override or (resolved_rule.workdir if resolved_rule is not None else None)
            return ProgramResolution(
                pack_path=pack_path,
                command=[python_bin, container_program, *normalized_args],
                workdir=workdir,
            )

        if program_candidate.suffix in {".sh", ".bash"}:
            return ProgramResolution(
                pack_path=pack_override or "docker/packs/default.toml",
                command=[shell or "/bin/bash", container_program, *normalized_args],
                workdir=workdir_override,
            )

        return ProgramResolution(
            pack_path=pack_override or "docker/packs/default.toml",
            command=[container_program, *normalized_args],
            workdir=workdir_override,
        )

    return ProgramResolution(
        pack_path=pack_override or "docker/packs/default.toml",
        command=[program, *normalized_args],
        workdir=workdir_override,
    )


def build_env_check_command() -> list[str]:
    """Return one lightweight preflight environment check command."""
    script = join_shell_lines(
        [
            "set -euo pipefail",
            "python3 --version",
            "python3 -m pip --version",
            "bash tools/docker_dependency_validator.sh",
            "if command -v cmake >/dev/null 2>&1; then cmake --version; fi",
            "if command -v ninja >/dev/null 2>&1; then ninja --version; fi",
            "if command -v docker >/dev/null 2>&1; then docker --version; fi",
        ]
    )
    return build_shell_invocation("/bin/bash", script)


def main() -> int:
    """Run the CLI."""
    try:
        args = build_parser().parse_args()
        resolution = resolve_program(
            dockerfile=args.dockerfile,
            rules_path=args.rules,
            pack_override=args.pack,
            program=args.program,
            program_args=list(args.program_args),
            shell=args.shell,
            workdir_override=args.workdir,
        )
        pack = apply_pack_overrides(
            load_or_default_pack(resolution.pack_path),
            dockerfile=args.dockerfile,
        )
        builder = resolve_builder(args.builder, print_only=args.print_only)
        build_command = build_build_command(builder, pack)
        print_label_and_command("build", build_command)

        env_check_command: list[str] | None = None
        if not args.skip_env_check:
            env_check_command = build_run_command(
                builder,
                pack,
                workspace_root=workspace_path("."),
                command=build_env_check_command(),
                env=tuple(args.env),
                mounts=tuple(args.mount),
            )
            print_label_and_command("env-check", env_check_command)

        run_command = build_run_command(
            builder,
            pack,
            workspace_root=workspace_path("."),
            command=resolution.command,
            env=tuple(args.env),
            mounts=tuple(args.mount),
            workdir=resolution.workdir,
        )
        print_label_and_command("run", run_command)

        if args.print_only:
            return 0

        image_built_here = False
        if not args.skip_build:
            build_result = subprocess.run(build_command, check=False)
            if build_result.returncode != 0:
                return build_result.returncode
            image_built_here = True

        try:
            if env_check_command is not None:
                env_check_result = subprocess.run(env_check_command, check=False)
                if env_check_result.returncode != 0:
                    return env_check_result.returncode
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
