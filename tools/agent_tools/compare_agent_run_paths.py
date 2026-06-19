#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Compares two agent run paths and flags inefficient route selection.
# upstream design ../../agents/workflows/adaptive-improvement-workflow.md rerun comparison  # noqa: E501
# upstream design ../../agents/templates/workflow_monitoring.md records path events
# downstream implementation ../../tests/agent_tools/test_compare_agent_run_paths.py tests it  # noqa: E501
# @dependency-end
"""Compare two workflow-monitoring paths for route efficiency feedback."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ROUTE_RE = re.compile(r"\bexecution_path=([A-Za-z0-9_.:-]+)")
EFFICIENCY_RE = re.compile(r"\broute_efficiency=([A-Za-z0-9_.:-]+)")
STATIC_RE = re.compile(r"\bstatic_analysis_feedback=([A-Za-z0-9_.:-]+)")
INEFFICIENT_VALUES = {"inefficient", "wasteful", "avoidable", "slow_path"}
EFFICIENT_VALUES = {"efficient", "preferred", "acceptable"}


@dataclass(frozen=True)
class RunPath:
    """Comparable path evidence from one run bundle."""

    label: str
    path: Path
    execution_path: str
    route_efficiency: str
    static_analysis_feedback: str

    @property
    def inefficient(self) -> bool:
        """Return whether the run selected a known inefficient path."""
        return self.route_efficiency in INEFFICIENT_VALUES


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Compare two run bundle execution paths."
    )
    parser.add_argument("--baseline-run", required=True, help="Baseline run bundle.")
    parser.add_argument("--candidate-run", required=True, help="Candidate run bundle.")
    parser.add_argument(
        "--report-out",
        help="Optional Markdown report path for the comparison.",
    )
    return parser


def monitoring_path(run_dir: Path) -> Path:
    """Return the workflow monitoring path for a run bundle."""
    return run_dir / "workflow_monitoring.md"


def first_match(pattern: re.Pattern[str], text: str) -> str:
    """Return the first normalized regex capture or an empty string."""
    match = pattern.search(text)
    return match.group(1).strip().lower() if match else ""


def read_run_path(label: str, run_dir: Path) -> RunPath:
    """Read path-comparison evidence from one run bundle."""
    path = monitoring_path(run_dir)
    text = path.read_text(encoding="utf-8").lower() if path.is_file() else ""
    return RunPath(
        label=label,
        path=run_dir,
        execution_path=first_match(ROUTE_RE, text),
        route_efficiency=first_match(EFFICIENCY_RE, text),
        static_analysis_feedback=first_match(STATIC_RE, text),
    )


def paths_differ(left: RunPath, right: RunPath) -> bool:
    """Return whether the comparable execution path changed."""
    return bool(left.execution_path or right.execution_path) and (
        left.execution_path != right.execution_path
    )


def selected_path(left: RunPath, right: RunPath) -> RunPath:
    """Return the candidate path as the selected path."""
    _ = left
    return right


def comparison_status(left: RunPath, right: RunPath) -> str:
    """Return pass/fail status for the path comparison."""
    selected = selected_path(left, right)
    if selected.inefficient:
        return "fail"
    return "pass"


def render_report(left: RunPath, right: RunPath) -> str:
    """Render a Markdown comparison report."""
    status = comparison_status(left, right)
    selected = selected_path(left, right)
    lines = [
        "# Agent Run Path Comparison",
        "<!--",
        "@dependency-start",
        "responsibility Records two-run execution path comparison evidence.",
        "upstream implementation ../../tools/agent_tools/"
        "compare_agent_run_paths.py generates this report",
        "@dependency-end",
        "-->",
        "",
        "## Summary",
        "",
        f"- comparison_status: {status}",
        f"- paths_differ: {'yes' if paths_differ(left, right) else 'no'}",
        f"- selected_execution_path: {selected.execution_path or 'unknown'}",
        f"- selected_route_efficiency: {selected.route_efficiency or 'unknown'}",
        "",
        "## Runs",
        "",
        "| Label | Run Directory | execution_path | route_efficiency | "
        "static_analysis_feedback |",
        "| ----- | ------------- | -------------- | ---------------- | "
        "------------------------ |",
        run_row(left),
        run_row(right),
        "",
        "## Workflow Monitoring Tokens",
        "",
        f"- execution_path_comparison={status}",
        (
            "- selected_inefficient_route=yes"
            if selected.inefficient
            else "- selected_inefficient_route=no"
        ),
        f"- route_efficiency={selected.route_efficiency or 'unknown'}",
        (
            "- static_analysis_feedback=missing"
            if not selected.static_analysis_feedback
            else f"- static_analysis_feedback={selected.static_analysis_feedback}"
        ),
        "",
    ]
    return "\n".join(lines)


def run_row(path: RunPath) -> str:
    """Render one report table row."""
    return (
        f"| {path.label} | {path.path} | {path.execution_path or 'unknown'} | "
        f"{path.route_efficiency or 'unknown'} | "
        f"{path.static_analysis_feedback or 'missing'} |"
    )


def print_machine_status(left: RunPath, right: RunPath) -> None:
    """Print grep-friendly comparison status."""
    status = comparison_status(left, right)
    selected = selected_path(left, right)
    print(f"RUN_PATH_COMPARISON={status}")
    print(f"RUN_PATHS_DIFFER={'yes' if paths_differ(left, right) else 'no'}")
    print(f"BASELINE_EXECUTION_PATH={left.execution_path or 'unknown'}")
    print(f"CANDIDATE_EXECUTION_PATH={right.execution_path or 'unknown'}")
    print(f"SELECTED_ROUTE_EFFICIENCY={selected.route_efficiency or 'unknown'}")
    print(
        "SELECTED_INEFFICIENT_ROUTE="
        f"{'yes' if selected.inefficient else 'no'}"
    )
    if not selected.static_analysis_feedback:
        print("STATIC_ANALYSIS_FEEDBACK=missing")
    else:
        print(f"STATIC_ANALYSIS_FEEDBACK={selected.static_analysis_feedback}")
    print(f"NEXT_ACTION={next_action(left, right)}")


def next_action(left: RunPath, right: RunPath) -> str:
    """Return the next action for workflow repair."""
    if selected_path(left, right).inefficient:
        return "repair_skill_workflow_prompt"
    if not selected_path(left, right).static_analysis_feedback:
        return "record_static_analysis_feedback"
    return "record_comparison_and_continue"


def main() -> int:
    """Run the comparison CLI."""
    args = build_parser().parse_args()
    baseline = read_run_path("baseline", Path(str(args.baseline_run)).resolve())
    candidate = read_run_path("candidate", Path(str(args.candidate_run)).resolve())
    if args.report_out:
        report_path = Path(str(args.report_out))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(baseline, candidate), encoding="utf-8")
    print_machine_status(baseline, candidate)
    return 1 if comparison_status(baseline, candidate) == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
