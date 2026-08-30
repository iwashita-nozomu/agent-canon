#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Verifies repository convention compliance wiring and workflow gates.
# upstream design ../../../../documents/conventions/README.md convention index
# upstream design ../../../../agents/canonical/CODEX_WORKFLOW.md completion readiness policy
# upstream design ../../../../agents/canonical/CODEX_SUBAGENTS.md subagent wave routing policy
# upstream design ../../../../agents/TASK_WORKFLOWS.md workflow skill routing policy
# upstream design ../../../../agents/skills/agent-orchestration.md canonical orchestration skill
# upstream design ../../../../agents/skills/codex-task-workflow.md implementation workflow skill
# upstream design ../../../../agents/skills/subagent-bootstrap.md subagent handoff skill
# upstream design ../../../../agents/skills/tool-finding-report.md tool warning closeout skill
# upstream design ../../../../agents/workflows/agent-canon-pr-workflow.md AgentCanon PR essence workflow
# upstream design ../../../../agents/workflows/pr-queue-cleanup-workflow.md PR queue cleanup body update workflow
# upstream design ../../../../agents/skills/md-style-check.md Markdown small-edit skill route
# upstream design ../../../../agents/skills/long-form-writing.md document claim grounding skill route
# upstream design ../../../../agents/USER_GUIDE_JA.md user-facing small-edit route guidance
# upstream design ../../../../templates/agents/workflow_monitoring.md tool warning closeout ledger
# upstream design ../../../../templates/agents/closeout_gate.md closeout gate policy
# upstream design ../../../../eval/definitions/skill_workflow_prompt_eval.toml prompt eval gate
# upstream implementation ../../../runtime/source/agent_canon_source_root.py resolves canonical parent adapter targets
# upstream design ../../../../documents/codex/codex-configuration-reference.md Codex hook severity policy
# upstream design ../../../../documents/conventions/coding-conventions-house-style.md implementation ownership guardrail
# upstream design ../../../../documents/notes/guardrails/engineering_avoidances.md recurring implementation avoidances
# upstream design ../../../../.codex/README.md Codex runtime hook behavior summary
# upstream design ../../../catalog.yaml structured tool catalog
# upstream design ../../../../.github/PULL_REQUEST_TEMPLATE.md standalone PR body checklist
# upstream design ../../../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md template PR body checklist
# upstream implementation ../tools/tool_drift.py validates tool/convention drift
# upstream implementation ./convention_compliance_contracts.toml declares marker contracts
# upstream implementation ../skills/check_skill_frontmatter.py validates runtime skill frontmatter
# downstream implementation ../../ci/runners/run_all_checks.sh runs convention compliance gate
# downstream implementation ../../../../tests/agent_tools/test_check_convention_compliance.py tests verifier  # noqa: E501
# @dependency-end
"""Verify that convention, workflow, and skill-routing gates are wired."""

from __future__ import annotations

import argparse
import json
import re

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

MARKER_CONTRACTS_PATH = Path("tools/validation/semantic/convention/convention_compliance_contracts.toml")


def load_marker_contracts() -> dict[str, dict[str, tuple[str, ...]]]:
    """Load declarative marker contracts from the checked-in manifest."""
    manifest = Path(__file__).resolve().parents[4] / MARKER_CONTRACTS_PATH
    payload = tomllib.loads(manifest.read_text(encoding="utf-8"))
    contracts: dict[str, dict[str, tuple[str, ...]]] = {}
    for contract in payload.get("contracts", []):
        contract_id = contract["id"]
        surfaces: dict[str, tuple[str, ...]] = {}
        for surface in contract.get("surfaces", []):
            path = surface["path"]
            if path.startswith(".codex/personal/skills/") and path.endswith("/SKILL.md"):
                raise ValueError(
                    "generated skill shims cannot own convention marker contracts: "
                    f"{path}"
                )
            surfaces[path] = tuple(surface.get("markers", []))
        contracts[contract_id] = surfaces
    return contracts


DECLARATIVE_MARKER_CONTRACTS = load_marker_contracts()
DESIGN_INTEGRITY_GATE_MARKERS = DECLARATIVE_MARKER_CONTRACTS["design_integrity_gate"]

CONVENTION_SOURCES = (
    "documents/conventions/README.md",
    "documents/conventions/common/01_principles.md",
    "documents/rule/naming.md",
    "documents/conventions/common/03_comments.md",
    "documents/conventions/common/04_operators.md",
    "documents/conventions/common/05_docs.md",
    "documents/conventions/python/01_scope.md",
    "documents/conventions/python/04_type_annotations.md",
    "documents/conventions/python/06_comments.md",
    "documents/conventions/python/07_type_checker.md",
    "documents/conventions/python/09_file_roles.md",
    "documents/conventions/python/11_naming.md",
    "documents/conventions/python/15_jax_rules.md",
    "documents/conventions/python/20_benchmark_policy.md",
    "documents/conventions/python/30_experiment_directory_structure.md",
    "documents/conventions/coding-conventions-python.md",
    "documents/conventions/coding-conventions-cpp.md",
    "documents/conventions/coding-conventions-project.md",
    "documents/conventions/coding-conventions-house-style.md",
    "documents/conventions/coding-conventions-testing.md",
    "documents/conventions/coding-conventions-reviews.md",
    "documents/conventions/coding-conventions-experiments.md",
    "documents/conventions/coding-conventions-logging.md",
    "documents/design/algorithm-implementation-boundary.md",
    "documents/conventions/object-oriented-design.md",
    "documents/conventions/REVIEW_PROCESS.md",
    "agents/canonical/CODEX_WORKFLOW.md",
)

TOOL_CATALOG_PATH = "tools/catalog.yaml"

# This table records execution surfaces and their owners.  It deliberately does
# not require every reader-facing document to repeat a tool filename: catalog,
# workflow, and runtime-profile checkers own those contracts independently.
TOOL_GATES = {
    "dependency_review": (
        "tools/analysis/dependencies/run_repo_dependency_review.sh",
        (TOOL_CATALOG_PATH,),
    ),
    "code_dependency_scan": (
        "tools/analysis/dependencies/scan_code_dependencies.sh",
        (TOOL_CATALOG_PATH,),
    ),
    "hardcoded_numbers": (
        "tools/validation/semantic/code/check_hardcoded_numbers.py",
        (TOOL_CATALOG_PATH,),
    ),
    "static_any": (
        "tools/validation/semantic/code/check_static_any.py",
        (TOOL_CATALOG_PATH,),
    ),
    "log_helper_names": (
        "tools/validation/semantic/logging/check_log_helper_names.py",
        (TOOL_CATALOG_PATH,),
    ),
    "notebook_quality": (
        "tools/validation/notebooks/notebook_quality.py",
        (TOOL_CATALOG_PATH,),
    ),
    "oop_readability": (
        "tools/validation/code/oop/python/readability.py",
        (TOOL_CATALOG_PATH,),
    ),
    "oop_cpp_readability": (
        "tools/validation/code/oop/cpp/readability.py",
        (TOOL_CATALOG_PATH,),
    ),
    "prompt_eval": (
        "eval/producers/evaluate_skill_workflow_prompts.py",
        (TOOL_CATALOG_PATH,),
    ),
    "behavior_eval": (
        "eval/producers/evaluate_agent_run.py",
        (TOOL_CATALOG_PATH,),
    ),
    "skill_frontmatter": (
        "tools/validation/semantic/skills/check_skill_frontmatter.py",
        (TOOL_CATALOG_PATH,),
    ),
    "convention_compliance": (
        "tools/validation/semantic/convention/check_convention_compliance.py",
        (TOOL_CATALOG_PATH,),
    ),
    "tool_catalog": (
        "tools/runtime/manifest/tool_catalog.py",
        (TOOL_CATALOG_PATH,),
    ),
    "tool_convention_drift": (
        "tools/validation/semantic/tools/tool_drift.py",
        (TOOL_CATALOG_PATH,),
    ),
    "import_responsibility": (
        "tools/analysis/code/import_responsibility.py",
        (TOOL_CATALOG_PATH,),
    ),
    "github_workflow_pr_flow": (
        "tools/validation/ci/checks/check_github_workflows.py",
        (TOOL_CATALOG_PATH,),
    ),
    "bootstrap_container_runtime": (
        "bootstrap.sh",
        ("documents/runtime/bootstrap-runtime.md",),
    ),
}

SKILL_ROUTING_PROMPTS = ("agents/skills/agent-orchestration.md",)

SKILL_ROUTING_MARKERS = (
    "$agent-orchestration",
    "$codex-task-workflow",
    "$subagent-bootstrap",
    "task-shape skill",
    "check_convention_compliance.py",
)
EXIT_BLOCKER_POLICY_MARKERS = {
    "agents/skills/agent-orchestration.md": (
        "evidence",
        "router_unavailable_blocker",
    ),
    "agents/skills/codex-task-workflow.md": (
        "selected_agent_type",
        "write_capable_handoff_blocker",
        "evidence",
        "parent_packet_ref",
        "status=blocked",
        "canonical_rerun_pass",
        "durable_blocker_or_issue",
        "router_unavailable_blocker",
        "new state evidence",
        "revised parent packet",
    ),
    "agents/skills/subagent-bootstrap.md": (
        "selected_agent_type",
        "write_capable_handoff_blocker",
        "evidence",
        "parent_packet_ref",
        "status=blocked",
        "new state evidence",
        "explicit revised packet",
    ),
    "agents/skills/tool-finding-report.md": (
        "tool_warning_exit_status",
        "resolved",
        "deferred_with_issue",
        "accepted_with_reason",
        "explicit_approval_evidence",
    ),
    "templates/agents/workflow_monitoring.md": (
        "tool_warning_exit_status",
        "resolved",
        "deferred_with_issue",
        "accepted_with_reason",
        "explicit_approval_evidence",
    ),
}
EXIT_BLOCKER_FORBIDDEN_RE = re.compile(
    r"(?i)(?:"
    r"sole basis for path selection|"
    r"falling back to a parent write alternate route|"
    r"parent write[^\n.。]{0,120}alternate route|"
    r"parent write\s*代替|"
    r"worker[^\n.。]{0,80}alternate route)"
)
DOCUMENT_STRUCTURE_ROUTING_MARKERS = {
    "agents/skills/agent-orchestration.md": (
        "prose-reasoning-graph",
        "structure-planning",
        "md-style-check",
        "format-only",
        "structure_contract=skipped",
    ),
    "agents/skills/codex-task-workflow.md": (
        "prose-reasoning-graph",
        "structure-planning",
        "md-style-check",
        "format-only",
        "structure_contract=skipped",
    ),
    "agents/skills/md-style-check.md": (
        "prose-reasoning-graph",
        "structure-planning",
        "format-only",
        "structure_contract=skipped",
    ),
    "agents/skills/README.md": (
        "prose-reasoning-graph",
        "structure-planning",
        "md-style-check",
        "structure_contract=skipped",
    ),
    "agents/skills/catalog.yaml": (
        "format-only docs work",
        "prose-reasoning-graph",
        "structure-planning",
    ),
    "agents/workflows/long-form-writing-workflow.md": (
        "$structure-planning",
        "$prose-reasoning-graph",
        "$md-style-check",
        "structure_contract=skipped",
    ),
    "documents/conventions/REVIEW_PROCESS.md": (
        "structure-planning",
        "prose-reasoning-graph",
        "md-style-check",
        "structure_contract=skipped",
    ),
    "templates/agents/closeout_gate.md": (
        "Document Structure Evidence",
        "document_structure_status",
        "structure_planning",
        "prose_graph",
        "md_style_check",
        "format_only_reason",
    ),
    "tools/runtime/lifecycle/task_close.py": (
        "changed_markdown_paths",
        "Document Structure Evidence",
        "document_structure_evidence",
        "DOCUMENT_STRUCTURE_REQUIRED",
    ),
}
DOCUMENT_SPLIT_DECISION_MARKERS = {
    "documents/conventions/common/05_docs.md": (
        "Document Split Decision",
        "document_split_decision",
        "document_unit",
        "split_when",
        "merge_when",
        "invalid_split_boundaries",
        "check_convention_compliance.py",
        "task_close.py",
    ),
    "agents/skills/long-form-writing.md": (
        "document_split_decision",
        "owner",
        "reader path",
        "source map",
        "validation route",
        "chunking convenience",
    ),
    "templates/agents/closeout_gate.md": (
        "document_split_decision",
        "keep:<reason>",
        "split:<new-owner-boundary>",
        "not_applicable:format-only:<reason>",
    ),
    "tools/runtime/lifecycle/task_close.py": (
        "document_split_decision",
        "DOCUMENT_SPLIT_DECISION_EVIDENCE",
        "document_split_decision_ready",
    ),
}
STATIC_READ_VALIDATION_POLICY_MARKERS = DECLARATIVE_MARKER_CONTRACTS[
    "static_read_validation_policy"
]
LITERATURE_BACKED_SKILL_CALL_ORDER_MARKERS = DECLARATIVE_MARKER_CONTRACTS[
    "literature_backed_skill_call_order"
]
RESPONSIBILITY_PREFLIGHT_GATE_MARKERS = DECLARATIVE_MARKER_CONTRACTS[
    "responsibility_preflight_gate"
]
EXPERIMENT_EXECUTION_SURFACE_GUARD_MARKERS = DECLARATIVE_MARKER_CONTRACTS[
    "experiment_execution_surface_guard"
]
BRANCH_WORKTREE_CREATION_GUARD_MARKERS = DECLARATIVE_MARKER_CONTRACTS[
    "branch_worktree_creation_guard"
]

WORKFLOW_GATE_MARKER = "check_convention_compliance.py"
WORKFLOW_GATE_CONSUMERS = ("tools/validation/ci/checks/check_agent_canon_pr.sh",)
WORKFLOW_GATE_COMMAND_RE = re.compile(
    r'(?m)^\s*python3\s+"\$\{WORKSPACE_ROOT\}/tools/validation/semantic/convention/check_convention_compliance\.py"\s+'
    r'--root\s+"\$\{WORKSPACE_ROOT\}"\s+--format\s+json$'
)
WORKFLOW_GATE_FORBIDDEN_RE = re.compile(
    r"(?is)(?:do\s+not|don't|never|skip|omit)\s+(?:\S+\s+){0,6}?"
    r"check_convention_compliance\.py|check_convention_compliance\.py"
    r"(?:\S+\s+){0,6}?(?:optional|not\s+required)"
)
CLOSEOUT_WORKFLOW_PATH = "agents/canonical/CODEX_WORKFLOW.md"
CLOSEOUT_OWNER_PATH = "tools/runtime/lifecycle/task_close.py"
CLOSEOUT_WORKFLOW_DELEGATION_MARKERS = (
    "[`task_close.py`](../../tools/runtime/lifecycle/task_close.py)",
    "sole terminal readiness predicate",
)
CLOSEOUT_OWNER_MARKERS = (
    "closeout_checks",
    "ready = all(closeout_checks.values())",
)
DOCUMENT_CLAIM_GROUNDING_MARKERS = {
    "documents/conventions/common/05_docs.md": (
        "claim grounding",
        "program contract",
        "public entrypoint",
        "return projection",
        "proof obligation",
        "provisional wording",
        "check_convention_compliance.py",
    ),
    "documents/conventions/coding-conventions-project.md": (
        "claim grounding",
        "program contract",
        "proof obligation",
        "run-local planning evidence",
    ),
    "agents/skills/long-form-writing.md": (
        "数学的 claim",
        "program contract",
        "proof obligation",
        "$formal-proof-workflow",
        "provisional wording",
    ),
    "agents/skills/formal-proof-workflow.md": (
        "program contract",
        "public entrypoint",
        "return projection",
        "proof obligation",
    ),
}
TEST_CONTRACT_ROUTING_MARKERS = {
    "documents/conventions/coding-conventions-testing.md": (
        "contract-only wrapper",
        "static contract validation",
        "static-analysis-duplicate-test",
        "canonical command",
        "Validation repair scope",
    ),
    "agents/canonical/CODEX_WORKFLOW.md": (
        "contract-only wrapper",
        "static contract validation",
        "canonical command evidence",
        "validation tool",
    ),
    "templates/agents/test_plan.md": (
        "validation route",
        "behavior-owned cases",
    ),
}
VALIDATION_FAILURE_RESPONSE_MARKERS = {
    "documents/operations/TROUBLESHOOTING.md": (
        "validation test/check failure",
        "failing_contract",
        "cause_classification",
        "intent_preservation",
        "documents/runtime/runtime-profiles-and-check-matrix.json",
        "documents/runtime/runtime-profiles-and-check-matrix.md",
    ),
    "documents/conventions/coding-conventions-testing.md": (
        "Validation test/check",
        "failing_contract",
        "cause_classification",
        "intent_preservation",
        "documents/runtime/runtime-profiles-and-check-matrix.json",
        "documents/runtime/runtime-profiles-and-check-matrix.md",
    ),
}
VALIDATION_FAILURE_RESPONSE_STALE_OWNER_PHRASES = (
    "runtime-profiles-and-check-matrix.md`、`agents/canonical/CODEX_WORKFLOW.md",
    "agents/canonical/CODEX_SUBAGENTS.md`、`documents/conventions/REVIEW_PROCESS.md",
)
MATHEMATICAL_NECESSITY_MARKERS = {
    "documents/conventions/common/05_docs.md": (
        "mathematical necessity gate",
        "Judgment / Mathematical Role / Necessity Evidence / Owner / Validation Route",
        "necessary-and-sufficient condition",
        "non-contractual mathematical judgment",
    ),
    "documents/conventions/coding-conventions-testing.md": (
        "mathematical necessity gate",
        "Numerical Trigger",
        "Non-Numerical Alternative",
        "checker-owned property",
    ),
    "agents/skills/computational-optimization.md": (
        "mathematical necessity gate",
        "iteration map",
        "stopping scalar",
        "failure semantics",
    ),
    "agents/skills/formal-proof-workflow.md": (
        "mathematical necessity gate",
        "program contract",
        "theorem surface",
        "proof obligation",
    ),
}
IMPLEMENTATION_GUARDRAIL_MARKERS = {
    "documents/conventions/coding-conventions-house-style.md": (
        "compatibility-preservation drift",
        "duplicate implementation",
        "canonical owner",
        "caller migration",
        "contract-complete implementation",
        "acceptance contract",
        "design_issue_blocker",
        "implementation shortcut",
        "check_convention_compliance.py",
    ),
    "documents/notes/guardrails/engineering_avoidances.md": (
        "compatibility-preservation drift",
        "duplicate implementation",
        "canonical owner",
        "contract-complete implementation",
        "acceptance contract",
        "design_issue_blocker",
        "implementation shortcut",
    ),
    "agents/canonical/CODEX_WORKFLOW.md": (
        "legacy-route drift",
        "duplicate implementation",
        "canonical owner",
        "caller migration",
        "contract-complete implementation",
        "acceptance contract",
        "design_issue_blocker",
        "implementation shortcut",
    ),
    "agents/skills/codex-task-workflow.md": (
        "design_issue_blocker",
        "implementation shortcut",
    ),
    "agents/workflows/comprehensive-refactoring-workflow.md": (
        "compatibility-preservation drift",
        "duplicate implementation",
        "canonical owner",
        "Removal and Caller Migration Plan",
    ),
}
REFACTOR_SEQUENCE_MARKERS = {
    "agents/skills/refactor-loop.md": (
        "two-stage refactor",
        "forced migration",
        "usage-surface repair",
        "return-gate validation",
    ),
    "agents/workflows/comprehensive-refactoring-workflow.md": (
        "two-stage refactor",
        "forced migration",
        "usage-surface repair",
        "return-gate validation",
    ),
    "documents/conventions/coding-conventions-house-style.md": (
        "two-stage refactor",
        "forced migration",
        "usage-surface repair",
        "return-gate validation",
    ),
}
REVIEW_ISSUE_ROUTING_MARKERS = {
    "documents/conventions/REVIEW_PROCESS.md": (
        "Review Finding Issue Routing",
        "issue_route",
        "github_issue",
        "issue_sync.py",
        "private packet",
    ),
}
SOLID_CODING_CONTRACT_MARKERS = DECLARATIVE_MARKER_CONTRACTS["solid_coding_contract"]

SOURCE_FILE_DEFINITION_ORDER_MARKERS = DECLARATIVE_MARKER_CONTRACTS[
    "source_file_definition_order"
]
PROVISIONAL_CANONICAL_WORDING_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?.*(?:"
    r"まずは|ひとまず|とりあえず|for now|first pass|first draft|"
    r"temporary policy|temporary rule|ad hoc|adhoc)"
)
PROVISIONAL_GROUNDING_RE = re.compile(
    r"(?i)(?:"
    r"run-local|planning evidence|evidence gap|verification route|"
    r"prompt-defect|acceptance condition|limitation|"
    r"受け入れ条件|validation route|責務名|proof_status)"
)
PROMPT_EVAL_MARKERS = (
    "check_convention_compliance",
    "WORKFLOW-GENERIC-1",
    "ORCH-SHIM-TOOLCALL-1",
    "CONVENTION-SKILL",
)
HOOK_GUARDRAIL_POLICY_MARKERS = {
    ".codex/hooks/hook_dispatcher.py": (
        "HOOK_EVENT_CONTRACTS",
        "HookEventContract",
        "ACTIVE_HOOK_HANDLERS",
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "Stop",
        "hook_safety",
        "validate_projection_bytes",
        "record_hook_invocation",
        "HookLogContext",
        "RETIRED_CHILD_TOMBSTONES",
        "MOVED_SOURCE_ABSENCES",
    ),
    "tools/runtime/authority/hook_safety.py": (
        "AGENT_CANON_BRANCH_WORKTREE_AUTHORITY",
        "AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY",
        "branch_block_payload",
        "command_sha256",
        "operation",
        "same-segment",
        "DESTRUCTIVE_GIT_GUARD=block",
        "BRANCH_WORKTREE_CREATION_GUARD=block",
    ),
    ".codex/README.md": (
        "active events",
        "active/inactive",
        "legacy `Stop`",
        "fail-open",
        "retired child tombstones",
        "bounded",
        "redacted",
    ),
    "documents/codex/codex-configuration-reference.md": (
        "Hook Severity Policy",
        "fail-open",
        "warning/evidence",
        "secret",
        "Active dispatcher failures",
    ),
}
OWNER_MAP_ENTRYPOINT_TABLE_ROWS = {
    "ROOT_AGENTS.md": (
        (
            "## Runtime Owner Map",
            (
                (
                    "workflow family, spawn budget, role topology",
                    "agents/task_catalog.yaml",
                    "check_agent_runtime_alignment.py",
                ),
                (
                    "task bootstrap and CLI entrypoints",
                    "agents/canonical/CLI_ENTRYPOINTS.md",
                    "bootstrap_agent_run.py",
                ),
                (
                    "subagent lifecycle, same-role instances, wave ledger",
                    "agents/canonical/CODEX_SUBAGENTS.md",
                    "workflow_monitor.py",
                ),
                (
                    "role behavior and stage conditions",
                    ".codex/agents/*.toml",
                    "check_agent_runtime_alignment.py",
                ),
                (
                    "skill routing and public skill surface",
                    "agents/skills/catalog.yaml",
                    "tools/agent/orchestration/route.py --prompt",
                ),
                (
                    "report and closeout structure",
                    "tools/runtime/lifecycle/task_close.py",
                    "closeout gate",
                ),
                (
                    "entrypoint responsibility grammar",
                    "documents/design/entrypoint-owner-map.md",
                    "check_entrypoint_owner_map.py",
                ),
                (
                    "bootstrap, image, and resident container",
                    "bootstrap.sh",
                    "bootstrap/container profile",
                ),
                (
                    "Python, Rust, and LSP tool dispatch",
                    "tools/runtime/dispatch/tool_dispatch.py",
                    "tool dispatch tests",
                ),
                (
                    "skill and agent installation",
                    "tools/agent/skills/skill_shim_materializer.py",
                    "skill materializer check",
                ),
                (
                    "source-side-effect boundary",
                    "documents/runtime/bootstrap-runtime.md",
                    "external runtime and source-unchanged checks",
                ),
                (
                    "eval archive",
                    "tools/runtime/archive/runtime_log_archive_git.py",
                    "archive readback",
                ),
                (
                    "source update",
                    "agents/skills/agent-canon-update.md",
                    "qualified PR and merged-main readback",
                ),
            ),
        ),
    ),
    "AGENTS.md": (
        (
            "## Runtime Owner Map",
            (
                (
                    "root runtime entrypoint",
                    "bootstrap.sh",
                    "bash bootstrap.sh --help",
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
            ),
        ),
    ),
    "agents/TASK_WORKFLOWS.md": (
        (
            "## Workflow Contract Owners",
            (
                (
                    "workflow family and spawn budget",
                    "agents/task_catalog.yaml",
                ),
                (
                    "role topology and same-role instance schema",
                    "agents/task_catalog.yaml",
                ),
                (
                    "default specialists and review packs",
                    "agents/task_catalog.yaml",
                    "agents/agents_config.json",
                ),
                (
                    "run bundle, declared workflow / skills / review, and dynamic wave ledger",
                    "bootstrap_agent_run.py",
                    "workflow_monitor.py",
                ),
                (
                    "skill selection",
                    "agents/skills/catalog.yaml",
                    "python3 tools/agent/orchestration/route.py --prompt",
                ),
                (
                    "implementation stage gate",
                    "agents/workflows/implementation-waterfall-workflow.md",
                ),
                (
                    "active design packet schema",
                    "agents/COMMUNICATION_PROTOCOL.md",
                    "agents/agents_config.json#artifacts.active_design_packet",
                ),
                (
                    "closeout authority",
                    "task_close.py",
                    "report_artifact_checks.py",
                ),
            ),
        ),
    ),
}
OWNER_MAP_ENTRYPOINT_MARKERS = {
    path: tuple(
        dict.fromkeys(
            marker
            for heading, rows in section_rows
            for row in ((heading,), *rows)
            for marker in row
        )
    )
    for path, section_rows in OWNER_MAP_ENTRYPOINT_TABLE_ROWS.items()
}
NORMATIVE_RE = re.compile(
    r"(?m)^\s*[-*]\s+.*(?:禁止|必須|しなければなりません|してはいけません|"
    r"must|must not|required|forbidden)",
    flags=re.IGNORECASE,
)
VERIFICATION_RE = re.compile(
    r"(?:tools/|check_|pyright|pytest|ruff|make ci|make agent-checks|"
    r"CONVENTION_COMPLIANCE|EVAL_STATUS|AGENT_EVALUATION_STATUS)"
)
FORWARDER_WARNING_REQUIRED_MARKER = "LEGACY_FORWARDER_WARNING_REQUIRED"
FORWARDER_WARNING_MARKERS = (
    "FORWARDER_CALLER",
    "FORWARDER_ACTION",
    "FORWARDER_SEVERITY=fix-now",
    "FORWARDER_PROMPT",
    "caller_process_chain",
)
AGENTS_FORWARDER_POLICY_MARKERS = (
    "*_FORWARDER=deprecated",
    "*_FORWARDER_SEVERITY=fix-now",
    "caller chain",
    "canonical command",
)
ENTRYPOINT_DELEGATED_SECTION_HEADINGS = (
    "## Subagent Usage",
    "## Plan Mode",
    "## Read Packets",
    "## Execution Priorities",
    "## Mechanical Guardrail Policy",
    "## Default Search And Routing",
    "## Runtime Profiles And Risk",
    "## Experiment And Log Diagnostics",
    "## AgentCanon Submodule Update Flow",
    "## PR Mutation Authority",
    "## Required Before Implementation",
)
ENTRYPOINT_DELEGATION_PATHS = ("ROOT_AGENTS.md", "AGENTS.md")


@dataclass(frozen=True)
class Finding:
    """One convention compliance wiring issue."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one stable machine-readable finding."""
        return f"CONVENTION_COMPLIANCE_FINDING={self.check}:{self.path}:{self.detail}"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify convention compliance tool, workflow, and skill prompt wiring."
        )
    )
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def readable_path(root: Path, relative_path: str) -> Path | None:
    """Return the readable root or vendored AgentCanon document path."""
    candidates = (root / relative_path, root / "vendor" / "agent-canon" / relative_path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def read_text(root: Path, relative_path: str) -> str:
    """Read a UTF-8 text file relative to root."""
    resolved = readable_path(root, relative_path)
    if resolved is None:
        return (root / relative_path).read_text(encoding="utf-8")
    return resolved.read_text(encoding="utf-8")


def markdown_section_lines(text: str, heading: str) -> list[str] | None:
    """Return lines under a Markdown heading until the next peer heading."""
    lines = text.splitlines()
    heading_index = next(
        (index for index, line in enumerate(lines) if line.strip() == heading),
        None,
    )
    if heading_index is None:
        return None
    heading_level = len(heading) - len(heading.lstrip("#"))
    section: list[str] = []
    for line in lines[heading_index + 1 :]:
        stripped = line.strip()
        if stripped.startswith("#"):
            next_level = len(stripped) - len(stripped.lstrip("#"))
            if next_level <= heading_level:
                break
        section.append(line)
    return section


def markdown_table_rows(lines: Sequence[str]) -> list[str]:
    """Return Markdown table data rows from a section."""
    rows: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(cell and set(cell) <= set("-: ") for cell in cells):
            continue
        rows.append(stripped)
    return rows


def same_resolved_file(left: Path, right: Path) -> bool:
    """Return whether two paths point to the same filesystem entry."""
    try:
        return left.resolve(strict=True) == right.resolve(strict=True)
    except OSError:
        return False


def owner_map_entrypoint_rows(
    root: Path, path: str
) -> Sequence[tuple[str, Sequence[tuple[str, ...]]]]:
    """Return owner-map rows for the entrypoint role active at ``path``."""
    agents_path = readable_path(root, "AGENTS.md")
    root_agents_path = readable_path(root, "ROOT_AGENTS.md")
    if (
        path == "AGENTS.md"
        and agents_path is not None
        and root_agents_path is not None
        and same_resolved_file(agents_path, root_agents_path)
    ):
        return OWNER_MAP_ENTRYPOINT_TABLE_ROWS["ROOT_AGENTS.md"]
    return OWNER_MAP_ENTRYPOINT_TABLE_ROWS[path]


def duplicate_root_view_entrypoint(root: Path, path: str) -> bool:
    """Return whether ``path`` is already covered by the root entrypoint view."""
    agents_path = readable_path(root, "AGENTS.md")
    root_agents_path = readable_path(root, "ROOT_AGENTS.md")
    return (
        path == "AGENTS.md"
        and agents_path is not None
        and root_agents_path is not None
        and same_resolved_file(agents_path, root_agents_path)
    )


def check_required_files(root: Path, paths: Sequence[str], check: str) -> list[Finding]:
    """Return findings for missing required files."""
    findings: list[Finding] = []
    for path in paths:
        if readable_path(root, path) is None:
            findings.append(Finding(check, path, "missing-required-file"))
    return findings


def check_tool_gates(root: Path) -> list[Finding]:
    """Verify each gate has an executable surface and one owning registry."""
    findings: list[Finding] = []
    for gate_name, (tool_path, references) in TOOL_GATES.items():
        if readable_path(root, tool_path) is None:
            findings.append(
                Finding("tool_gate", tool_path, f"{gate_name}:missing-tool")
            )
            continue
        for owner in references:
            owner_path = readable_path(root, owner)
            if owner_path is None:
                findings.append(
                    Finding("tool_gate", owner, f"{gate_name}:missing-owner-surface")
                )
                continue

            # The structured catalog is the owner for cataloged tools. Check
            # the path entry itself, not an incidental filename mention in a
            # README, workflow, or skill. Catalog shape and metadata remain
            # the responsibility of tool_catalog.py.
            if owner == TOOL_CATALOG_PATH:
                catalog_text = owner_path.read_text(encoding="utf-8")
                path_re = re.compile(
                    rf"(?m)^\s*path:\s*['\"]?{re.escape(tool_path)}['\"]?\s*(?:#.*)?$"
                )
                if not path_re.search(catalog_text):
                    findings.append(
                        Finding(
                            "tool_gate",
                            owner,
                            f"{gate_name}:missing-catalog-owner",
                        )
                    )
    return findings


def check_workflow_hooks(root: Path) -> list[Finding]:
    """Verify the canonical source gate owns convention verification."""
    findings = check_required_files(root, WORKFLOW_GATE_CONSUMERS, "workflow_hook")
    for relative in WORKFLOW_GATE_CONSUMERS:
        path = readable_path(root, relative)
        if path is None:
            continue
        text = path.read_text(encoding="utf-8")
        if WORKFLOW_GATE_MARKER not in text:
            findings.append(
                Finding(
                    "workflow_hook",
                    relative,
                    "missing-convention-compliance-gate",
                )
            )
            continue
        if not WORKFLOW_GATE_COMMAND_RE.search(text):
            findings.append(
                Finding(
                    "workflow_hook",
                    relative,
                    "missing-positive-convention-compliance-command",
                )
            )
        if WORKFLOW_GATE_FORBIDDEN_RE.search(text):
            findings.append(
                Finding(
                    "workflow_hook",
                    relative,
                    "forbidden-convention-compliance-suppression",
                )
            )
    return findings


def check_skill_routing(root: Path) -> list[Finding]:
    """Verify skill-routing prompts include required routing and verifier markers."""
    findings = check_required_files(root, SKILL_ROUTING_PROMPTS, "skill_routing")
    for path in SKILL_ROUTING_PROMPTS:
        full_path = root / path
        if not full_path.is_file():
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in SKILL_ROUTING_MARKERS:
            if marker not in text:
                findings.append(
                    Finding("skill_routing", path, f"missing-marker:{marker}")
                )
    return findings


def check_exit_blocker_policy(root: Path) -> list[Finding]:
    """Verify fallback paths are routed to explicit exit evidence."""
    paths = tuple(EXIT_BLOCKER_POLICY_MARKERS)
    findings = check_required_files(root, paths, "skill_exit_blocker_policy")
    for path, markers in EXIT_BLOCKER_POLICY_MARKERS.items():
        resolved = readable_path(root, path)
        if resolved is None:
            continue
        text = resolved.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "skill_exit_blocker_policy",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
        for match in EXIT_BLOCKER_FORBIDDEN_RE.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    "skill_exit_blocker_policy",
                    path,
                    f"forbidden-fallback-completion-wording:{line_no}",
                )
            )
        if "accepted_with_reason" in text and "explicit_approval_evidence" not in text:
            findings.append(
                Finding(
                    "skill_exit_blocker_policy",
                    path,
                    "accepted-without-explicit-approval-evidence",
                )
            )
    return findings


def check_document_structure_routing(root: Path) -> list[Finding]:
    """Verify docs edit routing keeps structure analysis mechanically visible."""
    paths = tuple(DOCUMENT_STRUCTURE_ROUTING_MARKERS)
    findings = check_required_files(root, paths, "document_structure_routing")
    for path, markers in DOCUMENT_STRUCTURE_ROUTING_MARKERS.items():
        resolved = readable_path(root, path)
        if resolved is None:
            continue
        text = resolved.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "document_structure_routing",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
    return findings


def collect_marker_contract_findings(
    root: Path, check: str, required_markers: dict[str, tuple[str, ...]]
) -> list[Finding]:
    """Verify a manifest-backed marker contract against repository files."""
    paths = tuple(required_markers)
    findings = check_required_files(root, paths, check)
    for path, markers in required_markers.items():
        resolved = readable_path(root, path)
        if resolved is None:
            continue
        text = resolved.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(Finding(check, path, f"missing-marker:{marker}"))
    return findings


def check_closeout_readiness(root: Path) -> list[Finding]:
    """Verify workflow delegates terminal readiness to the closeout owner."""
    findings = check_required_files(
        root,
        (CLOSEOUT_WORKFLOW_PATH, CLOSEOUT_OWNER_PATH),
        "workflow_readiness",
    )
    workflow = readable_path(root, CLOSEOUT_WORKFLOW_PATH)
    if workflow is not None:
        text = workflow.read_text(encoding="utf-8")
        for marker in CLOSEOUT_WORKFLOW_DELEGATION_MARKERS:
            if marker not in text:
                findings.append(
                    Finding(
                        "workflow_readiness",
                        CLOSEOUT_WORKFLOW_PATH,
                        f"missing-owner-delegation:{marker}",
                    )
                )
    owner = readable_path(root, CLOSEOUT_OWNER_PATH)
    if owner is not None:
        text = owner.read_text(encoding="utf-8")
        for marker in CLOSEOUT_OWNER_MARKERS:
            if marker not in text:
                findings.append(
                    Finding(
                        "workflow_readiness",
                        CLOSEOUT_OWNER_PATH,
                        f"missing-terminal-owner-marker:{marker}",
                    )
                )
    return findings


def check_document_claim_grounding(root: Path) -> list[Finding]:
    """Verify canonical docs route prose claims through evidence and proof status."""
    paths = tuple(DOCUMENT_CLAIM_GROUNDING_MARKERS)
    findings = check_required_files(root, paths, "document_claim_grounding")
    for path, markers in DOCUMENT_CLAIM_GROUNDING_MARKERS.items():
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "document_claim_grounding",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
        for match in PROVISIONAL_CANONICAL_WORDING_RE.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.start())
            if line_end == -1:
                line_end = len(text)
            line = text[line_start:line_end]
            if PROVISIONAL_GROUNDING_RE.search(line):
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    "document_claim_grounding",
                    path,
                    f"provisional-wording-without-grounding:{line_no}",
                )
            )
    return findings


def check_test_contract_routing(root: Path) -> list[Finding]:
    """Verify contract-only wrappers route to static validation before tests."""
    paths = tuple(TEST_CONTRACT_ROUTING_MARKERS)
    findings = check_required_files(root, paths, "test_contract_routing")
    for path, markers in TEST_CONTRACT_ROUTING_MARKERS.items():
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "test_contract_routing",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
    return findings


def check_validation_failure_response_owner_propagation(root: Path) -> list[Finding]:
    """Reject stale projection docs as validation-failure taxonomy owners."""
    findings: list[Finding] = []
    for path in VALIDATION_FAILURE_RESPONSE_MARKERS:
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for phrase in VALIDATION_FAILURE_RESPONSE_STALE_OWNER_PHRASES:
            if phrase in text:
                findings.append(
                    Finding(
                        "validation_failure_response",
                        path,
                        f"stale-taxonomy-owner:{phrase}",
                    )
                )
    return findings


def check_mathematical_necessity_gate(root: Path) -> list[Finding]:
    """Verify mathematical judgments stay wired to necessity evidence."""
    paths = tuple(MATHEMATICAL_NECESSITY_MARKERS)
    findings = check_required_files(root, paths, "mathematical_necessity_gate")
    for path, markers in MATHEMATICAL_NECESSITY_MARKERS.items():
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "mathematical_necessity_gate",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
    return findings


def check_implementation_guardrails(root: Path) -> list[Finding]:
    """Verify implementation ownership and acceptance guardrails stay visible."""
    paths = tuple(IMPLEMENTATION_GUARDRAIL_MARKERS)
    findings = check_required_files(root, paths, "implementation_guardrails")
    for path, markers in IMPLEMENTATION_GUARDRAIL_MARKERS.items():
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "implementation_guardrails",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
    return findings


def check_refactor_sequence(root: Path) -> list[Finding]:
    """Verify refactor procedure stays routed through the two-stage sequence."""
    paths = tuple(REFACTOR_SEQUENCE_MARKERS)
    findings = check_required_files(root, paths, "refactor_sequence")
    for path, markers in REFACTOR_SEQUENCE_MARKERS.items():
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "refactor_sequence",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
    return findings


def check_review_issue_routing(root: Path) -> list[Finding]:
    """Verify review findings stay connected to durable issue routes."""
    paths = tuple(REVIEW_ISSUE_ROUTING_MARKERS)
    findings = check_required_files(root, paths, "review_issue_routing")
    for path, markers in REVIEW_ISSUE_ROUTING_MARKERS.items():
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "review_issue_routing",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
    return findings


def check_prompt_eval_wiring(root: Path) -> list[Finding]:
    """Verify prompt evals cover convention verifier and skill-call routing."""
    path = "eval/definitions/skill_workflow_prompt_eval.toml"
    findings = check_required_files(root, (path,), "prompt_eval")
    if findings:
        return findings
    text = read_text(root, path)
    for marker in PROMPT_EVAL_MARKERS:
        if marker not in text:
            findings.append(Finding("prompt_eval", path, f"missing-marker:{marker}"))
    return findings


def check_hook_guardrail_policy(root: Path) -> list[Finding]:
    """Verify hook severity stays centralized and fail-open by default."""
    findings: list[Finding] = []
    for path, markers in HOOK_GUARDRAIL_POLICY_MARKERS.items():
        resolved = readable_path(root, path)
        if resolved is None:
            findings.append(
                Finding("hook_guardrail_policy", path, "missing-required-file")
            )
            continue
        text = resolved.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                findings.append(
                    Finding(
                        "hook_guardrail_policy",
                        path,
                        f"missing-marker:{marker}",
                    )
                )
    return findings


def check_owner_map_entrypoints(root: Path) -> list[Finding]:
    """Verify thin entrypoint docs keep required owner-map anchors."""
    findings = check_required_files(
        root,
        tuple(OWNER_MAP_ENTRYPOINT_TABLE_ROWS),
        "owner_map_entrypoints",
    )
    for path in OWNER_MAP_ENTRYPOINT_TABLE_ROWS:
        resolved = readable_path(root, path)
        if resolved is None:
            continue
        if duplicate_root_view_entrypoint(root, path):
            continue
        section_rows = owner_map_entrypoint_rows(root, path)
        text = resolved.read_text(encoding="utf-8")
        for heading, expected_rows in section_rows:
            section = markdown_section_lines(text, heading)
            if section is None:
                findings.append(
                    Finding(
                        "owner_map_entrypoints",
                        path,
                        f"missing-heading:{heading}",
                    )
                )
                continue
            table_rows = markdown_table_rows(section)
            if not table_rows:
                findings.append(
                    Finding(
                        "owner_map_entrypoints",
                        path,
                        f"missing-owner-table:{heading}",
                    )
                )
                continue
            for row_markers in expected_rows:
                if any(
                    all(marker in row for marker in row_markers) for row in table_rows
                ):
                    continue
                findings.append(
                    Finding(
                        "owner_map_entrypoints",
                        path,
                        f"missing-owner-row:{row_markers[0]}",
                    )
                )
    return findings


def check_entrypoint_delegated_sections(root: Path) -> list[Finding]:
    """Verify runtime entrypoints delegate detailed procedures to owner surfaces."""
    findings: list[Finding] = []
    for path in ENTRYPOINT_DELEGATION_PATHS:
        resolved = readable_path(root, path)
        if resolved is None:
            findings.append(
                Finding("entrypoint_delegation", path, "missing-required-file")
            )
            continue
        if duplicate_root_view_entrypoint(root, path):
            continue
        text = resolved.read_text(encoding="utf-8")
        for heading in ENTRYPOINT_DELEGATED_SECTION_HEADINGS:
            if markdown_section_lines(text, heading) is not None:
                findings.append(
                    Finding(
                        "entrypoint_delegation",
                        path,
                        f"delegated-section:{heading}",
                    )
                )
    return findings


def check_convention_assertions(root: Path) -> list[Finding]:
    """Verify convention documents expose checkable normative assertions."""
    findings: list[Finding] = []
    for path in CONVENTION_SOURCES:
        full_path = readable_path(root, path)
        if full_path is None:
            continue
        text = full_path.read_text(encoding="utf-8")
        normative_lines = NORMATIVE_RE.findall(text)
        if normative_lines and not VERIFICATION_RE.search(text):
            findings.append(
                Finding(
                    "convention_assertions",
                    path,
                    "normative-lines-without-verification-route",
                )
            )
    return findings


def check_legacy_forwarder_warning_policy(root: Path) -> list[Finding]:
    """Verify legacy forwarders emit caller/action migration warnings."""
    findings: list[Finding] = []
    tools_root = root / "tools"
    if tools_root.is_dir():
        for path in sorted(
            candidate
            for pattern in ("*.py", "*.sh")
            for candidate in tools_root.rglob(pattern)
            if candidate.is_file()
        ):
            text = path.read_text(encoding="utf-8", errors="replace")
            if FORWARDER_WARNING_REQUIRED_MARKER not in text:
                continue
            relative = path.relative_to(root).as_posix()
            for marker in FORWARDER_WARNING_MARKERS:
                if marker not in text:
                    findings.append(
                        Finding(
                            "legacy_forwarder_warning",
                            relative,
                            f"missing-marker:{marker}",
                        )
                    )

    policy_text = "\n".join(
        resolved.read_text(encoding="utf-8", errors="replace")
        for path in (
            "documents/codex/codex-configuration-reference.md",
            ".codex/README.md",
        )
        if (resolved := readable_path(root, path)) is not None
    )
    if policy_text:
        for marker in AGENTS_FORWARDER_POLICY_MARKERS:
            if marker not in policy_text:
                findings.append(
                    Finding(
                        "legacy_forwarder_warning",
                        "AGENTS.md",
                        f"missing-policy-marker:{marker}",
                    )
                )
    return findings


def run_checks(root: Path) -> list[Finding]:
    """Run all convention compliance wiring checks."""
    findings: list[Finding] = []
    findings.extend(
        check_required_files(root, CONVENTION_SOURCES, "convention_sources")
    )
    findings.extend(check_tool_gates(root))
    findings.extend(check_workflow_hooks(root))
    findings.extend(check_skill_routing(root))
    findings.extend(check_exit_blocker_policy(root))
    findings.extend(check_document_structure_routing(root))
    findings.extend(
        collect_marker_contract_findings(
            root, "document_split_decision", DOCUMENT_SPLIT_DECISION_MARKERS
        )
    )
    findings.extend(
        collect_marker_contract_findings(
            root, "design_integrity_gate", DESIGN_INTEGRITY_GATE_MARKERS
        )
    )
    findings.extend(
        collect_marker_contract_findings(
            root,
            "static_read_validation_policy",
            STATIC_READ_VALIDATION_POLICY_MARKERS,
        )
    )
    findings.extend(
        collect_marker_contract_findings(
            root,
            "literature_backed_skill_call_order",
            LITERATURE_BACKED_SKILL_CALL_ORDER_MARKERS,
        )
    )
    findings.extend(
        collect_marker_contract_findings(
            root,
            "responsibility_preflight_gate",
            RESPONSIBILITY_PREFLIGHT_GATE_MARKERS,
        )
    )
    findings.extend(
        collect_marker_contract_findings(
            root,
            "experiment_execution_surface_guard",
            EXPERIMENT_EXECUTION_SURFACE_GUARD_MARKERS,
        )
    )
    findings.extend(
        collect_marker_contract_findings(
            root,
            "branch_worktree_creation_guard",
            BRANCH_WORKTREE_CREATION_GUARD_MARKERS,
        )
    )
    findings.extend(check_closeout_readiness(root))
    findings.extend(check_document_claim_grounding(root))
    findings.extend(check_test_contract_routing(root))
    findings.extend(
        collect_marker_contract_findings(
            root,
            "validation_failure_response",
            VALIDATION_FAILURE_RESPONSE_MARKERS,
        )
    )
    findings.extend(check_validation_failure_response_owner_propagation(root))
    findings.extend(check_mathematical_necessity_gate(root))
    findings.extend(check_implementation_guardrails(root))
    findings.extend(check_refactor_sequence(root))
    findings.extend(check_review_issue_routing(root))
    findings.extend(
        collect_marker_contract_findings(
            root, "solid_coding_contract", SOLID_CODING_CONTRACT_MARKERS
        )
    )
    findings.extend(
        collect_marker_contract_findings(
            root,
            "source_file_definition_order",
            SOURCE_FILE_DEFINITION_ORDER_MARKERS,
        )
    )
    findings.extend(check_prompt_eval_wiring(root))
    findings.extend(check_hook_guardrail_policy(root))
    findings.extend(check_convention_assertions(root))
    findings.extend(check_legacy_forwarder_warning_policy(root))
    return sorted(
        findings,
        key=lambda finding: (finding.check, finding.path, finding.detail),
    )


def render_json(root: Path, findings: Sequence[Finding]) -> str:
    """Render JSON output."""
    workflows = [
        path
        for path in WORKFLOW_GATE_CONSUMERS
        if readable_path(root, path) is not None
    ]
    payload = {
        "status": "pass" if not findings else "fail",
        "findings": [asdict(finding) for finding in findings],
        "convention_sources": len(CONVENTION_SOURCES),
        "tool_gates": len(TOOL_GATES),
        "workflow_prompts": len(workflows),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run convention compliance checks."""
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    findings = run_checks(root)

    if args.format == "json":
        print(render_json(root, findings))
    else:
        for finding in findings:
            print(finding.render())
        print(f"CONVENTION_COMPLIANCE_SOURCES={len(CONVENTION_SOURCES)}")
        print(f"CONVENTION_COMPLIANCE_TOOL_GATES={len(TOOL_GATES)}")
        print(f"CONVENTION_COMPLIANCE_WORKFLOWS={len(WORKFLOW_GATE_CONSUMERS)}")
        print(f"CONVENTION_COMPLIANCE_FINDINGS={len(findings)}")
        print(f"CONVENTION_COMPLIANCE={'pass' if not findings else 'fail'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
