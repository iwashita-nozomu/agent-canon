#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Generates PR and push-time guidance from AgentCanon memory, eval, hook, and issue evidence.
# upstream design ../../evidence/agent-evals/README.md eval evidence contract
# upstream design ../../documents/runtime-log-archive.md hook result accumulation contract
# upstream implementation ./runtime_log_paths.py resolves mounted archive result paths
# upstream design ../../issues/README.md durable operational issue storage
# downstream implementation ../../.github/workflows/agent-improvement-guide.yml runs this on PR and push
# downstream implementation ../../tests/agent_tools/test_generate_agent_improvement_guide.py tests guide generation
# @dependency-end
"""Generate a deterministic AgentCanon improvement guide."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime_log_paths import (  # noqa: E402
    eval_result_search_dirs,
    hook_result_search_dirs,
)

COMMIT_TIME_FORMAT = "%ct"
GIT_LOG_TIMEOUT_SECONDS = 5
MAX_HOOK_FAILURE_LINES = 20
MAX_COUNTER_LINES = 20
NO_RESET_EPOCH = -1
CHECKER_TARGET_SUFFIXES = (
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
)
OPTION_VALUE_FLAGS = {
    "--baseline-ref",
    "--format",
    "--min-score",
    "--out",
    "--output",
    "--report-dir",
    "--root",
}
TRUSTED_SKILL_SOURCE_FIELDS = frozenset(("prompt", "last_assistant_message", "message"))


@dataclass(frozen=True)
class HookEvidenceCounts:
    """Summarized hook-run counters."""

    statuses: Counter[str]
    failures: Counter[str]
    files: Counter[str]
    events: Counter[str]
    namespaces: Counter[str]
    tools: Counter[str]
    skills: Counter[str]
    candidate_skills: Counter[str]
    candidate_workflows: Counter[str]
    candidate_tools: Counter[str]
    skill_events: Counter[str]
    skill_sources: Counter[str]
    feedback_labels: Counter[str]
    feedback_targets: Counter[str]
    feedback_actions: Counter[str]
    checker_targets: Counter[str]
    failure_targets: Counter[str]
    quality: Counter[str]


@dataclass(frozen=True)
class EvidenceSummary:
    """Summarized AgentCanon improvement evidence."""

    open_issues: tuple[Path, ...]
    closed_issues: tuple[Path, ...]
    memory_entries: dict[str, int]
    skill_eval_reports: tuple[Path, ...]
    failed_skill_eval_reports: tuple[Path, ...]
    hook_counts: HookEvidenceCounts


@dataclass
class HookCounterState:
    """Mutable hook evidence counters owned by one collector."""

    statuses: Counter[str]
    failures: Counter[str]
    files: Counter[str]
    events: Counter[str]
    namespaces: Counter[str]
    tools: Counter[str]
    skills: Counter[str]
    candidate_skills: Counter[str]
    candidate_workflows: Counter[str]
    candidate_tools: Counter[str]
    skill_events: Counter[str]
    skill_sources: Counter[str]
    feedback_labels: Counter[str]
    feedback_targets: Counter[str]
    feedback_actions: Counter[str]
    checker_targets: Counter[str]
    failure_targets: Counter[str]
    quality: Counter[str]

    @classmethod
    def empty(cls) -> HookCounterState:
        """Create empty mutable counters."""
        return cls(
            statuses=Counter(),
            failures=Counter(),
            files=Counter(),
            events=Counter(),
            namespaces=Counter(),
            tools=Counter(),
            skills=Counter(),
            candidate_skills=Counter(),
            candidate_workflows=Counter(),
            candidate_tools=Counter(),
            skill_events=Counter(),
            skill_sources=Counter(),
            feedback_labels=Counter(),
            feedback_targets=Counter(),
            feedback_actions=Counter(),
            checker_targets=Counter(),
            failure_targets=Counter(),
            quality=Counter(),
        )

    def to_counts(self) -> HookEvidenceCounts:
        """Return immutable summary counters."""
        return HookEvidenceCounts(
            statuses=self.statuses,
            failures=self.failures,
            files=self.files,
            events=self.events,
            namespaces=self.namespaces,
            tools=self.tools,
            skills=self.skills,
            candidate_skills=self.candidate_skills,
            candidate_workflows=self.candidate_workflows,
            candidate_tools=self.candidate_tools,
            skill_events=self.skill_events,
            skill_sources=self.skill_sources,
            feedback_labels=self.feedback_labels,
            feedback_targets=self.feedback_targets,
            feedback_actions=self.feedback_actions,
            checker_targets=self.checker_targets,
            failure_targets=self.failure_targets,
            quality=self.quality,
        )


def command_lists(value: object) -> tuple[tuple[str, ...], ...]:
    """Return command argument lists from hook result objects."""
    if not isinstance(value, list):
        return ()
    commands: list[tuple[str, ...]] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            continue
        command = cast(dict[str, object], item).get("command")
        if not isinstance(command, list):
            continue
        args = tuple(arg for arg in cast(list[object], command) if isinstance(arg, str))
        if args:
            commands.append(args)
    return tuple(commands)


def command_targets(command: tuple[str, ...]) -> tuple[str, ...]:
    """Return likely file target arguments from a checker command."""
    targets: list[str] = []
    skip_next = False
    for token in command:
        if skip_next:
            skip_next = False
            continue
        if token in OPTION_VALUE_FLAGS:
            skip_next = True
            continue
        if is_code_checker_executable(token):
            continue
        if token.startswith("-"):
            continue
        if token.endswith(CHECKER_TARGET_SUFFIXES) and "/" in token:
            targets.append(token)
    return tuple(targets)


def is_code_checker_command(command: tuple[str, ...]) -> bool:
    """Return whether a command is a code-checker hook invocation."""
    return any(is_code_checker_executable(token) for token in command)


def is_code_checker_executable(token: str) -> bool:
    """Return whether a command token is the checker executable itself."""
    return (
        token.endswith("readability.py")
        or token.endswith("oop_readability_check.py")
        or token in ("pyright", "ruff")
        or token.endswith("/pyright")
        or token.endswith("/ruff")
    )


class HookEvidenceCounter:
    """Count hook statuses, tool results, skills, and checker surfaces."""

    def __init__(
        self,
        known_skills: frozenset[str] = frozenset(),
        root: Path | None = None,
    ) -> None:
        """Initialize empty counters."""
        self.state = HookCounterState.empty()
        self.known_skills = known_skills
        self.root = root
        self.skill_reset_epochs: dict[str, int] = {}

    def add_line(self, path: Path, raw_line: str) -> None:
        """Add one hook JSONL line to the counters."""
        if not raw_line.strip():
            return
        self.state.files[path.name] += 1
        entry = self.loaded_entry(raw_line)
        if entry is not None:
            self.add_entry(path, entry)

    def loaded_entry(self, raw_line: str) -> dict[str, object] | None:
        """Parse one hook JSON object, recording malformed evidence."""
        try:
            loaded: object = json.loads(raw_line)
        except json.JSONDecodeError:
            self.state.statuses["invalid_json"] += 1
            self.state.quality["invalid_json"] += 1
            return None
        if not isinstance(loaded, dict):
            self.state.statuses["invalid_entry"] += 1
            self.state.quality["invalid_entry"] += 1
            return None
        return cast(dict[str, object], loaded)

    def add_entry(self, path: Path, entry: dict[str, object]) -> None:
        """Add one parsed hook JSON object."""
        self.add_common_quality(entry)
        status = str(
            entry.get("status")
            or ("pass" if path.name == "skill_usage.jsonl" else "unknown")
        )
        self.state.statuses[status] += 1
        event = str(entry.get("event") or "missing_event")
        self.state.events[event] += 1
        if event in ("UnknownHookEvent", "missing_event"):
            self.state.quality["unknown_event"] += 1
        if entry.get("event_declared") is False:
            self.state.quality["missing_declared_event"] += 1
        if entry.get("payload_empty") is True:
            self.state.quality["empty_payload"] += 1
        payload_status = str(entry.get("payload_status") or "")
        if payload_status and payload_status != "valid":
            self.state.quality[f"payload_status:{payload_status}"] += 1
        fingerprint = str(entry.get("failure_fingerprint") or "")
        if status == "fail" and fingerprint:
            self.state.failures[fingerprint] += 1
        if status == "fail" and not fingerprint:
            self.state.quality["failed_entry_without_failure_fingerprint"] += 1
        tool_name = str(entry.get("tool_name") or "")
        if tool_name:
            self.state.tools[tool_name] += 1
        self.add_skill_usage(path, entry, event)
        self.add_checker_targets(entry)
        if status == "fail":
            self.add_failure_targets(entry)

    def add_common_quality(self, entry: dict[str, object]) -> None:
        """Record log fields needed for later self-correction."""
        if not str(entry.get("hook_run_id") or ""):
            self.state.quality["missing_hook_run_id"] += 1
        if not str(entry.get("payload_fingerprint") or ""):
            self.state.quality["missing_payload_fingerprint"] += 1
        namespace = str(entry.get("hook_log_namespace") or "")
        if namespace:
            self.state.namespaces[namespace] += 1
        else:
            self.state.quality["missing_hook_log_namespace"] += 1

    def add_skill_usage(self, path: Path, entry: dict[str, object], event: str) -> None:
        """Record skill usage entries and weak usage signals."""
        if path.name != "skill_usage.jsonl":
            return
        sources = self.normalized_strings(entry.get("skill_source_fields"))
        if sources:
            for source in sources:
                self.state.skill_sources[source] += 1
        else:
            self.state.quality["missing_skill_source_fields"] += 1
        if "observed_text_field_count" not in entry:
            self.state.quality["missing_observed_text_field_count"] += 1
        for skill in self.normalized_strings(entry.get("candidate_skills")):
            if not self.skill_signal_in_active_window(skill, entry):
                continue
            self.state.candidate_skills[skill] += 1
        for workflow in self.normalized_strings(entry.get("candidate_workflows")):
            self.state.candidate_workflows[workflow] += 1
        for tool in self.normalized_strings(entry.get("candidate_tools")):
            self.state.candidate_tools[tool] += 1
        for label in self.normalized_strings(entry.get("feedback_labels")):
            self.state.feedback_labels[label] += 1
        trusted_skill_source = self.trusted_skill_source(sources)
        for target in self.normalized_strings(entry.get("feedback_targets")):
            if self.countable_feedback_target(target, trusted_skill_source):
                if not self.feedback_target_in_active_window(target, entry):
                    continue
                self.state.feedback_targets[target] += 1
        action = str(entry.get("feedback_action") or "")
        if action:
            self.state.feedback_actions[action] += 1
        if entry.get("prompt_feedback_detected") is True and not self.normalized_strings(entry.get("feedback_labels")):
            self.state.quality["feedback_detected_without_labels"] += 1
        skills = tuple(
            skill
            for skill in self.normalized_strings(entry.get("skills"))
            if self.countable_skill(skill, trusted_skill_source)
        )
        candidate_seen = any(
            (
                self.normalized_strings(entry.get("candidate_skills")),
                self.normalized_strings(entry.get("candidate_workflows")),
                self.normalized_strings(entry.get("candidate_tools")),
                self.normalized_strings(entry.get("feedback_labels")),
            )
        )
        if not skills and not candidate_seen:
            self.state.quality["empty_skill_usage"] += 1
            return
        for skill in skills:
            if not self.skill_signal_in_active_window(skill, entry):
                continue
            self.state.skills[skill] += 1
            self.state.skill_events[f"{skill}@{event}"] += 1
        monitor_count = self.integer_value(entry.get("workflow_monitor_event_count"))
        if monitor_count <= 0:
            self.state.quality["skill_without_workflow_monitor_event"] += 1
        if not str(entry.get("workflow_monitor_report_dir") or ""):
            self.state.quality["missing_workflow_monitor_report_dir"] += 1

    def trusted_skill_source(self, sources: tuple[str, ...]) -> bool:
        """Return whether source fields are trusted for explicit skill ids."""
        return not sources or any(source in TRUSTED_SKILL_SOURCE_FIELDS for source in sources)

    def countable_feedback_target(self, target: str, trusted_skill_source: bool) -> bool:
        """Return whether a feedback target should be counted as actionable."""
        if target.startswith("skill:"):
            skill = target.removeprefix("skill:")
            if not trusted_skill_source:
                self.state.quality["tool_input_skill_feedback_target_ignored"] += 1
                return False
            if self.known_skills and skill not in self.known_skills:
                self.state.quality["noncanonical_skill_feedback_target_ignored"] += 1
                self.state.quality[f"noncanonical_skill_feedback_target_ignored:{skill}"] += 1
                return False
        return True

    def countable_skill(self, skill: str, trusted_skill_source: bool) -> bool:
        """Return whether a skill id should be counted as an actual skill use."""
        if not trusted_skill_source:
            self.state.quality["tool_input_skill_usage_ignored"] += 1
            self.state.quality[f"tool_input_skill_usage_ignored:{skill}"] += 1
            return False
        if self.known_skills and skill not in self.known_skills:
            self.state.quality["noncanonical_skill_usage_ignored"] += 1
            self.state.quality[f"noncanonical_skill_usage_ignored:{skill}"] += 1
            return False
        return True

    def feedback_target_in_active_window(
        self,
        target: str,
        entry: dict[str, object],
    ) -> bool:
        """Return whether a feedback target belongs to the current skill-analysis window."""
        if not target.startswith("skill:"):
            return True
        return self.skill_signal_in_active_window(target.removeprefix("skill:"), entry)

    def skill_signal_in_active_window(self, skill: str, entry: dict[str, object]) -> bool:
        """Return whether one skill signal is not archived by a source-path cutover."""
        reset_epoch = self.skill_reset_epoch(skill)
        entry_epoch = hook_entry_epoch(entry)
        if (
            reset_epoch == NO_RESET_EPOCH
            or entry_epoch == NO_RESET_EPOCH
            or entry_epoch >= reset_epoch
        ):
            return True
        self.state.quality["skill_routing_signal_before_cutover_ignored"] += 1
        self.state.quality[f"skill_routing_signal_before_cutover_ignored:{skill}"] += 1
        return False

    def skill_reset_epoch(self, skill: str) -> int:
        """Return the latest source-path commit epoch for one skill."""
        if skill in self.skill_reset_epochs:
            return self.skill_reset_epochs[skill]
        epoch = latest_skill_source_epoch(self.root, skill)
        self.skill_reset_epochs[skill] = epoch
        return epoch

    def add_checker_targets(self, entry: dict[str, object]) -> None:
        """Record files checked by code-checker hook commands."""
        for command in command_lists(entry.get("commands")):
            if not is_code_checker_command(command):
                continue
            for target in command_targets(command):
                self.state.checker_targets[target] += 1

    def add_failure_targets(self, entry: dict[str, object]) -> None:
        """Record files and weak evidence for failing hook commands."""
        raw_commands = entry.get("commands")
        if not isinstance(raw_commands, list):
            self.state.quality["failed_entry_without_commands"] += 1
            return
        saw_failed_command = False
        for raw_command in cast(list[object], raw_commands):
            if not isinstance(raw_command, dict):
                continue
            command_entry = cast(dict[str, object], raw_command)
            returncode = self.integer_value(command_entry.get("returncode"))
            if returncode == 0:
                continue
            saw_failed_command = True
            if not str(command_entry.get("output_snippet") or ""):
                self.state.quality["failed_command_without_output_snippet"] += 1
            command = command_entry.get("command")
            if not isinstance(command, list):
                continue
            args = tuple(arg for arg in cast(list[object], command) if isinstance(arg, str))
            for target in command_targets(args):
                self.state.failure_targets[target] += 1
        if not saw_failed_command:
            self.state.quality["failed_entry_without_failed_command"] += 1

    def counts(self) -> HookEvidenceCounts:
        """Return accumulated counters."""
        return self.state.to_counts()

    @staticmethod
    def normalized_strings(value: object) -> tuple[str, ...]:
        """Return non-empty strings from a JSON scalar or list."""
        if isinstance(value, str):
            return (value,) if value else ()
        if not isinstance(value, list):
            return ()
        items = cast(list[object], value)
        return tuple(item for item in items if isinstance(item, str) and item)

    @staticmethod
    def integer_value(value: object) -> int:
        """Return an integer JSON value, defaulting to zero."""
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        return 0


class AgentImprovementGuide:
    """Build a reader-facing improvement guide from local evidence files."""

    def __init__(self, root: Path) -> None:
        """Store the AgentCanon root."""
        self.requested_root = root.resolve()
        self.root = resolve_agentcanon_root(root)

    def collect(self) -> EvidenceSummary:
        """Collect all evidence families needed by the guide."""
        skill_eval_reports = self.skill_eval_report_paths()
        failed_skill_eval_reports = tuple(
            path for path in skill_eval_reports if self.skill_eval_failed(path)
        )
        return EvidenceSummary(
            open_issues=self.paths("issues/open/AC-*.md"),
            closed_issues=self.paths("issues/closed/AC-*.md"),
            memory_entries=self.memory_entry_counts(),
            skill_eval_reports=skill_eval_reports,
            failed_skill_eval_reports=failed_skill_eval_reports,
            hook_counts=self.hook_counts(),
        )

    def paths(self, pattern: str) -> tuple[Path, ...]:
        """Return sorted paths for one root-relative glob."""
        return tuple(sorted(self.root.glob(pattern)))

    def skill_eval_report_paths(self) -> tuple[Path, ...]:
        """Return skill prompt eval reports from the mounted archive."""
        reports = {
            path
            for result_dir in (
                *eval_result_search_dirs(self.root, "skill-workflow-prompt"),
                self.root / "agents" / "evals" / "results" / "skill-workflow-prompt",
            )
            if result_dir.is_dir()
            for path in result_dir.glob("*.md")
            if path.name != "README.md"
        }
        legacy_dir = self.root / "agents" / "evals" / "results" / "skill-workflow-prompt"
        if legacy_dir.is_dir():
            reports.update(
                path for path in legacy_dir.glob("*.md") if path.name != "README.md"
            )
        return tuple(sorted(reports))

    def memory_entry_counts(self) -> dict[str, int]:
        """Return bullet-entry counts for shared memory notes."""
        counts: dict[str, int] = {}
        for relative in ("memory/USER_PREFERENCES.md", "memory/AGENT_PHILOSOPHY.md"):
            path = self.root / relative
            if not path.is_file():
                counts[relative] = 0
                continue
            counts[relative] = sum(
                1
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("- ") and "まだなし" not in line
            )
        return counts

    def skill_eval_failed(self, path: Path) -> bool:
        """Return whether one accumulated skill eval report is failing."""
        name = path.relative_to(self.root).name if path.is_relative_to(self.root) else path.name
        if "-fail-" in name:
            return True
        text = path.read_text(encoding="utf-8")
        return "EVAL_STATUS=fail" in text or "status: `fail`" in text

    def hook_counts(self) -> HookEvidenceCounts:
        """Return hook counters."""
        counter = HookEvidenceCounter(known_skill_ids(self.root), root=self.root)
        for path in self.hook_result_paths():
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                counter.add_line(path, raw_line)
        return counter.counts()

    def hook_result_paths(self) -> tuple[Path, ...]:
        """Return direct and runtime-sharded hook result JSONL paths."""
        paths: list[Path] = []
        hook_dirs = [
            *hook_result_search_dirs(self.requested_root, self.root),
            self.root / "agents" / "evals" / "results" / "hook-runs",
        ]
        for hook_dir in hook_dirs:
            direct = tuple(sorted(hook_dir.glob("*.jsonl"))) if hook_dir.is_dir() else ()
            sharded = tuple(sorted(hook_dir.glob("**/*.jsonl"))) if hook_dir.is_dir() else ()
            paths.extend(direct + sharded)
        return tuple(sorted(set(paths)))

    def render(self, summary: EvidenceSummary) -> str:
        """Render the improvement guide as Markdown."""
        lines = [
            "# Agent Improvement Guide",
            "",
            "<!--",
            "@dependency-start",
            "responsibility Records generated AgentCanon improvement guidance.",
            "upstream implementation tools/agent_tools/generate_agent_improvement_guide.py generates this report",
            "@dependency-end",
            "-->",
            "",
            "This generated guide is read-only evidence. Use it to choose a local",
            "Codex repair branch; do not let the workflow rewrite",
            "skills, workflows, tools, or memory directly.",
            "",
            "## Evidence Summary",
            "",
            *evidence_summary_lines(self.root, summary),
            "",
            *render_guidance_sections(self.root, summary),
        ]
        return "\n".join(lines)


def evidence_summary_lines(root: Path, summary: EvidenceSummary) -> list[str]:
    """Return machine-readable guide summary bullets."""
    counts = summary.hook_counts
    return [
        f"- evidence_root: `{root.as_posix()}`",
        f"- open_issues: `{len(summary.open_issues)}`",
        f"- closed_issues: `{len(summary.closed_issues)}`",
        f"- memory_entries: `{sum(summary.memory_entries.values())}`",
        f"- skill_eval_reports: `{len(summary.skill_eval_reports)}`",
        f"- failed_skill_eval_reports: `{len(summary.failed_skill_eval_reports)}`",
        f"- hook_status_counts: `{dict(counts.statuses)}`",
        f"- hook_file_counts: `{dict(counts.files)}`",
        f"- hook_event_counts: `{dict(counts.events)}`",
        f"- hook_namespace_counts: `{dict(counts.namespaces)}`",
        f"- hook_tool_counts: `{dict(counts.tools)}`",
        f"- skill_usage_counts: `{dict(counts.skills)}`",
        f"- prompt_candidate_skill_counts: `{dict(counts.candidate_skills)}`",
        f"- prompt_candidate_workflow_counts: `{dict(counts.candidate_workflows)}`",
        f"- prompt_candidate_tool_counts: `{dict(counts.candidate_tools)}`",
        f"- skill_source_counts: `{dict(counts.skill_sources)}`",
        f"- human_feedback_label_counts: `{dict(counts.feedback_labels)}`",
        f"- human_feedback_target_counts: `{dict(counts.feedback_targets)}`",
        f"- human_feedback_action_counts: `{dict(counts.feedback_actions)}`",
        f"- hook_failure_target_counts: `{dict(counts.failure_targets)}`",
        f"- hook_quality_counts: `{dict(counts.quality)}`",
    ]


def render_guidance_sections(root: Path, summary: EvidenceSummary) -> list[str]:
    """Return all detailed guide sections after the summary."""
    sections: list[str] = []
    sections.extend(named_section("Improvement Guidance", guidance(summary)))
    sections.extend(named_section("Skill Routing Gaps", skill_routing_gap_lines(summary.hook_counts)))
    sections.extend(named_section("Skill Usage Evidence", counter_lines(summary.hook_counts.skills)))
    sections.extend(named_section("Prompt Candidate Skills", counter_lines(summary.hook_counts.candidate_skills)))
    sections.extend(named_section("Prompt Candidate Workflows", counter_lines(summary.hook_counts.candidate_workflows)))
    sections.extend(named_section("Prompt Candidate Tools", counter_lines(summary.hook_counts.candidate_tools)))
    sections.extend(named_section("Skill Event Coverage", counter_lines(summary.hook_counts.skill_events)))
    sections.extend(named_section("Skill Source Fields", counter_lines(summary.hook_counts.skill_sources)))
    sections.extend(named_section("Human Feedback Labels", counter_lines(summary.hook_counts.feedback_labels)))
    sections.extend(named_section("Human Feedback Targets", counter_lines(summary.hook_counts.feedback_targets)))
    sections.extend(named_section("Human Feedback Actions", counter_lines(summary.hook_counts.feedback_actions)))
    sections.extend(named_section("Hook Runtime Namespaces", counter_lines(summary.hook_counts.namespaces)))
    sections.extend(named_section("Hook Tool Evidence", counter_lines(summary.hook_counts.tools)))
    sections.extend(named_section("Code Checker Targets", counter_lines(summary.hook_counts.checker_targets)))
    sections.extend(named_section("Top Failure Repair Targets", counter_lines(summary.hook_counts.failure_targets)))
    sections.extend(named_section("Hook Quality Findings", counter_lines(summary.hook_counts.quality)))
    sections.extend(named_section("Protocol Feedback Coverage", protocol_feedback_lines(summary)))
    sections.extend(named_section("Open Issues", path_lines(root, summary.open_issues)))
    sections.extend(
        named_section(
            "Failed Skill Eval Reports",
            path_lines(root, summary.failed_skill_eval_reports),
        )
    )
    sections.extend(named_section("Repeated Hook Failures", failure_lines(summary.hook_counts.failures)))
    sections.extend(named_section("Memory Entry Counts", memory_entry_lines(summary)))
    return sections


def named_section(name: str, lines: list[str]) -> list[str]:
    """Return one Markdown section."""
    return [f"## {name}", "", *lines, ""]


def memory_entry_lines(summary: EvidenceSummary) -> list[str]:
    """Return memory count bullets."""
    return [
        f"- `{path}`: `{count}`"
        for path, count in sorted(summary.memory_entries.items())
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="AgentCanon root. Default: current directory.")
    parser.add_argument(
        "--out",
        default="reports/agent-improvement-guide/agent-improvement-guide.md",
        help="Markdown output path.",
    )
    return parser


def resolve_agentcanon_root(root: Path) -> Path:
    """Resolve a parent/template root to its vendored AgentCanon evidence root."""
    resolved = root.resolve()
    vendored = resolved / "vendor" / "agent-canon"
    if is_agentcanon_root(vendored):
        return vendored.resolve()
    if is_agentcanon_root(resolved):
        return resolved
    return resolved


def is_agentcanon_root(root: Path) -> bool:
    """Return whether a path looks like the AgentCanon evidence root."""
    return (
        (root / "agents" / "evals" / "README.md").is_file()
        or (root / ".agents" / "skills").is_dir()
        or (root / "tools" / "agent_tools" / "generate_agent_improvement_guide.py").is_file()
        or (root / "agents" / "evals" / "results").is_dir()
        or (root / ".agents" / "skills").is_dir()
    )


def known_skill_ids(root: Path) -> frozenset[str]:
    """Return AgentCanon-owned skill ids from shim and human docs."""
    skills: set[str] = set()
    for path in (root / ".agents" / "skills").glob("*/SKILL.md"):
        skills.add(path.parent.name)
    for path in (root / "agents" / "skills").glob("*.md"):
        if path.name != "README.md":
            skills.add(path.stem)
    return frozenset(skills)


def hook_entry_epoch(entry: dict[str, object]) -> int:
    """Return UTC epoch seconds parsed from one hook timestamp."""
    timestamp = entry.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        return NO_RESET_EPOCH
    normalized = timestamp.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return NO_RESET_EPOCH
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def latest_skill_source_epoch(root: Path | None, skill: str) -> int:
    """Return latest Git commit epoch for source paths that define one skill."""
    if root is None:
        return NO_RESET_EPOCH
    paths = [
        path.as_posix()
        for path in skill_source_path_candidates(skill)
        if (root / path).exists()
    ]
    if not paths:
        return NO_RESET_EPOCH
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                root.as_posix(),
                "log",
                "-1",
                f"--format={COMMIT_TIME_FORMAT}",
                "--",
                *paths,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_LOG_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return NO_RESET_EPOCH
    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return NO_RESET_EPOCH
    try:
        return int(output.splitlines()[0])
    except ValueError:
        return NO_RESET_EPOCH


def skill_source_path_candidates(skill: str) -> tuple[Path, ...]:
    """Return likely source paths that define one skill id."""
    slug = skill.removeprefix("$")
    return (
        Path(".agents") / "skills" / slug / "SKILL.md",
        Path("agents") / "skills" / f"{slug}.md",
    )


def guidance(summary: EvidenceSummary) -> list[str]:
    """Return actionable guidance lines."""
    lines: list[str] = []
    if summary.open_issues:
        lines.append("- Prioritize open `issues/open/` findings before adding new workflow scope.")
    if summary.failed_skill_eval_reports:
        lines.append("- Repair skill or workflow prompt surfaces, then rerun accumulated prompt evals.")
    if summary.hook_counts.failures:
        lines.append(
            "- Group hook failures by `failure_fingerprint` and fix the highest-repeat tool or OOP boundary first."
        )
    if summary.hook_counts.failure_targets:
        lines.append(
            "- Start concrete repairs from `Top Failure Repair Targets`; those are the files currently blocking hook/tool runs."
        )
    if summary.hook_counts.checker_targets:
        lines.append(
            "- Review repeated code-checker target files and decide whether the tool, skill, or target code owns the repair."
        )
    if skill_routing_gap_lines(summary.hook_counts) != ["- none"]:
        lines.append(
            "- Repair skill-selection routing for skills with high candidate or feedback pressure but low selected-skill evidence."
        )
    if summary.hook_counts.quality:
        lines.append(
            "- Treat hook quality counters as instrumentation debt; repair unknown events, empty skill signals, or missing workflow monitor events."
        )
    if not lines:
        lines.append("- No immediate memory/eval/hook/issue improvement target was detected.")
    lines.append(
        "- Local Codex should make the actual skill/workflow/tool edits and attach validation evidence."
    )
    return lines


def path_lines(root: Path, paths: tuple[Path, ...]) -> list[str]:
    """Return Markdown bullets for repo-relative paths."""
    if not paths:
        return ["- none"]
    return [f"- `{path.relative_to(root).as_posix()}`" for path in paths]


def failure_lines(failures: Counter[str]) -> list[str]:
    """Return Markdown bullets for repeated hook failures."""
    if not failures:
        return ["- none"]
    return [
        f"- `{fingerprint}`: `{count}`"
        for fingerprint, count in failures.most_common(MAX_HOOK_FAILURE_LINES)
    ]


def counter_lines(counter: Counter[str]) -> list[str]:
    """Return Markdown bullets for a counter."""
    if not counter:
        return ["- none"]
    return [
        f"- `{name}`: `{count}`"
        for name, count in counter.most_common(MAX_COUNTER_LINES)
    ]


def skill_feedback_counts(feedback_targets: Counter[str]) -> Counter[str]:
    """Return feedback target counts keyed by skill id."""
    counts: Counter[str] = Counter()
    for target, count in feedback_targets.items():
        if target.startswith("skill:"):
            counts[target.removeprefix("skill:")] += count
    return counts


def skill_routing_gap_lines(counts: HookEvidenceCounts) -> list[str]:
    """Return bullets for skills whose candidate/feedback pressure exceeds selection."""
    feedback = skill_feedback_counts(counts.feedback_targets)
    rows: list[tuple[int, str, int, int, int]] = []
    for skill in set(counts.candidate_skills) | set(feedback) | set(counts.skills):
        selected = counts.skills[skill]
        candidate = counts.candidate_skills[skill]
        feedback_count = feedback[skill]
        pressure = candidate + feedback_count
        gap = max(pressure - selected, 0)
        if gap:
            rows.append((gap, skill, selected, candidate, feedback_count))
    if not rows:
        return ["- none"]
    return [
        (
            f"- `{skill}`: gap=`{gap}` selected=`{selected}` "
            f"candidate=`{candidate}` feedback=`{feedback_count}`"
        )
        for gap, skill, selected, candidate, feedback_count in sorted(rows, reverse=True)[
            :MAX_COUNTER_LINES
        ]
    ]


def protocol_feedback_lines(summary: EvidenceSummary) -> list[str]:
    """Return required protocol-feedback guidance from accumulated evidence."""
    lines = [
        "- required_tokens: `hook_tool_feedback=reviewed`, `parent_protocol_update=<applied|recorded|not_required>`, `subagent_protocol_update=<applied|recorded|not_required>`, `protocol_feedback_reason=...`",
    ]
    if (
        summary.hook_counts.failures
        or summary.hook_counts.quality
        or summary.failed_skill_eval_reports
    ):
        lines.append(
            "- next_repair_branch: record the parent/subagent protocol decision in `workflow_monitoring.md` with `tools/agent_tools/workflow_monitor.py`."
        )
    else:
        lines.append("- current_evidence: no failing hook, hook-quality, or skill-eval signal requires protocol repair.")
    return lines


def main() -> int:
    """Generate an improvement guide."""
    args = build_parser().parse_args()
    root = Path(args.root)
    output = Path(args.out)
    guide = AgentImprovementGuide(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(guide.render(guide.collect()), encoding="utf-8")
    print(f"AGENT_IMPROVEMENT_GUIDE={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
