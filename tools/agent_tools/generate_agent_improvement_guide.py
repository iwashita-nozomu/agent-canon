#!/usr/bin/env python3
# @dependency-start
# responsibility Generates PR and push-time guidance from AgentCanon memory, eval, hook, and issue evidence.
# upstream design ../../agents/evals/README.md eval evidence contract
# upstream design ../../agents/evals/results/hook-runs/README.md hook result accumulation contract
# upstream design ../../issues/README.md durable operational issue storage
# downstream implementation ../../.github/workflows/agent-improvement-guide.yml runs this on PR and push
# downstream implementation ../../tests/agent_tools/test_generate_agent_improvement_guide.py tests guide generation
# @dependency-end
"""Generate a deterministic AgentCanon improvement guide."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

MAX_HOOK_FAILURE_LINES = 20
MAX_COUNTER_LINES = 20
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


@dataclass(frozen=True)
class HookEvidenceCounts:
    """Summarized hook-run counters."""

    statuses: Counter[str]
    failures: Counter[str]
    files: Counter[str]
    events: Counter[str]
    tools: Counter[str]
    skills: Counter[str]
    skill_events: Counter[str]
    checker_targets: Counter[str]
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


class HookEvidenceCounter:
    """Count hook statuses, tool results, skills, and checker surfaces."""

    def __init__(self) -> None:
        """Initialize empty counters."""
        self.statuses: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()
        self.files: Counter[str] = Counter()
        self.events: Counter[str] = Counter()
        self.tools: Counter[str] = Counter()
        self.skills: Counter[str] = Counter()
        self.skill_events: Counter[str] = Counter()
        self.checker_targets: Counter[str] = Counter()
        self.quality: Counter[str] = Counter()

    def add_line(self, path: Path, raw_line: str) -> None:
        """Add one hook JSONL line to the counters."""
        if not raw_line.strip():
            return
        self.files[path.name] += 1
        try:
            loaded: object = json.loads(raw_line)
        except json.JSONDecodeError:
            self.statuses["invalid_json"] += 1
            self.quality["invalid_json"] += 1
            return
        if not isinstance(loaded, dict):
            self.statuses["invalid_entry"] += 1
            self.quality["invalid_entry"] += 1
            return
        entry = cast(dict[str, object], loaded)
        status = str(
            entry.get("status")
            or ("pass" if path.name == "skill_usage.jsonl" else "unknown")
        )
        self.statuses[status] += 1
        event = str(entry.get("event") or "missing_event")
        self.events[event] += 1
        if event in ("UnknownHookEvent", "missing_event"):
            self.quality["unknown_event"] += 1
        if entry.get("event_fallback") is True:
            self.quality["event_fallback"] += 1
        if entry.get("payload_fallback") is True:
            self.quality["payload_fallback"] += 1
        payload_status = str(entry.get("payload_status") or "")
        if payload_status and payload_status != "valid":
            self.quality[f"payload_status:{payload_status}"] += 1
        fingerprint = str(entry.get("failure_fingerprint") or "")
        if status == "fail" and fingerprint:
            self.failures[fingerprint] += 1
        tool_name = str(entry.get("tool_name") or "")
        if tool_name:
            self.tools[tool_name] += 1
        self.add_skill_usage(path, entry, event)
        self.add_checker_targets(entry)

    def add_skill_usage(self, path: Path, entry: dict[str, object], event: str) -> None:
        """Record skill usage entries and weak usage signals."""
        if path.name != "skill_usage.jsonl":
            return
        skills = self.normalized_strings(entry.get("skills"))
        if not skills:
            self.quality["empty_skill_usage"] += 1
            return
        for skill in skills:
            self.skills[skill] += 1
            self.skill_events[f"{skill}@{event}"] += 1
        monitor_count = self.integer_value(entry.get("workflow_monitor_event_count"))
        if monitor_count <= 0:
            self.quality["skill_without_workflow_monitor_event"] += 1

    def add_checker_targets(self, entry: dict[str, object]) -> None:
        """Record files checked by code-checker hook commands."""
        for command in self.command_lists(entry.get("commands")):
            if not self.is_code_checker_command(command):
                continue
            for target in self.command_targets(command):
                self.checker_targets[target] += 1

    def counts(self) -> HookEvidenceCounts:
        """Return accumulated counters."""
        return HookEvidenceCounts(
            statuses=self.statuses,
            failures=self.failures,
            files=self.files,
            events=self.events,
            tools=self.tools,
            skills=self.skills,
            skill_events=self.skill_events,
            checker_targets=self.checker_targets,
            quality=self.quality,
        )

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

    @staticmethod
    def command_lists(value: object) -> tuple[tuple[str, ...], ...]:
        """Return command argument lists from hook result objects."""
        if not isinstance(value, list):
            return ()
        items = cast(list[object], value)
        commands: list[tuple[str, ...]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            command = cast(dict[str, object], item).get("command")
            if not isinstance(command, list):
                continue
            args = tuple(arg for arg in cast(list[object], command) if isinstance(arg, str))
            if args:
                commands.append(args)
        return tuple(commands)

    @staticmethod
    def is_code_checker_command(command: tuple[str, ...]) -> bool:
        """Return whether a command is a code-checker hook invocation."""
        return any(HookEvidenceCounter.is_code_checker_executable(token) for token in command)

    @staticmethod
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
            if HookEvidenceCounter.is_code_checker_executable(token):
                continue
            if token.startswith("-"):
                continue
            if token.endswith(CHECKER_TARGET_SUFFIXES) and "/" in token:
                targets.append(token)
        return tuple(targets)

    @staticmethod
    def is_code_checker_executable(token: str) -> bool:
        """Return whether a command token is the checker executable itself."""
        return (
            token.endswith("readability.py")
            or token.endswith("oop_readability_check.py")
            or token in ("pyright", "ruff")
            or token.endswith("/pyright")
            or token.endswith("/ruff")
        )


class AgentImprovementGuide:
    """Build a reader-facing improvement guide from local evidence files."""

    def __init__(self, root: Path) -> None:
        """Store the AgentCanon root."""
        self.root = root.resolve()

    def collect(self) -> EvidenceSummary:
        """Collect all evidence families needed by the guide."""
        skill_eval_reports = self.paths("agents/evals/results/skill-workflow-prompt/*.md")
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
        counter = HookEvidenceCounter()
        for path in self.paths("agents/evals/results/hook-runs/*.jsonl"):
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                counter.add_line(path, raw_line)
        return counter.counts()

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
            "Agent or Copilot PR repair branch; do not let the workflow rewrite",
            "skills, workflows, tools, or memory directly.",
            "",
            "## Evidence Summary",
            "",
            f"- open_issues: `{len(summary.open_issues)}`",
            f"- closed_issues: `{len(summary.closed_issues)}`",
            f"- memory_entries: `{sum(summary.memory_entries.values())}`",
            f"- skill_eval_reports: `{len(summary.skill_eval_reports)}`",
            f"- failed_skill_eval_reports: `{len(summary.failed_skill_eval_reports)}`",
            f"- hook_status_counts: `{dict(summary.hook_counts.statuses)}`",
            f"- hook_file_counts: `{dict(summary.hook_counts.files)}`",
            f"- hook_event_counts: `{dict(summary.hook_counts.events)}`",
            f"- hook_tool_counts: `{dict(summary.hook_counts.tools)}`",
            f"- skill_usage_counts: `{dict(summary.hook_counts.skills)}`",
            f"- hook_quality_counts: `{dict(summary.hook_counts.quality)}`",
            "",
            "## Improvement Guidance",
            "",
            *guidance(summary),
            "",
            "## Skill Usage Evidence",
            "",
            *counter_lines(summary.hook_counts.skills),
            "",
            "## Skill Event Coverage",
            "",
            *counter_lines(summary.hook_counts.skill_events),
            "",
            "## Hook Tool Evidence",
            "",
            *counter_lines(summary.hook_counts.tools),
            "",
            "## Code Checker Targets",
            "",
            *counter_lines(summary.hook_counts.checker_targets),
            "",
            "## Protocol Feedback Coverage",
            "",
            *protocol_feedback_lines(summary),
            "",
            "## Open Issues",
            "",
            *path_lines(self.root, summary.open_issues),
            "",
            "## Failed Skill Eval Reports",
            "",
            *path_lines(self.root, summary.failed_skill_eval_reports),
            "",
            "## Repeated Hook Failures",
            "",
            *failure_lines(summary.hook_counts.failures),
            "",
            "## Memory Entry Counts",
            "",
            *[
                f"- `{path}`: `{count}`"
                for path, count in sorted(summary.memory_entries.items())
            ],
            "",
        ]
        return "\n".join(lines)


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
    if summary.hook_counts.checker_targets:
        lines.append(
            "- Review repeated code-checker target files and decide whether the tool, skill, or target code owns the repair."
        )
    if summary.hook_counts.quality:
        lines.append(
            "- Treat hook quality counters as instrumentation debt; repair unknown events, empty skill signals, or missing workflow monitor events."
        )
    if not lines:
        lines.append("- No immediate memory/eval/hook/issue improvement target was detected.")
    lines.append(
        "- Local Agent or Copilot PR should make the actual skill/workflow/tool edits and attach validation evidence."
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
