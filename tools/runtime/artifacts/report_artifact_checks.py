#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides report artifact checks agent workflow automation.
# upstream design ../../../README.md shared automation index
# upstream design ../../../documents/design/request-intent-and-update-relation.md run-bundle temporary-state and retention readback projection
# @dependency-end

"""Read-only checks for retained report and archive inputs."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


PLACEHOLDER_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
REVIEW_ADJUDICATION_PLACEHOLDERS = frozenset(
    {"", "-", "—", "none", "null", "n/a", "na", "missing", "unknown", "todo", "tbd"}
)
APPROVE_DECISION_PATTERN = re.compile(
    r"^(?:[-*]\s*)?(?:decision\s*:\s*)?approve\s*$",
    re.IGNORECASE,
)
REVIEW_TARGET_SHA_PATTERN = re.compile(
    r"\breview_target_sha256\s*=\s*`?([0-9a-f]{64})`?",
    re.IGNORECASE,
)
DESIGN_ARTIFACT_PATH_PATTERN = re.compile(
    r"^\s*-\s*Design artifact path:\s*`?([^`\r\n]+?)`?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
MECHANICALLY_REGENERATED_REPORT_ROOTS = (
    PurePosixPath("reports/agent-eval-runs"),
    PurePosixPath("reports/agent-improvement-guide"),
    PurePosixPath("reports/agent-runtime-dashboard"),
    PurePosixPath("reports/dependency-review"),
    PurePosixPath("reports/hooks"),
    PurePosixPath("reports/.cache"),
)
MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS = (
    re.compile(r"^reports/[^/]+\.(?:json|patch|txt)$"),
)
EVAL_TRANSIENT_CAPTURE_PATTERN = re.compile(
    r"^reports/agent-eval-runs/[^/]+/[^/]+\.(?:stdout|stderr)\.txt$"
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


def markdown_without_adjudicated_rejected_hypotheses(text: str) -> str:
    """Exclude only structurally valid rejected hypothesis table rows."""
    lines = text.splitlines()
    table_indexes: tuple[int, int, int] | None = None
    output: list[str] = []
    for line in lines:
        cells = tuple(cell.strip() for cell in line.split("|")[1:-1])
        normalized = tuple(
            re.sub(r"[^a-z0-9]+", "_", cell.lower()).strip("_") for cell in cells
        )
        if {
            "adjudication",
            "reason_code",
            "evidence_ref",
        }.issubset(normalized):
            table_indexes = (
                normalized.index("adjudication"),
                normalized.index("reason_code"),
                normalized.index("evidence_ref"),
            )
            output.append(line)
            continue
        if not cells or not line.lstrip().startswith("|"):
            table_indexes = None
            output.append(line)
            continue
        if table_indexes is not None:
            adjudication_index, reason_index, evidence_index = table_indexes
            indexes = (adjudication_index, reason_index, evidence_index)
            if max(indexes) < len(cells):
                adjudication = cells[adjudication_index].lower()
                reason_code = cells[reason_index].lower()
                evidence_ref = cells[evidence_index].lower()
                if (
                    adjudication == "rejected"
                    and reason_code not in REVIEW_ADJUDICATION_PLACEHOLDERS
                    and evidence_ref not in REVIEW_ADJUDICATION_PLACEHOLDERS
                ):
                    continue
        output.append(line)
    return "\n".join(output)


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
    body_text = "\n".join(
        line for line in body_text.splitlines() if line.strip()
    ).strip()
    return bool(body_text)


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


def token_fields(line: str) -> dict[str, str]:
    """Parse whitespace-separated key=value fields from one evidence line."""
    data: dict[str, str] = {}
    for token in line.strip().strip("-").strip("`").split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        data[key.strip()] = value.strip("`'\"")
    return data


def _git_report_paths(workspace: Path, args: tuple[str, ...]) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *args, "-z", "--", "reports"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return []
    return [
        raw_path.decode("utf-8", errors="surrogateescape")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def _normalized_git_path(path: str) -> str:
    """Return a POSIX-style Git path for classification."""
    return path.replace("\\", "/").strip("/")


def _is_relative_to(path: PurePosixPath, root: PurePosixPath) -> bool:
    """Return whether a POSIX path is equal to or nested under root."""
    return path == root or path.is_relative_to(root)


def is_mechanically_regenerated_report_path(path: str) -> bool:
    """Return whether one report path is a known mechanically regenerated output."""
    normalized = _normalized_git_path(path)
    candidate = PurePosixPath(normalized)
    if any(
        _is_relative_to(candidate, root)
        for root in MECHANICALLY_REGENERATED_REPORT_ROOTS
    ):
        return True
    return any(
        pattern.match(normalized)
        for pattern in MECHANICALLY_REGENERATED_REPORT_FILE_PATTERNS
    )


def generated_eval_transient_blockers(workspace: Path) -> list[str]:
    """Return exact two-level eval producer stdout/stderr captures in the tree."""
    report_paths = {
        path: "tracked"
        for path in _git_report_paths(workspace, ())
        if EVAL_TRANSIENT_CAPTURE_PATTERN.fullmatch(_normalized_git_path(path))
    }
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        if EVAL_TRANSIENT_CAPTURE_PATTERN.fullmatch(_normalized_git_path(path)):
            report_paths.setdefault(path, "untracked")
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        if EVAL_TRANSIENT_CAPTURE_PATTERN.fullmatch(_normalized_git_path(path)):
            report_paths.setdefault(path, "ignored")
    return [
        f"generated_report_artifact_{state}_left_in_tree:{path}"
        for path, state in sorted(report_paths.items())
    ]


def report_artifact_placement_blockers(workspace: Path, report_dir: Path) -> list[str]:
    """Return generated report artifacts outside the active run bundle.

    Tracked report history is baseline repository state and is not a placement
    error.  Untracked generated report files are allowed only under the current
    run directory because runtime archive tooling collects one active run bundle
    at closeout. Ignored non-generated report paths are local cache and do not
    block closeout.
    """
    if not report_dir.resolve().is_relative_to(workspace.resolve()):
        return []
    report_paths: dict[str, str] = {}
    for path in _git_report_paths(
        workspace,
        ("--others", "--exclude-standard"),
    ):
        report_paths.setdefault(path, "untracked")
    for path in _git_report_paths(
        workspace,
        ("--others", "--ignored", "--exclude-standard"),
    ):
        report_paths.setdefault(path, "ignored")

    blockers: list[str] = []
    report_root_metadata = {
        (report_dir.parent / ".active_run").resolve(),
        (report_dir.parent / ".active_run.sha256").resolve(),
        (report_dir.parent / ".run_bundle_materialization.lock").resolve(),
    }
    for path, state in sorted(report_paths.items()):
        candidate = workspace / path
        if candidate.resolve() in report_root_metadata:
            continue
        if candidate.resolve().is_relative_to(report_dir.resolve()):
            continue
        if state == "ignored" and not is_mechanically_regenerated_report_path(path):
            continue
        blockers.append(f"report_artifact_{state}_outside_current_run:{path}")
    return blockers


def check_work_log_artifact(text: str) -> list[str]:
    """Return blockers for work_log.md."""
    blockers: list[str] = []
    if not section_has_content(text, "## Entries"):
        blockers.append("work_log.md:section_empty_or_missing:entries")
        return blockers
    if not bullet_rows(text, "## Entries"):
        blockers.append("work_log.md:entries_empty")
    return blockers


def final_review_decision_lines(text: str) -> list[str]:
    """Return normalized non-placeholder lines from a final-review Decision section."""
    lines: list[str] = []
    in_decision = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_decision:
                break
            in_decision = stripped == "## Decision"
            continue
        if in_decision:
            normalized = PLACEHOLDER_PATTERN.sub("", line).strip()
            if normalized:
                lines.append(normalized)
    return lines


def has_approve_decision(text: str) -> bool:
    """Return whether a final-review Decision section contains an exact approve decision."""
    return any(
        APPROVE_DECISION_PATTERN.fullmatch(line)
        for line in final_review_decision_lines(text)
    )


@dataclass(frozen=True)
class ReviewIdentityResult:
    """Authoritative design-path, target-digest, and decision projection."""

    design_artifact_path: str | None
    review_target_sha256: str | None
    decision_approved: bool


def parse_review_identity(text: str) -> ReviewIdentityResult:
    """Parse one review identity through the shared structural decision owner."""
    path_matches = DESIGN_ARTIFACT_PATH_PATTERN.findall(text)
    sha_matches = REVIEW_TARGET_SHA_PATTERN.findall(text)
    return ReviewIdentityResult(
        design_artifact_path=(
            path_matches[-1].strip().strip("'\"") if path_matches else None
        ),
        review_target_sha256=(sha_matches[-1].lower() if sha_matches else None),
        decision_approved=has_approve_decision(text),
    )


def check_final_review_artifact(text: str) -> list[str]:
    """Return blockers for final_review.md."""
    blockers: list[str] = []
    if is_placeholder_only_section(text):
        blockers.append("final_review.md:placeholder_only")
    if not section_has_content(text, "## Decision"):
        blockers.append("final_review.md:section_empty_or_missing:decision")
        return blockers
    if not has_approve_decision(text):
        blockers.append("final_review.md:decision_not_approve")
    return blockers
