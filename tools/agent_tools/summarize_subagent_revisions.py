#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Summarizes subagent revision evidence from generated run-bundle artifacts.
# upstream design ../../agents/skills/agent-log-analysis.md requires compact summaries before log analysis
# upstream design ../../agents/skills/result-artifact-writeout.md defines raw and summary artifact writeout
# upstream implementation ./generate_agent_runtime_dashboard.py generates compact runtime summaries
# downstream implementation ../../tools/README.md documents run-local summary output
# @dependency-end
"""Summarize subagent revise/rework evidence without reading raw JSONL logs."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "subagent_revision_summary.v1"
DEFAULT_MAX_EVIDENCE_ROWS = 30
SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60

TIMESTAMP_RE = re.compile(
    r"\b(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z)\b"
)
WORK_LOG_RE = re.compile(
    r"^-\s+(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z)\s+\|\s+"
    r"(?P<kind>[^|]+)\|\s+(?P<clauses>[^|]+)\|\s+"
    r"(?P<message>.*?)(?:\s+\|\s+Next:\s+(?P<next>.*))?$"
)
BACKTICK_ROLE_RE = re.compile(r"`(?P<role>[a-z][a-z0-9_-]{0,79})`")

SUBAGENT_TERMS = (
    "subagent",
    "worker",
    "spark_worker",
    "python_reviewer",
    "reviewer",
    "test_designer",
    "explorer",
)
REVISION_TERMS = (
    "revise",
    "revision",
    "rework",
    "rerun",
    "fix",
    "fixed",
    "repair",
    "updated",
    "stale",
    "regression",
    "introduced",
    "inlined",
    "parent",
    "failed",
    "failure",
)
TOOL_TERMS = (
    "tool",
    "finding",
    "oop",
    "helper",
    "config_defaults",
    "structure_hash",
    "validation",
)
ROLE_NAMES = {
    "worker",
    "spark_worker",
    "python_reviewer",
    "reviewer",
    "test_designer",
    "explorer",
    "manager_reviewer",
    "plan_reviewer",
    "detailed_design_reviewer",
    "document_flow_reviewer",
    "requirements_organizer",
    "execution_planner",
}


@dataclass(frozen=True)
class WorkEntry:
    """One parsed work-log style entry."""

    timestamp: str | None
    kind: str
    message: str
    source: str


@dataclass(frozen=True)
class Evidence:
    """One classified evidence line."""

    timestamp: str | None
    kind: str
    category: str
    source: str
    message: str


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Summarize subagent revise/rework evidence from generated run-bundle "
            "Markdown/YAML artifacts without reading raw JSONL logs."
        )
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="Run bundle directory. Defaults to newest reports/agents/* directory.",
    )
    parser.add_argument(
        "--reports-root",
        type=Path,
        default=Path("reports/agents"),
        help="Reports root used when --run-dir is omitted.",
    )
    parser.add_argument(
        "--dashboard-compact",
        type=Path,
        default=Path("reports/agent-runtime-dashboard/agent-runtime-compact.md"),
        help="Generated compact runtime dashboard path.",
    )
    parser.add_argument("--out-json", type=Path, help="Optional JSON output path.")
    parser.add_argument("--out-md", type=Path, help="Optional Markdown output path.")
    parser.add_argument(
        "--max-evidence",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_ROWS,
        help="Maximum evidence rows per Markdown section.",
    )
    return parser


def newest_run_dir(reports_root: Path) -> Path:
    """Return the newest run directory by modification time."""
    candidates = [path for path in reports_root.iterdir() if path.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"no run directories found under {reports_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_text_artifact(path: Path) -> str:
    """Read one generated text artifact, rejecting raw log inputs."""
    if path.suffix == ".jsonl":
        raise ValueError(f"raw JSONL input is not allowed: {path}")
    return path.read_text(encoding="utf-8")


def source_paths(run_dir: Path, dashboard_compact: Path) -> list[Path]:
    """Return generated text artifacts used for this summary."""
    paths = sorted(run_dir.glob("*.md"))
    paths.extend(sorted(run_dir.glob("*.yaml")))
    paths.extend(sorted(run_dir.glob("*.yml")))
    paths = [
        path
        for path in paths
        if not path.name.startswith("subagent_revision_summary")
    ]
    if dashboard_compact.is_file():
        paths.append(dashboard_compact)
    return [path for path in paths if path.is_file()]


def parse_entries(paths: Iterable[Path]) -> list[WorkEntry]:
    """Parse generated artifact lines into searchable evidence entries."""
    entries: list[WorkEntry] = []
    for path in paths:
        text = read_text_artifact(path)
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = WORK_LOG_RE.match(line)
            if match:
                message = match.group("message").strip()
                next_text = match.group("next")
                if next_text:
                    message = f"{message} | Next: {next_text.strip()}"
                entries.append(
                    WorkEntry(
                        timestamp=match.group("ts"),
                        kind=match.group("kind").strip(),
                        message=message,
                        source=str(path),
                    )
                )
                continue
            ts_match = TIMESTAMP_RE.search(line)
            if ts_match:
                entries.append(
                    WorkEntry(
                        timestamp=ts_match.group("ts"),
                        kind="timestamped-text",
                        message=line,
                        source=str(path),
                    )
                )
                continue
            if is_evidence_line(line):
                entries.append(
                    WorkEntry(
                        timestamp=None,
                        kind=path.stem,
                        message=line,
                        source=str(path),
                    )
                )
    return entries


def is_evidence_line(line: str) -> bool:
    """Return whether a generated text line can carry runtime evidence."""
    if line.startswith(("<!--", "@dependency-", "#")):
        return False
    if lowered_contains(line, SUBAGENT_TERMS):
        return True
    if lowered_contains(line, REVISION_TERMS):
        return True
    if lowered_contains(line, TOOL_TERMS):
        return True
    return line.startswith(("- ", "* ", "| `", "| `AGENT_RUNTIME_DASHBOARD_"))


def lowered_contains(text: str, terms: Iterable[str]) -> bool:
    """Return whether text contains any term case-insensitively."""
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def classify_entries(entries: Iterable[WorkEntry]) -> list[Evidence]:
    """Classify entries into revise/rework evidence categories."""
    evidence: list[Evidence] = []
    for entry in entries:
        combined = f"{entry.kind} {entry.message}"
        has_subagent = lowered_contains(combined, SUBAGENT_TERMS)
        has_revision = lowered_contains(combined, REVISION_TERMS)
        has_tool = lowered_contains(combined, TOOL_TERMS)
        category: str | None = None
        if has_direct_subagent_revision(combined):
            category = "direct_subagent_output_revision"
        elif has_revision:
            category = "broader_parent_or_validation_rework"
        elif has_subagent:
            category = "subagent_activity"
        elif has_tool:
            category = "tool_or_validation_loop"
        if category:
            evidence.append(
                Evidence(
                    timestamp=entry.timestamp,
                    kind=entry.kind,
                    category=category,
                    source=entry.source,
                    message=entry.message,
                )
            )
    return evidence


def has_direct_subagent_revision(text: str) -> bool:
    """Return whether text explicitly records revision of subagent output."""
    lowered = text.lower()
    explicit_markers = (
        "worker first",
        "subagent output",
        "agent output",
        "spark_worker output",
        "worker output",
    )
    if any(marker in lowered for marker in explicit_markers):
        return True
    has_subagent = lowered_contains(lowered, SUBAGENT_TERMS)
    if not has_subagent:
        return False
    parent_repaired = "parent" in lowered and lowered_contains(
        lowered,
        ("fixed", "repaired", "revised", "inlined", "updated", "rerun"),
    )
    introduced_regression = "introduced" in lowered and lowered_contains(
        lowered,
        ("finding", "warning", "regression", "failure"),
    )
    return parent_repaired or introduced_regression


def parse_roles(paths: Iterable[Path]) -> Counter[str]:
    """Count explicit role mentions from generated text artifacts."""
    counts: Counter[str] = Counter()
    for path in paths:
        text = read_text_artifact(path)
        for match in BACKTICK_ROLE_RE.finditer(text):
            role = match.group("role")
            if role in ROLE_NAMES or role.endswith("_reviewer"):
                counts[role] += 1
        lowered = text.lower()
        for role in ROLE_NAMES:
            plain_count = lowered.count(role.lower())
            if plain_count:
                counts[role] += plain_count
    return counts


def parse_dashboard_metrics(dashboard_compact: Path) -> dict[str, str]:
    """Parse machine-summary KEY=VALUE lines from the compact dashboard."""
    if not dashboard_compact.is_file():
        return {}
    metrics: dict[str, str] = {}
    for raw_line in read_text_artifact(dashboard_compact).splitlines():
        line = raw_line.strip()
        if not line.startswith("AGENT_RUNTIME_DASHBOARD_") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        metrics[key] = value
    return metrics


def parse_time_span(entries: Iterable[WorkEntry]) -> dict[str, str | int | None]:
    """Return first/last timestamp and elapsed seconds."""
    timestamps: list[datetime] = []
    for entry in entries:
        if entry.timestamp is None:
            continue
        timestamps.append(parse_timestamp(entry.timestamp))
    if not timestamps:
        return {"first": None, "last": None, "elapsed_seconds": None}
    first = min(timestamps)
    last = max(timestamps)
    return {
        "first": first.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last": last.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_seconds": int((last - first).total_seconds()),
    }


def parse_timestamp(value: str) -> datetime:
    """Parse a compact UTC timestamp with optional seconds."""
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$", value):
        return datetime.strptime(value, "%Y-%m-%dT%H:%MZ")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def artifact_time_span(paths: Iterable[Path]) -> dict[str, str | int | None]:
    """Return first/last artifact modification time as generated evidence."""
    timestamps: list[datetime] = []
    for path in paths:
        if not path.exists():
            continue
        timestamps.append(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))
    if not timestamps:
        return {"first": None, "last": None, "elapsed_seconds": None}
    first = min(timestamps)
    last = max(timestamps)
    return {
        "first": first.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last": last.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_seconds": int((last - first).total_seconds()),
    }


def tool_artifact_counts(run_dir: Path) -> dict[str, int]:
    """Count generated tool artifacts by family without opening raw result files."""
    tool_dir = run_dir / "tool"
    if not tool_dir.is_dir():
        return {}
    files = [path for path in tool_dir.iterdir() if path.is_file()]
    names = [path.name for path in files]
    return {
        "tool_file_count": len(files),
        "json_tool_file_count": sum(path.suffix == ".json" for path in files),
        "markdown_tool_file_count": sum(path.suffix == ".md" for path in files),
        "helper_inventory_files": sum(name.startswith("helper_inventory") for name in names),
        "oop_readability_files": sum(name.startswith("oop_readability") for name in names),
        "config_defaults_files": sum(name.startswith("config_defaults") for name in names),
        "structure_hash_files": sum("structure_hash" in name for name in names),
        "algorithm_contract_files": sum("algorithm_contract" in name for name in names),
    }


def generated_artifact_paths(run_dir: Path, source_text_paths: Iterable[Path]) -> list[Path]:
    """Return generated artifacts used for file-count and mtime span evidence."""
    paths = list(source_text_paths)
    tool_dir = run_dir / "tool"
    if tool_dir.is_dir():
        paths.extend(path for path in tool_dir.iterdir() if path.is_file())
    return paths


def category_counts(evidence: Iterable[Evidence]) -> dict[str, int]:
    """Count evidence categories."""
    return dict(Counter(item.category for item in evidence))


def summarize(run_dir: Path, dashboard_compact: Path) -> dict[str, object]:
    """Build a machine-readable summary."""
    paths = source_paths(run_dir, dashboard_compact)
    entries = parse_entries(paths)
    evidence = classify_entries(entries)
    roles = parse_roles(paths)
    artifact_paths = generated_artifact_paths(run_dir, paths)
    counts = {
        "parsed_entry_count": len(entries),
        "classified_evidence_count": len(evidence),
        "source_text_artifact_count": len(paths),
    }
    counts.update(category_counts(evidence))
    counts.update(tool_artifact_counts(run_dir))
    return {
        "schema": SCHEMA,
        "run_dir": str(run_dir),
        "dashboard_compact": str(dashboard_compact) if dashboard_compact.is_file() else None,
        "source_text_artifacts": [str(path) for path in paths],
        "raw_jsonl_read": False,
        "time_span": parse_time_span(entries),
        "artifact_time_span": artifact_time_span(artifact_paths),
        "counts": counts,
        "role_counts": dict(roles.most_common()),
        "dashboard_metrics": parse_dashboard_metrics(dashboard_compact),
        "evidence": [asdict(item) for item in evidence],
    }


def format_elapsed(seconds: object) -> str:
    """Format elapsed seconds for Markdown."""
    if not isinstance(seconds, int):
        return "unknown"
    hours, remainder = divmod(seconds, SECONDS_PER_HOUR)
    minutes, secs = divmod(remainder, SECONDS_PER_MINUTE)
    return f"{hours}h {minutes}m {secs}s"


def md_escape(value: object) -> str:
    """Escape a value for a compact Markdown table cell."""
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(summary: dict[str, object], *, max_evidence: int) -> str:
    """Render the summary as Markdown."""
    counts = summary["counts"]
    assert isinstance(counts, dict)
    time_span = summary["time_span"]
    assert isinstance(time_span, dict)
    artifact_span = summary["artifact_time_span"]
    assert isinstance(artifact_span, dict)
    role_counts = summary["role_counts"]
    assert isinstance(role_counts, dict)
    dashboard_metrics = summary["dashboard_metrics"]
    assert isinstance(dashboard_metrics, dict)
    evidence = summary["evidence"]
    assert isinstance(evidence, list)

    lines = [
        "# Subagent Revision Summary",
        "<!--",
        "@dependency-start",
        "responsibility Records generated subagent revision and rework summary evidence.",
        "upstream implementation ../../tools/agent_tools/summarize_subagent_revisions.py generates this report",
        f"upstream report {summary['dashboard_compact']} compact runtime dashboard source",
        "@dependency-end",
        "-->",
        "",
        "## Scope",
        "",
        f"- `run_dir`: `{summary['run_dir']}`",
        f"- `raw_jsonl_read`: `{summary['raw_jsonl_read']}`",
        f"- `first_entry`: `{time_span.get('first')}`",
        f"- `last_entry`: `{time_span.get('last')}`",
        f"- `elapsed`: `{format_elapsed(time_span.get('elapsed_seconds'))}`",
        f"- `first_artifact_mtime`: `{artifact_span.get('first')}`",
        f"- `last_artifact_mtime`: `{artifact_span.get('last')}`",
        f"- `artifact_mtime_elapsed`: `{format_elapsed(artifact_span.get('elapsed_seconds'))}`",
        "",
        "## Counts",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key in sorted(counts):
        lines.append(f"| `{md_escape(key)}` | `{md_escape(counts[key])}` |")

    if role_counts:
        lines.extend(["", "## Role Mentions", "", "| role | mentions |", "| --- | ---: |"])
        for role, count in sorted(role_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"| `{md_escape(role)}` | `{md_escape(count)}` |")

    selected_dashboard_keys = [
        "AGENT_RUNTIME_DASHBOARD_HOOK_ENTRIES",
        "AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING",
        "AGENT_RUNTIME_DASHBOARD_TOKEN_COMPARISONS",
        "AGENT_RUNTIME_DASHBOARD_PROMPT_ENTRIES",
        "AGENT_RUNTIME_DASHBOARD_TOOL_SELECTION_ENTRIES",
    ]
    lines.extend(["", "## Runtime Dashboard Signals", "", "| metric | value |", "| --- | ---: |"])
    for key in selected_dashboard_keys:
        lines.append(f"| `{key}` | `{md_escape(dashboard_metrics.get(key, 'missing'))}` |")

    by_category: dict[str, list[dict[str, object]]] = {}
    for item in evidence:
        category = str(item["category"])
        by_category.setdefault(category, []).append(item)
    for category in (
        "direct_subagent_output_revision",
        "broader_parent_or_validation_rework",
        "subagent_activity",
        "tool_or_validation_loop",
    ):
        rows = by_category.get(category, [])[:max_evidence]
        lines.extend(["", f"## {category}", "", "| timestamp | kind | source | message |", "| --- | --- | --- | --- |"])
        if not rows:
            lines.append("| `none` | `none` | `none` | `none` |")
            continue
        for item in rows:
            lines.append(
                "| `{}` | `{}` | `{}` | {} |".format(
                    md_escape(item.get("timestamp")),
                    md_escape(item.get("kind")),
                    md_escape(Path(str(item.get("source"))).name),
                    md_escape(item.get("message")),
                )
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    """Run the CLI."""
    args = build_parser().parse_args()
    run_dir = args.run_dir or newest_run_dir(args.reports_root)
    summary = summarize(run_dir, args.dashboard_compact)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    markdown = render_markdown(summary, max_evidence=args.max_evidence)
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(markdown, encoding="utf-8")
    if not args.out_json and not args.out_md:
        print(markdown)
    else:
        print(f"SUBAGENT_REVISION_SUMMARY_SCHEMA={SCHEMA}")
        print(f"SUBAGENT_REVISION_SUMMARY_RUN_DIR={run_dir}")
        if args.out_json:
            print(f"SUBAGENT_REVISION_SUMMARY_JSON={args.out_json}")
        if args.out_md:
            print(f"SUBAGENT_REVISION_SUMMARY_MD={args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
