#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Verifies that root agent instruction entrypoints remain thin owner maps instead of procedural policy stores.
# upstream design ../../documents/design/entrypoint-owner-map.md structural grammar and owner-map contract
# upstream implementation ./convention_compliance_contracts.toml operational marker ownership manifest
# downstream implementation ../../tests/agent_tools/test_check_entrypoint_owner_map.py focused regression
# downstream implementation ../../.github/workflows/entrypoint-owner-map.yml remote verification
# @dependency-end
"""Validate the structural owner-map contract for root instruction files."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class EntrypointContract:
    """Structural contract for one root instruction file."""

    path: str
    title: str
    headings: tuple[str, ...]
    owner_rows: tuple[tuple[str, ...], ...]


CONTRACTS = (
    EntrypointContract(
        path="AGENTS.md",
        title="# AgentCanon Repository Instructions",
        headings=(
            "## Repository Role",
            "## Reader Map",
            "## Always-On Boundary",
            "## Runtime Owner Map",
            "## Task Entry",
            "## Validation Routing",
        ),
        owner_rows=(
            (
                "root runtime entrypoint",
                "ROOT_AGENTS.md",
                "PYTHONPATH=tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check",
            ),
            (
                "workflow family, spawn budget, role topology",
                "agents/task_catalog.yaml",
                "check_agent_runtime_alignment.py",
            ),
            (
                "public skill registry",
                "agents/skills/catalog.yaml",
                "check_agent_runtime_alignment.py",
            ),
            (
                "AgentCanon update transaction",
                "documents/agent-canon/agent-canon-update-route.md",
                "update_lifecycle_contract.py",
            ),
            (
                "entrypoint responsibility grammar",
                "documents/design/entrypoint-owner-map.md",
                "check_entrypoint_owner_map.py",
            ),
        ),
    ),
    EntrypointContract(
        path="ROOT_AGENTS.md",
        title="# AgentCanon Live-Integration Repository Instructions",
        headings=(
            "## Integration Role",
            "## Reader Map",
            "## Always-On Boundary",
            "## Runtime Owner Map",
            "## Task Entry",
            "## Validation Routing",
        ),
        owner_rows=(
            (
                "workflow family, spawn budget, role topology",
                "vendor/agent-canon/agents/task_catalog.yaml",
                "check_agent_runtime_alignment.py",
            ),
            (
                "task bootstrap and CLI entrypoints",
                "vendor/agent-canon/agents/canonical/CLI_ENTRYPOINTS.md",
                "bootstrap_agent_run.py",
            ),
            (
                "subagent lifecycle, same-role instances, wave ledger",
                "vendor/agent-canon/agents/canonical/CODEX_SUBAGENTS.md",
                "workflow_monitor.py",
            ),
            (
                "role behavior and stage conditions",
                "vendor/agent-canon/.codex/agents/*.toml",
                "check_agent_runtime_alignment.py",
            ),
            (
                "skill routing and public skill surface",
                "vendor/agent-canon/agents/skills/catalog.yaml",
                "python3 vendor/agent-canon/tools/agent_tools/route.py --prompt",
            ),
            (
                "report and closeout structure",
                "task_close.py",
                "closeout gate",
            ),
            (
                "entrypoint responsibility grammar",
                "vendor/agent-canon/documents/design/entrypoint-owner-map.md",
                "check_entrypoint_owner_map.py",
            ),
        ),
    ),
)

MARKER_MANIFEST_PATH = "tools/agent_tools/convention_compliance_contracts.toml"
ROOT_ENTRYPOINT_PATHS = frozenset(contract.path for contract in CONTRACTS)

H1_RE = re.compile(r"^#(?!#)\s+\S")
H2_RE = re.compile(r"^##(?!#)\s+\S")
NESTED_HEADING_RE = re.compile(r"^#{3,}\s+\S")
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
ORDERED_PROCEDURE_RE = re.compile(r"^\s*\d+[.)]\s+\S")
DIRECT_COMMAND_RE = re.compile(
    r"^\s*(?:"
    r"python(?:3(?:\.\d+)?)?|bash|sh|git|make|cargo|npm|npx|docker|"
    r"tools/[A-Za-z0-9_./-]+|PYTHONPATH=\S+|AGENT_CANON_[A-Z0-9_]+=\S+"
    r")(?:\s|$)"
)
BULLET_COMMAND_RE = re.compile(
    r"^\s*[-*]\s+(?:`)?(?:"
    r"python(?:3(?:\.\d+)?)?|bash|sh|git|make|cargo|npm|npx|docker|"
    r"tools/[A-Za-z0-9_./-]+|PYTHONPATH=\S+|AGENT_CANON_[A-Z0-9_]+=\S+"
    r")(?:`|\s|$)"
)


@dataclass(frozen=True)
class Finding:
    """One stable entrypoint-contract finding."""

    path: str
    rule: str
    detail: str
    line: int | None = None

    def render(self) -> str:
        """Render a stable text finding."""
        location = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"ENTRYPOINT_OWNER_MAP_FINDING={self.rule}:{location}:{self.detail}"


def _section_lines(lines: Sequence[str], heading: str) -> list[str] | None:
    """Return one level-2 section body."""
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return None
    section: list[str] = []
    for line in lines[start + 1 :]:
        if H2_RE.match(line.strip()):
            break
        section.append(line)
    return section


def _table_rows(lines: Sequence[str]) -> tuple[str, ...]:
    """Return Markdown table data rows, excluding header separators."""
    rows: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(cell and set(cell) <= set("-: ") for cell in cells):
            continue
        rows.append(stripped)
    return tuple(rows)


def check_entrypoint(root: Path, contract: EntrypointContract) -> list[Finding]:
    """Validate one entrypoint against its structural contract."""
    target = root / contract.path
    if not target.is_file():
        return [Finding(contract.path, "file", "missing")]

    text = target.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[Finding] = []

    h1 = [(index + 1, line.strip()) for index, line in enumerate(lines) if H1_RE.match(line)]
    if len(h1) != 1:
        findings.append(Finding(contract.path, "title", f"h1-count={len(h1)}"))
    elif h1[0][1] != contract.title:
        findings.append(
            Finding(contract.path, "title", f"expected={contract.title!r}", h1[0][0])
        )

    actual_headings = tuple(line.strip() for line in lines if H2_RE.match(line))
    if actual_headings != contract.headings:
        findings.append(
            Finding(
                contract.path,
                "heading-sequence",
                f"expected={contract.headings!r};actual={actual_headings!r}",
            )
        )

    for line_number, line in enumerate(lines, start=1):
        if NESTED_HEADING_RE.match(line):
            findings.append(
                Finding(contract.path, "nested-heading", line.strip(), line_number)
            )
        if FENCE_RE.match(line):
            findings.append(Finding(contract.path, "fenced-recipe", line.strip(), line_number))
        if ORDERED_PROCEDURE_RE.match(line):
            findings.append(
                Finding(contract.path, "ordered-procedure", line.strip(), line_number)
            )
        if DIRECT_COMMAND_RE.match(line) or BULLET_COMMAND_RE.match(line):
            findings.append(
                Finding(contract.path, "command-recipe", line.strip(), line_number)
            )

    owner_section = _section_lines(lines, "## Runtime Owner Map")
    if owner_section is None:
        findings.append(Finding(contract.path, "owner-map", "missing-section"))
    else:
        rows = _table_rows(owner_section)
        for markers in contract.owner_rows:
            if not any(all(marker in row for marker in markers) for row in rows):
                findings.append(
                    Finding(contract.path, "owner-map", f"missing-row={markers[0]}")
                )

    return findings


def check_marker_manifest(root: Path) -> list[Finding]:
    """Reject operational marker contracts that re-own root entrypoint prose."""
    target = root / MARKER_MANIFEST_PATH
    if not target.is_file():
        return [Finding(MARKER_MANIFEST_PATH, "marker-manifest", "missing")]

    try:
        payload = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [
            Finding(
                MARKER_MANIFEST_PATH,
                "marker-manifest",
                f"parse-error={type(exc).__name__}",
            )
        ]

    contracts = payload.get("contracts")
    if not isinstance(contracts, list):
        return [Finding(MARKER_MANIFEST_PATH, "marker-manifest", "contracts-not-list")]

    findings: list[Finding] = []
    for contract in contracts:
        if not isinstance(contract, dict):
            findings.append(
                Finding(MARKER_MANIFEST_PATH, "marker-manifest", "contract-not-table")
            )
            continue
        contract_id = str(contract.get("id", "<missing>"))
        surfaces = contract.get("surfaces", [])
        if not isinstance(surfaces, list):
            findings.append(
                Finding(
                    MARKER_MANIFEST_PATH,
                    "marker-manifest",
                    f"contract={contract_id};surfaces-not-list",
                )
            )
            continue
        for surface in surfaces:
            if not isinstance(surface, dict):
                findings.append(
                    Finding(
                        MARKER_MANIFEST_PATH,
                        "marker-manifest",
                        f"contract={contract_id};surface-not-table",
                    )
                )
                continue
            surface_path = surface.get("path")
            if surface_path in ROOT_ENTRYPOINT_PATHS:
                findings.append(
                    Finding(
                        MARKER_MANIFEST_PATH,
                        "delegated-marker-surface",
                        f"contract={contract_id};path={surface_path}",
                    )
                )
    return findings


def run_checks(root: Path) -> list[Finding]:
    """Run all root entrypoint checks."""
    findings = [
        finding
        for contract in CONTRACTS
        for finding in check_entrypoint(root, contract)
    ]
    findings.extend(check_marker_manifest(root))
    return sorted(
        findings,
        key=lambda finding: (
            finding.path,
            finding.line if finding.line is not None else -1,
            finding.rule,
            finding.detail,
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Verify that AGENTS.md entrypoints are thin canonical owner maps."
    )
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the checker and return non-zero on findings."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    findings = run_checks(root)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "status": "pass" if not findings else "fail",
                    "checked": [contract.path for contract in CONTRACTS],
                    "findings": [asdict(finding) for finding in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for finding in findings:
            print(finding.render())
        print(f"ENTRYPOINT_OWNER_MAP_FINDINGS={len(findings)}")
        print(f"ENTRYPOINT_OWNER_MAP={'pass' if not findings else 'fail'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
