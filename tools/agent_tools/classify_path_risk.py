#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Selects canonical changed-path validation responsibilities for AgentCanon PRs.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md defines profile-based validation routing.
# upstream design ../../documents/design/responsibility-rationale.md defines evidence-triggered validation selection.
# upstream design ../../agents/TASK_WORKFLOWS.md defines risk-scaled workflow families.
# downstream design ../../documents/tools/classify_path_risk.md documents path-risk classification.
# downstream implementation ../../tests/agent_tools/test_classify_path_risk.py tests representative profiles.
# downstream implementation ../ci/run_selected_agent_canon_pr_checks.py executes this selection without a second classifier.
# @dependency-end
"""Classify changed paths into one canonical set of validation responsibilities."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathRisk:
    """One selected semantic validation responsibility."""

    profile: str
    reason: str
    checks: tuple[str, ...]


DOC_SUFFIXES = {".md", ".rst", ".txt"}
PYTHON_SUFFIXES = {".py", ".pyi"}
DOCKER_PREFIXES = ("docker/", ".devcontainer/")
GITHUB_PREFIXES = (".github/",)
EVAL_PREFIXES = ("agents/evals/", "evidence/agent-evals/", "reports/agent-runtime-dashboard/")
RUST_PREFIXES = ("rust/",)
DEPENDENCY_PATHS = {
    "agents/skills/catalog.yaml",
    "agents/skills/skill-dependencies.yaml",
    "tools/catalog.yaml",
    "documents/tools/tool-docs.toml",
}
FULL_CONFIDENCE_PATHS = {
    "tools/agent_tools/classify_path_risk.py",
    "tools/ci/run_selected_agent_canon_pr_checks.py",
    "tools/ci/check_agent_canon_pr.sh",
    ".github/workflows/agent-canon-static-gates.yml",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", default=[], help="Changed path. Repeatable.")
    parser.add_argument("--paths-file", help="Newline-delimited changed paths.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--full-confidence",
        action="store_true",
        help="Select the canonical repository-wide validation responsibility explicitly.",
    )
    return parser


def normalize_paths(paths: list[str], paths_file: str | None) -> tuple[str, ...]:
    collected = list(paths)
    if paths_file:
        collected.extend(Path(paths_file).read_text(encoding="utf-8").splitlines())
    normalized: list[str] = []
    for raw_path in collected:
        path = raw_path.strip()
        if not path:
            continue
        path = path.removeprefix("./")
        normalized.append(path)
    return tuple(dict.fromkeys(normalized))


def _has_prefix(paths: tuple[str, ...], prefixes: tuple[str, ...]) -> bool:
    return any(path.startswith(prefixes) for path in paths)


def classify(paths: tuple[str, ...], *, full_confidence: bool = False) -> tuple[PathRisk, ...]:
    """Select responsibilities from changed paths without delegating to another classifier."""
    if full_confidence or any(path in FULL_CONFIDENCE_PATHS for path in paths):
        return (
            PathRisk(
                profile="full-confidence",
                reason="explicit_or_selector_boundary_changed",
                checks=("bash tools/ci/check_agent_canon_pr.sh",),
            ),
        )

    active: list[PathRisk] = []
    if any(Path(path).suffix in DOC_SUFFIXES for path in paths):
        active.append(
            PathRisk(
                profile="docs",
                reason="reader_facing_document_changed",
                checks=(
                    "bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header",
                    "tools/bin/agent-canon docs check",
                ),
            )
        )
    if any(Path(path).suffix in PYTHON_SUFFIXES for path in paths):
        active.append(
            PathRisk(
                profile="python",
                reason="python_runtime_or_tooling_changed",
                checks=(
                    "python3 -m ruff check <changed-python-paths>",
                    "PYTHONPATH=tools/agent_tools python3 -m pyright <changed-python-paths>",
                    "python3 -m pytest -q <targeted-python-tests>",
                ),
            )
        )
    if _has_prefix(paths, DOCKER_PREFIXES):
        active.append(
            PathRisk(
                profile="container",
                reason="docker_or_devcontainer_contract_changed",
                checks=(
                    "python3 tools/ci/container_config.py --root .",
                    "bash tools/ci/check_docker_build.sh",
                ),
            )
        )
    if _has_prefix(paths, GITHUB_PREFIXES):
        active.append(
            PathRisk(
                profile="workflow",
                reason="github_automation_changed",
                checks=("python3 tools/ci/check_github_workflows.py",),
            )
        )
    if _has_prefix(paths, EVAL_PREFIXES):
        active.append(
            PathRisk(
                profile="eval",
                reason="eval_schema_or_producer_changed",
                checks=(
                    "python3 tools/agent_tools/run_accumulated_agent_evals.py --root . --run-id selected-pr-gate",
                    "python3 tools/agent_tools/eval_accumulation_check.py --root .",
                ),
            )
        )
    if _has_prefix(paths, RUST_PREFIXES):
        active.append(
            PathRisk(
                profile="rust",
                reason="rust_source_changed",
                checks=(
                    "cargo fmt --manifest-path rust/agent-canon/Cargo.toml -- --check",
                    "cargo clippy --manifest-path rust/agent-canon/Cargo.toml --all-targets -- -D warnings",
                    "cargo test --manifest-path rust/agent-canon/Cargo.toml",
                ),
            )
        )
    if any(path in DEPENDENCY_PATHS for path in paths):
        active.append(
            PathRisk(
                profile="dependency",
                reason="catalog_or_dependency_owner_changed",
                checks=("bash tools/agent_tools/run_repo_dependency_review.sh",),
            )
        )

    # Preserve first occurrence order while deduplicating identical responsibilities.
    return tuple(dict.fromkeys(active))


def render_text(paths: tuple[str, ...], risks: tuple[PathRisk, ...]) -> str:
    lines = [
        f"PATH_RISK_INPUT_COUNT={len(paths)}",
        "PATH_RISK_ACTIVE_PROFILES=" + ",".join(risk.profile for risk in risks),
    ]
    for risk in risks:
        lines.append(f"PATH_RISK_PROFILE={risk.profile} reason={risk.reason}")
        for check in risk.checks:
            lines.append(f"PATH_RISK_CHECK={risk.profile}:{check}")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = build_parser().parse_args()
    paths = normalize_paths(args.path, args.paths_file)
    risks = classify(paths, full_confidence=args.full_confidence)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "paths": paths,
                    "risks": [asdict(risk) for risk in risks],
                    "profiles": [risk.profile for risk in risks],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(render_text(paths, risks), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
