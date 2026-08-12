#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Executes the canonical changed-path validation selection without reclassifying paths.
# upstream design ../../documents/design/responsibility-rationale.md selected-validation execution boundary
# upstream implementation ../agent_tools/classify_path_risk.py sole changed-path validation selector
# upstream implementation ./check_agent_canon_pr.sh full-confidence executor retained for explicit/manual/cross-surface validation
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml invokes this selected executor for pull requests
# @dependency-end
"""Execute only validation responsibilities selected by classify_path_risk.py."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from agent_tools.classify_path_risk import PathRisk, classify, normalize_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths-file", required=True)
    parser.add_argument("--full-confidence", action="store_true")
    parser.add_argument("--print-only", action="store_true")
    return parser


def _changed_python(paths: tuple[str, ...]) -> list[str]:
    return [path for path in paths if Path(path).suffix in {".py", ".pyi"} and Path(path).exists()]


def _targeted_python_tests(paths: tuple[str, ...]) -> list[str]:
    tests: list[str] = []
    for raw in paths:
        path = Path(raw)
        if path.suffix not in {".py", ".pyi"}:
            continue
        if raw.startswith("tests/") and path.exists():
            tests.append(raw)
            continue
        if raw.startswith("tools/agent_tools/"):
            candidate = Path("tests/agent_tools") / f"test_{path.stem}.py"
            if candidate.exists():
                tests.append(candidate.as_posix())
    return list(dict.fromkeys(tests))


def _run(command: list[str], *, print_only: bool) -> None:
    print("SELECTED_VALIDATION_COMMAND=" + " ".join(command), flush=True)
    if not print_only:
        subprocess.run(command, check=True)


def execute(paths: tuple[str, ...], risks: tuple[PathRisk, ...], *, print_only: bool) -> None:
    profiles = {risk.profile for risk in risks}
    print("SELECTED_VALIDATION_PROFILES=" + ",".join(risk.profile for risk in risks), flush=True)

    if "full-confidence" in profiles:
        _run(["bash", "tools/ci/check_agent_canon_pr.sh"], print_only=print_only)
        return

    if "docs" in profiles:
        _run(
            ["bash", "tools/agent_tools/check_dependency_header_format.sh", "--changed", "--require-header"],
            print_only=print_only,
        )

    if "python" in profiles:
        changed_python = _changed_python(paths)
        if changed_python:
            _run(["python3", "-m", "ruff", "check", *changed_python], print_only=print_only)
            _run(
                ["python3", "-m", "pyright", *changed_python],
                print_only=print_only,
            )
            targeted_tests = _targeted_python_tests(paths)
            if targeted_tests:
                _run(["python3", "-m", "pytest", "-q", *targeted_tests], print_only=print_only)

    if "container" in profiles:
        _run(["python3", "tools/ci/container_config.py", "--root", "."], print_only=print_only)
        _run(["bash", "tools/ci/check_docker_build.sh"], print_only=print_only)

    if "workflow" in profiles:
        _run(["python3", "tools/ci/check_github_workflows.py"], print_only=print_only)

    if "eval" in profiles:
        _run(
            [
                "python3",
                "tools/agent_tools/run_accumulated_agent_evals.py",
                "--root",
                ".",
                "--run-id",
                "selected-pr-gate",
            ],
            print_only=print_only,
        )
        _run(
            ["python3", "tools/agent_tools/eval_accumulation_check.py", "--root", "."],
            print_only=print_only,
        )

    if "rust" in profiles:
        _run(
            ["cargo", "fmt", "--manifest-path", "rust/agent-canon/Cargo.toml", "--", "--check"],
            print_only=print_only,
        )
        _run(
            [
                "cargo",
                "clippy",
                "--manifest-path",
                "rust/agent-canon/Cargo.toml",
                "--all-targets",
                "--",
                "-D",
                "warnings",
            ],
            print_only=print_only,
        )
        _run(
            ["cargo", "test", "--manifest-path", "rust/agent-canon/Cargo.toml"],
            print_only=print_only,
        )

    if "dependency" in profiles:
        _run(["bash", "tools/agent_tools/run_repo_dependency_review.sh"], print_only=print_only)


def main() -> int:
    args = build_parser().parse_args()
    paths = normalize_paths([], args.paths_file)
    risks = classify(paths, full_confidence=args.full_confidence)
    print(
        "SELECTED_VALIDATION="
        + json.dumps(
            {
                "paths": paths,
                "profiles": [risk.profile for risk in risks],
                "reasons": [risk.reason for risk in risks],
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    execute(paths, risks, print_only=args.print_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
