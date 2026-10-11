"""Launch the topic-owned native executable and preserve its standard output."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--multi-case", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config_path = args.config.resolve()
    if not config_path.is_file():
        raise SystemExit(f"configuration file does not exist: {config_path}")

    raw_dir_text = os.environ.get("EXPERIMENT_RAW_DIR")
    if not raw_dir_text:
        raise SystemExit("EXPERIMENT_RAW_DIR must be set by the consumer run owner")
    raw_dir = Path(raw_dir_text).resolve()
    if not raw_dir.is_dir():
        raise SystemExit(f"raw result directory does not exist: {raw_dir}")

    topic_name = Path(__file__).resolve().parent.name
    executable_text = os.environ.get("EXPERIMENT_EXECUTABLE")
    executable = (
        Path(executable_text).expanduser().resolve()
        if executable_text
        else Path(shutil.which(topic_name) or "")
    )
    if not executable_text and not executable.is_file():
        raise SystemExit(
            f"native target {topic_name!r} is not on PATH; set EXPERIMENT_EXECUTABLE"
        )
    if not executable.is_file():
        raise SystemExit(f"native executable does not exist: {executable}")

    if args.multi_case:
        from cases import CaseSpec

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise SystemExit(
                f"multi-case config must be JSON-compatible YAML: {error}"
            ) from error
        if not isinstance(config, dict):
            raise SystemExit("multi-case config root must be a mapping")
        raw_cases = config.get("cases")
        if not isinstance(raw_cases, list) or not raw_cases:
            raise SystemExit("multi-case config requires a non-empty cases list")
        try:
            cases = tuple(
                CaseSpec(
                    case_id=raw_case.get("case_id"),
                    parameters=raw_case.get("parameters"),
                )
                for raw_case in raw_cases
                if isinstance(raw_case, dict)
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error
        if len(cases) != len(raw_cases):
            raise SystemExit("every case must be a mapping")
        case_ids = [case.case_id for case in cases]
        if len(case_ids) != len(set(case_ids)):
            raise SystemExit("case_id values must be unique")
    else:
        cases = (None,)

    for case in cases:
        command = [str(executable), "--config", str(config_path)]
        output_name = "native-output.txt"
        if case is not None:
            command.extend(("--case-id", case.case_id))
            output_name = f"case-{case.case_id}.stdout.txt"
        completed = subprocess.run(command, check=False, capture_output=True)
        if completed.stdout:
            (raw_dir / output_name).write_bytes(completed.stdout)
        if completed.stderr:
            sys.stderr.buffer.write(completed.stderr)
            sys.stderr.buffer.flush()
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
