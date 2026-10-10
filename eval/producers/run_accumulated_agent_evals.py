#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs all registered AgentCanon eval producers in append-only accumulation mode.
# upstream design ../../eval/definitions/README.md eval family and accumulation contract
# upstream design ../../documents/runtime/runtime-log-archive.md external runtime log archive contract
# upstream design ../../tools/README.md shared tool index
# upstream design ../../documents/tools/README.md user-facing tool index
# upstream design ../../tools/catalog.yaml structured tool catalog
# upstream implementation ../../tools/runtime/archive/runtime_log_paths.py owns accumulated report destinations
# upstream implementation ./evaluate_codex_agent_roles.py writes Codex agent role eval reports
# upstream implementation ./evaluate_workflow_selection.py writes workflow selection eval reports
# downstream implementation ../../tools/validation/ci/runners/run_all_checks.sh runs producers before accumulation validation
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml runs producers before accumulation validation
# downstream implementation ../../tests/agent_tools/test_run_accumulated_agent_evals.py validates command construction and log writeout
# @dependency-end
"""Run AgentCanon eval producers with mechanical append-only accumulation."""

from __future__ import annotations

import argparse
import inspect
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.runtime.artifacts.runtime_artifacts import (  # noqa: E402
    RuntimeArtifactBoundary,
    RuntimeArtifactError,
    root_capability_environment,
    runtime_artifact_boundary,
)

DEFAULT_RUN_ID = "agent-canon-accumulated-eval"


@dataclass(frozen=True)
class EvalProducer:
    """One accumulated eval producer command."""

    name: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class EvalProducerResult:
    """One eval producer execution result."""

    producer: EvalProducer
    returncode: int
    stdout_log: Path
    stderr_log: Path


Runner = Callable[..., subprocess.CompletedProcess[str]]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--target-root",
        type=Path,
        help="Observed read-only project target; producer definitions stay under --root.",
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        help="Explicit external runtime root; required for eval output and logs.",
    )
    parser.add_argument(
        "--run-id",
        default=DEFAULT_RUN_ID,
        help="Run bundle or CI gate id recorded inside accumulated reports.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        help=(
            "Directory for captured producer stdout/stderr. Defaults to "
            "reports/agent-eval-runs/<run-id>."
        ),
    )
    return parser


def script_root() -> Path:
    """Return the AgentCanon source root that owns this tool."""
    return Path(__file__).resolve().parents[2]


def safe_slug(value: str) -> str:
    """Return a filesystem-safe slug for log paths."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("._-") or "run"


def resolve_log_dir(
    root: Path,
    value: Path | None,
    run_id: str,
    runtime_root: Path | str | None = None,
) -> Path:
    """Resolve the directory for captured producer logs."""
    boundary = runtime_artifact_boundary(root, runtime_root)
    if value is not None:
        return boundary.resolve(value)
    return boundary.resolve(Path("tasks") / safe_slug(run_id) / "logs")


def build_producers(
    *,
    root: Path,
    run_id: str,
    python_bin: str,
    runtime_root: Path | str | None = None,
) -> tuple[EvalProducer, ...]:
    """Build role/workflow argv and delegate report paths to the archive owner.

    This collector owns the producer set and passes the explicit runtime
    capability. Leaving ``--results-dir`` unset lets each producer use the
    shared ``runtime_log_paths`` resolver, while this runner keeps capture
    logs separate. Collection flow:
    ``agents/skills/agent-eval-accumulation.md#Required Flow``.
    """
    canon = script_root()
    boundary = runtime_artifact_boundary(root, runtime_root)
    runtime_option = ("--runtime-root", str(boundary.root))
    return (
        EvalProducer(
            "codex-agent-role",
            (
                python_bin,
                str(canon / "eval" / "producers" / "evaluate_codex_agent_roles.py"),
                "--root",
                str(root),
                "--accumulate",
                "--run-id",
                run_id,
                *runtime_option,
            ),
        ),
        EvalProducer(
            "workflow-selection",
            (
                python_bin,
                str(canon / "eval" / "producers" / "evaluate_workflow_selection.py"),
                "--root",
                str(root),
                "--accumulate",
                "--run-id",
                run_id,
                *runtime_option,
            ),
        ),
    )


def subprocess_runner(
    command: Sequence[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one command, capturing stdout and stderr for bounded parent output."""
    return subprocess.run(
        tuple(command),
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def write_text(boundary: RuntimeArtifactBoundary, path: Path, text: str) -> Path:
    """Write captured command output to one log file."""
    return boundary.atomic_write_text(path, text)


def run_producers(
    *,
    root: Path,
    producers: Sequence[EvalProducer],
    log_dir: Path,
    target_root: Path | None = None,
    runtime_root: Path | str | None = None,
    runner: Runner = subprocess_runner,
) -> tuple[EvalProducerResult, ...]:
    """Run supplied producer argv and persist stdout/stderr beneath ``log_dir``.

    The runtime boundary supplies the child environment and authorizes these
    writes; returned records give the caller each exit code and capture path.
    This step does not read or validate the accumulated archive.
    """
    boundary = runtime_artifact_boundary(root, runtime_root)
    log_dir = boundary.resolve(log_dir)
    child_env = root_capability_environment(
        source_root=root,
        runtime_root=boundary.root,
        target_root=target_root or root,
    )
    results: list[EvalProducerResult] = []
    for index, producer in enumerate(producers, start=1):
        # Keep the tiny two-argument test seam source-compatible while every
        # real subprocess receives the complete typed root handoff.
        signature = inspect.signature(runner)
        accepts_env = len(signature.parameters) >= 3 or any(
            parameter.kind is inspect.Parameter.VAR_POSITIONAL
            for parameter in signature.parameters.values()
        )
        if accepts_env:
            completed = runner(producer.command, root, child_env)
        else:
            completed = runner(producer.command, root)
        prefix = f"{index:02d}-{safe_slug(producer.name)}"
        stdout_log = write_text(
            boundary, log_dir / f"{prefix}.stdout.txt", completed.stdout
        )
        stderr_log = write_text(
            boundary, log_dir / f"{prefix}.stderr.txt", completed.stderr
        )
        results.append(
            EvalProducerResult(
                producer=producer,
                returncode=completed.returncode,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )
        )
    return tuple(results)


def relative(root: Path, path: Path) -> str:
    """Return a root-relative path where possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def render_results(root: Path, results: Sequence[EvalProducerResult]) -> str:
    """Render bounded machine-readable status lines."""
    lines: list[str] = []
    for result in results:
        status = "pass" if result.returncode == 0 else "fail"
        lines.append(
            "ACCUMULATED_AGENT_EVAL_PRODUCER="
            f"{result.producer.name}:{status}:"
            f"stdout={relative(root, result.stdout_log)}:"
            f"stderr={relative(root, result.stderr_log)}"
        )
    failed = [result.producer.name for result in results if result.returncode != 0]
    lines.append(f"ACCUMULATED_AGENT_EVAL_PRODUCERS={len(results)}")
    lines.append(f"ACCUMULATED_AGENT_EVAL_FAILED={','.join(failed) or '-'}")
    lines.append(f"ACCUMULATED_AGENT_EVAL={'fail' if failed else 'pass'}")
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace, runner: Runner = subprocess_runner) -> int:
    """Run accumulated eval producers from parsed args."""
    root = Path(str(args.root)).resolve()
    target_root = (
        Path(str(args.target_root)).resolve() if args.target_root is not None else root
    )
    runtime_root = args.runtime_root
    boundary = runtime_artifact_boundary(root, runtime_root)
    log_dir = resolve_log_dir(root, args.log_dir, str(args.run_id), runtime_root)
    boundary.ensure_directory(log_dir.relative_to(boundary.root))
    producers = build_producers(
        root=root,
        run_id=str(args.run_id),
        python_bin=sys.executable,
        runtime_root=runtime_root,
    )
    results = run_producers(
        root=root,
        producers=producers,
        log_dir=log_dir,
        target_root=target_root,
        runtime_root=runtime_root,
        runner=runner,
    )
    print(render_results(root, results), end="")
    return 1 if any(result.returncode != 0 for result in results) else 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeArtifactError as exc:
        print(
            f"run_accumulated_agent_evals.py: runtime_root_required: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
