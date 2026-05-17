#!/usr/bin/env python3
# @dependency-start
# responsibility Generates read-only dashboards for AgentCanon runtime logs and eval results.
# upstream design ../../agents/evals/README.md eval evidence contract
# upstream design ../../agents/evals/results/README.md eval result storage contract
# upstream design ../../agents/evals/results/hook-runs/README.md hook result accumulation contract
# upstream implementation ./generate_agent_improvement_guide.py summarizes hook, memory, eval, and issue evidence
# downstream implementation ../../.github/workflows/agent-runtime-dashboard.yml publishes PR and push dashboards
# downstream implementation ../../tests/agent_tools/test_generate_agent_runtime_dashboard.py tests dashboard rendering
# @dependency-end
"""Generate a read-only AgentCanon runtime evidence dashboard."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_agent_improvement_guide import (  # noqa: E402
    AgentImprovementGuide,
    EvidenceSummary,
    counter_lines,
)

STATUS_RE = re.compile(r"\b[A-Z_]*STATUS=(pass|fail|skip)\b")
MAX_REPORT_LINES = 20


@dataclass(frozen=True)
class ResultFamilySummary:
    """Summarized accumulated result files for one result family."""

    family: str
    directory: Path
    reports: tuple[Path, ...]
    failed_reports: tuple[Path, ...]
    status_counts: Counter[str]


@dataclass(frozen=True)
class RuntimeDashboardSummary:
    """All evidence used by one runtime dashboard."""

    root: Path
    evidence: EvidenceSummary
    hook_files: tuple[Path, ...]
    hook_entries: int
    result_families: tuple[ResultFamilySummary, ...]


class ResultFamilyReader:
    """Reads accumulated Markdown result families."""

    def __init__(self, root: Path) -> None:
        """Store the AgentCanon evidence root."""
        self.root = root

    def read_family(self, family: str, relative_dir: str) -> ResultFamilySummary:
        """Read one accumulated Markdown report directory."""
        directory = self.root / relative_dir
        reports = tuple(sorted(path for path in directory.glob("*.md") if path.name != "README.md"))
        status_counts: Counter[str] = Counter()
        failed_reports: list[Path] = []
        for report in reports:
            status = self.report_status(report)
            status_counts[status] += 1
            if status == "fail":
                failed_reports.append(report)
        return ResultFamilySummary(
            family=family,
            directory=directory,
            reports=reports,
            failed_reports=tuple(failed_reports),
            status_counts=status_counts,
        )

    @staticmethod
    def report_status(path: Path) -> str:
        """Return the report status inferred from file name or machine tokens."""
        if "-fail" in path.name:
            return "fail"
        if "-skip" in path.name:
            return "skip"
        if "-pass" in path.name:
            return "pass"
        text = path.read_text(encoding="utf-8")
        match = STATUS_RE.search(text)
        return match.group(1) if match else "unknown"


class AgentRuntimeDashboard:
    """Builds a reader-facing dashboard from AgentCanon runtime evidence."""

    def __init__(self, root: Path) -> None:
        """Resolve the requested root to the AgentCanon evidence root."""
        self.guide = AgentImprovementGuide(root)
        self.root = self.guide.root

    def collect(self) -> RuntimeDashboardSummary:
        """Collect dashboard evidence without mutating repository state."""
        evidence = self.guide.collect()
        hook_files = self.guide.hook_result_paths()
        reader = ResultFamilyReader(self.root)
        return RuntimeDashboardSummary(
            root=self.root,
            evidence=evidence,
            hook_files=hook_files,
            hook_entries=sum(self.non_empty_line_count(path) for path in hook_files),
            result_families=(
                reader.read_family(
                    "skill-workflow-prompt",
                    "agents/evals/results/skill-workflow-prompt",
                ),
                reader.read_family(
                    "local-llm-responsibility",
                    "agents/evals/results/local-llm-responsibility",
                ),
                reader.read_family(
                    "workflow-selection",
                    "agents/evals/results/workflow-selection",
                ),
                reader.read_family(
                    "report-quality",
                    "agents/evals/results/report-quality",
                ),
            ),
        )

    def render(self, summary: RuntimeDashboardSummary) -> str:
        """Render the dashboard as Markdown."""
        lines = [
            "# Agent Runtime Dashboard",
            "",
            "<!--",
            "@dependency-start",
            "responsibility Records generated read-only AgentCanon runtime evidence dashboard.",
            "upstream implementation tools/agent_tools/generate_agent_runtime_dashboard.py generates this report",
            "@dependency-end",
            "-->",
            "",
            "This report is a read-only view over accumulated AgentCanon evidence.",
            "It tells humans and PR reviewers where logs live and what signals have",
            "been collected; it does not create GitHub Issues or rewrite skills,",
            "workflows, tools, hooks, or memory.",
            "",
            "## Machine Summary",
            "",
            "AGENT_RUNTIME_DASHBOARD_STATUS=pass",
            f"AGENT_RUNTIME_DASHBOARD_EVIDENCE_ROOT={summary.root.as_posix()}",
            f"AGENT_RUNTIME_DASHBOARD_HOOK_FILES={len(summary.hook_files)}",
            f"AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES={summary.hook_entries}",
            f"AGENT_RUNTIME_DASHBOARD_SKILL_EVAL_REPORTS={len(summary.evidence.skill_eval_reports)}",
            f"AGENT_RUNTIME_DASHBOARD_LOCAL_LLM_REPORTS={self.family_count(summary, 'local-llm-responsibility')}",
            f"AGENT_RUNTIME_DASHBOARD_WORKFLOW_SELECTION_REPORTS={self.family_count(summary, 'workflow-selection')}",
            f"AGENT_RUNTIME_DASHBOARD_REPORT_QUALITY_REPORTS={self.family_count(summary, 'report-quality')}",
            f"AGENT_RUNTIME_DASHBOARD_OPEN_ISSUES={len(summary.evidence.open_issues)}",
            f"AGENT_RUNTIME_DASHBOARD_CLOSED_ISSUES={len(summary.evidence.closed_issues)}",
            "",
            "## Where Logs Accumulate",
            "",
            *self.evidence_location_lines(summary.root),
            "",
            "## Accumulated Result Families",
            "",
            *self.result_family_lines(summary),
            "",
            "## Hook Summary",
            "",
            f"- hook_jsonl_files: `{len(summary.hook_files)}`",
            f"- hook_jsonl_entries: `{summary.hook_entries}`",
            f"- status_counts: `{dict(summary.evidence.hook_counts.statuses)}`",
            f"- event_counts: `{dict(summary.evidence.hook_counts.events)}`",
            "",
            "## Hook Runtime Namespaces",
            "",
            *counter_lines(summary.evidence.hook_counts.namespaces),
            "",
            "## Skill Usage",
            "",
            *counter_lines(summary.evidence.hook_counts.skills),
            "",
            "## Prompt Candidate Workflows",
            "",
            *counter_lines(summary.evidence.hook_counts.candidate_workflows),
            "",
            "## Prompt Candidate Tools",
            "",
            *counter_lines(summary.evidence.hook_counts.candidate_tools),
            "",
            "## Human Feedback Signals",
            "",
            *counter_lines(summary.evidence.hook_counts.feedback_labels),
            "",
            "## Hook Quality Counters",
            "",
            *counter_lines(summary.evidence.hook_counts.quality),
            "",
            "## Failed Eval Reports",
            "",
            *self.failed_report_lines(summary),
        ]
        return "\n".join(lines) + "\n"

    @staticmethod
    def non_empty_line_count(path: Path) -> int:
        """Count non-empty JSONL lines in one evidence file."""
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    @staticmethod
    def family_count(summary: RuntimeDashboardSummary, family_name: str) -> int:
        """Return report count for one result family."""
        for family in summary.result_families:
            if family.family == family_name:
                return len(family.reports)
        return 0

    @staticmethod
    def evidence_location_lines(root: Path) -> list[str]:
        """Return the canonical runtime evidence locations."""
        return [
            f"- evidence_root: `{root.as_posix()}`",
            "- hook_jsonl: `agents/evals/results/hook-runs/<runtime-namespace>/<hook-name>.jsonl`",
            "- skill_prompt_eval_reports: `agents/evals/results/skill-workflow-prompt/<eval-run-id>-<status>-<skill-slug>.md`",
            "- local_llm_eval_reports: `agents/evals/results/local-llm-responsibility/<eval-run-id>-<status>.md`",
            "- workflow_selection_eval_reports: `agents/evals/results/workflow-selection/<eval-run-id>-<status>.md`",
            "- report_quality_eval_reports: `agents/evals/results/report-quality/<eval-run-id>-<status>.md`",
            "- durable_issues: `issues/open/AC-*.md` and `issues/closed/AC-*.md`",
            "- shared_memory: `memory/USER_PREFERENCES.md` and `memory/AGENT_PHILOSOPHY.md`",
            "- github_actions_dashboard: Step Summary plus uploaded artifact under `reports/agent-runtime-dashboard/` during the run",
        ]

    @staticmethod
    def result_family_lines(summary: RuntimeDashboardSummary) -> list[str]:
        """Return a Markdown table for accumulated result families."""
        lines = [
            "| family | path | reports | failed | status counts |",
            "| --- | --- | ---: | ---: | --- |",
        ]
        for family in summary.result_families:
            lines.append(
                "| "
                + " | ".join(
                    (
                        f"`{family.family}`",
                        f"`{family.directory.relative_to(summary.root).as_posix()}`",
                        f"`{len(family.reports)}`",
                        f"`{len(family.failed_reports)}`",
                        f"`{dict(family.status_counts)}`",
                    )
                )
                + " |"
            )
        return lines

    @staticmethod
    def failed_report_lines(summary: RuntimeDashboardSummary) -> list[str]:
        """Return bounded failed-report bullets."""
        reports = list(summary.evidence.failed_skill_eval_reports)
        for family in summary.result_families:
            reports.extend(family.failed_reports)
        if not reports:
            return ["- none"]
        return [
            f"- `{path.relative_to(summary.root).as_posix()}`"
            for path in sorted(set(reports))[:MAX_REPORT_LINES]
        ]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--out",
        default="reports/agent-runtime-dashboard/agent-runtime-dashboard.md",
        help="Markdown output path.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate an AgentCanon runtime dashboard."""
    args = build_parser().parse_args(argv)
    dashboard = AgentRuntimeDashboard(args.root)
    summary = dashboard.collect()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dashboard.render(summary), encoding="utf-8")
    print(f"AGENT_RUNTIME_DASHBOARD={output}")
    print("AGENT_RUNTIME_DASHBOARD_STATUS=pass")
    print(f"AGENT_RUNTIME_DASHBOARD_EVIDENCE_ROOT={summary.root.as_posix()}")
    print(f"AGENT_RUNTIME_DASHBOARD_HOOK_FILES={len(summary.hook_files)}")
    print(f"AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES={summary.hook_entries}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
