#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Reports Lean proof-obligation coverage for cataloged AgentCanon tools.
# upstream design ../../tools/catalog.yaml structured AgentCanon tool catalog
# upstream design ../../agents/skills/formal-proof-workflow.md formal proof status policy
# upstream design ../../documents/tools/lean_capability_matrix.md Lean capability routing policy
# upstream implementation ../../tools/agent_tools/tool_catalog.py validates tool catalog rows
# downstream design ../../documents/tools/tool_proof_coverage.md documents proof coverage reports
# downstream implementation ../../tests/agent_tools/test_tool_proof_coverage.py tests proof coverage reporting
# @dependency-end
"""Report formal proof-obligation coverage for cataloged AgentCanon tools."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml
from tool_catalog import (
    CATALOG_PATH,
    as_mapping,
    as_sequence,
    resolve_repo_path,
    validate_catalog,
)

LEAN_VERIFIED = "lean_verified"
INVALID_LEAN_VERIFIED = "invalid_lean_verified"
UNVERIFIED = "unverified_with_next_witness"
EXTERNAL_ASSUMPTION = "external_assumption_required"
TEST_EVIDENCE_ONLY = "test_evidence_only"
PROOF_ESCAPE_RE = re.compile(r"\b(sorry|admit|axiom)\b")


@dataclass(frozen=True)
class Finding:
    """One proof coverage validation finding."""

    check: str
    tool_id: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return f"TOOL_PROOF_COVERAGE_FINDING={self.check}:{self.tool_id}:{self.detail}"


@dataclass(frozen=True)
class ProofClaim:
    """Proof status for one behavior or performance claim."""

    status: str
    theorem: str | None
    artifact: str | None
    checker: str | None
    next_witness: str


@dataclass(frozen=True)
class ToolProofRow:
    """Proof coverage row for one cataloged tool."""

    tool_id: str
    path: str
    role: str
    writes: bool
    docs: tuple[str, ...]
    tests: tuple[str, ...]
    performance_model: str
    behavior: ProofClaim
    performance: ProofClaim


@dataclass(frozen=True)
class ProofCoverageReport:
    """Complete proof coverage report."""

    findings: tuple[Finding, ...]
    rows: tuple[ToolProofRow, ...]
    require_lean_verified: bool


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument(
        "--require-lean-verified",
        action="store_true",
        help="Fail unless every behavior and performance claim is Lean verified.",
    )
    return parser


def load_catalog_entries(root: Path) -> tuple[list[Mapping[str, object]], list[Finding]]:
    """Load raw catalog entries after reusing the catalog validator."""
    report = validate_catalog(root)
    findings = [
        Finding("catalog", finding.path, finding.detail) for finding in report.findings
    ]
    catalog_path = resolve_repo_path(root, CATALOG_PATH)
    if findings or not catalog_path.is_file():
        return [], findings
    data = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    catalog = as_mapping(data)
    if catalog is None:
        return [], [Finding("catalog", CATALOG_PATH, "must-parse-as-mapping")]
    entries_raw = as_sequence(catalog.get("entries"))
    if entries_raw is None:
        return [], [Finding("catalog", CATALOG_PATH, "entries-must-be-list")]
    entries: list[Mapping[str, object]] = []
    for raw_entry in entries_raw:
        entry = as_mapping(raw_entry)
        if entry is not None:
            entries.append(entry)
    return entries, findings


def string_tuple(value: object) -> tuple[str, ...]:
    """Return a tuple of strings from a YAML sequence."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        return ()
    sequence = cast(Sequence[object], value)
    return tuple(item for item in sequence if isinstance(item, str))


def entry_bool(entry: Mapping[str, object], key: str) -> bool:
    """Return an explicitly true boolean entry value."""
    return entry.get(key) is True


def performance_model_for(role: str, writes: bool) -> str:
    """Classify the cost-model shape needed before a Lean performance proof."""
    if role in {"catalog", "checker", "inventory", "docs"}:
        return "bounded_catalog_or_file_scan"
    if role in {"runner", "sync", "workflow", "experiment"}:
        return "external_command_or_runtime"
    if writes:
        return "bounded_artifact_write"
    return "command_contract"


def default_claim(kind: str, tool_id: str, role: str, tests: tuple[str, ...]) -> ProofClaim:
    """Return the default unverified claim for a catalog row."""
    if kind == "behavior" and tests:
        status = TEST_EVIDENCE_ONLY
        witness = f"Lean theorem binding {tool_id} behavior spec to implementation model"
    elif role in {"runner", "sync", "workflow", "experiment"} and kind == "performance":
        status = EXTERNAL_ASSUMPTION
        witness = f"explicit runtime/backend cost axiom plus Lean theorem for {tool_id}"
    else:
        status = UNVERIFIED
        witness = f"Lean theorem and checked proof artifact for {tool_id} {kind}"
    return ProofClaim(
        status=status,
        theorem=None,
        artifact=None,
        checker=None,
        next_witness=witness,
    )


def proof_claim_from_entry(
    root: Path,
    entry: Mapping[str, object],
    kind: str,
    default: ProofClaim,
) -> tuple[ProofClaim, list[Finding]]:
    """Read an optional declared proof claim and validate its evidence."""
    tool_id = str(entry.get("id") or "<missing-id>")
    proofs = as_mapping(entry.get("proofs"))
    if proofs is None:
        return default, []
    raw_claim = as_mapping(proofs.get(kind))
    if raw_claim is None:
        return default, []
    status = raw_claim.get("status")
    if status != LEAN_VERIFIED:
        return non_verified_claim(raw_claim, default), []
    return verified_claim_from_metadata(root, tool_id, kind, raw_claim)


def non_verified_claim(raw_claim: Mapping[str, object], default: ProofClaim) -> ProofClaim:
    """Return a declared non-verified proof claim."""
    theorem = raw_claim.get("theorem")
    artifact = raw_claim.get("artifact")
    checker = raw_claim.get("checker")
    next_witness = raw_claim.get("next_witness")
    status = raw_claim.get("status")
    return ProofClaim(
        status=str(status or default.status),
        theorem=theorem if isinstance(theorem, str) else None,
        artifact=artifact if isinstance(artifact, str) else None,
        checker=checker if isinstance(checker, str) else None,
        next_witness=next_witness if isinstance(next_witness, str) else default.next_witness,
    )


def verified_claim_from_metadata(
    root: Path,
    tool_id: str,
    kind: str,
    raw_claim: Mapping[str, object],
) -> tuple[ProofClaim, list[Finding]]:
    """Return a Lean-verified claim plus metadata findings."""
    theorem = raw_claim.get("theorem")
    artifact = raw_claim.get("artifact")
    checker = raw_claim.get("checker")
    checked = raw_claim.get("checked")
    findings: list[Finding] = []
    if checked is not True:
        findings.append(Finding("proof", tool_id, f"{kind}-lean-verified-requires-checked-true"))
    if not isinstance(theorem, str) or not theorem.strip():
        findings.append(Finding("proof", tool_id, f"{kind}-lean-verified-missing-theorem"))
    if not isinstance(checker, str) or not checker.strip():
        findings.append(Finding("proof", tool_id, f"{kind}-lean-verified-missing-checker"))
    findings.extend(validate_proof_artifact(root, tool_id, kind, artifact))
    status = INVALID_LEAN_VERIFIED if findings else LEAN_VERIFIED
    next_witness = f"repair Lean proof metadata for {tool_id} {kind}" if findings else "none"
    return ProofClaim(
        status=status,
        theorem=theorem if isinstance(theorem, str) else None,
        artifact=artifact if isinstance(artifact, str) else None,
        checker=checker if isinstance(checker, str) else None,
        next_witness=next_witness,
    ), findings


def validate_proof_artifact(
    root: Path,
    tool_id: str,
    kind: str,
    artifact: object,
) -> list[Finding]:
    """Validate one declared Lean proof artifact path."""
    if not isinstance(artifact, str) or not artifact.strip():
        return [Finding("proof", tool_id, f"{kind}-lean-verified-missing-artifact")]
    artifact_path = resolve_repo_path(root, artifact)
    if not artifact_path.is_file():
        return [Finding("proof", tool_id, f"{kind}-proof-artifact-missing:{artifact}")]
    text = artifact_path.read_text(encoding="utf-8")
    if PROOF_ESCAPE_RE.search(text):
        return [Finding("proof", tool_id, f"{kind}-proof-artifact-has-escape")]
    return []


def row_from_entry(root: Path, entry: Mapping[str, object]) -> tuple[ToolProofRow, list[Finding]]:
    """Build one proof coverage row from a catalog entry."""
    tool_id = str(entry.get("id") or "<missing-id>")
    path = str(entry.get("path") or "<missing-path>")
    role = str(entry.get("role") or "<missing-role>")
    writes = entry_bool(entry, "writes")
    docs = string_tuple(entry.get("docs"))
    tests = string_tuple(entry.get("tests"))
    performance_model = performance_model_for(role, writes)
    behavior, behavior_findings = proof_claim_from_entry(
        root,
        entry,
        "behavior",
        default_claim("behavior", tool_id, role, tests),
    )
    performance, performance_findings = proof_claim_from_entry(
        root,
        entry,
        "performance",
        default_claim("performance", tool_id, role, tests),
    )
    row = ToolProofRow(
        tool_id=tool_id,
        path=path,
        role=role,
        writes=writes,
        docs=docs,
        tests=tests,
        performance_model=performance_model,
        behavior=behavior,
        performance=performance,
    )
    return row, behavior_findings + performance_findings


def build_report(root: Path, require_lean_verified: bool = False) -> ProofCoverageReport:
    """Build a proof coverage report for all cataloged tools."""
    root = root.resolve()
    entries, findings = load_catalog_entries(root)
    rows: list[ToolProofRow] = []
    for entry in entries:
        row, row_findings = row_from_entry(root, entry)
        rows.append(row)
        findings.extend(row_findings)
        if require_lean_verified and row.behavior.status != LEAN_VERIFIED:
            findings.append(Finding("coverage", row.tool_id, "behavior-not-lean-verified"))
        if require_lean_verified and row.performance.status != LEAN_VERIFIED:
            findings.append(Finding("coverage", row.tool_id, "performance-not-lean-verified"))
    findings = sorted(findings, key=lambda finding: (finding.check, finding.tool_id, finding.detail))
    return ProofCoverageReport(tuple(findings), tuple(rows), require_lean_verified)


def render_json(report: ProofCoverageReport) -> str:
    """Render JSON output."""
    payload = {
        "status": "pass" if not report.findings else "fail",
        "require_lean_verified": report.require_lean_verified,
        "findings": [asdict(finding) for finding in report.findings],
        "rows": [asdict(row) for row in report.rows],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def markdown_cell(value: object) -> str:
    """Render a safe Markdown table cell."""
    return str(value).replace("|", "\\|")


def render_markdown(report: ProofCoverageReport) -> str:
    """Render a Markdown proof coverage table."""
    lines = [
        "# Tool Proof Coverage",
        "",
        f"- Status: `{'pass' if not report.findings else 'fail'}`",
        f"- Tools: `{len(report.rows)}`",
        f"- Findings: `{len(report.findings)}`",
        f"- Require Lean verified: `{'yes' if report.require_lean_verified else 'no'}`",
        "",
        "| Tool | Behavior Status | Performance Status | Performance Model | Next Witness |",
        "| ---- | --------------- | ------------------ | ----------------- | ------------ |",
    ]
    for row in report.rows:
        lines.append(
            "| "
            f"`{markdown_cell(row.tool_id)}` | "
            f"{markdown_cell(row.behavior.status)} | "
            f"{markdown_cell(row.performance.status)} | "
            f"{markdown_cell(row.performance_model)} | "
            f"{markdown_cell(row.behavior.next_witness)}; "
            f"{markdown_cell(row.performance.next_witness)} |"
        )
    if report.findings:
        lines.extend(["", "## Findings", "", "| Check | Tool | Detail |", "| ----- | ---- | ------ |"])
        for finding in report.findings:
            lines.append(
                "| "
                f"{markdown_cell(finding.check)} | "
                f"`{markdown_cell(finding.tool_id)}` | "
                f"{markdown_cell(finding.detail)} |"
            )
    return "\n".join(lines)


def count_status(rows: Sequence[ToolProofRow], kind: str) -> Counter[str]:
    """Count behavior or performance proof statuses."""
    if kind == "behavior":
        return Counter(row.behavior.status for row in rows)
    return Counter(row.performance.status for row in rows)


def render_text(report: ProofCoverageReport) -> str:
    """Render compact machine-readable text output."""
    behavior_counts = count_status(report.rows, "behavior")
    performance_counts = count_status(report.rows, "performance")
    lines = [finding.render() for finding in report.findings]
    lines.extend(
        [
            f"TOOL_PROOF_COVERAGE_TOOLS={len(report.rows)}",
            f"TOOL_PROOF_COVERAGE_BEHAVIOR_LEAN_VERIFIED={behavior_counts[LEAN_VERIFIED]}",
            f"TOOL_PROOF_COVERAGE_PERFORMANCE_LEAN_VERIFIED={performance_counts[LEAN_VERIFIED]}",
            f"TOOL_PROOF_COVERAGE_BEHAVIOR_TEST_EVIDENCE_ONLY={behavior_counts[TEST_EVIDENCE_ONLY]}",
            f"TOOL_PROOF_COVERAGE_PERFORMANCE_EXTERNAL_ASSUMPTION={performance_counts[EXTERNAL_ASSUMPTION]}",
            f"TOOL_PROOF_COVERAGE_REQUIRE_LEAN_VERIFIED={'yes' if report.require_lean_verified else 'no'}",
            f"TOOL_PROOF_COVERAGE_FINDINGS={len(report.findings)}",
            f"TOOL_PROOF_COVERAGE={'pass' if not report.findings else 'fail'}",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the proof coverage reporter."""
    args = build_parser().parse_args(argv)
    report = build_report(Path(args.root), require_lean_verified=bool(args.require_lean_verified))
    if args.format == "json":
        print(render_json(report))
    elif args.format == "markdown":
        print(render_markdown(report))
    else:
        print(render_text(report))
    return 1 if report.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
