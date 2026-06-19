#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Creates and checks AgentCanon Lean proof environments with proof-search, theorem-search, and counterexample tools.
# upstream design ../../agents/skills/formal-proof-workflow.md requires checked Lean automation and counterexample routes before hand-built proof scaffolds.
# downstream design ../../documents/tools/lean_proof_env.md documents the CLI contract.
# downstream implementation ../../tests/agent_tools/test_lean_proof_env.py tests generated environment files and dry-run commands.
# @dependency-end
"""Create or check a reusable Lean 4 proof environment for agent proof work."""

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
class CommandSpec:
    """Checker command plus the success condition expected by this tool."""

    parts: tuple[str, ...]
    expected_counterexample: bool = False


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
        choices=(
            "init",
            "smoke",
            "agent-smoke",
            "counterexample-smoke",
            "all-smoke",
            "check-file",
        ),
        help=(
            "Initialize the env, run proof-search smoke, run agent-interface "
            "smoke, run counterexample smoke, run all smokes, or check a Lean file."
        ),
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
            "downstream implementation AgentCanonLeanProofEnv.lean imports Mathlib, Aesop, Plausible, and LeanSearchClient.",
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
            "responsibility Re-exports Mathlib, Aesop, Plausible, and LeanSearchClient for AgentCanon proof tasks.",
            "upstream implementation lean_proof_env.py generates this module.",
            "downstream implementation AgentCanonLeanProofEnvSmoke.lean smoke-checks proof-search automation.",
            "downstream implementation AgentCanonLeanProofEnvAgent.lean smoke-checks agent theorem-search imports.",
            "downstream implementation AgentCanonLeanProofEnvCounterexample.lean smoke-checks counterexample discovery.",
            "@dependency-end",
            "-/",
            "",
            "import Mathlib",
            "import Aesop",
            "import Plausible",
            "import LeanSearchClient",
            "",
        ]
    )


def smoke_text(module_name: str) -> str:
    """Return checked theorems that exercise local proof-search tactics."""
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
            "theorem omega_index_example {i j k : Int}",
            "    (hij : i <= j) (hjk : j <= k) : i <= k := by",
            "  omega",
            "",
            "theorem linarith_budget_example {a b c : Real}",
            "    (hab : a <= b) (hbc : b <= c) : a <= c := by",
            "  linarith",
            "",
            "theorem grind_symmetry_example {a b : Nat}",
            "    (h : a = b) : b = a := by",
            "  grind",
            "",
            "#eval Plausible.Testable.check <|",
            "  forall (xs : Array Nat), xs.size = xs.size",
            "",
            "end AgentCanonLeanProofEnvSmoke",
            "",
        ]
    )


def agent_smoke_text(module_name: str) -> str:
    """Return a checked file for agent-facing theorem-search interfaces."""
    return "\n".join(
        [
            f"import {module_name}",
            "",
            "namespace AgentCanonLeanProofEnvAgent",
            "",
            "set_option leansearchclient.backend \"leansearch\"",
            "",
            "#check LeanSearchClient.SearchResult",
            "#check LeanSearchClient.SearchServer",
            "#check LeanSearchClient.leanSearchServer",
            "",
            "theorem leansearchclient_import_surface_ready : True := by",
            "  trivial",
            "",
            "end AgentCanonLeanProofEnvAgent",
            "",
        ]
    )


def counterexample_text(module_name: str) -> str:
    """Return a Plausible probe that is expected to find a counterexample."""
    return "\n".join(
        [
            f"import {module_name}",
            "",
            "namespace AgentCanonLeanProofEnvCounterexample",
            "",
            "/--",
            "This command is intentionally false. The environment check succeeds",
            "only when Plausible finds a concrete counterexample and Lean exits",
            "with a failing check.",
            "-/",
            "#eval Plausible.Testable.check <|",
            "  forall (xs ys : Array Nat), xs.size = ys.size -> xs = ys",
            "",
            "end AgentCanonLeanProofEnvCounterexample",
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


def render_command(spec: CommandSpec) -> str:
    """Return the report command string for a checker command spec."""
    command = shell_join(spec.parts)
    if spec.expected_counterexample:
        return f"{command} # expected Plausible counterexample"
    return command


def run_command(spec: CommandSpec, cwd: Path) -> CommandResult:
    """Run a command and capture output."""
    completed = subprocess.run(
        spec.parts,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout
    stderr = completed.stderr
    returncode = completed.returncode
    if spec.expected_counterexample:
        combined_output = f"{stdout}\n{stderr}"
        if completed.returncode != 0 and "Found a counter-example!" in combined_output:
            returncode = 0
        else:
            returncode = 1
            stderr = (
                stderr
                + "\nExpected Plausible to find a counterexample, but the expected "
                "counterexample marker was absent."
            )
    return CommandResult(
        command=render_command(spec),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
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

    lean_files: list[Path] = []
    counterexample_files: set[Path] = set()
    if args.action in {"smoke", "all-smoke"}:
        smoke_file = env_dir / f"{module_name}Smoke.lean"
        if write_generated(smoke_file, smoke_text(module_name), bool(args.force)):
            created_files.append(str(smoke_file))
        lean_files.append(smoke_file)
    if args.action in {"agent-smoke", "all-smoke"}:
        agent_file = env_dir / f"{module_name}Agent.lean"
        if write_generated(agent_file, agent_smoke_text(module_name), bool(args.force)):
            created_files.append(str(agent_file))
        lean_files.append(agent_file)
    if args.action in {"counterexample-smoke", "all-smoke"}:
        counterexample_file = env_dir / f"{module_name}Counterexample.lean"
        if write_generated(
            counterexample_file, counterexample_text(module_name), bool(args.force)
        ):
            created_files.append(str(counterexample_file))
        lean_files.append(counterexample_file)
        counterexample_files.add(counterexample_file)
    elif args.action == "check-file":
        if not args.lean_file:
            raise ValueError("--lean-file is required for check-file")
        lean_files.append(Path(args.lean_file).resolve())

    commands: list[CommandSpec] = []
    if args.action in {
        "smoke",
        "agent-smoke",
        "counterexample-smoke",
        "all-smoke",
        "check-file",
    }:
        commands.append(CommandSpec(("lake", "update")))
        commands.append(CommandSpec(("lake", "build")))
        for lean_file in lean_files:
            commands.append(
                CommandSpec(
                    ("lake", "env", "lean", str(lean_file)),
                    expected_counterexample=lean_file in counterexample_files,
                )
            )

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
    elif commands:
        status = "dry_run"

    notes = (
        "This environment belongs to AgentCanon proof tooling, not to an individual theorem package.",
        "Use smoke for local proof-search tactics, agent-smoke for LeanSearchClient imports, and counterexample-smoke for Plausible counterexample discovery.",
        "Use check-file for Mathlib/Aesop/Plausible/LeanSearchClient-backed proof stubs generated outside this Lake package.",
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
        commands=tuple(render_command(command) for command in commands),
        executed=bool(args.execute),
        command_results=tuple(command_results),
        lean_file=str(lean_files[-1]) if lean_files else None,
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
