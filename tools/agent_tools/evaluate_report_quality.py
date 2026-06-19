#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Evaluates report-writing quality checklist surfaces.
# upstream design ../../evidence/agent-evals/README.md eval usage contract
# upstream design ../../evidence/agent-evals/report_quality_eval.toml report quality eval manifest
# upstream design ../../agents/skills/report-writing.md report writing skill contract
# upstream implementation ./runtime_log_paths.py resolves accumulated eval archive paths
# downstream implementation ../../tests/agent_tools/test_evaluate_report_quality.py tests report quality eval behavior
# @dependency-end
"""Evaluate report-writing quality checklist surfaces."""

from __future__ import annotations

import argparse
import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
import tomllib

from eval_manifest_paths import eval_manifest_path, resolve_eval_manifest
from runtime_log_paths import agent_canon_root, eval_results_dir

DEFAULT_MANIFEST = eval_manifest_path("report_quality_eval.toml")
DEFAULT_RESULTS_FAMILY = "report-quality"
RUN_ID_DIGEST_LENGTH = 10


@dataclass(frozen=True)
class QualityChecklistItem:
    """One report quality checklist item."""

    item_id: str
    critical: bool
    description: str
    required_regex: tuple[str, ...]
    forbidden_regex: tuple[str, ...]


@dataclass(frozen=True)
class QualityEval:
    """One report quality eval target."""

    eval_id: str
    target: Path
    description: str
    checklist: tuple[QualityChecklistItem, ...]


@dataclass(frozen=True)
class QualityChecklistResult:
    """One report quality checklist result."""

    eval_id: str
    target: Path
    item_id: str
    critical: bool
    description: str
    missing_required: tuple[str, ...]
    matched_forbidden: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return whether the checklist item passed."""
        return not self.missing_required and not self.matched_forbidden


@dataclass(frozen=True)
class ReportQualityBundle:
    """All report quality eval data for one run."""

    run_id: str
    status: str
    root: Path
    manifest: Path
    evals: tuple[QualityEval, ...]
    results: tuple[QualityChecklistResult, ...]

    @property
    def failed_count(self) -> int:
        """Return failed checklist count."""
        return sum(1 for result in self.results if not result.passed)

    @property
    def critical_failed_count(self) -> int:
        """Return failed critical checklist count."""
        return sum(1 for result in self.results if result.critical and not result.passed)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--report-out", default="")
    parser.add_argument("--accumulate", action="store_true")
    parser.add_argument(
        "--results-dir",
        default="",
        help=(
            "Directory for accumulated reports. Defaults to the mounted "
            "AgentCanon log archive eval-results/report-quality path, falling "
            "back to the legacy in-tree path only when no archive is mounted."
        ),
    )
    return parser


def string_list(value: object, field: str) -> tuple[str, ...]:
    """Return a tuple of strings from a TOML list."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{field} must be a list of strings")
    return tuple(cast(list[str], items))


def load_checklist_item(raw_item: object, eval_id: str) -> QualityChecklistItem:
    """Load one checklist item."""
    if not isinstance(raw_item, dict):
        raise ValueError(f"eval {eval_id} checklist item must be a table")
    item = cast(dict[str, object], raw_item)
    item_id = str(item.get("id") or "").strip()
    if not item_id:
        raise ValueError(f"eval {eval_id} checklist item must define id")
    required_regex = string_list(item.get("required_regex"), f"{eval_id}.{item_id}.required_regex")
    forbidden_regex = string_list(item.get("forbidden_regex"), f"{eval_id}.{item_id}.forbidden_regex")
    if not required_regex and not forbidden_regex:
        raise ValueError(f"eval {eval_id} checklist item {item_id} must define regex checks")
    return QualityChecklistItem(
        item_id=item_id,
        critical=bool(item.get("critical", True)),
        description=str(item.get("description") or ""),
        required_regex=required_regex,
        forbidden_regex=forbidden_regex,
    )


def load_manifest(path: Path, root: Path) -> tuple[QualityEval, ...]:
    """Load report quality eval targets."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw_evals = data.get("evals")
    if not isinstance(raw_evals, list) or not raw_evals:
        raise ValueError("manifest must define at least one [[evals]] entry")
    evals: list[QualityEval] = []
    seen_eval_ids: set[str] = set()
    seen_targets: set[str] = set()
    for index, raw_eval in enumerate(cast(list[object], raw_evals), start=1):
        evals.append(load_eval_entry(raw_eval, index, root, seen_eval_ids, seen_targets))
    return tuple(evals)


def load_eval_entry(
    raw_eval: object,
    index: int,
    root: Path,
    seen_eval_ids: set[str],
    seen_targets: set[str],
) -> QualityEval:
    """Load one report quality eval entry."""
    entry = raw_eval_table(raw_eval, index)
    eval_id = read_eval_id(entry, index)
    if eval_id in seen_eval_ids:
        raise ValueError(f"duplicate eval id: {eval_id}")
    seen_eval_ids.add(eval_id)
    target = read_target(entry, eval_id)
    if target in seen_targets:
        raise ValueError(f"duplicate eval target: {target}")
    seen_targets.add(target)
    target_path = validated_target_path(root, eval_id, target)
    checklist = load_eval_checklist(entry, eval_id)
    return QualityEval(
        eval_id=eval_id,
        target=target_path,
        description=str(entry.get("description") or ""),
        checklist=checklist,
    )


def raw_eval_table(raw_eval: object, index: int) -> dict[str, object]:
    """Return a TOML eval table."""
    if not isinstance(raw_eval, dict):
        raise ValueError(f"eval {index} must be a table")
    return cast(dict[str, object], raw_eval)


def read_eval_id(entry: dict[str, object], index: int) -> str:
    """Return the eval id from one entry."""
    eval_id = str(entry.get("id") or "").strip()
    if not eval_id:
        raise ValueError(f"eval {index} must define id")
    return eval_id


def read_target(entry: dict[str, object], eval_id: str) -> str:
    """Return the target string from one entry."""
    target = str(entry.get("target") or "").strip()
    if not target:
        raise ValueError(f"eval {eval_id} must define target")
    return target


def validated_target_path(root: Path, eval_id: str, target: str) -> Path:
    """Return an existing target path."""
    target_path = root / target
    if not target_path.is_file():
        raise ValueError(f"eval {eval_id} target missing: {target}")
    return target_path


def load_eval_checklist(entry: dict[str, object], eval_id: str) -> tuple[QualityChecklistItem, ...]:
    """Load and validate checklist items for one eval."""
    raw_checklist = entry.get("checklist")
    if not isinstance(raw_checklist, list) or not raw_checklist:
        raise ValueError(f"eval {eval_id} must define checklist items")
    checklist = tuple(load_checklist_item(item, eval_id) for item in cast(list[object], raw_checklist))
    duplicate_items = duplicate_ids(tuple(item.item_id for item in checklist))
    if duplicate_items:
        raise ValueError(f"eval {eval_id} duplicate checklist ids: {', '.join(duplicate_items)}")
    return checklist


def duplicate_ids(values: Sequence[str]) -> tuple[str, ...]:
    """Return duplicate identifiers in stable order."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return tuple(duplicates)


def evaluate_item(report_eval: QualityEval, item: QualityChecklistItem, text: str) -> QualityChecklistResult:
    """Evaluate one checklist item against target text."""
    return QualityChecklistResult(
        eval_id=report_eval.eval_id,
        target=report_eval.target,
        item_id=item.item_id,
        critical=item.critical,
        description=item.description,
        missing_required=tuple(pattern for pattern in item.required_regex if re.search(pattern, text) is None),
        matched_forbidden=tuple(pattern for pattern in item.forbidden_regex if re.search(pattern, text) is not None),
    )


def evaluate(root: Path, manifest: Path) -> ReportQualityBundle:
    """Evaluate one report quality manifest."""
    resolved_root = root.resolve()
    resolved_manifest = resolve_eval_manifest(resolved_root, manifest).resolve()
    evals = load_manifest(resolved_manifest, resolved_root)
    results: list[QualityChecklistResult] = []
    for report_eval in evals:
        text = report_eval.target.read_text(encoding="utf-8")
        results.extend(evaluate_item(report_eval, item, text) for item in report_eval.checklist)
    result_tuple = tuple(results)
    status = "pass" if all(result.passed or not result.critical for result in result_tuple) else "fail"
    return ReportQualityBundle(
        run_id=run_id_for(resolved_manifest, result_tuple),
        status=status,
        root=resolved_root,
        manifest=resolved_manifest,
        evals=evals,
        results=result_tuple,
    )


def run_id_for(manifest: Path, results: tuple[QualityChecklistResult, ...]) -> str:
    """Return a unique report quality eval run id."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    digest_source = "\n".join(
        [
            manifest.as_posix(),
            *(f"{item.eval_id}:{item.item_id}:{item.passed}" for item in results),
            timestamp,
        ]
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:RUN_ID_DIGEST_LENGTH]
    return f"report-quality-eval-{timestamp}-{digest}"


def render_report(bundle: ReportQualityBundle) -> str:
    """Render a bounded Markdown report quality eval report."""
    lines = [
        "# Report Quality Eval",
        "",
        "<!--",
        "@dependency-start",
        "responsibility Records one report quality eval run.",
        "upstream implementation ../../../../tools/agent_tools/evaluate_report_quality.py generates this report",
        "@dependency-end",
        "-->",
        "",
        f"REPORT_QUALITY_EVAL_RUN_ID={bundle.run_id}",
        f"REPORT_QUALITY_EVAL_STATUS={bundle.status}",
        f"REPORT_QUALITY_EVAL_TARGETS={len(bundle.evals)}",
        f"REPORT_QUALITY_EVAL_CHECKS={len(bundle.results)}",
        f"REPORT_QUALITY_EVAL_FAILED={bundle.failed_count}",
        f"REPORT_QUALITY_EVAL_CRITICAL_FAILED={bundle.critical_failed_count}",
        f"manifest: `{bundle.manifest.relative_to(bundle.root).as_posix()}`",
        "",
        "| eval | item | status | critical | missing required | matched forbidden |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in bundle.results:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{result.eval_id}`",
                    f"`{result.item_id}`",
                    "`pass`" if result.passed else "`fail`",
                    "`yes`" if result.critical else "`no`",
                    comma(result.missing_required),
                    comma(result.matched_forbidden),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def comma(values: Sequence[str]) -> str:
    """Return a comma-joined Markdown table value."""
    return ", ".join(f"`{value}`" for value in values) if values else "`none`"


def write_report(path: Path, bundle: ReportQualityBundle) -> Path:
    """Write a report path without overwriting an existing report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path = path.with_name(f"{path.stem}-{bundle.run_id}{path.suffix}")
    path.write_text(render_report(bundle), encoding="utf-8")
    return path


def resolve_results_dir(root: Path, value: str) -> Path:
    """Resolve the CLI results directory or the default archive location."""
    stripped = value.strip()
    if stripped:
        path = Path(stripped)
        return path if path.is_absolute() else root / path
    return eval_results_dir(agent_canon_root(root), DEFAULT_RESULTS_FAMILY)


def accumulated_report_path(results_dir: Path, bundle: ReportQualityBundle) -> Path:
    """Return the unique accumulated report path."""
    return results_dir / f"{bundle.run_id}-{bundle.status}.md"


def main(argv: Sequence[str] | None = None) -> int:
    """Run report quality evals."""
    args = build_parser().parse_args(argv)
    bundle = evaluate(args.root, Path(args.manifest))
    report_paths: list[Path] = []
    if args.report_out:
        report_paths.append(write_report(Path(args.report_out), bundle))
    if args.accumulate:
        report_paths.append(
            write_report(
                accumulated_report_path(resolve_results_dir(bundle.root, str(args.results_dir)), bundle),
                bundle,
            )
        )
    print(f"REPORT_QUALITY_EVAL_RUN_ID={bundle.run_id}")
    print(f"REPORT_QUALITY_EVAL_TARGETS={len(bundle.evals)}")
    print(f"REPORT_QUALITY_EVAL_CHECKS={len(bundle.results)}")
    print(f"REPORT_QUALITY_EVAL_FAILED={bundle.failed_count}")
    print(f"REPORT_QUALITY_EVAL_CRITICAL_FAILED={bundle.critical_failed_count}")
    for path in report_paths:
        print(f"REPORT_QUALITY_EVAL_REPORT={path}")
    print(f"REPORT_QUALITY_EVAL_STATUS={bundle.status}")
    return 0 if bundle.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
