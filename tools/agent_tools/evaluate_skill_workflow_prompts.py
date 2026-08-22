#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Evaluates skill and workflow prompt surfaces against frozen prompt evals.
# upstream design ../../evidence/agent-evals/README.md prompt eval directory contract
# upstream design ../../evidence/agent-evals/skill_workflow_prompt_eval.toml default prompt eval manifest
# upstream implementation ./runtime_log_paths.py resolves accumulated eval archive paths
# upstream implementation ./runtime_artifacts.py owns external prompt-eval artifact writes
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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import cast

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from eval_manifest_paths import (
    eval_manifest_path,
    relative_manifest_path,
    resolve_eval_manifest,
)
from runtime_log_paths import agent_canon_root, eval_results_dir
from runtime_artifacts import RuntimeArtifactError, runtime_artifact_boundary

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
    canonical_target: Path | None
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
    runtime_root: Path | str | None = None


@dataclass(frozen=True)
class AccumulatedReportRequest:
    """Inputs for writing one accumulated eval report."""

    root: Path
    results_dir: Path
    bundle: EvalRunBundle
    runtime_root: Path | str | None = None


@dataclass(frozen=True)
class SkillEvaluatorReport:
    """One validated, parent-owned T14 evaluator observation."""

    raw_report_path: Path
    command: str
    artifacts: tuple[str, ...]
    authority: str
    route: str
    retry_count: int
    ambiguity: str
    extra_refs: tuple[str, ...]
    scenario_id: str
    iteration: int
    attempt: int
    provenance: str
    evaluation_status: str
    feedback_actions_resolved: str
    learning_capture_complete: str
    requirement_results: tuple[tuple[str, str, str], ...]


class SkillEvaluatorReportParseError(ValueError):
    """One fixed malformed T14 report error; never expose free-form traceback."""

    def __init__(self, code: str) -> None:
        """Bind the stable malformed-report code."""
        self.code = code
        super().__init__(code)


class T14EvaluationError(ValueError):
    """One fixed parent-accumulator error with a stable code attribute."""

    def __init__(self, code: str) -> None:
        """Bind the stable accumulator failure code."""
        self.code = code
        super().__init__(code)


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
        "--runtime-root",
        type=Path,
        help="Explicit external runtime root for reports and monitoring artifacts.",
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
                canonical_target=(
                    resolve_target(root, str(entry["canonical_target"]))
                    if entry.get("canonical_target") is not None
                    else None
                ),
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
    canonical_target = (
        resolve_target(root, str(entry["canonical_target"]))
        if entry.get("canonical_target") is not None
        else None
    )
    return tuple(
        PromptEval(
            eval_id=f"{eval_id}:{path.relative_to(root).as_posix()}",
            target=path,
            canonical_target=canonical_target,
            kind=kind,
            description=description,
            checklist=checklist,
        )
        for path in paths
    )


def resolve_target(root: Path, target: str) -> Path:
    """Resolve a prompt target in the selected source checkout."""
    return root / target


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


def evaluate_item(
    item: ChecklistItem,
    eval_def: PromptEval,
    required_text: str,
    forbidden_text: str,
) -> ChecklistResult:
    """Evaluate one checklist item against target text."""
    missing_required = tuple(
        pattern
        for pattern in item.required_regex
        if re.search(pattern, required_text, re.MULTILINE) is None
    )
    matched_forbidden = tuple(
        pattern for pattern in item.forbidden_regex if re.search(pattern, forbidden_text, re.MULTILINE)
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
    shim_text = eval_def.target.read_text(encoding="utf-8")
    required_text = shim_text
    if eval_def.canonical_target is not None:
        if not eval_def.canonical_target.is_file():
            return tuple(
                ChecklistResult(
                    eval_id=eval_def.eval_id,
                    item_id=item.item_id,
                    critical=item.critical,
                    passed=False,
                    description=f"missing canonical target: {eval_def.canonical_target}",
                    missing_required=("canonical-target-file",),
                    matched_forbidden=(),
                )
                for item in eval_def.checklist
            )
        required_text += "\n" + eval_def.canonical_target.read_text(encoding="utf-8")
    return tuple(
        evaluate_item(item, eval_def, required_text, shim_text)
        for item in eval_def.checklist
    )


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


def write_compact_summary(
    path: Path,
    bundle: EvalRunBundle,
    outputs: EvalOutputs,
    runtime_root: Path | str | None = None,
) -> Path:
    """Write a bounded JSON summary for agent consumption."""
    boundary = runtime_artifact_boundary(bundle.metadata.root and Path(bundle.metadata.root), runtime_root)
    return boundary.atomic_write_text(
        path,
        json.dumps(compact_summary(bundle, outputs), indent=2, sort_keys=True) + "\n",
    )


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
    boundary = runtime_artifact_boundary(request.root, request.runtime_root)
    return boundary.atomic_write_text(
        report_path,
        render_markdown_report(
            request.bundle,
            dependency_paths=report_dependency_paths(
                report_path,
                request.root,
                request.bundle.manifest,
            ),
        ),
    )


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
    now = datetime.now(timezone.utc)
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
    report_path = output_dir / report_slug(
        request.bundle.manifest,
        request.bundle.metadata,
        status,
    )
    return write_report(
        ReportWriteRequest(
            path=str(report_path),
            root=request.root,
            bundle=request.bundle,
            runtime_root=request.runtime_root,
        )
    )


def resolve_results_dir(
    root: Path,
    value: str,
    runtime_root: Path | str | None = None,
) -> Path:
    """Resolve the CLI results directory or the default archive location."""
    stripped = value.strip()
    if stripped:
        path = Path(stripped)
        if path.is_absolute():
            return path
        if runtime_root is not None:
            return runtime_artifact_boundary(root, runtime_root).resolve(path)
        return root / path
    return eval_results_dir(agent_canon_root(root), DEFAULT_RESULTS_FAMILY, runtime_root)


def eval_status(results: tuple[ChecklistResult, ...], audit: ManifestAudit) -> str:
    """Return the aggregate prompt eval status."""
    prompt_checks_passed = all(result.passed or not result.critical for result in results)
    return "pass" if audit.passed and prompt_checks_passed else "fail"


_T14_HEADINGS = (
    "Output:",
    "Requirement Results:",
    "Telemetry:",
    "Result Metadata:",
    "Evaluation Status:",
)
_T14_FIELDS = {
    "Output:": ("command", "artifacts", "authority", "route"),
    "Telemetry:": ("retry_count", "ambiguity", "extra_refs"),
    "Result Metadata:": ("scenario_id", "iteration", "provenance"),
    "Evaluation Status:": (
        "evaluation_status",
        "feedback_actions_resolved",
        "learning_capture_complete",
    ),
}
_T14_SCENARIOS = (
    "OOP-TYPE-SCENARIO-01",
    "OOP-TYPE-SCENARIO-02",
    "OOP-TYPE-SCENARIO-03",
)
_T14_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_T14_INTEGER_RE = re.compile(r"^[0-9]+$")
_T14_REF_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_T14_REQUIREMENT_RE = re.compile(r"^(R[0-9]+)=(pass|fail|malformed): ([^\r\n]+)$")
_T14_PARENT_HEADER = (
    "schema=agent_canon.t14.agent_evaluation.v1\n"
    "run_id={run_id}\n"
    "run_root=runtime-root/reports/agents/{run_id}/\n"
    "workspace_root=runtime-root/tmp/agentcanon-type-design-workspaces/{run_id}/\n"
    "raw_report_base=runtime-root/reports/agents/{run_id}/evaluator_artifacts/\n"
    "return_artifact_base=runtime-root/tmp/agentcanon-type-design-workspaces/{run_id}/\n"
    "iteration_count=2\n"
    "scenario_count=3\n"
)


def compute_t14_packet_digest(packet_path: Path) -> str:
    """Return the digest of one canonical, frozen T14 packet."""
    raw = packet_path.read_bytes()
    return _compute_t14_packet_digest_bytes(raw)


def _compute_t14_packet_digest_bytes(raw: bytes) -> str:
    """Return the T14 digest after the caller has receipt-read the bytes."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise T14EvaluationError("t14-packet-digest-mismatch") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("\ufeff") or not normalized.endswith("\n"):
        raise T14EvaluationError("t14-packet-digest-mismatch")
    lines = normalized[:-1].split("\n")
    if any(line != line.rstrip(" \t") for line in lines):
        raise T14EvaluationError("t14-packet-digest-mismatch")
    if normalized.endswith("\n\n"):
        raise T14EvaluationError("t14-packet-digest-mismatch")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _t14_parse_value(lines: str, field: str) -> str:
    """Parse one ordinary ``key=value`` field."""
    if lines.count("=") != 1:
        raise SkillEvaluatorReportParseError("t14-report-lexical-value")
    key, value = lines.split("=", 1)
    if key != field:
        expected = _T14_FIELDS.get(lines, ())
        if key in expected:
            raise SkillEvaluatorReportParseError("t14-report-field-order")
        raise SkillEvaluatorReportParseError("t14-report-unknown-field")
    if not value or re.fullmatch(r"[ -~]+", value) is None:
        raise SkillEvaluatorReportParseError("t14-report-lexical-value")
    if value != value.strip():
        raise SkillEvaluatorReportParseError("t14-report-lexical-value")
    return value


def _t14_parse_refs(value: str) -> tuple[str, ...]:
    """Parse the basename-only artifact/reference fields."""
    if value == "none":
        return ()
    refs = tuple(value.split(","))
    if not refs or any(_T14_REF_RE.fullmatch(ref) is None for ref in refs):
        raise SkillEvaluatorReportParseError("t14-report-lexical-value")
    return refs


def _t14_parse_blocks(text: str) -> dict[str, list[str]]:
    """Parse exact headings and field blocks without accepting free text."""
    if text.startswith("\ufeff") or not text.endswith("\n"):
        raise SkillEvaluatorReportParseError("t14-report-lexical-value")
    body = text[:-1]
    if not body or body.startswith("\n") or body.endswith("\n"):
        raise SkillEvaluatorReportParseError("t14-report-free-text")
    lines = body.split("\n")
    cursor = 0
    blocks: dict[str, list[str]] = {}
    for heading_index, heading in enumerate(_T14_HEADINGS):
        if cursor >= len(lines) or lines[cursor] != heading:
            raise SkillEvaluatorReportParseError("t14-report-heading")
        if heading in blocks:
            raise SkillEvaluatorReportParseError("t14-report-heading")
        blocks[heading] = []
        cursor += 1
        while cursor < len(lines) and lines[cursor] not in _T14_HEADINGS:
            line = lines[cursor]
            if line == "":
                if cursor + 1 >= len(lines) or lines[cursor + 1] not in _T14_HEADINGS:
                    raise SkillEvaluatorReportParseError("t14-report-free-text")
                cursor += 1
                break
            if line != line.rstrip(" \t"):
                raise SkillEvaluatorReportParseError("t14-report-lexical-value")
            blocks[heading].append(line)
            cursor += 1
        if heading_index < len(_T14_HEADINGS) - 1:
            if cursor >= len(lines) or lines[cursor] != _T14_HEADINGS[heading_index + 1]:
                raise SkillEvaluatorReportParseError("t14-report-heading")
    if cursor != len(lines):
        raise SkillEvaluatorReportParseError("t14-report-free-text")
    return blocks


def _t14_parse_ordinary_block(heading: str, lines: list[str]) -> dict[str, str]:
    """Validate one fixed ordinary-field block."""
    expected = _T14_FIELDS[heading]
    values: dict[str, str] = {}
    for line in lines:
        if line.count("=") != 1:
            if "=" not in line:
                raise SkillEvaluatorReportParseError("t14-report-free-text")
            raise SkillEvaluatorReportParseError("t14-report-lexical-value")
        key = line.split("=", 1)[0]
        if key not in expected:
            raise SkillEvaluatorReportParseError("t14-report-unknown-field")
        if key in values:
            raise SkillEvaluatorReportParseError("t14-report-duplicate-field")
        if len(values) != expected.index(key):
            raise SkillEvaluatorReportParseError("t14-report-field-order")
        values[key] = _t14_parse_value(line, key)
    if len(values) != len(expected):
        raise SkillEvaluatorReportParseError("t14-report-missing-field")
    return values


def parse_skill_evaluator_report(
    raw_evaluator_report: Path,
    expected_raw_evaluator_report: Path,
    expected_requirement_ids: Sequence[str],
    expected_scenario_id: str,
    expected_iteration: int,
    expected_attempt: int,
    *,
    raw_bytes: bytes | None = None,
) -> SkillEvaluatorReport:
    """Parse one exact five-section, parent-owned T14 evaluator report."""
    if raw_evaluator_report != expected_raw_evaluator_report:
        raise SkillEvaluatorReportParseError("t14-report-path-mismatch")
    if (
        raw_evaluator_report.parent.name != f"attempt-{expected_attempt}"
        or raw_evaluator_report.parent.parent.name != f"iteration-{expected_iteration}"
    ):
        if raw_evaluator_report.parent.name != f"attempt-{expected_attempt}":
            raise SkillEvaluatorReportParseError("t14-report-attempt-path-mismatch")
        raise SkillEvaluatorReportParseError("t14-report-iteration-path-mismatch")
    if raw_evaluator_report.stem != expected_scenario_id:
        raise SkillEvaluatorReportParseError("t14-report-path-mismatch")
    if raw_bytes is None:
        raw_bytes = raw_evaluator_report.read_bytes()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillEvaluatorReportParseError("t14-report-invalid-utf8") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = _t14_parse_blocks(normalized)
    output = _t14_parse_ordinary_block("Output:", blocks["Output:"])
    telemetry = _t14_parse_ordinary_block("Telemetry:", blocks["Telemetry:"])
    metadata = _t14_parse_ordinary_block("Result Metadata:", blocks["Result Metadata:"])
    status = _t14_parse_ordinary_block("Evaluation Status:", blocks["Evaluation Status:"])

    requirement_results: list[tuple[str, str, str]] = []
    seen_ids: set[str] = set()
    expected_ids = tuple(expected_requirement_ids)
    for line in blocks["Requirement Results:"]:
        match = _T14_REQUIREMENT_RE.fullmatch(line)
        if match is None:
            raise SkillEvaluatorReportParseError("t14-report-requirement-id")
        requirement_id, result_status, evidence = match.groups()
        if requirement_id in seen_ids or requirement_id not in expected_ids:
            raise SkillEvaluatorReportParseError("t14-report-requirement-id")
        seen_ids.add(requirement_id)
        requirement_results.append((requirement_id, result_status, evidence))
    if set(seen_ids) != set(expected_ids) or len(requirement_results) != len(expected_ids):
        raise SkillEvaluatorReportParseError("t14-report-requirement-id")
    if tuple(row[0] for row in requirement_results) != expected_ids:
        raise SkillEvaluatorReportParseError("t14-report-requirement-id")

    retry_count = telemetry["retry_count"]
    iteration = metadata["iteration"]
    if _T14_INTEGER_RE.fullmatch(retry_count) is None or _T14_INTEGER_RE.fullmatch(iteration) is None:
        raise SkillEvaluatorReportParseError("t14-report-metadata")
    parsed_iteration = int(iteration)
    if parsed_iteration != expected_iteration or metadata["scenario_id"] != expected_scenario_id:
        raise SkillEvaluatorReportParseError("t14-report-metadata")
    if telemetry["ambiguity"] not in {"none", "token"}:
        raise SkillEvaluatorReportParseError("t14-report-enum")
    if metadata["provenance"] != "fresh":
        raise SkillEvaluatorReportParseError("t14-report-enum")
    if status["evaluation_status"] not in {"pass", "fail"}:
        raise SkillEvaluatorReportParseError("t14-report-enum")
    if status["feedback_actions_resolved"] != "no" or status["learning_capture_complete"] != "no":
        raise SkillEvaluatorReportParseError("t14-report-enum")
    if not output["command"] or not output["authority"] or not output["route"]:
        raise SkillEvaluatorReportParseError("t14-report-metadata")
    return SkillEvaluatorReport(
        raw_report_path=raw_evaluator_report,
        command=output["command"],
        artifacts=_t14_parse_refs(output["artifacts"]),
        authority=output["authority"],
        route=output["route"],
        retry_count=int(retry_count),
        ambiguity=telemetry["ambiguity"],
        extra_refs=_t14_parse_refs(telemetry["extra_refs"]),
        scenario_id=metadata["scenario_id"],
        iteration=parsed_iteration,
        attempt=expected_attempt,
        provenance=metadata["provenance"],
        evaluation_status=status["evaluation_status"],
        feedback_actions_resolved=status["feedback_actions_resolved"],
        learning_capture_complete=status["learning_capture_complete"],
        requirement_results=tuple(requirement_results),
    )


def _t14_parent_blocks(text: str) -> list[dict[str, str]]:
    """Read scenario blocks from the parent evaluation without rewriting them."""
    blocks: list[dict[str, str]] = []
    marker = "## Scenario "
    for chunk in text.split(marker)[1:]:
        lines = chunk.splitlines()
        if not lines:
            continue
        values: dict[str, str] = {"scenario_id": lines[0].strip()}
        for line in lines[1:]:
            if line.startswith("## "):
                break
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        blocks.append(values)
    return blocks


def _t14_summary_blocks(text: str) -> list[dict[str, str]]:
    """Read iteration summaries from the parent evaluation."""
    summaries: list[dict[str, str]] = []
    marker = "## Iteration "
    for chunk in text.split(marker)[1:]:
        lines = chunk.splitlines()
        if not lines or not lines[0].endswith(" Summary"):
            continue
        values: dict[str, str] = {}
        match = re.fullmatch(r"([0-9]+) Summary", lines[0])
        if match is None:
            continue
        values["iteration"] = match.group(1)
        for line in lines[1:]:
            if line.startswith("## "):
                break
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        summaries.append(values)
    return summaries


def _t14_parent_text(
    parent_evaluation: Path,
    run_id: str,
    *,
    parent_bytes: bytes | None,
    parent_present: bool,
) -> str:
    """Return an existing parent file or the exact initial header."""
    if not parent_present:
        return _T14_PARENT_HEADER.format(run_id=run_id) + "\n"
    if parent_bytes is None:
        raise T14EvaluationError("t14-iteration-order")
    try:
        text = parent_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise T14EvaluationError("t14-iteration-order") from exc
    header = _T14_PARENT_HEADER.format(run_id=run_id)
    if not text.startswith(header):
        raise T14EvaluationError("t14-iteration-order")
    return text


def _t14_relative_raw_path(raw_report: Path, parent_evaluation: Path) -> str:
    """Render a raw report path relative to the parent run root."""
    try:
        return raw_report.relative_to(parent_evaluation.parent).as_posix()
    except ValueError as exc:
        raise T14EvaluationError("t14-raw-report-exists") from exc


def _t14_validate_effective_retry_counts(text: str) -> None:
    """Reject an already-persisted retry arithmetic contradiction."""
    for block in _t14_parent_blocks(text):
        if not {"retry_count", "malformed_attempts", "evaluator_retry_count"}.issubset(block):
            continue
        try:
            retry_count = int(block["retry_count"])
            malformed = int(block["malformed_attempts"])
            evaluator = int(block["evaluator_retry_count"])
        except ValueError as exc:
            raise T14EvaluationError("t14-retry-count-mismatch") from exc
        if retry_count != malformed + evaluator:
            raise T14EvaluationError("t14-retry-count-mismatch")


def _t14_validate_record_order(
    text: str,
    expected_scenario_id: str,
    expected_iteration: int,
) -> None:
    """Validate the fixed two-iteration, three-scenario append order."""
    blocks = _t14_parent_blocks(text)
    if any(block.get("scenario_id") == expected_scenario_id for block in blocks):
        raise T14EvaluationError("t14-duplicate-scenario")
    expected_index = len(blocks)
    expected_round = expected_index // len(_T14_SCENARIOS) + 1
    if expected_iteration != expected_round:
        raise T14EvaluationError(
            "t14-unexpected-iteration" if expected_iteration not in {1, 2} else "t14-iteration-order"
        )
    expected_scenario = _T14_SCENARIOS[expected_index % len(_T14_SCENARIOS)]
    if expected_scenario_id != expected_scenario:
        raise T14EvaluationError("t14-iteration-order")


def _t14_runtime_boundary(runtime_root: Path | str | None = None):
    """Return the explicit external runtime boundary for T14 artifacts."""
    return runtime_artifact_boundary(Path.cwd(), runtime_root)


def _t14_return_artifact(boundary, run_id: str, iteration: int, attempt: int, scenario_id: str) -> Path:
    """Return the evaluator-return receipt path inside the runtime root."""
    return boundary.resolve(
        Path("tmp")
        / "agentcanon-type-design-workspaces"
        / run_id
        / f"iteration-{iteration}"
        / f"attempt-{attempt}"
        / scenario_id
        / "evaluator_return.bin"
    )


def record_t14_evaluation(
    run_id: str,
    evaluator_bytes: bytes,
    raw_evaluator_report: Path,
    expected_raw_evaluator_report: Path,
    expected_requirement_ids: Sequence[str],
    expected_scenario_id: str,
    expected_iteration: int,
    expected_attempt: int,
    scenario_packet: Path,
    expected_packet_digest: str,
    parent_evaluation: Path,
    runtime_root: Path | str | None = None,
) -> SkillEvaluatorReport:
    """Persist and parse one fresh evaluator return, then append its observation."""
    if _T14_RUN_ID_RE.fullmatch(run_id) is None:
        raise T14EvaluationError("t14-iteration-order")
    if expected_iteration not in {1, 2} or expected_attempt < 0:
        raise T14EvaluationError("t14-unexpected-iteration")
    if raw_evaluator_report != expected_raw_evaluator_report:
        raise T14EvaluationError("t14-raw-report-exists")
    boundary = _t14_runtime_boundary(runtime_root)
    parent_path = boundary.resolve(parent_evaluation)
    raw_path = boundary.resolve(raw_evaluator_report)
    expected_raw_path = boundary.resolve(expected_raw_evaluator_report)
    packet_path = boundary.resolve(scenario_packet)
    return_path = _t14_return_artifact(
        boundary, run_id, expected_iteration, expected_attempt, expected_scenario_id
    )
    if expected_attempt > 0:
        prior = (
            raw_evaluator_report.parent.parent
            / f"attempt-{expected_attempt - 1}"
            / raw_evaluator_report.name
        )
        prior_path = boundary.resolve(prior)

    parent_exists = parent_path.is_file()
    parent_bytes = parent_path.read_bytes() if parent_exists else None
    scenario_bytes = packet_path.read_bytes() if packet_path.is_file() else None
    return_bytes = return_path.read_bytes() if return_path.is_file() else None
    prior_exists = expected_attempt > 0 and prior_path.is_file()
    parent_text = _t14_parent_text(
        parent_evaluation,
        run_id,
        parent_bytes=parent_bytes,
        parent_present=parent_exists,
    )
    _t14_validate_effective_retry_counts(parent_text)
    _t14_validate_record_order(parent_text, expected_scenario_id, expected_iteration)
    if raw_path.exists():
        raise T14EvaluationError("t14-raw-report-exists")
    if expected_raw_path.exists():
        raise T14EvaluationError("t14-raw-report-exists")
    if expected_attempt > 0 and not prior_exists:
        raise T14EvaluationError("t14-attempt-order")
    if scenario_bytes is None:
        raise T14EvaluationError("t14-packet-digest-mismatch")
    actual_digest = _compute_t14_packet_digest_bytes(scenario_bytes)
    if actual_digest != expected_packet_digest:
        raise T14EvaluationError("t14-packet-digest-mismatch")
    if return_bytes is None or return_bytes != evaluator_bytes:
        raise T14EvaluationError("t14-report-failure")
    try:
        published_raw_path = boundary.atomic_write_bytes(raw_path, evaluator_bytes)
    except OSError as exc:
        raise T14EvaluationError("t14-raw-report-exists") from exc
    report = parse_skill_evaluator_report(
        published_raw_path,
        expected_raw_path,
        expected_requirement_ids,
        expected_scenario_id,
        expected_iteration,
        expected_attempt,
        raw_bytes=published_raw_path.read_bytes(),
    )
    relative_raw = _t14_relative_raw_path(raw_evaluator_report, parent_evaluation)
    effective_retry = expected_attempt + report.retry_count
    block = (
        f"## Scenario {report.scenario_id}\n"
        f"iteration={report.iteration}\n"
        f"attempt={report.attempt}\n"
        f"scenario_id={report.scenario_id}\n"
        f"packet_digest={actual_digest}\n"
        f"raw_report={relative_raw}\n"
        f"retry_count={effective_retry}\n"
        f"malformed_attempts={expected_attempt}\n"
        f"evaluator_retry_count={report.retry_count}\n"
        f"ambiguity={report.ambiguity}\n"
        f"provenance={report.provenance}\n"
        f"evaluation_status={report.evaluation_status}\n"
        "requirement_results="
        + ";".join(f"{requirement_id}:{result_status}" for requirement_id, result_status, _ in report.requirement_results)
        + "\nparser_status=pass\n"
    )
    payload = (parent_text + ("\n" if parent_exists else "") + block).encode("utf-8")
    if parent_exists:
        boundary.append_bytes(parent_path, payload[len(parent_text.encode("utf-8")) :])
    else:
        boundary.atomic_write_bytes(parent_path, payload)
    return report


def _t14_decimal(value: Decimal) -> Decimal:
    """Parse one finite decimal and enforce the inclusive 0..100 range."""
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise T14EvaluationError("t14-score-out-of-range") from exc
    if not decimal_value.is_finite() or decimal_value < Decimal("0") or decimal_value > Decimal("100"):
        raise T14EvaluationError("t14-score-out-of-range")
    return decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _t14_summary_line_values(
    iteration: int,
    scenario_reports: Sequence[SkillEvaluatorReport],
    graph_check_status: Mapping[str, bool],
    parent_score: Decimal,
    parent_critical_pass: bool,
    holdout_gap: Decimal,
) -> str:
    """Serialize one complete structural T14 iteration summary."""
    retry_counts = ";".join(
        f"{report.scenario_id}:{report.attempt + report.retry_count}" for report in scenario_reports
    )
    ambiguities = ";".join(f"{report.scenario_id}:{report.ambiguity}" for report in scenario_reports)
    provenance = ";".join(f"{report.scenario_id}:{report.provenance}" for report in scenario_reports)
    graph_checks = ";".join(
        f"{report.scenario_id}:{'pass' if graph_check_status[report.scenario_id] else 'fail'}"
        for report in scenario_reports
    )
    all_reports_pass = all(
        report.evaluation_status == "pass"
        and report.ambiguity == "none"
        and report.provenance == "fresh"
        and all(status == "pass" for _, status, _ in report.requirement_results)
        for report in scenario_reports
    )
    all_graphs_pass = all(graph_check_status[report.scenario_id] for report in scenario_reports)
    if all_reports_pass and all_graphs_pass and parent_critical_pass:
        convergence = "converged"
        reason = "none"
    elif not all_reports_pass:
        convergence = "not_converged"
        reason = "t14-report-failure"
        if any(report.ambiguity != "none" for report in scenario_reports):
            reason = "t14-ambiguity"
    elif not all_graphs_pass:
        convergence = "not_converged"
        reason = "t14-graph-failure"
    else:
        convergence = "not_converged"
        reason = "t14-critical-failure"
    return (
        f"## Iteration {iteration} Summary\n"
        f"iteration={iteration}\n"
        f"parent_score_percent={parent_score:.2f}\n"
        f"parent_critical_pass={'yes' if parent_critical_pass else 'no'}\n"
        f"holdout_gap_percent={holdout_gap:.2f}\n"
        f"retry_counts={retry_counts}\n"
        f"ambiguities={ambiguities}\n"
        f"provenance={provenance}\n"
        f"graph_checks={graph_checks}\n"
        f"convergence={convergence}\n"
        f"convergence_reason={reason}\n"
    )


def append_t14_iteration_summary(
    parent_evaluation: Path,
    iteration: int,
    scenario_reports: Sequence[SkillEvaluatorReport],
    graph_check_status: Mapping[str, bool],
    parent_score_percent: Decimal,
    parent_critical_pass: bool,
    holdout_gap_percent: Decimal,
    runtime_root: Path | str | None = None,
) -> None:
    """Append exactly one deterministic summary for one completed iteration."""
    if iteration not in {1, 2}:
        raise T14EvaluationError("t14-iteration-order")
    boundary = _t14_runtime_boundary(runtime_root)
    parent_path = boundary.resolve(parent_evaluation)
    try:
        text = parent_path.read_bytes().decode("utf-8")
    except FileNotFoundError as exc:
        raise T14EvaluationError("t14-iteration-order") from exc
    summaries = _t14_summary_blocks(text)
    if any(summary.get("iteration") == str(iteration) for summary in summaries):
        raise T14EvaluationError("t14-duplicate-summary")
    if iteration != len(summaries) + 1:
        raise T14EvaluationError("t14-iteration-order")
    reports = tuple(scenario_reports)
    complete_structure = (
        len(reports) == len(_T14_SCENARIOS)
        and tuple(report.scenario_id for report in reports) == _T14_SCENARIOS
        and all(report.iteration == iteration for report in reports)
        and set(graph_check_status) == set(_T14_SCENARIOS)
    )
    try:
        score = _t14_decimal(parent_score_percent)
        gap = _t14_decimal(holdout_gap_percent)
    except T14EvaluationError:
        score = Decimal("0")
        gap = Decimal("0")
        complete_structure = False
        blocked_reason = "t14-score-out-of-range"
    else:
        blocked_reason = "t14-incomplete-iteration"
    if not complete_structure:
        updated = (
            text.rstrip("\n")
            + "\n\n"
            + (
                f"## Iteration {iteration} Summary\n"
                f"iteration={iteration}\n"
                "parent_score_percent=unscored\n"
                "parent_critical_pass=unknown\n"
                "holdout_gap_percent=unscored\n"
                "retry_counts=none\n"
                "ambiguities=none\n"
                "provenance=none\n"
                "graph_checks=none\n"
                "convergence=blocked\n"
                f"convergence_reason={blocked_reason}\n"
            )
        )
    else:
        summary = _t14_summary_line_values(
            iteration,
            reports,
            graph_check_status,
            score,
            parent_critical_pass,
            gap,
        )
        updated = text.rstrip("\n") + "\n\n" + summary
    suffix = updated[len(text) :]
    boundary.append_bytes(parent_path, suffix.encode("utf-8"))


def _t14_summary_map(text: str) -> dict[int, dict[str, str]]:
    """Return iteration summaries keyed by iteration number."""
    result: dict[int, dict[str, str]] = {}
    for summary in _t14_summary_blocks(text):
        try:
            iteration = int(summary["iteration"])
        except (KeyError, ValueError):
            continue
        result[iteration] = summary
    return result


def _t14_failure_code_for_summaries(summaries: Mapping[int, Mapping[str, str]]) -> str:
    """Apply the fixed finalization failure precedence."""
    if len(summaries) != 2 or 1 not in summaries or 2 not in summaries:
        return "t14-incomplete-iteration"
    for summary in summaries.values():
        convergence = summary.get("convergence")
        reason = summary.get("convergence_reason")
        if convergence == "blocked" and reason == "t14-score-out-of-range":
            return "t14-score-out-of-range"
    if any(summary.get("convergence") == "blocked" for summary in summaries.values()):
        return "t14-incomplete-iteration"
    if any(summary.get("convergence") == "not_converged" for summary in summaries.values()):
        return "t14-iteration-not-converged"
    retry_values = [summary.get("retry_counts", "") for summary in summaries.values()]
    if len(set(retry_values)) != 1:
        return "t14-retry-mismatch"
    if any(value != "none" and any(part.split(":", 1)[-1] != "0" for part in value.split(";")) for value in retry_values):
        return "t14-nonzero-retry"
    for summary in summaries.values():
        try:
            gaps = [Decimal(part) for part in summary.get("holdout_gap_percent", "unscored").split(";")]
        except InvalidOperation:
            return "t14-holdout-gap"
        if not gaps or any(gap >= Decimal("15.00") for gap in gaps):
            return "t14-holdout-gap"
    return "none"


def finalize_t14_evaluation(
    parent_evaluation: Path,
    runtime_root: Path | str | None = None,
) -> None:
    """Append the sole final parent summary after the two iteration summaries."""
    boundary = _t14_runtime_boundary(runtime_root)
    parent_path = boundary.resolve(parent_evaluation)
    try:
        text = parent_path.read_bytes().decode("utf-8")
    except FileNotFoundError as exc:
        raise T14EvaluationError("t14-iteration-order") from exc
    if "## Parent Summary" in text:
        raise T14EvaluationError("t14-duplicate-summary")
    summaries = _t14_summary_map(text)
    failure_code = _t14_failure_code_for_summaries(summaries)
    converged = sum(1 for summary in summaries.values() if summary.get("convergence") == "converged")
    second = summaries.get(2, {})
    score = second.get("parent_score_percent", "unscored")
    critical = second.get("parent_critical_pass", "unknown")
    if failure_code == "none" and critical != "yes":
        failure_code = "t14-retry-mismatch"
    completion = "complete" if failure_code == "none" else "incomplete"
    block = (
        "## Parent Summary\n"
        f"consecutive_converged_iterations={converged}\n"
        f"parent_score_percent={score}\n"
        f"parent_critical_pass={critical}\n"
        f"completion={completion}\n"
        f"failure_code={failure_code}\n"
    )
    updated = text.rstrip("\n") + "\n\n" + block
    suffix = updated[len(text) :]
    boundary.append_bytes(parent_path, suffix.encode("utf-8"))


def append_prompt_eval_monitoring(
    report_dir: Path,
    bundle: EvalRunBundle,
    accumulated_report: Path,
    runtime_root: Path | str | None = None,
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
    boundary = runtime_artifact_boundary(Path(bundle.metadata.root), runtime_root)
    monitoring_path = boundary.resolve(report_dir) / "workflow_monitoring.md"
    existing = monitoring_path.read_text(encoding="utf-8") if monitoring_path.is_file() else (
        "# Workflow Monitoring\n\n## Behavior Events\n\n"
    )
    marker = "## Behavior Events"
    if marker not in existing:
        existing = existing.rstrip() + f"\n\n{marker}\n\n"
    updated = existing.rstrip() + "\n\n- " + event + "\n"
    return boundary.atomic_write_text(monitoring_path, updated)


def run(args: argparse.Namespace) -> int:
    """Run prompt evals."""
    root = Path(str(args.root)).resolve()
    boundary = (
        runtime_artifact_boundary(root, args.runtime_root)
        if args.report_out or args.compact_out or args.accumulate or args.report_dir
        else None
    )
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
        assert boundary is not None
        report_out = write_report(
            ReportWriteRequest(
                path=str(args.report_out),
                root=root,
                bundle=bundle,
                runtime_root=boundary.root,
            )
        )
    if args.accumulate:
        assert boundary is not None
        accumulated_report = write_accumulated_report(
            AccumulatedReportRequest(
                root=root,
                results_dir=resolve_results_dir(root, str(args.results_dir), boundary.root),
                bundle=bundle,
                runtime_root=boundary.root,
            )
        )
    if args.report_dir and accumulated_report is not None:
        append_prompt_eval_monitoring(
            Path(str(args.report_dir)),
            bundle,
            (
                accumulated_report
            ),
            boundary.root,
        )
    outputs = EvalOutputs(
        accumulated_report=(
            accumulated_report.as_posix()
            if accumulated_report is not None
            else ""
        ),
        report_out=report_out.as_posix() if report_out is not None else "",
        compact_out=str(args.compact_out or ""),
    )
    if args.compact_out:
        compact_out = write_compact_summary(
            Path(str(args.compact_out)), bundle, outputs, boundary.root
        )
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
    except RuntimeArtifactError as exc:
        print(f"evaluate_skill_workflow_prompts.py: runtime_root_required: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"evaluate_skill_workflow_prompts.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
