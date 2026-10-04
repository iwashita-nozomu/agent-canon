#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs native Lake setup and Lean proof, interface, and counterexample checks without interpreting diagnostic text as success.
# upstream design ../../../agents/skills/formal-proof-workflow.md owns proof workflow selection
# downstream design ../../../documents/tools/lean_proof_env.md documents the CLI and native configuration boundary
# downstream implementation ../../../tests/agent_tools/test_lean_proof_env.py tests native command and failure propagation
# @dependency-end
"""Create or check a reusable Lean package through Lake's native interface."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_PACKAGE_NAME = "agent_canon_lean_proof_env"


@dataclass(frozen=True)
class CommandResult:
    """One native command result, including its unchanged exit status."""

    command: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class LeanProofEnvResult:
    """Execution evidence; planned commands are not successful checks."""

    action: str
    status: str
    env_dir: str
    created_or_updated_files: tuple[str, ...]
    commands: tuple[str, ...]
    executed: bool
    command_results: tuple[CommandResult, ...]
    lean_file: str | None
    lean_toolchain: str | None
    lake_manifest: str | None


def build_parser() -> argparse.ArgumentParser:
    """Build the existing action-oriented CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "init", "smoke", "agent-smoke", "counterexample-smoke",
            "all-smoke", "check-file",
        ),
    )
    parser.add_argument("--env-dir", required=True, help="Selected Lake package directory.")
    parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
    parser.add_argument("--lean-file", help="File to check for the check-file action.")
    parser.add_argument(
        "--execute", action="store_true",
        help="Execute the printed native commands; otherwise make no changes.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def smoke_text() -> str:
    """Exercise existing proof-search tactics and a true Plausible property."""
    return """import Mathlib
import Aesop
import Plausible

namespace AgentCanonLeanProofEnvSmoke

theorem aesop_relation_composition
    {P Q R S : Prop} (hP : P) (hPQ : P -> Q)
    (hQR : Q -> R) (hRS : R -> S) : S := by
  aesop

theorem mathlib_nat_order_example {a b c : Nat}
    (hab : a <= b) (hbc : b <= c) : a <= c := by
  exact Nat.le_trans hab hbc

theorem omega_index_example {i j k : Int}
    (hij : i <= j) (hjk : j <= k) : i <= k := by
  omega

theorem linarith_budget_example {a b c : Real}
    (hab : a <= b) (hbc : b <= c) : a <= c := by
  linarith

theorem grind_symmetry_example {a b : Nat} (h : a = b) : b = a := by
  grind

#eval Plausible.Testable.check (forall (xs : Array Nat), xs.size = xs.size)

end AgentCanonLeanProofEnvSmoke
"""


def agent_smoke_text() -> str:
    """Check theorem-search imports without invoking a remote search service."""
    return """import LeanSearchClient

namespace AgentCanonLeanProofEnvAgent

set_option leansearchclient.backend "leansearch"

#check LeanSearchClient.SearchResult
#check LeanSearchClient.SearchServer
#check LeanSearchClient.leanSearchServer

theorem leansearchclient_import_surface_ready : True := by
  trivial

end AgentCanonLeanProofEnvAgent
"""


def counterexample_text() -> str:
    """Let Lean check the expected diagnostic, including unexpected failures."""
    return """import Plausible

namespace AgentCanonLeanProofEnvCounterexample

/-- error: Found a counter-example! -/
#guard_msgs in
#eval Plausible.Testable.check (forall (n : Nat), n < n) { quiet := true }

end AgentCanonLeanProofEnvCounterexample
"""


def write_generated(path: Path, text: str) -> bool:
    """Write only a selected probe; never overwrite different existing content."""
    if path.is_symlink():
        raise ValueError(f"Refusing to write a probe through a symlink: {path}")
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Refusing to overwrite non-matching probe: {path}")
        return False
    path.write_text(text, encoding="utf-8")
    return True


def run_command(parts: Sequence[str], cwd: Path) -> CommandResult:
    """Return native output and status without counterexample-text heuristics."""
    completed = subprocess.run(
        tuple(parts), cwd=cwd, check=False, capture_output=True, text=True,
    )
    return CommandResult(
        command=shlex.join(parts), returncode=completed.returncode,
        stdout=completed.stdout, stderr=completed.stderr,
    )


def build_result(args: argparse.Namespace) -> LeanProofEnvResult:
    """Initialize with Lake when needed, then run the selected native checks."""
    env_dir = Path(args.env_dir).resolve()
    configured = any((env_dir / name).is_file() for name in ("lakefile.lean", "lakefile.toml"))
    if not configured and env_dir.exists() and any(env_dir.iterdir()):
        raise ValueError(f"Choose an empty directory or an existing Lake package: {env_dir}")

    probes: dict[Path, str] = {}
    if args.action in {"smoke", "all-smoke"}:
        probes[env_dir / "AgentCanonLeanProofEnvSmoke.lean"] = smoke_text()
    if args.action in {"agent-smoke", "all-smoke"}:
        probes[env_dir / "AgentCanonLeanProofEnvAgent.lean"] = agent_smoke_text()
    if args.action in {"counterexample-smoke", "all-smoke"}:
        probes[env_dir / "AgentCanonLeanProofEnvCounterexample.lean"] = counterexample_text()
    lean_files = list(probes)
    if args.action == "check-file":
        if not args.lean_file:
            raise ValueError("--lean-file is required for check-file")
        lean_files.append(Path(args.lean_file).resolve())

    commands: list[tuple[str, ...]] = []
    if not configured:
        commands.append(("lake", "init", str(args.package_name), "math"))
    commands.append(("lake", "--version"))
    commands.append(("lake", "--keep-toolchain", "env", "lean", "--version"))
    if lean_files:
        commands.append(("lake", "--keep-toolchain", "build"))
        commands.extend(
            ("lake", "--keep-toolchain", "env", "lean", str(path))
            for path in lean_files
        )

    results: list[CommandResult] = []
    created_files: list[str] = []
    status = "dry_run"
    if args.execute:
        env_dir.mkdir(parents=True, exist_ok=True)
        # Probe writes are delayed until native initialization has succeeded.
        for command in commands:
            if command[-1] in {str(path) for path in probes}:
                path = Path(command[-1])
                if write_generated(path, probes[path]):
                    created_files.append(str(path))
            result = run_command(command, cwd=env_dir)
            results.append(result)
            if result.returncode != 0:
                status = "failed"
                break
        else:
            status = "checked" if lean_files else "initialized"

    toolchain = env_dir / "lean-toolchain"
    manifest = env_dir / "lake-manifest.json"
    return LeanProofEnvResult(
        action=str(args.action), status=status, env_dir=str(env_dir),
        created_or_updated_files=tuple(created_files),
        commands=tuple(shlex.join(command) for command in commands),
        executed=bool(args.execute), command_results=tuple(results),
        lean_file=str(lean_files[-1]) if lean_files else None,
        lean_toolchain=toolchain.read_text(encoding="utf-8").strip() if toolchain.is_file() else None,
        lake_manifest=str(manifest) if manifest.is_file() else None,
    )


def render_text(result: LeanProofEnvResult) -> str:
    """Render status, native commands, and their unmodified diagnostics."""
    lines = [
        f"LEAN_PROOF_ENV_ACTION={result.action}",
        f"LEAN_PROOF_ENV_STATUS={result.status}",
        f"LEAN_PROOF_ENV_DIR={result.env_dir}",
        f"LEAN_PROOF_ENV_EXECUTED={'yes' if result.executed else 'no'}",
    ]
    lines.extend(f"  {command}" for command in result.commands)
    for command in result.command_results:
        lines.append(f"LEAN_PROOF_ENV_COMMAND_RESULT={command.returncode} {command.command}")
        lines.extend((command.stdout, command.stderr))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected action and propagate the first failing native status."""
    args = build_parser().parse_args(argv)
    try:
        result = build_result(args)
    except (OSError, ValueError) as error:
        print(f"LEAN_PROOF_ENV_ERROR={error}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print(render_text(result))
    return next((item.returncode for item in result.command_results if item.returncode), 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
