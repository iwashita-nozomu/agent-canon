#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Detects drift between tool contracts, convention docs, and dependency manifests.
# upstream design ../../documents/design/dependency-manifest-design.md dependency manifest graph semantics
# upstream design ../../agents/workflows/agent-canon-pr-workflow.md PR validation contract
# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md subagent wave routing contract
# upstream design ../../agents/TASK_WORKFLOWS.md workflow routing contract
# upstream design ../../agents/skills/agent-orchestration.md orchestration routing contract
# upstream design ../../evidence/agent-evals/skill_workflow_prompt_eval.toml prompt routing eval contract
# upstream design ../../documents/conventions/REVIEW_PROCESS.md closeout validation policy
# upstream design ../../tools/catalog.yaml structured tool catalog
# upstream design ../../documents/tools/tool-docs.toml one-to-one tool documentation map
# upstream implementation ./tool_catalog.py validates catalog structure
# upstream implementation ./check_convention_compliance.py verifies skill-routing markers
# upstream implementation ./graph_client.py provides verified manifest dependency facts
# upstream implementation ./tool_path_policy.py defines retired legacy path policy
# downstream implementation ../../tools/ci/run_all_checks.sh runs drift checker
# downstream implementation ../../tests/agent_tools/test_tool_drift.py tests checker
# @dependency-end
"""Check tool/convention drift using dependency manifests as the trace map."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.agent_tools.graph_client import (
    CANONICAL_GRAPH_EXECUTABLE,
    GraphClient,
    GraphClientError,
    GraphDependencyFact,
)
from tools.agent_tools.tool_path_policy import (
    is_retired_legacy_tool_path,
    iter_retired_legacy_tool_paths,
    retired_legacy_tool_detail,
)


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
class CommandCheck:
    """One required shell command pattern for a tool contract."""

    path: str
    pattern: str
    detail: str
    required_count: int = 1


@dataclass(frozen=True)
class ToolContract:
    """One tool/convention consistency contract."""

    name: str
    tool: str
    links: tuple[LinkCheck, ...]
    text_checks: tuple[TextCheck, ...] = ()
    command_checks: tuple[CommandCheck, ...] = ()


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
            LinkCheck("templates/documents/github/pull-request/agent_canon.md"),
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
            LinkCheck("documents/tools/repo-local-tool-imports.md"),
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
                "documents/tools/repo-local-tool-imports.md",
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
            LinkCheck("templates/documents/responsibility-scope.template.toml"),
            LinkCheck("documents/design/responsibility-scope-management.md"),
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
            LinkCheck("documents/design/responsibility-scope-management.md"),
            LinkCheck("documents/conventions/coding-conventions-python.md"),
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
            LinkCheck("agents/skills/owner-bounded-routing.md"),
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
                "agents/skills/codex-task-workflow.md",
                "responsibility_scope",
                "missing-runtime-workflow-responsibility-preflight",
            ),
            TextCheck(
                "agents/skills/owner-bounded-routing.md",
                "responsibility_scope",
                "missing-runtime-small-change-responsibility-preflight",
            ),
        ),
    ),
    ToolContract(
        name="issue_sync",
        tool="tools/agent_tools/issue_sync.py",
        links=(
            LinkCheck("issues/README.md"),
            LinkCheck("documents/design/responsibility-scope-management.md"),
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
            LinkCheck("documents/runtime/runtime-log-archive.md"),
            LinkCheck("documents/runtime/runtime-log-archive-migration.md"),
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
            LinkCheck("documents/runtime/runtime-log-archive.md"),
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
            LinkCheck("templates/agents/closeout_gate.md"),
            LinkCheck("tests/agent_tools/test_generated_artifact_guard.py"),
        ),
        text_checks=(),
        command_checks=(
            CommandCheck(
                "tools/ci/check_agent_canon_pr.sh",
                r'^python3\s+"\$\{CANON_TOOLS_ROOT\}/agent_tools/generated_artifact_guard\.py"\s+--root\s+"\$\{WORKSPACE_ROOT\}"\s*$',
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
            LinkCheck("templates/documents/github/pull-request/agent_canon.md"),
            LinkCheck("tools/agent_tools/run_repo_dependency_review.sh"),
            LinkCheck("tools/agent_tools/run_accumulated_agent_evals.py"),
            LinkCheck("tools/agent_tools/generated_artifact_guard.py"),
            LinkCheck("tools/agent_tools/evaluate_skill_workflow_prompts.py"),
            LinkCheck("tools/agent_tools/check_agent_runtime_alignment.py"),
            LinkCheck("tools/agent_tools/check_convention_compliance.py"),
            LinkCheck("tools/ci/agent_canon_pr_graph_selector.py"),
            LinkCheck("tools/ci/check_github_workflows.py"),
            LinkCheck("tools/ci/run_all_checks.sh"),
        ),
        text_checks=(
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                'python3 "${CANON_TOOLS_ROOT}/agent_tools/check_agent_runtime_alignment.py"',
                "missing-agent-runtime-alignment-check",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                'AGENT_CANON_HOOK_ARCHIVE_DIR="${PR_HOOK_ARCHIVE_DIR}"',
                "missing-agent-canon-pr-hook-archive-env",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "not_applicable_standalone_source",
                "missing-standalone-shared-surface-skip",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "agentcanon_pr_dependency_graph_required()",
                "missing-dependency-graph-requirement-selector",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "if agentcanon_pr_dependency_graph_required; then",
                "missing-conditional-dependency-graph-gate",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "PR_GATE_DEPENDENCY_GRAPH_STATUS=skipped",
                "missing-optional-dependency-graph-receipt-status",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                'python3 "${CANON_TOOLS_ROOT}/ci/agent_canon_pr_graph_selector.py"',
                "missing-canonical-dependency-graph-selector",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "selector_reason=%s",
                "missing-dependency-graph-selector-reason-receipt",
            ),
            TextCheck(
                "tools/ci/check_agent_canon_pr.sh",
                "selector_evidence=%s",
                "missing-dependency-graph-selector-evidence-receipt",
            ),
        ),
        command_checks=(
            CommandCheck(
                "tools/ci/check_agent_canon_pr.sh",
                r'^bash\s+"\$\{CANON_TOOLS_ROOT\}/agent_tools/run_repo_dependency_review\.sh"\s+--fail-missing\s+--cycle-report-only\s+--changed-path-packet\s+"\$\{PR_GATE_DEPENDENCY_CHANGED_PATH_PACKET\}"\s+--report-dir\s+"\$\{PR_DEPENDENCY_REVIEW_DIR\}"\s*$',
                "missing-strict-dependency-review",
            ),
            CommandCheck(
                "tools/ci/check_agent_canon_pr.sh",
                r'^(?:AGENT_CANON_HOOK_ARCHIVE_DIR="\$\{PR_HOOK_ARCHIVE_DIR\}"\s+)?python3\s+"\$\{CANON_TOOLS_ROOT\}/agent_tools/run_accumulated_agent_evals\.py"\s+--run-id\s+agent-canon-pr-gate\s+--log-dir\s+"\$\{PR_AGENT_EVAL_LOG_DIR\}"\s*$',
                "missing-accumulated-agent-eval-producer",
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
            LinkCheck("evidence/agent-evals/skill_workflow_prompt_eval.toml"),
            LinkCheck("templates/agents/closeout_gate.md"),
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
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "VERTICAL-WAVE-POLICY",
                "missing-vertical-wave-prompt-eval",
            ),
            TextCheck(
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "ORCH-SHIM-POINTER-1",
                "missing-orchestration-owner-pointer-eval",
            ),
            TextCheck(
                "evidence/agent-evals/skill_workflow_prompt_eval.toml",
                "ORCH-SHIM-TOOLCALL-1",
                "missing-orchestration-toolcall-eval",
            ),
        ),
    ),
    ToolContract(
        name="repo_dependency_review",
        tool="tools/agent_tools/run_repo_dependency_review.sh",
        links=(
            LinkCheck("documents/design/dependency-manifest-design.md"),
            LinkCheck("agents/canonical/CODEX_WORKFLOW.md"),
            LinkCheck("templates/agents/closeout_gate.md"),
            LinkCheck(".github/PULL_REQUEST_TEMPLATE.md"),
            LinkCheck("templates/documents/github/pull-request/agent_canon.md"),
            LinkCheck("tools/ci/check_agent_canon_pr.sh"),
        ),
    ),
    ToolContract(
        name="container_config",
        tool="tools/ci/container_config.py",
        links=(
            LinkCheck("documents/conventions/coding-conventions-project.md"),
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


def resolve_repo_path(root: Path, relative_path: str) -> Path:
    """Resolve a path through the root view or vendored AgentCanon source."""
    root_path = root / relative_path
    if root_path.exists():
        return root_path
    if relative_path.startswith("tools/"):
        projected_path = (
            root / "tools" / "agent-canon" / relative_path.removeprefix("tools/")
        )
        if projected_path.exists():
            return projected_path
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


def opposite_direction(direction: str) -> str:
    """Return the reverse dependency direction."""
    return "downstream" if direction == "upstream" else "upstream"


def compatible_reverse_kind(
    direct: GraphDependencyFact, reverse: GraphDependencyFact
) -> bool:
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


def logical_graph_path(path: str) -> str:
    """Normalize standalone, vendored, and projected graph paths."""
    normalized = path.replace("\\", "/").removeprefix("./")
    if normalized.startswith("vendor/agent-canon/"):
        return normalized.removeprefix("vendor/agent-canon/")
    if normalized.startswith("tools/agent-canon/"):
        return "tools/" + normalized.removeprefix("tools/agent-canon/")
    return normalized


def matching_direct_edges(
    edges: Sequence[GraphDependencyFact], tool: str, target: str
) -> tuple[GraphDependencyFact, ...]:
    """Return direct tool-to-target manifest edges."""
    return tuple(
        edge
        for edge in edges
        if logical_graph_path(edge.source) == tool
        and logical_graph_path(edge.target) == target
    )


def matching_reverse_edges(
    edges: Sequence[GraphDependencyFact], tool: str, target: str
) -> tuple[GraphDependencyFact, ...]:
    """Return target-to-tool manifest edges."""
    return tuple(
        edge
        for edge in edges
        if logical_graph_path(edge.source) == target
        and logical_graph_path(edge.target) == tool
    )


def check_link(
    contract: ToolContract,
    link: LinkCheck,
    all_edges: Sequence[GraphDependencyFact],
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


def check_text(
    root: Path, contract: ToolContract, text_check: TextCheck
) -> list[Finding]:
    """Check one required snippet."""
    path = resolve_repo_path(root, text_check.path)
    if not path.is_file():
        return [
            Finding("missing-file", contract.name, text_check.path, text_check.detail)
        ]
    text = path.read_text(encoding="utf-8")
    snippets = {text_check.snippet, projected_runtime_snippet(root, text_check.snippet)}
    if any(snippet in text for snippet in snippets):
        return []
    return [
        Finding(
            "missing-required-text", contract.name, text_check.path, text_check.detail
        )
    ]


def collect_shell_executable_commands(path: Path) -> tuple[str, ...]:
    """Collect executable command lines from a shell script."""
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    continuation_lines: list[str] = []
    current = ""
    for raw_line in raw_lines:
        if raw_line.endswith("\\"):
            current += (" " if current else "") + raw_line[:-1]
            continue
        full_line = current + (" " if current else "") + raw_line
        current = ""
        continuation_lines.append(full_line)
    if current:
        continuation_lines.append(current)

    commands: list[str] = []
    disabled_depth = 0
    for raw_line in continuation_lines:
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^\s*#", line):
            continue
        if re.match(r"^\s*:", line):
            continue
        if re.match(r"^\s*(echo|printf)\b", line):
            continue
        if re.search(r"\|\|\s*true\b", line):
            continue
        if re.match(r"^\s*if\b.*\bfalse\b.*\bthen\b\s*$", line):
            disabled_depth += 1
            continue
        if re.match(r"^\s*fi\b", line):
            disabled_depth = max(0, disabled_depth - 1)
            continue
        if disabled_depth > 0:
            continue
        line = line.split(" #", 1)[0].rstrip()
        if not line:
            continue
        commands.append(re.sub(r"\s+", " ", line))
    return tuple(commands)


def check_command(
    root: Path, contract: ToolContract, command_check: CommandCheck
) -> list[Finding]:
    """Check one required shell command pattern."""
    path = resolve_repo_path(root, command_check.path)
    if not path.is_file():
        return [
            Finding(
                "missing-file", contract.name, command_check.path, command_check.detail
            )
        ]
    commands = collect_shell_executable_commands(path)
    pattern = re.compile(command_check.pattern)
    hits = [command for command in commands if pattern.search(command)]
    if not hits:
        return [
            Finding(
                "missing-required-command",
                contract.name,
                command_check.path,
                command_check.detail,
            )
        ]
    if len(hits) != command_check.required_count:
        return [
            Finding(
                "duplicate-required-command",
                contract.name,
                command_check.path,
                (
                    f"{command_check.detail}:actual={len(hits)}:"
                    f"expected={command_check.required_count}"
                ),
            )
        ]
    return []


def projected_runtime_snippet(root: Path, snippet: str) -> str:
    """Map standalone AgentCanon tool paths to a parent runtime projection."""
    if (
        not (root / "tools" / "agent-canon").exists()
        or (root / "tools" / "ci").exists()
    ):
        return snippet
    return (
        snippet.replace("tools/agent_tools/", "tools/agent-canon/agent_tools/")
        .replace("tools/ci/", "tools/agent-canon/ci/")
        .replace("tools/sync_agent_canon.sh", "tools/agent-canon/sync_agent_canon.sh")
        .replace(
            "tools/update_agent_canon.sh", "tools/agent-canon/update_agent_canon.sh"
        )
    )


def check_catalog_entries(root: Path) -> list[Finding]:
    """Check catalog entries for stale paths and legacy/default confusion."""
    catalog_path = resolve_repo_path(root, "tools/catalog.yaml")
    if not catalog_path.is_file():
        return [
            Finding("missing-file", "tool_catalog", "tools/catalog.yaml", "catalog")
        ]
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    catalog = as_mapping(raw)
    if catalog is None:
        return [
            Finding(
                "invalid-catalog", "tool_catalog", "tools/catalog.yaml", "not-mapping"
            )
        ]
    entries = as_sequence(catalog.get("entries"))
    if entries is None:
        return [
            Finding(
                "invalid-catalog",
                "tool_catalog",
                "tools/catalog.yaml",
                "entries-not-list",
            )
        ]
    findings: list[Finding] = []
    catalog_retired_paths: set[str] = set()
    for index, raw_entry in enumerate(entries, start=1):
        entry = as_mapping(raw_entry)
        if entry is None:
            findings.append(
                Finding(
                    "invalid-catalog-entry",
                    "tool_catalog",
                    "tools/catalog.yaml",
                    f"entry-{index}-not-mapping",
                )
            )
            continue
        entry_path = entry.get("path")
        status = entry.get("status")
        if not isinstance(entry_path, str):
            findings.append(
                Finding(
                    "invalid-catalog-entry",
                    "tool_catalog",
                    "tools/catalog.yaml",
                    f"entry-{index}-missing-path",
                )
            )
            continue
        if not resolve_repo_path(root, entry_path).exists():
            findings.append(
                Finding(
                    "stale-catalog-entry", "tool_catalog", entry_path, "missing-path"
                )
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
    graph = GraphClient(root, CANONICAL_GRAPH_EXECUTABLE).query(
        all_nodes=True,
        relation="dependency",
        direction="both",
        depth=0,
    )
    if graph.status != "fresh" or graph.exit_code != 0:
        raise GraphClientError(
            "canonical graph dependency query is unavailable: "
            f"status={graph.status} reason={graph.payload.get('reason')}"
        )
    all_edges = graph.dependency_facts
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
        for command_check in contract.command_checks:
            findings.extend(check_command(root, contract, command_check))
        if contract.name == "tool_catalog":
            findings.extend(check_catalog_entries(root))
    return sorted(
        findings,
        key=lambda finding: (
            finding.kind,
            finding.contract,
            finding.path,
            finding.detail,
        ),
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
    try:
        findings = run_checks(root, args.contract)
    except GraphClientError as error:
        findings = [Finding("graph-unavailable", "canonical_graph", ".", str(error))]
    if args.format == "json":
        print(render_json(findings))
    else:
        for finding in findings:
            print(finding.render())
        print(
            f"TOOL_CONVENTION_DRIFT_CONTRACTS={len(selected_contracts(args.contract))}"
        )
        print(f"TOOL_CONVENTION_DRIFT_FINDINGS={len(findings)}")
        print(f"TOOL_CONVENTION_DRIFT={'pass' if not findings else 'fail'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
