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
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_agent_improvement_guide import (  # noqa: E402
    AgentImprovementGuide,
    EvidenceSummary,
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

    WORKFLOW_FIELDS = (
        "candidate_workflows",
        "workflows",
        "workflow",
        "workflow_family",
        "selected_workflow",
    )

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
        return RuntimeDashboardSummary(
            root=self.root,
            evidence=evidence,
            hook_files=hook_files,
            hook_entries=sum(non_empty_line_count(path) for path in hook_files),
            result_families=result_families,
            skill_eval_breakdown=SkillEvalBreakdownReader.read(result_families[0]),
            hook_workflow_breakdown=HookWorkflowBreakdownReader.read(hook_files),
            token_usage_breakdown=TokenUsageBreakdownReader.read(self.root),
            prompt_tool_breakdown=read_prompt_tool_breakdown(hook_files),
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
        "## Prompt And Tool Selection Evidence",
        "",
        *prompt_tool_lines(summary),
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


def failure_rate(failed: int, total: int) -> str:
    """Return a compact percent failure rate."""
    if total <= 0:
        return "unknown"
    return f"{(failed / total) * 100:.1f}%"


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
