#!/usr/bin/env python3
# @dependency-start
# responsibility Validates append-only AgentCanon eval and hook result accumulation.
# upstream design ../../agents/evals/README.md eval usage contract
# upstream design ../../agents/evals/results/README.md eval result storage contract
# upstream design ../../agents/evals/results/hook-runs/README.md hook result accumulation contract
# upstream design ../../agents/evals/results/local-llm-responsibility/README.md local LLM eval result accumulation contract
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
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

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
    skill_reports: int
    local_llm_reports: int
    findings: tuple[Finding, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def agent_canon_root(root: Path) -> Path:
    """Return AgentCanon source root for standalone or parent invocation."""
    vendored = root / "vendor" / "agent-canon"
    if (vendored / "agents" / "evals" / "results").is_dir():
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


def required_directory_findings(root: Path) -> list[Finding]:
    """Validate required eval result directories."""
    findings: list[Finding] = []
    for path in (
        root / "agents" / "evals" / "results",
        root / "agents" / "evals" / "results" / "hook-runs",
        root / "agents" / "evals" / "results" / "skill-workflow-prompt",
        root / "agents" / "evals" / "results" / "local-llm-responsibility",
    ):
        if not path.is_dir():
            findings.append(Finding("directory", relative(root, path), "missing"))
    return findings


def ignored_path_findings(root: Path, paths: Sequence[Path]) -> list[Finding]:
    """Return findings for result files ignored by git."""
    return [
        Finding("gitignore", relative(root, path), "ignored-result-path")
        for path in paths
        if git_check_ignored(root, path)
    ]


def parse_hook_line(root: Path, path: Path, line_no: int, raw_line: str) -> tuple[str, list[Finding]]:
    """Parse one hook JSONL line and return its run id plus findings."""
    label = f"{relative(root, path)}:{line_no}"
    try:
        loaded = json.loads(raw_line)
    except json.JSONDecodeError:
        return "", [Finding("hook_jsonl", label, "invalid-json")]
    if not isinstance(loaded, dict):
        return "", [Finding("hook_jsonl", label, "entry-not-object")]
    entry = cast(dict[str, object], loaded)
    namespaced = path.parent.name != "hook-runs"
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
    if namespaced and not isinstance(entry.get("hook_log_namespace"), str):
        findings.append(Finding("hook_jsonl", label, "missing-field:hook_log_namespace"))
    run_id = entry.get("hook_run_id")
    return (run_id if isinstance(run_id, str) else ""), findings


def hook_result_findings(root: Path, hook_dir: Path) -> tuple[int, int, list[Finding]]:
    """Validate hook JSONL files."""
    findings: list[Finding] = []
    seen_run_ids: dict[str, str] = {}
    files = sorted(hook_dir.rglob("*.jsonl")) if hook_dir.is_dir() else []
    entries = 0
    for path in files:
        for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw_line.strip():
                continue
            entries += 1
            run_id, line_findings = parse_hook_line(root, path, line_no, raw_line)
            findings.extend(line_findings)
            if not run_id:
                continue
            previous = seen_run_ids.get(run_id)
            label = f"{relative(root, path)}:{line_no}"
            if previous is not None:
                findings.append(Finding("hook_run_id", label, f"duplicate:{previous}"))
            seen_run_ids[run_id] = label
    if not files:
        findings.append(Finding("hook_jsonl", relative(root, hook_dir), "no-hook-jsonl"))
    if files and entries == 0:
        findings.append(Finding("hook_jsonl", relative(root, hook_dir), "no-hook-entries"))
    findings.extend(ignored_path_findings(root, files))
    return len(files), entries, findings


def eval_run_id_from_text(text: str) -> str:
    """Extract an eval run id from current or legacy report text."""
    current = re.search(r"\bEVAL_RUN_ID=([A-Za-z0-9_.:-]+)", text)
    if current:
        return current.group(1)
    legacy = re.search(r"eval_run_id:\s*`?([A-Za-z0-9_.:-]+)`?", text)
    return legacy.group(1) if legacy else ""


def skill_eval_findings(root: Path, results_dir: Path) -> tuple[int, list[Finding]]:
    """Validate accumulated skill/workflow prompt eval reports."""
    findings: list[Finding] = []
    reports = sorted(path for path in results_dir.glob("*.md") if path.name != "README.md")
    seen_run_ids: dict[str, str] = {}
    if not reports:
        findings.append(Finding("skill_eval", relative(root, results_dir), "no-skill-eval-reports"))
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


def local_llm_eval_findings(root: Path, results_dir: Path) -> tuple[int, list[Finding]]:
    """Validate accumulated local LLM responsibility eval reports."""
    findings: list[Finding] = []
    reports = sorted(path for path in results_dir.glob("*.md") if path.name != "README.md")
    seen_run_ids: dict[str, str] = {}
    if not reports:
        findings.append(Finding("local_llm_eval", relative(root, results_dir), "no-local-llm-eval-reports"))
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


def validate(root: Path) -> EvalAccumulationReport:
    """Validate accumulated eval results."""
    canon_root = agent_canon_root(root.resolve())
    findings = required_directory_findings(canon_root)
    hook_files, hook_entries, hook_findings = hook_result_findings(
        canon_root,
        canon_root / "agents" / "evals" / "results" / "hook-runs",
    )
    skill_reports, skill_findings = skill_eval_findings(
        canon_root,
        canon_root / "agents" / "evals" / "results" / "skill-workflow-prompt",
    )
    local_llm_reports, local_llm_findings = local_llm_eval_findings(
        canon_root,
        canon_root / "agents" / "evals" / "results" / "local-llm-responsibility",
    )
    findings.extend(hook_findings)
    findings.extend(skill_findings)
    findings.extend(local_llm_findings)
    return EvalAccumulationReport(
        hook_files=hook_files,
        hook_entries=hook_entries,
        skill_reports=skill_reports,
        local_llm_reports=local_llm_reports,
        findings=tuple(sorted(findings, key=lambda item: (item.check, item.path, item.detail))),
    )


def render_json(report: EvalAccumulationReport) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": "pass" if not report.findings else "fail",
            "hook_files": report.hook_files,
            "hook_entries": report.hook_entries,
            "skill_reports": report.skill_reports,
            "local_llm_reports": report.local_llm_reports,
            "findings": [asdict(item) for item in report.findings],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the eval accumulation checker."""
    args = build_parser().parse_args(argv)
    report = validate(args.root)
    if args.format == "json":
        print(render_json(report))
    else:
        for finding in report.findings:
            print(finding.render())
        print(f"EVAL_ACCUMULATION_HOOK_FILES={report.hook_files}")
        print(f"EVAL_ACCUMULATION_HOOK_ENTRIES={report.hook_entries}")
        print(f"EVAL_ACCUMULATION_SKILL_REPORTS={report.skill_reports}")
        print(f"EVAL_ACCUMULATION_LOCAL_LLM_REPORTS={report.local_llm_reports}")
        print(f"EVAL_ACCUMULATION_FINDINGS={len(report.findings)}")
        print(f"EVAL_ACCUMULATION={'pass' if not report.findings else 'fail'}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
