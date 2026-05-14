#!/usr/bin/env python3
# @dependency-start
# responsibility Finds non-canonical document candidates and their likely canonical sources.
# upstream design ../../agents/skills/document-canon-cleanup.md document cleanup workflow
# upstream design ../../documents/dependency-manifest-design.md dependency manifest model
# downstream implementation ../../tests/agent_tools/test_noncanonical_document_inventory.py tests inventory behavior
# @dependency-end
"""Find non-canonical document candidates in an AgentCanon checkout."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from itertools import groupby
from pathlib import Path

DOC_SUFFIXES = frozenset({".md", ".rst", ".txt"})
HEADER_SCAN_LINES = 120
MAX_MARKDOWN_FINDINGS = 200
CLAUDE_SKILL_PART_COUNT = 4
CLAUDE_SKILL_NAME_INDEX = 2
CLAUDE_SKILL_FILE_INDEX = 3
EVAL_REPORT_MIN_PART_COUNT = 5
EVAL_RESULT_PREFIX_PART_COUNT = 4
EVAL_RESULT_PARTICIPATION_PREFIX_COUNT = 3
PRIORITY_AGENT_SKILL = 0
PRIORITY_HUMAN_SKILL = 1
PRIORITY_CANON_DOC = 2
PRIORITY_OTHER = 5
PRIORITY_RUNTIME_MIRROR = 9
STALE_NAME_RE = re.compile(
    r"(^|[-_/])(backup|copy|duplicate|legacy|old|snapshot|stale)([-_/]|$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DocumentRecord:
    """One document-like file in the repository."""

    path: str
    title: str
    responsibility: str
    has_dependency_manifest: bool


@dataclass(frozen=True)
class DocumentFinding:
    """One non-canonical document candidate."""

    path: str
    kind: str
    canonical_path: str
    action: str
    reason: str


@dataclass(frozen=True)
class InventoryReport:
    """Document inventory and non-canonical findings."""

    root: str
    documents: tuple[DocumentRecord, ...]
    findings: tuple[DocumentFinding, ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--json-out", help="Optional JSON report path.")
    parser.add_argument("--markdown-out", help="Optional Markdown report path.")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit non-zero when non-canonical candidates are found.",
    )
    return parser


def git_document_paths(root: Path) -> tuple[str, ...]:
    """Return git-visible document paths, or a filesystem fallback."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode == 0 and result.stdout:
        paths = [
            raw.decode("utf-8", errors="replace")
            for raw in result.stdout.split(b"\0")
            if raw
        ]
    else:
        paths = [
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        ]
    return tuple(
        sorted(path for path in paths if Path(path).suffix.lower() in DOC_SUFFIXES)
    )


def text_lines(path: Path) -> list[str]:
    """Return text lines for one document path."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()


def has_dependency_manifest(lines: Sequence[str]) -> bool:
    """Return whether a file has a dependency manifest near the top."""
    header = lines[:HEADER_SCAN_LINES]
    return any("@dependency-start" in line for line in header) and any(
        "@dependency-end" in line for line in header
    )


def dependency_responsibility(lines: Sequence[str]) -> str:
    """Return the dependency manifest responsibility line."""
    for raw_line in lines[:HEADER_SCAN_LINES]:
        stripped = raw_line.strip().lstrip("#").strip()
        if stripped.startswith("responsibility "):
            return stripped.removeprefix("responsibility ").strip()
    return ""


def markdown_title(lines: Sequence[str]) -> str:
    """Return the first Markdown-style H1 title."""
    for line in lines[:HEADER_SCAN_LINES]:
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def collect_documents(root: Path) -> tuple[DocumentRecord, ...]:
    """Collect document records."""
    records: list[DocumentRecord] = []
    for relative_path in git_document_paths(root):
        path = root / relative_path
        if not path.is_file() or path.is_symlink():
            continue
        lines = text_lines(path)
        records.append(
            DocumentRecord(
                path=relative_path,
                title=markdown_title(lines),
                responsibility=dependency_responsibility(lines),
                has_dependency_manifest=has_dependency_manifest(lines),
            )
        )
    return tuple(records)


def direct_findings(record: DocumentRecord) -> tuple[DocumentFinding, ...]:
    """Return direct non-canonical findings for one document."""
    path = Path(record.path)
    findings: list[DocumentFinding] = []

    mirror_source = claude_skill_source(path)
    if mirror_source:
        findings.append(
            DocumentFinding(
                path=record.path,
                kind="runtime_mirror",
                canonical_path=mirror_source,
                action="edit canonical skill source, then run mirror_skill_shims.py",
                reason=".claude skill files are generated runtime mirrors",
            )
        )

    if is_accumulated_eval_report(path):
        findings.append(
            DocumentFinding(
                path=record.path,
                kind="accumulated_eval_result",
                canonical_path="agents/evals/README.md",
                action="retain as evidence; do not edit as policy",
                reason="accumulated eval reports are run evidence, not the prompt canon",
            )
        )

    if path.parts and path.parts[0] == "reports":
        findings.append(
            DocumentFinding(
                path=record.path,
                kind="generated_report",
                canonical_path="tools/README.md",
                action="regenerate or cite as evidence; do not treat as source policy",
                reason="reports are generated run artifacts",
            )
        )

    if path.parts[:2] == ("issues", "closed") and path.name != "README.md":
        findings.append(
            DocumentFinding(
                path=record.path,
                kind="closed_issue_record",
                canonical_path="issues/README.md",
                action="retain as historical finding; open a new issue for new scope",
                reason="closed issue files are immutable operational records",
            )
        )

    if not record.has_dependency_manifest:
        findings.append(
            DocumentFinding(
                path=record.path,
                kind="missing_dependency_manifest",
                canonical_path=nearest_canonical_anchor(path),
                action="add a dependency manifest or move the artifact out of source docs",
                reason="document lacks a top dependency manifest",
            )
        )

    if STALE_NAME_RE.search(record.path):
        findings.append(
            DocumentFinding(
                path=record.path,
                kind="stale_name_candidate",
                canonical_path=nearest_canonical_anchor(path),
                action="confirm whether the document is current, then rename, merge, or remove",
                reason="path name suggests backup, copy, legacy, snapshot, old, or stale content",
            )
        )

    return tuple(findings)


def claude_skill_source(path: Path) -> str:
    """Return the canonical skill source for a Claude skill mirror."""
    parts = path.parts
    if (
        len(parts) == CLAUDE_SKILL_PART_COUNT
        and parts[0] == ".claude"
        and parts[1] == "skills"
    ):
        skill_name = parts[CLAUDE_SKILL_NAME_INDEX]
        if parts[CLAUDE_SKILL_FILE_INDEX] == "SKILL.md":
            return f".agents/skills/{skill_name}/SKILL.md"
    return ""


def is_accumulated_eval_report(path: Path) -> bool:
    """Return whether a path is an accumulated prompt eval report."""
    parts = path.parts
    return (
        len(parts) >= EVAL_REPORT_MIN_PART_COUNT
        and parts[:EVAL_RESULT_PREFIX_PART_COUNT]
        == ("agents", "evals", "results", "skill-workflow-prompt")
        and path.name != "README.md"
    )


def nearest_canonical_anchor(path: Path) -> str:
    """Return a likely canonical anchor for one document path."""
    if path.parts:
        root = path.parts[0]
        if root in {"agents", "documents", "issues", "memory", "notes", "tools"}:
            return f"{root}/README.md"
        if root.startswith("."):
            return "AGENTS.md"
    return "README.md"


def duplicate_title_findings(records: Sequence[DocumentRecord]) -> tuple[DocumentFinding, ...]:
    """Return findings for duplicate document titles."""
    return tuple(
        finding
        for _title, group in groupby(titled_records(records), key=lambda item: item[0])
        for finding in duplicate_group_findings(
            tuple(record for _title_key, record in group)
        )
    )


def titled_records(
    records: Sequence[DocumentRecord],
) -> tuple[tuple[str, DocumentRecord], ...]:
    """Return records with normalized titles."""
    return tuple(
        sorted(
            (
                (normalize_heading(record.title), record)
                for record in records
                if normalize_heading(record.title)
                and participates_in_duplicate_title_check(Path(record.path))
            ),
            key=lambda item: (item[0], item[1].path),
        )
    )


def participates_in_duplicate_title_check(path: Path) -> bool:
    """Return whether a path should be considered for active-doc title duplication."""
    if path.parts[:2] in {
        (".agents", "skills"),
        (".claude", "skills"),
        ("issues", "closed"),
        ("agents", "templates"),
    }:
        return False
    if path.parts[:EVAL_RESULT_PARTICIPATION_PREFIX_COUNT] == (
        "agents",
        "evals",
        "results",
    ):
        return False
    return True


def duplicate_group_findings(
    group: Sequence[DocumentRecord],
) -> tuple[DocumentFinding, ...]:
    """Return duplicate-title findings for one title group."""
    if len(group) < 2:
        return ()
    canonical = min(group, key=canonical_priority)
    return tuple(
        DocumentFinding(
            path=record.path,
            kind="duplicate_heading_candidate",
            canonical_path=canonical.path,
            action="merge, retitle, or document why both headings are active",
            reason=f"shares H1 title with {canonical.path}",
        )
        for record in group
        if record.path != canonical.path and not claude_skill_source(Path(record.path))
    )


def normalize_heading(value: str) -> str:
    """Return a normalized heading key."""
    return re.sub(r"\s+", " ", value.casefold()).strip()


def canonical_priority(record: DocumentRecord) -> tuple[int, str]:
    """Return sorting priority for likely canonical source selection."""
    path = record.path
    if path.startswith(".agents/skills/"):
        return (PRIORITY_AGENT_SKILL, path)
    if path.startswith("agents/skills/"):
        return (PRIORITY_HUMAN_SKILL, path)
    if path.startswith("agents/") or path.startswith("documents/"):
        return (PRIORITY_CANON_DOC, path)
    if path.startswith(".claude/skills/"):
        return (PRIORITY_RUNTIME_MIRROR, path)
    return (PRIORITY_OTHER, path)


def collect_findings(records: Sequence[DocumentRecord]) -> tuple[DocumentFinding, ...]:
    """Collect non-canonical document findings."""
    findings: list[DocumentFinding] = []
    for record in records:
        findings.extend(direct_findings(record))
    findings.extend(duplicate_title_findings(records))
    return tuple(sorted(dedupe_findings(findings), key=finding_sort_key))


def dedupe_findings(findings: Iterable[DocumentFinding]) -> tuple[DocumentFinding, ...]:
    """Return findings without duplicate rows."""
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[DocumentFinding] = []
    for finding in findings:
        key = (
            finding.path,
            finding.kind,
            finding.canonical_path,
            finding.action,
            finding.reason,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return tuple(unique)


def finding_sort_key(finding: DocumentFinding) -> tuple[str, str]:
    """Return stable finding sort key."""
    return (finding.path, finding.kind)


def build_report(root: Path) -> InventoryReport:
    """Build the non-canonical document inventory."""
    documents = collect_documents(root)
    findings = collect_findings(documents)
    return InventoryReport(root=root.as_posix(), documents=documents, findings=findings)


def render_json(report: InventoryReport) -> str:
    """Render JSON report."""
    payload = {
        "status": "pass",
        "root": report.root,
        "documents": [asdict(document) for document in report.documents],
        "findings": [asdict(finding) for finding in report.findings],
        "document_count": len(report.documents),
        "finding_count": len(report.findings),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def render_markdown(report: InventoryReport) -> str:
    """Render Markdown report."""
    lines = [
        "# Non-Canonical Document Inventory",
        "",
        "<!--",
        "@dependency-start",
        "responsibility Records non-canonical document candidates for cleanup review.",
        "upstream implementation tools/agent_tools/noncanonical_document_inventory.py generates this report",
        "@dependency-end",
        "-->",
        "",
        f"- root: `{report.root}`",
        f"- documents: `{len(report.documents)}`",
        f"- findings: `{len(report.findings)}`",
        "",
        "## Findings",
        "",
        "| Kind | Path | Canonical Path | Action | Reason |",
        "| ---- | ---- | -------------- | ------ | ------ |",
    ]
    for finding in report.findings[:MAX_MARKDOWN_FINDINGS]:
        lines.append(
            "| "
            + " | ".join(
                (
                    finding.kind,
                    f"`{finding.path}`",
                    f"`{finding.canonical_path}`",
                    finding.action,
                    finding.reason,
                )
            )
            + " |"
        )
    if len(report.findings) > MAX_MARKDOWN_FINDINGS:
        lines.append(
            f"| truncated | ... | ... | ... | {len(report.findings) - MAX_MARKDOWN_FINDINGS} additional findings omitted |"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_report(path: Path, text: str) -> None:
    """Write a report output."""
    target = path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def print_summary(report: InventoryReport) -> None:
    """Print machine-readable summary lines."""
    print("NONCANONICAL_DOCUMENT_INVENTORY=pass")
    print(f"NONCANONICAL_DOCUMENTS={len(report.documents)}")
    print(f"NONCANONICAL_DOCUMENT_FINDINGS={len(report.findings)}")
    for finding in report.findings:
        print(
            "NONCANONICAL_DOCUMENT_FINDING="
            f"{finding.kind}:{finding.path}:{finding.canonical_path}:{finding.action}"
        )


def main() -> int:
    """Run the non-canonical document inventory."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    report = build_report(root)
    if args.json_out:
        write_report(Path(args.json_out), render_json(report))
    if args.markdown_out:
        write_report(Path(args.markdown_out), render_markdown(report))
    print_summary(report)
    if args.fail_on_findings and report.findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
