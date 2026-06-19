#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Evaluates skill and workflow prompt surfaces against frozen prompt evals.
# upstream design ../../evidence/agent-evals/README.md prompt eval directory contract
# upstream design ../../evidence/agent-evals/skill_workflow_prompt_eval.toml default prompt eval manifest
# upstream implementation ./runtime_log_paths.py resolves accumulated eval archive paths
# downstream implementation ../../tests/agent_tools/test_evaluate_skill_workflow_prompts.py tests it
# @dependency-end
"""Evaluate skill and workflow prompt surfaces against frozen checklist evals."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
import tomllib

from eval_manifest_paths import eval_manifest_path, relative_manifest_path, resolve_eval_manifest
from runtime_log_paths import agent_canon_root, eval_results_dir
from workflow_monitor import MonitoringEntries, append_monitoring

DEFAULT_RESULTS_FAMILY = "skill-workflow-prompt"
REPORT_STATUS_LINE_LIMIT = 13
RUN_ID_DIGEST_LENGTH = 10
UNIQUE_REPORT_CANDIDATE_LIMIT = 1000
GIT_COMMAND_TIMEOUT_SECONDS = 5
COMPACT_MISSING_REQUIRED_SAMPLE_LIMIT = 5
COMPACT_MATCHED_FORBIDDEN_SAMPLE_LIMIT = 5
COMPACT_FAILED_CHECK_SAMPLE_LIMIT = 25


@dataclass(frozen=True)
class ChecklistItem:
    """One frozen eval checklist item."""

    item_id: str
    critical: bool
    description: str
    required_regex: tuple[str, ...]
    forbidden_regex: tuple[str, ...]


@dataclass(frozen=True)
class PromptEval:
    """One target prompt eval definition."""

    eval_id: str
    target: Path
    kind: str
    description: str
    checklist: tuple[ChecklistItem, ...]


@dataclass(frozen=True)
class ChecklistResult:
    """One checklist result."""

    eval_id: str
    item_id: str
    critical: bool
    passed: bool
    description: str
    missing_required: tuple[str, ...]
    matched_forbidden: tuple[str, ...]


@dataclass(frozen=True)
class ManifestAudit:
    """Manifest-level duplicate and growth-candidate audit."""

    duplicate_eval_ids: tuple[str, ...]
    duplicate_targets: tuple[str, ...]
    duplicate_checklist_ids: tuple[str, ...]

    @property
    def growth_candidates(self) -> int:
        """Return the number of manifest fixes still required."""
        return (
            len(self.duplicate_eval_ids)
            + len(self.duplicate_targets)
            + len(self.duplicate_checklist_ids)
        )

    @property
    def passed(self) -> bool:
        """Return true when no manifest growth candidates remain."""
        return self.growth_candidates == 0


@dataclass(frozen=True)
class EvalRunMetadata:
    """Metadata recorded with one prompt eval run."""

    created_at: str
    eval_run_id: str
    used_skills: tuple[str, ...]
    run_id: str
    argv: tuple[str, ...]
    cwd: str
    root: str
    manifest: str
    git_branch: str
    git_commit: str
    git_dirty: str


@dataclass(frozen=True)
class ReportDependencyPaths:
    """Dependency paths rendered relative to one Markdown report."""

    tool: str
    manifest: str


@dataclass(frozen=True)
class EvalOutputs:
    """Optional output paths rendered in machine status lines."""

    accumulated_report: str = ""
    report_out: str = ""
    compact_out: str = ""


EMPTY_EVAL_OUTPUTS = EvalOutputs()


@dataclass(frozen=True)
class EvalRunBundle:
    """All evaluated prompt data used to render reports and status."""

    manifest: Path
    evals: tuple[PromptEval, ...]
    results: tuple[ChecklistResult, ...]
    audit: ManifestAudit
    metadata: EvalRunMetadata


@dataclass(frozen=True)
class ReportWriteRequest:
    """Inputs for writing one Markdown eval report."""

    path: str
    root: Path
    bundle: EvalRunBundle


@dataclass(frozen=True)
class AccumulatedReportRequest:
    """Inputs for writing one accumulated eval report."""

    root: Path
    results_dir: Path
    bundle: EvalRunBundle


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Evaluate skill and workflow prompt drift from a TOML manifest."
    )
    parser.add_argument(
        "--manifest",
        default=eval_manifest_path("skill_workflow_prompt_eval.toml"),
        help="Prompt eval TOML manifest.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root. Defaults to current directory.",
    )
    parser.add_argument(
        "--report-out",
        help="Optional Markdown report path.",
    )
    parser.add_argument(
        "--compact-out",
        help=(
            "Optional JSON summary path. When set, stdout is limited to status "
            "and artifact paths; detailed check rows are written to artifacts."
        ),
    )
    parser.add_argument(
        "--accumulate",
        action="store_true",
        help=(
            "Write a unique durable Markdown report under --results-dir. "
            "Use this whenever a skill is selected or invoked."
        ),
    )
    parser.add_argument(
        "--results-dir",
        default="",
        help=(
            "Directory for accumulated detailed reports. Defaults to the mounted "
            "AgentCanon log archive eval-results/skill-workflow-prompt path."
        ),
    )
    parser.add_argument(
        "--skill-used",
        action="append",
        default=[],
        help="Skill id used in the run. Repeat for every selected or invoked skill.",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional run bundle id recorded in accumulated reports.",
    )
    parser.add_argument(
        "--report-dir",
        help=(
            "Optional run bundle directory. When set with --accumulate, append "
            "the prompt eval behavior event to workflow_monitoring.md."
        ),
    )
    return parser


def string_list(value: object, field: str) -> tuple[str, ...]:
    """Return a tuple of strings from a manifest value."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    items = cast(list[object], value)
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"{field} must be a list of strings")
    return tuple(cast(list[str], value))


def load_manifest(path: Path, root: Path) -> tuple[tuple[PromptEval, ...], ManifestAudit]:
    """Load a prompt eval manifest."""
    data: dict[str, object] = tomllib.loads(path.read_text(encoding="utf-8"))
    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        raise ValueError("manifest must define at least one [[evals]] entry")
    raw_evals = cast(list[object], evals)
    audit = audit_manifest(raw_evals)
    if not audit.passed:
        raise ValueError(render_audit_errors(audit))
    loaded: list[PromptEval] = []
    for index, raw_entry in enumerate(raw_evals, 1):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"eval entry {index} must be a table")
        entry = cast(dict[str, object], raw_entry)
        raw_checklist = entry.get("checklist")
        if not isinstance(raw_checklist, list) or not raw_checklist:
            raise ValueError(f"eval {entry.get('id', index)} must define checklist items")
        checklist_items = cast(list[object], raw_checklist)
        checklist = tuple(
            load_checklist_item(item, str(entry.get("id", index))) for item in checklist_items
        )
        loaded.extend(expand_eval_entry(entry, checklist, root))
    return tuple(loaded), audit


def audit_manifest(raw_evals: list[object]) -> ManifestAudit:
    """Find duplicate manifest surfaces before prompt evaluation."""
    eval_ids: list[str] = []
    explicit_targets: list[str] = []
    duplicate_checklist_ids: list[str] = []
    for index, raw_entry in enumerate(raw_evals, 1):
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[str, object], raw_entry)
        eval_id = str(entry.get("id", index))
        eval_ids.append(eval_id)
        if "target" in entry:
            explicit_targets.append(str(entry["target"]))
        raw_checklist = entry.get("checklist")
        if isinstance(raw_checklist, list):
            checklist_items = cast(list[object], raw_checklist)
            seen_items: set[str] = set()
            for raw_item in checklist_items:
                if not isinstance(raw_item, dict):
                    continue
                item = cast(dict[str, object], raw_item)
                item_id = str(item.get("id", ""))
                key = f"{eval_id}:{item_id}"
                if item_id in seen_items:
                    duplicate_checklist_ids.append(key)
                seen_items.add(item_id)
    return ManifestAudit(
        duplicate_eval_ids=duplicates(eval_ids),
        duplicate_targets=duplicates(explicit_targets),
        duplicate_checklist_ids=tuple(sorted(duplicate_checklist_ids)),
    )


def duplicates(values: list[str]) -> tuple[str, ...]:
    """Return duplicate values in stable first-seen order."""
    seen: set[str] = set()
    repeated: list[str] = []
    for value in values:
        if value in seen and value not in repeated:
            repeated.append(value)
        seen.add(value)
    return tuple(repeated)


def render_audit_errors(audit: ManifestAudit) -> str:
    """Render manifest audit failures for stderr."""
    lines = ["manifest audit failed"]
    for eval_id in audit.duplicate_eval_ids:
        lines.append(f"duplicate eval id: {eval_id}")
    for target in audit.duplicate_targets:
        lines.append(f"duplicate explicit target: {target}")
    for item_id in audit.duplicate_checklist_ids:
        lines.append(f"duplicate checklist id: {item_id}")
    return "; ".join(lines)


def expand_eval_entry(
    entry: dict[str, object],
    checklist: tuple[ChecklistItem, ...],
    root: Path,
) -> tuple[PromptEval, ...]:
    """Expand one manifest eval entry into target-specific evals."""
    eval_id = str(entry["id"])
    kind = str(entry.get("kind", "prompt"))
    description = str(entry.get("description", ""))
    has_target = "target" in entry
    has_target_glob = "target_glob" in entry
    if has_target == has_target_glob:
        raise ValueError(f"eval {eval_id} must define exactly one of target or target_glob")
    if has_target:
        return (
            PromptEval(
                eval_id=eval_id,
                target=resolve_target(root, str(entry["target"])),
                kind=kind,
                description=description,
                checklist=checklist,
            ),
        )
    pattern = str(entry["target_glob"])
    paths = tuple(
        sorted(
            root / path
            for path in glob.glob(pattern, root_dir=root)
            if (root / path).is_file()
        )
    )
    if not paths:
        raise ValueError(f"eval {eval_id} target_glob matched no files: {pattern}")
    expected_count = entry.get("expected_count")
    if expected_count is not None and int(str(expected_count)) != len(paths):
        raise ValueError(
            f"eval {eval_id} target_glob expected_count={expected_count} "
            f"actual_count={len(paths)} pattern={pattern}"
        )
    return tuple(
        PromptEval(
            eval_id=f"{eval_id}:{path.relative_to(root).as_posix()}",
            target=path,
            kind=kind,
            description=description,
            checklist=checklist,
        )
        for path in paths
    )


def resolve_target(root: Path, target: str) -> Path:
    """Resolve a prompt target in source or vendored snapshot layouts."""
    direct = root / target
    if direct.exists():
        return direct
    vendored = root / "vendor" / "agent-canon" / target
    if vendored.exists():
        return vendored
    return direct


def load_checklist_item(entry: object, eval_id: str) -> ChecklistItem:
    """Load one checklist item."""
    if not isinstance(entry, dict):
        raise ValueError(f"checklist item for {eval_id} must be a table")
    item = cast(dict[str, object], entry)
    return ChecklistItem(
        item_id=str(item["id"]),
        critical=bool(item.get("critical", False)),
        description=str(item.get("description", "")),
        required_regex=string_list(item.get("required_regex"), f"{eval_id}.required_regex"),
        forbidden_regex=string_list(item.get("forbidden_regex"), f"{eval_id}.forbidden_regex"),
    )


def evaluate_item(item: ChecklistItem, eval_def: PromptEval, text: str) -> ChecklistResult:
    """Evaluate one checklist item against target text."""
    missing_required = tuple(
        pattern for pattern in item.required_regex if re.search(pattern, text, re.MULTILINE) is None
    )
    matched_forbidden = tuple(
        pattern for pattern in item.forbidden_regex if re.search(pattern, text, re.MULTILINE)
    )
    return ChecklistResult(
        eval_id=eval_def.eval_id,
        item_id=item.item_id,
        critical=item.critical,
        passed=not missing_required and not matched_forbidden,
        description=item.description,
        missing_required=missing_required,
        matched_forbidden=matched_forbidden,
    )


def evaluate_prompt(eval_def: PromptEval) -> tuple[ChecklistResult, ...]:
    """Evaluate one prompt surface."""
    if not eval_def.target.is_file():
        return tuple(
            ChecklistResult(
                eval_id=eval_def.eval_id,
                item_id=item.item_id,
                critical=item.critical,
                passed=False,
                description=f"missing target: {eval_def.target}",
                missing_required=("target-file",),
                matched_forbidden=(),
            )
            for item in eval_def.checklist
        )
    text = eval_def.target.read_text(encoding="utf-8")
    return tuple(evaluate_item(item, eval_def, text) for item in eval_def.checklist)


def render_machine_status(
    bundle: EvalRunBundle,
    outputs: EvalOutputs = EMPTY_EVAL_OUTPUTS,
    *,
    include_details: bool = True,
) -> str:
    """Render machine-readable status."""
    results = bundle.results
    audit = bundle.audit
    metadata = bundle.metadata
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    critical_total = sum(1 for result in results if result.critical)
    critical_failed = sum(1 for result in results if result.critical and not result.passed)
    status = "pass" if critical_failed == 0 and audit.passed else "fail"
    lines = [
        f"EVAL_STATUS={status}",
        f"EVAL_CHECKS_TOTAL={total}",
        f"EVAL_CHECKS_PASSED={passed}",
        f"EVAL_CRITICAL_TOTAL={critical_total}",
        f"EVAL_CRITICAL_FAILED={critical_failed}",
        f"EVAL_AUDIT_STATUS={'pass' if audit.passed else 'fail'}",
        f"EVAL_DUPLICATE_EVAL_IDS={len(audit.duplicate_eval_ids)}",
        f"EVAL_DUPLICATE_TARGETS={len(audit.duplicate_targets)}",
        f"EVAL_DUPLICATE_CHECKLIST_IDS={len(audit.duplicate_checklist_ids)}",
        f"EVAL_GROWTH_CANDIDATES={audit.growth_candidates}",
        f"EVAL_RUN_ID={metadata.eval_run_id}",
        f"EVAL_USED_SKILLS={','.join(metadata.used_skills) or '-'}",
        f"EVAL_GIT_BRANCH={metadata.git_branch}",
        f"EVAL_GIT_COMMIT={metadata.git_commit}",
        f"EVAL_GIT_DIRTY={metadata.git_dirty}",
    ]
    if outputs.accumulated_report:
        lines.append(f"EVAL_ACCUMULATED_REPORT={outputs.accumulated_report}")
    if outputs.report_out:
        lines.append(f"EVAL_REPORT_OUT={outputs.report_out}")
    if outputs.compact_out:
        lines.append(f"EVAL_COMPACT_OUT={outputs.compact_out}")
    if not include_details:
        return "\n".join(lines) + "\n"
    for result in results:
        verdict = "pass" if result.passed else "fail"
        lines.append(
            f"EVAL_CHECK eval={result.eval_id} item={result.item_id} "
            f"critical={str(result.critical).lower()} status={verdict}"
        )
        for pattern in result.missing_required:
            lines.append(
                f"EVAL_MISSING_REQUIRED eval={result.eval_id} item={result.item_id} "
                f"pattern={pattern}"
            )
        for pattern in result.matched_forbidden:
            lines.append(
                f"EVAL_MATCHED_FORBIDDEN eval={result.eval_id} item={result.item_id} "
                f"pattern={pattern}"
            )
    return "\n".join(lines) + "\n"


def compact_summary(bundle: EvalRunBundle, outputs: EvalOutputs) -> dict[str, object]:
    """Return a bounded JSON-friendly eval summary."""
    results = bundle.results
    audit = bundle.audit
    failed = [result for result in results if not result.passed]
    critical_failed = [result for result in failed if result.critical]
    return {
        "status": eval_status(results, audit),
        "eval_run_id": bundle.metadata.eval_run_id,
        "run_id": bundle.metadata.run_id,
        "used_skills": list(bundle.metadata.used_skills),
        "git_branch": bundle.metadata.git_branch,
        "git_commit": bundle.metadata.git_commit,
        "git_dirty": bundle.metadata.git_dirty,
        "checks_total": len(results),
        "checks_passed": sum(1 for result in results if result.passed),
        "critical_total": sum(1 for result in results if result.critical),
        "critical_failed": len(critical_failed),
        "audit_status": "pass" if audit.passed else "fail",
        "audit": {
            "duplicate_eval_ids": len(audit.duplicate_eval_ids),
            "duplicate_targets": len(audit.duplicate_targets),
            "duplicate_checklist_ids": len(audit.duplicate_checklist_ids),
            "growth_candidates": audit.growth_candidates,
        },
        "outputs": {
            "accumulated_report": outputs.accumulated_report,
            "report_out": outputs.report_out,
            "compact_out": outputs.compact_out,
        },
        "failed_check_samples": [
            {
                "eval_id": result.eval_id,
                "item_id": result.item_id,
                "critical": result.critical,
                "missing_required": list(
                    result.missing_required[:COMPACT_MISSING_REQUIRED_SAMPLE_LIMIT]
                ),
                "matched_forbidden": list(
                    result.matched_forbidden[:COMPACT_MATCHED_FORBIDDEN_SAMPLE_LIMIT]
                ),
            }
            for result in failed[:COMPACT_FAILED_CHECK_SAMPLE_LIMIT]
        ],
    }


def write_compact_summary(path: Path, bundle: EvalRunBundle, outputs: EvalOutputs) -> Path:
    """Write a bounded JSON summary for agent consumption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(compact_summary(bundle, outputs), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def render_markdown_report(
    bundle: EvalRunBundle,
    dependency_paths: ReportDependencyPaths,
) -> str:
    """Render a Markdown eval report."""
    evals = bundle.evals
    results = bundle.results
    metadata = bundle.metadata
    by_eval = {eval_def.eval_id: eval_def for eval_def in evals}
    lines = [
        "# Skill Workflow Prompt Eval",
        "<!--",
        "@dependency-start",
        "responsibility Records skill/workflow prompt eval results.",
        f"upstream implementation {dependency_paths.tool} "
        "generates this report",
        f"upstream design {dependency_paths.manifest} defines frozen evals",
        "@dependency-end",
        "-->",
        "",
        "## Summary",
        "",
        f"- created_at: `{metadata.created_at}`",
        f"- eval_run_id: `{metadata.eval_run_id}`",
        f"- run_id: `{metadata.run_id or '-'}`",
        f"- used_skills: `{', '.join(metadata.used_skills) or '-'}`",
    ]
    status_lines = render_machine_status(bundle).strip().splitlines()
    lines.extend(f"- {line}" for line in status_lines[:REPORT_STATUS_LINE_LIMIT])
    lines.extend(
        [
            "",
            "## Run Manifest",
            "",
            f"- argv: `{' '.join(metadata.argv)}`",
            f"- cwd: `{metadata.cwd}`",
            f"- root: `{metadata.root}`",
            f"- manifest: `{metadata.manifest}`",
            f"- git_branch: `{metadata.git_branch}`",
            f"- git_commit: `{metadata.git_commit}`",
            f"- git_dirty: `{metadata.git_dirty}`",
            "",
            "## Results",
            "",
        ]
    )
    for result in results:
        eval_def = by_eval[result.eval_id]
        verdict = "pass" if result.passed else "fail"
        lines.append(f"- `{result.eval_id}` / `{result.item_id}`: `{verdict}`")
        lines.append(f"  - target: `{eval_def.target}`")
        lines.append(f"  - critical: `{str(result.critical).lower()}`")
        lines.append(f"  - description: {result.description}")
        if result.missing_required:
            lines.append(f"  - missing_required: `{', '.join(result.missing_required)}`")
        if result.matched_forbidden:
            lines.append(f"  - matched_forbidden: `{', '.join(result.matched_forbidden)}`")
    lines.append("")
    return "\n".join(lines)


def write_report(request: ReportWriteRequest) -> Path:
    """Write a Markdown eval report."""
    report_path = unique_report_path(Path(request.path), request.bundle.metadata)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_markdown_report(
            request.bundle,
            dependency_paths=report_dependency_paths(
                report_path,
                request.root,
                request.bundle.manifest,
            ),
        ),
        encoding="utf-8",
    )
    return report_path


def relative_posix_path(from_dir: Path, to_path: Path) -> str:
    """Return a POSIX relative path from one directory to a target."""
    return os.path.relpath(to_path.resolve(), from_dir.resolve()).replace(os.sep, "/")


def report_dependency_paths(report_path: Path, root: Path, manifest: Path) -> ReportDependencyPaths:
    """Return dependency paths that are valid from the generated report."""
    report_dir = report_path.parent
    manifest_path = manifest if manifest.is_absolute() else root / manifest
    tool_path = root / "tools" / "agent_tools" / "evaluate_skill_workflow_prompts.py"
    return ReportDependencyPaths(
        tool=relative_posix_path(report_dir, tool_path),
        manifest=relative_posix_path(report_dir, manifest_path),
    )


def report_slug(manifest: Path, metadata: EvalRunMetadata, status: str) -> str:
    """Return a stable filename slug for one accumulated report."""
    skill_slug = "-".join(skill.replace("_", "-") for skill in metadata.used_skills) or "no-skill"
    return f"{metadata.eval_run_id}-{status}-{skill_slug}.md"


def unique_report_path(path: Path, metadata: EvalRunMetadata) -> Path:
    """Return a non-existing report path by adding the run id when needed."""
    if not path.exists():
        return path
    candidate = path.with_name(f"{path.stem}-{metadata.eval_run_id}{path.suffix}")
    if not candidate.exists():
        return candidate
    for index in range(2, UNIQUE_REPORT_CANDIDATE_LIMIT):
        indexed = path.with_name(f"{path.stem}-{metadata.eval_run_id}-{index:03d}{path.suffix}")
        if not indexed.exists():
            return indexed
    raise RuntimeError(f"unable to allocate unique eval report path for {path}")


def build_eval_run_metadata(
    manifest: Path,
    used_skills: Sequence[str],
    run_id: str,
    root: Path,
) -> EvalRunMetadata:
    """Build metadata with a unique, filename-safe eval run id."""
    now = datetime.now(UTC)
    created_at = now.isoformat()
    timestamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    clean_skills = tuple(skill.strip() for skill in used_skills if skill.strip())
    digest_source = "|".join((manifest.as_posix(), run_id.strip(), ",".join(clean_skills), created_at))
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:RUN_ID_DIGEST_LENGTH]
    return EvalRunMetadata(
        created_at=created_at,
        eval_run_id=f"skill-eval-{timestamp}-{digest}",
        used_skills=clean_skills,
        run_id=run_id.strip(),
        argv=tuple(sys.argv),
        cwd=Path.cwd().as_posix(),
        root=root.as_posix(),
        manifest=manifest.as_posix(),
        git_branch=git_output(root, "rev-parse", "--abbrev-ref", "HEAD"),
        git_commit=git_output(root, "rev-parse", "HEAD"),
        git_dirty="yes" if git_output(root, "status", "--short", "--untracked-files=all") else "no",
    )


def git_output(root: Path, *args: str) -> str:
    """Return one git command output, or '-' outside a usable git checkout."""
    try:
        result = subprocess.run(
            ("git", "-C", root.as_posix(), *args),
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "-"
    if result.returncode != 0:
        return "-"
    return result.stdout.strip() or "-"


def write_accumulated_report(request: AccumulatedReportRequest) -> Path:
    """Write one non-overwriting accumulated eval report."""
    status = eval_status(request.bundle.results, request.bundle.audit)
    output_dir = request.results_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / report_slug(
        request.bundle.manifest,
        request.bundle.metadata,
        status,
    )
    return write_report(ReportWriteRequest(path=str(report_path), root=request.root, bundle=request.bundle))


def resolve_results_dir(root: Path, value: str) -> Path:
    """Resolve the CLI results directory or the default archive location."""
    stripped = value.strip()
    if stripped:
        path = Path(stripped)
        return path if path.is_absolute() else root / path
    return eval_results_dir(agent_canon_root(root), DEFAULT_RESULTS_FAMILY)


def eval_status(results: tuple[ChecklistResult, ...], audit: ManifestAudit) -> str:
    """Return the aggregate prompt eval status."""
    prompt_checks_passed = all(result.passed or not result.critical for result in results)
    return "pass" if audit.passed and prompt_checks_passed else "fail"


def append_prompt_eval_monitoring(
    report_dir: Path,
    bundle: EvalRunBundle,
    accumulated_report: Path,
) -> Path:
    """Record accumulated prompt eval evidence in workflow monitoring."""
    metadata = bundle.metadata
    results = bundle.results
    audit = bundle.audit
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    critical_failed = sum(1 for result in results if result.critical and not result.passed)
    event = (
        "tool_call=evaluate_skill_workflow_prompts.py "
        f"prompt_eval={eval_status(results, audit)} "
        f"EVAL_STATUS={eval_status(results, audit)} "
        f"EVAL_RUN_ID={metadata.eval_run_id} "
        f"EVAL_USED_SKILLS={','.join(metadata.used_skills) or '-'} "
        f"EVAL_ACCUMULATED_REPORT={accumulated_report.as_posix()} "
        f"EVAL_CHECKS_TOTAL={total} "
        f"EVAL_CHECKS_PASSED={passed} "
        f"EVAL_CRITICAL_FAILED={critical_failed} "
        f"EVAL_AUDIT_STATUS={'pass' if audit.passed else 'fail'} "
        f"EVAL_GROWTH_CANDIDATES={audit.growth_candidates} "
        f"EVAL_GIT_BRANCH={metadata.git_branch} "
        f"EVAL_GIT_COMMIT={metadata.git_commit} "
        f"EVAL_GIT_DIRTY={metadata.git_dirty}"
    )
    return append_monitoring(
        report_dir,
        MonitoringEntries(behavior_events=(event,)),
    )


def run(args: argparse.Namespace) -> int:
    """Run prompt evals."""
    root = Path(str(args.root)).resolve()
    manifest_arg = Path(str(args.manifest))
    manifest = resolve_eval_manifest(root, manifest_arg)
    manifest_for_report = relative_manifest_path(root, manifest)
    evals, audit = load_manifest(manifest, root)
    results = tuple(result for eval_def in evals for result in evaluate_prompt(eval_def))
    metadata = build_eval_run_metadata(
        manifest_for_report,
        tuple(str(skill) for skill in args.skill_used),
        str(args.run_id),
        root,
    )
    bundle = EvalRunBundle(
        manifest=manifest_for_report,
        evals=evals,
        results=results,
        audit=audit,
        metadata=metadata,
    )
    accumulated_report: Path | None = None
    report_out: Path | None = None
    compact_out: Path | None = None
    if args.report_out:
        report_out = write_report(
            ReportWriteRequest(path=str(args.report_out), root=root, bundle=bundle)
        )
    if args.accumulate:
        accumulated_report = write_accumulated_report(
            AccumulatedReportRequest(
                root=root,
                results_dir=resolve_results_dir(root, str(args.results_dir)),
                bundle=bundle,
            )
        )
    if args.report_dir and accumulated_report is not None:
        append_prompt_eval_monitoring(
            Path(str(args.report_dir)),
            bundle,
            (
                relative_to_root(accumulated_report, root)
            ),
        )
    outputs = EvalOutputs(
        accumulated_report=(
            relative_to_root(accumulated_report, root).as_posix()
            if accumulated_report is not None
            else ""
        ),
        report_out=report_out.as_posix() if report_out is not None else "",
        compact_out=str(args.compact_out or ""),
    )
    if args.compact_out:
        compact_out = write_compact_summary(Path(str(args.compact_out)), bundle, outputs)
        outputs = EvalOutputs(
            accumulated_report=outputs.accumulated_report,
            report_out=outputs.report_out,
            compact_out=compact_out.as_posix(),
        )
    print(
        render_machine_status(
            bundle,
            outputs,
            include_details=compact_out is None,
        ),
        end="",
    )
    return 0 if eval_status(results, audit) == "pass" else 1


def relative_to_root(path: Path, root: Path) -> Path:
    """Return a root-relative path when possible."""
    return path.relative_to(root) if path.is_relative_to(root) else path


def main() -> int:
    """Run the CLI."""
    try:
        return run(build_parser().parse_args())
    except (OSError, ValueError) as exc:
        print(f"evaluate_skill_workflow_prompts.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
