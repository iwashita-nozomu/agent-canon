#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Detects drift between tool contracts, convention docs, and dependency manifests.
# upstream design ../../documents/dependency-manifest-design.md dependency manifest graph semantics
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md PR validation contract
# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md subagent wave routing contract
# upstream design ../../agents/TASK_WORKFLOWS.md workflow routing contract
# upstream design ../../agents/skills/agent-orchestration.md orchestration routing contract
# upstream design ../../.agents/skills/agent-orchestration/SKILL.md runtime orchestration skill prompt
# upstream design ../../evidence/agent-evals/skill_workflow_prompt_eval.toml prompt routing eval contract
# upstream design ../../documents/REVIEW_PROCESS.md closeout validation policy
# upstream design ../../tools/catalog.yaml structured tool catalog
# upstream design ../../documents/tools/tool-docs.toml one-to-one tool documentation map
# upstream implementation ./tool_catalog.py validates catalog structure
# upstream implementation ./check_convention_compliance.py verifies skill-routing markers
# upstream implementation ./tool_path_policy.py defines retired legacy path policy
# downstream implementation ../../tools/ci/run_all_checks.sh runs drift checker
# downstream implementation ../../tests/agent_tools/test_tool_drift.py tests checker
# @dependency-end
"""Check tool/convention drift using dependency manifests as the trace map."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml
from tool_path_policy import (
    is_retired_legacy_tool_path,
    iter_retired_legacy_tool_paths,
    retired_legacy_tool_detail,
)

HEADER_SCAN_LINES = 80
MANIFEST_FIELD_COUNT = 4
MANIFEST_REASON_MAX_SPLIT = MANIFEST_FIELD_COUNT - 1


@dataclass(frozen=True)
class ManifestEdge:
    """One dependency manifest edge."""

    direction: str
    kind: str
    source: str
    target: str


@dataclass(frozen=True)
class LinkCheck:
    """One required tool-to-surface trace."""

    target: str
    direct_required: bool = True
    reverse_required: bool = False


@dataclass(frozen=True)
class TextCheck:
    """One required text snippet for a tool contract."""

    path: str
    snippet: str
    detail: str


@dataclass(frozen=True)
class ToolContract:
    """One tool/convention consistency contract."""

    name: str
    tool: str
    links: tuple[LinkCheck, ...]
    text_checks: tuple[TextCheck, ...] = ()


@dataclass(frozen=True)
class Finding:
    """One tool/convention drift finding."""

    kind: str
    contract: str
    path: str
    detail: str

    def render(self) -> str:
        """Render a stable machine-readable finding."""
        return (
            "TOOL_CONVENTION_DRIFT_FINDING="
            f"{self.kind}:{self.contract}:{self.path}:{self.detail}"
        )


CONTRACTS = (
    ToolContract(
        name="github_pr_flow",
        tool="tools/ci/check_github_workflows.py",
        links=(
            LinkCheck("agents/workflows/agent-canon-pr-workflow.md"),
            LinkCheck(".github/AGENTS.md"),
            LinkCheck(".github/PULL_REQUEST_TEMPLATE.md"),
            LinkCheck(".github/PULL_REQUEST_TEMPLATE/agent_canon.md"),
            LinkCheck(".github/workflows/agent-coordination.yml"),
            LinkCheck("tools/ci/checkout_agent_canon_submodule.sh"),
            LinkCheck("README.md"),
        ),
        text_checks=(
            TextCheck(
                ".github/workflows/agent-coordination.yml",
                "tools/ci/checkout_agent_canon_submodule.sh",
                "missing-standalone-checkout-helper-route",
            ),
        ),
    ),
    ToolContract(
        name="tool_catalog",
        tool="tools/agent_tools/tool_catalog.py",
        links=(
            LinkCheck("tools/catalog.yaml", reverse_required=True),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("documents/tools/tool-docs.toml"),
            LinkCheck("documents/repo-local-tool-imports.md"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck("tests/agent_tools/test_tool_catalog.py"),
        ),
        text_checks=(
            TextCheck(
                "tools/README.md",
                "tools/catalog.yaml",
                "missing-tool-catalog-pointer",
            ),
            TextCheck(
                "documents/tools/README.md",
                "tools/catalog.yaml",
                "missing-tool-catalog-pointer",
            ),
            TextCheck(
                "documents/tools/README.md",
                "documents/tools/tool-docs.toml",
                "missing-tool-docs-pointer",
            ),
            TextCheck(
                "documents/repo-local-tool-imports.md",
                "tools/catalog.yaml",
                "missing-tool-catalog-pointer",
            ),
        ),
    ),
    ToolContract(
        name="responsibility_scope",
        tool="tools/agent_tools/responsibility_scope.py",
        links=(
            LinkCheck("responsibility-scope.toml"),
            LinkCheck("documents/templates/responsibility-scope.template.toml"),
            LinkCheck("documents/responsibility-scope-management.md"),
            LinkCheck("tools/catalog.yaml"),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck("tests/agent_tools/test_responsibility_scope.py"),
        ),
    ),
    ToolContract(
        name="import_responsibility",
        tool="tools/agent_tools/import_responsibility.py",
        links=(
            LinkCheck("responsibility-scope.toml"),
            LinkCheck("documents/responsibility-scope-management.md"),
            LinkCheck("documents/coding-conventions-python.md"),
            LinkCheck("tools/catalog.yaml"),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck("tests/agent_tools/test_import_responsibility.py"),
        ),
    ),
    ToolContract(
        name="tool_rejection_preflight",
        tool="tools/agent_tools/tool_rejection_preflight.py",
        links=(
            LinkCheck("agents/COMMUNICATION_PROTOCOL.md"),
            LinkCheck("agents/skills/codex-task-workflow.md"),
            LinkCheck(".agents/skills/codex-task-workflow/SKILL.md"),
            LinkCheck("agents/skills/owner-bounded-routing.md"),
            LinkCheck(".agents/skills/owner-bounded-routing/SKILL.md"),
            LinkCheck("tools/agent_tools/responsibility_scope.py"),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("tests/agent_tools/test_tool_rejection_preflight.py"),
        ),
        text_checks=(
            TextCheck(
                "agents/COMMUNICATION_PROTOCOL.md",
                "`responsibility_scope` gate records",
                "missing-responsibility-scope-preflight-protocol",
            ),
            TextCheck(
                ".agents/skills/codex-task-workflow/SKILL.md",
                "responsibility_scope",
                "missing-runtime-workflow-responsibility-preflight",
            ),
            TextCheck(
                ".agents/skills/owner-bounded-routing/SKILL.md",
                "responsibility_scope",
                "missing-runtime-small-change-responsibility-preflight",
            ),
        ),
    ),
    ToolContract(
        name="local_llm_eval",
        tool="tools/agent_tools/local_llm_eval.py",
        links=(
            LinkCheck("evidence/agent-evals/README.md"),
            LinkCheck("evidence/agent-evals/local_llm_responsibility_eval.toml"),
            LinkCheck("documents/runtime-log-archive.md"),
            LinkCheck("documents/local-llm-responsibility-analysis.md"),
            LinkCheck("tools/catalog.yaml"),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck("tests/agent_tools/test_local_llm_eval.py"),
        ),
    ),
    ToolContract(
        name="agent_canon_local_llm",
        tool="rust/agent-canon/src/local_llm.rs",
        links=(
            LinkCheck("agent-canon-environment.toml"),
            LinkCheck("documents/local-llm-responsibility-analysis.md"),
            LinkCheck("documents/search-coordination.md"),
            LinkCheck("documents/rust-agent-tool-migration.md"),
            LinkCheck("tools/catalog.yaml"),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck(".github/workflows/agent-canon-static-gates.yml"),
        ),
    ),
    ToolContract(
        name="issue_sync",
        tool="tools/agent_tools/issue_sync.py",
        links=(
            LinkCheck("issues/README.md"),
            LinkCheck("documents/responsibility-scope-management.md"),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck("tests/agent_tools/test_issue_sync.py"),
        ),
    ),
    ToolContract(
        name="eval_accumulation",
        tool="tools/agent_tools/eval_accumulation_check.py",
        links=(
            LinkCheck("evidence/agent-evals/README.md"),
            LinkCheck("documents/runtime-log-archive.md"),
            LinkCheck("documents/runtime-log-archive-migration.md"),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck("tests/agent_tools/test_eval_accumulation_check.py"),
        ),
    ),
    ToolContract(
        name="run_accumulated_agent_evals",
        tool="tools/agent_tools/run_accumulated_agent_evals.py",
        links=(
            LinkCheck("evidence/agent-evals/README.md"),
            LinkCheck("documents/runtime-log-archive.md"),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("tools/catalog.yaml"),
            LinkCheck("tools/ci/check_agent_canon_pr.sh"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck(".github/workflows/agent-canon-static-gates.yml"),
            LinkCheck("tests/agent_tools/test_run_accumulated_agent_evals.py"),
        ),
    ),
    ToolContract(
        name="generated_artifact_guard",
        tool="tools/agent_tools/generated_artifact_guard.py",
        links=(
            LinkCheck("tools/agent_tools/report_artifact_checks.py"),
            LinkCheck("tools/README.md"),
            LinkCheck("documents/tools/README.md"),
            LinkCheck("tools/catalog.yaml"),
            LinkCheck("tools/ci/check_agent_canon_pr.sh"),
            LinkCheck("agents/canonical/ARTIFACT_PLACEMENT.md"),
            LinkCheck("agents/templates/closeout_gate.md"),
            LinkCheck("tests/agent_tools/test_generated_artifact_guard.py"),
        ),
        text_checks=(
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "python3 tools/agent_tools/generated_artifact_guard.py",
                "missing-generated-artifact-pr-guard",
            ),
        ),
    ),
    ToolContract(
        name="agent_canon_pr_check",
        tool="tools/ci/check_agent_canon_pr.sh",
        links=(
            LinkCheck("agents/workflows/agent-canon-pr-workflow.md"),
            LinkCheck(".github/PULL_REQUEST_TEMPLATE.md"),
            LinkCheck(".github/PULL_REQUEST_TEMPLATE/agent_canon.md"),
            LinkCheck("tools/agent_tools/run_repo_dependency_review.sh"),
            LinkCheck("tools/agent_tools/run_accumulated_agent_evals.py"),
            LinkCheck("tools/agent_tools/generated_artifact_guard.py"),
            LinkCheck("tools/agent_tools/evaluate_skill_workflow_prompts.py"),
            LinkCheck("tools/agent_tools/check_agent_runtime_alignment.py"),
            LinkCheck("tools/agent_tools/check_convention_compliance.py"),
            LinkCheck("tools/ci/check_github_workflows.py"),
            LinkCheck("tools/ci/run_all_checks.sh"),
        ),
        text_checks=(
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "run_repo_dependency_review.sh --fail-missing",
                "missing-strict-dependency-review",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "check_agent_runtime_alignment.py",
                "missing-agent-runtime-alignment-check",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "run_accumulated_agent_evals.py --run-id agent-canon-pr-gate",
                "missing-accumulated-agent-eval-producer",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                'AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}"',
                "missing-agent-canon-pr-hook-archive-env",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "python3 tools/agent_tools/generated_artifact_guard.py",
                "missing-generated-artifact-pr-guard",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "not_applicable_standalone_source",
                "missing-standalone-shared-surface-skip",
            ),
        ),
    ),
    ToolContract(
        name="convention_compliance",
        tool="tools/agent_tools/check_convention_compliance.py",
        links=(
            LinkCheck("documents/conventions/README.md"),
            LinkCheck("agents/canonical/CODEX_WORKFLOW.md"),
            LinkCheck("agents/canonical/CODEX_SUBAGENTS.md"),
            LinkCheck("agents/TASK_WORKFLOWS.md"),
            LinkCheck("agents/skills/agent-orchestration.md"),
            LinkCheck(".agents/skills/agent-orchestration/SKILL.md"),
            LinkCheck("evidence/agent-evals/skill_workflow_prompt_eval.toml"),
            LinkCheck("agents/templates/closeout_gate.md"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck("tools/agent_tools/tool_drift.py"),
        ),
    ),
    ToolContract(
        name="subagent_wave_routing",
        tool="tools/agent_tools/tool_drift.py",
        links=(
            LinkCheck("agents/canonical/CODEX_SUBAGENTS.md"),
            LinkCheck("agents/TASK_WORKFLOWS.md"),
            LinkCheck("agents/skills/agent-orchestration.md"),
            LinkCheck(".agents/skills/agent-orchestration/SKILL.md"),
            LinkCheck("evidence/agent-evals/skill_workflow_prompt_eval.toml"),
            LinkCheck("tools/agent_tools/check_convention_compliance.py"),
            LinkCheck("tests/agent_tools/test_tool_drift.py"),
        ),
        text_checks=(
            TextCheck(
                "agents/canonical/CODEX_SUBAGENTS.md",
                "vertical dynamic wave",
                "missing-canonical-vertical-wave-policy",
            ),
            TextCheck(
                "agents/canonical/CODEX_SUBAGENTS.md",
                "write-capable handoff",
                "missing-canonical-write-capable-handoff-policy",
            ),
            TextCheck(
                "agents/skills/agent-orchestration.md",
                "vertical dynamic wave",
                "missing-orchestration-vertical-wave-policy",
            ),
            TextCheck(
                "agents/skills/agent-orchestration.md",
                "write-capable handoff",
                "missing-orchestration-write-capable-handoff-policy",
            ),
            TextCheck(
                ".agents/skills/agent-orchestration/SKILL.md",
                "vertical dynamic wave",
                "missing-runtime-orchestration-vertical-wave-policy",
            ),
            TextCheck(
                ".agents/skills/agent-orchestration/SKILL.md",
                "write-capable handoff",
                "missing-runtime-orchestration-write-capable-handoff-policy",
            ),
            TextCheck(
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "VERTICAL-WAVE-POLICY",
                "missing-vertical-wave-prompt-eval",
            ),
            TextCheck(
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "write-capable handoff",
                "missing-write-capable-handoff-prompt-eval",
            ),
        ),
    ),
    ToolContract(
        name="repo_dependency_review",
        tool="tools/agent_tools/run_repo_dependency_review.sh",
        links=(
            LinkCheck("documents/dependency-manifest-design.md"),
            LinkCheck("agents/canonical/CODEX_WORKFLOW.md"),
            LinkCheck("agents/templates/closeout_gate.md"),
            LinkCheck(".github/PULL_REQUEST_TEMPLATE.md"),
            LinkCheck(".github/PULL_REQUEST_TEMPLATE/agent_canon.md"),
            LinkCheck("tools/ci/check_agent_canon_pr.sh"),
        ),
    ),
    ToolContract(
        name="container_config",
        tool="tools/ci/container_config.py",
        links=(
            LinkCheck("documents/coding-conventions-project.md"),
            LinkCheck("agents/skills/environment-maintenance.md"),
            LinkCheck("tools/docker_dependency_validator.sh"),
            LinkCheck("tools/ci/container_runtime.py"),
            LinkCheck("tools/ci/run_container_pack.py"),
            LinkCheck("tools/ci/run_all_checks.sh"),
            LinkCheck("tests/tools/test_container_config.py"),
        ),
        text_checks=(
            TextCheck(
                "agents/skills/environment-maintenance.md",
                "tools/ci/container_config.py",
                "missing-container-config-validator",
            ),
            TextCheck(
                "documents/tools/README.md",
                "tools/ci/container_config.py",
                "missing-container-config-entrypoint",
            ),
        ),
    ),
)


def as_mapping(value: object) -> dict[str, object] | None:
    """Return value as a string-keyed mapping when possible."""
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return None
    return cast(dict[str, object], mapping)


def as_sequence(value: object) -> Sequence[object] | None:
    """Return value as a non-string sequence."""
    if isinstance(value, str):
        return None
    if isinstance(value, Sequence):
        return cast(Sequence[object], value)
    return None


def has_dependency_manifest(path: Path) -> bool:
    """Return whether one file has dependency manifest markers near the top."""
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()[:HEADER_SCAN_LINES]
    return any("@dependency-start" in line for line in lines) and any(
        "@dependency-end" in line for line in lines
    )


def resolve_repo_path(root: Path, relative_path: str) -> Path:
    """Resolve a path through the root view or vendored AgentCanon source."""
    root_path = root / relative_path
    if root_path.exists():
        return root_path
    vendor_path = root / "vendor" / "agent-canon" / relative_path
    if vendor_path.exists():
        return vendor_path
    return root_path


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--contract",
        action="append",
        default=[],
        choices=tuple(contract.name for contract in CONTRACTS),
        help="Limit checks to one contract. May be repeated.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def strip_manifest_line(line: str) -> str:
    """Strip common comment syntax from one manifest line."""
    stripped = line.rstrip("\r").strip()
    for prefix in ("#", "//", "*"):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
    stripped = stripped.rstrip(",").strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        stripped = stripped[1:-1]
    return stripped.strip()


def repo_relative(root: Path, path: Path) -> str:
    """Return a stable repository-relative path."""
    absolute_root = Path(os.path.normpath(root.absolute().as_posix()))
    absolute_path = Path(os.path.normpath(path.absolute().as_posix()))
    try:
        relative = absolute_path.relative_to(absolute_root).as_posix()
    except ValueError:
        return path.as_posix()
    vendor_prefix = "vendor/agent-canon/"
    if relative.startswith(vendor_prefix):
        return relative[len(vendor_prefix) :]
    return relative


def normalize_target(root: Path, source: Path, relative_target: str) -> str:
    """Normalize one manifest target relative to its source file."""
    return repo_relative(root, source.parent / relative_target)


def manifest_edges(root: Path, relative_path: str) -> tuple[ManifestEdge, ...]:
    """Extract dependency manifest edges from one file."""
    path = resolve_repo_path(root, relative_path)
    if not path.is_file():
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()[:HEADER_SCAN_LINES]
    in_manifest = False
    edges: list[ManifestEdge] = []
    source = repo_relative(root, path)
    for line in lines:
        stripped = strip_manifest_line(line)
        if stripped == "@dependency-start":
            in_manifest = True
            continue
        if stripped == "@dependency-end":
            break
        if not in_manifest or not stripped:
            continue
        if stripped in {"<!--", "-->", "/*", "*/", '"""', "'''"}:
            continue
        fields = stripped.split(maxsplit=MANIFEST_REASON_MAX_SPLIT)
        if len(fields) < MANIFEST_FIELD_COUNT:
            continue
        direction, kind, target_path, _reason = fields
        if direction not in {"upstream", "downstream"}:
            continue
        edges.append(
            ManifestEdge(
                direction=direction,
                kind=kind,
                source=source,
                target=normalize_target(root, path, target_path),
            )
        )
    return tuple(edges)


def opposite_direction(direction: str) -> str:
    """Return the reverse dependency direction."""
    return "downstream" if direction == "upstream" else "upstream"


def compatible_reverse_kind(direct: ManifestEdge, reverse: ManifestEdge) -> bool:
    """Return whether a direct/reverse pair has compatible edge kinds."""
    if direct.kind == reverse.kind:
        return True
    return (
        direct.direction == "upstream"
        and direct.kind == "design"
        and reverse.direction == "downstream"
        and reverse.kind == "implementation"
    ) or (
        direct.direction == "downstream"
        and direct.kind == "implementation"
        and reverse.direction == "upstream"
        and reverse.kind == "design"
    )


def matching_direct_edges(
    edges: Sequence[ManifestEdge], tool: str, target: str
) -> tuple[ManifestEdge, ...]:
    """Return direct tool-to-target manifest edges."""
    return tuple(edge for edge in edges if edge.source == tool and edge.target == target)


def matching_reverse_edges(
    edges: Sequence[ManifestEdge], tool: str, target: str
) -> tuple[ManifestEdge, ...]:
    """Return target-to-tool manifest edges."""
    return tuple(edge for edge in edges if edge.source == target and edge.target == tool)


def check_link(
    contract: ToolContract,
    link: LinkCheck,
    all_edges: Sequence[ManifestEdge],
) -> list[Finding]:
    """Check one required manifest link."""
    direct = matching_direct_edges(all_edges, contract.tool, link.target)
    reverse = matching_reverse_edges(all_edges, contract.tool, link.target)
    if not direct and not reverse:
        return [
            Finding(
                "missing-manifest-link",
                contract.name,
                contract.tool,
                link.target,
            )
        ]
    findings: list[Finding] = []
    if link.direct_required and not direct:
        findings.append(
            Finding(
                "missing-direct-manifest-link",
                contract.name,
                contract.tool,
                link.target,
            )
        )
    if link.reverse_required and not reverse:
        findings.append(
            Finding(
                "missing-reverse-manifest-link",
                contract.name,
                contract.tool,
                link.target,
            )
        )
    for direct_edge in direct:
        for reverse_edge in reverse:
            if reverse_edge.direction != opposite_direction(direct_edge.direction):
                continue
            if not compatible_reverse_kind(direct_edge, reverse_edge):
                findings.append(
                    Finding(
                        "kind-mismatch",
                        contract.name,
                        contract.tool,
                        (
                            f"{link.target}:{direct_edge.direction} "
                            f"{direct_edge.kind} != {reverse_edge.direction} "
                            f"{reverse_edge.kind}"
                        ),
                    )
                )
    return findings


def check_text(root: Path, contract: ToolContract, text_check: TextCheck) -> list[Finding]:
    """Check one required snippet."""
    path = resolve_repo_path(root, text_check.path)
    if not path.is_file():
        return [
            Finding("missing-file", contract.name, text_check.path, text_check.detail)
        ]
    text = path.read_text(encoding="utf-8")
    if text_check.snippet in text:
        return []
    return [
        Finding("missing-required-text", contract.name, text_check.path, text_check.detail)
    ]


def check_catalog_entries(root: Path) -> list[Finding]:
    """Check catalog entries for stale paths and legacy/default confusion."""
    catalog_path = resolve_repo_path(root, "tools/catalog.yaml")
    if not catalog_path.is_file():
        return [Finding("missing-file", "tool_catalog", "tools/catalog.yaml", "catalog")]
    if not has_dependency_manifest(catalog_path):
        return [Finding("missing-dependency-header", "tool_catalog", "tools/catalog.yaml", "catalog")]
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    catalog = as_mapping(raw)
    if catalog is None:
        return [Finding("invalid-catalog", "tool_catalog", "tools/catalog.yaml", "not-mapping")]
    entries = as_sequence(catalog.get("entries"))
    if entries is None:
        return [Finding("invalid-catalog", "tool_catalog", "tools/catalog.yaml", "entries-not-list")]
    findings: list[Finding] = []
    catalog_retired_paths: set[str] = set()
    for index, raw_entry in enumerate(entries, start=1):
        entry = as_mapping(raw_entry)
        if entry is None:
            findings.append(
                Finding("invalid-catalog-entry", "tool_catalog", "tools/catalog.yaml", f"entry-{index}-not-mapping")
            )
            continue
        entry_path = entry.get("path")
        status = entry.get("status")
        if not isinstance(entry_path, str):
            findings.append(
                Finding("invalid-catalog-entry", "tool_catalog", "tools/catalog.yaml", f"entry-{index}-missing-path")
            )
            continue
        if not resolve_repo_path(root, entry_path).exists():
            findings.append(
                Finding("stale-catalog-entry", "tool_catalog", entry_path, "missing-path")
            )
        if is_retired_legacy_tool_path(entry_path) or status == "legacy_provenance":
            catalog_retired_paths.add(entry_path.replace("\\", "/").removeprefix("./"))
            findings.append(
                Finding(
                    "retired-legacy-tool",
                    "tool_catalog",
                    entry_path,
                    "legacy-tools-are-retired",
                )
            )
    for retired_path in iter_retired_legacy_tool_paths(root):
        if retired_path in catalog_retired_paths:
            continue
        findings.append(
            Finding(
                "retired-legacy-tool",
                "tool_catalog",
                retired_path,
                retired_legacy_tool_detail(retired_path),
            )
        )
    return findings


def selected_contracts(names: Sequence[str]) -> tuple[ToolContract, ...]:
    """Return selected contracts."""
    if not names:
        return CONTRACTS
    selected = set(names)
    return tuple(contract for contract in CONTRACTS if contract.name in selected)


def run_checks(root: Path, names: Sequence[str]) -> list[Finding]:
    """Run drift checks."""
    contracts = selected_contracts(names)
    paths = sorted(
        {
            path
            for contract in contracts
            for path in (
                contract.tool,
                *(link.target for link in contract.links),
                *(text_check.path for text_check in contract.text_checks),
            )
        }
    )
    all_edges: list[ManifestEdge] = []
    for path in paths:
        all_edges.extend(manifest_edges(root, path))
    findings: list[Finding] = []
    for contract in contracts:
        if not resolve_repo_path(root, contract.tool).is_file():
            findings.append(
                Finding("missing-tool", contract.name, contract.tool, "missing-file")
            )
            continue
        for link in contract.links:
            if not resolve_repo_path(root, link.target).is_file():
                findings.append(
                    Finding("missing-file", contract.name, link.target, "link-target")
                )
                continue
            findings.extend(check_link(contract, link, all_edges))
        for text_check in contract.text_checks:
            findings.extend(check_text(root, contract, text_check))
        if contract.name == "tool_catalog":
            findings.extend(check_catalog_entries(root))
    return sorted(
        findings,
        key=lambda finding: (finding.kind, finding.contract, finding.path, finding.detail),
    )


def render_json(findings: Sequence[Finding]) -> str:
    """Render JSON output."""
    payload = {
        "status": "pass" if not findings else "fail",
        "findings": [asdict(finding) for finding in findings],
        "contracts": len(CONTRACTS),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run tool/convention drift checks."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    findings = run_checks(root, args.contract)
    if args.format == "json":
        print(render_json(findings))
    else:
        for finding in findings:
            print(finding.render())
        print(f"TOOL_CONVENTION_DRIFT_CONTRACTS={len(selected_contracts(args.contract))}")
        print(f"TOOL_CONVENTION_DRIFT_FINDINGS={len(findings)}")
        print(f"TOOL_CONVENTION_DRIFT={'pass' if not findings else 'fail'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
