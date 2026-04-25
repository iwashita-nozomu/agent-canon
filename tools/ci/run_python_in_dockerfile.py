#!/usr/bin/env python3
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

"""Run one Python file inside the repo-defined Docker runtime."""

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
    load_or_default_pack,
    load_toml,
    print_label_and_command,
    resolve_builder,
    workspace_path,
)


@dataclass(frozen=True)
class PythonExecutionRule:
    """Describe one rule for mapping a Python file to a runtime pack."""

    name: str
    dockerfile: str
    match_roots: tuple[str, ...]
    pack: str
    python_bin: str
    workdir: str | None


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Run one Python file inside the repo Docker runtime.")
    parser.add_argument("dockerfile", help="Dockerfile path used for rule resolution.")
    parser.add_argument("python_file", help="Python file to run inside the container.")
    parser.add_argument(
        "--rules",
        default="docker/python-execution-rules.toml",
        help="Rule file. Default: docker/python-execution-rules.toml",
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
        "python_args",
        nargs="*",
        help="Arguments passed to the Python file. Use -- to separate them.",
    )
    return parser


def load_rules(path_like: str) -> tuple[str, list[PythonExecutionRule]]:
    """Load rule definitions."""
    data = load_toml(path_like)
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("docker/python-execution-rules.toml: [defaults] must be a table")
    default_pack = defaults.get("default_pack", "docker/packs/default.toml")
    if not isinstance(default_pack, str):
        raise ValueError("docker/python-execution-rules.toml: [defaults].default_pack must be a string")

    raw_rules = data.get("rule", [])
    if not isinstance(raw_rules, list):
        raise ValueError("docker/python-execution-rules.toml: [[rule]] entries must form a list")

    rules: list[PythonExecutionRule] = []
    for index, raw_rule in enumerate(raw_rules, start=1):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"docker/python-execution-rules.toml: rule #{index} must be a table")
        match_roots = raw_rule.get("match_roots", [])
        if not isinstance(match_roots, list) or not all(isinstance(item, str) for item in match_roots):
            raise ValueError(f"docker/python-execution-rules.toml: rule #{index} match_roots must be strings")
        workdir = raw_rule.get("workdir")
        if workdir is not None and not isinstance(workdir, str):
            raise ValueError(f"docker/python-execution-rules.toml: rule #{index} workdir must be a string")
        rules.append(
            PythonExecutionRule(
                name=str(raw_rule.get("name", f"rule-{index}")),
                dockerfile=str(raw_rule.get("dockerfile", "")),
                match_roots=tuple(match_roots),
                pack=str(raw_rule.get("pack", default_pack)),
                python_bin=str(raw_rule.get("python_bin", "python3")),
                workdir=workdir,
            )
        )
    return default_pack, rules


def resolve_rule(
    *,
    dockerfile: str,
    python_file: Path,
    rules: list[PythonExecutionRule],
) -> PythonExecutionRule | None:
    """Return the first matching rule for a Python file."""
    normalized_dockerfile = workspace_path(dockerfile).resolve()
    relative_file = python_file.relative_to(workspace_path("."))
    normalized_relative = relative_file.as_posix()
    for rule in rules:
        if workspace_path(rule.dockerfile).resolve() != normalized_dockerfile:
            continue
        if any(normalized_relative.startswith(prefix) for prefix in rule.match_roots):
            return rule
    return None


def cleanup_image(builder: str, image_tag: str) -> None:
    """Remove one image quietly."""
    subprocess.run([builder, "image", "rm", "-f", image_tag], check=False, capture_output=True)


def main() -> int:
    """Run the CLI."""
    try:
        args = build_parser().parse_args()
        python_file = workspace_path(args.python_file)
        if not python_file.is_file():
            raise SystemExit(f"Python file not found: {python_file}")

        _, rules = load_rules(args.rules)
        resolved_rule = resolve_rule(dockerfile=args.dockerfile, python_file=python_file, rules=rules)
        pack_path = args.pack or (resolved_rule.pack if resolved_rule is not None else "docker/packs/default.toml")
        python_bin = resolved_rule.python_bin if resolved_rule is not None else "python3"
        workdir = resolved_rule.workdir if resolved_rule is not None else None

        pack = apply_pack_overrides(load_or_default_pack(pack_path), dockerfile=args.dockerfile)
        builder = resolve_builder(args.builder, print_only=args.print_only)
        relative_python = python_file.relative_to(workspace_path(".")).as_posix()
        container_python = f"{pack.runtime.workspace_mount.rstrip('/')}/{relative_python}"

        python_args = list(args.python_args)
        if python_args and python_args[0] == "--":
            python_args = python_args[1:]

        build_command = build_build_command(builder, pack)
        run_command = build_run_command(
            builder,
            pack,
            workspace_root=workspace_path("."),
            command=[python_bin, container_python, *python_args],
            env=tuple(args.env),
            mounts=tuple(args.mount),
            workdir=workdir,
        )

        print_label_and_command("build", build_command)
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
