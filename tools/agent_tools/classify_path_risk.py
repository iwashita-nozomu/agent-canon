#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Classifies changed paths into runtime risk profiles and canonical static-gate execution units.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md defines profile-based validation routing.
# upstream design ../../documents/design/responsibility-rationale.md defines evidence-triggered validation selection.
# upstream design ../../agents/TASK_WORKFLOWS.md defines risk-scaled workflow families.
# downstream design ../../documents/tools/classify_path_risk.md documents path-risk classification.
# downstream implementation ../../tests/agent_tools/test_classify_path_risk.py tests representative profiles.
# downstream implementation ../../.github/workflows/agent-canon-static-gates.yml consumes unit selection without a second classifier.
# @dependency-end
"""Classify changed paths into AgentCanon risk profiles and static-gate units."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathRisk:
    """One active profile and validation route."""

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
SELECTOR_BOUNDARY_PATHS = {
    "tools/agent_tools/classify_path_risk.py",
    "tools/ci/run_standalone_static_gate_unit.sh",
    "tools/ci/check_agent_canon_pr.sh",
    ".github/workflows/agent-canon-static-gates.yml",
}
STATIC_GATE_UNITS = ("rust", "contracts", "eval", "workflow-container")


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", default=[], help="Changed path. Repeatable.")
    parser.add_argument("--paths-file", help="Newline-delimited changed paths.")
    parser.add_argument("--format", choices=("text", "json", "github-output"), default="text")
    parser.add_argument("--full-confidence", action="store_true")
    return parser


def normalize_paths(paths: list[str], paths_file: str | None) -> tuple[str, ...]:
    """Collect and normalize changed paths."""
    collected = list(paths)
    if paths_file:
        collected.extend(Path(paths_file).read_text(encoding="utf-8").splitlines())
    normalized: list[str] = []
    for raw_path in collected:
        path = raw_path.strip().removeprefix("./")
        if path:
            normalized.append(path)
    return tuple(dict.fromkeys(normalized))


def classify(paths: tuple[str, ...]) -> tuple[PathRisk, ...]:
    """Classify paths into active profile checks without selecting a second route."""
    active: list[PathRisk] = []
    if any(Path(path).suffix in DOC_SUFFIXES for path in paths):
        active.append(
            PathRisk(
                profile="docs-only-or-docs-impact",
                reason="markdown_or_text_changed",
                checks=(
                    "tools/bin/agent-canon docs check",
                    "bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header",
                ),
            )
        )
    if any(Path(path).suffix in PYTHON_SUFFIXES for path in paths):
        active.append(
            PathRisk(
                profile="python-tooling",
                reason="python_path_changed",
                checks=(
                    "python3 -m ruff check <changed-python-paths>",
                    "PYTHONPATH=tools/agent_tools python3 -m pyright <changed-python-paths>",
                    "python3 -m pytest -q <targeted-tests>",
                ),
            )
        )
    if any(path.startswith(DOCKER_PREFIXES) for path in paths):
        active.append(
            PathRisk(
                profile="docker-devcontainer",
                reason="docker_or_devcontainer_surface_changed",
                checks=("python3 tools/ci/container_config.py --root .",),
            )
        )
    if any(path.startswith(GITHUB_PREFIXES) for path in paths):
        active.append(
            PathRisk(
                profile="github-automation",
                reason="github_surface_changed",
                checks=("python3 tools/ci/check_github_workflows.py",),
            )
        )
    if any(path.startswith(EVAL_PREFIXES) for path in paths):
        active.append(
            PathRisk(
                profile="agent-eval",
                reason="eval_surface_changed",
                checks=("python3 tools/agent_tools/run_accumulated_agent_evals.py",),
            )
        )
    if any(path.startswith(RUST_PREFIXES) for path in paths):
        active.append(
            PathRisk(
                profile="rust",
                reason="rust_surface_changed",
                checks=("cargo test --manifest-path rust/agent-canon/Cargo.toml",),
            )
        )
    if any(path in DEPENDENCY_PATHS for path in paths):
        active.append(
            PathRisk(
                profile="dependency",
                reason="dependency_owner_changed",
                checks=("bash tools/agent_tools/run_repo_dependency_review.sh",),
            )
        )
    return tuple(dict.fromkeys(active))


def select_static_gate_units(
    paths: tuple[str, ...], *, full_confidence: bool = False
) -> tuple[str, ...]:
    """Map the canonical path classification to the four execution units."""
    if full_confidence or any(path in SELECTOR_BOUNDARY_PATHS for path in paths):
        return STATIC_GATE_UNITS

    profiles = {risk.profile for risk in classify(paths)}
    selected: list[str] = []
    if "rust" in profiles:
        selected.append("rust")
    if profiles & {"docs-only-or-docs-impact", "python-tooling", "dependency"}:
        selected.append("contracts")
    if "agent-eval" in profiles:
        selected.append("eval")
    if profiles & {"github-automation", "docker-devcontainer"}:
        selected.append("workflow-container")

    # Unknown repository surfaces still receive the inexpensive contract unit rather
    # than silently receiving no validation. This is fallback, not a second classifier.
    if paths and not selected:
        selected.append("contracts")
    return tuple(selected)


def render_text(paths: tuple[str, ...], risks: tuple[PathRisk, ...], units: tuple[str, ...]) -> str:
    """Render text output."""
    lines = [
        f"PATH_RISK_INPUT_COUNT={len(paths)}",
        "PATH_RISK_ACTIVE_PROFILES=" + ",".join(risk.profile for risk in risks),
        "STATIC_GATE_UNITS=" + ",".join(units),
    ]
    for risk in risks:
        lines.append(f"PATH_RISK_PROFILE={risk.profile} reason={risk.reason}")
        for check in risk.checks:
            lines.append(f"PATH_RISK_CHECK={risk.profile}:{check}")
    return "\n".join(lines) + "\n"


def render_github_output(paths: tuple[str, ...], units: tuple[str, ...]) -> str:
    """Render stable GitHub Actions outputs from the canonical unit selection."""
    selected = set(units)
    lines = [
        "units=" + ",".join(units),
        f"input_count={len(paths)}",
    ]
    for unit in STATIC_GATE_UNITS:
        key = unit.replace("-", "_")
        lines.append(f"{key}={'true' if unit in selected else 'false'}")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run classifier."""
    args = build_parser().parse_args()
    paths = normalize_paths(args.path, args.paths_file)
    risks = classify(paths)
    units = select_static_gate_units(paths, full_confidence=args.full_confidence)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "paths": paths,
                    "risks": [asdict(risk) for risk in risks],
                    "units": units,
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif args.format == "github-output":
        print(render_github_output(paths, units), end="")
    else:
        print(render_text(paths, risks, units), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
