#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Generates read-only dashboards for AgentCanon runtime logs and eval results.
# upstream design ../../evidence/agent-evals/README.md eval evidence contract
# upstream design ../../documents/runtime-log-archive.md eval and hook result storage contract
# upstream design ../../references/README.md external-source capture and Markdown retention contract
# upstream implementation ./generate_agent_improvement_guide.py summarizes hook, memory, eval, and issue evidence
# upstream implementation ./runtime_log_paths.py resolves mounted archive result paths
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
import time
from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_agent_improvement_guide import (  # noqa: E402
    AgentImprovementGuide,
    EvidenceSummary,
    HookEvidenceCounter,
    HookEvidenceCounts,
    counter_lines,
    known_skill_ids,
)
from report_artifact_checks import (  # noqa: E402
    actual_wave_event_fields,
    markdown_table_dict_rows,
)
from runtime_log_paths import eval_result_search_dirs  # noqa: E402

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
TOKEN_SUMMARY_RE = re.compile(
    r"token_usage_summary=present\s+"
    r"session_count=(?P<sessions>\d+)\s+"
    r"token_event_count=(?P<events>\d+)\s+"
    r"total_tokens=(?P<total>\d+)\s+"
    r"moving_average_window=(?P<window>\d+)\s+"
    r"latest_moving_average_total=(?P<moving>[0-9.]+)\s+"
    r"average_tokens_per_event=(?P<average>[0-9.]+)"
)
TOKEN_SUMMARY_MARKDOWN_RE = re.compile(
    r"TOKEN_USAGE_SESSION_COUNT=(?P<sessions>\d+).*?"
    r"TOKEN_USAGE_TOKEN_EVENT_COUNT=(?P<events>\d+).*?"
    r"TOKEN_USAGE_TOTAL_TOKENS=(?P<total>\d+).*?"
    r"TOKEN_USAGE_AVERAGE_TOKENS_PER_EVENT=(?P<average>[0-9.]+).*?"
    r"TOKEN_USAGE_MOVING_AVERAGE_WINDOW=(?P<window>\d+).*?"
    r"TOKEN_USAGE_LATEST_MOVING_AVERAGE_TOTAL=(?P<moving>[0-9.]+)",
    re.DOTALL,
)
ISO_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
RUN_ID_TIMESTAMP_RE = re.compile(r"\d{8}T\d{6}(?:\d{6})?Z")
MAX_REPORT_LINES = 20
MAX_COMPACT_REPORT_LINES = 8
ROLLING_TREND_WINDOW = 8
UNKNOWN_SORT_ORDER = 9
NO_RESET_EPOCH = 0
GIT_LOG_TIMEOUT_SECONDS = 5
COMMIT_ABBREV_CHARS = 12
HOURS_PER_DAY = 24
MINUTES_PER_HOUR = 60
SECONDS_PER_MINUTE = 60
PERCENT_SCALE = 100.0
UNKNOWN_RESET_BASIS = "untracked-or-unknown"
HOOK_FAMILY_COMMIT_SUFFIX_RE = re.compile(r"-(?:[0-9a-f]{7,40}|no-git-head)$")
MARKDOWN_SKILL_IDS = ("md-style-check",)
MARKDOWN_TOOL_IDS = (
    "agent-canon-cli",
    "audit_and_fix_links.py",
    "fix_markdown_docs.py",
    "fix_markdown_headers.py",
    "run_docs_checks.sh",
)
TOOL_SELECTION_ALIASES = {
    "run_docs_checks.sh": "agent-canon-cli",
}
SELECTION_EVIDENCE_TARGET = "compact report Selection Evidence Drilldown"
MARKDOWN_EVIDENCE_TARGET = "compact report Markdown And Prompt Drilldown"
PROMPT_TOOL_EVIDENCE_TARGET = "compact report Markdown And Prompt Drilldown"
REFERENCE_CAPTURE_EVIDENCE_TARGET = "compact report Reference Capture Drilldown"
WORKFLOW_ATTRIBUTION_EVIDENCE_TARGET = "compact report Workflow Attribution Drilldown"
TOKEN_USAGE_EVIDENCE_TARGET = "compact report Token Consumption Drilldown"
SKILL_EVAL_EVIDENCE_TARGET = "compact report Skill Eval Failure Drilldown"
WAVE_EXECUTION_EVIDENCE_TARGET = "compact report Wave And Subagent Execution Drilldown"
SELECTION_RESPONSIBILITIES = ("skill", "workflow", "tool")
SELECTED_WORKFLOW_FIELDS = (
    "workflows",
    "workflow",
    "workflow_family",
    "selected_workflow",
)
RUN_BUNDLE_WORKFLOW_RE = re.compile(
    r"(?:^|[\s`])workflow=([^\n\r,]+?)(?=\s+skills=|,\s*skills=|$)"
)
ALL_SELECTION_NAMESPACES = "*"
CROSS_NAMESPACE_SELECTION_COMPONENTS = frozenset(
    {
        ("skill", "oop-readability-check"),
    }
)
SelectionEvent = tuple[
    int,
    int,
    str,
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
]


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
    active_failed: Counter[str]
    resolved_failed: Counter[str]
    reports_missing_used_skills: int
    failed_reports_missing_used_skills: int


@dataclass(frozen=True)
class HookWorkflowBreakdown:
    """Workflow attribution inferred from hook JSONL entries."""

    workflows: Counter[str]
    workflow_events: Counter[str]
    missing_workflow_by_file: Counter[str]
    missing_workflow_events: Counter[str]
    missing_workflow_namespaces: Counter[str]
    missing_workflow_statuses: Counter[str]
    missing_workflow_tools: Counter[str]
    entries_with_workflow: int
    entries_without_workflow: int
    context_attributed_entries: int


@dataclass(frozen=True)
class TimedIntMetric:
    """One integer metric with an optional chronological timestamp."""

    epoch: int
    value: int


@dataclass(frozen=True)
class TimedFloatMetric:
    """One float metric with an optional chronological timestamp."""

    epoch: int
    value: float


@dataclass(frozen=True)
class TokenUsageBreakdown:
    """Token consumption evidence inferred from workflow monitor reports."""

    comparison_files: tuple[Path, ...]
    comparison_count: int
    summary_files: tuple[Path, ...]
    summary_count: int
    baseline_total_tokens: int
    candidate_total_tokens: int
    baseline_token_counts: tuple[int, ...]
    candidate_token_counts: tuple[int, ...]
    token_ratios: tuple[float, ...]
    session_count: int
    token_event_count: int
    total_tokens: int
    latest_moving_average_total: float
    average_tokens_per_event: float
    timed_candidate_token_counts: tuple[TimedIntMetric, ...]
    timed_token_ratios: tuple[TimedFloatMetric, ...]


@dataclass(frozen=True)
class WaveExecutionBreakdown:
    """Wave and subagent execution evidence inferred from run-bundle reports."""

    report_files: tuple[Path, ...]
    planned_wave_count: int
    actual_wave_event_count: int
    spawned_event_count: int
    blocked_event_count: int
    skipped_event_count: int
    completed_event_count: int
    missing_actual_wave_count: int
    unplanned_actual_wave_count: int
    events_by_status: Counter[str]
    events_by_spawn_authority: Counter[str]
    spawned_roles: Counter[str]
    skipped_roles: Counter[str]


@dataclass(frozen=True)
class PromptToolBreakdown:
    """Prompt capture and tool selection evidence inferred from hook logs."""

    prompt_entries: int
    prompt_excerpt_entries: int
    prompt_missing_excerpt_entries: int
    prompt_total_chars: int
    prompt_char_counts: tuple[int, ...]
    timed_prompt_char_counts: tuple[TimedIntMetric, ...]
    tool_selection_entries: int
    tools: Counter[str]
    command_verbs: Counter[str]
    selected_tools: Counter[str]


@dataclass(frozen=True)
class MarkdownDocsBreakdown:
    """Markdown/docs hook and eval signals inferred from accumulated evidence."""

    eval_reports: int
    failed_eval_reports: int
    candidate_skill_entries: int
    candidate_tool_entries: int
    candidate_tools: Counter[str]


@dataclass(frozen=True)
class ReferenceCaptureBreakdown:
    """Reference-capture hook signals inferred from accumulated evidence."""

    entries: int
    url_observations: int
    registered_url_observations: int
    missing_url_observations: int
    blocked_entries: int
    source_fields: Counter[str]
    events: Counter[str]
    urls: Counter[str]
    registered_urls: Counter[str]
    missing_urls: Counter[str]


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
class DashboardNextAction:
    """One mechanically generated dashboard next action."""

    priority: str
    action: str
    reason: str
    evidence: str
    owner_surface: str
    command: str
    done_condition: str
    issue: str
    automation: str


@dataclass(frozen=True)
class ProblemComponent:
    """One skill, workflow, tool, or hook that needs attention."""

    component_type: str
    name: str
    status: str
    problem: str
    evidence: str
    next_action: str


@dataclass(frozen=True)
class RuntimeDashboardSummary:
    """All evidence used by one runtime dashboard."""

    root: Path
    recent_days: int | None
    recent_cutoff_epoch: int | None
    evidence: EvidenceSummary
    hook_files: tuple[Path, ...]
    hook_entries: int
    result_families: tuple[ResultFamilySummary, ...]
    skill_eval_breakdown: SkillEvalBreakdown
    hook_workflow_breakdown: HookWorkflowBreakdown
    token_usage_breakdown: TokenUsageBreakdown
    wave_execution_breakdown: WaveExecutionBreakdown
    prompt_tool_breakdown: PromptToolBreakdown
    markdown_docs_breakdown: MarkdownDocsBreakdown
    reference_capture_breakdown: ReferenceCaptureBreakdown
    selection_metrics_breakdown: SelectionMetricsBreakdown


class ResultFamilyReader:
    """Reads accumulated Markdown result families."""

    def __init__(self, root: Path, recent_cutoff_epoch: int | None = None) -> None:
        """Store the AgentCanon evidence root."""
        self.root = root
        self.recent_cutoff_epoch = recent_cutoff_epoch

    def read_family(self, family: str) -> ResultFamilySummary:
        """Read one accumulated Markdown report directory."""
        try:
            directories = eval_result_search_dirs(self.root, family)
        except RuntimeError as error:
            if not missing_log_archive_error(error):
                raise
            directories = (self.root / "agents" / "evals" / "results" / family,)
        reports = tuple(
            sorted(
                {
                    path
                    for directory in directories
                    if directory.is_dir()
                    for path in directory.glob("*.md")
                    if path.name != "README.md"
                    if path_inside_recent_window(path, self.recent_cutoff_epoch)
                }
            )
        )
        status_counts: Counter[str] = Counter()
        failed_reports: list[Path] = []
        for report in reports:
            status = self.report_status(report)
            status_counts[status] += 1
            if status == "fail":
                failed_reports.append(report)
        return ResultFamilySummary(
            family=family,
            directory=directories[0],
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
        latest_status: dict[str, str] = {}
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
                latest_status[skill] = status
                if status == "fail":
                    failed[skill] += 1
        active_failed = Counter(
            {skill: 1 for skill, status in latest_status.items() if status == "fail"}
        )
        resolved_failed = Counter(
            {
                skill: count
                for skill, count in failed.items()
                if latest_status.get(skill) not in {"fail", None}
            }
        )
        return SkillEvalBreakdown(
            evaluated=evaluated,
            failed=failed,
            active_failed=active_failed,
            resolved_failed=resolved_failed,
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
    def read(
        cls,
        hook_files: Sequence[Path],
        root: Path,
        recent_cutoff_epoch: int | None = None,
    ) -> HookWorkflowBreakdown:
        """Return workflow attribution for hook entries."""
        workflows: Counter[str] = Counter()
        workflow_events: Counter[str] = Counter()
        missing_by_file: Counter[str] = Counter()
        missing_events: Counter[str] = Counter()
        missing_namespaces: Counter[str] = Counter()
        missing_statuses: Counter[str] = Counter()
        missing_tools: Counter[str] = Counter()
        entries_with_workflow = 0
        entries_without_workflow = 0
        context_attributed_entries = 0
        latest_by_namespace: dict[str, tuple[str, ...]] = {}
        for _entry_epoch, _sequence, hook_file, entry in cls.sorted_entries(
            hook_files,
            recent_cutoff_epoch,
        ):
            namespace = str(entry.get("hook_log_namespace") or "missing_namespace")
            names = cls.workflow_names(entry)
            if names:
                latest_by_namespace[namespace] = names
                attributed_names = names
            else:
                attributed_names = latest_by_namespace.get(namespace, ())
                context_attributed_entries += int(bool(attributed_names))
            if not attributed_names:
                entries_without_workflow += 1
                missing_by_file[relative_path_label(hook_file, root)] += 1
                missing_events[str(entry.get("event") or "missing_event")] += 1
                missing_namespaces[namespace] += 1
                missing_statuses[str(entry.get("status") or "missing_status")] += 1
                tool_name = str(
                    entry.get("tool_name") or entry.get("tool_command_verb") or ""
                )
                if tool_name:
                    missing_tools[tool_name] += 1
                continue
            entries_with_workflow += 1
            event = str(entry.get("event") or "missing_event")
            for name in attributed_names:
                workflows[name] += 1
                workflow_events[f"{name}@{event}"] += 1
        return HookWorkflowBreakdown(
            workflows=workflows,
            workflow_events=workflow_events,
            missing_workflow_by_file=missing_by_file,
            missing_workflow_events=missing_events,
            missing_workflow_namespaces=missing_namespaces,
            missing_workflow_statuses=missing_statuses,
            missing_workflow_tools=missing_tools,
            entries_with_workflow=entries_with_workflow,
            entries_without_workflow=entries_without_workflow,
            context_attributed_entries=context_attributed_entries,
        )

    @classmethod
    def sorted_entries(
        cls,
        hook_files: Sequence[Path],
        recent_cutoff_epoch: int | None = None,
    ) -> tuple[tuple[int, int, Path, dict[str, object]], ...]:
        """Return hook entries in a stable approximate runtime order."""
        rows: list[tuple[int, int, Path, dict[str, object]]] = []
        sequence = 0
        for hook_file in hook_files:
            for entry in cls.iter_entries(hook_file, recent_cutoff_epoch):
                rows.append(
                    (
                        parse_hook_timestamp(entry.get("timestamp")),
                        sequence,
                        hook_file,
                        entry,
                    )
                )
                sequence += 1
        return tuple(sorted(rows, key=lambda row: (row[0] or row[1], row[1])))

    @staticmethod
    def iter_entries(
        hook_file: Path,
        recent_cutoff_epoch: int | None = None,
    ) -> tuple[dict[str, object], ...]:
        """Return parsed hook entries from one JSONL file."""
        entries: list[dict[str, object]] = []
        try:
            lines = hook_file.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return ()
        for line in lines:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                entry = cast(dict[str, object], value)
                if hook_entry_inside_recent_window(entry, hook_file, recent_cutoff_epoch):
                    entries.append(entry)
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
    def read(
        cls,
        root: Path,
        recent_cutoff_epoch: int | None = None,
    ) -> TokenUsageBreakdown:
        """Return accumulated token comparison stats."""
        files: set[Path] = set()
        summary_files: set[Path] = set()
        ratios: list[float] = []
        baseline_counts: list[int] = []
        candidate_counts: list[int] = []
        timed_candidate_counts: list[TimedIntMetric] = []
        timed_ratios: list[TimedFloatMetric] = []
        baseline_total = 0
        candidate_total = 0
        summary_count = 0
        session_count = 0
        token_event_count = 0
        total_tokens = 0
        latest_moving_average_total = 0.0
        average_tokens_per_event = 0.0
        for path in cls.candidate_paths(root):
            text = path.read_text(encoding="utf-8")
            epoch = cls.evidence_epoch(path, text)
            if not evidence_inside_recent_window(path, epoch, recent_cutoff_epoch):
                continue
            for baseline, candidate, ratio in cls.comparisons(text):
                files.add(path)
                baseline_total += baseline
                candidate_total += candidate
                baseline_counts.append(baseline)
                candidate_counts.append(candidate)
                if epoch > 0:
                    timed_candidate_counts.append(TimedIntMetric(epoch, candidate))
                    timed_ratios.append(TimedFloatMetric(epoch, ratio))
                ratios.append(ratio)
            for sessions, events, total, moving, average in cls.summaries(text):
                summary_files.add(path)
                summary_count += 1
                session_count += sessions
                token_event_count += events
                total_tokens += total
                latest_moving_average_total = moving
                average_tokens_per_event = average
        return TokenUsageBreakdown(
            comparison_files=tuple(sorted(files)),
            comparison_count=len(ratios),
            summary_files=tuple(sorted(summary_files)),
            summary_count=summary_count,
            baseline_total_tokens=baseline_total,
            candidate_total_tokens=candidate_total,
            baseline_token_counts=tuple(baseline_counts),
            candidate_token_counts=tuple(candidate_counts),
            token_ratios=tuple(ratios),
            session_count=session_count,
            token_event_count=token_event_count,
            total_tokens=total_tokens,
            latest_moving_average_total=latest_moving_average_total,
            average_tokens_per_event=average_tokens_per_event,
            timed_candidate_token_counts=tuple(
                sorted(timed_candidate_counts, key=lambda observation: observation.epoch)
            ),
            timed_token_ratios=tuple(
                sorted(timed_ratios, key=lambda observation: observation.epoch)
            ),
        )

    @staticmethod
    def candidate_paths(root: Path) -> tuple[Path, ...]:
        """Return likely text files containing token comparison evidence."""
        patterns = (
            "reports/agents/**/workflow_monitoring.md",
            "reports/agents/**/*token*.md",
            "reports/**/*token*.md",
            ".agent-canon/log-archive/eval-results/**/*.md",
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

    @staticmethod
    def summaries(text: str) -> tuple[tuple[int, int, int, float, float], ...]:
        """Return token moving-average summaries found in one text blob."""
        matches: list[tuple[int, int, int, float, float]] = []
        for pattern in (TOKEN_SUMMARY_RE, TOKEN_SUMMARY_MARKDOWN_RE):
            for match in pattern.finditer(text):
                matches.append(
                    (
                        int(match.group("sessions")),
                        int(match.group("events")),
                        int(match.group("total")),
                        float(match.group("moving")),
                        float(match.group("average")),
                    )
                )
        return tuple(matches)

    @staticmethod
    def evidence_epoch(path: Path, text: str) -> int:
        """Return a chronological timestamp for token evidence when available."""
        text_match = ISO_TIMESTAMP_RE.search(text)
        if text_match is not None:
            return parse_hook_timestamp(text_match.group(0))
        path_match = RUN_ID_TIMESTAMP_RE.search(path.as_posix())
        if path_match is None:
            return NO_RESET_EPOCH
        return parse_compact_utc_timestamp(path_match.group(0))


class WaveExecutionBreakdownReader:
    """Reads wave execution evidence from run-bundle monitor files."""

    @classmethod
    def read(
        cls,
        root: Path,
        recent_cutoff_epoch: int | None = None,
    ) -> WaveExecutionBreakdown:
        """Return accumulated wave and subagent execution stats."""
        report_files: set[Path] = set()
        planned_wave_count = 0
        actual_wave_event_count = 0
        spawned_event_count = 0
        blocked_event_count = 0
        skipped_event_count = 0
        completed_event_count = 0
        missing_actual_wave_count = 0
        unplanned_actual_wave_count = 0
        events_by_status: Counter[str] = Counter()
        events_by_spawn_authority: Counter[str] = Counter()
        spawned_roles: Counter[str] = Counter()
        skipped_roles: Counter[str] = Counter()
        for workflow_path in cls.candidate_paths(root):
            text = workflow_path.read_text(encoding="utf-8")
            epoch = TokenUsageBreakdownReader.evidence_epoch(workflow_path, text)
            if not evidence_inside_recent_window(workflow_path, epoch, recent_cutoff_epoch):
                continue
            actual_rows = actual_wave_event_fields(text)
            planned_ids = cls.planned_wave_ids(workflow_path)
            if not actual_rows and not planned_ids:
                continue
            report_files.add(workflow_path)
            actual_wave_event_count += len(actual_rows)
            actual_by_id = {
                row.get("wave_id", "").strip(): row
                for row in actual_rows
                if row.get("wave_id", "").strip()
            }
            planned_wave_count += len(planned_ids)
            missing_actual_wave_count += len(planned_ids - set(actual_by_id))
            unplanned_actual_wave_count += len(set(actual_by_id) - planned_ids)
            for row in actual_rows:
                status = row.get("status", "missing").strip() or "missing"
                authority = row.get("spawn_authority", "missing").strip() or "missing"
                events_by_status[status] += 1
                events_by_spawn_authority[authority] += 1
                spawned = split_counter_field(row.get("spawned_roles", ""))
                skipped = split_counter_field(row.get("skipped_roles", ""))
                spawned_roles.update(spawned)
                skipped_roles.update(skipped)
                spawned_event_count += int(bool(spawned))
                skipped_event_count += int(bool(skipped))
                blocked_event_count += int(
                    "blocked" in status or "required" in authority
                )
                completed_event_count += int(status in {"done", "complete", "completed"})
        return WaveExecutionBreakdown(
            report_files=tuple(sorted(report_files)),
            planned_wave_count=planned_wave_count,
            actual_wave_event_count=actual_wave_event_count,
            spawned_event_count=spawned_event_count,
            blocked_event_count=blocked_event_count,
            skipped_event_count=skipped_event_count,
            completed_event_count=completed_event_count,
            missing_actual_wave_count=missing_actual_wave_count,
            unplanned_actual_wave_count=unplanned_actual_wave_count,
            events_by_status=events_by_status,
            events_by_spawn_authority=events_by_spawn_authority,
            spawned_roles=spawned_roles,
            skipped_roles=skipped_roles,
        )

    @staticmethod
    def candidate_paths(root: Path) -> tuple[Path, ...]:
        """Return workflow monitor reports that may carry wave-event rows."""
        patterns = (
            "reports/agents/**/workflow_monitoring.md",
            ".agent-canon/log-archive/agent-reports/**/workflow_monitoring.md",
        )
        paths: set[Path] = set()
        for pattern in patterns:
            paths.update(path for path in root.glob(pattern) if path.is_file())
        return tuple(sorted(paths))

    @staticmethod
    def planned_wave_ids(workflow_path: Path) -> set[str]:
        """Return planned wave ids from sibling schedule.md when present."""
        schedule_path = workflow_path.with_name("schedule.md")
        if not schedule_path.is_file():
            return set()
        rows = markdown_table_dict_rows(
            schedule_path.read_text(encoding="utf-8"),
            "## Agent Wave Ledger",
        )
        return {
            row.get("Wave ID", "").strip()
            for row in rows
            if row.get("Wave ID", "").strip()
        }


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
        self.known_skill_ids = known_skill_ids(root)
        self.known_workflow_names = known_workflow_names(root)

    def read(
        self,
        hook_files: Sequence[Path],
        recent_cutoff_epoch: int | None = None,
    ) -> SelectionMetricsBreakdown:
        """Return responsibility-scoped selection metrics."""
        store = SelectionMetricStore(self.root)
        entries_seen = 0
        entries_with_candidates = 0
        entries_with_selection = 0
        filtered_observations = 0
        events: list[SelectionEvent] = []
        sequence = 0
        for hook_file in hook_files:
            for entry in HookWorkflowBreakdownReader.iter_entries(
                hook_file,
                recent_cutoff_epoch,
            ):
                selected = self.canonical_selection_map(
                    selected_by_responsibility(entry, hook_file)
                )
                candidates = self.canonical_selection_map(
                    candidates_by_responsibility(entry)
                )
                events.append(
                    (
                        sequence,
                        parse_hook_timestamp(entry.get("timestamp")),
                        selection_namespace(entry, hook_file),
                        selected,
                        candidates,
                    )
                )
                sequence += 1
        workflow_events = self.workflow_report_selection_events(
            sequence,
            recent_cutoff_epoch or NO_RESET_EPOCH,
        )
        future_selected = future_selected_positions((*events, *workflow_events))
        for sequence, entry_epoch, namespace, selected, candidates in events:
            entries_seen += 1
            entries_with_selection += int(any(selected.values()))
            entries_with_candidates += int(any(candidates.values()))
            filtered_observations += self.add_selected_components(store, selected, entry_epoch)
            filtered_observations += self.add_candidate_components(
                store,
                candidates,
                selected,
                entry_epoch,
                future_selected,
                namespace,
                sequence,
            )
        for _sequence, entry_epoch, _namespace, selected, _candidates in workflow_events:
            filtered_observations += self.add_selected_components(store, selected, entry_epoch)
        return SelectionMetricsBreakdown(
            metrics=store.to_metrics(),
            entries_seen=entries_seen,
            entries_with_candidates=entries_with_candidates,
            entries_with_selection=entries_with_selection,
            filtered_observations=filtered_observations,
        )

    def canonical_selection_map(
        self,
        values_by_responsibility: dict[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        """Return selection values normalized for responsibility-local matching."""
        return {
            responsibility: canonical_selection_values(
                responsibility,
                values,
                self.known_skill_ids,
                self.known_workflow_names,
            )
            for responsibility, values in values_by_responsibility.items()
        }

    def workflow_report_selection_events(
        self,
        start_sequence: int,
        cutoff_epoch: int,
    ) -> tuple[SelectionEvent, ...]:
        """Return workflow selections recorded in run-bundle monitor reports."""
        events: list[SelectionEvent] = []
        sequence = start_sequence
        for workflow_path in WaveExecutionBreakdownReader.candidate_paths(self.root):
            text = workflow_path.read_text(encoding="utf-8")
            epoch = TokenUsageBreakdownReader.evidence_epoch(workflow_path, text)
            if cutoff_epoch > NO_RESET_EPOCH and not timestamped_evidence_after_cutoff(
                workflow_path,
                epoch,
                cutoff_epoch,
            ):
                continue
            workflows = workflow_names_from_run_bundle(text)
            if not workflows:
                continue
            events.append(
                (
                    sequence,
                    epoch,
                    ALL_SELECTION_NAMESPACES,
                    {"workflow": workflows},
                    {},
                )
            )
            sequence += 1
        return tuple(events)

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
        future_selected: dict[tuple[str, str, str], tuple[int, ...]],
        namespace: str,
        sequence: int,
    ) -> int:
        """Add candidate components and return filtered observation count."""
        filtered = 0
        for responsibility, names in candidates.items():
            selected_names = set(selected.get(responsibility, ()))
            for name in names:
                missed = name not in selected_names and not has_future_selection(
                    future_selected,
                    namespace,
                    responsibility,
                    name,
                    sequence,
                )
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
            f"  SkillFailures[\"Skill failure attribution<br/>active failed skills: {len(summary.skill_eval_breakdown.active_failed)}\"]",
            f"  WorkflowHooks[\"Workflow hook attribution<br/>attributed: {summary.hook_workflow_breakdown.entries_with_workflow}<br/>missing: {summary.hook_workflow_breakdown.entries_without_workflow}\"]",
            f"  Tokens[\"Token consumption<br/>comparisons: {summary.token_usage_breakdown.comparison_count}<br/>summaries: {summary.token_usage_breakdown.summary_count}\"]",
            f"  Waves[\"Wave execution<br/>events: {summary.wave_execution_breakdown.actual_wave_event_count}<br/>blocked: {summary.wave_execution_breakdown.blocked_event_count}\"]",
            f"  PromptTools[\"Prompt + tool selection<br/>prompts: {summary.prompt_tool_breakdown.prompt_entries}<br/>tools: {summary.prompt_tool_breakdown.tool_selection_entries}\"]",
            f"  Selection[\"Selection accuracy<br/>items: {len(summary.selection_metrics_breakdown.metrics)}<br/>misses: {selection_missed_total(summary)}\"]",
            f"  MarkdownDocs[\"Markdown/docs signals<br/>eval fails: {summary.markdown_docs_breakdown.failed_eval_reports}<br/>hook signals: {markdown_hook_signal_count(summary)}\"]",
            f"  ReferenceCapture[\"Reference capture<br/>urls: {summary.reference_capture_breakdown.url_observations}<br/>missing: {summary.reference_capture_breakdown.missing_url_observations}\"]",
            f"  WorkflowEval[\"Workflow selection evals<br/>reports: {family_count(summary, 'workflow-selection')}\"]",
            f"  ReportEval[\"Report quality evals<br/>reports: {family_count(summary, 'report-quality')}\"]",
            f"  LocalLLM[\"Local LLM evals<br/>reports: {family_count(summary, 'local-llm-responsibility')}\"]",
            f"  RoleEval[\"Codex role evals<br/>reports: {family_count(summary, 'codex-agent-role')}\"]",
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
            "  Waves --> Dashboard",
            "  PromptTools --> Dashboard",
            "  Hooks --> Selection",
            "  PromptTools --> Selection",
            "  Selection --> Dashboard",
            "  PromptTools --> MarkdownDocs",
            "  SkillEval --> MarkdownDocs",
            "  MarkdownDocs --> Dashboard",
            "  Hooks --> ReferenceCapture",
            "  ReferenceCapture --> Dashboard",
            "  ReferenceCapture --> Guide",
            "  WorkflowEval --> Dashboard",
            "  ReportEval --> Dashboard",
            "  LocalLLM --> Dashboard",
            "  RoleEval --> Dashboard",
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
            self.wave_execution_row(),
            self.prompt_tool_row(),
            self.selection_metrics_row(),
            self.markdown_docs_row(),
            self._reference_capture_row(),
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
            self.family_row(
                "Codex role eval",
                "codex-agent-role",
                "repair subagent role TOML, model settings, routing, or runtime metric capture",
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
            bool(self.summary.skill_eval_breakdown.active_failed),
        )

    def skill_failure_row(self) -> str:
        """Return the skill-failure analysis action-map row."""
        breakdown = self.summary.skill_eval_breakdown
        evidence_count = sum(breakdown.evaluated.values())
        needs_attention = bool(
            breakdown.active_failed or breakdown.failed_reports_missing_used_skills
        )
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
            "record token_count comparisons or moving averages when token use drives workflow design",
            breakdown.comparison_count + breakdown.summary_count,
            breakdown.comparison_count == 0 and breakdown.summary_count == 0,
        )

    def wave_execution_row(self) -> str:
        """Return the wave execution action-map row."""
        breakdown = self.summary.wave_execution_breakdown
        return action_map_row(
            "wave and subagent execution",
            "record spawned, skipped, or authority-blocked wave rows before closeout",
            breakdown.actual_wave_event_count,
            breakdown.actual_wave_event_count == 0
            or breakdown.blocked_event_count > 0
            or breakdown.missing_actual_wave_count > 0,
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

    def _reference_capture_row(self) -> str:
        """Return the reference-capture action-map row."""
        breakdown = self.summary.reference_capture_breakdown
        return action_map_row(
            "reference capture",
            "materialize consulted PDF/HTML sources under references/ before closeout",
            breakdown.url_observations,
            breakdown.entries == 0 or breakdown.missing_url_observations > 0 or breakdown.blocked_entries > 0,
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

    def __init__(self, root: Path, recent_days: int | None = None) -> None:
        """Resolve the requested root to the AgentCanon evidence root."""
        self.guide = AgentImprovementGuide(root)
        self.root = self.guide.root
        self.recent_days = recent_days
        self.recent_cutoff_epoch = recent_cutoff_epoch(recent_days)

    def collect(self) -> RuntimeDashboardSummary:
        """Collect dashboard evidence without mutating repository state."""
        evidence, hook_files = self.collect_evidence()
        reader = ResultFamilyReader(self.root, self.recent_cutoff_epoch)
        result_families = (
            reader.read_family("skill-workflow-prompt"),
            reader.read_family("local-llm-responsibility"),
            reader.read_family("workflow-selection"),
            reader.read_family("report-quality"),
            reader.read_family("codex-agent-role"),
        )
        skill_eval_breakdown = SkillEvalBreakdownReader.read(result_families[0])
        if self.recent_cutoff_epoch is not None:
            evidence = EvidenceSummary(
                open_issues=evidence.open_issues,
                closed_issues=evidence.closed_issues,
                memory_entries=evidence.memory_entries,
                skill_eval_reports=result_families[0].reports,
                failed_skill_eval_reports=result_families[0].failed_reports,
                hook_counts=read_hook_evidence_counts(
                    self.root,
                    hook_files,
                    self.recent_cutoff_epoch,
                ),
            )
        return RuntimeDashboardSummary(
            root=self.root,
            recent_days=self.recent_days,
            recent_cutoff_epoch=self.recent_cutoff_epoch,
            evidence=evidence,
            hook_files=hook_files,
            hook_entries=sum(
                hook_entry_count(path, self.recent_cutoff_epoch) for path in hook_files
            ),
            result_families=result_families,
            skill_eval_breakdown=skill_eval_breakdown,
            hook_workflow_breakdown=HookWorkflowBreakdownReader.read(
                hook_files,
                self.root,
                self.recent_cutoff_epoch,
            ),
            token_usage_breakdown=TokenUsageBreakdownReader.read(
                self.root,
                self.recent_cutoff_epoch,
            ),
            wave_execution_breakdown=WaveExecutionBreakdownReader.read(
                self.root,
                self.recent_cutoff_epoch,
            ),
            prompt_tool_breakdown=read_prompt_tool_breakdown(
                hook_files,
                self.recent_cutoff_epoch,
            ),
            markdown_docs_breakdown=read_markdown_docs_breakdown(
                evidence.hook_counts,
                skill_eval_breakdown,
            ),
            reference_capture_breakdown=read_reference_capture_breakdown(
                hook_files,
                self.recent_cutoff_epoch,
            ),
            selection_metrics_breakdown=SelectionMetricsReader(self.root).read(
                hook_files,
                self.recent_cutoff_epoch,
            ),
        )

    def collect_evidence(self) -> tuple[EvidenceSummary, tuple[Path, ...]]:
        """Collect guide evidence, tolerating a missing read-only log archive."""
        try:
            evidence = self.guide.collect()
            hook_files = filter_hook_paths(
                self.guide.hook_result_paths(),
                self.recent_cutoff_epoch,
            )
            return evidence, hook_files
        except RuntimeError as error:
            if not missing_log_archive_error(error):
                raise
        hook_files: tuple[Path, ...] = ()
        return (
            EvidenceSummary(
                open_issues=self.guide.paths("issues/open/AC-*.md"),
                closed_issues=self.guide.paths("issues/closed/AC-*.md"),
                memory_entries=self.guide.memory_entry_counts(),
                skill_eval_reports=(),
                failed_skill_eval_reports=(),
                hook_counts=read_hook_evidence_counts(
                    self.root,
                    hook_files,
                    self.recent_cutoff_epoch,
                ),
            ),
            hook_files,
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


def render_compact_dashboard_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return token-light dashboard lines for agent log analysis."""
    return [
        "# Agent Runtime Compact Summary",
        "",
        "## Machine Summary",
        "",
        "```text",
        *machine_summary_lines(summary),
        "```",
        "",
        "## Priority Problems",
        "",
        *compact_problem_component_lines(summary),
        "",
        "## Priority Next Actions",
        "",
        *compact_next_action_lines(summary),
        "",
        "## Selection Misses",
        "",
        *compact_selection_miss_lines(summary),
        "",
        "## Evidence Drilldown",
        "",
        *compact_evidence_drilldown_lines(summary),
        "",
        "## Reading Rule",
        "",
        "- Use this compact summary as the default input for agent log analysis.",
        "- Do not read raw JSONL during normal agent log analysis.",
        "- If this summary lacks needed detail, extend or rerun the dashboard tool with a more specific generated summary instead of searching raw logs.",
        "- Raw JSONL inspection is reserved for tool implementation, corruption audits, or schema debugging with an explicit rationale.",
    ]


def render_compact_dashboard(summary: RuntimeDashboardSummary) -> str:
    """Render a compact dashboard as Markdown."""
    return "\n".join(render_compact_dashboard_lines(summary)) + "\n"


def compact_problem_component_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return the top dashboard problems without the full dashboard context."""
    components = dashboard_problem_components(summary)[:MAX_COMPACT_REPORT_LINES]
    lines = [
        "| type | component | status | problem | evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not components:
        return [
            *lines,
            "| `none` | `none` | `healthy` | `no problem components detected` | `dashboard` |",
        ]
    lines.extend(
        "| "
        + " | ".join(
            table_cell(value)
            for value in (
                component.component_type,
                component.name,
                component.status,
                component.problem,
                component.evidence,
            )
        )
        + " |"
        for component in components
    )
    return lines


def compact_next_action_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return the highest-priority generated next actions."""
    actions = dashboard_next_actions(summary)[:MAX_COMPACT_REPORT_LINES]
    lines = [
        "| priority | action | reason | evidence | owner surface | command |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not actions:
        return [
            *lines,
            "| `none` | no immediate dashboard action | all observed dashboard signals are healthy | `dashboard` | `none` | `none` |",
        ]
    lines.extend(
        "| "
        + " | ".join(
            table_cell(value)
            for value in (
                action.priority,
                action.action,
                action.reason,
                action.evidence,
                action.owner_surface,
                action.command,
            )
        )
        + " |"
        for action in actions
    )
    return lines


def compact_selection_miss_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return top skill, workflow, and tool selection misses."""
    missed = top_selection_misses(summary)
    lines = [
        "| responsibility | name | selected | candidate | missed | miss rate | reset basis |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not missed:
        return [
            *lines,
            "| `none` | `none` | `0` | `0` | `0` | `0.0%` | `none` |",
        ]
    lines.extend(
        "| "
        + " | ".join(
            table_cell(value)
            for value in (
                row.responsibility,
                row.name,
                str(row.selected_count),
                str(row.candidate_count),
                str(row.missed_count),
                failure_rate(row.missed_count, row.candidate_count),
                selection_reset_label(row),
            )
        )
        + " |"
        for row in missed
    )
    return lines


def top_selection_misses(summary: RuntimeDashboardSummary) -> tuple[SelectionMetric, ...]:
    """Return highest-impact selection misses in compact-dashboard order."""
    missed = sorted(
        (
            row
            for row in summary.selection_metrics_breakdown.metrics
            if row.missed_count > 0
        ),
        key=lambda row: (-row.missed_count, row.responsibility, row.name),
    )
    return tuple(missed[:MAX_COMPACT_REPORT_LINES])


def compact_evidence_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return generated evidence details so agents do not open raw JSONL."""
    return [
        "### Hook Failure Drilldown",
        "",
        *compact_hook_failure_drilldown_lines(summary),
        "",
        "### Workflow Attribution Drilldown",
        "",
        *compact_workflow_attribution_drilldown_lines(summary),
        "",
        "### Skill Eval Failure Drilldown",
        "",
        *compact_skill_eval_failure_drilldown_lines(summary),
        "",
        "### Selection Evidence Drilldown",
        "",
        *compact_selection_evidence_drilldown_lines(summary),
        "",
        "### Markdown And Prompt Drilldown",
        "",
        *compact_markdown_prompt_drilldown_lines(summary),
        "",
        "### Prompt Token Trend Drilldown",
        "",
        *compact_prompt_token_trend_drilldown_lines(summary),
        "",
        "### Token Consumption Drilldown",
        "",
        *compact_token_consumption_drilldown_lines(summary),
        "",
        "### Wave And Subagent Execution Drilldown",
        "",
        *compact_wave_execution_drilldown_lines(summary),
        "",
        "### Reference Capture Drilldown",
        "",
        *compact_reference_capture_drilldown_lines(summary),
    ]


def compact_hook_failure_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return top hook-failure grouping without raw log excerpts."""
    fingerprint = top_hook_failure_fingerprint(summary)
    if fingerprint == "none":
        return [
            "| fingerprint | status | failed entries | top namespaces | top events | top tools |",
            "| --- | --- | ---: | --- | --- | --- |",
            "| `none` | `healthy` | `0` | `none` | `none` | `none` |",
        ]
    namespaces: Counter[str] = Counter()
    events: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    for hook_file in summary.hook_files:
        for entry in HookWorkflowBreakdownReader.iter_entries(
            hook_file,
            summary.recent_cutoff_epoch,
        ):
            if (
                str(entry.get("status") or "") == "fail"
                and str(entry.get("failure_fingerprint") or "") == fingerprint
            ):
                namespaces[str(entry.get("hook_log_namespace") or "missing_namespace")] += 1
                events[str(entry.get("event") or "missing_event")] += 1
                tool = str(entry.get("tool_name") or entry.get("tool_command_verb") or "")
                if tool:
                    tools[tool] += 1
    return [
        "| fingerprint | status | failed entries | top namespaces | top events | top tools |",
        "| --- | --- | ---: | --- | --- | --- |",
        "| "
        + " | ".join(
            table_cell(value)
            for value in (
                fingerprint,
                "fail",
                str(summary.evidence.hook_counts.failures[fingerprint]),
                compact_counter_summary(namespaces),
                compact_counter_summary(events),
                compact_counter_summary(tools),
            )
        )
        + " |",
    ]


def compact_workflow_attribution_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return generated missing-workflow dimensions without raw log files."""
    breakdown = summary.hook_workflow_breakdown
    schema = hook_schema_breakdown(summary)
    return [
        "| metric | value |",
        "| --- | --- |",
        f"| `entries_with_workflow` | `{breakdown.entries_with_workflow}` |",
        f"| `entries_missing_workflow` | `{breakdown.entries_without_workflow}` |",
        f"| `entries_context_attributed` | `{breakdown.context_attributed_entries}` |",
        f"| `missing_events` | `{compact_counter_summary(breakdown.missing_workflow_events)}` |",
        f"| `missing_namespaces` | `{compact_counter_summary(breakdown.missing_workflow_namespaces)}` |",
        f"| `missing_statuses` | `{compact_counter_summary(breakdown.missing_workflow_statuses)}` |",
        f"| `missing_tools` | `{compact_counter_summary(breakdown.missing_workflow_tools)}` |",
        f"| `unknown_event_count` | `{schema['unknown_event_count']}` |",
        f"| `namespace_debt_by_hook_family` | `{compact_mapping_summary(schema['namespace_debt_by_hook_family'])}` |",
        f"| `status_by_hook_family` | `{compact_nested_mapping_summary(schema['status_by_hook_family'])}` |",
        f"| `failure_by_hook_family` | `{compact_nested_mapping_summary(schema['failure_by_hook_family'])}` |",
        f"| `skip_by_hook_family` | `{compact_nested_mapping_summary(schema['skip_by_hook_family'])}` |",
        f"| `oop_applicability` | `{compact_oop_applicability(schema['oop_applicability'])}` |",
    ]


def compact_skill_eval_failure_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return generated failed-skill attribution without report file targets."""
    breakdown = summary.skill_eval_breakdown
    lines = [
        "| skill | evaluated reports | failed reports | failure rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    if not breakdown.active_failed:
        return [*lines, "| `none` | `0` | `0` | `0.0%` |"]
    lines.extend(
        skill_eval_failure_row(breakdown, skill)
        for skill, _count in breakdown.active_failed.most_common(MAX_COMPACT_REPORT_LINES)
    )
    if breakdown.failed_reports_missing_used_skills:
        lines.append(
            "| `_missing_used_skills` | `0` | "
            f"`{breakdown.failed_reports_missing_used_skills}` | `unknown` |"
        )
    return lines


def compact_selection_evidence_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return selection accounting details from parsed hook logs."""
    breakdown = summary.selection_metrics_breakdown
    return [
        "| metric | value |",
        "| --- | ---: |",
        f"| `entries_seen` | `{breakdown.entries_seen}` |",
        f"| `entries_with_candidates` | `{breakdown.entries_with_candidates}` |",
        f"| `entries_with_confirmed_selection` | `{breakdown.entries_with_selection}` |",
        f"| `filtered_observations_before_component_update` | `{breakdown.filtered_observations}` |",
        f"| `total_selected` | `{selection_selected_total(summary)}` |",
        f"| `total_candidates` | `{selection_candidate_total(summary)}` |",
        f"| `total_misses` | `{selection_missed_total(summary)}` |",
    ]


def compact_markdown_prompt_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return Markdown, prompt, and tool-selection details."""
    markdown = summary.markdown_docs_breakdown
    prompt = summary.prompt_tool_breakdown
    return [
        "| metric | value |",
        "| --- | --- |",
        f"| `markdown_eval_reports` | `{markdown.eval_reports}` |",
        f"| `markdown_failed_eval_reports` | `{markdown.failed_eval_reports}` |",
        f"| `markdown_candidate_skill_entries` | `{markdown.candidate_skill_entries}` |",
        f"| `markdown_candidate_tool_entries` | `{markdown.candidate_tool_entries}` |",
        f"| `markdown_candidate_tools` | `{compact_counter_summary(markdown.candidate_tools)}` |",
        f"| `prompt_entries` | `{prompt.prompt_entries}` |",
        f"| `prompt_excerpt_entries` | `{prompt.prompt_excerpt_entries}` |",
        f"| `prompt_missing_excerpt_entries` | `{prompt.prompt_missing_excerpt_entries}` |",
        f"| `prompt_total_chars` | `{prompt.prompt_total_chars}` |",
        f"| `tool_selection_entries` | `{prompt.tool_selection_entries}` |",
        f"| `top_tools` | `{compact_counter_summary(prompt.tools)}` |",
        f"| `top_command_verbs` | `{compact_counter_summary(prompt.command_verbs)}` |",
        f"| `top_selected_repo_tools` | `{compact_counter_summary(prompt.selected_tools)}` |",
    ]


def compact_token_consumption_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return generated token-evidence details without report globs."""
    breakdown = summary.token_usage_breakdown
    return [
        "| metric | value |",
        "| --- | --- |",
        f"| `comparison_count` | `{breakdown.comparison_count}` |",
        f"| `summary_count` | `{breakdown.summary_count}` |",
        f"| `evidence_files` | `{len(set(breakdown.comparison_files + breakdown.summary_files))}` |",
        f"| `baseline_total_tokens` | `{breakdown.baseline_total_tokens}` |",
        f"| `candidate_total_tokens` | `{breakdown.candidate_total_tokens}` |",
        f"| `average_token_ratio` | `{average_ratio(breakdown.token_ratios)}` |",
        f"| `summary_session_count` | `{breakdown.session_count}` |",
        f"| `summary_token_event_count` | `{breakdown.token_event_count}` |",
        f"| `summary_total_tokens` | `{breakdown.total_tokens}` |",
        f"| `latest_moving_average_total_tokens` | `{breakdown.latest_moving_average_total:.3f}` |",
        f"| `average_tokens_per_event` | `{breakdown.average_tokens_per_event:.3f}` |",
    ]


def compact_prompt_token_trend_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return rolling prompt/token trend metrics from generated summaries."""
    prompt = summary.prompt_tool_breakdown
    token = summary.token_usage_breakdown
    return [
        "| metric | value |",
        "| --- | --- |",
        f"| `rolling_window_observations` | `{ROLLING_TREND_WINDOW}` |",
        f"| `prompt_calls` | `{prompt.prompt_entries}` |",
        f"| `prompt_chars_per_call_all` | `{mean_int_label(prompt.prompt_char_counts)}` |",
        f"| `prompt_chars_per_call_recent` | `{rolling_mean_timed_int_label(prompt.timed_prompt_char_counts)}` |",
        f"| `token_comparisons` | `{token.comparison_count}` |",
        f"| `token_ratio_all` | `{average_ratio(token.token_ratios)}` |",
        f"| `token_ratio_recent` | `{rolling_average_timed_ratio(token.timed_token_ratios)}` |",
        f"| `candidate_tokens_per_comparison_all` | `{mean_int_label(token.candidate_token_counts)}` |",
        f"| `candidate_tokens_per_comparison_recent` | `{rolling_mean_timed_int_label(token.timed_candidate_token_counts)}` |",
        f"| `prompt_timed_observations` | `{len(prompt.timed_prompt_char_counts)}` |",
        f"| `token_timed_observations` | `{len(token.timed_token_ratios)}` |",
        f"| `joint_trend_status` | `{prompt_token_joint_status(summary)}` |",
    ]


def compact_reference_capture_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return reference-capture details from parsed hook logs."""
    breakdown = summary.reference_capture_breakdown
    return [
        "| metric | value |",
        "| --- | --- |",
        f"| `entries` | `{breakdown.entries}` |",
        f"| `url_observations` | `{breakdown.url_observations}` |",
        f"| `registered_url_observations` | `{breakdown.registered_url_observations}` |",
        f"| `missing_url_observations` | `{breakdown.missing_url_observations}` |",
        f"| `blocked_entries` | `{breakdown.blocked_entries}` |",
        f"| `events` | `{compact_counter_summary(breakdown.events)}` |",
        f"| `source_fields` | `{compact_counter_summary(breakdown.source_fields)}` |",
        f"| `missing_urls` | `{compact_counter_summary(breakdown.missing_urls)}` |",
        f"| `registered_urls` | `{compact_counter_summary(breakdown.registered_urls)}` |",
    ]


def compact_wave_execution_drilldown_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return compact wave and subagent execution details."""
    breakdown = summary.wave_execution_breakdown
    return [
        "| metric | value |",
        "| --- | --- |",
        f"| `report_files` | `{len(breakdown.report_files)}` |",
        f"| `planned_waves` | `{breakdown.planned_wave_count}` |",
        f"| `actual_wave_events` | `{breakdown.actual_wave_event_count}` |",
        f"| `spawned_events` | `{breakdown.spawned_event_count}` |",
        f"| `blocked_events` | `{breakdown.blocked_event_count}` |",
        f"| `skipped_events` | `{breakdown.skipped_event_count}` |",
        f"| `completed_events` | `{breakdown.completed_event_count}` |",
        f"| `missing_actual_waves` | `{breakdown.missing_actual_wave_count}` |",
        f"| `unplanned_actual_waves` | `{breakdown.unplanned_actual_wave_count}` |",
        f"| `status_counts` | `{compact_counter_summary(breakdown.events_by_status)}` |",
        f"| `authority_counts` | `{compact_counter_summary(breakdown.events_by_spawn_authority)}` |",
        f"| `spawned_roles` | `{compact_counter_summary(breakdown.spawned_roles)}` |",
        f"| `skipped_roles` | `{compact_counter_summary(breakdown.skipped_roles)}` |",
    ]


def compact_counter_summary(counter: Counter[str]) -> str:
    """Return a compact counter summary for one table cell."""
    if not counter:
        return "none"
    return ", ".join(
        f"{key}={value}"
        for key, value in counter.most_common(MAX_COMPACT_REPORT_LINES)
    )


def compact_mapping_summary(mapping: object) -> str:
    """Return a compact sorted mapping summary for one table cell."""
    if not isinstance(mapping, dict) or not mapping:
        return "none"
    items = sorted((str(key), int(value)) for key, value in mapping.items())
    return ", ".join(f"{key}={value}" for key, value in items[:MAX_COMPACT_REPORT_LINES])


def compact_nested_mapping_summary(mapping: object) -> str:
    """Return a compact nested counter summary for one table cell."""
    if not isinstance(mapping, dict) or not mapping:
        return "none"
    parts: list[str] = []
    for key, value in sorted(mapping.items()):
        if not isinstance(value, dict) or not value:
            continue
        parts.append(f"{key}:({compact_mapping_summary(value)})")
    return ", ".join(parts[:MAX_COMPACT_REPORT_LINES]) if parts else "none"


def compact_oop_applicability(payload: object) -> str:
    """Return compact OOP applicability counts for one table cell."""
    if not isinstance(payload, dict):
        return "none"
    return (
        f"applicable={payload.get('applicable_count', 0)}, "
        f"not_applicable={payload.get('not_applicable_count', 0)}, "
        f"missing_reason={payload.get('missing_reason_count', 0)}"
    )


def render_dashboard_api(summary: RuntimeDashboardSummary) -> str:
    """Render the stable agent-facing dashboard API JSON."""
    payload: dict[str, object] = {
        "schema": "agent_runtime_dashboard.v1",
        "root": summary.root.as_posix(),
        "recent_days": summary.recent_days if summary.recent_days is not None else "all",
        "hook_files": len(summary.hook_files),
        "hook_entries": summary.hook_entries,
    }
    payload.update(hook_schema_breakdown(summary))
    payload.update(dashboard_repair_payload(summary))
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def dashboard_repair_payload(summary: RuntimeDashboardSummary) -> dict[str, object]:
    """Return structured repair candidates mirrored by the compact dashboard."""
    return {
        "priority_problems": [
            problem_component_payload(component)
            for component in dashboard_problem_components(summary)[:MAX_COMPACT_REPORT_LINES]
        ],
        "priority_next_actions": [
            next_action_payload(action)
            for action in dashboard_next_actions(summary)[:MAX_COMPACT_REPORT_LINES]
        ],
        "selection_misses": [
            selection_metric_payload(row)
            for row in top_selection_misses(summary)
        ],
    }


def problem_component_payload(component: ProblemComponent) -> dict[str, str]:
    """Return one dashboard problem component as API data."""
    return {
        "type": component.component_type,
        "component": component.name,
        "status": component.status,
        "problem": component.problem,
        "evidence": component.evidence,
        "next_action": component.next_action,
    }


def next_action_payload(action: DashboardNextAction) -> dict[str, str]:
    """Return one dashboard next action as API data."""
    return {
        "priority": action.priority,
        "action": action.action,
        "reason": action.reason,
        "evidence": action.evidence,
        "owner_surface": action.owner_surface,
        "command": action.command,
        "done_condition": action.done_condition,
        "issue": action.issue,
        "automation": action.automation,
    }


def selection_metric_payload(row: SelectionMetric) -> dict[str, object]:
    """Return one selection-miss row as API data."""
    return {
        "responsibility": row.responsibility,
        "name": row.name,
        "selected": row.selected_count,
        "candidate": row.candidate_count,
        "missed": row.missed_count,
        "miss_rate": failure_rate(row.missed_count, row.candidate_count),
        "reset_basis": selection_reset_label(row),
    }


def hook_schema_breakdown(summary: RuntimeDashboardSummary) -> dict[str, object]:
    """Return compact hook-family dimensions needed for routing repair."""
    unknown_events_by_file: Counter[str] = Counter()
    status_by_hook_family: defaultdict[str, Counter[str]] = defaultdict(Counter)
    failure_by_hook_family: defaultdict[str, Counter[str]] = defaultdict(Counter)
    skip_by_hook_family: defaultdict[str, Counter[str]] = defaultdict(Counter)
    namespace_debt_by_hook_family: Counter[str] = Counter()
    oop_applicability = OopApplicabilityAccumulator()
    for hook_file in summary.hook_files:
        family = hook_family(hook_file)
        file_label = relative_path_label(hook_file, summary.root)
        for entry in HookWorkflowBreakdownReader.iter_entries(
            hook_file,
            summary.recent_cutoff_epoch,
        ):
            status = str(entry.get("status") or "unknown")
            event = str(entry.get("event") or "missing_event")
            status_by_hook_family[family][status] += 1
            if event in ("UnknownHookEvent", "missing_event"):
                unknown_events_by_file[file_label] += 1
            if not str(entry.get("hook_log_namespace") or "").strip():
                namespace_debt_by_hook_family[family] += 1
            failure_key = hook_failure_key(entry, status)
            if failure_key:
                failure_by_hook_family[family][failure_key] += 1
            skip_key = hook_skip_key(entry, status)
            if skip_key:
                skip_by_hook_family[family][skip_key] += 1
            if family == "oop_readability_guard":
                oop_applicability.add(entry, status)
    return {
        "unknown_event_count": sum(unknown_events_by_file.values()),
        "unknown_events_by_file": counter_to_dict(unknown_events_by_file),
        "status_by_hook_family": nested_counter_to_dict(status_by_hook_family),
        "failure_by_hook_family": nested_counter_to_dict(failure_by_hook_family),
        "skip_by_hook_family": nested_counter_to_dict(skip_by_hook_family),
        "namespace_debt_by_hook_family": counter_to_dict(namespace_debt_by_hook_family),
        "oop_applicability": oop_applicability.to_payload(),
    }


@dataclass
class OopApplicabilityAccumulator:
    """Mutable OOP applicability counters for dashboard API output."""

    applicable_count: int = 0
    not_applicable_count: int = 0
    missing_reason_count: int = 0
    reasons_by_status: defaultdict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )

    def add(self, entry: dict[str, object], status: str) -> None:
        """Add one OOP hook entry."""
        checked = entry.get("checked")
        applicable = checked is True or (
            checked is None and status not in {"skip", "skipped", "unknown"}
        )
        if applicable:
            self.applicable_count += 1
            return
        self.not_applicable_count += 1
        reason = str(entry.get("skip_reason") or "").strip()
        if not reason:
            self.missing_reason_count += 1
            reason = "missing_reason"
        self.reasons_by_status[status][reason] += 1

    def to_payload(self) -> dict[str, object]:
        """Return a JSON-friendly OOP applicability payload."""
        return {
            "applicable_count": self.applicable_count,
            "not_applicable_count": self.not_applicable_count,
            "missing_reason_count": self.missing_reason_count,
            "reasons_by_status": nested_counter_to_dict(self.reasons_by_status),
        }


def hook_family(path: Path) -> str:
    """Return the stable hook family name for one hook JSONL path."""
    return HOOK_FAMILY_COMMIT_SUFFIX_RE.sub("", path.stem)


def hook_failure_key(entry: dict[str, object], status: str) -> str:
    """Return the failure bucket for one hook entry, or empty when healthy."""
    fingerprint = str(entry.get("failure_fingerprint") or "").strip()
    if fingerprint:
        return fingerprint
    if status in {"fail", "warn", "error"}:
        return status
    return ""


def hook_skip_key(entry: dict[str, object], status: str) -> str:
    """Return the skip bucket for one hook entry, or empty when not skipped."""
    if status not in {"skip", "skipped"}:
        return ""
    return str(entry.get("skip_reason") or "").strip() or "missing_reason"


def counter_to_dict(counter: Counter[str]) -> dict[str, int]:
    """Return a stable JSON object from a counter."""
    return dict(sorted((key, int(value)) for key, value in counter.items()))


def nested_counter_to_dict(mapping: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    """Return a stable JSON object from nested counters."""
    return {
        key: counter_to_dict(value)
        for key, value in sorted(mapping.items())
        if value
    }


def read_prompt_tool_breakdown(
    hook_files: Sequence[Path],
    recent_cutoff_epoch: int | None = None,
) -> PromptToolBreakdown:
    """Return prompt capture and tool-selection summary."""
    prompt = PromptToolAccumulator()
    for hook_file in hook_files:
        for entry in HookWorkflowBreakdownReader.iter_entries(
            hook_file,
            recent_cutoff_epoch,
        ):
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
        failed_eval_reports=sum(
            skill_eval.active_failed.get(skill, 0) for skill in MARKDOWN_SKILL_IDS
        ),
        candidate_skill_entries=sum(hook_counts.candidate_skills.get(skill, 0) for skill in MARKDOWN_SKILL_IDS),
        candidate_tool_entries=sum(markdown_tools.values()),
        candidate_tools=markdown_tools,
    )


def read_reference_capture_breakdown(
    hook_files: Sequence[Path],
    recent_cutoff_epoch: int | None = None,
) -> ReferenceCaptureBreakdown:
    """Return reference-capture hook signal counts."""
    accumulator = ReferenceCaptureAccumulator()
    for hook_file in hook_files:
        for entry in HookWorkflowBreakdownReader.iter_entries(
            hook_file,
            recent_cutoff_epoch,
        ):
            accumulator.add_entry(entry)
    return accumulator.to_breakdown()


@dataclass
class PromptToolAccumulator:
    """Mutable accumulator for prompt and tool selection evidence."""

    prompt_entries: int = 0
    prompt_excerpt_entries: int = 0
    prompt_missing_excerpt_entries: int = 0
    prompt_total_chars: int = 0
    prompt_char_counts: list[int] = field(default_factory=lambda: list[int]())
    timed_prompt_char_counts: list[TimedIntMetric] = field(default_factory=lambda: list[TimedIntMetric]())
    tool_selection_entries: int = 0
    tools: Counter[str] = field(default_factory=lambda: Counter[str]())
    command_verbs: Counter[str] = field(default_factory=lambda: Counter[str]())
    selected_tools: Counter[str] = field(default_factory=lambda: Counter[str]())

    def add_entry(self, entry: dict[str, object]) -> None:
        """Add prompt and tool-selection evidence from one hook entry."""
        self.add_prompt(entry)
        self.add_tool(entry)

    def add_prompt(self, entry: dict[str, object]) -> None:
        """Add prompt capture evidence from one hook entry."""
        if entry.get("prompt_capture_status") != "present":
            return
        prompt_chars = integer_field(entry, "prompt_char_count")
        self.prompt_entries += 1
        self.prompt_total_chars += prompt_chars
        self.prompt_char_counts.append(prompt_chars)
        timestamp = parse_hook_timestamp(entry.get("timestamp"))
        if timestamp > 0:
            self.timed_prompt_char_counts.append(TimedIntMetric(timestamp, prompt_chars))
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
        for selected_tool in normalized_text_values(entry.get("selected_tools")):
            self.selected_tools[selected_tool] += 1

    def to_breakdown(self) -> PromptToolBreakdown:
        """Return immutable prompt/tool evidence."""
        return PromptToolBreakdown(
            prompt_entries=self.prompt_entries,
            prompt_excerpt_entries=self.prompt_excerpt_entries,
            prompt_missing_excerpt_entries=self.prompt_missing_excerpt_entries,
            prompt_total_chars=self.prompt_total_chars,
            prompt_char_counts=tuple(self.prompt_char_counts),
            timed_prompt_char_counts=tuple(
                sorted(self.timed_prompt_char_counts, key=lambda observation: observation.epoch)
            ),
            tool_selection_entries=self.tool_selection_entries,
            tools=self.tools,
            command_verbs=self.command_verbs,
            selected_tools=self.selected_tools,
        )


@dataclass
class ReferenceCaptureAccumulator:
    """Mutable accumulator for reference-capture hook evidence."""

    entries: int = 0
    url_observations: int = 0
    registered_url_observations: int = 0
    missing_url_observations: int = 0
    blocked_entries: int = 0
    source_fields: Counter[str] = field(default_factory=lambda: Counter[str]())
    events: Counter[str] = field(default_factory=lambda: Counter[str]())
    urls: Counter[str] = field(default_factory=lambda: Counter[str]())
    registered_urls: Counter[str] = field(default_factory=lambda: Counter[str]())
    missing_urls: Counter[str] = field(default_factory=lambda: Counter[str]())

    def add_entry(self, entry: dict[str, object]) -> None:
        """Add one reference-capture hook entry if it carries URL evidence."""
        if not entry_is_reference_capture(entry):
            return
        self.entries += 1
        self.url_observations += integer_field(entry, "url_count")
        self.registered_url_observations += integer_field(entry, "registered_count")
        self.missing_url_observations += integer_field(entry, "missing_count")
        self.blocked_entries += int(str(entry.get("decision") or "") == "block")
        self.events[str(entry.get("event") or "missing_event")] += 1
        for field_name in normalized_text_values(entry.get("source_fields")):
            self.source_fields[field_name] += 1
        for url in normalized_text_values(entry.get("urls")):
            self.urls[url] += 1
        for url in normalized_text_values(entry.get("registered_urls")):
            self.registered_urls[url] += 1
        for url in normalized_text_values(entry.get("missing_urls")):
            self.missing_urls[url] += 1

    def to_breakdown(self) -> ReferenceCaptureBreakdown:
        """Return immutable reference-capture evidence."""
        return ReferenceCaptureBreakdown(
            entries=self.entries,
            url_observations=self.url_observations,
            registered_url_observations=self.registered_url_observations,
            missing_url_observations=self.missing_url_observations,
            blocked_entries=self.blocked_entries,
            source_fields=self.source_fields,
            events=self.events,
            urls=self.urls,
            registered_urls=self.registered_urls,
            missing_urls=self.missing_urls,
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
        "## Problem Components",
        "",
        *problem_component_lines(summary),
        "",
        "## Next Actions",
        "",
        *next_action_lines(summary),
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
        "## Wave And Subagent Execution",
        "",
        *wave_execution_lines(summary),
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
        "## Reference Capture Signals",
        "",
        *reference_capture_lines(summary),
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


def hook_entry_count(path: Path, recent_cutoff_epoch: int | None = None) -> int:
    """Count hook JSONL entries inside an optional recent window."""
    return len(HookWorkflowBreakdownReader.iter_entries(path, recent_cutoff_epoch))


def filter_hook_paths(
    hook_files: Sequence[Path],
    recent_cutoff_epoch: int | None = None,
) -> tuple[Path, ...]:
    """Return hook files that contain at least one entry inside the recent window."""
    if recent_cutoff_epoch is None:
        return tuple(hook_files)
    return tuple(
        path
        for path in hook_files
        if HookWorkflowBreakdownReader.iter_entries(path, recent_cutoff_epoch)
    )


def read_hook_evidence_counts(
    root: Path,
    hook_files: Sequence[Path],
    recent_cutoff_epoch: int | None = None,
) -> HookEvidenceCounts:
    """Return hook counters from already-selected hook entries."""
    counter = HookEvidenceCounter(known_skill_ids(root), root=root)
    for path in hook_files:
        for entry in HookWorkflowBreakdownReader.iter_entries(path, recent_cutoff_epoch):
            counter.add_entry(path, entry)
    return counter.counts()


def evidence_location_lines(root: Path) -> list[str]:
    """Return the canonical runtime evidence locations."""
    return [
        f"- evidence_root: `{root.as_posix()}`",
        "- hook_jsonl_archive_mount: `.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>.jsonl`",
        "- hook_jsonl_archive_remote: `git@github.com:iwashita-nozomu/agent-canon-log.git`",
        "- agent_report_archive_index: `.agent-canon/log-archive/agent-reports/<repo-key>/index.jsonl`",
        "- agent_report_archive_command: `python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir reports/agents/<run-id>`",
        "- skill_prompt_eval_reports: `.agent-canon/log-archive/eval-results/skill-workflow-prompt/<eval-run-id>-<status>-<skill-slug>.md`",
        "- local_llm_eval_reports: `.agent-canon/log-archive/eval-results/local-llm-responsibility/<eval-run-id>-<status>.md`",
        "- workflow_selection_eval_reports: `.agent-canon/log-archive/eval-results/workflow-selection/<eval-run-id>-<status>.md`",
        "- report_quality_eval_reports: `.agent-canon/log-archive/eval-results/report-quality/<eval-run-id>-<status>.md`",
        "- durable_issues: `issues/open/AC-*.md` and `issues/closed/AC-*.md`",
        "- shared_memory: `memory/USER_PREFERENCES.md` and `memory/AGENT_PHILOSOPHY.md`",
        "- token_comparison_reports: `reports/agents/**/workflow_monitoring.md` or `reports/agents/**/*token*.md`",
        "- reference_capture_hook: `.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/reference_capture_guard.jsonl`",
        "- materialized_references: `references/external/*.md` in the parent repository that consulted the source",
        "- github_actions_dashboard: AgentCanon repository Step Summary plus uploaded artifact under `reports/agent-runtime-dashboard/` during the run",
    ]


def missing_log_archive_error(error: RuntimeError) -> bool:
    """Return whether a RuntimeError only means the read-only log archive is absent."""
    return "AgentCanon log archive root is required" in str(error)


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
        f"`{relative_path_label(family.directory, summary.root)}`",
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
        f"- `{relative_path_label(path, summary.root)}`"
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
            f"- historical_failed_skill_reports: `{sum(breakdown.failed.values())}`",
            f"- resolved_failed_skill_reports: `{sum(breakdown.resolved_failed.values())}`",
        )
    )
    return lines


def skill_eval_failure_row(breakdown: SkillEvalBreakdown, skill: str) -> str:
    """Return one per-skill eval failure table row."""
    total = breakdown.evaluated[skill]
    failed = breakdown.active_failed.get(skill, 0)
    return f"| `{skill}` | `{total}` | `{failed}` | `{failure_rate(failed, total)}` |"


def hook_workflow_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return workflow hook attribution lines."""
    breakdown = summary.hook_workflow_breakdown
    return [
        f"- hook_entries_with_workflow_attribution: `{breakdown.entries_with_workflow}`",
        f"- hook_entries_missing_workflow_attribution: `{breakdown.entries_without_workflow}`",
        f"- hook_entries_context_attributed: `{breakdown.context_attributed_entries}`",
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
    if breakdown.comparison_count == 0 and breakdown.summary_count == 0:
        return [
            "- token_comparison_status: `missing`",
            "- token_comparison_reason: `no token footprint comparison evidence found`",
            "- expected_sources: `reports/agents/**/workflow_monitoring.md`, `reports/agents/**/*token*.md`, or Codex session token_count comparisons",
        ]
    return [
        "- token_comparison_status: `present`",
        f"- token_comparison_count: `{breakdown.comparison_count}`",
        f"- token_summary_count: `{breakdown.summary_count}`",
        f"- baseline_total_tokens: `{breakdown.baseline_total_tokens}`",
        f"- candidate_total_tokens: `{breakdown.candidate_total_tokens}`",
        f"- average_token_ratio: `{average_ratio(breakdown.token_ratios)}`",
        f"- token_summary_session_count: `{breakdown.session_count}`",
        f"- token_summary_event_count: `{breakdown.token_event_count}`",
        f"- token_summary_total_tokens: `{breakdown.total_tokens}`",
        f"- latest_moving_average_total_tokens: `{breakdown.latest_moving_average_total:.3f}`",
        f"- average_tokens_per_event: `{breakdown.average_tokens_per_event:.3f}`",
        "",
        "| evidence file |",
        "| --- |",
        *token_file_rows(summary),
    ]


def wave_execution_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return wave and subagent execution evidence lines."""
    breakdown = summary.wave_execution_breakdown
    if breakdown.actual_wave_event_count == 0 and breakdown.planned_wave_count == 0:
        return [
            "- wave_execution_status: `missing`",
            "- wave_execution_reason: `no Agent Wave Ledger or Actual Wave Events evidence found`",
            "- expected_sources: `reports/agents/**/schedule.md` and `reports/agents/**/workflow_monitoring.md`",
        ]
    return [
        "- wave_execution_status: `present`",
        f"- wave_report_files: `{len(breakdown.report_files)}`",
        f"- planned_waves: `{breakdown.planned_wave_count}`",
        f"- actual_wave_events: `{breakdown.actual_wave_event_count}`",
        f"- spawned_events: `{breakdown.spawned_event_count}`",
        f"- blocked_events: `{breakdown.blocked_event_count}`",
        f"- skipped_events: `{breakdown.skipped_event_count}`",
        f"- completed_events: `{breakdown.completed_event_count}`",
        f"- missing_actual_waves: `{breakdown.missing_actual_wave_count}`",
        f"- unplanned_actual_waves: `{breakdown.unplanned_actual_wave_count}`",
        "",
        "| counter | values |",
        "| --- | --- |",
        f"| `status_counts` | `{compact_counter_summary(breakdown.events_by_status)}` |",
        f"| `authority_counts` | `{compact_counter_summary(breakdown.events_by_spawn_authority)}` |",
        f"| `spawned_roles` | `{compact_counter_summary(breakdown.spawned_roles)}` |",
        f"| `skipped_roles` | `{compact_counter_summary(breakdown.skipped_roles)}` |",
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
        "",
        "### Selected Repo Tools",
        "",
        "| repo tool | entries |",
        "| --- | ---: |",
        *counter_table_rows(breakdown.selected_tools),
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


def reference_capture_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return reference-capture hook signal lines."""
    breakdown = summary.reference_capture_breakdown
    status = "present" if breakdown.entries > 0 else "missing"
    reason = (
        "Reference-capture hook entries are present in accumulated hook JSONL."
        if status == "present"
        else "No reference-capture hook entries are present yet; consulted external sources may be invisible to later prompt improvement."
    )
    return [
        f"- reference_capture_status: `{status}`",
        f"- reference_capture_reason: `{reason}`",
        f"- reference_capture_entries: `{breakdown.entries}`",
        f"- reference_url_observations: `{breakdown.url_observations}`",
        f"- reference_registered_url_observations: `{breakdown.registered_url_observations}`",
        f"- reference_missing_url_observations: `{breakdown.missing_url_observations}`",
        f"- reference_blocked_entries: `{breakdown.blocked_entries}`",
        "",
        "### Reference Capture Events",
        "",
        "| event | entries |",
        "| --- | ---: |",
        *counter_table_rows(breakdown.events),
        "",
        "### Reference Capture Source Fields",
        "",
        "| source field | entries |",
        "| --- | ---: |",
        *counter_table_rows(breakdown.source_fields),
        "",
        "### Reference Capture URL Summary",
        "",
        "| url class | bounded summary |",
        "| --- | --- |",
        f"| `missing_urls` | `{compact_counter_summary(breakdown.missing_urls)}` |",
        f"| `registered_urls` | `{compact_counter_summary(breakdown.registered_urls)}` |",
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
                "repair missing workflow attribution, Wave execution, prompt capture, or token comparison evidence",
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
        or summary.wave_execution_breakdown.missing_actual_wave_count > 0
        or summary.wave_execution_breakdown.blocked_event_count > 0
        or summary.wave_execution_breakdown.actual_wave_event_count == 0
        or (
            summary.token_usage_breakdown.comparison_count == 0
            and summary.token_usage_breakdown.summary_count == 0
        )
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
    files = tuple(
        sorted(
            set(
                summary.token_usage_breakdown.comparison_files
                + summary.token_usage_breakdown.summary_files
            )
        )
    )[:MAX_REPORT_LINES]
    return [f"| `{path.relative_to(summary.root).as_posix()}` |" for path in files]


def problem_component_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return a glanceable component health table."""
    components = dashboard_problem_components(summary)
    lines = [
        "| type | component | status | what is wrong | evidence | next action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not components:
        return [
            *lines,
            "| `none` | `none` | `healthy` | `no problem components detected` | `dashboard` | `none` |",
        ]
    lines.extend(problem_component_row(component) for component in components)
    return lines


def dashboard_problem_components(summary: RuntimeDashboardSummary) -> tuple[ProblemComponent, ...]:
    """Return skills, workflows, tools, and hooks with dashboard-visible problems."""
    builders = (
        hook_problem_components,
        skill_problem_components,
        workflow_problem_components,
        wave_problem_components,
        evidence_problem_components,
    )
    components = [component for builder in builders for component in builder(summary)]
    components.extend(selection_problem_components(summary, "tool"))
    return tuple(sorted(components, key=problem_component_sort_key)[:MAX_REPORT_LINES])


def hook_problem_components(summary: RuntimeDashboardSummary) -> tuple[ProblemComponent, ...]:
    """Return hook components that need attention."""
    components: list[ProblemComponent] = []
    failed = summary.evidence.hook_counts.statuses.get("fail", 0)
    if failed > 0:
        components.append(
            ProblemComponent(
                component_type="hook",
                name="hook evidence",
                status="fail",
                problem=f"{failed} hook entries report status=fail",
                evidence=top_hook_failure_evidence(summary),
                next_action="repair failing hook evidence",
            )
        )
    reference = summary.reference_capture_breakdown
    if reference.entries == 0 or reference.missing_url_observations > 0:
        status = "missing" if reference.entries == 0 else "attention"
        problem = (
            "reference_capture_guard has no entries"
            if reference.entries == 0
            else f"{reference.missing_url_observations} referenced URLs are unregistered"
        )
        components.append(
            ProblemComponent(
                component_type="hook",
                name="reference_capture_guard",
                status=status,
                problem=problem,
                evidence=REFERENCE_CAPTURE_EVIDENCE_TARGET,
                next_action="materialize references or repair hook logging",
            )
        )
    return tuple(components)


def skill_problem_components(summary: RuntimeDashboardSummary) -> tuple[ProblemComponent, ...]:
    """Return skill components that need attention."""
    components: list[ProblemComponent] = []
    for skill, failed in summary.skill_eval_breakdown.active_failed.most_common(
        MAX_REPORT_LINES
    ):
        components.append(
            ProblemComponent(
                component_type="skill",
                name=skill,
                status="fail",
                problem=f"{failed} failed eval report(s)",
                evidence=f"{SKILL_EVAL_EVIDENCE_TARGET} skill={skill}",
                next_action=f"repair failed skill eval for {skill}",
            )
        )
    components.extend(selection_problem_components(summary, "skill"))
    return tuple(components)


def workflow_problem_components(summary: RuntimeDashboardSummary) -> tuple[ProblemComponent, ...]:
    """Return workflow components that need attention."""
    components: list[ProblemComponent] = []
    missing = summary.hook_workflow_breakdown.entries_without_workflow
    if missing > 0:
        components.append(
            ProblemComponent(
                component_type="workflow",
                name="_unattributed_hook_entries",
                status="attention",
                problem=f"{missing} hook entries lack workflow attribution",
                evidence=WORKFLOW_ATTRIBUTION_EVIDENCE_TARGET,
                next_action="repair workflow attribution logging",
            )
        )
    components.extend(selection_problem_components(summary, "workflow"))
    return tuple(components)


def wave_problem_components(summary: RuntimeDashboardSummary) -> tuple[ProblemComponent, ...]:
    """Return wave execution components that need attention."""
    breakdown = summary.wave_execution_breakdown
    components: list[ProblemComponent] = []
    if breakdown.missing_actual_wave_count > 0:
        components.append(
            ProblemComponent(
                component_type="workflow",
                name="wave_execution_reconciliation",
                status="fail",
                problem=f"{breakdown.missing_actual_wave_count} planned wave(s) lack actual events",
                evidence=WAVE_EXECUTION_EVIDENCE_TARGET,
                next_action="record actual spawned/skipped/blocked wave rows",
            )
        )
    if breakdown.actual_wave_event_count == 0:
        components.append(
            ProblemComponent(
                component_type="workflow",
                name="wave_execution_evidence",
                status="missing",
                problem="no wave execution events are present",
                evidence=WAVE_EXECUTION_EVIDENCE_TARGET,
                next_action="bootstrap a run with an explicit wave execution gate",
            )
        )
    elif breakdown.blocked_event_count > 0:
        components.append(
            ProblemComponent(
                component_type="workflow",
                name="wave_execution_authority",
                status="attention",
                problem=f"{breakdown.blocked_event_count} wave event(s) are authority blocked",
                evidence=WAVE_EXECUTION_EVIDENCE_TARGET,
                next_action="parent runtime must spawn or explicitly skip the wave",
            )
        )
    return tuple(components)


def evidence_problem_components(summary: RuntimeDashboardSummary) -> tuple[ProblemComponent, ...]:
    """Return cross-cutting evidence components that need attention."""
    components: list[ProblemComponent] = []
    prompt = summary.prompt_tool_breakdown
    if prompt.prompt_entries == 0 or prompt.tool_selection_entries == 0:
        components.append(
            ProblemComponent(
                component_type="hook",
            name="skill_usage_logger",
            status="missing",
            problem="prompt or tool selection evidence is missing",
            evidence=PROMPT_TOOL_EVIDENCE_TARGET,
            next_action="repair prompt/tool evidence logging",
        )
        )
    if (
        summary.token_usage_breakdown.comparison_count == 0
        and summary.token_usage_breakdown.summary_count == 0
    ):
        components.append(
            ProblemComponent(
                component_type="workflow",
                name="token_consumption_evidence",
                status="missing",
                problem="no token footprint comparison or moving-average evidence found",
                evidence=TOKEN_USAGE_EVIDENCE_TARGET,
                next_action="record token usage evidence",
            )
        )
    return tuple(components)


def selection_problem_components(
    summary: RuntimeDashboardSummary,
    responsibility: str,
) -> tuple[ProblemComponent, ...]:
    """Return selection-miss components for one responsibility."""
    components: list[ProblemComponent] = []
    for row in summary.selection_metrics_breakdown.metrics:
        if row.responsibility != responsibility or row.missed_count <= 0:
            continue
        components.append(
            ProblemComponent(
                component_type=responsibility,
                name=row.name,
                status="attention",
                problem=f"{row.missed_count} candidate miss(es); miss rate {failure_rate(row.missed_count, row.candidate_count)}",
                evidence=SELECTION_EVIDENCE_TARGET,
                next_action=f"repair {responsibility} selection or logging",
            )
        )
    return tuple(components)


def problem_component_row(component: ProblemComponent) -> str:
    """Return one problem-component Markdown table row."""
    cells = (
        component.component_type,
        component.name,
        component.status,
        component.problem,
        component.evidence,
        component.next_action,
    )
    return "| " + " | ".join(table_cell(cell) for cell in cells) + " |"


def problem_component_sort_key(component: ProblemComponent) -> tuple[int, str, str]:
    """Return stable sort key for problem components."""
    status_order = {"fail": 0, "attention": 1, "missing": 2}
    return (
        status_order.get(component.status, UNKNOWN_SORT_ORDER),
        component.component_type,
        component.name,
    )


def next_action_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return a concrete next-action table generated from dashboard signals."""
    actions = dashboard_next_actions(summary)
    lines = [
        "| priority | action | reason | evidence | owner surface | command | done condition | issue | automation |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not actions:
        return [
            *lines,
            "| `none` | no immediate dashboard action | all observed dashboard signals are healthy | `dashboard` | `none` | `none` | `next_action_count=0` | `none` | `none` |",
        ]
    lines.extend(next_action_row(action) for action in actions)
    return lines


def dashboard_next_actions(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return prioritized concrete next actions inferred from dashboard metrics."""
    builders = (
        hook_failure_next_action,
        reference_capture_next_action,
        workflow_attribution_next_action,
        wave_execution_next_action,
        selection_metrics_next_action,
        skill_eval_next_action,
        markdown_docs_next_action,
        prompt_tool_next_action,
        token_usage_next_action,
        durable_issue_next_action,
    )
    actions = [action for builder in builders for action in builder(summary)]
    return tuple(sorted(actions, key=next_action_sort_key))


def hook_failure_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for failing hook evidence."""
    failed = summary.evidence.hook_counts.statuses.get("fail", 0)
    if failed <= 0:
        return ()
    evidence = top_hook_failure_evidence(summary)
    return (DashboardNextAction(
        priority="P0",
        action="repair failing hook evidence",
        reason=f"{failed} hook entries report status=fail",
        evidence=evidence,
        owner_surface=".codex/hooks/ and hook accumulation tooling",
        command="python3 tools/agent_tools/eval_accumulation_check.py",
        done_condition="hook status fail count is 0",
        issue=issue_label_by_slug(summary, "eval-accumulation-gaps"),
        automation="agent-fix",
    ),)


def top_hook_failure_evidence(summary: RuntimeDashboardSummary) -> str:
    """Return a compact-report evidence target for the top failure fingerprint."""
    fingerprint = top_hook_failure_fingerprint(summary)
    if fingerprint == "none":
        return "compact report Hook Failure Drilldown"
    return f"compact report Hook Failure Drilldown fingerprint={fingerprint}"


def top_hook_failure_fingerprint(summary: RuntimeDashboardSummary) -> str:
    """Return the most frequent hook failure fingerprint."""
    fingerprint = top_counter_key(summary.evidence.hook_counts.failures, "hook failure fingerprints")
    if fingerprint == "none":
        return "none"
    return fingerprint


def reference_capture_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for reference-capture evidence gaps."""
    breakdown = summary.reference_capture_breakdown
    if breakdown.entries == 0:
        return (DashboardNextAction(
            priority="P1",
            action="confirm reference capture hook is producing evidence",
            reason="no reference_capture_guard entries are present",
            evidence=REFERENCE_CAPTURE_EVIDENCE_TARGET,
            owner_surface=".codex/hooks/reference_capture_guard.py",
            command="python3 tools/agent_tools/generate_agent_runtime_dashboard.py --root .",
            done_condition="AGENT_RUNTIME_DASHBOARD_REFERENCE_CAPTURE_ENTRIES>0",
            issue=issue_label_by_slug(summary, "eval-accumulation-gaps"),
            automation="agent-fix",
        ),)
    if breakdown.missing_url_observations <= 0 and breakdown.blocked_entries <= 0:
        return ()
    return (DashboardNextAction(
        priority="P1",
        action="materialize missing consulted source URLs",
        reason=f"{breakdown.missing_url_observations} observed URLs are not registered",
        evidence=REFERENCE_CAPTURE_EVIDENCE_TARGET,
        owner_surface="references/external/ and tools/agent_tools/reference_materializer.py",
        command="python3 tools/agent_tools/reference_materializer.py --url <url> --input <pdf-or-html>",
        done_condition="AGENT_RUNTIME_DASHBOARD_REFERENCE_MISSING_URLS=0",
        issue=issue_label_by_slug(summary, "eval-accumulation-gaps"),
        automation="agent-fix-with-source-file",
    ),)


def workflow_attribution_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for missing workflow attribution."""
    breakdown = summary.hook_workflow_breakdown
    if breakdown.entries_without_workflow <= 0:
        return ()
    return (DashboardNextAction(
        priority="P1",
        action="repair workflow attribution logging",
        reason=f"{breakdown.entries_without_workflow} hook entries lack workflow attribution",
        evidence=WORKFLOW_ATTRIBUTION_EVIDENCE_TARGET,
        owner_surface=".codex/hooks/skill_usage_logger.py and workflow_monitoring.md",
        command="python3 tools/agent_tools/generate_agent_runtime_dashboard.py --root .",
        done_condition="AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING=0 or entries are explicitly exempt",
        issue=issue_label_by_slug(summary, "eval-accumulation-gaps"),
        automation="agent-fix",
    ),)


def wave_execution_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for wave execution evidence gaps."""
    breakdown = summary.wave_execution_breakdown
    if breakdown.missing_actual_wave_count > 0:
        return (DashboardNextAction(
            priority="P1",
            action="record missing actual wave execution rows",
            reason=f"{breakdown.missing_actual_wave_count} planned waves lack actual events",
            evidence=WAVE_EXECUTION_EVIDENCE_TARGET,
            owner_surface="schedule.md and workflow_monitoring.md",
            command="python3 tools/agent_tools/task_close.py --run-id <run-id>",
            done_condition="AGENT_RUNTIME_DASHBOARD_WAVE_MISSING_ACTUAL=0",
            issue=issue_label_by_slug(summary, "wave-activation-launcher-gap"),
            automation="agent-fix",
        ),)
    if breakdown.blocked_event_count > 0:
        return (DashboardNextAction(
            priority="P1",
            action="resolve wave execution authority blockers",
            reason=f"{breakdown.blocked_event_count} wave events are authority blocked",
            evidence=WAVE_EXECUTION_EVIDENCE_TARGET,
            owner_surface="parent Codex runtime subagent wave and run bundle ledger",
            command="spawn/skip the listed roles, then update schedule.md and workflow_monitoring.md",
            done_condition="AGENT_RUNTIME_DASHBOARD_WAVE_BLOCKED=0 or explicit skipped wave rows remain",
            issue=issue_label_by_slug(summary, "wave-activation-launcher-gap"),
            automation="parent-runtime",
        ),)
    if breakdown.actual_wave_event_count > 0:
        return ()
    return (DashboardNextAction(
        priority="P2",
        action="add wave execution evidence to run bundles",
        reason="no Actual Wave Events rows were found",
        evidence=WAVE_EXECUTION_EVIDENCE_TARGET,
        owner_surface="tools/agent_tools/agent_team.py",
        command="python3 tools/agent_tools/bootstrap_agent_run.py --task-id <id>",
        done_condition="AGENT_RUNTIME_DASHBOARD_WAVE_EVENTS>0",
        issue=issue_label_by_slug(summary, "wave-activation-launcher-gap"),
        automation="agent-fix",
    ),)


def selection_metrics_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for selection misses."""
    missed = selection_missed_total(summary)
    if missed <= 0:
        return ()
    row = max(summary.selection_metrics_breakdown.metrics, key=lambda item: item.missed_count)
    return (DashboardNextAction(
        priority="P1",
        action=f"repair {row.responsibility} selection for {row.name}",
        reason=f"{missed} candidate selections were not confirmed",
        evidence=SELECTION_EVIDENCE_TARGET,
        owner_surface=row.reset_path,
        command="python3 tools/agent_tools/generate_agent_runtime_dashboard.py --root .",
        done_condition=f"{row.responsibility}:{row.name} miss rate is 0% after its reset window",
        issue=issue_label_by_slug(summary, "eval-accumulation-gaps"),
        automation="human-review-then-agent-fix",
    ),)


def skill_eval_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for failed skill evals."""
    failed = summary.skill_eval_breakdown.active_failed
    if not failed:
        return ()
    skill = failed.most_common(1)[0][0]
    return (DashboardNextAction(
        priority="P1",
        action=f"repair failed skill eval for {skill}",
        reason=f"{failed[skill]} failed eval reports are attributed to {skill}",
        evidence=f"{SKILL_EVAL_EVIDENCE_TARGET} skill={skill}",
        owner_surface=selection_reset_path_for(summary.root, "skill", skill),
        command="python3 tools/agent_tools/evaluate_skill_workflow_prompts.py",
        done_condition=f"{skill} failed eval reports are 0",
        issue=issue_label_by_slug(summary, "eval-accumulation-gaps"),
        automation="agent-fix",
    ),)


def markdown_docs_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for Markdown/docs checker signals."""
    breakdown = summary.markdown_docs_breakdown
    if breakdown.failed_eval_reports <= 0 and markdown_hook_signal_count(summary) > 0:
        return ()
    priority = "P1" if breakdown.failed_eval_reports > 0 else "P2"
    reason = (
        f"{breakdown.failed_eval_reports} Markdown skill evals failed"
        if breakdown.failed_eval_reports > 0
        else "Markdown/docs hook signals are missing"
    )
    return (DashboardNextAction(
        priority=priority,
        action="repair Markdown/docs checking signal",
        reason=reason,
        evidence=MARKDOWN_EVIDENCE_TARGET,
        owner_surface=".agents/skills/md-style-check/SKILL.md and rust/agent-canon/src/docs.rs",
        command="tools/bin/agent-canon docs check",
        done_condition="markdown eval failures are 0 and markdown hook signal is present",
        issue=issue_label_by_slug(summary, "eval-accumulation-gaps"),
        automation="agent-fix",
    ),)


def prompt_tool_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for prompt/tool selection evidence gaps."""
    breakdown = summary.prompt_tool_breakdown
    if (
        breakdown.prompt_entries > 0
        and breakdown.tool_selection_entries > 0
        and breakdown.prompt_missing_excerpt_entries == 0
    ):
        return ()
    return (DashboardNextAction(
        priority="P2",
        action="repair prompt and tool selection evidence",
        reason="prompt excerpts or tool selection entries are missing",
        evidence=PROMPT_TOOL_EVIDENCE_TARGET,
        owner_surface=".codex/hooks/skill_usage_logger.py",
        command="python3 tools/agent_tools/generate_agent_runtime_dashboard.py --root .",
        done_condition="prompt_entries>0, tool_selection_entries>0, prompt_missing_excerpt_entries=0",
        issue=issue_label_by_slug(summary, "eval-accumulation-gaps"),
        automation="agent-fix",
    ),)


def token_usage_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for missing token evidence."""
    if (
        summary.token_usage_breakdown.comparison_count > 0
        or summary.token_usage_breakdown.summary_count > 0
    ):
        return ()
    return (DashboardNextAction(
        priority="P2",
        action="add token consumption moving-average evidence",
        reason="no token footprint comparison or moving-average evidence found",
        evidence=TOKEN_USAGE_EVIDENCE_TARGET,
        owner_surface="workflow_monitoring.md and token logging hooks",
        command="python3 tools/agent_tools/compare_codex_token_footprints.py --session-glob '<sessions>' --report-dir <run>",
        done_condition="AGENT_RUNTIME_DASHBOARD_TOKEN_COMPARISONS>0 or AGENT_RUNTIME_DASHBOARD_TOKEN_SUMMARIES>0",
        issue=issue_label_by_slug(summary, "eval-accumulation-gaps"),
        automation="human-review-then-agent-fix",
    ),)


def durable_issue_next_action(summary: RuntimeDashboardSummary) -> tuple[DashboardNextAction, ...]:
    """Return the next action for open durable issues."""
    if not summary.evidence.open_issues:
        return ()
    issue = summary.evidence.open_issues[0].relative_to(summary.root).as_posix()
    return (DashboardNextAction(
        priority="P2",
        action="triage oldest open durable issue",
        reason=f"{len(summary.evidence.open_issues)} durable issues are open",
        evidence=issue,
        owner_surface="issues/open/ and issues/closed/",
        command="python3 tools/agent_tools/issue_sync.py",
        done_condition="issue is resolved, moved to issues/closed, or explicitly deferred",
        issue=f"`{issue}`",
        automation="human-review",
    ),)


def next_action_row(action: DashboardNextAction) -> str:
    """Return one Markdown table row for a next action."""
    cells = (
        action.priority,
        action.action,
        action.reason,
        action.evidence,
        action.owner_surface,
        action.command,
        action.done_condition,
        action.issue,
        action.automation,
    )
    return "| " + " | ".join(table_cell(cell) for cell in cells) + " |"


def table_cell(value: str) -> str:
    """Return a compact Markdown table cell."""
    return f"`{value.replace('|', '/')}`"


def next_action_sort_key(action: DashboardNextAction) -> tuple[int, str]:
    """Return stable priority sorting for dashboard actions."""
    order = {"P0": 0, "P1": 1, "P2": 2}
    return (order.get(action.priority, UNKNOWN_SORT_ORDER), action.action)


def blocking_next_action_count(summary: RuntimeDashboardSummary) -> int:
    """Return P0/P1 next action count."""
    return sum(1 for action in dashboard_next_actions(summary) if action.priority in {"P0", "P1"})


def top_counter_key(counter: Counter[str], default_key: str) -> str:
    """Return the most common key from a counter."""
    if not counter:
        return default_key
    return counter.most_common(1)[0][0]


def selection_reset_path_for(root: Path, responsibility: str, name: str) -> str:
    """Return a likely owner path for one selectable item."""
    reset = read_selection_reset(root, responsibility, name)
    return reset.reset_path


def issue_label_by_slug(summary: RuntimeDashboardSummary, slug: str) -> str:
    """Return a dashboard issue label for one slug."""
    issue = issue_by_slug(summary, slug)
    if issue is None:
        return "missing-local-issue"
    return issue.relative_to(summary.root).as_posix()


def relative_path_label(path: Path, root: Path) -> str:
    """Return a root-relative path label when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def machine_summary_lines(summary: RuntimeDashboardSummary) -> list[str]:
    """Return the machine-readable summary block."""
    return [
        "AGENT_RUNTIME_DASHBOARD_STATUS=pass",
        f"AGENT_RUNTIME_DASHBOARD_EVIDENCE_ROOT={summary.root.as_posix()}",
        f"AGENT_RUNTIME_DASHBOARD_RECENT_DAYS={summary.recent_days if summary.recent_days is not None else 'all'}",
        f"AGENT_RUNTIME_DASHBOARD_HOOK_FILES={len(summary.hook_files)}",
        f"AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES={summary.hook_entries}",
        f"AGENT_RUNTIME_DASHBOARD_SKILL_EVAL_REPORTS={family_count(summary, 'skill-workflow-prompt')}",
        f"AGENT_RUNTIME_DASHBOARD_LOCAL_LLM_REPORTS={family_count(summary, 'local-llm-responsibility')}",
        f"AGENT_RUNTIME_DASHBOARD_WORKFLOW_SELECTION_REPORTS={family_count(summary, 'workflow-selection')}",
        f"AGENT_RUNTIME_DASHBOARD_REPORT_QUALITY_REPORTS={family_count(summary, 'report-quality')}",
        f"AGENT_RUNTIME_DASHBOARD_CODEX_AGENT_ROLE_REPORTS={family_count(summary, 'codex-agent-role')}",
        f"AGENT_RUNTIME_DASHBOARD_SKILL_EVAL_FAILED_SKILLS={len(summary.skill_eval_breakdown.active_failed)}",
        f"AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_ATTRIBUTED={summary.hook_workflow_breakdown.entries_with_workflow}",
        f"AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING={summary.hook_workflow_breakdown.entries_without_workflow}",
        f"AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_CONTEXT_ATTRIBUTED={summary.hook_workflow_breakdown.context_attributed_entries}",
        f"AGENT_RUNTIME_DASHBOARD_TOKEN_COMPARISONS={summary.token_usage_breakdown.comparison_count}",
        f"AGENT_RUNTIME_DASHBOARD_TOKEN_SUMMARIES={summary.token_usage_breakdown.summary_count}",
        f"AGENT_RUNTIME_DASHBOARD_TOKEN_SUMMARY_SESSIONS={summary.token_usage_breakdown.session_count}",
        f"AGENT_RUNTIME_DASHBOARD_TOKEN_SUMMARY_EVENTS={summary.token_usage_breakdown.token_event_count}",
        f"AGENT_RUNTIME_DASHBOARD_WAVE_REPORTS={len(summary.wave_execution_breakdown.report_files)}",
        f"AGENT_RUNTIME_DASHBOARD_WAVE_PLANNED={summary.wave_execution_breakdown.planned_wave_count}",
        f"AGENT_RUNTIME_DASHBOARD_WAVE_EVENTS={summary.wave_execution_breakdown.actual_wave_event_count}",
        f"AGENT_RUNTIME_DASHBOARD_WAVE_SPAWNED={summary.wave_execution_breakdown.spawned_event_count}",
        f"AGENT_RUNTIME_DASHBOARD_WAVE_BLOCKED={summary.wave_execution_breakdown.blocked_event_count}",
        f"AGENT_RUNTIME_DASHBOARD_WAVE_SKIPPED={summary.wave_execution_breakdown.skipped_event_count}",
        f"AGENT_RUNTIME_DASHBOARD_WAVE_COMPLETED={summary.wave_execution_breakdown.completed_event_count}",
        f"AGENT_RUNTIME_DASHBOARD_WAVE_MISSING_ACTUAL={summary.wave_execution_breakdown.missing_actual_wave_count}",
        f"AGENT_RUNTIME_DASHBOARD_WAVE_UNPLANNED_ACTUAL={summary.wave_execution_breakdown.unplanned_actual_wave_count}",
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
        f"AGENT_RUNTIME_DASHBOARD_REFERENCE_CAPTURE_ENTRIES={summary.reference_capture_breakdown.entries}",
        f"AGENT_RUNTIME_DASHBOARD_REFERENCE_URL_OBSERVATIONS={summary.reference_capture_breakdown.url_observations}",
        f"AGENT_RUNTIME_DASHBOARD_REFERENCE_MISSING_URLS={summary.reference_capture_breakdown.missing_url_observations}",
        f"AGENT_RUNTIME_DASHBOARD_REFERENCE_BLOCKED_ENTRIES={summary.reference_capture_breakdown.blocked_entries}",
        f"AGENT_RUNTIME_DASHBOARD_PROBLEM_COMPONENTS={len(dashboard_problem_components(summary))}",
        f"AGENT_RUNTIME_DASHBOARD_NEXT_ACTIONS={len(dashboard_next_actions(summary))}",
        f"AGENT_RUNTIME_DASHBOARD_BLOCKING_NEXT_ACTIONS={blocking_next_action_count(summary)}",
        f"AGENT_RUNTIME_DASHBOARD_OPEN_ISSUES={len(summary.evidence.open_issues)}",
        f"AGENT_RUNTIME_DASHBOARD_CLOSED_ISSUES={len(summary.evidence.closed_issues)}",
    ]


def entry_is_reference_capture(entry: dict[str, object]) -> bool:
    """Return whether a hook entry carries reference-capture evidence."""
    return "url_count" in entry or str(entry.get("hook_name") or "") == "reference_capture_guard"


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


def split_counter_field(value: str) -> tuple[str, ...]:
    """Return comma-separated role names from one wave-event counter field."""
    roles: list[str] = []
    for item in value.split(","):
        role = item.strip()
        if not role or role.lower() == "none":
            continue
        roles.append(role.split(":", 1)[0])
    return tuple(roles)


def integer_field(entry: dict[str, object], key: str) -> int:
    """Return an integer field from a hook entry."""
    value = entry.get(key)
    return value if isinstance(value, int) else 0


def selection_namespace(entry: dict[str, object], hook_file: Path) -> str:
    """Return the runtime namespace used for cross-entry selection matching."""
    return str(entry.get("hook_log_namespace") or hook_file.parent.name or "missing_namespace")


def future_selected_positions(
    events: Sequence[
        tuple[
            int,
            int,
            str,
            dict[str, tuple[str, ...]],
            dict[str, tuple[str, ...]],
        ]
    ],
) -> dict[tuple[str, str, str], tuple[int, ...]]:
    """Return selected component positions keyed by namespace and responsibility."""
    positions: defaultdict[tuple[str, str, str], list[int]] = defaultdict(list)
    for sequence, _epoch, namespace, selected, _candidates in events:
        for responsibility, names in selected.items():
            for name in names:
                positions[(namespace, responsibility, name)].append(sequence)
                positions[(ALL_SELECTION_NAMESPACES, responsibility, name)].append(sequence)
    return {key: tuple(value) for key, value in positions.items()}


def has_future_selection(
    positions: dict[tuple[str, str, str], tuple[int, ...]],
    namespace: str,
    responsibility: str,
    name: str,
    sequence: int,
) -> bool:
    """Return whether a candidate is confirmed later in the same runtime namespace."""
    namespace_match = any(
        selected_sequence >= sequence
        for selected_sequence in positions.get((namespace, responsibility, name), ())
    )
    if namespace_match:
        return True
    if responsibility == "workflow" or (responsibility, name) in CROSS_NAMESPACE_SELECTION_COMPONENTS:
        return bool(positions.get((ALL_SELECTION_NAMESPACES, responsibility, name), ()))
    return False


def selected_by_responsibility(
    entry: dict[str, object],
    hook_file: Path | None = None,
) -> dict[str, tuple[str, ...]]:
    """Return selected skills, workflows, and tools from one hook entry."""
    skills = list(normalized_text_values(entry.get("skills")))
    if hook_file is not None and hook_file.name == "oop_readability_guard.jsonl":
        skills.append("oop-readability-check")
    return {
        "skill": unique_text_values(skills),
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
    names.extend(normalized_text_values(entry.get("selected_tools")))
    names.extend(command_tool_values(entry.get("commands")))
    return unique_text_values(names)


def canonical_selection_values(
    responsibility: str,
    values: tuple[str, ...],
    valid_skill_ids: Collection[str],
    valid_workflow_names: Collection[str],
) -> tuple[str, ...]:
    """Return responsibility-local canonical selection values."""
    if responsibility == "skill":
        if not valid_skill_ids:
            return unique_text_values(values)
        return tuple(value for value in unique_text_values(values) if value in valid_skill_ids)
    if responsibility == "workflow":
        workflows = unique_text_values(canonical_workflow_name(value) for value in values)
        if not valid_workflow_names:
            return workflows
        return tuple(value for value in workflows if value in valid_workflow_names)
    if responsibility == "tool":
        return unique_text_values(canonical_tool_name(value) for value in values)
    return unique_text_values(values)


def canonical_tool_name(value: str) -> str:
    """Return the canonical tool id used for selection accounting."""
    return TOOL_SELECTION_ALIASES.get(value, value)


def canonical_workflow_name(value: str) -> str:
    """Return a stable workflow selection slug."""
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return re.sub(r"-+", "-", normalized)


def known_workflow_names(root: Path) -> frozenset[str]:
    """Return canonical workflow family names from the task catalog."""
    catalog = root / "agents" / "task_catalog.yaml"
    if not catalog.is_file():
        return frozenset()
    names: set[str] = set()
    in_workflow_families = False
    for line in catalog.read_text(encoding="utf-8").splitlines():
        if line.strip() == "workflow_families:":
            in_workflow_families = True
            continue
        if in_workflow_families and line and not line.startswith(" "):
            break
        if not in_workflow_families:
            continue
        match = re.match(r"\s*-\s+id:\s+([A-Za-z0-9_-]+)\s*$", line)
        if match is not None:
            names.add(canonical_workflow_name(match.group(1)))
    return frozenset(names)


def workflow_names_from_run_bundle(text: str) -> tuple[str, ...]:
    """Return canonical workflow selections from run-bundle monitoring text."""
    workflows: list[str] = []
    for match in RUN_BUNDLE_WORKFLOW_RE.finditer(text):
        name = canonical_workflow_name(match.group(1))
        if name and name != "unspecified":
            workflows.append(name)
    return unique_text_values(workflows)


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
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def parse_compact_utc_timestamp(value: str) -> int:
    """Return epoch seconds parsed from a compact UTC run id timestamp."""
    trimmed = value.removesuffix("Z")
    if len(trimmed) == len("YYYYMMDDTHHMMSS"):
        format_string = "%Y%m%dT%H%M%S"
    else:
        format_string = "%Y%m%dT%H%M%S%f"
    try:
        parsed = datetime.strptime(trimmed, format_string).replace(tzinfo=UTC)
    except ValueError:
        return NO_RESET_EPOCH
    return int(parsed.timestamp())


def recent_cutoff_epoch(recent_days: int | None) -> int | None:
    """Return the lower epoch bound for a recent-day filter."""
    if recent_days is None:
        return None
    return int(time.time()) - recent_days * HOURS_PER_DAY * MINUTES_PER_HOUR * SECONDS_PER_MINUTE


def path_mtime_epoch(path: Path) -> int:
    """Return file mtime as an epoch second, or zero when unavailable."""
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return NO_RESET_EPOCH


def path_inside_recent_window(path: Path, recent_cutoff_epoch: int | None) -> bool:
    """Return whether a path is inside an optional mtime-based recent window."""
    return recent_cutoff_epoch is None or path_mtime_epoch(path) >= recent_cutoff_epoch


def evidence_inside_recent_window(
    path: Path,
    evidence_epoch: int,
    recent_cutoff_epoch: int | None,
) -> bool:
    """Return whether timestamped evidence is inside an optional recent window."""
    if recent_cutoff_epoch is None:
        return True
    if evidence_epoch > 0:
        return evidence_epoch >= recent_cutoff_epoch
    return path_inside_recent_window(path, recent_cutoff_epoch)


def timestamped_evidence_after_cutoff(
    path: Path,
    evidence_epoch: int,
    cutoff_epoch: int,
) -> bool:
    """Return whether timestamped evidence is at or after a concrete cutoff."""
    if evidence_epoch > NO_RESET_EPOCH:
        return evidence_epoch >= cutoff_epoch
    return path_mtime_epoch(path) >= cutoff_epoch


def hook_entry_inside_recent_window(
    entry: dict[str, object],
    hook_file: Path,
    recent_cutoff_epoch: int | None,
) -> bool:
    """Return whether one hook entry is inside an optional recent window."""
    if recent_cutoff_epoch is None:
        return True
    entry_epoch = parse_hook_timestamp(entry.get("timestamp"))
    if entry_epoch > 0:
        return entry_epoch >= recent_cutoff_epoch
    return path_inside_recent_window(hook_file, recent_cutoff_epoch)


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
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%d")


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


def rolling_average_timed_ratio(values: Sequence[TimedFloatMetric]) -> str:
    """Return a compact chronological moving-average ratio."""
    return average_ratio(tuple(observation.value for observation in values[-ROLLING_TREND_WINDOW:]))


def mean_int_label(values: Sequence[int]) -> str:
    """Return a compact integer mean label."""
    if not values:
        return "unknown"
    return str(round(sum(values) / len(values)))


def rolling_mean_timed_int_label(values: Sequence[TimedIntMetric]) -> str:
    """Return a compact chronological integer moving-average label."""
    return mean_int_label(tuple(observation.value for observation in values[-ROLLING_TREND_WINDOW:]))


def prompt_token_joint_status(summary: RuntimeDashboardSummary) -> str:
    """Return whether prompt and token trend observations can be compared."""
    prompt_count = len(summary.prompt_tool_breakdown.timed_prompt_char_counts)
    token_count = len(summary.token_usage_breakdown.timed_token_ratios)
    if prompt_count == 0 and token_count == 0:
        return "missing_prompt_and_token_observations"
    if prompt_count == 0:
        return "missing_prompt_observations"
    if token_count == 0:
        return "missing_token_observations"
    if prompt_count < ROLLING_TREND_WINDOW or token_count < ROLLING_TREND_WINDOW:
        return "limited_joint_window"
    return "ready"


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
    parser.add_argument(
        "--compact-out",
        type=Path,
        help=(
            "Optional token-light Markdown summary path for agent log analysis. "
            "The compact report contains machine summary, priority problems, "
            "next actions, and selection misses without raw JSONL excerpts."
        ),
    )
    parser.add_argument(
        "--api-out",
        "--api-output",
        dest="api_out",
        type=Path,
        help="Optional stable JSON API summary path for agent log analysis.",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        help=(
            "Limit hook, eval, and token evidence to entries or reports from the "
            "last N days. Hook entries use their timestamp when present and fall "
            "back to JSONL mtime."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate an AgentCanon runtime dashboard."""
    args = build_parser().parse_args(argv)
    dashboard = AgentRuntimeDashboard(args.root, recent_days=args.recent_days)
    summary = dashboard.collect()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard(summary), encoding="utf-8")
    if args.compact_out is not None:
        args.compact_out.parent.mkdir(parents=True, exist_ok=True)
        args.compact_out.write_text(render_compact_dashboard(summary), encoding="utf-8")
    if args.api_out is not None:
        args.api_out.parent.mkdir(parents=True, exist_ok=True)
        args.api_out.write_text(render_dashboard_api(summary), encoding="utf-8")
    print(f"AGENT_RUNTIME_DASHBOARD={output}")
    print("AGENT_RUNTIME_DASHBOARD_STATUS=pass")
    print(f"AGENT_RUNTIME_DASHBOARD_EVIDENCE_ROOT={summary.root.as_posix()}")
    print(f"AGENT_RUNTIME_DASHBOARD_RECENT_DAYS={summary.recent_days if summary.recent_days is not None else 'all'}")
    print(f"AGENT_RUNTIME_DASHBOARD_HOOK_FILES={len(summary.hook_files)}")
    print(f"AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES={summary.hook_entries}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
