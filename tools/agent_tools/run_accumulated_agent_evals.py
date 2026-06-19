#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs all registered AgentCanon eval producers in append-only accumulation mode.
# upstream design ../../evidence/agent-evals/README.md eval family and accumulation contract
# upstream design ../../documents/runtime-log-archive.md external runtime log archive contract
# upstream design ../../tools/README.md shared tool index
# upstream design ../../documents/tools/README.md user-facing tool index
# upstream design ../../tools/catalog.yaml structured tool catalog
# upstream implementation ./evaluate_codex_agent_roles.py writes Codex agent role eval reports
# upstream implementation ./evaluate_skill_workflow_prompts.py writes skill and workflow prompt eval reports
# upstream implementation ./evaluate_workflow_selection.py writes workflow selection eval reports
# upstream implementation ./evaluate_report_quality.py writes report quality eval reports
# upstream implementation ./local_llm_eval.py writes local LLM responsibility eval reports
# downstream implementation ../ci/check_agent_canon_pr.sh runs producers before accumulation validation
# downstream implementation ../ci/run_all_checks.sh runs producers before accumulation validation
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml runs producers before accumulation validation
# downstream implementation ../../tests/agent_tools/test_run_accumulated_agent_evals.py validates command construction and log writeout
# @dependency-end
"""Run AgentCanon eval producers with mechanical append-only accumulation."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_manifest_paths import eval_manifest_path, resolve_eval_manifest  # noqa: E402

DEFAULT_RUN_ID = "agent-canon-accumulated-eval"
DEFAULT_PROMPT_EVAL_MANIFEST = Path(eval_manifest_path("skill_workflow_prompt_eval.toml"))


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


Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--run-id",
        default=DEFAULT_RUN_ID,
        help="Run bundle or CI gate id recorded inside accumulated reports.",
    )
    parser.add_argument(
        "--skill-used",
        action="append",
        default=[],
        help="Skill id to record in the skill/workflow prompt eval. Repeat as needed.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        help="Optional reports/agents/<run-id> directory for workflow monitoring append.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        help=(
            "Directory for captured producer stdout/stderr. Defaults to "
            "reports/agent-eval-runs/<run-id>."
        ),
    )
    parser.add_argument(
        "--prompt-eval-manifest",
        type=Path,
        default=DEFAULT_PROMPT_EVAL_MANIFEST,
        help="Skill/workflow prompt eval manifest.",
    )
    return parser


def script_root() -> Path:
    """Return the AgentCanon source root that owns this tool."""
    return Path(__file__).resolve().parents[2]


def safe_slug(value: str) -> str:
    """Return a filesystem-safe slug for log paths."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("._-") or "run"


def resolve_log_dir(root: Path, value: Path | None, run_id: str) -> Path:
    """Resolve the directory for captured producer logs."""
    if value is not None:
        return value if value.is_absolute() else root / value
    return root / "reports" / "agent-eval-runs" / safe_slug(run_id)


def resolve_path(root: Path, value: Path) -> Path:
    """Resolve one CLI path against the selected repository root."""
    return resolve_eval_manifest(root, value)


def build_producers(
    *,
    root: Path,
    run_id: str,
    skill_used: Sequence[str],
    report_dir: Path | None,
    prompt_eval_manifest: Path,
    python_bin: str,
) -> tuple[EvalProducer, ...]:
    """Build all accumulated eval producer commands."""
    canon = script_root()
    prompt_command: list[str] = [
        python_bin,
        str(canon / "tools" / "agent_tools" / "evaluate_skill_workflow_prompts.py"),
        "--root",
        str(root),
        "--manifest",
        str(prompt_eval_manifest),
        "--accumulate",
        "--run-id",
        run_id,
    ]
    for skill in skill_used:
        prompt_command.extend(["--skill-used", skill])
    if report_dir is not None:
        prompt_command.extend(["--report-dir", str(report_dir)])
    return (
        EvalProducer(
            "codex-agent-role",
            (
                python_bin,
                str(canon / "tools" / "agent_tools" / "evaluate_codex_agent_roles.py"),
                "--root",
                str(root),
                "--accumulate",
                "--run-id",
                run_id,
            ),
        ),
        EvalProducer("skill-workflow-prompt", tuple(prompt_command)),
        EvalProducer(
            "local-llm-responsibility",
            (
                str(canon / "tools" / "bin" / "agent-canon"),
                "local-llm",
                "eval",
                "--root",
                str(root),
                "--accumulate",
            ),
        ),
        EvalProducer(
            "workflow-selection",
            (
                python_bin,
                str(canon / "tools" / "agent_tools" / "evaluate_workflow_selection.py"),
                "--root",
                str(root),
                "--accumulate",
                "--run-id",
                run_id,
            ),
        ),
        EvalProducer(
            "report-quality",
            (
                python_bin,
                str(canon / "tools" / "agent_tools" / "evaluate_report_quality.py"),
                "--root",
                str(root),
                "--accumulate",
            ),
        ),
    )


def subprocess_runner(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one command, capturing stdout and stderr for bounded parent output."""
    return subprocess.run(
        tuple(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )


def write_text(path: Path, text: str) -> Path:
    """Write captured command output to one log file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_producers(
    *,
    root: Path,
    producers: Sequence[EvalProducer],
    log_dir: Path,
    runner: Runner = subprocess_runner,
) -> tuple[EvalProducerResult, ...]:
    """Run producers and capture their outputs."""
    results: list[EvalProducerResult] = []
    for index, producer in enumerate(producers, start=1):
        completed = runner(producer.command, root)
        prefix = f"{index:02d}-{safe_slug(producer.name)}"
        stdout_log = write_text(log_dir / f"{prefix}.stdout.txt", completed.stdout)
        stderr_log = write_text(log_dir / f"{prefix}.stderr.txt", completed.stderr)
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
    lines = []
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
    report_dir = resolve_path(root, args.report_dir) if args.report_dir else None
    prompt_eval_manifest = resolve_path(root, args.prompt_eval_manifest)
    log_dir = resolve_log_dir(root, args.log_dir, str(args.run_id))
    producers = build_producers(
        root=root,
        run_id=str(args.run_id),
        skill_used=tuple(str(skill) for skill in args.skill_used),
        report_dir=report_dir,
        prompt_eval_manifest=prompt_eval_manifest,
        python_bin=sys.executable,
    )
    results = run_producers(root=root, producers=producers, log_dir=log_dir, runner=runner)
    print(render_results(root, results), end="")
    return 1 if any(result.returncode != 0 for result in results) else 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
