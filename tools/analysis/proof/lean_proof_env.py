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
    lake_version: str | None
    lean_version: str | None
    lake_manifest: str | None
    mathlib_revision: str | None


def build_parser() -> argparse.ArgumentParser:
    """Build the existing action-oriented CLI."""
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
    )
    parser.add_argument(
        "--env-dir", required=True, help="Selected Lake package directory."
    )
    parser.add_argument(
        "--lean-toolchain",
        help="Exact Lean toolchain to select when the package has no declaration.",
    )
    parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
    parser.add_argument("--lean-file", help="File to check for the check-file action.")
    parser.add_argument(
        "--execute",
        action="store_true",
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
        tuple(parts),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return CommandResult(
        command=shlex.join(parts),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def manifest_mathlib_revision(path: Path) -> str | None:
    """Read the resolved Mathlib revision from Lake's native manifest."""
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    packages = manifest.get("packages", [])
    if not isinstance(packages, list):
        return None
    for package in packages:
        if isinstance(package, dict) and package.get("name") == "mathlib":
            revision = package.get("rev")
            return revision if isinstance(revision, str) else None
    return None


def build_result(args: argparse.Namespace) -> LeanProofEnvResult:
    """Initialize with Lake when needed, then run the selected native checks."""
    env_dir = Path(args.env_dir).resolve()
    if args.action == "check-file" and not args.lean_file:
        raise ValueError("--lean-file is required for check-file")

    configured = any(
        (env_dir / name).is_file() for name in ("lakefile.lean", "lakefile.toml")
    )
    toolchain_file = env_dir / "lean-toolchain"
    declared_toolchain = (
        toolchain_file.read_text(encoding="utf-8").strip() or None
        if toolchain_file.is_file()
        else None
    )
    requested_toolchain = str(getattr(args, "lean_toolchain", "") or "").strip()
    requested_toolchain = requested_toolchain or None

    if (
        not configured
        and env_dir.exists()
        and any(path.name != "lean-toolchain" for path in env_dir.iterdir())
    ):
        raise ValueError(
            "Choose an empty directory, a toolchain-only directory, or an existing "
            f"Lake package: {env_dir}"
        )
    if (
        declared_toolchain
        and requested_toolchain
        and declared_toolchain != requested_toolchain
    ):
        raise ValueError(
            f"--lean-toolchain does not match the project declaration in {toolchain_file}"
        )
    selected_toolchain = requested_toolchain or declared_toolchain
    if selected_toolchain is None:
        raise ValueError(
            "Select an exact Lean toolchain with --lean-toolchain or a "
            "project lean-toolchain file."
        )

    probes: dict[Path, str] = {}
    if args.action in {"smoke", "all-smoke"}:
        probes[env_dir / "AgentCanonLeanProofEnvSmoke.lean"] = smoke_text()
    if args.action in {"agent-smoke", "all-smoke"}:
        probes[env_dir / "AgentCanonLeanProofEnvAgent.lean"] = agent_smoke_text()
    if args.action in {"counterexample-smoke", "all-smoke"}:
        probes[env_dir / "AgentCanonLeanProofEnvCounterexample.lean"] = (
            counterexample_text()
        )
    lean_files = list(probes)
    if args.action == "check-file":
        lean_files.append(Path(args.lean_file).resolve())

    lake = ("lake", f"+{selected_toolchain}")
    commands: list[tuple[str, ...]] = []
    if not configured:
        commands.append((*lake, "init", str(args.package_name), "math"))
    commands.append((*lake, "--version"))
    commands.append((*lake, "--keep-toolchain", "env", "lean", "--version"))
    if lean_files:
        commands.append((*lake, "--keep-toolchain", "build"))
        commands.extend(
            (*lake, "--keep-toolchain", "env", "lean", str(path)) for path in lean_files
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

    manifest = env_dir / "lake-manifest.json"
    try:
        toolchain_readback = (
            toolchain_file.read_text(encoding="utf-8").strip()
            if toolchain_file.is_file()
            else None
        )
    except (OSError, UnicodeError):
        toolchain_readback = None
    command_pairs = tuple(zip(commands, results, strict=False))
    lake_version = next(
        (
            result.stdout.strip()
            for command, result in command_pairs
            if command[-1:] == ("--version",)
            and command[-2:-1] == (f"+{selected_toolchain}",)
            and result.returncode == 0
        ),
        None,
    )
    lean_version = next(
        (
            result.stdout.strip()
            for command, result in command_pairs
            if command[-3:] == ("env", "lean", "--version") and result.returncode == 0
        ),
        None,
    )
    return LeanProofEnvResult(
        action=str(args.action),
        status=status,
        env_dir=str(env_dir),
        created_or_updated_files=tuple(created_files),
        commands=tuple(shlex.join(command) for command in commands),
        executed=bool(args.execute),
        command_results=tuple(results),
        lean_file=str(lean_files[-1]) if lean_files else None,
        lean_toolchain=toolchain_readback,
        lake_version=lake_version,
        lean_version=lean_version,
        lake_manifest=str(manifest) if manifest.is_file() else None,
        mathlib_revision=manifest_mathlib_revision(manifest),
    )


def render_text(result: LeanProofEnvResult) -> str:
    """Render status, native commands, and their unmodified diagnostics."""
    lines = [
        f"LEAN_PROOF_ENV_ACTION={result.action}",
        f"LEAN_PROOF_ENV_STATUS={result.status}",
        f"LEAN_PROOF_ENV_DIR={result.env_dir}",
        f"LEAN_PROOF_ENV_EXECUTED={'yes' if result.executed else 'no'}",
    ]
    for key, value in (
        ("LEAN_PROOF_ENV_TOOLCHAIN", result.lean_toolchain),
        ("LEAN_PROOF_ENV_LAKE_VERSION", result.lake_version),
        ("LEAN_PROOF_ENV_LEAN_VERSION", result.lean_version),
        ("LEAN_PROOF_ENV_LAKE_MANIFEST", result.lake_manifest),
        ("LEAN_PROOF_ENV_MATHLIB_REVISION", result.mathlib_revision),
    ):
        if value is not None:
            lines.append(f"{key}={value}")
    lines.extend(f"  {command}" for command in result.commands)
    for command in result.command_results:
        lines.append(
            f"LEAN_PROOF_ENV_COMMAND_RESULT={command.returncode} {command.command}"
        )
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
    return next(
        (item.returncode for item in result.command_results if item.returncode), 0
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
