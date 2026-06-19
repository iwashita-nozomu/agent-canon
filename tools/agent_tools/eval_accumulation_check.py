#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Validates append-only AgentCanon eval and hook result accumulation.
# upstream design ../../evidence/agent-evals/README.md eval usage contract
# upstream design ../../evidence/agent-evals/eval_result_families.toml eval family artifact registry
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
import tomllib

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_manifest_paths import eval_manifest_path, resolve_eval_manifest  # noqa: E402
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
DEFAULT_FAMILY_REGISTRY = Path(eval_manifest_path("eval_result_families.toml"))
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
class EvalFamilyContract:
    """One accumulated eval family artifact contract."""

    family_id: str
    check_id: str
    count_label: str
    summary: str
    producer: str
    filename_regex: str
    run_id_regex: str
    missing_reports_detail: str
    missing_run_id_detail: str
    duplicate_run_id_detail: str


@dataclass(frozen=True)
class EvalAccumulationReport:
    """Eval accumulation report."""

    hook_files: int
    hook_entries: int
    hook_legacy_missing_namespace: int
    eval_report_counts: dict[str, int]
    findings: tuple[Finding, ...]


def is_mounted_archive_path(path_label: str) -> bool:
    """Return whether a finding path points at the mounted external archive."""
    return path_label.startswith(".agent-canon/log-archive/")


def is_warning_finding(finding: Finding) -> bool:
    """Return whether a finding is nonblocking archive evidence debt."""
    if finding.check == "hook_jsonl" and is_mounted_archive_path(finding.path):
        return True
    return (
        finding.detail == "missing-eval-run-id"
        and finding.path.startswith(".agent-canon/log-archive/eval-results/legacy-import/")
    )


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
    parser.add_argument(
        "--family-registry",
        default=DEFAULT_FAMILY_REGISTRY.as_posix(),
        help="TOML registry that declares accumulated eval result families.",
    )
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
    return ".agent-canon" in parts and "log-archive" in parts


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


def resolve_family_registry(canon_root: Path, registry_value: str) -> Path:
    """Resolve the eval family registry path."""
    return resolve_eval_manifest(canon_root, registry_value)


def load_family_contracts(registry_path: Path) -> tuple[EvalFamilyContract, ...]:
    """Load accumulated eval family contracts from TOML."""
    data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
    families = data.get("families")
    if not isinstance(families, list) or not families:
        raise ValueError("eval family registry must define at least one [[families]] entry")
    contracts: list[EvalFamilyContract] = []
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    for raw_family in cast(list[object], families):
        if not isinstance(raw_family, dict):
            raise ValueError("eval family registry entries must be TOML tables")
        family = cast(dict[str, object], raw_family)
        values: dict[str, str] = {}
        for field in (
            "id",
            "check_id",
            "count_label",
            "summary",
            "producer",
            "filename_regex",
            "run_id_regex",
            "missing_reports_detail",
            "missing_run_id_detail",
            "duplicate_run_id_detail",
        ):
            value = family.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"eval family registry entry missing string field: {field}")
            values[field] = value.strip()
        if values["id"] in seen_ids:
            raise ValueError(f"duplicate eval family id: {values['id']}")
        if values["count_label"] in seen_labels:
            raise ValueError(f"duplicate eval family count label: {values['count_label']}")
        re.compile(values["filename_regex"])
        re.compile(values["run_id_regex"])
        seen_ids.add(values["id"])
        seen_labels.add(values["count_label"])
        contracts.append(
            EvalFamilyContract(
                family_id=values["id"],
                check_id=values["check_id"],
                count_label=values["count_label"],
                summary=values["summary"],
                producer=values["producer"],
                filename_regex=values["filename_regex"],
                run_id_regex=values["run_id_regex"],
                missing_reports_detail=values["missing_reports_detail"],
                missing_run_id_detail=values["missing_run_id_detail"],
                duplicate_run_id_detail=values["duplicate_run_id_detail"],
            )
        )
    return tuple(contracts)


def eval_family_findings(
    root: Path,
    contract: EvalFamilyContract,
    results_dirs: Sequence[Path],
    *,
    require_reports: bool,
) -> tuple[int, list[Finding]]:
    """Validate one accumulated eval report family declared by the registry."""
    findings: list[Finding] = []
    reports = markdown_reports(results_dirs)
    seen_run_ids: dict[str, str] = {}
    filename_pattern = re.compile(contract.filename_regex)
    run_id_pattern = re.compile(contract.run_id_regex)
    if not reports and require_reports:
        findings.append(
            Finding(
                contract.check_id,
                missing_reports_label(root, results_dirs),
                contract.missing_reports_detail,
            )
        )
    for path in reports:
        rel_path = relative(root, path)
        if not filename_pattern.fullmatch(path.name):
            findings.append(Finding(contract.check_id, rel_path, "invalid-report-name"))
        text = path.read_text(encoding="utf-8")
        run_id_match = run_id_pattern.search(text)
        if run_id_match is None:
            findings.append(Finding(contract.check_id, rel_path, contract.missing_run_id_detail))
            continue
        run_id = run_id_match.group(1)
        previous = seen_run_ids.get(run_id)
        if previous is not None:
            findings.append(
                Finding(contract.check_id, rel_path, f"{contract.duplicate_run_id_detail}:{previous}")
            )
        seen_run_ids[run_id] = rel_path
    findings.extend(ignored_path_findings(root, reports))
    return len(reports), findings


def validate(root: Path, family_registry: str = DEFAULT_FAMILY_REGISTRY.as_posix()) -> EvalAccumulationReport:
    """Validate accumulated eval results."""
    requested_root = root.resolve()
    canon_root = agent_canon_root(requested_root)
    contracts = load_family_contracts(resolve_family_registry(canon_root, family_registry))
    findings: list[Finding] = []
    hook_files, hook_entries, hook_legacy_missing_namespace, hook_findings = hook_result_findings(
        canon_root,
        hook_result_search_dirs(requested_root, canon_root),
    )
    archive_mounted = mounted_log_archive_root(canon_root).is_dir()
    eval_report_counts: dict[str, int] = {}
    findings.extend(hook_findings)
    for contract in contracts:
        results_dirs = eval_result_search_dirs(canon_root, contract.family_id)
        report_count, family_findings = eval_family_findings(
            canon_root,
            contract,
            results_dirs,
            require_reports=reports_required(results_dirs, archive_mounted=archive_mounted),
        )
        eval_report_counts[contract.family_id] = report_count
        findings.extend(family_findings)
    return EvalAccumulationReport(
        hook_files=hook_files,
        hook_entries=hook_entries,
        hook_legacy_missing_namespace=hook_legacy_missing_namespace,
        eval_report_counts=eval_report_counts,
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
            "hook_namespace_debt": report.hook_legacy_missing_namespace,
            "eval_report_counts": report.eval_report_counts,
            "skill_reports": eval_report_count(report, "skill-workflow-prompt"),
            "local_llm_reports": eval_report_count(report, "local-llm-responsibility"),
            "workflow_selection_reports": eval_report_count(report, "workflow-selection"),
            "report_quality_reports": eval_report_count(report, "report-quality"),
            "codex_agent_role_reports": eval_report_count(report, "codex-agent-role"),
            "blocking_finding_count": len(blocking),
            "warning_count": len(warnings),
            "findings": [asdict(item) for item in report.findings],
        },
        indent=2,
        sort_keys=True,
    )


def eval_report_count(report: EvalAccumulationReport, family_id: str) -> int:
    """Return a report count for one family id."""
    return report.eval_report_counts.get(family_id, 0)


def eval_family_count_lines(report: EvalAccumulationReport) -> list[str]:
    """Return generic per-family count lines without dynamic field names."""
    return [
        f"EVAL_ACCUMULATION_FAMILY_REPORTS={family_id}:{count}"
        for family_id, count in sorted(report.eval_report_counts.items())
    ]


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
        "hook_namespace_debt": report.hook_legacy_missing_namespace,
        "eval_report_counts": report.eval_report_counts,
        "skill_reports": eval_report_count(report, "skill-workflow-prompt"),
        "local_llm_reports": eval_report_count(report, "local-llm-responsibility"),
        "workflow_selection_reports": eval_report_count(report, "workflow-selection"),
        "report_quality_reports": eval_report_count(report, "report-quality"),
        "codex_agent_role_reports": eval_report_count(report, "codex-agent-role"),
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
            f"EVAL_ACCUMULATION_HOOK_NAMESPACE_DEBT={report.hook_legacy_missing_namespace}",
            f"EVAL_ACCUMULATION_SKILL_REPORTS={eval_report_count(report, 'skill-workflow-prompt')}",
            "EVAL_ACCUMULATION_LOCAL_LLM_REPORTS="
            f"{eval_report_count(report, 'local-llm-responsibility')}",
            "EVAL_ACCUMULATION_WORKFLOW_SELECTION_REPORTS="
            f"{eval_report_count(report, 'workflow-selection')}",
            f"EVAL_ACCUMULATION_REPORT_QUALITY_REPORTS={eval_report_count(report, 'report-quality')}",
            f"EVAL_ACCUMULATION_CODEX_AGENT_ROLE_REPORTS={eval_report_count(report, 'codex-agent-role')}",
            *eval_family_count_lines(report),
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
    try:
        report = validate(args.root, str(args.family_registry))
    except RuntimeError as error:
        if "AgentCanon log archive root is required" not in str(error):
            raise
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "status": "error",
                        "error_code": "log_archive_required",
                        "message": str(error),
                        "next_action": "mount .agent-canon/log-archive or set AGENT_CANON_HOOK_ARCHIVE_DIR",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("EVAL_ACCUMULATION=error")
            print("EVAL_ACCUMULATION_ERROR_CODE=log_archive_required")
            print(f"EVAL_ACCUMULATION_ERROR={error}")
            print("NEXT_ACTION=mount_.agent-canon/log-archive_or_set_AGENT_CANON_HOOK_ARCHIVE_DIR")
        return 1
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
