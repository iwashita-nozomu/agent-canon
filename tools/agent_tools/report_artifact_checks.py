#!/usr/bin/env python3
"""Shared checks for run-bundle artifact completeness."""

from __future__ import annotations

import re


PLACEHOLDER_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
WORK_LOG_ENTRY_PATTERN = re.compile(
    r"^- `"
    r"(?P<timestamp>[^|`]+?) \| "
    r"(?P<kind>[^|`]+?) \| "
    r"(?P<message>.*?) \| "
    r"status: (?P<status>.*?) \| "
    r"request_clause_ids: (?P<clause_ids>.*?)(?: \| refs: (?P<refs>.*?))? \| "
    r"next: (?P<next>.*?)"
    r"`$"
)


def is_placeholder_only_section(text: str) -> bool:
    """Return whether the artifact still looks like an untouched template."""
    stripped = PLACEHOLDER_PATTERN.sub("", text).strip()
    stripped = "\n".join(
        line
        for line in stripped.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
        and not line.strip().startswith("- Run ID:")
        and not line.strip().startswith("- Task:")
        and not line.strip().startswith("- Owner:")
        and not line.strip().startswith("- Created At")
        and not line.strip().startswith("|")
    ).strip()
    return not stripped


def section_has_content(text: str, heading: str) -> bool:
    """Return whether a markdown section exists and has non-placeholder content."""
    lines = text.splitlines()
    in_section = False
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == heading
            continue
        if in_section:
            body.append(line)
    if not in_section:
        return False
    body_text = PLACEHOLDER_PATTERN.sub("", "\n".join(body))
    body_text = "\n".join(line for line in body_text.splitlines() if line.strip()).strip()
    return bool(body_text)


def table_body_rows(text: str, heading: str) -> list[str]:
    """Return non-header table rows under one markdown section."""
    rows: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= {"-"} for cell in cells):
            continue
        if any(cell in {"Clause ID", "Source Bucket", "Stage", "Unit ID"} for cell in cells):
            continue
        rows.append(stripped)
    return rows


def bullet_rows(text: str, heading: str) -> list[str]:
    """Return bullet rows under one markdown section."""
    rows: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped == heading
            continue
        if not in_section:
            continue
        if stripped.startswith("- "):
            rows.append(stripped)
    return rows


def parse_work_log_entries(text: str) -> list[dict[str, str]]:
    """Return parsed work-log entries from the Entries section."""
    entries: list[dict[str, str]] = []
    for index, row in enumerate(bullet_rows(text, "## Entries"), start=1):
        match = WORK_LOG_ENTRY_PATTERN.match(row)
        if match is None:
            raise ValueError(f"work_log.md:entry_malformed:{index}")
        entries.append({key: value.strip() for key, value in match.groupdict(default="").items()})
    return entries


def check_schedule_artifact(text: str) -> list[str]:
    """Return blockers for schedule.md."""
    blockers: list[str] = []
    required_tables = (
        ("## Stage Plan", "stage_plan_empty"),
        ("## Clause Coverage", "clause_coverage_empty"),
        ("## Planned Work Units", "planned_work_units_empty"),
    )
    for heading, slug in required_tables:
        if not table_body_rows(text, heading):
            blockers.append(f"schedule.md:{slug}")
    return blockers


def check_work_log_artifact(text: str) -> list[str]:
    """Return blockers for work_log.md."""
    blockers: list[str] = []
    if not section_has_content(text, "## Entries"):
        blockers.append("work_log.md:section_empty_or_missing:entries")
        return blockers
    rows = bullet_rows(text, "## Entries")
    if not rows:
        blockers.append("work_log.md:entries_empty")
        return blockers
    try:
        entries = parse_work_log_entries(text)
    except ValueError as exc:
        blockers.append(str(exc))
        return blockers
    if len(entries) < 3:
        blockers.append("work_log.md:entries_too_few")
    distinct_kinds = {entry["kind"] for entry in entries}
    if len(distinct_kinds) < 2:
        blockers.append("work_log.md:entry_kind_diversity_too_low")
    return blockers
