#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides the provider-independent admitted direct GPU command CLI.
# upstream implementation ./gpu_command_admission.py owns strict admission, plan freeze, environment, execution, evidence, and release
# upstream design ../../agents/skills/gpu-execution.md selects direct versus managed execution
# upstream design ../../documents/experiments/gpu-direct-command.md CLI and evidence contract
# downstream implementation ../../tests/tools/test_run_gpu_command.py validates parsing and no-provider execution
# @dependency-end

"""Run an arbitrary argv on a conservatively admitted free GPU set."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:  # Support the documented path invocation.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.experiments.execution_resource_plan import (  # noqa: E402
    HOST_RUNTIME_ROOT,
    LOCK_ROOT,
    TypedPreflightFailure,
)
from tools.experiments.gpu_command_admission import (  # noqa: E402
    DirectGpuCommandRequest,
    DirectGpuCommandRunner,
    forward_command_output,
    process_exit_code,
    resolve_candidate_allocation,
)


def _default_output_dir() -> Path:
    timestamp = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y%m%dT%H%M%SZ")
    )
    return (
        Path.cwd()
        / "reports"
        / "agents"
        / f"gpu-command-{timestamp}-{os.getpid()}"
        / "runtime"
    ).absolute()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Admit FREE full-UUID GPU/MIG leaves, freeze a direct-command plan, "
            "and launch argv with shell=False."
        )
    )
    parser.add_argument("--gpu-count", type=int, default=1)
    parser.add_argument(
        "--min-free-memory",
        "--minimum-free-memory-bytes",
        dest="minimum_free_memory_bytes",
        type=int,
        default=0,
        help="minimum free bytes required on every selected GPU/MIG leaf",
    )
    parser.add_argument(
        "--candidate-gpu",
        action="append",
        default=[],
        metavar="FULL_UUID",
        help=(
            "restrict candidates to a complete GPU-/MIG- UUID; repeat for more "
            "than one candidate"
        ),
    )
    parser.add_argument("--cwd", default=str(Path.cwd()))
    parser.add_argument("--output-dir", default="")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="command argv after --",
    )
    return parser


def _command_argv(raw: Sequence[str]) -> tuple[str, ...]:
    command = tuple(raw[1:] if raw and raw[0] == "--" else raw)
    if not command:
        raise TypedPreflightFailure(
            "gpu_command_argv_invalid",
            "a direct command argv is required after --",
        )
    return command


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output_dir = (
        Path(args.output_dir).absolute()
        if args.output_dir
        else _default_output_dir()
    )
    try:
        command = _command_argv(args.command)
        environment = dict(os.environ)
        allocation = resolve_candidate_allocation(
            environment,
            explicit_candidates=tuple(args.candidate_gpu),
        )
        request = DirectGpuCommandRequest(
            argv=command,
            cwd=Path(args.cwd).absolute(),
            environment=environment,
            candidate_allocation=allocation,
            gpu_count=args.gpu_count,
            minimum_free_memory_bytes=args.minimum_free_memory_bytes,
            output_dir=output_dir,
            runtime_root=Path(HOST_RUNTIME_ROOT),
            lock_root=LOCK_ROOT,
        )
        result = DirectGpuCommandRunner().run(request)
        forward_command_output(result)
        return process_exit_code(result.returncode)
    except BaseException as exc:
        code = exc.code if isinstance(exc, TypedPreflightFailure) else type(exc).__name__
        payload = {
            "schema_version": "agentcanon-gpu-command-cli-error/v1",
            "failure_code": code,
            "message": str(exc),
            "output_dir": str(output_dir),
        }
        sys.stderr.write(json.dumps(payload, sort_keys=True) + "\n")
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
