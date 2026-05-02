#!/usr/bin/env python3
# @dependency-start
# responsibility Evaluates skill and workflow prompt surfaces against frozen prompt evals.
# upstream design ../../agents/evals/README.md prompt eval directory contract
# upstream design ../../agents/evals/skill_workflow_prompt_eval.toml default prompt eval manifest
# downstream implementation ../../tests/agent_tools/test_evaluate_skill_workflow_prompts.py tests it
# @dependency-end
"""Evaluate skill and workflow prompt surfaces against frozen checklist evals."""

from __future__ import annotations

import argparse
import glob
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]


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


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description="Evaluate skill and workflow prompt drift from a TOML manifest."
    )
    parser.add_argument(
        "--manifest",
        default="agents/evals/skill_workflow_prompt_eval.toml",
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
    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
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
    results: tuple[ChecklistResult, ...],
    audit: ManifestAudit,
) -> str:
    """Render machine-readable status."""
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
    ]
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


def render_markdown_report(
    manifest: Path,
    evals: tuple[PromptEval, ...],
    results: tuple[ChecklistResult, ...],
    audit: ManifestAudit,
) -> str:
    """Render a Markdown eval report."""
    by_eval = {eval_def.eval_id: eval_def for eval_def in evals}
    lines = [
        "# Skill Workflow Prompt Eval",
        "<!--",
        "@dependency-start",
        "responsibility Records skill/workflow prompt eval results.",
        "upstream implementation ../../tools/agent_tools/evaluate_skill_workflow_prompts.py "
        "generates this report",
        f"upstream design ../../{manifest.as_posix()} defines frozen evals",
        "@dependency-end",
        "-->",
        "",
        "## Summary",
        "",
    ]
    status_lines = render_machine_status(results, audit).strip().splitlines()
    lines.extend(f"- {line}" for line in status_lines[:10])
    lines.extend(["", "## Results", ""])
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


def write_report(
    path: str,
    manifest: Path,
    evals: tuple[PromptEval, ...],
    results: tuple[ChecklistResult, ...],
    audit: ManifestAudit,
) -> None:
    """Write a Markdown eval report."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_markdown_report(manifest, evals, results, audit),
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    """Run prompt evals."""
    root = Path(str(args.root)).resolve()
    manifest = (root / str(args.manifest)).resolve()
    evals, audit = load_manifest(manifest, root)
    results = tuple(result for eval_def in evals for result in evaluate_prompt(eval_def))
    if args.report_out:
        write_report(str(args.report_out), manifest.relative_to(root), evals, results, audit)
    print(render_machine_status(results, audit), end="")
    prompt_checks_passed = all(result.passed or not result.critical for result in results)
    return 0 if audit.passed and prompt_checks_passed else 1


def main() -> int:
    """Run the CLI."""
    try:
        return run(build_parser().parse_args())
    except (OSError, ValueError) as exc:
        print(f"evaluate_skill_workflow_prompts.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
