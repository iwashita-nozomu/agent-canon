#!/usr/bin/env python3
# @dependency-start
# responsibility Generates read-only dashboards for AgentCanon runtime logs and eval results.
# upstream design ../../agents/evals/README.md eval evidence contract
# upstream design ../../agents/evals/results/README.md eval result storage contract
# upstream design ../../agents/evals/results/hook-runs/README.md hook result accumulation contract
# upstream implementation ./generate_agent_improvement_guide.py summarizes hook, memory, eval, and issue evidence
# downstream implementation ../../.github/workflows/agent-runtime-dashboard.yml publishes standalone AgentCanon dashboards
# downstream implementation ../../tests/agent_tools/test_generate_agent_runtime_dashboard.py tests dashboard rendering
# @dependency-end
"""Generate a read-only AgentCanon runtime evidence dashboard."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_agent_improvement_guide import (  # noqa: E402
    AgentImprovementGuide,
    EvidenceSummary,
    HookEvidenceCounts,
    counter_lines,
)

STATUS_RE = re.compile(r"\b[A-Z_]*STATUS=(pass|fail|skip)\b")
TOKEN_COMPARISON_RE = re.compile(
    r"baseline_total=(?P<baseline>\d+)\s+"
    r"candidate_total=(?P<candidate>\d+)\s+"
    r"token_ratio=(?P<ratio>[0-9.]+)"
)
TOKEN_MARKDOWN_RE = re.compile(
    r"baseline_total_tokens:\s*(?P<baseline>\d+).*?"
    r"candidate_total_tokens:\s*(?P<candidate>\d+).*?"
    r"token_ratio:\s*(?P<ratio>[0-9.]+)",
    re.DOTALL,
)
MAX_REPORT_LINES = 20
NO_RESET_EPOCH = 0
GIT_LOG_TIMEOUT_SECONDS = 5
COMMIT_ABBREV_CHARS = 12
PERCENT_SCALE = 100.0
UNKNOWN_RESET_BASIS = "untracked-or-unknown"
MARKDOWN_SKILL_IDS = ("md-style-check",)
MARKDOWN_TOOL_IDS = (
    "audit_and_fix_links.py",
    "check_markdown_lint.py",
    "check_markdown_math.py",
    "format_markdown.py",
    "fix_markdown_docs.py",
    "fix_markdown_headers.py",
    "run_docs_checks.sh",
)
SELECTION_RESPONSIBILITIES = ("skill", "workflow", "tool")
SELECTED_WORKFLOW_FIELDS = (
    "workflows",
    "workflow",
    "workflow_family",
    "selected_workflow",
)


@dataclass(frozen=True)
class ResultFamilySummary:
    """Summarized accumulated result files for one result family."""

    family: str
    directory: Path
    reports: tuple[Path, ...]
    failed_reports: tuple[Path, ...]
    status_counts: Counter[str]


@dataclass(frozen=True)
class SkillEvalBreakdown:
    """Per-skill eval failure attribution inferred from accumulated reports."""

    evaluated: Counter[str]
    failed: Counter[str]
    reports_missing_used_skills: int
    failed_reports_missing_used_skills: int


@dataclass(frozen=True)
class HookWorkflowBreakdown:
    """Workflow attribution inferred from hook JSONL entries."""

    workflows: Counter[str]
    workflow_events: Counter[str]
    missing_workflow_by_file: Counter[str]
    entries_with_workflow: int
    entries_without_workflow: int


@dataclass(frozen=True)
class TokenUsageBreakdown:
    """Token consumption evidence inferred from workflow monitor reports."""

    comparison_files: tuple[Path, ...]
    comparison_count: int
    baseline_total_tokens: int
    candidate_total_tokens: int
    token_ratios: tuple[float, ...]


@dataclass(frozen=True)
class PromptToolBreakdown:
    """Prompt capture and tool selection evidence inferred from hook logs."""

    prompt_entries: int
    prompt_excerpt_entries: int
    prompt_missing_excerpt_entries: int
    prompt_total_chars: int
    tool_selection_entries: int
    tools: Counter[str]
    command_verbs: Counter[str]


@dataclass(frozen=True)
class MarkdownDocsBreakdown:
    """Markdown/docs hook and eval signals inferred from accumulated evidence."""

    eval_reports: int
    failed_eval_reports: int
    candidate_skill_entries: int
    candidate_tool_entries: int
    candidate_tools: Counter[str]


@dataclass(frozen=True)
class SelectionReset:
    """Reset window for one selectable AgentCanon component."""

    reset_path: str
    reset_epoch: int
    reset_commit: str


@dataclass(frozen=True)
class SelectionMetric:
    """Selection and miss counts for one skill, workflow, or tool."""

    responsibility: str
    name: str
    selected_count: int
    candidate_count: int
    missed_count: int
    reset_path: str
    reset_at: str
    reset_commit: str


@dataclass(frozen=True)
class SelectionMetricsBreakdown:
    """Responsibility-scoped selection accuracy inferred from hook logs."""

    metrics: tuple[SelectionMetric, ...]
    entries_seen: int
    entries_with_candidates: int
    entries_with_selection: int
    filtered_observations: int


@dataclass(frozen=True)
class RuntimeDashboardSummary:
    """All evidence used by one runtime dashboard."""

    root: Path
    evidence: EvidenceSummary
    hook_files: tuple[Path, ...]
    hook_entries: int
    result_families: tuple[ResultFamilySummary, ...]
    skill_eval_breakdown: SkillEvalBreakdown
    hook_workflow_breakdown: HookWorkflowBreakdown
    token_usage_breakdown: TokenUsageBreakdown
    prompt_tool_breakdown: PromptToolBreakdown
    markdown_docs_breakdown: MarkdownDocsBreakdown
    selection_metrics_breakdown: SelectionMetricsBreakdown


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


class SkillEvalBreakdownReader:
    """Reads per-skill eval attribution from skill prompt eval reports."""

    USED_SKILLS_RE = re.compile(r"^- used_skills:\s*`([^`]*)`", re.MULTILINE)

    @classmethod
    def read(cls, family: ResultFamilySummary) -> SkillEvalBreakdown:
        """Return per-skill pass/fail attribution from one result family."""
        evaluated: Counter[str] = Counter()
        failed: Counter[str] = Counter()
        missing = 0
        failed_missing = 0
        for report in family.reports:
            status = ResultFamilyReader.report_status(report)
            skills = cls.used_skills(report)
            if not skills:
                missing += 1
                failed_missing += int(status == "fail")
                continue
            for skill in skills:
                evaluated[skill] += 1
                if status == "fail":
                    failed[skill] += 1
        return SkillEvalBreakdown(
            evaluated=evaluated,
            failed=failed,
            reports_missing_used_skills=missing,
            failed_reports_missing_used_skills=failed_missing,
        )

    @classmethod
    def used_skills(cls, report: Path) -> tuple[str, ...]:
        """Return used skills recorded in one eval report."""
        match = cls.USED_SKILLS_RE.search(report.read_text(encoding="utf-8"))
        if match is None:
            return ()
        return tuple(skill.strip() for skill in match.group(1).split(",") if skill.strip())


class HookWorkflowBreakdownReader:
    """Reads workflow attribution from accumulated hook JSONL entries."""

    WORKFLOW_FIELDS = ("candidate_workflows", *SELECTED_WORKFLOW_FIELDS)

    @classmethod
    def read(cls, hook_files: Sequence[Path]) -> HookWorkflowBreakdown:
        """Return workflow attribution for hook entries."""
        workflows: Counter[str] = Counter()
        workflow_events: Counter[str] = Counter()
        missing_by_file: Counter[str] = Counter()
        entries_with_workflow = 0
        entries_without_workflow = 0
        for hook_file in hook_files:
            for entry in cls.iter_entries(hook_file):
                names = cls.workflow_names(entry)
                if not names:
                    entries_without_workflow += 1
                    missing_by_file[hook_file.name] += 1
                    continue
                entries_with_workflow += 1
                event = str(entry.get("event") or "missing_event")
                for name in names:
                    workflows[name] += 1
                    workflow_events[f"{name}@{event}"] += 1
        return HookWorkflowBreakdown(
            workflows=workflows,
            workflow_events=workflow_events,
            missing_workflow_by_file=missing_by_file,
            entries_with_workflow=entries_with_workflow,
            entries_without_workflow=entries_without_workflow,
        )

    @staticmethod
    def iter_entries(hook_file: Path) -> tuple[dict[str, object], ...]:
        """Return parsed hook entries from one JSONL file."""
        entries: list[dict[str, object]] = []
        for line in hook_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                entries.append(cast(dict[str, object], value))
        return tuple(entries)

    @classmethod
    def workflow_names(cls, entry: dict[str, object]) -> tuple[str, ...]:
        """Return workflow names present in a hook entry."""
        names: list[str] = []
        for workflow_field in cls.WORKFLOW_FIELDS:
            names.extend(normalized_text_values(entry.get(workflow_field)))
        return tuple(dict.fromkeys(names))


class TokenUsageBreakdownReader:
    """Reads token consumption evidence from accumulated run reports."""

    @classmethod
    def read(cls, root: Path) -> TokenUsageBreakdown:
        """Return accumulated token comparison stats."""
        files: set[Path] = set()
        ratios: list[float] = []
        baseline_total = 0
        candidate_total = 0
        for path in cls.candidate_paths(root):
            text = path.read_text(encoding="utf-8")
            for baseline, candidate, ratio in cls.comparisons(text):
                files.add(path)
                baseline_total += baseline
                candidate_total += candidate
                ratios.append(ratio)
        return TokenUsageBreakdown(
            comparison_files=tuple(sorted(files)),
            comparison_count=len(ratios),
            baseline_total_tokens=baseline_total,
            candidate_total_tokens=candidate_total,
            token_ratios=tuple(ratios),
        )

    @staticmethod
    def candidate_paths(root: Path) -> tuple[Path, ...]:
        """Return likely text files containing token comparison evidence."""
        patterns = (
            "reports/agents/**/workflow_monitoring.md",
            "reports/agents/**/*token*.md",
            "agents/evals/results/**/*.md",
        )
        paths: set[Path] = set()
        for pattern in patterns:
            paths.update(path for path in root.glob(pattern) if path.is_file())
        return tuple(sorted(paths))

    @staticmethod
    def comparisons(text: str) -> tuple[tuple[int, int, float], ...]:
        """Return token comparisons found in one text blob."""
        matches: list[tuple[int, int, float]] = []
        for pattern in (TOKEN_COMPARISON_RE, TOKEN_MARKDOWN_RE):
            for match in pattern.finditer(text):
                matches.append(
                    (
                        int(match.group("baseline")),
                        int(match.group("candidate")),
                        float(match.group("ratio")),
                    )
                )
        return tuple(matches)


@dataclass
class SelectionMetricAccumulator:
    """Mutable accumulator for one selection metric."""

    responsibility: str
    name: str
    reset: SelectionReset
    selected_count: int = 0
    candidate_count: int = 0
    missed_count: int = 0

    def add_selected(self) -> None:
        """Record one confirmed selection."""
        self.selected_count += 1

    def add_candidate(self, missed: bool) -> None:
        """Record one candidate and whether it was missed in the same entry."""
        self.candidate_count += 1
        if missed:
            self.missed_count += 1

    def to_metric(self) -> SelectionMetric:
        """Return an immutable metric row."""
        return SelectionMetric(
            responsibility=self.responsibility,
            name=self.name,
            selected_count=self.selected_count,
            candidate_count=self.candidate_count,
            missed_count=self.missed_count,
            reset_path=self.reset.reset_path,
            reset_at=reset_epoch_label(self.reset.reset_epoch),
            reset_commit=self.reset.reset_commit,
        )


class SelectionMetricStore:
    """Stores selection metrics and source-path reset windows."""

    def __init__(self, root: Path) -> None:
        """Store the evidence root and initialize caches."""
        self.root = root
        self.resets: dict[tuple[str, str], SelectionReset] = {}
        self.metrics: dict[tuple[str, str], SelectionMetricAccumulator] = {}

    def add_selected(self, responsibility: str, name: str, entry_epoch: int) -> bool:
        """Add a selected component if the entry is inside its reset window."""
        metric = self.metric_for(responsibility, name)
        if not entry_inside_reset_window(entry_epoch, metric.reset):
            return False
        metric.add_selected()
        return True

    def add_candidate(
        self,
        responsibility: str,
        name: str,
        entry_epoch: int,
        missed: bool,
    ) -> bool:
        """Add a candidate component if the entry is inside its reset window."""
        metric = self.metric_for(responsibility, name)
        if not entry_inside_reset_window(entry_epoch, metric.reset):
            return False
        metric.add_candidate(missed)
        return True

    def metric_for(self, responsibility: str, name: str) -> SelectionMetricAccumulator:
        """Return a stable metric accumulator for a component."""
        key = (responsibility, name)
        if key not in self.metrics:
            reset = self.reset_for(responsibility, name)
            self.metrics[key] = SelectionMetricAccumulator(responsibility, name, reset)
        return self.metrics[key]

    def reset_for(self, responsibility: str, name: str) -> SelectionReset:
        """Return the reset window for a component."""
        key = (responsibility, name)
        if key not in self.resets:
            self.resets[key] = read_selection_reset(self.root, responsibility, name)
        return self.resets[key]

    def to_metrics(self) -> tuple[SelectionMetric, ...]:
        """Return sorted immutable metric rows."""
        rows = tuple(metric.to_metric() for metric in self.metrics.values())
        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    SELECTION_RESPONSIBILITIES.index(row.responsibility),
                    -row.missed_count,
                    -row.candidate_count,
                    row.name,
                ),
            )
        )


class SelectionMetricsReader:
    """Reads selection accuracy for skills, workflows, and tools."""

    def __init__(self, root: Path) -> None:
        """Store the AgentCanon root used to resolve reset windows."""
        self.root = root

    def read(self, hook_files: Sequence[Path]) -> SelectionMetricsBreakdown:
        """Return responsibility-scoped selection metrics."""
        store = SelectionMetricStore(self.root)
        entries_seen = 0
        entries_with_candidates = 0
        entries_with_selection = 0
        filtered_observations = 0
        for hook_file in hook_files:
            for entry in HookWorkflowBreakdownReader.iter_entries(hook_file):
                entries_seen += 1
                entry_epoch = parse_hook_timestamp(entry.get("timestamp"))
                selected = selected_by_responsibility(entry)
                candidates = candidates_by_responsibility(entry)
                entries_with_selection += int(any(selected.values()))
                entries_with_candidates += int(any(candidates.values()))
                filtered_observations += self.add_selected_components(store, selected, entry_epoch)
                filtered_observations += self.add_candidate_components(
                    store,
                    candidates,
                    selected,
                    entry_epoch,
                )
        return SelectionMetricsBreakdown(
            metrics=store.to_metrics(),
            entries_seen=entries_seen,
            entries_with_candidates=entries_with_candidates,
            entries_with_selection=entries_with_selection,
            filtered_observations=filtered_observations,
        )

    @staticmethod
    def add_selected_components(
        store: SelectionMetricStore,
        selected: dict[str, tuple[str, ...]],
        entry_epoch: int,
    ) -> int:
        """Add selected components and return filtered observation count."""
        filtered = 0
        for responsibility, names in selected.items():
            for name in names:
                if not store.add_selected(responsibility, name, entry_epoch):
                    filtered += 1
        return filtered

    @staticmethod
    def add_candidate_components(
        store: SelectionMetricStore,
        candidates: dict[str, tuple[str, ...]],
        selected: dict[str, tuple[str, ...]],
        entry_epoch: int,
    ) -> int:
        """Add candidate components and return filtered observation count."""
        filtered = 0
        for responsibility, names in candidates.items():
            selected_names = set(selected.get(responsibility, ()))
            for name in names:
                missed = name not in selected_names
                if not store.add_candidate(responsibility, name, entry_epoch, missed):
                    filtered += 1
        return filtered


class RuntimeDashboardVisuals:
    """Renders reader-facing visual dashboard sections."""

    def __init__(self, summary: RuntimeDashboardSummary) -> None:
        """Store the dashboard summary used by visual sections."""
        self.summary = summary

    def evidence_flow_lines(self) -> list[str]:
        """Return a Mermaid diagram showing how evidence flows into decisions."""
        summary = self.summary
        return [
            "```mermaid",
            "flowchart LR",
            f"  Hooks[\"Hook JSONL<br/>files: {len(summary.hook_files)}<br/>entries: {summary.hook_entries}\"]",
            f"  SkillEval[\"Skill prompt evals<br/>reports: {family_count(summary, 'skill-workflow-prompt')}\"]",
            f"  SkillFailures[\"Skill failure attribution<br/>skills: {len(summary.skill_eval_breakdown.failed)}\"]",
            f"  WorkflowHooks[\"Workflow hook attribution<br/>attributed: {summary.hook_workflow_breakdown.entries_with_workflow}<br/>missing: {summary.hook_workflow_breakdown.entries_without_workflow}\"]",
            f"  Tokens[\"Token consumption<br/>comparisons: {summary.token_usage_breakdown.comparison_count}\"]",
            f"  PromptTools[\"Prompt + tool selection<br/>prompts: {summary.prompt_tool_breakdown.prompt_entries}<br/>tools: {summary.prompt_tool_breakdown.tool_selection_entries}\"]",
            f"  Selection[\"Selection accuracy<br/>items: {len(summary.selection_metrics_breakdown.metrics)}<br/>misses: {selection_missed_total(summary)}\"]",
            f"  MarkdownDocs[\"Markdown/docs signals<br/>eval fails: {summary.markdown_docs_breakdown.failed_eval_reports}<br/>hook signals: {markdown_hook_signal_count(summary)}\"]",
            f"  WorkflowEval[\"Workflow selection evals<br/>reports: {family_count(summary, 'workflow-selection')}\"]",
            f"  ReportEval[\"Report quality evals<br/>reports: {family_count(summary, 'report-quality')}\"]",
            f"  LocalLLM[\"Local LLM evals<br/>reports: {family_count(summary, 'local-llm-responsibility')}\"]",
            f"  Issues[\"Durable issues<br/>open: {len(summary.evidence.open_issues)}<br/>closed: {len(summary.evidence.closed_issues)}\"]",
            "  Dashboard[\"Runtime dashboard<br/>read-only view\"]",
            "  Guide[\"Improvement guide<br/>next repair targets\"]",
            "  Reviewer[\"Human / PR reviewer<br/>summary + artifacts\"]",
            "  Hooks --> Dashboard",
            "  SkillEval --> Dashboard",
            "  SkillEval --> SkillFailures",
            "  SkillFailures --> Dashboard",
            "  Hooks --> WorkflowHooks",
            "  WorkflowHooks --> Dashboard",
            "  Tokens --> Dashboard",
            "  PromptTools --> Dashboard",
            "  Hooks --> Selection",
            "  PromptTools --> Selection",
            "  Selection --> Dashboard",
            "  PromptTools --> MarkdownDocs",
            "  SkillEval --> MarkdownDocs",
            "  MarkdownDocs --> Dashboard",
            "  WorkflowEval --> Dashboard",
            "  ReportEval --> Dashboard",
            "  LocalLLM --> Dashboard",
            "  Issues --> Dashboard",
            "  Dashboard --> Reviewer",
            "  Dashboard --> Guide",
            "  Issues --> Guide",
            "```",
        ]

    def action_map_lines(self) -> list[str]:
        """Return a reader-facing table that maps signals to next actions."""
        rows = (
            self.hook_row(),
            self.skill_eval_row(),
            self.skill_failure_row(),
            self.workflow_hook_row(),
            self.token_usage_row(),
            self.prompt_tool_row(),
            self.selection_metrics_row(),
            self.markdown_docs_row(),
            self.family_row(
                "workflow selection eval",
                "workflow-selection",
                "repair workflow routing examples or classifier rules",
            ),
            self.family_row(
                "report quality eval",
                "report-quality",
                "repair report-writing skill or reader-facing report outputs",
            ),
            self.family_row(
                "local LLM eval",
                "local-llm-responsibility",
                "repair single-file responsibility prompt or local model harness",
            ),
            self.issue_row(),
        )
        return [
            "| signal | state | evidence | action when attention is needed |",
            "| --- | --- | ---: | --- |",
            *rows,
        ]

    def hook_row(self) -> str:
        """Return the hook evidence action-map row."""
        failed = self.summary.evidence.hook_counts.statuses.get("fail", 0) > 0
        return action_map_row(
            "hook evidence",
            "review failing hook namespaces first",
            len(self.summary.hook_files),
            failed,
        )

    def skill_eval_row(self) -> str:
        """Return the skill prompt eval action-map row."""
        return action_map_row(
            "skill prompt eval",
            "repair skills or prompts with failed eval reports",
            len(family_by_name(self.summary, "skill-workflow-prompt").reports),
            bool(family_by_name(self.summary, "skill-workflow-prompt").failed_reports),
        )

    def skill_failure_row(self) -> str:
        """Return the skill-failure analysis action-map row."""
        breakdown = self.summary.skill_eval_breakdown
        evidence_count = sum(breakdown.evaluated.values())
        needs_attention = bool(breakdown.failed or breakdown.failed_reports_missing_used_skills)
        return action_map_row(
            "skill eval failure attribution",
            "repair failed skills; missing attribution means eval reports need used_skills",
            evidence_count,
            needs_attention,
        )

    def workflow_hook_row(self) -> str:
        """Return the workflow hook attribution action-map row."""
        breakdown = self.summary.hook_workflow_breakdown
        return action_map_row(
            "workflow hook attribution",
            "add workflow fields to hook logs when missing attribution is high",
            breakdown.entries_with_workflow,
            breakdown.entries_without_workflow > 0,
        )

    def token_usage_row(self) -> str:
        """Return the token consumption action-map row."""
        breakdown = self.summary.token_usage_breakdown
        return action_map_row(
            "token consumption",
            "record token_count comparisons when token use drives workflow design",
            breakdown.comparison_count,
            breakdown.comparison_count == 0,
        )

    def prompt_tool_row(self) -> str:
        """Return the prompt/tool selection evidence action-map row."""
        breakdown = self.summary.prompt_tool_breakdown
        evidence_count = breakdown.prompt_entries + breakdown.tool_selection_entries
        return action_map_row(
            "prompt and tool selection",
            "add prompt/tool fields to hook logs if selection analysis is missing",
            evidence_count,
            breakdown.prompt_entries == 0
            or breakdown.tool_selection_entries == 0
            or breakdown.prompt_missing_excerpt_entries > 0,
        )

    def selection_metrics_row(self) -> str:
        """Return the selection accuracy action-map row."""
        return action_map_row(
            "selection accuracy by responsibility",
            "repair routing or logging when candidate skills/workflows/tools are not selected",
            selection_candidate_total(self.summary) + selection_selected_total(self.summary),
            selection_missed_total(self.summary) > 0,
        )

    def markdown_docs_row(self) -> str:
        """Return the Markdown/docs signal action-map row."""
        breakdown = self.summary.markdown_docs_breakdown
        evidence_count = breakdown.eval_reports + markdown_hook_signal_count(self.summary)
        return action_map_row(
            "Markdown/docs hook signals",
            "add or inspect Markdown/docs hook measurements when markdown checks feel noisy",
            evidence_count,
            breakdown.failed_eval_reports > 0 or markdown_hook_signal_count(self.summary) == 0,
        )

    def family_row(self, signal: str, family_name: str, action: str) -> str:
        """Return an eval-family action-map row."""
        family = family_by_name(self.summary, family_name)
        return action_map_row(signal, action, len(family.reports), bool(family.failed_reports))

    def issue_row(self) -> str:
        """Return the durable issue action-map row."""
        return action_map_row(
            "durable issues",
            "triage open issues before claiming workflow health",
            len(self.summary.evidence.open_issues),
            bool(self.summary.evidence.open_issues),
        )


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
        result_families = (
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
        )
        skill_eval_breakdown = SkillEvalBreakdownReader.read(result_families[0])
        return RuntimeDashboardSummary(
            root=self.root,
            evidence=evidence,
            hook_files=hook_files,
            hook_entries=sum(non_empty_line_count(path) for path in hook_files),
            result_families=result_families,
            skill_eval_breakdown=skill_eval_breakdown,
            hook_workflow_breakdown=HookWorkflowBreakdownReader.read(hook_files),
            token_usage_breakdown=TokenUsageBreakdownReader.read(self.root),
            prompt_tool_breakdown=read_prompt_tool_breakdown(hook_files),
            markdown_docs_breakdown=read_markdown_docs_breakdown(
                evidence.hook_counts,
                skill_eval_breakdown,
            ),
            selection_metrics_breakdown=SelectionMetricsReader(self.root).read(hook_files),
        )


def render_dashboard_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return full dashboard lines."""
    return [
        *dashboard_header_lines(),
        *dashboard_visual_lines(summary),
        *dashboard_location_lines(summary),
        *dashboard_analysis_lines(summary),
        *dashboard_hook_lines(summary),
        "## Failed Eval Reports",
        "",
        *failed_report_lines(summary),
    ]


def render_dashboard(summary: RuntimeDashboardSummary) -> str:
    """Render the dashboard as Markdown."""
    return "\n".join(render_dashboard_lines(summary)) + "\n"


def read_prompt_tool_breakdown(hook_files: Sequence[Path]) -> PromptToolBreakdown:
    """Return prompt capture and tool-selection summary."""
    prompt = PromptToolAccumulator()
    for hook_file in hook_files:
        for entry in HookWorkflowBreakdownReader.iter_entries(hook_file):
            prompt.add_entry(entry)
    return prompt.to_breakdown()


def read_markdown_docs_breakdown(
    hook_counts: HookEvidenceCounts,
    skill_eval: SkillEvalBreakdown,
) -> MarkdownDocsBreakdown:
    """Return Markdown/docs-specific hook and eval signal counts."""
    markdown_tools = Counter(
        {
            tool: hook_counts.candidate_tools[tool]
            for tool in MARKDOWN_TOOL_IDS
            if hook_counts.candidate_tools.get(tool, 0) > 0
        }
    )
    return MarkdownDocsBreakdown(
        eval_reports=sum(skill_eval.evaluated.get(skill, 0) for skill in MARKDOWN_SKILL_IDS),
        failed_eval_reports=sum(skill_eval.failed.get(skill, 0) for skill in MARKDOWN_SKILL_IDS),
        candidate_skill_entries=sum(hook_counts.candidate_skills.get(skill, 0) for skill in MARKDOWN_SKILL_IDS),
        candidate_tool_entries=sum(markdown_tools.values()),
        candidate_tools=markdown_tools,
    )


@dataclass
class PromptToolAccumulator:
    """Mutable accumulator for prompt and tool selection evidence."""

    prompt_entries: int = 0
    prompt_excerpt_entries: int = 0
    prompt_missing_excerpt_entries: int = 0
    prompt_total_chars: int = 0
    tool_selection_entries: int = 0
    tools: Counter[str] = field(default_factory=lambda: Counter[str]())
    command_verbs: Counter[str] = field(default_factory=lambda: Counter[str]())

    def add_entry(self, entry: dict[str, object]) -> None:
        """Add prompt and tool-selection evidence from one hook entry."""
        self.add_prompt(entry)
        self.add_tool(entry)

    def add_prompt(self, entry: dict[str, object]) -> None:
        """Add prompt capture evidence from one hook entry."""
        if entry.get("prompt_capture_status") != "present":
            return
        self.prompt_entries += 1
        self.prompt_total_chars += integer_field(entry, "prompt_char_count")
        if str(entry.get("prompt_excerpt_redacted") or ""):
            self.prompt_excerpt_entries += 1
        else:
            self.prompt_missing_excerpt_entries += 1

    def add_tool(self, entry: dict[str, object]) -> None:
        """Add tool-selection evidence from one hook entry."""
        tool_name = str(entry.get("tool_name") or "")
        if tool_name:
            self.tool_selection_entries += 1
            self.tools[tool_name] += 1
        command_verb = str(entry.get("tool_command_verb") or "")
        if command_verb:
            self.command_verbs[command_verb] += 1

    def to_breakdown(self) -> PromptToolBreakdown:
        """Return immutable prompt/tool evidence."""
        return PromptToolBreakdown(
            prompt_entries=self.prompt_entries,
            prompt_excerpt_entries=self.prompt_excerpt_entries,
            prompt_missing_excerpt_entries=self.prompt_missing_excerpt_entries,
            prompt_total_chars=self.prompt_total_chars,
            tool_selection_entries=self.tool_selection_entries,
            tools=self.tools,
            command_verbs=self.command_verbs,
        )


def dashboard_header_lines() -> list[str]:
    """Return dashboard header and machine summary lines."""
    return [
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
    ]


def dashboard_visual_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return visual evidence and action map sections."""
    visuals = RuntimeDashboardVisuals(summary)
    return [
        *machine_summary_lines(summary),
        "",
        "## Visual Evidence Map",
        "",
        *visuals.evidence_flow_lines(),
        "",
        "## Action Map",
        "",
        *visuals.action_map_lines(),
        "",
        "## Issue Routing",
        "",
        *issue_routing_lines(summary),
        "",
    ]


def dashboard_location_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return evidence location and result-family sections."""
    return [
        "## Where Logs Accumulate",
        "",
        *evidence_location_lines(summary.root),
        "",
        "## Accumulated Result Families",
        "",
        *result_family_lines(summary),
        "",
    ]


def dashboard_analysis_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return skill, workflow, and token analysis sections."""
    return [
        "## Skill Eval Failure Analysis",
        "",
        "This section attributes skill prompt eval failures to the `used_skills` field in eval reports.",
        "If a failed report lacks `used_skills`, the dashboard reports missing evidence instead of guessing from file names.",
        "",
        *skill_eval_failure_lines(summary),
        "",
        "## Hook Workflow Attribution",
        "",
        "This section attributes hook entries to workflow fields present in hook JSONL.",
        "Missing attribution means the hook log did not carry enough workflow context for mechanical analysis.",
        "",
        *hook_workflow_lines(summary),
        "",
        "## Token Consumption Evidence",
        "",
        *token_usage_lines(summary),
        "",
        "## Selection Accuracy By Responsibility",
        "",
        "This section compares candidate skills, workflows, and tools against the same-entry selections recorded in hook JSONL.",
        "Counts are filtered to hook entries after the component source path's latest Git commit when a source path can be resolved.",
        "A tool miss means a candidate repo tool was not confirmed by `tool_name` or `tool_command_verb`; coarse Bash-only logs can therefore identify missing evidence rather than definite misuse.",
        "",
        *selection_metrics_lines(summary),
        "",
        "## Prompt And Tool Selection Evidence",
        "",
        *prompt_tool_lines(summary),
        "",
        "## Markdown Docs Hook Signals",
        "",
        *markdown_docs_lines(summary),
        "",
    ]


def dashboard_hook_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return hook counter sections."""
    return [
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
    ]


def non_empty_line_count(path: Path) -> int:
    """Count non-empty JSONL lines in one evidence file."""
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


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
        "- token_comparison_reports: `reports/agents/**/workflow_monitoring.md` or `reports/agents/**/*token*.md`",
        "- github_actions_dashboard: AgentCanon repository Step Summary plus uploaded artifact under `reports/agent-runtime-dashboard/` during the run",
    ]


def result_family_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return a Markdown table for accumulated result families."""
    lines = [
        "| family | path | reports | failed | status counts |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for family in summary.result_families:
        lines.append(result_family_row(summary, family))
    return lines


def result_family_row(summary: RuntimeDashboardSummary, family: ResultFamilySummary) -> str:
    """Return one accumulated result-family row."""
    cells = (
        f"`{family.family}`",
        f"`{family.directory.relative_to(summary.root).as_posix()}`",
        f"`{len(family.reports)}`",
        f"`{len(family.failed_reports)}`",
        f"`{dict(family.status_counts)}`",
    )
    return "| " + " | ".join(cells) + " |"


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


def skill_eval_failure_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return per-skill eval failure table lines."""
    breakdown = summary.skill_eval_breakdown
    lines = [
        "| skill | eval reports | failed reports | failure rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for skill in sorted(breakdown.evaluated):
        lines.append(skill_eval_failure_row(breakdown, skill))
    if not breakdown.evaluated:
        lines.append("| `_missing_used_skills` | `0` | `0` | `unknown` |")
    lines.extend(
        (
            "",
            f"- reports_missing_used_skills: `{breakdown.reports_missing_used_skills}`",
            f"- failed_reports_missing_used_skills: `{breakdown.failed_reports_missing_used_skills}`",
        )
    )
    return lines


def skill_eval_failure_row(breakdown: SkillEvalBreakdown, skill: str) -> str:
    """Return one per-skill eval failure table row."""
    total = breakdown.evaluated[skill]
    failed = breakdown.failed.get(skill, 0)
    return f"| `{skill}` | `{total}` | `{failed}` | `{failure_rate(failed, total)}` |"


def hook_workflow_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return workflow hook attribution lines."""
    breakdown = summary.hook_workflow_breakdown
    return [
        f"- hook_entries_with_workflow_attribution: `{breakdown.entries_with_workflow}`",
        f"- hook_entries_missing_workflow_attribution: `{breakdown.entries_without_workflow}`",
        "",
        "| workflow | hook entries |",
        "| --- | ---: |",
        *counter_table_rows(breakdown.workflows),
        "",
        "### Workflow Hook Events",
        "",
        "| workflow@event | hook entries |",
        "| --- | ---: |",
        *counter_table_rows(breakdown.workflow_events),
        "",
        "### Missing Workflow Attribution By Hook File",
        "",
        "| hook file | missing entries |",
        "| --- | ---: |",
        *counter_table_rows(breakdown.missing_workflow_by_file),
    ]


def token_usage_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return token consumption evidence lines."""
    breakdown = summary.token_usage_breakdown
    if breakdown.comparison_count == 0:
        return [
            "- token_comparison_status: `missing`",
            "- token_comparison_reason: `no token footprint comparison evidence found`",
            "- expected_sources: `reports/agents/**/workflow_monitoring.md`, `reports/agents/**/*token*.md`, or Codex session token_count comparisons",
        ]
    return [
        "- token_comparison_status: `present`",
        f"- token_comparison_count: `{breakdown.comparison_count}`",
        f"- baseline_total_tokens: `{breakdown.baseline_total_tokens}`",
        f"- candidate_total_tokens: `{breakdown.candidate_total_tokens}`",
        f"- average_token_ratio: `{average_ratio(breakdown.token_ratios)}`",
        "",
        "| evidence file |",
        "| --- |",
        *token_file_rows(summary),
    ]


def prompt_tool_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return prompt capture and tool-selection evidence lines."""
    breakdown = summary.prompt_tool_breakdown
    return [
        f"- prompt_entries: `{breakdown.prompt_entries}`",
        f"- prompt_excerpt_entries: `{breakdown.prompt_excerpt_entries}`",
        f"- prompt_missing_excerpt_entries: `{breakdown.prompt_missing_excerpt_entries}`",
        f"- prompt_total_chars: `{breakdown.prompt_total_chars}`",
        f"- tool_selection_entries: `{breakdown.tool_selection_entries}`",
        "",
        "### Tool Selection Counts",
        "",
        "| tool | entries |",
        "| --- | ---: |",
        *counter_table_rows(breakdown.tools),
        "",
        "### Tool Command Verbs",
        "",
        "| command verb | entries |",
        "| --- | ---: |",
        *counter_table_rows(breakdown.command_verbs),
    ]


def selection_metrics_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return selection accuracy tables by responsibility."""
    breakdown = summary.selection_metrics_breakdown
    lines = [
        f"- selection_entries_seen: `{breakdown.entries_seen}`",
        f"- selection_entries_with_candidates: `{breakdown.entries_with_candidates}`",
        f"- selection_entries_with_confirmed_selection: `{breakdown.entries_with_selection}`",
        f"- selection_filtered_observations_before_component_update: `{breakdown.filtered_observations}`",
        "",
        "| responsibility | item | selected | candidates | missed | miss rate | reset window |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    if not breakdown.metrics:
        lines.append("| `_none` | `_none` | `0` | `0` | `0` | `unknown` | `_none` |")
        return lines
    lines.extend(selection_metric_row(row) for row in breakdown.metrics)
    lines.extend(
        (
            "",
            "### Responsibility Totals",
            "",
            "| responsibility | selected | candidates | missed | miss rate |",
            "| --- | ---: | ---: | ---: | ---: |",
            *selection_responsibility_rows(summary),
        )
    )
    return lines


def selection_metric_row(row: SelectionMetric) -> str:
    """Return one responsibility-scoped selection metric row."""
    cells = (
        f"`{row.responsibility}`",
        f"`{row.name}`",
        f"`{row.selected_count}`",
        f"`{row.candidate_count}`",
        f"`{row.missed_count}`",
        f"`{failure_rate(row.missed_count, row.candidate_count)}`",
        f"`{selection_reset_label(row)}`",
    )
    return "| " + " | ".join(cells) + " |"


def selection_responsibility_rows(summary: RuntimeDashboardSummary) -> list[str]:
    """Return aggregate rows for each selectable responsibility."""
    return [
        selection_responsibility_row(summary, responsibility)
        for responsibility in SELECTION_RESPONSIBILITIES
    ]


def selection_responsibility_row(summary: RuntimeDashboardSummary, responsibility: str) -> str:
    """Return one aggregate responsibility row."""
    selected = selection_selected_total_for(summary, responsibility)
    candidates = selection_candidate_total_for(summary, responsibility)
    missed = selection_missed_total_for(summary, responsibility)
    return (
        f"| `{responsibility}` | `{selected}` | `{candidates}` | `{missed}` | "
        f"`{failure_rate(missed, candidates)}` |"
    )


def markdown_docs_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return Markdown/docs-specific hook and eval signal lines."""
    breakdown = summary.markdown_docs_breakdown
    status = "present" if markdown_hook_signal_count(summary) > 0 else "missing"
    reason = (
        "Markdown/docs prompt or tool signals are present in hook JSONL."
        if status == "present"
        else "No Markdown/docs candidate skill or docs-tool signal is present in hook JSONL yet."
    )
    return [
        f"- markdown_hook_signal_status: `{status}`",
        f"- markdown_hook_signal_reason: `{reason}`",
        f"- markdown_skill_eval_reports: `{breakdown.eval_reports}`",
        f"- markdown_failed_skill_eval_reports: `{breakdown.failed_eval_reports}`",
        f"- markdown_candidate_skill_entries: `{breakdown.candidate_skill_entries}`",
        f"- markdown_candidate_tool_entries: `{breakdown.candidate_tool_entries}`",
        "",
        "### Markdown Docs Candidate Tools",
        "",
        "| tool | hook entries |",
        "| --- | ---: |",
        *counter_table_rows(breakdown.candidate_tools),
    ]


def issue_routing_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return durable issue routes for dashboard attention signals."""
    rows = [
        issue_route_row(
            summary,
            "mcp preflight scope",
            "mcp-inventory-preflight-cache",
            "use Rust policy/cache commands for GitHub-only read versus local repo task boundaries",
        )
    ]
    if dashboard_has_evidence_gaps(summary):
        rows.append(
            issue_route_row(
                summary,
                "eval evidence gaps",
                "eval-accumulation-gaps",
                "repair missing workflow attribution, prompt capture, or token comparison evidence",
            )
        )
    rows.append(
        issue_route_row(
            summary,
            "GitHub issue mirror",
            "github-folder-issue-sync",
            "mirror durable local issues to GitHub only through explicit sync tooling",
        )
    )
    return [
        "| signal | durable issue | route reason |",
        "| --- | --- | --- |",
        *rows,
    ]


def dashboard_has_evidence_gaps(summary: RuntimeDashboardSummary) -> bool:
    """Return whether the dashboard found missing runtime evidence."""
    return (
        summary.hook_workflow_breakdown.entries_without_workflow > 0
        or summary.token_usage_breakdown.comparison_count == 0
        or summary.prompt_tool_breakdown.prompt_entries == 0
    )


def issue_route_row(summary: RuntimeDashboardSummary, signal: str, slug: str, reason: str) -> str:
    """Return one durable issue routing row."""
    issue = issue_by_slug(summary, slug)
    issue_label = (
        f"`{issue.relative_to(summary.root).as_posix()}`"
        if issue is not None
        else "`missing-local-issue`"
    )
    return f"| `{signal}` | {issue_label} | {reason} |"


def issue_by_slug(summary: RuntimeDashboardSummary, slug: str) -> Path | None:
    """Return a durable issue path whose filename contains the requested slug."""
    for issue in (*summary.evidence.open_issues, *summary.evidence.closed_issues):
        if slug in issue.name:
            return issue
    return None


def token_file_rows(summary: RuntimeDashboardSummary) -> list[str]:
    """Return bounded token evidence file rows."""
    files = summary.token_usage_breakdown.comparison_files[:MAX_REPORT_LINES]
    return [f"| `{path.relative_to(summary.root).as_posix()}` |" for path in files]


def machine_summary_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return the machine-readable summary block."""
    return [
        "AGENT_RUNTIME_DASHBOARD_STATUS=pass",
        f"AGENT_RUNTIME_DASHBOARD_EVIDENCE_ROOT={summary.root.as_posix()}",
        f"AGENT_RUNTIME_DASHBOARD_HOOK_FILES={len(summary.hook_files)}",
        f"AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES={summary.hook_entries}",
        f"AGENT_RUNTIME_DASHBOARD_SKILL_EVAL_REPORTS={family_count(summary, 'skill-workflow-prompt')}",
        f"AGENT_RUNTIME_DASHBOARD_LOCAL_LLM_REPORTS={family_count(summary, 'local-llm-responsibility')}",
        f"AGENT_RUNTIME_DASHBOARD_WORKFLOW_SELECTION_REPORTS={family_count(summary, 'workflow-selection')}",
        f"AGENT_RUNTIME_DASHBOARD_REPORT_QUALITY_REPORTS={family_count(summary, 'report-quality')}",
        f"AGENT_RUNTIME_DASHBOARD_SKILL_EVAL_FAILED_SKILLS={len(summary.skill_eval_breakdown.failed)}",
        f"AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_ATTRIBUTED={summary.hook_workflow_breakdown.entries_with_workflow}",
        f"AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING={summary.hook_workflow_breakdown.entries_without_workflow}",
        f"AGENT_RUNTIME_DASHBOARD_TOKEN_COMPARISONS={summary.token_usage_breakdown.comparison_count}",
        f"AGENT_RUNTIME_DASHBOARD_PROMPT_ENTRIES={summary.prompt_tool_breakdown.prompt_entries}",
        f"AGENT_RUNTIME_DASHBOARD_TOOL_SELECTION_ENTRIES={summary.prompt_tool_breakdown.tool_selection_entries}",
        f"AGENT_RUNTIME_DASHBOARD_SELECTION_ITEMS={len(summary.selection_metrics_breakdown.metrics)}",
        f"AGENT_RUNTIME_DASHBOARD_SELECTION_SELECTED={selection_selected_total(summary)}",
        f"AGENT_RUNTIME_DASHBOARD_SELECTION_CANDIDATES={selection_candidate_total(summary)}",
        f"AGENT_RUNTIME_DASHBOARD_SELECTION_MISSES={selection_missed_total(summary)}",
        f"AGENT_RUNTIME_DASHBOARD_SKILL_SELECTION_MISS_RATE={selection_miss_rate(summary, 'skill')}",
        f"AGENT_RUNTIME_DASHBOARD_WORKFLOW_SELECTION_MISS_RATE={selection_miss_rate(summary, 'workflow')}",
        f"AGENT_RUNTIME_DASHBOARD_TOOL_SELECTION_MISS_RATE={selection_miss_rate(summary, 'tool')}",
        f"AGENT_RUNTIME_DASHBOARD_MARKDOWN_EVAL_REPORTS={summary.markdown_docs_breakdown.eval_reports}",
        f"AGENT_RUNTIME_DASHBOARD_MARKDOWN_EVAL_FAILURES={summary.markdown_docs_breakdown.failed_eval_reports}",
        f"AGENT_RUNTIME_DASHBOARD_MARKDOWN_HOOK_SIGNALS={markdown_hook_signal_count(summary)}",
        f"AGENT_RUNTIME_DASHBOARD_OPEN_ISSUES={len(summary.evidence.open_issues)}",
        f"AGENT_RUNTIME_DASHBOARD_CLOSED_ISSUES={len(summary.evidence.closed_issues)}",
    ]


def family_count(summary: RuntimeDashboardSummary, family_name: str) -> int:
    """Return report count for one result family."""
    return len(family_by_name(summary, family_name).reports)


def family_by_name(
    summary: RuntimeDashboardSummary,
    family_name: str,
) -> ResultFamilySummary:
    """Return one result family summary by name."""
    for family in summary.result_families:
        if family.family == family_name:
            return family
    raise KeyError(family_name)


def action_map_row(
    signal: str,
    action: str,
    evidence_count: int,
    needs_attention: bool,
) -> str:
    """Return one action-map table row."""
    if evidence_count == 0:
        state = "missing"
    elif needs_attention:
        state = "attention"
    else:
        state = "healthy"
    return f"| {signal} | `{state}` | `{evidence_count}` | {action} |"


def markdown_hook_signal_count(summary: RuntimeDashboardSummary) -> int:
    """Return total Markdown/docs candidate hook signals."""
    breakdown = summary.markdown_docs_breakdown
    return breakdown.candidate_skill_entries + breakdown.candidate_tool_entries


def selection_selected_total(summary: RuntimeDashboardSummary) -> int:
    """Return total selected count for all responsibilities."""
    return sum(row.selected_count for row in summary.selection_metrics_breakdown.metrics)


def selection_candidate_total(summary: RuntimeDashboardSummary) -> int:
    """Return total candidate count for all responsibilities."""
    return sum(row.candidate_count for row in summary.selection_metrics_breakdown.metrics)


def selection_missed_total(summary: RuntimeDashboardSummary) -> int:
    """Return total missed candidate count for all responsibilities."""
    return sum(row.missed_count for row in summary.selection_metrics_breakdown.metrics)


def selection_selected_total_for(summary: RuntimeDashboardSummary, responsibility: str) -> int:
    """Return selected count for one responsibility."""
    return sum(
        row.selected_count
        for row in summary.selection_metrics_breakdown.metrics
        if row.responsibility == responsibility
    )


def selection_candidate_total_for(summary: RuntimeDashboardSummary, responsibility: str) -> int:
    """Return candidate count for one responsibility."""
    return sum(
        row.candidate_count
        for row in summary.selection_metrics_breakdown.metrics
        if row.responsibility == responsibility
    )


def selection_missed_total_for(summary: RuntimeDashboardSummary, responsibility: str) -> int:
    """Return missed candidate count for one responsibility."""
    return sum(
        row.missed_count
        for row in summary.selection_metrics_breakdown.metrics
        if row.responsibility == responsibility
    )


def selection_miss_rate(summary: RuntimeDashboardSummary, responsibility: str) -> str:
    """Return candidate miss rate for one responsibility."""
    return failure_rate(
        selection_missed_total_for(summary, responsibility),
        selection_candidate_total_for(summary, responsibility),
    )


def selection_reset_label(row: SelectionMetric) -> str:
    """Return a compact reset-window label for one selection row."""
    if row.reset_path == UNKNOWN_RESET_BASIS:
        return UNKNOWN_RESET_BASIS
    return f"{row.reset_at} {row.reset_commit} {row.reset_path}"


def normalized_text_values(value: object) -> tuple[str, ...]:
    """Return non-empty string values from a string or list-like field."""
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, list):
        return ()
    return tuple(item for item in cast(list[object], value) if isinstance(item, str) and item)


def integer_field(entry: dict[str, object], key: str) -> int:
    """Return an integer field from a hook entry."""
    value = entry.get(key)
    return value if isinstance(value, int) else 0


def selected_by_responsibility(entry: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Return selected skills, workflows, and tools from one hook entry."""
    return {
        "skill": normalized_text_values(entry.get("skills")),
        "workflow": selected_workflow_values(entry),
        "tool": selected_tool_values(entry),
    }


def candidates_by_responsibility(entry: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Return candidate skills, workflows, and tools from one hook entry."""
    return {
        "skill": normalized_text_values(entry.get("candidate_skills")),
        "workflow": normalized_text_values(entry.get("candidate_workflows")),
        "tool": normalized_text_values(entry.get("candidate_tools")),
    }


def selected_workflow_values(entry: dict[str, object]) -> tuple[str, ...]:
    """Return selected workflow names from one hook entry."""
    names: list[str] = []
    for workflow_field in SELECTED_WORKFLOW_FIELDS:
        names.extend(normalized_text_values(entry.get(workflow_field)))
    return unique_text_values(names)


def selected_tool_values(entry: dict[str, object]) -> tuple[str, ...]:
    """Return selected tool names from one hook entry."""
    names: list[str] = []
    names.extend(normalized_text_values(entry.get("tool_name")))
    names.extend(normalized_text_values(entry.get("tool_command_verb")))
    names.extend(command_tool_values(entry.get("commands")))
    return unique_text_values(names)


def command_tool_values(value: object) -> tuple[str, ...]:
    """Return command-derived tool names from a hook command result list."""
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            continue
        command = cast(dict[str, object], item).get("command")
        names.extend(command_parts_to_tool_values(command))
    return unique_text_values(names)


def command_parts_to_tool_values(value: object) -> tuple[str, ...]:
    """Return selected tool names inferred from a command array."""
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    parts = tuple(part for part in cast(list[object], value) if isinstance(part, str) and part)
    if not parts:
        return ()
    names.append(command_part_tool_name(parts[0]))
    for part in parts[1:]:
        if command_part_is_repo_tool_path(part):
            names.append(command_part_tool_name(part))
    return unique_text_values(names)


def command_part_tool_name(part: str) -> str:
    """Return a compact command or path basename for tool selection accounting."""
    if "/" not in part:
        return part
    return Path(part).name


def command_part_is_repo_tool_path(part: str) -> bool:
    """Return whether a command argument points at a repo tool script."""
    tool_path = "tools/" in part
    tool_suffix = part.endswith((".py", ".sh"))
    return tool_path and tool_suffix


def parse_hook_timestamp(value: object) -> int:
    """Return a UTC epoch second parsed from a hook timestamp field."""
    if not isinstance(value, str) or not value:
        return NO_RESET_EPOCH
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return NO_RESET_EPOCH
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def entry_inside_reset_window(entry_epoch: int, reset: SelectionReset) -> bool:
    """Return whether an event should count for a component reset window."""
    return (
        reset.reset_epoch == NO_RESET_EPOCH
        or entry_epoch == NO_RESET_EPOCH
        or entry_epoch >= reset.reset_epoch
    )


def reset_epoch_label(epoch: int) -> str:
    """Return a compact UTC reset timestamp label."""
    if epoch == NO_RESET_EPOCH:
        return UNKNOWN_RESET_BASIS
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def read_selection_reset(root: Path, responsibility: str, name: str) -> SelectionReset:
    """Return the latest source-path update window for one component."""
    resets = read_candidate_selection_resets(root, responsibility, name)
    if not resets:
        return SelectionReset(UNKNOWN_RESET_BASIS, NO_RESET_EPOCH, UNKNOWN_RESET_BASIS)
    return max(resets, key=lambda reset: reset.reset_epoch)


def read_candidate_selection_resets(
    root: Path,
    responsibility: str,
    name: str,
) -> tuple[SelectionReset, ...]:
    """Return reset windows for existing candidate source paths."""
    resets: list[SelectionReset] = []
    for relative_path in selection_source_path_candidates(responsibility, name):
        if (root / relative_path).exists():
            resets.append(read_selection_path_reset(root, relative_path))
    return tuple(resets)


def read_selection_path_reset(root: Path, relative_path: Path) -> SelectionReset:
    """Return latest Git update timestamp for an existing source path."""
    result = subprocess.run(
        [
            "git",
            "-C",
            root.as_posix(),
            "log",
            "-1",
            "--format=%ct%x00%H",
            "--",
            relative_path.as_posix(),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=GIT_LOG_TIMEOUT_SECONDS,
    )
    output = result.stdout.strip()
    if result.returncode == 0 and output:
        epoch_text, commit = output.split("\x00", maxsplit=1)
        return SelectionReset(
            relative_path.as_posix(),
            int(epoch_text),
            commit[:COMMIT_ABBREV_CHARS],
        )
    return SelectionReset(relative_path.as_posix(), NO_RESET_EPOCH, UNKNOWN_RESET_BASIS)


def selection_source_path_candidates(responsibility: str, name: str) -> tuple[Path, ...]:
    """Return likely source paths for one skill, workflow, or tool."""
    slug = name.removeprefix("$")
    if responsibility == "skill":
        return skill_source_path_candidates(slug)
    if responsibility == "workflow":
        return workflow_source_path_candidates(slug)
    if responsibility == "tool":
        return tool_source_path_candidates(slug)
    return ()


def skill_source_path_candidates(slug: str) -> tuple[Path, ...]:
    """Return likely source paths for one skill slug."""
    return (
        Path(".agents") / "skills" / slug / "SKILL.md",
        Path("agents") / "skills" / f"{slug}.md",
        Path(".claude") / "skills" / slug / "SKILL.md",
    )


def workflow_source_path_candidates(slug: str) -> tuple[Path, ...]:
    """Return likely source paths for one workflow slug."""
    return (
        Path("agents") / "workflows" / f"{slug}.md",
        Path("agents") / "workflows" / f"{slug}-workflow.md",
        Path(".agents") / "skills" / slug / "SKILL.md",
        Path("agents") / "TASK_WORKFLOWS.md",
    )


def tool_source_path_candidates(slug: str) -> tuple[Path, ...]:
    """Return likely source paths for one tool name."""
    if "/" in slug:
        return (Path(slug),)
    return (
        Path(".codex") / "hooks" / slug,
        Path("tools") / "agent_tools" / slug,
        Path("tools") / "ci" / slug,
        Path("tools") / "docs" / slug,
        Path("tools") / "oop" / "python" / slug,
        Path("tools") / slug,
    )


def unique_text_values(values: Sequence[str]) -> tuple[str, ...]:
    """Return non-empty unique text values while preserving order."""
    return tuple(dict.fromkeys(value for value in values if value))


def failure_rate(failed: int, total: int) -> str:
    """Return a compact percent failure rate."""
    if total <= 0:
        return "unknown"
    return f"{(failed / total) * PERCENT_SCALE:.1f}%"


def average_ratio(values: Sequence[float]) -> str:
    """Return a compact average ratio."""
    if not values:
        return "unknown"
    return f"{sum(values) / len(values):.3f}"


def counter_table_rows(counter: Counter[str]) -> list[str]:
    """Return table rows for a counter, or an explicit none row."""
    if not counter:
        return ["| `_none` | `0` |"]
    return [f"| `{key}` | `{value}` |" for key, value in counter.most_common(MAX_REPORT_LINES)]


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
    output.write_text(render_dashboard(summary), encoding="utf-8")
    print(f"AGENT_RUNTIME_DASHBOARD={output}")
    print("AGENT_RUNTIME_DASHBOARD_STATUS=pass")
    print(f"AGENT_RUNTIME_DASHBOARD_EVIDENCE_ROOT={summary.root.as_posix()}")
    print(f"AGENT_RUNTIME_DASHBOARD_HOOK_FILES={len(summary.hook_files)}")
    print(f"AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES={summary.hook_entries}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
