#!/usr/bin/env python3
# @dependency-start
# responsibility Creates and checks AgentCanon Lean proof environments with Mathlib/Aesop.
# upstream design ../../agents/skills/formal-proof-workflow.md requires Mathlib/Aesop before hand-built Lean scaffolds.
# downstream design ../../documents/tools/lean_proof_env.md documents the CLI contract.
# downstream implementation ../../tests/agent_tools/test_lean_proof_env.py tests generated environment files and dry-run commands.
# @dependency-end
"""Create or check a reusable Lean 4 proof environment with Mathlib and Aesop."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_LEAN_TOOLCHAIN = "leanprover/lean4:v4.30.0"
DEFAULT_MATHLIB_REV = "v4.30.0"
DEFAULT_PACKAGE_NAME = "agent_canon_lean_proof_env"
DEFAULT_MODULE_NAME = "AgentCanonLeanProofEnv"


@dataclass(frozen=True)
class CommandResult:
    """Captured command result for executed proof-environment checks."""

    command: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class LeanProofEnvResult:
    """Machine-readable result for Lean proof environment setup/checks."""

    action: str
    status: str
    env_dir: str
    lean_toolchain: str
    mathlib_rev: str
    package_name: str
    module_name: str
    created_or_updated_files: tuple[str, ...]
    commands: tuple[str, ...]
    executed: bool
    command_results: tuple[CommandResult, ...]
    lean_file: str | None
    notes: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("init", "smoke", "check-file"),
        help="Initialize the env, write/check the smoke theorem, or check a Lean file.",
    )
    parser.add_argument(
        "--env-dir",
        required=True,
        help="Lake package directory for the reusable proof environment.",
    )
    parser.add_argument(
        "--lean-toolchain",
        default=DEFAULT_LEAN_TOOLCHAIN,
        help=f"lean-toolchain content. Default: {DEFAULT_LEAN_TOOLCHAIN}",
    )
    parser.add_argument(
        "--mathlib-rev",
        default=DEFAULT_MATHLIB_REV,
        help=f"Mathlib git revision or tag. Default: {DEFAULT_MATHLIB_REV}",
    )
    parser.add_argument(
        "--package-name",
        default=DEFAULT_PACKAGE_NAME,
        help=f"Lake package name. Default: {DEFAULT_PACKAGE_NAME}",
    )
    parser.add_argument(
        "--module-name",
        default=DEFAULT_MODULE_NAME,
        help=f"Lean module name created in the environment. Default: {DEFAULT_MODULE_NAME}",
    )
    parser.add_argument(
        "--lean-file",
        help="Lean file to check for the check-file action.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run lake update and lake env lean after writing environment files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite non-matching generated files in the environment directory.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def lakefile_text(package_name: str, module_name: str, mathlib_rev: str) -> str:
    """Return the generated Lake package definition."""
    return "\n".join(
        [
            "/-",
            "@dependency-start",
            "responsibility Defines the AgentCanon reusable Lean proof environment.",
            "upstream implementation tools/agent_tools/lean_proof_env.py generates this file.",
            "downstream implementation AgentCanonLeanProofEnv.lean imports Mathlib and Aesop.",
            "@dependency-end",
            "-/",
            "",
            "import Lake",
            "open Lake DSL",
            "",
            f"package {package_name} where",
            "",
            "require mathlib from git",
            f'  "https://github.com/leanprover-community/mathlib4.git" @ "{mathlib_rev}"',
            "",
            "@[default_target]",
            f"lean_lib {module_name} where",
            "",
        ]
    )


def module_text() -> str:
    """Return the generated proof-environment module imports."""
    return "\n".join(
        [
            "/-",
            "@dependency-start",
            "responsibility Re-exports Mathlib and Aesop for AgentCanon proof tasks.",
            "upstream implementation lean_proof_env.py generates this module.",
            "downstream implementation AgentCanonLeanProofEnvSmoke.lean smoke-checks Aesop automation.",
            "@dependency-end",
            "-/",
            "",
            "import Mathlib",
            "import Aesop",
            "",
        ]
    )


def smoke_text(module_name: str) -> str:
    """Return a small checked theorem that exercises Aesop."""
    return "\n".join(
        [
            f"import {module_name}",
            "",
            "namespace AgentCanonLeanProofEnvSmoke",
            "",
            "theorem aesop_relation_composition",
            "    {P Q R S : Prop}",
            "    (hP : P)",
            "    (hPQ : P -> Q)",
            "    (hQR : Q -> R)",
            "    (hRS : R -> S) : S := by",
            "  aesop",
            "",
            "theorem mathlib_nat_order_example {a b c : Nat}",
            "    (hab : a <= b) (hbc : b <= c) : a <= c := by",
            "  exact Nat.le_trans hab hbc",
            "",
            "end AgentCanonLeanProofEnvSmoke",
            "",
        ]
    )


def write_generated(path: Path, text: str, force: bool) -> bool:
    """Write a generated file; return True when the file changed."""
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == text:
            return False
        if not force:
            raise ValueError(f"Refusing to overwrite non-matching generated file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def shell_join(parts: Sequence[str]) -> str:
    """Return a shell-readable command string for reports."""
    return shlex.join(tuple(parts))


def run_command(parts: Sequence[str], cwd: Path) -> CommandResult:
    """Run a command and capture output."""
    completed = subprocess.run(
        tuple(parts),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        command=shell_join(parts),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def build_result(args: argparse.Namespace) -> LeanProofEnvResult:
    """Create environment files and optionally run checker commands."""
    env_dir = Path(args.env_dir).resolve()
    module_name = str(args.module_name)
    created_files: list[str] = []

    generated_files = {
        env_dir / "lean-toolchain": str(args.lean_toolchain).strip() + "\n",
        env_dir / "lakefile.lean": lakefile_text(
            str(args.package_name), module_name, str(args.mathlib_rev)
        ),
        env_dir / f"{module_name}.lean": module_text(),
    }
    for path, text in generated_files.items():
        if write_generated(path, text, bool(args.force)):
            created_files.append(str(path))

    lean_file: Path | None = None
    if args.action == "smoke":
        lean_file = env_dir / f"{module_name}Smoke.lean"
        if write_generated(lean_file, smoke_text(module_name), bool(args.force)):
            created_files.append(str(lean_file))
    elif args.action == "check-file":
        if not args.lean_file:
            raise ValueError("--lean-file is required for check-file")
        lean_file = Path(args.lean_file).resolve()

    commands: list[tuple[str, ...]] = []
    if args.action in {"smoke", "check-file"}:
        commands.append(("lake", "update"))
        commands.append(("lake", "build"))
        if lean_file is None:
            raise ValueError("internal error: lean_file was not selected")
        commands.append(("lake", "env", "lean", str(lean_file)))

    command_results: list[CommandResult] = []
    status = "initialized"
    if args.execute and commands:
        for command in commands:
            result = run_command(command, cwd=env_dir)
            command_results.append(result)
            if result.returncode != 0:
                status = "failed"
                break
        else:
            status = "checked"
    elif args.action in {"smoke", "check-file"}:
        status = "dry_run"

    notes = (
        "This environment belongs to AgentCanon proof tooling, not to an individual theorem package.",
        "Use check-file for Mathlib/Aesop-backed proof stubs generated outside this Lake package.",
    )
    return LeanProofEnvResult(
        action=str(args.action),
        status=status,
        env_dir=str(env_dir),
        lean_toolchain=str(args.lean_toolchain),
        mathlib_rev=str(args.mathlib_rev),
        package_name=str(args.package_name),
        module_name=module_name,
        created_or_updated_files=tuple(created_files),
        commands=tuple(shell_join(command) for command in commands),
        executed=bool(args.execute),
        command_results=tuple(command_results),
        lean_file=str(lean_file) if lean_file is not None else None,
        notes=notes,
    )


def render_text(result: LeanProofEnvResult) -> str:
    """Render a compact human-readable result."""
    lines = [
        f"LEAN_PROOF_ENV_ACTION={result.action}",
        f"LEAN_PROOF_ENV_STATUS={result.status}",
        f"LEAN_PROOF_ENV_DIR={result.env_dir}",
        f"LEAN_PROOF_ENV_EXECUTED={'yes' if result.executed else 'no'}",
    ]
    if result.lean_file:
        lines.append(f"LEAN_PROOF_ENV_LEAN_FILE={result.lean_file}")
    if result.commands:
        lines.append("LEAN_PROOF_ENV_COMMANDS:")
        lines.extend(f"  {command}" for command in result.commands)
    for command_result in result.command_results:
        lines.append(
            "LEAN_PROOF_ENV_COMMAND_RESULT="
            f"{command_result.returncode} {command_result.command}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = build_result(args)
    except ValueError as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(result))
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
