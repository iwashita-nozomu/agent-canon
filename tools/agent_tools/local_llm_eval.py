#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Runs configurable local LLM single-file responsibility evals.
# upstream design ../../evidence/agent-evals/README.md eval directory contract
# upstream design ../../documents/runtime-log-archive.md eval result archive contract
# upstream design ../../evidence/agent-evals/local_llm_responsibility_eval.toml local LLM eval manifest
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and mount policy
# upstream implementation ./runtime_log_paths.py resolves accumulated eval archive paths
# upstream design ../../documents/local-llm-responsibility-analysis.md single-file local LLM scope policy
# upstream design ../../tools/catalog.yaml structured tool catalog
# upstream design ../../tools/README.md tool entrypoint index
# upstream design ../../documents/tools/README.md user-facing tool index
# upstream implementation ../../rust/agent-canon/src/local_llm.rs routes local LLM eval command
# upstream implementation ./file_responsibility_llm.py renders prompts and runs llama.cpp
# downstream implementation ../../tools/ci/run_all_checks.sh runs local LLM eval checks
# downstream implementation ../../tests/agent_tools/test_local_llm_eval.py tests eval harness behavior
# @dependency-end
"""Run local LLM single-file responsibility evals."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
import tomllib

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_manifest_paths import eval_manifest_path, resolve_eval_manifest  # noqa: E402
from file_responsibility_llm import (  # noqa: E402
    DEFAULT_MAX_BYTES,
    DEFAULT_MODEL,
    find_llama_cli,
    prompt_digest,
    prompt_for_target,
    read_target,
)
from runtime_log_paths import agent_canon_root, eval_results_dir  # noqa: E402

MANIFEST_PATH = eval_manifest_path("local_llm_responsibility_eval.toml")
RESULTS_FAMILY = "local-llm-responsibility"
RUN_ID_PREFIX = "local-llm-eval"
STATUS_VALUES = ("pass", "fail", "skip")
RUN_ID_DIGEST_LENGTH = 10


@dataclass(frozen=True)
class Finding:
    """One local LLM eval finding."""

    check: str
    case_id: str
    detail: str

    def render(self) -> str:
        """Render one machine-readable finding."""
        return f"LOCAL_LLM_EVAL_FINDING={self.check}:{self.case_id}:{self.detail}"


@dataclass(frozen=True)
class EvalCase:
    """One configured local LLM eval case."""

    case_id: str
    target: str
    description: str
    required_prompt_regex: tuple[str, ...]
    forbidden_prompt_regex: tuple[str, ...]
    required_llm_regex: tuple[str, ...]
    forbidden_llm_regex: tuple[str, ...]


@dataclass(frozen=True)
class CaseResult:
    """Result for one local LLM eval case."""

    case_id: str
    target: str
    status: str
    prompt_sha: str
    llm_status: str
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class EvalReport:
    """Complete local LLM eval report."""

    run_id: str
    status: str
    model: str
    run_llm: bool
    cases: tuple[CaseResult, ...]
    report_path: str

    @property
    def findings(self) -> tuple[Finding, ...]:
        """Return all case findings."""
        return tuple(finding for case in self.cases for finding in case.findings)


class LocalLlmEvalRunner:
    """Run configured single-file responsibility evals."""

    def __init__(
        self,
        root: Path,
        manifest_path: Path,
        model: str,
        llama_cli: str,
        run_llm: bool,
        require_llm: bool,
    ) -> None:
        """Create one eval runner with resolved AgentCanon paths."""
        self.root = agent_canon_root(root.resolve())
        self.manifest_path = resolve_eval_manifest(self.root, manifest_path)
        self.model = model
        self.llama_cli = llama_cli
        self.run_llm = run_llm
        self.require_llm = require_llm

    def run(self) -> EvalReport:
        """Run all configured cases and return a report."""
        cases, manifest_findings = load_manifest(self.root, self.manifest_path)
        run_id = make_run_id(self.manifest_path.read_text(encoding="utf-8") if self.manifest_path.is_file() else "")
        case_results = [
            CaseResult(
                case_id=finding.case_id,
                target="<manifest>",
                status="fail",
                prompt_sha="",
                llm_status="not_run",
                findings=(finding,),
            )
            for finding in manifest_findings
        ]
        case_results.extend(self.run_case(case) for case in cases)
        status = report_status(case_results)
        return EvalReport(
            run_id=run_id,
            status=status,
            model=self.model,
            run_llm=self.run_llm,
            cases=tuple(case_results),
            report_path="",
        )

    def run_case(self, case: EvalCase) -> CaseResult:
        """Run one eval case."""
        findings: list[Finding] = []
        try:
            target = read_target(self.root, case.target, max_bytes=DEFAULT_MAX_BYTES)
        except ValueError as exc:
            return CaseResult(
                case_id=case.case_id,
                target=case.target,
                status="fail",
                prompt_sha="",
                llm_status="not_run",
                findings=(Finding("target", case.case_id, str(exc)),),
            )
        prompt = prompt_for_target(target)
        findings.extend(regex_findings("prompt", case.case_id, prompt, case.required_prompt_regex, True))
        findings.extend(regex_findings("prompt", case.case_id, prompt, case.forbidden_prompt_regex, False))
        llm_status = "not_run"
        if self.run_llm:
            llm_status, llm_findings = self.run_llm_case(case)
            findings.extend(llm_findings)
        status = case_status(findings, llm_status)
        return CaseResult(
            case_id=case.case_id,
            target=case.target,
            status=status,
            prompt_sha=prompt_digest(prompt),
            llm_status=llm_status,
            findings=tuple(findings),
        )

    def run_llm_case(self, case: EvalCase) -> tuple[str, tuple[Finding, ...]]:
        """Run the model-backed portion of one eval case."""
        executable = find_llama_cli(self.llama_cli)
        if not executable:
            if self.require_llm:
                return "fail", (Finding("llm", case.case_id, "llama-cli-not-found"),)
            return "unavailable", ()
        command = [
            sys.executable,
            str(Path(__file__).with_name("file_responsibility_llm.py")),
            "--root",
            str(self.root),
            "--model",
            self.model,
            "--llama-cli",
            executable,
            case.target,
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        output = result.stdout + "\n" + result.stderr
        findings: list[Finding] = []
        if result.returncode != 0:
            findings.append(Finding("llm", case.case_id, f"returncode:{result.returncode}"))
        findings.extend(regex_findings("llm", case.case_id, output, case.required_llm_regex, True))
        findings.extend(regex_findings("llm", case.case_id, output, case.forbidden_llm_regex, False))
        return ("pass" if not findings else "fail"), tuple(findings)


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", default=MANIFEST_PATH)
    parser.add_argument("--model", default=os.environ.get("AGENT_CANON_LOCAL_LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--llama-cli", default=os.environ.get("AGENT_CANON_LLAMA_CLI", ""))
    parser.add_argument("--run-llm", action="store_true")
    parser.add_argument("--require-llm", action="store_true")
    parser.add_argument("--accumulate", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def string_tuple(value: object) -> tuple[str, ...]:
    """Return a tuple of strings from a TOML list value."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def mappings(value: object) -> tuple[Mapping[str, object], ...]:
    """Return a tuple of string-keyed mappings."""
    if not isinstance(value, list):
        return ()
    result: list[Mapping[str, object]] = []
    for item in cast(list[object], value):
        if isinstance(item, Mapping) and all(isinstance(key, str) for key in item):
            result.append(cast(Mapping[str, object], item))
    return tuple(result)


def compile_findings(case_id: str, field: str, patterns: Sequence[str]) -> list[Finding]:
    """Return findings for invalid regex patterns."""
    findings: list[Finding] = []
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            findings.append(Finding("manifest", case_id, f"invalid-regex:{field}:{pattern}:{exc}"))
    return findings


def case_from_mapping(raw: Mapping[str, object]) -> tuple[EvalCase | None, list[Finding]]:
    """Parse one manifest eval case."""
    case_id = raw.get("id")
    target = raw.get("target")
    findings: list[Finding] = []
    if not isinstance(case_id, str) or not case_id:
        case_id = "<missing-id>"
        findings.append(Finding("manifest", case_id, "missing-id"))
    if not isinstance(target, str) or not target:
        target = ""
        findings.append(Finding("manifest", case_id, "missing-target"))
    required_prompt = string_tuple(raw.get("required_prompt_regex"))
    forbidden_prompt = string_tuple(raw.get("forbidden_prompt_regex"))
    required_llm = string_tuple(raw.get("required_llm_regex"))
    forbidden_llm = string_tuple(raw.get("forbidden_llm_regex"))
    for field, patterns in (
        ("required_prompt_regex", required_prompt),
        ("forbidden_prompt_regex", forbidden_prompt),
        ("required_llm_regex", required_llm),
        ("forbidden_llm_regex", forbidden_llm),
    ):
        findings.extend(compile_findings(case_id, field, patterns))
    if findings:
        return None, findings
    return EvalCase(
        case_id=case_id,
        target=target,
        description=str(raw.get("description") or ""),
        required_prompt_regex=required_prompt,
        forbidden_prompt_regex=forbidden_prompt,
        required_llm_regex=required_llm,
        forbidden_llm_regex=forbidden_llm,
    ), []


def load_manifest(root: Path, path: Path) -> tuple[tuple[EvalCase, ...], list[Finding]]:
    """Load the local LLM eval manifest."""
    if not path.is_file():
        return (), [Finding("manifest", "<manifest>", f"missing-file:{relative(root, path)}")]
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return (), [Finding("manifest", "<manifest>", f"toml-decode:{exc}")]
    if data.get("catalog_kind") != "agent_canon_local_llm_responsibility_eval":
        return (), [Finding("manifest", "<manifest>", "invalid-catalog-kind")]
    cases: list[EvalCase] = []
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for raw_case in mappings(data.get("evals")):
        case, case_findings = case_from_mapping(raw_case)
        findings.extend(case_findings)
        if case is None:
            continue
        previous = seen.get(case.case_id)
        if previous is not None:
            findings.append(Finding("manifest", case.case_id, f"duplicate-id:{previous}"))
            continue
        if not (root / case.target).is_file():
            findings.append(Finding("manifest", case.case_id, f"missing-target:{case.target}"))
            continue
        seen[case.case_id] = case.target
        cases.append(case)
    if not cases and not findings:
        findings.append(Finding("manifest", "<manifest>", "no-eval-cases"))
    return tuple(cases), findings


def regex_findings(
    check: str,
    case_id: str,
    text: str,
    patterns: Sequence[str],
    required: bool,
) -> list[Finding]:
    """Return regex match findings for one text."""
    findings: list[Finding] = []
    for pattern in patterns:
        matched = re.search(pattern, text, re.MULTILINE) is not None
        if required and not matched:
            findings.append(Finding(check, case_id, f"missing-regex:{pattern}"))
        if not required and matched:
            findings.append(Finding(check, case_id, f"forbidden-regex:{pattern}"))
    return findings


def case_status(findings: Sequence[Finding], llm_status: str) -> str:
    """Return one case status."""
    if findings:
        return "fail"
    if llm_status == "unavailable":
        return "skip"
    return "pass"


def report_status(results: Sequence[CaseResult]) -> str:
    """Return aggregate status."""
    if any(result.status == "fail" for result in results):
        return "fail"
    if any(result.status == "skip" for result in results):
        return "skip"
    return "pass"


def make_run_id(seed: str) -> str:
    """Return a unique local LLM eval run id."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha256(f"{timestamp}\n{seed}".encode()).hexdigest()[:RUN_ID_DIGEST_LENGTH]
    return f"{RUN_ID_PREFIX}-{timestamp}-{digest}"


def relative(root: Path, path: Path) -> str:
    """Return a stable root-relative path."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def report_markdown(report: EvalReport) -> str:
    """Render an accumulated Markdown report."""
    lines = [
        "<!--",
        "@dependency-start",
        "responsibility Records one local LLM responsibility eval result.",
        "upstream implementation ../../../../tools/agent_tools/local_llm_eval.py generates this report",
        "upstream design ../../../../evidence/agent-evals/local_llm_responsibility_eval.toml defines local LLM eval cases",
        "@dependency-end",
        "-->",
        "",
        "# Local LLM Responsibility Eval Result",
        "",
        f"- LOCAL_LLM_EVAL_RUN_ID={report.run_id}",
        f"- LOCAL_LLM_EVAL_STATUS={report.status}",
        f"- LOCAL_LLM_EVAL_MODEL={report.model}",
        f"- LOCAL_LLM_EVAL_RUN_LLM={str(report.run_llm).lower()}",
        "",
        "## Cases",
        "",
    ]
    for case in report.cases:
        lines.extend(
            [
                f"### {case.case_id}",
                "",
                f"- target: `{case.target}`",
                f"- status: `{case.status}`",
                f"- llm_status: `{case.llm_status}`",
                f"- prompt_sha: `{case.prompt_sha}`",
                "",
            ]
        )
        if case.findings:
            lines.append("Findings:")
            lines.append("")
            lines.extend(f"- `{finding.check}`: {finding.detail}" for finding in case.findings)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_accumulated_report(root: Path, report: EvalReport) -> EvalReport:
    """Write an append-only report and return a report with path populated."""
    result_dir = eval_results_dir(root, RESULTS_FAMILY)
    result_dir.mkdir(parents=True, exist_ok=True)
    path = result_dir / f"{report.run_id}-{report.status}.md"
    path.write_text(report_markdown(report), encoding="utf-8")
    return EvalReport(
        run_id=report.run_id,
        status=report.status,
        model=report.model,
        run_llm=report.run_llm,
        cases=report.cases,
        report_path=relative(root, path),
    )


def render_json(report: EvalReport) -> str:
    """Render JSON output."""
    return json.dumps(
        {
            "run_id": report.run_id,
            "status": report.status,
            "model": report.model,
            "run_llm": report.run_llm,
            "report_path": report.report_path,
            "cases": [asdict(item) for item in report.cases],
        },
        indent=2,
        sort_keys=True,
    )


def render_text(report: EvalReport) -> str:
    """Render text output."""
    lines: list[str] = []
    for finding in report.findings:
        lines.append(finding.render())
    lines.extend(
        [
            f"LOCAL_LLM_EVAL_RUN_ID={report.run_id}",
            f"LOCAL_LLM_EVAL_MODEL={report.model}",
            f"LOCAL_LLM_EVAL_RUN_LLM={str(report.run_llm).lower()}",
            f"LOCAL_LLM_EVAL_CASES={len(report.cases)}",
            f"LOCAL_LLM_EVAL_FINDINGS={len(report.findings)}",
            f"LOCAL_LLM_EVAL={report.status}",
        ]
    )
    if report.report_path:
        lines.append(f"LOCAL_LLM_EVAL_ACCUMULATED_REPORT={report.report_path}")
    return "\n".join(lines)


def print_text_report(report: EvalReport) -> None:
    """Print text output with statically discoverable machine-readable fields."""
    for finding in report.findings:
        print(finding.render())
    print(f"LOCAL_LLM_EVAL_RUN_ID={report.run_id}")
    print(f"LOCAL_LLM_EVAL_MODEL={report.model}")
    print(f"LOCAL_LLM_EVAL_RUN_LLM={str(report.run_llm).lower()}")
    print(f"LOCAL_LLM_EVAL_CASES={len(report.cases)}")
    print(f"LOCAL_LLM_EVAL_FINDINGS={len(report.findings)}")
    print(f"LOCAL_LLM_EVAL={report.status}")
    if report.report_path:
        print(f"LOCAL_LLM_EVAL_ACCUMULATED_REPORT={report.report_path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run local LLM evals."""
    args = build_parser().parse_args(argv)
    root = agent_canon_root(args.root.resolve())
    runner = LocalLlmEvalRunner(
        root=root,
        manifest_path=Path(args.manifest),
        model=args.model,
        llama_cli=args.llama_cli,
        run_llm=args.run_llm,
        require_llm=args.require_llm,
    )
    report = runner.run()
    if args.accumulate:
        report = write_accumulated_report(root, report)
    if args.format == "json":
        print(render_json(report))
    else:
        print_text_report(report)
    return 1 if report.status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
