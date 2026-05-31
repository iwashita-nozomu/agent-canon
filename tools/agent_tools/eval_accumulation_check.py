#!/usr/bin/env python3
# @dependency-start
# responsibility Validates append-only AgentCanon eval and hook result accumulation.
# upstream design ../../agents/evals/README.md eval usage contract
# upstream design ../../documents/runtime-log-archive.md eval and hook result archive contract
# upstream design ../../documents/runtime-log-archive-migration.md legacy in-tree result migration contract
# upstream implementation ./runtime_log_paths.py resolves mounted archive result paths
# upstream design ../../tools/README.md tool entrypoint index
# upstream design ../../documents/tools/README.md user-facing tool index
# downstream implementation ../../tools/ci/run_all_checks.sh runs eval accumulation checks
# downstream implementation ../../tests/agent_tools/test_eval_accumulation_check.py tests result validation
# @dependency-end
"""Check accumulated AgentCanon eval and hook results."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime_log_paths import (  # noqa: E402
    eval_result_search_dirs,
    hook_result_search_dirs,
    mounted_log_archive_root,
)

HOOK_REQUIRED_FIELDS = (
    "hook_run_id",
    "timestamp",
    "status",
    "payload_fingerprint",
)
SKILL_REPORT_RE = re.compile(
    r"^skill-eval-\d{8}T\d{12}Z-[0-9a-f]{10}-(?:pass|fail)-[a-z0-9-]+(?:-[a-z0-9-]+)*\.md$"
)
LOCAL_LLM_REPORT_RE = re.compile(
    r"^local-llm-eval-\d{8}T\d{12}Z-[0-9a-f]{10}-(?:pass|fail|skip)\.md$"
)
WORKFLOW_SELECTION_REPORT_RE = re.compile(
    r"^workflow-selection-eval-\d{8}T\d{12}Z-[0-9a-f]{10}-(?:pass|fail)\.md$"
)
REPORT_QUALITY_REPORT_RE = re.compile(
    r"^report-quality-eval-\d{8}T\d{12}Z-[0-9a-f]{10}-(?:pass|fail)\.md$"
)
COMPACT_FINDING_SAMPLE_LIMIT = 25


@dataclass(frozen=True)
class Finding:
    """One eval accumulation finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one machine-readable finding."""
        return f"EVAL_ACCUMULATION_FINDING={self.check}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class EvalAccumulationReport:
    """Eval accumulation report."""

    hook_files: int
    hook_entries: int
    hook_legacy_missing_namespace: int
    skill_reports: int
    local_llm_reports: int
    workflow_selection_reports: int
    report_quality_reports: int
    findings: tuple[Finding, ...]


def is_mounted_archive_path(path_label: str) -> bool:
    """Return whether a finding path points at the mounted external archive."""
    return path_label.startswith(".agent-canon/archive/") or path_label.startswith(
        ".agent-canon/log-archive/"
    )


def is_warning_finding(finding: Finding) -> bool:
    """Return whether a finding is nonblocking archive evidence debt."""
    return finding.check == "hook_jsonl" and is_mounted_archive_path(finding.path)


def blocking_findings(report: EvalAccumulationReport) -> tuple[Finding, ...]:
    """Return findings that should fail the checker."""
    return tuple(finding for finding in report.findings if not is_warning_finding(finding))


def warning_findings(report: EvalAccumulationReport) -> tuple[Finding, ...]:
    """Return findings that should be reported without blocking the checker."""
    return tuple(finding for finding in report.findings if is_warning_finding(finding))


def report_status(report: EvalAccumulationReport) -> str:
    """Return pass/fail status from blocking findings only."""
    return "pass" if not blocking_findings(report) else "fail"


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--compact-out",
        type=Path,
        help="Optional JSON summary path. When set, stdout omits full finding detail.",
    )
    return parser


def agent_canon_root(root: Path) -> Path:
    """Return AgentCanon source root for standalone or parent invocation."""
    vendored = root / "vendor" / "agent-canon"
    if (vendored / "agents" / "evals" / "README.md").is_file():
        return vendored
    return root


def relative(root: Path, path: Path) -> str:
    """Return a stable root-relative path."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def git_check_ignored(root: Path, path: Path) -> bool:
    """Return whether git ignore rules ignore a path."""
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", "--", relative(root, path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def ignored_path_findings(root: Path, paths: Sequence[Path]) -> list[Finding]:
    """Return findings for result files ignored by git."""
    return [
        Finding("gitignore", relative(root, path), "ignored-result-path")
        for path in paths
        if not intentionally_ignored_archive_path(path) and git_check_ignored(root, path)
    ]


def intentionally_ignored_archive_path(path: Path) -> bool:
    """Return whether the path is inside the mounted external log archive."""
    parts = path.parts
    return ".agent-canon" in parts and ("archive" in parts or "log-archive" in parts)


def parse_hook_line(root: Path, path: Path, line_no: int, raw_line: str) -> tuple[str, int, list[Finding]]:
    """Parse one hook JSONL line and return its run id plus findings."""
    label = f"{relative(root, path)}:{line_no}"
    try:
        loaded = json.loads(raw_line)
    except json.JSONDecodeError:
        return "", 0, [Finding("hook_jsonl", label, "invalid-json")]
    if not isinstance(loaded, dict):
        return "", 0, [Finding("hook_jsonl", label, "entry-not-object")]
    entry = cast(dict[str, object], loaded)
    namespaced = path.parent.name not in ("hook-runs", "legacy-import")
    required_fields = HOOK_REQUIRED_FIELDS if namespaced else (
        "hook_run_id",
        "timestamp",
        "payload_fingerprint",
    )
    findings = [
        Finding("hook_jsonl", label, f"missing-field:{field}")
        for field in required_fields
        if not isinstance(entry.get(field), str) or not str(entry.get(field)).strip()
    ]
    legacy_missing_namespace = 0
    if namespaced and not isinstance(entry.get("hook_log_namespace"), str):
        legacy_missing_namespace = 1
    run_id = entry.get("hook_run_id")
    return (run_id if isinstance(run_id, str) else ""), legacy_missing_namespace, findings


def hook_result_findings(root: Path, hook_dirs: Sequence[Path]) -> tuple[int, int, int, list[Finding]]:
    """Validate hook JSONL files."""
    findings: list[Finding] = []
    seen_run_ids: dict[str, str] = {}
    files = sorted(
        {
            path
            for hook_dir in hook_dirs
            if hook_dir.is_dir()
            for path in hook_dir.rglob("*.jsonl")
        }
    )
    entries = 0
    legacy_missing_namespace = 0
    for path in files:
        for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw_line.strip():
                continue
            entries += 1
            run_id, line_legacy_missing_namespace, line_findings = parse_hook_line(
                root, path, line_no, raw_line
            )
            legacy_missing_namespace += line_legacy_missing_namespace
            findings.extend(line_findings)
            if not run_id:
                continue
            previous = seen_run_ids.get(run_id)
            label = f"{relative(root, path)}:{line_no}"
            if previous is not None:
                findings.append(Finding("hook_run_id", label, f"duplicate:{previous}"))
            seen_run_ids[run_id] = label
    if files and entries == 0:
        labels = ",".join(relative(root, hook_dir) for hook_dir in hook_dirs)
        findings.append(Finding("hook_jsonl", labels, "no-hook-entries"))
    findings.extend(ignored_path_findings(root, files))
    return len(files), entries, legacy_missing_namespace, findings


def eval_run_id_from_text(text: str) -> str:
    """Extract an eval run id from current or legacy report text."""
    current = re.search(r"\bEVAL_RUN_ID=([A-Za-z0-9_.:-]+)", text)
    if current:
        return current.group(1)
    legacy = re.search(r"eval_run_id:\s*`?([A-Za-z0-9_.:-]+)`?", text)
    return legacy.group(1) if legacy else ""


def markdown_reports(results_dirs: Sequence[Path]) -> tuple[Path, ...]:
    """Return unique Markdown reports from multiple result directories."""
    return tuple(
        sorted(
            {
                path
                for results_dir in results_dirs
                if results_dir.is_dir()
                for path in results_dir.glob("*.md")
                if path.name != "README.md"
            }
        )
    )


def missing_reports_label(root: Path, results_dirs: Sequence[Path]) -> str:
    """Return a bounded path label for a missing report family."""
    return ",".join(relative(root, path) for path in results_dirs)


def reports_required(results_dirs: Sequence[Path], *, archive_mounted: bool) -> bool:
    """Return whether absence of a report family is a validation failure."""
    return archive_mounted or any(results_dir.is_dir() for results_dir in results_dirs)


def skill_eval_findings(
    root: Path,
    results_dirs: Sequence[Path],
    *,
    require_reports: bool,
) -> tuple[int, list[Finding]]:
    """Validate accumulated skill/workflow prompt eval reports."""
    findings: list[Finding] = []
    reports = markdown_reports(results_dirs)
    seen_run_ids: dict[str, str] = {}
    if not reports and require_reports:
        findings.append(Finding("skill_eval", missing_reports_label(root, results_dirs), "no-skill-eval-reports"))
    for path in reports:
        rel_path = relative(root, path)
        if not SKILL_REPORT_RE.fullmatch(path.name):
            findings.append(Finding("skill_eval", rel_path, "invalid-report-name"))
        text = path.read_text(encoding="utf-8")
        run_id = eval_run_id_from_text(text)
        if not run_id:
            findings.append(Finding("skill_eval", rel_path, "missing-eval-run-id"))
            continue
        previous = seen_run_ids.get(run_id)
        if previous is not None:
            findings.append(Finding("skill_eval", rel_path, f"duplicate-eval-run-id:{previous}"))
        seen_run_ids[run_id] = rel_path
    findings.extend(ignored_path_findings(root, reports))
    return len(reports), findings


def local_llm_eval_findings(
    root: Path,
    results_dirs: Sequence[Path],
    *,
    require_reports: bool,
) -> tuple[int, list[Finding]]:
    """Validate accumulated local LLM responsibility eval reports."""
    findings: list[Finding] = []
    reports = markdown_reports(results_dirs)
    seen_run_ids: dict[str, str] = {}
    if not reports and require_reports:
        findings.append(Finding("local_llm_eval", missing_reports_label(root, results_dirs), "no-local-llm-eval-reports"))
    for path in reports:
        rel_path = relative(root, path)
        if not LOCAL_LLM_REPORT_RE.fullmatch(path.name):
            findings.append(Finding("local_llm_eval", rel_path, "invalid-report-name"))
        text = path.read_text(encoding="utf-8")
        run_id = re.search(r"\bLOCAL_LLM_EVAL_RUN_ID=([A-Za-z0-9_.:-]+)", text)
        if run_id is None:
            findings.append(Finding("local_llm_eval", rel_path, "missing-local-llm-eval-run-id"))
            continue
        previous = seen_run_ids.get(run_id.group(1))
        if previous is not None:
            findings.append(Finding("local_llm_eval", rel_path, f"duplicate-local-llm-eval-run-id:{previous}"))
        seen_run_ids[run_id.group(1)] = rel_path
    findings.extend(ignored_path_findings(root, reports))
    return len(reports), findings


def workflow_selection_eval_findings(
    root: Path,
    results_dirs: Sequence[Path],
    *,
    require_reports: bool,
) -> tuple[int, list[Finding]]:
    """Validate accumulated workflow selection eval reports."""
    findings: list[Finding] = []
    reports = markdown_reports(results_dirs)
    seen_run_ids: dict[str, str] = {}
    if not reports and require_reports:
        findings.append(
            Finding(
                "workflow_selection_eval",
                missing_reports_label(root, results_dirs),
                "no-workflow-selection-eval-reports",
            )
        )
    for path in reports:
        rel_path = relative(root, path)
        if not WORKFLOW_SELECTION_REPORT_RE.fullmatch(path.name):
            findings.append(Finding("workflow_selection_eval", rel_path, "invalid-report-name"))
        text = path.read_text(encoding="utf-8")
        run_id = re.search(r"\bWORKFLOW_SELECTION_EVAL_RUN_ID=([A-Za-z0-9_.:-]+)", text)
        if run_id is None:
            findings.append(Finding("workflow_selection_eval", rel_path, "missing-workflow-selection-eval-run-id"))
            continue
        previous = seen_run_ids.get(run_id.group(1))
        if previous is not None:
            findings.append(
                Finding(
                    "workflow_selection_eval",
                    rel_path,
                    f"duplicate-workflow-selection-eval-run-id:{previous}",
                )
            )
        seen_run_ids[run_id.group(1)] = rel_path
    findings.extend(ignored_path_findings(root, reports))
    return len(reports), findings


def report_quality_eval_findings(
    root: Path,
    results_dirs: Sequence[Path],
    *,
    require_reports: bool,
) -> tuple[int, list[Finding]]:
    """Validate accumulated report quality eval reports."""
    findings: list[Finding] = []
    reports = markdown_reports(results_dirs)
    seen_run_ids: dict[str, str] = {}
    if not reports and require_reports:
        findings.append(Finding("report_quality_eval", missing_reports_label(root, results_dirs), "no-report-quality-eval-reports"))
    for path in reports:
        rel_path = relative(root, path)
        if not REPORT_QUALITY_REPORT_RE.fullmatch(path.name):
            findings.append(Finding("report_quality_eval", rel_path, "invalid-report-name"))
        text = path.read_text(encoding="utf-8")
        run_id = re.search(r"\bREPORT_QUALITY_EVAL_RUN_ID=([A-Za-z0-9_.:-]+)", text)
        if run_id is None:
            findings.append(Finding("report_quality_eval", rel_path, "missing-report-quality-eval-run-id"))
            continue
        previous = seen_run_ids.get(run_id.group(1))
        if previous is not None:
            findings.append(
                Finding(
                    "report_quality_eval",
                    rel_path,
                    f"duplicate-report-quality-eval-run-id:{previous}",
                )
            )
        seen_run_ids[run_id.group(1)] = rel_path
    findings.extend(ignored_path_findings(root, reports))
    return len(reports), findings


def validate(root: Path) -> EvalAccumulationReport:
    """Validate accumulated eval results."""
    requested_root = root.resolve()
    canon_root = agent_canon_root(requested_root)
    findings: list[Finding] = []
    hook_files, hook_entries, hook_legacy_missing_namespace, hook_findings = hook_result_findings(
        canon_root,
        hook_result_search_dirs(requested_root, canon_root),
    )
    archive_mounted = mounted_log_archive_root(canon_root).is_dir()
    skill_results_dirs = eval_result_search_dirs(canon_root, "skill-workflow-prompt")
    skill_reports, skill_findings = skill_eval_findings(
        canon_root,
        skill_results_dirs,
        require_reports=reports_required(skill_results_dirs, archive_mounted=archive_mounted),
    )
    local_llm_results_dirs = eval_result_search_dirs(canon_root, "local-llm-responsibility")
    local_llm_reports, local_llm_findings = local_llm_eval_findings(
        canon_root,
        local_llm_results_dirs,
        require_reports=reports_required(local_llm_results_dirs, archive_mounted=archive_mounted),
    )
    workflow_selection_results_dirs = eval_result_search_dirs(canon_root, "workflow-selection")
    workflow_selection_reports, workflow_selection_findings = workflow_selection_eval_findings(
        canon_root,
        workflow_selection_results_dirs,
        require_reports=reports_required(
            workflow_selection_results_dirs,
            archive_mounted=archive_mounted,
        ),
    )
    report_quality_results_dirs = eval_result_search_dirs(canon_root, "report-quality")
    report_quality_reports, report_quality_findings = report_quality_eval_findings(
        canon_root,
        report_quality_results_dirs,
        require_reports=reports_required(report_quality_results_dirs, archive_mounted=archive_mounted),
    )
    findings.extend(hook_findings)
    findings.extend(skill_findings)
    findings.extend(local_llm_findings)
    findings.extend(workflow_selection_findings)
    findings.extend(report_quality_findings)
    return EvalAccumulationReport(
        hook_files=hook_files,
        hook_entries=hook_entries,
        hook_legacy_missing_namespace=hook_legacy_missing_namespace,
        skill_reports=skill_reports,
        local_llm_reports=local_llm_reports,
        workflow_selection_reports=workflow_selection_reports,
        report_quality_reports=report_quality_reports,
        findings=tuple(sorted(findings, key=lambda item: (item.check, item.path, item.detail))),
    )


def render_json(report: EvalAccumulationReport) -> str:
    """Render JSON output."""
    blocking = blocking_findings(report)
    warnings = warning_findings(report)
    return json.dumps(
        {
            "status": report_status(report),
            "hook_files": report.hook_files,
            "hook_entries": report.hook_entries,
            "hook_legacy_missing_namespace": report.hook_legacy_missing_namespace,
            "skill_reports": report.skill_reports,
            "local_llm_reports": report.local_llm_reports,
            "workflow_selection_reports": report.workflow_selection_reports,
            "report_quality_reports": report.report_quality_reports,
            "blocking_finding_count": len(blocking),
            "warning_count": len(warnings),
            "findings": [asdict(item) for item in report.findings],
        },
        indent=2,
        sort_keys=True,
    )


def compact_summary(report: EvalAccumulationReport) -> dict[str, object]:
    """Return a bounded JSON-friendly accumulation summary."""
    finding_counts: dict[str, int] = {}
    for finding in report.findings:
        finding_counts[finding.check] = finding_counts.get(finding.check, 0) + 1
    blocking = blocking_findings(report)
    warnings = warning_findings(report)
    return {
        "status": report_status(report),
        "finding_count": len(report.findings),
        "blocking_finding_count": len(blocking),
        "warning_count": len(warnings),
        "finding_counts": dict(sorted(finding_counts.items())),
        "hook_files": report.hook_files,
        "hook_entries": report.hook_entries,
        "hook_legacy_missing_namespace": report.hook_legacy_missing_namespace,
        "skill_reports": report.skill_reports,
        "local_llm_reports": report.local_llm_reports,
        "workflow_selection_reports": report.workflow_selection_reports,
        "report_quality_reports": report.report_quality_reports,
        "blocking_finding_samples": [
            asdict(finding) for finding in blocking[:COMPACT_FINDING_SAMPLE_LIMIT]
        ],
        "warning_samples": [
            asdict(finding) for finding in warnings[:COMPACT_FINDING_SAMPLE_LIMIT]
        ],
        "finding_samples": [
            asdict(finding) for finding in report.findings[:COMPACT_FINDING_SAMPLE_LIMIT]
        ],
    }


def write_compact_summary(path: Path, report: EvalAccumulationReport) -> None:
    """Write a bounded JSON summary for agent consumption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(compact_summary(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_text(
    report: EvalAccumulationReport,
    *,
    include_details: bool = True,
    compact_out: Path | None = None,
) -> str:
    """Render machine-readable text output."""
    blocking = blocking_findings(report)
    warnings = warning_findings(report)
    lines: list[str] = []
    if include_details:
        lines.extend(finding.render() for finding in report.findings)
    lines.extend(
        [
            f"EVAL_ACCUMULATION_HOOK_FILES={report.hook_files}",
            f"EVAL_ACCUMULATION_HOOK_ENTRIES={report.hook_entries}",
            "EVAL_ACCUMULATION_HOOK_LEGACY_MISSING_NAMESPACE="
            f"{report.hook_legacy_missing_namespace}",
            f"EVAL_ACCUMULATION_SKILL_REPORTS={report.skill_reports}",
            f"EVAL_ACCUMULATION_LOCAL_LLM_REPORTS={report.local_llm_reports}",
            f"EVAL_ACCUMULATION_WORKFLOW_SELECTION_REPORTS={report.workflow_selection_reports}",
            f"EVAL_ACCUMULATION_REPORT_QUALITY_REPORTS={report.report_quality_reports}",
            f"EVAL_ACCUMULATION_FINDINGS={len(report.findings)}",
            f"EVAL_ACCUMULATION_BLOCKING_FINDINGS={len(blocking)}",
            f"EVAL_ACCUMULATION_WARNINGS={len(warnings)}",
            f"EVAL_ACCUMULATION={report_status(report)}",
        ]
    )
    if compact_out is not None:
        lines.append(f"EVAL_ACCUMULATION_COMPACT_OUT={compact_out.as_posix()}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the eval accumulation checker."""
    args = build_parser().parse_args(argv)
    report = validate(args.root)
    if args.compact_out is not None:
        write_compact_summary(args.compact_out, report)
    if args.format == "json":
        print(render_json(report))
    else:
        print(
            render_text(
                report,
                include_details=args.compact_out is None,
                compact_out=args.compact_out,
            ),
            end="",
        )
    return 1 if blocking_findings(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
