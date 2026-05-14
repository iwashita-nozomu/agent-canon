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

MAX_HOOK_FAILURE_LINES = 20


@dataclass(frozen=True)
class EvidenceSummary:
    """Summarized AgentCanon improvement evidence."""

    open_issues: tuple[Path, ...]
    closed_issues: tuple[Path, ...]
    memory_entries: dict[str, int]
    skill_eval_reports: tuple[Path, ...]
    failed_skill_eval_reports: tuple[Path, ...]
    hook_status_counts: Counter[str]
    hook_failure_counts: Counter[str]


class HookEvidenceCounter:
    """Count hook statuses and repeated failure fingerprints."""

    def __init__(self) -> None:
        """Initialize empty counters."""
        self.statuses: Counter[str] = Counter()
        self.failures: Counter[str] = Counter()

    def add_line(self, path: Path, raw_line: str) -> None:
        """Add one hook JSONL line to the counters."""
        if not raw_line.strip():
            return
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            self.statuses["invalid_json"] += 1
            return
        if not isinstance(entry, dict):
            self.statuses["invalid_entry"] += 1
            return
        status = str(
            entry.get("status")
            or ("pass" if path.name == "skill_usage.jsonl" else "unknown")
        )
        self.statuses[status] += 1
        fingerprint = str(entry.get("failure_fingerprint") or "")
        if status == "fail" and fingerprint:
            self.failures[fingerprint] += 1

    def counts(self) -> tuple[Counter[str], Counter[str]]:
        """Return accumulated counters."""
        return self.statuses, self.failures


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
        hook_status_counts, hook_failure_counts = self.hook_counts()
        return EvidenceSummary(
            open_issues=self.paths("issues/open/AC-*.md"),
            closed_issues=self.paths("issues/closed/AC-*.md"),
            memory_entries=self.memory_entry_counts(),
            skill_eval_reports=skill_eval_reports,
            failed_skill_eval_reports=failed_skill_eval_reports,
            hook_status_counts=hook_status_counts,
            hook_failure_counts=hook_failure_counts,
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

    def hook_counts(self) -> tuple[Counter[str], Counter[str]]:
        """Return hook status and repeated-failure counters."""
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
            f"- hook_status_counts: `{dict(summary.hook_status_counts)}`",
            "",
            "## Improvement Guidance",
            "",
            *guidance(summary),
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
            *failure_lines(summary.hook_failure_counts),
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
    if summary.hook_failure_counts:
        lines.append(
            "- Group hook failures by `failure_fingerprint` and fix the highest-repeat tool or OOP boundary first."
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
