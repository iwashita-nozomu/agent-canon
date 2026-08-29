#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Evaluates deterministic workflow selection routing cases.
# upstream design ../../evidence/agent-evals/README.md eval usage contract
# upstream design ../../evidence/agent-evals/workflow_selection_eval.toml workflow selection eval manifest
# upstream implementation ./prompt_classifier.py owns prompt-to-workflow classification
# upstream implementation ./runtime_log_paths.py resolves accumulated eval archive paths
# downstream implementation ../../tests/agent_tools/test_evaluate_workflow_selection.py tests workflow selection eval behavior
# @dependency-end
"""Evaluate workflow selection routing against frozen prompt cases."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path
from typing import cast

from tools.agent.orchestration.prompt_classifier import (
    PromptClassifierInputs,
    SkillLaneEvidence,
    prompt_intake_signals,
)
from tools.agent.skills.skill_lane_detector import (
    structural_skill_lane_concept_matches,
    validation_failure_repair_concept_matches,
)

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

from eval.checkers.eval_manifest_paths import eval_manifest_path, resolve_eval_manifest
from tools.runtime.archive.runtime_log_paths import agent_canon_root, eval_results_dir
from tools.runtime.artifacts.runtime_artifacts import RuntimeArtifactError, runtime_artifact_boundary

DEFAULT_MANIFEST = eval_manifest_path("workflow_selection_eval.toml")
DEFAULT_RESULTS_FAMILY = "workflow-selection"
RUN_ID_DIGEST_LENGTH = 10


@dataclass(frozen=True)
class WorkflowSelectionCase:
    """One deterministic workflow selection eval case."""

    case_id: str
    group_id: str
    description: str
    prompt: str
    expected_workflows: tuple[str, ...]
    forbidden_workflows: tuple[str, ...]
    expected_skills: tuple[str, ...]
    expected_tools: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowSelectionResult:
    """One workflow selection case result."""

    case: WorkflowSelectionCase
    observed_workflows: tuple[str, ...]
    selected_skills: tuple[str, ...]
    candidate_skills: tuple[str, ...]
    observed_tools: tuple[str, ...]
    missing_workflows: tuple[str, ...]
    forbidden_workflows_seen: tuple[str, ...]
    missing_skills: tuple[str, ...]
    missing_tools: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return whether this case passed all expectations."""
        return not (
            self.missing_workflows
            or self.forbidden_workflows_seen
            or self.missing_skills
            or self.missing_tools
        )


@dataclass(frozen=True)
class WorkflowSelectionBundle:
    """All workflow selection eval data for one run."""

    run_id: str
    requested_run_id: str
    status: str
    root: Path
    manifest: Path
    results: tuple[WorkflowSelectionResult, ...]
    expected_case_count: int | None
    expected_generated_case_count: int | None
    generated_case_count: int
    count_failures: tuple[str, ...]

    @property
    def failed_count(self) -> int:
        """Return failed case count."""
        return sum(1 for result in self.results if not result.passed)


@dataclass(frozen=True)
class WorkflowSelectionManifest:
    """Expanded workflow selection manifest data."""

    cases: tuple[WorkflowSelectionCase, ...]
    expected_case_count: int | None
    expected_generated_case_count: int | None
    generated_case_count: int
    count_failures: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--runtime-root",
        type=Path,
        help="Explicit external runtime root for reports; required when writing output.",
    )
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--report-out", default="")
    parser.add_argument("--accumulate", action="store_true")
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional parent run-bundle or CI gate id recorded inside accumulated reports.",
    )
    parser.add_argument(
        "--results-dir",
        default="",
        help=(
            "Directory for accumulated reports. Defaults to the mounted "
            "AgentCanon log archive eval-results/workflow-selection path."
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


def optional_count(value: object, field: str) -> int | None:
    """Return an optional non-negative integer manifest count."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def positive_count(value: object, field: str) -> int:
    """Return a required positive integer manifest count."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def format_group_prompt(template: str, subject: str, group_id: str) -> str:
    """Format one generated prompt template."""
    try:
        prompt = template.format(subject=subject)
    except KeyError as exc:
        raise ValueError(
            f"case group {group_id} template uses unsupported field {exc.args[0]!r}"
        ) from exc
    except (IndexError, ValueError) as exc:
        raise ValueError(f"case group {group_id} has invalid prompt template") from exc
    prompt = prompt.strip()
    if not prompt:
        raise ValueError(f"case group {group_id} generated an empty prompt")
    return prompt


def load_explicit_cases(
    raw_cases: object,
    seen_ids: set[str],
) -> list[WorkflowSelectionCase]:
    """Load explicit workflow selection cases."""
    if raw_cases is None:
        return []
    if not isinstance(raw_cases, list):
        raise ValueError("cases must be a list of tables")
    cases: list[WorkflowSelectionCase] = []
    for index, raw_case in enumerate(cast(list[object], raw_cases), start=1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"case {index} must be a table")
        entry = cast(dict[str, object], raw_case)
        case_id = str(entry.get("id") or "").strip()
        if not case_id:
            raise ValueError(f"case {index} must define id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)
        prompt = str(entry.get("prompt") or "").strip()
        if not prompt:
            raise ValueError(f"case {case_id} must define prompt")
        expected_workflows = string_list(entry.get("expected_workflows"), f"{case_id}.expected_workflows")
        if not expected_workflows:
            raise ValueError(f"case {case_id} must define expected_workflows")
        cases.append(
            WorkflowSelectionCase(
                case_id=case_id,
                group_id=str(entry.get("group_id") or "explicit"),
                description=str(entry.get("description") or ""),
                prompt=prompt,
                expected_workflows=expected_workflows,
                forbidden_workflows=string_list(
                    entry.get("forbidden_workflows"),
                    f"{case_id}.forbidden_workflows",
                ),
                expected_skills=string_list(entry.get("expected_skills"), f"{case_id}.expected_skills"),
                expected_tools=string_list(entry.get("expected_tools"), f"{case_id}.expected_tools"),
            )
        )
    return cases


def load_case_groups(
    raw_groups: object,
    seen_ids: set[str],
) -> tuple[list[WorkflowSelectionCase], int]:
    """Expand generated workflow selection case groups."""
    if raw_groups is None:
        return [], 0
    if not isinstance(raw_groups, list):
        raise ValueError("case_groups must be a list of tables")
    cases: list[WorkflowSelectionCase] = []
    generated_count = 0
    for index, raw_group in enumerate(cast(list[object], raw_groups), start=1):
        if not isinstance(raw_group, dict):
            raise ValueError(f"case group {index} must be a table")
        entry = cast(dict[str, object], raw_group)
        group_id = str(entry.get("id") or "").strip()
        if not group_id:
            raise ValueError(f"case group {index} must define id")
        templates = string_list(entry.get("prompt_templates"), f"{group_id}.prompt_templates")
        subjects = string_list(entry.get("subjects"), f"{group_id}.subjects")
        if not templates:
            raise ValueError(f"case group {group_id} must define prompt_templates")
        if not subjects:
            raise ValueError(f"case group {group_id} must define subjects")
        expected_workflows = string_list(entry.get("expected_workflows"), f"{group_id}.expected_workflows")
        if not expected_workflows:
            raise ValueError(f"case group {group_id} must define expected_workflows")
        requested_limit = entry.get("limit")
        limit = (
            positive_count(requested_limit, f"{group_id}.limit")
            if requested_limit is not None
            else len(templates) * len(subjects)
        )
        if len(templates) * len(subjects) < limit:
            raise ValueError(
                f"case group {group_id} has {len(templates) * len(subjects)} prompt combinations "
                f"but limit={limit}"
            )
        group_count = 0
        for subject in subjects:
            for template in templates:
                if group_count >= limit:
                    break
                group_count += 1
                case_id = f"{group_id}-{group_count:03d}"
                if case_id in seen_ids:
                    raise ValueError(f"duplicate case id: {case_id}")
                seen_ids.add(case_id)
                cases.append(
                    WorkflowSelectionCase(
                        case_id=case_id,
                        group_id=group_id,
                        description=str(entry.get("description") or ""),
                        prompt=format_group_prompt(template, subject, group_id),
                        expected_workflows=expected_workflows,
                        forbidden_workflows=string_list(
                            entry.get("forbidden_workflows"),
                            f"{group_id}.forbidden_workflows",
                        ),
                        expected_skills=string_list(entry.get("expected_skills"), f"{group_id}.expected_skills"),
                        expected_tools=string_list(entry.get("expected_tools"), f"{group_id}.expected_tools"),
                    )
                )
            if group_count >= limit:
                break
        generated_count += group_count
    return cases, generated_count


def load_manifest(path: Path) -> WorkflowSelectionManifest:
    """Load and expand one workflow selection eval manifest."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    seen_ids: set[str] = set()
    cases = load_explicit_cases(data.get("cases"), seen_ids)
    generated_cases, generated_case_count = load_case_groups(data.get("case_groups"), seen_ids)
    cases.extend(generated_cases)
    if not cases:
        raise ValueError("manifest must define at least one [[cases]] or [[case_groups]] entry")
    expected_case_count = optional_count(data.get("expected_case_count"), "expected_case_count")
    expected_generated_case_count = optional_count(
        data.get("expected_generated_case_count"),
        "expected_generated_case_count",
    )
    count_failures: list[str] = []
    if expected_case_count is not None and expected_case_count != len(cases):
        count_failures.append(f"expected_case_count={expected_case_count} observed={len(cases)}")
    if expected_generated_case_count is not None and expected_generated_case_count != generated_case_count:
        count_failures.append(
            f"expected_generated_case_count={expected_generated_case_count} "
            f"observed={generated_case_count}"
        )
    return WorkflowSelectionManifest(
        cases=tuple(cases),
        expected_case_count=expected_case_count,
        expected_generated_case_count=expected_generated_case_count,
        generated_case_count=generated_case_count,
        count_failures=tuple(count_failures),
    )


def load_cases(path: Path) -> tuple[WorkflowSelectionCase, ...]:
    """Load workflow selection eval cases."""
    return load_manifest(path).cases


def evaluate_case(root: Path, case: WorkflowSelectionCase) -> WorkflowSelectionResult:
    """Evaluate one case through the pure injected routing classifier."""
    lane_evidence = tuple(
        SkillLaneEvidence(
            schema="agent-canon.skill-lane.v1",
            lane=match.concept.name,
            route_skills=match.concept.route_skills,
            evidence_categories=match.observed_evidence_categories,
            status="observed",
        )
        for match in structural_skill_lane_concept_matches(case.prompt)
    )
    validation_evidence = tuple(match.reason() for match in validation_failure_repair_concept_matches(case.prompt))
    signals = prompt_intake_signals(
        PromptClassifierInputs(
            prompt=case.prompt,
            repo_root=root.resolve(),
            catalog={},
            routing_rules={},
            structural_lane_evidence=lane_evidence,
            validation_repair_evidence=validation_evidence,
        )
    )
    observed_workflows = tuple(
        dict.fromkeys(tuple(signals.selected_workflows) + tuple(signals.candidate_workflows))
    )
    selected_skills = tuple(signals.skills)
    candidate_skills = tuple(signals.candidate_skills)
    observed_skills = tuple(dict.fromkeys(selected_skills + candidate_skills))
    observed_tools = tuple(signals.candidate_tools)
    return WorkflowSelectionResult(
        case=case,
        observed_workflows=observed_workflows,
        selected_skills=selected_skills,
        candidate_skills=candidate_skills,
        observed_tools=observed_tools,
        missing_workflows=tuple(
            workflow for workflow in case.expected_workflows if workflow not in observed_workflows
        ),
        forbidden_workflows_seen=tuple(
            workflow for workflow in case.forbidden_workflows if workflow in observed_workflows
        ),
        missing_skills=tuple(skill for skill in case.expected_skills if skill not in observed_skills),
        missing_tools=tuple(tool for tool in case.expected_tools if tool not in observed_tools),
    )


def run_id_for(
    manifest: Path,
    results: tuple[WorkflowSelectionResult, ...],
    requested_run_id: str,
) -> str:
    """Return one unique workflow selection eval run id."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    digest_source = "\n".join(
        [
            manifest.as_posix(),
            requested_run_id,
            *(f"{item.case.case_id}:{item.passed}:{item.observed_workflows}" for item in results),
            *(f"{item.case.case_id}:selected:{item.selected_skills}" for item in results),
            *(f"{item.case.case_id}:candidate:{item.candidate_skills}" for item in results),
            *(f"{item.case.case_id}:tools:{item.observed_tools}" for item in results),
            timestamp,
        ]
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:RUN_ID_DIGEST_LENGTH]
    return f"workflow-selection-eval-{timestamp}-{digest}"


def evaluate(root: Path, manifest: Path, requested_run_id: str = "") -> WorkflowSelectionBundle:
    """Evaluate one workflow selection manifest."""
    resolved_root = root.resolve()
    resolved_manifest = resolve_eval_manifest(resolved_root, manifest).resolve()
    manifest_data = load_manifest(resolved_manifest)
    results = tuple(evaluate_case(resolved_root, case) for case in manifest_data.cases)
    status = "pass" if all(result.passed for result in results) and not manifest_data.count_failures else "fail"
    return WorkflowSelectionBundle(
        run_id=run_id_for(resolved_manifest, results, requested_run_id),
        requested_run_id=requested_run_id,
        status=status,
        root=resolved_root,
        manifest=resolved_manifest,
        results=results,
        expected_case_count=manifest_data.expected_case_count,
        expected_generated_case_count=manifest_data.expected_generated_case_count,
        generated_case_count=manifest_data.generated_case_count,
        count_failures=manifest_data.count_failures,
    )


def render_report(bundle: WorkflowSelectionBundle) -> str:
    """Render a Markdown report without copying raw prompt text."""
    count_failures = "; ".join(bundle.count_failures) if bundle.count_failures else "none"
    lines = [
        "# Workflow Selection Eval",
        "",
        "<!--",
        "@dependency-start",
        "responsibility Records one workflow selection eval run.",
        "upstream implementation ../../../../eval/producers/evaluate_workflow_selection.py generates this report",
        "@dependency-end",
        "-->",
        "",
        f"WORKFLOW_SELECTION_EVAL_RUN_ID={bundle.run_id}",
        f"WORKFLOW_SELECTION_EVAL_SOURCE_RUN_ID={bundle.requested_run_id or 'none'}",
        f"WORKFLOW_SELECTION_EVAL_STATUS={bundle.status}",
        f"WORKFLOW_SELECTION_EVAL_CASES={len(bundle.results)}",
        f"WORKFLOW_SELECTION_EVAL_EXPECTED_CASES={bundle.expected_case_count if bundle.expected_case_count is not None else 'none'}",
        f"WORKFLOW_SELECTION_EVAL_GENERATED_CASES={bundle.generated_case_count}",
        f"WORKFLOW_SELECTION_EVAL_EXPECTED_GENERATED_CASES={bundle.expected_generated_case_count if bundle.expected_generated_case_count is not None else 'none'}",
        f"WORKFLOW_SELECTION_EVAL_COUNT_FAILURES={count_failures}",
        f"WORKFLOW_SELECTION_EVAL_FAILED={bundle.failed_count}",
        f"manifest: `{display_path(bundle.root, bundle.manifest)}`",
        "",
        (
            "| group | case | status | expected workflows | observed workflows | selected skills | "
            "candidate skills | expected tools | observed tools | missing workflows | forbidden workflows | "
            "missing skills | missing tools |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in bundle.results:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{result.case.group_id}`",
                    f"`{result.case.case_id}`",
                    "`pass`" if result.passed else "`fail`",
                    comma(result.case.expected_workflows),
                    comma(result.observed_workflows),
                    comma(result.selected_skills),
                    comma(result.candidate_skills),
                    comma(result.case.expected_tools),
                    comma(result.observed_tools),
                    comma(result.missing_workflows),
                    comma(result.forbidden_workflows_seen),
                    comma(result.missing_skills),
                    comma(result.missing_tools),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def comma(values: Sequence[str]) -> str:
    """Return a comma-joined table value."""
    return ", ".join(f"`{value}`" for value in values) if values else "`none`"


def display_path(root: Path, path: Path) -> str:
    """Return a root-relative path where possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def write_report(
    path: Path,
    bundle: WorkflowSelectionBundle,
    runtime_root: Path | str | None = None,
) -> Path:
    """Write a report path, avoiding accidental overwrite."""
    if path.exists():
        path = path.with_name(f"{path.stem}-{bundle.run_id}{path.suffix}")
    boundary = runtime_artifact_boundary(bundle.root, runtime_root)
    return boundary.atomic_write_text(path, render_report(bundle))


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


def accumulated_report_path(results_dir: Path, bundle: WorkflowSelectionBundle) -> Path:
    """Return the unique accumulated report path."""
    return results_dir / f"{bundle.run_id}-{bundle.status}.md"


def main(argv: Sequence[str] | None = None) -> int:
    """Run workflow selection evals."""
    args = build_parser().parse_args(argv)
    bundle = evaluate(args.root, Path(args.manifest), requested_run_id=str(args.run_id))
    boundary = (
        runtime_artifact_boundary(args.root, args.runtime_root)
        if args.report_out or args.accumulate
        else None
    )
    report_paths: list[Path] = []
    if args.report_out:
        assert boundary is not None
        report_paths.append(write_report(Path(args.report_out), bundle, boundary.root))
    if args.accumulate:
        report_paths.append(
            write_report(
                accumulated_report_path(
                    resolve_results_dir(
                        bundle.root, str(args.results_dir), boundary.root  # type: ignore[union-attr]
                    ),
                    bundle,
                ),
                bundle,
                boundary.root if boundary is not None else None,
            )
        )
    print(f"WORKFLOW_SELECTION_EVAL_RUN_ID={bundle.run_id}")
    print(f"WORKFLOW_SELECTION_EVAL_SOURCE_RUN_ID={bundle.requested_run_id or 'none'}")
    print(f"WORKFLOW_SELECTION_EVAL_CASES={len(bundle.results)}")
    print(f"WORKFLOW_SELECTION_EVAL_EXPECTED_CASES={bundle.expected_case_count if bundle.expected_case_count is not None else 'none'}")
    print(f"WORKFLOW_SELECTION_EVAL_GENERATED_CASES={bundle.generated_case_count}")
    print(f"WORKFLOW_SELECTION_EVAL_EXPECTED_GENERATED_CASES={bundle.expected_generated_case_count if bundle.expected_generated_case_count is not None else 'none'}")
    print(
        "WORKFLOW_SELECTION_EVAL_COUNT_FAILURES="
        + ("; ".join(bundle.count_failures) if bundle.count_failures else "none")
    )
    print(f"WORKFLOW_SELECTION_EVAL_FAILED={bundle.failed_count}")
    for path in report_paths:
        print(f"WORKFLOW_SELECTION_EVAL_REPORT={path}")
    print(f"WORKFLOW_SELECTION_EVAL_STATUS={bundle.status}")
    return 0 if bundle.status == "pass" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeArtifactError as exc:
        print(f"evaluate_workflow_selection.py: runtime_root_required: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
