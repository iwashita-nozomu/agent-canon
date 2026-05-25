#!/usr/bin/env python3
# @dependency-start
# responsibility Validates AgentCanon hook/eval log management boundaries.
# upstream design ../../agents/evals/results/README.md eval result storage contract
# upstream design ../../agents/evals/results/hook-runs/README.md hook result accumulation contract
# upstream implementation ../../tools/update_agent_canon.sh parks eval logs
# downstream implementation ../../tools/ci/run_all_checks.sh runs log management checks
# downstream implementation ../../tests/agent_tools/test_agent_canon_log_management_check.py tests
# @dependency-end
"""Check AgentCanon hook/eval log management boundaries."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

EVAL_RESULTS_PREFIX = "agents/evals/results/"
HOOK_RESULTS_PATH = Path("agents/evals/results/hook-runs")


@dataclass(frozen=True)
class Finding:
    """One AgentCanon log management finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"AGENT_CANON_LOG_MANAGEMENT_FINDING={self.check}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class LogManagementReport:
    """AgentCanon log management report."""

    canon_root: str
    git_branch: str
    dirty_eval_log_paths: int
    hook_files: int
    hook_entries: int
    hook_legacy_missing_namespace: int
    findings: tuple[Finding, ...]


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def agent_canon_root(root: Path) -> Path:
    """Return AgentCanon source root for standalone or parent invocation."""
    resolved = root.resolve()
    vendored = resolved / "vendor" / "agent-canon"
    if (vendored / "agents" / "evals" / "results").is_dir():
        return vendored
    return resolved


def relative(root: Path, path: Path) -> str:
    """Return a stable root-relative path."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def status_path(line: str) -> str:
    """Extract the changed path from one porcelain status line."""
    path = line[3:]
    if " -> " in path:
        path = path.rsplit(" -> ", maxsplit=1)[-1]
    return path


def is_accumulated_result_path(path: str) -> bool:
    """Return whether a dirty path is an accumulated eval/hook result artifact."""
    return path.startswith(EVAL_RESULTS_PREFIX) and not path.endswith("/README.md") and (
        path.endswith(".jsonl") or path.endswith(".md")
    )


def git_output(root: Path, args: Sequence[str]) -> str:
    """Return stdout for a git command, or an empty string outside git."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def current_branch(root: Path) -> str:
    """Return the current git branch or detached."""
    branch = git_output(root, ["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
    return branch or "detached"


def dirty_eval_log_findings(root: Path, branch: str) -> tuple[int, list[Finding]]:
    """Return findings for dirty eval logs in the wrong management branch."""
    status = git_output(root, ["status", "--porcelain=v1", "--untracked-files=all"])
    dirty_log_paths = [
        status_path(line)
        for line in status.splitlines()
        if is_accumulated_result_path(status_path(line))
    ]
    if branch.startswith("agent-logs/"):
        return len(dirty_log_paths), []
    return (
        len(dirty_log_paths),
        [
            Finding(
                "dirty_log_branch",
                path,
                f"dirty-eval-log-on-{branch};park-with-tools/update_agent_canon.sh-latest",
            )
            for path in dirty_log_paths
        ],
    )


def hook_namespace_findings(root: Path) -> tuple[int, int, int, list[Finding]]:
    """Validate hook log namespace ownership inside JSONL files."""
    hook_dir = root / HOOK_RESULTS_PATH
    files = sorted(hook_dir.rglob("*.jsonl")) if hook_dir.is_dir() else []
    findings: list[Finding] = []
    entries = 0
    legacy_missing_namespace = 0
    for path in files:
        namespaced = path.parent.name != "hook-runs"
        expected_namespace = path.parent.name
        for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw_line.strip():
                continue
            entries += 1
            label = f"{relative(root, path)}:{line_no}"
            try:
                loaded = json.loads(raw_line)
            except json.JSONDecodeError:
                findings.append(Finding("hook_jsonl", label, "invalid-json"))
                continue
            if not isinstance(loaded, dict):
                findings.append(Finding("hook_jsonl", label, "entry-not-object"))
                continue
            entry = cast(dict[str, object], loaded)
            namespace = entry.get("hook_log_namespace")
            if namespaced and not isinstance(namespace, str):
                legacy_missing_namespace += 1
                continue
            if namespaced and namespace != expected_namespace:
                findings.append(
                    Finding(
                        "hook_log_namespace",
                        label,
                        f"entry={namespace};path={expected_namespace}",
                    )
                )
    return len(files), entries, legacy_missing_namespace, findings


def validate(root: Path) -> LogManagementReport:
    """Validate AgentCanon log management boundaries."""
    canon_root = agent_canon_root(root)
    branch = current_branch(canon_root)
    dirty_count, findings = dirty_eval_log_findings(canon_root, branch)
    hook_files, hook_entries, legacy_missing_namespace, hook_findings = hook_namespace_findings(
        canon_root
    )
    findings.extend(hook_findings)
    return LogManagementReport(
        canon_root=canon_root.as_posix(),
        git_branch=branch,
        dirty_eval_log_paths=dirty_count,
        hook_files=hook_files,
        hook_entries=hook_entries,
        hook_legacy_missing_namespace=legacy_missing_namespace,
        findings=tuple(sorted(findings, key=lambda item: (item.check, item.path, item.detail))),
    )


def render_json(report: LogManagementReport) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "status": "pass" if not report.findings else "fail",
            "canon_root": report.canon_root,
            "git_branch": report.git_branch,
            "dirty_eval_log_paths": report.dirty_eval_log_paths,
            "hook_files": report.hook_files,
            "hook_entries": report.hook_entries,
            "hook_legacy_missing_namespace": report.hook_legacy_missing_namespace,
            "findings": [asdict(item) for item in report.findings],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the AgentCanon log management checker."""
    args = build_parser().parse_args(argv)
    report = validate(args.root)
    if args.format == "json":
        print(render_json(report))
    else:
        for finding in report.findings:
            print(finding.render())
        print(f"AGENT_CANON_LOG_MANAGEMENT_CANON_ROOT={report.canon_root}")
        print(f"AGENT_CANON_LOG_MANAGEMENT_GIT_BRANCH={report.git_branch}")
        print(f"AGENT_CANON_LOG_MANAGEMENT_DIRTY_EVAL_LOG_PATHS={report.dirty_eval_log_paths}")
        print(f"AGENT_CANON_LOG_MANAGEMENT_HOOK_FILES={report.hook_files}")
        print(f"AGENT_CANON_LOG_MANAGEMENT_HOOK_ENTRIES={report.hook_entries}")
        print(
            "AGENT_CANON_LOG_MANAGEMENT_HOOK_LEGACY_MISSING_NAMESPACE="
            f"{report.hook_legacy_missing_namespace}"
        )
        print(f"AGENT_CANON_LOG_MANAGEMENT_FINDINGS={len(report.findings)}")
        print(f"AGENT_CANON_LOG_MANAGEMENT={'pass' if not report.findings else 'fail'}")
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
