#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Classifies changed paths into runtime risk profiles and targeted validation checks.
# upstream design ../../documents/runtime-profiles-and-check-matrix.md defines profile-based validation routing.
# upstream design ../../agents/TASK_WORKFLOWS.md defines risk-scaled workflow families.
# downstream implementation ../../.github/workflows/path-risk-check-matrix-smoke.yml runs manual path/risk smoke.
# downstream design ../../documents/tools/classify_path_risk.md documents path-risk classification.
# downstream implementation ../../tests/agent_tools/test_classify_path_risk.py tests representative profiles.
# @dependency-end
"""Classify changed paths into AgentCanon runtime risk/check profiles."""

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
SHARED_CANON_PREFIXES = (".agents/", ".codex/", "agents/", "mcp/", "tools/", "documents/", "memory/", "notes/")
FULL_CONFIDENCE_PREFIXES = ("rust/", "tests/", "src/", "include/", "lib/")


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", default=[], help="Changed path. Repeatable.")
    parser.add_argument("--paths-file", help="Newline-delimited changed paths.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def normalize_paths(paths: list[str], paths_file: str | None) -> tuple[str, ...]:
    """Collect and normalize changed paths."""
    collected = list(paths)
    if paths_file:
        collected.extend(Path(paths_file).read_text(encoding="utf-8").splitlines())
    normalized: list[str] = []
    for raw_path in collected:
        path = raw_path.strip()
        if not path:
            continue
        if path.startswith("./"):
            path = path[2:]
        normalized.append(path)
    return tuple(dict.fromkeys(normalized))


def classify(paths: tuple[str, ...]) -> tuple[PathRisk, ...]:
    """Classify paths into active profile checks."""
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
                checks=(
                    "python3 tools/ci/container_config.py --root .",
                    "bash tools/ci/check_docker_build.sh",
                ),
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
    if any(path.startswith(SHARED_CANON_PREFIXES) for path in paths):
        active.append(
            PathRisk(
                profile="agentcanon-shared-surface",
                reason="shared_canon_surface_changed",
                checks=("bash tools/ci/check_agent_canon_pr.sh",),
            )
        )
    if any(path.startswith(FULL_CONFIDENCE_PREFIXES) for path in paths) or len(paths) > 20:
        active.append(
            PathRisk(
                profile="full-confidence-candidate",
                reason="source_tests_or_large_path_set_changed",
                checks=("make ci-quick", "make ci"),
            )
        )
    return tuple(dict.fromkeys(active))


def render_text(paths: tuple[str, ...], risks: tuple[PathRisk, ...]) -> str:
    """Render text output."""
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
    """Run classifier."""
    args = build_parser().parse_args()
    paths = normalize_paths(args.path, args.paths_file)
    risks = classify(paths)
    if args.format == "json":
        print(json.dumps({"paths": paths, "risks": [asdict(risk) for risk in risks]}, indent=2, sort_keys=True))
    else:
        print(render_text(paths, risks), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
