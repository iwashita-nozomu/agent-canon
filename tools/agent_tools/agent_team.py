#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides agent team agent workflow automation.
# upstream design ../README.md shared automation index
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared vendor-only document packet policy
# upstream implementation ./skill_tool_commands.py builds selected skill command packets.
# @dependency-end
"""Shared runtime helpers for the permanent agent team."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import yaml
from route import decide_skills, implementation_handoff_required, load_skill_route_rules
from skill_tool_commands import (
    PROMPT_PLACEHOLDER,
    SkillCommandPacket,
    packet_for_skill,
)
from task_authority import AUTHORITY_FILE_NAME, build_default_task_authority

ROOT = Path(__file__).resolve().parents[2]
TEAM_CONFIG_PATH = ROOT / "agents" / "agents_config.json"
DEFAULT_REPORT_ROOT = Path("reports") / "agents"
TEMPLATE_ROOT = ROOT / "agents" / "templates"
TEMPLATE_PARTIAL_ROOT = TEMPLATE_ROOT / "_partials"
TEMPLATE_PARTIAL_RE = re.compile(r"\{\{>\s*([A-Za-z0-9_-]+)\s*\}\}")
GIT_STATUS_SHORT_MIN_LINE_LENGTH = 4
GIT_STATUS_SHORT_PATH_START = 3
DEPENDENCY_MANIFEST_CLOSE_MARKER = "-->"
RUN_ID_TASK_SLUG_MAX_CHARS = 40
SHA256_READ_CHUNK_BYTES = 65_536
NEWLINE = "\n"
PYTHON_SUFFIXES = {".py", ".pyi"}
CPP_SUFFIXES = {
    ".c",
    ".cc",
    ".cp",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".ixx",
    ".tpp",
    ".ipp",
}
CPP_PATH_MARKERS = (
    "CMakeLists.txt",
    "cmake/",
    "src/",
    "include/",
    "lib/",
)
DOC_SUFFIXES = {".md", ".rst", ".txt"}
CONFIG_SUFFIXES = {".json", ".toml", ".yaml", ".yml"}
DOC_OR_RUNTIME_PATH_MARKERS = (
    ".agents/",
    ".codex/",
    ".devcontainer/",
    ".github/",
    "agents/",
    "documents/",
    "memory/",
    "notes/",
    "tools/catalog.yaml",
)
CODEX_AGENT_ROOT = ROOT / ".codex" / "agents"
SUBAGENT_STARTUP_ROUTE = "agents/internal-routines/subagent-startup.md"
DEFERRED_SPAWN_ROLE_IDS = {
    "implementer",
    "change_reviewer",
    "final_reviewer",
    "verifier",
    "auditor",
}
INITIAL_INTAKE_AGENT_TYPES = (
    "requirements_organizer",
    "explorer",
    "execution_planner",
)
STANDARD_AGENT_WAVE_SEQUENCE = ("plan", "review", "edit")
STANDARD_AGENT_WAVE_SEQUENCE_SOURCE = (
    "agents/canonical/CODEX_SUBAGENTS.md#Wave Plan Contract"
)
STANDARD_AGENT_WAVE_SEQUENCE_GATE = "plan_packet,review_gate,edit_handoff"
USER_FACING_LANGUAGE_POLICY_SOURCE = "AGENTS.md#Template Context"
USER_FACING_LANGUAGE = "ja"
USER_FACING_LANGUAGE_SCOPE = (
    "updates",
    "final_reports",
    "review_summaries",
    "handoff_guidance",
    "reader_facing_docs",
)
USER_FACING_MACHINE_FIELDS = "canonical_keys_commands_paths_role_ids_schemas"
USER_FACING_LANGUAGE_RULE = (
    "人間が読む説明、作業更新、最終報告、レビュー要約、handoff guidance、"
    "reader-facing docs は日本語を使う。機械可読の key、command、path、"
    "role id、schema は正本表記を保つ。"
)
CONTRACT_COMPLETE_IMPLEMENTATION_POLICY_SOURCE = (
    "agents/canonical/CODEX_WORKFLOW.md#Implementation"
)
CONTRACT_COMPLETE_IMPLEMENTATION_SCOPE_BASIS = "contract_required_behavior"
CONTRACT_COMPLETE_IMPLEMENTATION_REQUIRED_INPUTS = (
    "request_clause_ids",
    "acceptance_contract",
    "implementation_source_packet",
    "design_to_implementation_trace",
    "dependency_expanded_scope",
    "pre_handoff_gate_status",
    "validation_route",
    "review_gate",
)
CONTRACT_COMPLETE_IMPLEMENTATION_ROUTE_SIGNALS = (
    "apparent_breadth",
    "owner_bounded_change",
    "mvp",
    "thin_slice",
)
CONTRACT_COMPLETE_IMPLEMENTATION_ESCALATION = "design_issue_blocker_to_gate_5_6"
CONTRACT_COMPLETE_IMPLEMENTATION_RULE = (
    "実装 behavior は request clauses、acceptance contract、"
    "Implementation Source Packet、Design-To-Implementation Trace、"
    "dependency-expanded scope、validation route、review gate から導く。"
    "見た目の広さ、Owner-Bounded Change、MVP、thin slice は暫定的な routing、"
    "wave、validation profile の選択 signal に留め、owner boundary や "
    "impact surface が違うと分かった時点で route を更新する。contract gap、"
    "責務境界、API shape、依存方向、runtime contract の不足は "
    "design_issue_blocker として Gate 5-6 へ戻す。"
)
IMPLEMENTATION_HANDOFF_REQUIRED = "yes"
PARENT_REPO_EDITS_ALLOWED = "no"
PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED = "yes"
PARENT_DIRECT_WRITE_EXCEPTION = "-"
REPO_TOOL_ROUTING_POLICY_SOURCE = "agents/skills/task-routing.md#Standard Command"
REPO_TOOL_ROUTING_OWNER = "tools/agent_tools/skill_tool_commands.py"
REPO_TOOL_ROUTING_STATUS = "selected_skill_command_packets"
REPO_TOOL_ROUTING_ROUTE_BASIS = "selected_public_skills"
REPO_TOOL_ROUTING_EXECUTION_MODE = "sequential_by_skill_and_stage"
REPO_TOOL_ROUTING_SEQUENCE = (
    "show_skill_packet",
    "run_required_commands",
    "run_task_matching_conditional_commands",
    "run_validation_commands",
)
REPO_TOOL_ROUTING_SHOW_COMMAND_TEMPLATE = (
    "python3 tools/agent_tools/skill_tool_commands.py show "
    "--skill <skill> --format text"
)
REPO_TOOL_ROUTING_CHECK_COMMAND = (
    "python3 tools/agent_tools/skill_tool_commands.py check"
)
REPO_TOOL_ROUTING_STAGE_FIELDS = (
    "required_commands",
    "conditional_commands",
    "validation_commands",
)
REPO_DYNAMIC_SKILL_ROUTING_STATUS = "related_skill_candidates"
REPO_DYNAMIC_SKILL_ROUTING_COMMAND = (
    'python3 tools/agent_tools/route.py --prompt "<user request>" --format json'
)
REPO_DYNAMIC_SKILL_AREA_COMMAND = (
    "python3 tools/agent_tools/route.py --area skills --changed <paths...>"
)
REPO_DYNAMIC_SKILL_ROUTING_NEXT = "add_skill_then_regenerate_repo_tool_routes"
PRE_HANDOFF_SCOPE_POLICY_SOURCE = (
    "agents/COMMUNICATION_PROTOCOL.md#Pre-Edit Repository Investigation Packet"
)
PRE_HANDOFF_SCOPE_SEQUENCE = (
    "surface_route_seed",
    "responsibility_search",
    "reuse_survey",
    "stale_surface_scan",
    "dependency_expansion",
    "handoff_scope",
)
PRE_HANDOFF_SCOPE_STATUS = "seed_then_expand_before_handoff"
PRE_HANDOFF_SCOPE_HANDOFF_RULE = (
    "allowed_paths と write_scope は surface-route seed、responsibility search、"
    "reuse survey、stale-surface scan、dependency expansion から導く handoff 制約"
)
PRE_HANDOFF_GATE_STATUS_SOURCE = (
    "agents/COMMUNICATION_PROTOCOL.md#Handoff Packet and Parent-Direct Context Note"
)
PRE_HANDOFF_GATE_STATUS_DEFAULT = "pending_design_review_gate_check"
PRE_HANDOFF_GATE_STATUS_REQUIRED_EVIDENCE = (
    "current_design_brief",
    "design_review_artifact_under_review",
    "design_review_decision_approve",
    "waterfall_gate_check_design_pass",
    "document_flow_review_when_active",
)
VALIDATION_FAILURE_TRIAGE_TRIGGER = "validation_failure_requires_parallel_triage"
VALIDATION_FAILURE_REPAIR_REQUIRED_FIELDS = (
    "failing_contract",
    "observation_level",
    "cause_classification",
    "intent_preservation",
    "evidence",
)
VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES = (
    "repair_same_intent",
    "redesign_same_intent",
    "escalate_design_conflict",
)
CONTRACT_COMPLETE_IMPLEMENTATION_HANDOFF_INSERT_INDEX = 6
DEFAULT_QUALITY_CHECK_POLICY_SOURCE = (
    "agents/canonical/CODEX_SUBAGENTS.md#Quality Check Default"
)
DEFAULT_QUALITY_CHECK_ROLE_IDS = (
    "test_designer",
    "docs_workflow_steward",
    "python_reviewer",
    "cpp_reviewer",
    "change_reviewer",
)
DEFAULT_QUALITY_CHECK_STAGES = (
    "review_before_edit_handoff",
    "post_edit_review",
)
DEFAULT_QUALITY_CHECK_STATIC_COMMANDS = (
    "python3 tools/agent_tools/check_convention_compliance.py",
    "python3 tools/agent_tools/check_dependency_headers.py --changed",
    "bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing",
    "bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header",
    "python3 tools/agent_tools/helper_function_inventory.py --root . --changed --baseline-ref HEAD",
    "python3 tools/oop/python/readability.py --root . --min-score 95 <changed-python-paths>",
    "python3 tools/agent_tools/check_solid_evidence.py --root . <changed-python-paths> --evidence <oop-readability-report>",
    "tools/bin/agent-canon docs check <changed-markdown-paths>",
)
DYNAMIC_EXPANSION_ROLE_STAGE_WAVES = (
    (
        "manager_reviewer",
        "scheduler",
        "schedule_reviewer",
        "project_reviewer",
        "docs_workflow_steward",
        "prompt_config_reviewer",
        "researcher",
    ),
    ("designer",),
    ("design_reviewer", "document_flow_reviewer", "test_designer"),
    ("implementer", "experimenter", "infra_steward"),
    (
        "change_reviewer",
        "research_reviewer",
        "experiment_reviewer",
        "report_reviewer",
        "reproducibility_reviewer",
        "artifact_reviewer",
        "scientific_computing_reviewer",
        "benchmark_reviewer",
        "fair_data_reviewer",
        "ml_science_reviewer",
        "citation_evidence_reviewer",
        "notation_definition_reviewer",
        "logic_gap_reviewer",
        "infra_reviewer",
        "python_reviewer",
        "cpp_reviewer",
    ),
    ("final_reviewer",),
)
NON_SPAWN_WAVE_ROLE_IDS = {"manager", "verifier", "auditor"}
SAME_ROLE_SUBAGENT_INSTANCE_POLICY = {
    "status": "allowed_with_distinct_packets",
    "identity_key": "role_type+instance_id",
    "parallel_read_only": "allowed_when_input_packets_or_review_focus_are_distinct",
    "parallel_write": "allowed_only_with_disjoint_write_scopes_and_parent_integration_order",
    "collision_policy": "serialize_current_checkout_waves",
}
SAME_ROLE_SUBAGENT_REQUIRED_FIELDS = (
    "role_type",
    "instance_id",
    "input_packet",
    "allowed_paths",
    "do_not_read",
    "expected_output",
    "write_scope",
    "validation_route",
    "review_gate",
)
SUBAGENT_WAVE_RECORD_COMMAND_TEMPLATE = (
    "python3 tools/agent_tools/workflow_monitor.py --report-dir {report_dir} "
    '--subagent-wave "wave_id=<WAVE-N> parent_or_delegate=<parent-or-role> '
    "spawn_authority=<authority> trigger=<trigger> budget_before=<used/limit> "
    "budget_after=<used/limit> runtime_max_threads=<n> runtime_max_depth=<n> "
    "spawned_roles=<roles-or-none> role_instances=<role:instance:packet> "
    "skipped_roles=<roles-or-none> allowed_paths=<paths> do_not_read=<paths> "
    "write_scope=<scope> validation_route=<route> review_gate=<gate> "
    'handoff_artifacts=<artifacts> status=<status>"'
)
COMMON_PROMPT_MUST_INCLUDE = (
    "request_clause_ids",
    "run_report_dir",
    "team_manifest_path",
    "user_facing_language_policy",
    "contract_complete_implementation_policy",
    "standard_wave_sequence",
    "pre_handoff_scope_policy",
    "pre_handoff_gate_status",
    "default_quality_check_policy",
    "subagent_lifecycle_policy",
    "subagent_startup_route",
    "cross_cutting_document_packet",
    "role_document_packet",
    "context_artifacts",
    "allowed_paths",
    "do_not_read",
    "expected_output_artifacts",
    "expected_output_schema",
    "implementation_surface_route",
    "repo_tool_routing_policy",
    "tool_reuse_ledger",
    "pre_edit_rejection_prediction",
    "dependency_files_header_plan",
    "next_review_gate",
)
CURRENT_STAGE_SKILLS = {
    "$agent-orchestration",
    "$task-routing",
    "$literature-survey",
    "$research-workflow",
    "$environment-maintenance",
    "$comprehensive-development",
    "$adaptive-improvement-loop",
    "$refactor-loop",
    "$paper-writing",
}
ROLE_DOCUMENT_PACKET_SPECS: dict[str, dict[str, object]] = {
    "manager": {
        "artifact_keys": ["intent_brief", "user_request_contract", "schedule"],
        "workspace_paths": ["agents/workflows/implementation-waterfall-workflow.md"],
        "notes": "Requirements and planning start from explicit documented clauses and stage plan.",
    },
    "designer": {
        "artifact_keys": ["intent_brief", "user_request_contract", "schedule"],
        "workspace_paths": [
            "agents/workflows/implementation-waterfall-workflow.md",
            "agents/canonical/CODEX_WORKFLOW.md",
        ],
        "notes": (
            "Detailed design must read upstream documented requirements and waterfall rules before "
            "design begins."
        ),
    },
    "design_reviewer": {
        "artifact_keys": ["user_request_contract", "schedule", "design_brief"],
        "workspace_paths": ["documents/REVIEW_PROCESS.md"],
        "notes": "Design review checks the same upstream packet and the resulting design brief.",
    },
    "test_designer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
        ],
        "workspace_paths": ["agents/workflows/implementation-waterfall-workflow.md"],
        "notes": "Test design derives cases from the approved design packet.",
    },
    "implementer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
            "document_flow_review",
            "test_plan",
        ],
        "workspace_paths": [
            "agents/workflows/implementation-waterfall-workflow.md",
            "agents/canonical/CODEX_WORKFLOW.md",
        ],
        "must_cite_before_edit": True,
        "notes": "Implementation must read and cite the approved design packet before editing.",
    },
    "change_reviewer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
            "test_plan",
            "change_review",
        ],
        "workspace_paths": ["documents/REVIEW_PROCESS.md"],
        "notes": "Checkpoint review verifies that implementation cited the approved packet.",
    },
    "final_reviewer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
            "test_plan",
            "final_review",
        ],
        "workspace_paths": ["documents/REVIEW_PROCESS.md"],
        "notes": "Final review verifies whole-request traceability back to the approved packet.",
    },
    "scheduler": {
        "artifact_keys": ["user_request_contract", "schedule"],
        "workspace_paths": ["agents/workflows/implementation-waterfall-workflow.md"],
        "notes": "Scheduling reads explicit requirement and plan surfaces.",
    },
}
COMMON_CROSS_CUTTING_DOCUMENT_PATHS: tuple[str, ...] = (
    "documents/REVIEW_PROCESS.md",
    "documents/AGENTS_COORDINATION.md",
    "documents/coding-conventions-python.md",
    "documents/notes-lifecycle.md",
    "agents/workflows/agent-learning-workflow.md",
    "documents/agent-canon-subtree-migration.md",
    "notes/guardrails/README.md",
    "notes/guardrails/engineering_avoidances.md",
    "memory/USER_PREFERENCES.md",
    "memory/AGENT_PHILOSOPHY.md",
)
OPTIONAL_CROSS_CUTTING_DOCUMENT_PATHS: tuple[str, ...] = ("docker/README.md",)


def resolve_workspace_document_path(workspace_root: Path, relative_path: str) -> Path:
    """Resolve a document path through the root view or vendored AgentCanon source."""
    root_path = (workspace_root / relative_path).resolve()
    if root_path.exists():
        return root_path
    vendor_path = (workspace_root / "vendor" / "agent-canon" / relative_path).resolve()
    if vendor_path.exists():
        return vendor_path
    canon_path = (ROOT / relative_path).resolve()
    if canon_path.exists():
        return canon_path
    return root_path


def resolve_report_root(
    report_root: str | None,
    workspace_root: Path | None = None,
) -> Path:
    """Resolve the report root relative to the active workspace by default."""
    base_root = (
        workspace_root.resolve() if workspace_root is not None else Path.cwd().resolve()
    )
    if report_root is None:
        return (base_root / DEFAULT_REPORT_ROOT).resolve()
    candidate = Path(report_root)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_root / candidate).resolve()


@dataclass(frozen=True)
class WritePolicy:
    """Describe how one role may write to the filesystem."""

    mode: str
    allowed_artifacts: tuple[str, ...]
    allowed_directories: tuple[str, ...] = ()
    requires_worktree_scope: bool = False
    notes: str = ""


@dataclass(frozen=True)
class Role:
    """Describe one permanent team role."""

    id: str
    owns: tuple[str, ...]
    required_outputs: tuple[str, ...]
    activation: str
    write_policy: WritePolicy
    codex_agents: tuple[str, ...]


@dataclass(frozen=True)
class SubagentWaveSlot:
    """One executable subagent instance in a stage wave."""

    role_id: str
    agent_type: str

    @property
    def instance_id(self) -> str:
        """Return a stable role-instance id for wave ledgers."""
        return f"{self.role_id}_{self.agent_type}"


@dataclass(frozen=True)
class RoleWriteScope:
    """Resolved write scope for one role in one workspace."""

    role_id: str
    mode: str
    allowed_files: tuple[Path, ...]
    allowed_directories: tuple[Path, ...]
    requires_worktree_scope: bool
    worktree_scope_file: Path | None
    unresolved_reason: str | None
    notes: str


@dataclass(frozen=True)
class DocumentPacketEntry:
    """One explicit path a role must read before work."""

    path: Path
    rationale: str


@dataclass(frozen=True)
class RoleDocumentPacket:
    """Resolved explicit document packet for one role."""

    role_id: str
    read_before_work: tuple[DocumentPacketEntry, ...]
    must_cite_before_edit: bool
    notes: str


def resolve_cross_cutting_document_packet(
    workspace_root: Path,
) -> tuple[DocumentPacketEntry, ...]:
    """Resolve the common cross-cutting document packet for one workspace."""
    required_entries = tuple(
        DocumentPacketEntry(
            path=resolve_workspace_document_path(workspace_root, relative_path),
            rationale=f"cross_cutting_doc:{relative_path}",
        )
        for relative_path in COMMON_CROSS_CUTTING_DOCUMENT_PATHS
    )
    optional_entries = tuple(
        DocumentPacketEntry(
            path=resolve_workspace_document_path(workspace_root, relative_path),
            rationale=f"cross_cutting_doc:{relative_path}",
        )
        for relative_path in OPTIONAL_CROSS_CUTTING_DOCUMENT_PATHS
        if resolve_workspace_document_path(workspace_root, relative_path).exists()
    )
    return required_entries + optional_entries


@dataclass(frozen=True)
class TeamConfig:
    """Materialized team configuration."""

    raw: dict[str, object]
    team: dict[str, object]
    always_on_roles: tuple[Role, ...]
    specialist_roles: tuple[Role, ...]
    handoffs: tuple[dict[str, object], ...]
    context_policies: tuple[dict[str, object], ...]
    activation_rules: tuple[dict[str, object], ...]
    quality_gates: tuple[str, ...]
    artifacts: dict[str, str]


@dataclass(frozen=True)
class TaskCatalog:
    """Materialized task catalog."""

    raw: dict[str, object]
    workflow_families: tuple[dict[str, object], ...]
    tasks: tuple[dict[str, object], ...]
    review_packs: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class RunBundleSpec:
    """Inputs required to create a run bundle and team manifest."""

    config: TeamConfig
    report_dir: Path
    run_id: str
    task: str
    owner: str
    created_at_iso: str
    roles: tuple[Role, ...]
    workspace_root: Path
    workflow_family_id: str = ""
    manual_specialists: tuple[str, ...] = ()
    task_default_specialists: tuple[str, ...] = ()
    auto_specialists: tuple[str, ...] = ()
    default_review_packs_enabled: bool = False
    default_review_pack_ids: tuple[str, ...] = ()
    selected_skills: tuple[str, ...] = ()


def load_team_config(path: Path = TEAM_CONFIG_PATH) -> TeamConfig:
    """Load the canonical team config."""
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    raw = _as_object_mapping(parsed, "team config")
    team = _as_object_mapping(raw.get("team"), "team")
    always_on_roles = tuple(
        _parse_role(role, "always")
        for role in _as_mapping_tuple(raw.get("always_on_roles"), "always_on_roles")
    )
    specialist_roles = tuple(
        _parse_role(role, "optional")
        for role in _as_mapping_tuple(raw.get("specialist_roles"), "specialist_roles")
    )
    handoffs = _as_mapping_tuple(raw.get("handoffs"), "handoffs")
    context_policies = _as_mapping_tuple(
        raw.get("context_policies"), "context_policies"
    )
    activation_rules = _as_mapping_tuple(
        raw.get("activation_rules"), "activation_rules"
    )
    quality_gates = _as_string_tuple(raw.get("quality_gates"), "quality_gates")
    artifacts = {
        key: _as_required_string(value, f"artifacts.{key}")
        for key, value in _as_object_mapping(raw.get("artifacts"), "artifacts").items()
    }
    return TeamConfig(
        raw=raw,
        team=team,
        always_on_roles=always_on_roles,
        specialist_roles=specialist_roles,
        handoffs=handoffs,
        context_policies=context_policies,
        activation_rules=activation_rules,
        quality_gates=quality_gates,
        artifacts=artifacts,
    )


def load_task_catalog(config: TeamConfig, root: Path = ROOT) -> TaskCatalog:
    """Load the task catalog referenced by the team config."""
    catalog_path = root / str(config.team["task_catalog"])
    parsed: object = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    raw = _as_object_mapping(parsed, f"task catalog {catalog_path}")
    return TaskCatalog(
        raw=raw,
        workflow_families=_as_mapping_tuple(
            raw.get("workflow_families"), "workflow_families"
        ),
        tasks=_as_mapping_tuple(raw.get("tasks"), "tasks"),
        review_packs=_as_mapping_tuple(raw.get("review_packs"), "review_packs"),
    )


def specialist_role_ids(config: TeamConfig) -> tuple[str, ...]:
    """Return specialist role ids."""
    return tuple(role.id for role in config.specialist_roles)


def same_role_subagent_policy_output_lines() -> tuple[str, ...]:
    """Return machine-readable stdout lines for same-role subagent instances."""
    return (
        f"SAME_ROLE_SUBAGENT_INSTANCES={SAME_ROLE_SUBAGENT_INSTANCE_POLICY['status']}",
        f"SAME_ROLE_SUBAGENT_INSTANCE_KEY={SAME_ROLE_SUBAGENT_INSTANCE_POLICY['identity_key']}",
        "SAME_ROLE_SUBAGENT_REQUIRED_FIELDS="
        f"{','.join(SAME_ROLE_SUBAGENT_REQUIRED_FIELDS)}",
    )


def standard_agent_wave_sequence_output_lines() -> tuple[str, ...]:
    """Return machine-readable stdout lines for the standard Agent Wave order."""
    return (
        f"STANDARD_AGENT_WAVE_SEQUENCE={','.join(STANDARD_AGENT_WAVE_SEQUENCE)}",
        f"STANDARD_AGENT_WAVE_SEQUENCE_SOURCE={STANDARD_AGENT_WAVE_SEQUENCE_SOURCE}",
        f"STANDARD_AGENT_WAVE_SEQUENCE_GATE={STANDARD_AGENT_WAVE_SEQUENCE_GATE}",
    )


def pre_handoff_scope_policy_output_lines() -> tuple[str, ...]:
    """Return machine-readable stdout lines for scope discovery before handoff."""
    return (
        "PRE_HANDOFF_SCOPE_POLICY=discovery_before_handoff_scope",
        f"PRE_HANDOFF_SCOPE_SOURCE={PRE_HANDOFF_SCOPE_POLICY_SOURCE}",
        f"PRE_HANDOFF_SCOPE_SEQUENCE={','.join(PRE_HANDOFF_SCOPE_SEQUENCE)}",
        f"PRE_HANDOFF_SCOPE_STATUS={PRE_HANDOFF_SCOPE_STATUS}",
    )


def pre_handoff_gate_status_output_lines() -> tuple[str, ...]:
    """Return machine-readable stdout lines for gate status before handoff."""
    return (
        f"PRE_HANDOFF_GATE_STATUS={PRE_HANDOFF_GATE_STATUS_DEFAULT}",
        f"PRE_HANDOFF_GATE_STATUS_SOURCE={PRE_HANDOFF_GATE_STATUS_SOURCE}",
        "PRE_HANDOFF_GATE_STATUS_REQUIRED_EVIDENCE="
        f"{','.join(PRE_HANDOFF_GATE_STATUS_REQUIRED_EVIDENCE)}",
    )


def user_facing_language_policy_output_lines() -> tuple[str, ...]:
    """Return machine-readable stdout lines for user-facing language policy."""
    return (
        f"USER_FACING_LANGUAGE={USER_FACING_LANGUAGE}",
        f"USER_FACING_LANGUAGE_SOURCE={USER_FACING_LANGUAGE_POLICY_SOURCE}",
        f"USER_FACING_LANGUAGE_SCOPE={','.join(USER_FACING_LANGUAGE_SCOPE)}",
        f"USER_FACING_MACHINE_FIELDS={USER_FACING_MACHINE_FIELDS}",
    )


def contract_complete_implementation_policy_output_lines(
    task_text: str = "",
) -> tuple[str, ...]:
    """Return stdout lines for contract-complete implementation policy."""
    handoff_lines: tuple[str, ...] = ()
    if implementation_handoff_required(task_text):
        handoff_lines = (
            f"IMPLEMENTATION_HANDOFF_REQUIRED={IMPLEMENTATION_HANDOFF_REQUIRED}",
            f"PARENT_REPO_EDITS_ALLOWED={PARENT_REPO_EDITS_ALLOWED}",
            "PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED="
            f"{PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED}",
            f"PARENT_DIRECT_WRITE_EXCEPTION={PARENT_DIRECT_WRITE_EXCEPTION}",
        )
    return (
        *handoff_lines,
        "IMPLEMENTATION_COMPLETENESS_POLICY=contract_complete",
        "IMPLEMENTATION_COMPLETENESS_SCOPE_BASIS="
        f"{CONTRACT_COMPLETE_IMPLEMENTATION_SCOPE_BASIS}",
        "IMPLEMENTATION_COMPLETENESS_SOURCE="
        f"{CONTRACT_COMPLETE_IMPLEMENTATION_POLICY_SOURCE}",
        "IMPLEMENTATION_COMPLETENESS_REQUIRED_INPUTS="
        f"{','.join(CONTRACT_COMPLETE_IMPLEMENTATION_REQUIRED_INPUTS)}",
        "IMPLEMENTATION_COMPLETENESS_ROUTE_SIGNALS="
        f"{','.join(CONTRACT_COMPLETE_IMPLEMENTATION_ROUTE_SIGNALS)}",
        "IMPLEMENTATION_COMPLETENESS_ESCALATION="
        f"{CONTRACT_COMPLETE_IMPLEMENTATION_ESCALATION}",
    )


def normalized_public_skill_name(skill: str) -> str:
    """Return one public skill name without runtime sigils."""
    return skill.strip().removeprefix("$")


def selected_skill_names(selected_skills: tuple[str, ...]) -> tuple[str, ...]:
    """Return selected public skill names in stable first-seen order."""
    return tuple(
        dict.fromkeys(
            skill
            for raw_skill in selected_skills
            if (skill := normalized_public_skill_name(raw_skill))
        )
    )


def skill_tool_packet_command(skill: str) -> str:
    """Return the canonical command that prints one selected skill tool packet."""
    return (
        "python3 tools/agent_tools/skill_tool_commands.py show "
        f"--skill {skill} --format text"
    )


def selected_skill_command_packets(
    selected_skills: tuple[str, ...],
) -> tuple[SkillCommandPacket, ...]:
    """Build repo tool command packets for selected public skills."""
    return tuple(
        packet_for_skill(ROOT, skill) for skill in selected_skill_names(selected_skills)
    )


def conditional_commands_for_packet(packet: SkillCommandPacket) -> tuple[str, ...]:
    """Return task-matching command candidates for one skill packet."""
    if packet.discovered_commands:
        return packet.discovered_commands
    return (
        f'python3 tools/agent_tools/route.py --prompt "{PROMPT_PLACEHOLDER}" --format json',
    )


def dynamic_skill_candidate_names(
    selected_skills: tuple[str, ...],
) -> tuple[str, ...]:
    """Return related public skills that can activate in later waves."""
    selected = set(selected_skill_names(selected_skills))
    candidates: list[str] = []
    for packet in selected_skill_command_packets(selected_skills):
        for candidate in packet.related_skills:
            if candidate in selected or candidate in candidates:
                continue
            candidates.append(candidate)
    return tuple(candidates)


def format_public_skill_list(skills: tuple[str, ...]) -> str:
    """Return a machine-readable public skill list."""
    return ",".join(f"${skill}" for skill in skills) or "-"


def repo_tool_routing_policy_output_lines(
    selected_skills: tuple[str, ...],
) -> tuple[str, ...]:
    """Return stdout lines for selected-skill repo tool routing."""
    skill_names = selected_skill_names(selected_skills)
    packet_commands = tuple(skill_tool_packet_command(skill) for skill in skill_names)
    first_command = packet_commands[0] if packet_commands else "-"
    skill_list = format_public_skill_list(skill_names)
    dynamic_candidates = dynamic_skill_candidate_names(selected_skills)
    return (
        f"REPO_TOOL_ROUTING_POLICY={REPO_TOOL_ROUTING_STATUS}",
        f"REPO_TOOL_ROUTING_SOURCE={REPO_TOOL_ROUTING_POLICY_SOURCE}",
        f"REPO_TOOL_ROUTING_OWNER={REPO_TOOL_ROUTING_OWNER}",
        f"REPO_TOOL_ROUTING_ROUTE_BASIS={REPO_TOOL_ROUTING_ROUTE_BASIS}",
        f"REPO_TOOL_ROUTING_EXECUTION_MODE={REPO_TOOL_ROUTING_EXECUTION_MODE}",
        f"REPO_TOOL_ROUTING_SEQUENCE={','.join(REPO_TOOL_ROUTING_SEQUENCE)}",
        f"REPO_TOOL_ROUTING_NEXT_COMMAND={first_command}",
        f"REPO_TOOL_ROUTING_STAGE_FIELDS={','.join(REPO_TOOL_ROUTING_STAGE_FIELDS)}",
        f"REPO_TOOL_ROUTING_SKILLS={skill_list}",
        f"REPO_TOOL_ROUTING_PACKET_COUNT={len(packet_commands)}",
        f"REPO_TOOL_ROUTING_PACKET_COMMANDS={';'.join(packet_commands) or '-'}",
        f"REPO_TOOL_ROUTING_CHECK={REPO_TOOL_ROUTING_CHECK_COMMAND}",
        f"REPO_DYNAMIC_SKILL_ROUTING_POLICY={REPO_DYNAMIC_SKILL_ROUTING_STATUS}",
        f"REPO_DYNAMIC_SKILL_ROUTING_COMMAND={REPO_DYNAMIC_SKILL_ROUTING_COMMAND}",
        f"REPO_DYNAMIC_SKILL_AREA_COMMAND={REPO_DYNAMIC_SKILL_AREA_COMMAND}",
        f"REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES={format_public_skill_list(dynamic_candidates)}",
        f"REPO_DYNAMIC_SKILL_ROUTING_NEXT={REPO_DYNAMIC_SKILL_ROUTING_NEXT}",
    )


def default_quality_check_role_ids(roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return active role ids that provide the default quality-check path."""
    active_role_ids = {role.id for role in roles}
    return tuple(
        role_id
        for role_id in DEFAULT_QUALITY_CHECK_ROLE_IDS
        if role_id in active_role_ids
    )


def default_quality_check_agent_types(roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return active Codex agent types that provide the default quality-check path."""
    roles_by_id = {role.id: role for role in roles}
    agent_types: list[str] = []
    for role_id in DEFAULT_QUALITY_CHECK_ROLE_IDS:
        role = roles_by_id.get(role_id)
        if role is None:
            continue
        for agent_type in role.codex_agents:
            if agent_type not in agent_types:
                agent_types.append(agent_type)
    return tuple(agent_types)


def default_quality_check_policy_output_lines(
    roles: tuple[Role, ...],
    *,
    manual_specialists: tuple[str, ...] = (),
    task_default_specialists: tuple[str, ...] = (),
    auto_specialists: tuple[str, ...] = (),
    default_review_packs_enabled: bool = False,
    default_review_pack_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return machine-readable stdout lines for default quality-check routing."""
    review_pack_state = (
        "active" if default_review_packs_enabled else "route_without_default_packs"
    )
    return (
        "DEFAULT_QUALITY_CHECKS=enabled",
        f"DEFAULT_QUALITY_CHECK_SOURCE={DEFAULT_QUALITY_CHECK_POLICY_SOURCE}",
        "DEFAULT_QUALITY_CHECK_ROLES="
        f"{','.join(default_quality_check_role_ids(roles)) or '-'}",
        "DEFAULT_QUALITY_CHECK_AGENT_TYPES="
        f"{','.join(default_quality_check_agent_types(roles)) or '-'}",
        f"DEFAULT_QUALITY_CHECK_STAGES={','.join(DEFAULT_QUALITY_CHECK_STAGES)}",
        "DEFAULT_QUALITY_CHECK_TASK_DEFAULT_SPECIALISTS="
        f"{','.join(task_default_specialists) or '-'}",
        "DEFAULT_QUALITY_CHECK_AUTO_LANGUAGE_REVIEWERS="
        f"{','.join(auto_specialists) or '-'}",
        "DEFAULT_QUALITY_CHECK_MANUAL_SPECIALISTS="
        f"{','.join(manual_specialists) or '-'}",
        f"DEFAULT_QUALITY_CHECK_REVIEW_PACKS={review_pack_state}",
        "DEFAULT_QUALITY_CHECK_DEFAULT_REVIEW_PACKS="
        f"{','.join(default_review_pack_ids) or '-'}",
    )


def suggested_public_skills(
    task_id: str | None,
    workflow_family_id: str | None,
    task_text: str = "",
) -> tuple[str, ...]:
    """Return the public skill set required by the selected route."""
    selected = ["$agent-orchestration", "$codex-task-workflow", "$subagent-bootstrap"]
    if workflow_family_id == "research_driven_change":
        selected.append("$literature-survey")
        selected.append("$research-workflow")
    elif workflow_family_id == "platform_and_environment":
        selected.append("$environment-maintenance")
    elif workflow_family_id == "comprehensive_development":
        selected.append("$comprehensive-development")
    elif workflow_family_id == "adaptive_improvement_loop":
        selected.append("$adaptive-improvement-loop")
    if task_id == "T6":
        selected.append("$refactor-loop")
    if task_id == "T10":
        selected.append("$paper-writing")
    if task_text.strip():
        decision = decide_skills(
            task_text,
            "repo-changing",
            load_skill_route_rules(ROOT),
        )
        selected.extend(f"${skill}" for skill in decision.skills)
    return tuple(dict.fromkeys(selected))


def subagent_wave_record_command(report_dir: Path | str = "<run-report-dir>") -> str:
    """Return the canonical command for recording a spawned subagent wave."""
    return SUBAGENT_WAVE_RECORD_COMMAND_TEMPLATE.format(report_dir=str(report_dir))


def review_pack_ids(catalog: TaskCatalog) -> tuple[str, ...]:
    """Return known review pack ids."""
    return tuple(str(pack["id"]) for pack in catalog.review_packs)


def default_review_pack_ids_for_task(
    catalog: TaskCatalog,
    task_id: str,
) -> tuple[str, ...]:
    """Return review pack ids selected by default for one task."""
    selected: list[str] = []
    for pack in catalog.review_packs:
        default_tasks = _as_string_tuple(
            pack.get("default_for_tasks"),
            f"review_packs[{pack['id']}].default_for_tasks",
        )
        if task_id in default_tasks:
            selected.append(str(pack["id"]))
    return tuple(selected)


def enable_choices(config: TeamConfig, catalog: TaskCatalog) -> tuple[str, ...]:
    """Return valid --enable values for specialist roles and review packs."""
    return tuple(sorted((*specialist_role_ids(config), *review_pack_ids(catalog))))


def expand_enabled_specialists(
    config: TeamConfig,
    catalog: TaskCatalog,
    enabled_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Expand specialist role ids and named review packs into role ids."""
    specialist_ids = set(specialist_role_ids(config))
    review_packs = {str(pack["id"]): pack for pack in catalog.review_packs}
    expanded: list[str] = []
    for name in enabled_names:
        if name in specialist_ids:
            if name not in expanded:
                expanded.append(name)
            continue
        if name in review_packs:
            for role_id in _as_string_tuple(
                review_packs[name].get("specialists"),
                f"review_packs[{name}].specialists",
            ):
                resolve_role(config, role_id)
                if role_id not in expanded:
                    expanded.append(role_id)
            continue
        raise KeyError(f"unknown specialist or review pack: {name}")
    return tuple(expanded)


def resolve_role(config: TeamConfig, role_name: str) -> Role:
    """Resolve a role id to a role."""
    for role in config.always_on_roles + config.specialist_roles:
        if role_name == role.id:
            return role
    raise KeyError(f"unknown role: {role_name}")


def task_ids(catalog: TaskCatalog) -> tuple[str, ...]:
    """Return known task ids from the catalog."""
    return tuple(str(task["id"]) for task in catalog.tasks)


def discover_changed_paths(workspace_root: Path) -> tuple[str, ...]:
    """Return changed paths from git status when available."""
    result = subprocess.run(
        ["git", "-C", str(workspace_root), "status", "--short"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()

    changed: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.rstrip()
        if len(line) < GIT_STATUS_SHORT_MIN_LINE_LENGTH:
            continue
        path_part = line[GIT_STATUS_SHORT_PATH_START:]
        if " -> " in path_part:
            _, path_part = path_part.split(" -> ", 1)
        normalized = path_part.strip()
        if normalized and normalized not in changed:
            changed.append(normalized)
    return tuple(changed)


def auto_language_specialists(
    workspace_root: Path,
    changed_paths: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Infer language-specific reviewers from changed paths."""
    candidate_paths = changed_paths or discover_changed_paths(workspace_root)
    normalized_paths = tuple(
        raw_path.replace("\\", "/").lstrip("./") for raw_path in candidate_paths
    )
    has_python = any(
        normalized.startswith("python/")
        or normalized.startswith("tests/")
        or Path(normalized).suffix.lower() in PYTHON_SUFFIXES
        for normalized in normalized_paths
    )
    has_cpp = any(
        Path(normalized).suffix.lower() in CPP_SUFFIXES
        or any(
            normalized == marker or normalized.startswith(marker)
            for marker in CPP_PATH_MARKERS
        )
        for normalized in normalized_paths
    )
    has_docs_or_runtime = any(
        Path(normalized).suffix.lower() in DOC_SUFFIXES | CONFIG_SUFFIXES
        or any(
            normalized == marker or normalized.startswith(marker)
            for marker in DOC_OR_RUNTIME_PATH_MARKERS
        )
        for normalized in normalized_paths
    )
    return tuple(
        role_id
        for role_id, enabled in (
            ("python_reviewer", has_python),
            ("cpp_reviewer", has_cpp),
            ("docs_workflow_steward", has_docs_or_runtime),
        )
        if enabled
    )


def resolve_task_spec(catalog: TaskCatalog, task_id: str) -> dict[str, object]:
    """Resolve one task id from the catalog."""
    for task in catalog.tasks:
        if task.get("id") == task_id:
            return task
    raise KeyError(f"unknown task id: {task_id}")


def resolve_workflow_family(catalog: TaskCatalog, family_id: str) -> dict[str, object]:
    """Resolve one workflow family from the catalog."""
    for family in catalog.workflow_families:
        if family.get("id") == family_id:
            return family
    raise KeyError(f"unknown workflow family: {family_id}")


def workflow_spawn_budget(catalog: TaskCatalog, family_id: str) -> tuple[int, int]:
    """Return the active and write-capable spawn budget for one workflow family."""
    family = resolve_workflow_family(catalog, family_id)
    raw_budget = family.get("spawn_budget")
    if not isinstance(raw_budget, dict):
        raise RuntimeError(
            f"workflow family spawn_budget must be a mapping for {family_id}"
        )
    raw_budget = _as_object_mapping(
        cast(object, raw_budget), f"workflow_families[{family_id}].spawn_budget"
    )
    active = raw_budget.get("active_subagents")
    max_write = raw_budget.get("max_write_subagents")
    if not isinstance(active, int) or active < 1:
        raise RuntimeError(
            f"workflow family active_subagents must be >= 1 for {family_id}"
        )
    if not isinstance(max_write, int) or max_write < 1:
        raise RuntimeError(
            f"workflow family max_write_subagents must be >= 1 for {family_id}"
        )
    if max_write > active:
        raise RuntimeError(
            "workflow family max_write_subagents exceeds active_subagents "
            f"for {family_id}: {max_write} > {active}"
        )
    runtime_max_threads = codex_runtime_max_threads()
    if active > runtime_max_threads:
        raise RuntimeError(
            "workflow family active_subagents exceeds runtime max_threads "
            f"for {family_id}: {active} > {runtime_max_threads}"
        )
    return active, max_write


def codex_runtime_max_threads() -> int:
    """Return the configured runtime max_threads from .codex/config.toml."""
    return codex_runtime_agent_int("max_threads")


def codex_runtime_max_depth() -> int:
    """Return the configured runtime max_depth from .codex/config.toml."""
    return codex_runtime_agent_int("max_depth")


def codex_runtime_agent_int(key: str) -> int:
    """Return one configured integer from the Codex [agents] runtime section."""
    config_path = ROOT / ".codex" / "config.toml"
    parsed: object = tomllib.loads(config_path.read_text(encoding="utf-8"))
    data = _as_object_mapping(parsed, ".codex/config.toml")
    agents = data.get("agents")
    if not isinstance(agents, dict):
        raise RuntimeError("missing [agents] section in .codex/config.toml")
    agents = _as_object_mapping(cast(object, agents), ".codex/config.toml agents")
    value = agents.get(key)
    if not isinstance(value, int) or value < 1:
        raise RuntimeError(f"agents.{key} must be an integer >= 1")
    return value


def unique_codex_agents_for_roles(roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return unique Codex agent types in permanent-role order."""
    agents: list[str] = []
    for role in roles:
        for codex_agent in role.codex_agents:
            if codex_agent not in agents:
                agents.append(codex_agent)
    return tuple(agents)


def registered_codex_agent_types(agent_root: Path = CODEX_AGENT_ROOT) -> set[str]:
    """Return Codex agent types registered in the local runtime config."""
    if not agent_root.is_dir():
        return set()
    return {path.stem for path in agent_root.glob("*.toml") if path.is_file()}


def _role_stage_slots(
    roles_by_id: dict[str, Role],
    role_ids: tuple[str, ...],
    available_agents: set[str],
    used_slots: set[tuple[str, str]],
) -> tuple[SubagentWaveSlot, ...]:
    """Return stage-ready slots without collapsing shared agent types."""
    return tuple(
        SubagentWaveSlot(role_id=role.id, agent_type=agent_type)
        for role_id in role_ids
        for role in (roles_by_id.get(role_id),)
        if role is not None
        for agent_type in role.codex_agents
        if agent_type in available_agents
        if (role.id, agent_type) not in used_slots
    )


def _chunk_wave_slots(
    slots: tuple[SubagentWaveSlot, ...],
    active_subagents: int,
) -> tuple[tuple[SubagentWaveSlot, ...], ...]:
    """Split one role-instance stage wave within the active subagent budget."""
    if active_subagents < 1:
        return ()
    return tuple(
        slots[index : index + active_subagents]
        for index in range(0, len(slots), active_subagents)
        if slots[index : index + active_subagents]
    )


def recommended_initial_subagent_wave(
    roles: tuple[Role, ...],
    active_subagents: int,
) -> tuple[str, ...]:
    """Return executable agent_type values for the stage-ready intake wave."""
    if active_subagents < 1:
        return ()
    available_agents = set(unique_codex_agents_for_roles(roles))
    available_agents.update(registered_codex_agent_types())
    intake_agents = tuple(
        agent_type
        for agent_type in INITIAL_INTAKE_AGENT_TYPES
        if agent_type in available_agents
    )
    return intake_agents[:active_subagents]


def recommended_dynamic_expansion_waves(
    roles: tuple[Role, ...],
    active_subagents: int,
    initial_wave: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    """Return executable follow-up stage waves inside the active budget."""
    return tuple(
        tuple(slot.agent_type for slot in wave)
        for wave in recommended_dynamic_expansion_wave_slots(
            roles, active_subagents, initial_wave
        )
    )


def recommended_dynamic_expansion_wave_slots(
    roles: tuple[Role, ...],
    active_subagents: int,
    initial_wave: tuple[str, ...],
) -> tuple[tuple[SubagentWaveSlot, ...], ...]:
    """Return executable follow-up role-instance waves inside the active budget."""
    if active_subagents < 1:
        return ()
    initial_agent_types = set(initial_wave)
    available_agents = set(unique_codex_agents_for_roles(roles))
    roles_by_id = {role.id: role for role in roles}
    used_slots: set[tuple[str, str]] = set()
    waves: list[tuple[SubagentWaveSlot, ...]] = []
    staged_role_ids = {
        role_id
        for stage_role_ids in DYNAMIC_EXPANSION_ROLE_STAGE_WAVES
        for role_id in stage_role_ids
    }
    for stage_role_ids in DYNAMIC_EXPANSION_ROLE_STAGE_WAVES[:-1]:
        stage_slots = _role_stage_slots(
            roles_by_id, stage_role_ids, available_agents, used_slots
        )
        used_slots.update((slot.role_id, slot.agent_type) for slot in stage_slots)
        waves.extend(_chunk_wave_slots(stage_slots, active_subagents))
    fallback_role_ids = tuple(
        role.id
        for role in roles
        if role.id not in staged_role_ids
        and role.id not in NON_SPAWN_WAVE_ROLE_IDS
        and any(
            agent_type not in initial_agent_types for agent_type in role.codex_agents
        )
    )
    fallback_slots = _role_stage_slots(
        roles_by_id, fallback_role_ids, available_agents, used_slots
    )
    used_slots.update((slot.role_id, slot.agent_type) for slot in fallback_slots)
    waves.extend(_chunk_wave_slots(fallback_slots, active_subagents))
    final_stage_slots = _role_stage_slots(
        roles_by_id,
        DYNAMIC_EXPANSION_ROLE_STAGE_WAVES[-1],
        available_agents,
        used_slots,
    )
    waves.extend(_chunk_wave_slots(final_stage_slots, active_subagents))
    return tuple(waves)


def current_stage_skills(
    selected_skills: tuple[str, ...],
    task_text: str = "",
) -> tuple[str, ...]:
    """Return public skills to declare for the current stage only."""
    active_skills = set(CURRENT_STAGE_SKILLS)
    active_skills.update(catalog_active_stage_skills())
    if implementation_handoff_required(task_text):
        active_skills.add("$subagent-bootstrap")
    return tuple(skill for skill in selected_skills if skill in active_skills)


def deferred_stage_skills(
    selected_skills: tuple[str, ...],
    task_text: str = "",
) -> tuple[str, ...]:
    """Return selected public skills that should wait for dynamic wave triggers."""
    active = set(current_stage_skills(selected_skills, task_text))
    return tuple(skill for skill in selected_skills if skill not in active)


def catalog_active_stage_skills() -> tuple[str, ...]:
    """Return public skills marked active in the skill catalog."""
    return tuple(
        f"${rule.skill}"
        for rule in load_skill_route_rules(ROOT)
        if rule.stage_policy == "active"
    )


def format_subagent_wave(agent_types: tuple[str, ...]) -> str:
    """Render one wave as a comma-separated agent_type list."""
    return ",".join(agent_types)


def format_subagent_wave_chunks(waves: tuple[tuple[str, ...], ...]) -> str:
    """Render follow-up waves in a machine-readable summary form."""
    return ";".join(
        f"WAVE-{index + 2}={format_subagent_wave(wave)}"
        for index, wave in enumerate(waves)
    )


def format_subagent_role_instance_wave_chunks(
    waves: tuple[tuple[SubagentWaveSlot, ...], ...],
) -> str:
    """Render follow-up role-instance waves in a machine-readable summary form."""
    return ";".join(
        f"WAVE-{index + 2}="
        + ",".join(
            f"{slot.role_id}:{slot.agent_type}:{slot.instance_id}" for slot in wave
        )
        for index, wave in enumerate(waves)
    )


def default_specialists_for_task(
    config: TeamConfig,
    catalog: TaskCatalog,
    task_id: str,
    include_default_review_packs: bool = True,
) -> tuple[str, ...]:
    """Return task-default specialist ids including default review packs."""
    task = resolve_task_spec(catalog, task_id)
    family = resolve_workflow_family(catalog, str(task["family"]))
    family_roles = family.get("roles", {})
    if not isinstance(family_roles, dict):
        raise RuntimeError(
            f"workflow family roles must be a mapping for {family['id']}"
        )
    family_roles = _as_object_mapping(
        cast(object, family_roles), f"workflow_families[{family['id']}].roles"
    )
    family_specialists = _as_string_tuple(
        family_roles.get("specialists"),
        f"workflow_families[{family['id']}].roles.specialists",
    )
    selected: list[str] = []

    for role_id in _as_string_tuple(
        task.get("specialists"), f"tasks[{task_id}].specialists"
    ):
        if role_id not in family_specialists:
            raise RuntimeError(
                f"task {task_id} specialist {role_id} is not declared in family {family['id']}"
            )
        resolve_role(config, role_id)
        if role_id not in selected:
            selected.append(role_id)

    if include_default_review_packs:
        for pack in catalog.review_packs:
            default_tasks = _as_string_tuple(
                pack.get("default_for_tasks"),
                f"review_packs[{pack['id']}].default_for_tasks",
            )
            if task_id not in default_tasks:
                continue
            for role_id in _as_string_tuple(
                pack.get("specialists"),
                f"review_packs[{pack['id']}].specialists",
            ):
                resolve_role(config, role_id)
                if role_id not in selected:
                    selected.append(role_id)

    return tuple(selected)


def select_roles(
    config: TeamConfig,
    enabled_specialists: list[str],
    full_team: bool,
    catalog: TaskCatalog | None = None,
    workflow_family_id: str | None = None,
) -> tuple[Role, ...]:
    """Return the active roles for one run."""
    if full_team:
        return config.always_on_roles + config.specialist_roles
    always_on_roles = workflow_always_on_roles(config, catalog, workflow_family_id)
    enabled_roles = tuple(resolve_role(config, name) for name in enabled_specialists)
    selected_roles = list(always_on_roles)
    selected_ids = {role.id for role in selected_roles}
    for role in enabled_roles:
        if role.id not in selected_ids:
            selected_roles.append(role)
            selected_ids.add(role.id)
    enabled_set = {role.id for role in enabled_roles}
    enabled_activations = {
        role.activation for role in enabled_roles if role in config.specialist_roles
    }
    selected_specialists = tuple(
        role
        for role in config.specialist_roles
        if role.id in enabled_set or role.activation in enabled_activations
        if role.id not in selected_ids
    )
    return tuple(selected_roles) + selected_specialists


def workflow_always_on_roles(
    config: TeamConfig,
    catalog: TaskCatalog | None,
    workflow_family_id: str | None,
) -> tuple[Role, ...]:
    """Return family-specific always-on roles when a workflow family declares them."""
    if catalog is None or not workflow_family_id:
        return config.always_on_roles
    family = resolve_workflow_family(catalog, workflow_family_id)
    family_roles = family.get("roles", {})
    if not isinstance(family_roles, dict):
        return config.always_on_roles
    family_roles = _as_object_mapping(
        cast(object, family_roles),
        f"workflow_families[{workflow_family_id}].roles",
    )
    role_ids = _as_string_tuple(
        family_roles.get("always_on"),
        f"workflow_families[{workflow_family_id}].roles.always_on",
    )
    if not role_ids:
        return config.always_on_roles
    return tuple(resolve_role(config, role_id) for role_id in role_ids)


def load_codex_agent_configs() -> dict[str, dict[str, object]]:
    """Load Codex custom agent TOML files by declared agent name."""
    configs: dict[str, dict[str, object]] = {}
    for path in sorted(CODEX_AGENT_ROOT.glob("*.toml")):
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        name = parsed.get("name", path.stem)
        configs[str(name)] = parsed
    return configs


def codex_agent_model_matrix_for_roles(
    roles: tuple[Role, ...],
    configs: dict[str, dict[str, object]] | None = None,
) -> tuple[str, ...]:
    """Return role:agent:model:effort rows for active Codex agents."""
    agent_configs = configs if configs is not None else load_codex_agent_configs()
    rows: list[str] = []
    for role in roles:
        for agent_id in role.codex_agents:
            agent_config = agent_configs.get(agent_id, {})
            model = str(agent_config.get("model", "inherit"))
            effort = str(agent_config.get("model_reasoning_effort", "inherit"))
            rows.append(f"{role.id}:{agent_id}:{model}:{effort}")
    return tuple(dict.fromkeys(rows))


def iter_artifacts(config: TeamConfig, roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return unique artifact filenames in deterministic order."""
    return tuple(
        dict.fromkeys(
            (
                *(output for role in roles for output in role.required_outputs),
                config.artifacts["team_manifest"],
                config.artifacts["verification"],
            )
        )
    )


def resolve_role_document_packet(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
    workspace_root: Path,
) -> RoleDocumentPacket:
    """Resolve explicit read-before-work packet for one role."""
    spec = ROLE_DOCUMENT_PACKET_SPECS.get(role.id, {})
    artifact_keys = _as_string_tuple(
        spec.get("artifact_keys"),
        f"document_packet[{role.id}].artifact_keys",
    )
    workspace_paths = _as_string_tuple(
        spec.get("workspace_paths"),
        f"document_packet[{role.id}].workspace_paths",
    )
    entries: list[DocumentPacketEntry] = []
    seen_paths: set[Path] = set()

    def add_entry(entry: DocumentPacketEntry) -> None:
        resolved_path = entry.path.resolve()
        if resolved_path in seen_paths:
            return
        seen_paths.add(resolved_path)
        entries.append(
            DocumentPacketEntry(
                path=resolved_path,
                rationale=entry.rationale,
            )
        )

    for artifact_key in artifact_keys:
        if artifact_key not in config.artifacts:
            raise RuntimeError(
                f"document packet artifact key missing for role {role.id}: {artifact_key}"
            )
        add_entry(
            DocumentPacketEntry(
                path=(report_dir / config.artifacts[artifact_key]).resolve(),
                rationale=f"run artifact:{artifact_key}",
            )
        )
    for relative_path in workspace_paths:
        add_entry(
            DocumentPacketEntry(
                path=resolve_workspace_document_path(workspace_root, relative_path),
                rationale=f"workspace doc:{relative_path}",
            )
        )
    for entry in resolve_cross_cutting_document_packet(workspace_root):
        add_entry(entry)
    return RoleDocumentPacket(
        role_id=role.id,
        read_before_work=tuple(entries),
        must_cite_before_edit=bool(spec.get("must_cite_before_edit", False)),
        notes=str(spec.get("notes", "")),
    )


def strip_dependency_manifest(text: str) -> str:
    """Remove a dependency manifest block from text included inside another template."""
    trimmed = text.lstrip()
    leading = text[: len(text) - len(trimmed)]
    if not trimmed.startswith("<!--") or "@dependency-start" not in trimmed:
        return text
    end = trimmed.find(DEPENDENCY_MANIFEST_CLOSE_MARKER)
    if end == -1:
        return text
    return leading + trimmed[end + len(DEPENDENCY_MANIFEST_CLOSE_MARKER) :].lstrip(
        NEWLINE
    )


def render_template_partial(partial_name: str, seen: tuple[str, ...] = ()) -> str:
    """Load one reusable template partial without leaking its manifest into output."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", partial_name):
        raise RuntimeError(f"invalid template partial name: {partial_name}")
    if partial_name in seen:
        chain = " -> ".join((*seen, partial_name))
        raise RuntimeError(f"recursive template partial include: {chain}")
    path = TEMPLATE_PARTIAL_ROOT / f"{partial_name}.md"
    if not path.is_file():
        raise RuntimeError(f"template partial not found: {partial_name}")
    content = strip_dependency_manifest(path.read_text(encoding="utf-8"))
    return expand_template_partials(content, (*seen, partial_name))


def expand_template_partials(content: str, seen: tuple[str, ...] = ()) -> str:
    """Expand reusable partial markers in one template body."""
    return TEMPLATE_PARTIAL_RE.sub(
        lambda match: render_template_partial(match.group(1), seen),
        content,
    )


def apply_template_replacements(content: str, replacements: dict[str, str]) -> str:
    """Apply run-specific replacements to one rendered template."""
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
        content = content.replace(f"{{\\{{{key}}}}}", value)
    return content


def render_template(template_name: str, replacements: dict[str, str]) -> str:
    """Load and fill a text template from agents/templates."""
    content = (TEMPLATE_ROOT / template_name).read_text(encoding="utf-8")
    content = expand_template_partials(content)
    content = apply_template_replacements(content, replacements)
    return content


def has_template(artifact_name: str) -> bool:
    """Return whether a template exists for one artifact filename."""
    return (TEMPLATE_ROOT / artifact_name).is_file()


def required_output_templates_missing(
    config: TeamConfig,
    roles: tuple[Role, ...],
    allowed_missing: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return required output templates that are missing from agents/templates."""
    return tuple(
        dict.fromkeys(
            output
            for role in roles
            for output in role.required_outputs
            if output not in allowed_missing and not has_template(output)
        )
    )


def create_run_bundle(spec: RunBundleSpec) -> tuple[str, ...]:
    """Create the standard files for a run."""
    replacements = {
        "RUN_ID": spec.run_id,
        "TASK": spec.task,
        "OWNER": spec.owner,
        "CREATED_AT": spec.created_at_iso,
    }
    spec.report_dir.mkdir(parents=True, exist_ok=True)
    created_files = list(iter_artifacts(spec.config, spec.roles))
    for artifact in created_files:
        if has_template(artifact):
            (spec.report_dir / artifact).write_text(
                render_template(artifact, replacements),
                encoding="utf-8",
            )
    (spec.report_dir / spec.config.artifacts["team_manifest"]).write_text(
        build_manifest(spec),
        encoding="utf-8",
    )
    (spec.report_dir / spec.config.artifacts["verification"]).write_text(
        "\n".join(
            [
                f"run_id={spec.run_id}",
                f"task={spec.task}",
                f"owner={spec.owner}",
                f"created_at_utc={spec.created_at_iso}",
                "status=pending",
                "user_completion_report=locked",
                "closeout_gate_status=pending",
                "",
            ]
        ),
        encoding="utf-8",
    )
    authority_roles = {
        role.id: role.write_policy.mode not in {"read_only", "artifacts_only"}
        for role in spec.roles
    }
    (spec.report_dir / AUTHORITY_FILE_NAME).write_text(
        build_default_task_authority(
            run_id=spec.run_id,
            task=spec.task,
            roles=authority_roles,
        ),
        encoding="utf-8",
    )
    created_files.append(AUTHORITY_FILE_NAME)
    write_initial_wave_execution_gate(spec)
    unique_created_files: list[str] = []
    for artifact in created_files:
        if artifact not in unique_created_files:
            unique_created_files.append(artifact)
    return tuple(unique_created_files)


def write_initial_wave_execution_gate(spec: RunBundleSpec) -> None:
    """Record the parent runtime gate for the first recommended subagent wave."""
    if not spec.workflow_family_id:
        return
    active_subagents, _max_write_subagents = workflow_spawn_budget(
        load_task_catalog(spec.config),
        spec.workflow_family_id,
    )
    initial_wave = recommended_initial_subagent_wave(spec.roles, active_subagents)
    if not initial_wave:
        return
    row = initial_wave_gate_fields(
        initial_wave=initial_wave,
        active_subagents=active_subagents,
    )
    append_markdown_section_line(
        spec.report_dir / "schedule.md",
        "## Agent Wave Ledger",
        schedule_wave_row(row),
    )
    append_markdown_section_line(
        spec.report_dir / "workflow_monitoring.md",
        "## Actual Wave Events",
        workflow_wave_event_line(row),
    )


def initial_wave_gate_fields(
    *,
    initial_wave: tuple[str, ...],
    active_subagents: int,
) -> dict[str, str]:
    """Return one schedule/monitor row for a parent-executed WAVE-1 gate."""
    skipped_roles = ",".join(initial_wave) + ":pending_explicit_runtime_spawn_authority"
    active_budget = f"{active_subagents}/{active_subagents}"
    return {
        "wave_id": "WAVE-1",
        "parent_or_delegate": "parent",
        "spawn_authority": "parent_runtime_authority_required",
        "trigger": "bootstrap_initial_intake_wave",
        "budget_before": active_budget,
        "budget_after": active_budget,
        "runtime_max_threads": str(codex_runtime_max_threads()),
        "runtime_max_depth": str(codex_runtime_max_depth()),
        "spawned_roles": "none",
        "role_instances": "none",
        "skipped_roles": skipped_roles,
        "allowed_paths": "team_manifest.yaml,schedule.md,workflow_monitoring.md,user_request_contract.md",
        "do_not_read": "broad_raw_logs,unrelated_reports",
        "write_scope": "read_only_intake_until_parent_updates_wave_row",
        "validation_route": "parent_spawn_or_skip_update_required",
        "review_gate": "parent_execution_gate",
        "handoff_artifacts": (
            "team_manifest.yaml#run.spawn_wave_recommendation,"
            "team_manifest.yaml#run.standard_wave_sequence"
        ),
        "delegated_policy_ref": "team_manifest.yaml#run.delegated_spawn_policy",
        "status": "blocked_authority_required",
    }


def schedule_wave_row(row: dict[str, str]) -> str:
    """Return a schedule.md Agent Wave Ledger row."""
    cells = (
        row["wave_id"],
        row["parent_or_delegate"],
        row["spawn_authority"],
        row["trigger"],
        row["budget_before"],
        row["budget_after"],
        row["runtime_max_threads"],
        row["runtime_max_depth"],
        row["spawned_roles"],
        row["role_instances"],
        row["skipped_roles"],
        row["allowed_paths"],
        row["do_not_read"],
        row["write_scope"],
        row["validation_route"],
        row["review_gate"],
        row["handoff_artifacts"],
        row["delegated_policy_ref"],
        row["status"],
    )
    return "| " + " | ".join(cells) + " |"


def workflow_wave_event_line(row: dict[str, str]) -> str:
    """Return a workflow_monitoring.md Actual Wave Events token row."""
    fields = (
        ("wave_event", "recorded"),
        ("wave_id", row["wave_id"]),
        ("event_kind", "authority_blocker"),
        ("spawn_authority", row["spawn_authority"]),
        ("trigger", row["trigger"]),
        ("budget_before", row["budget_before"]),
        ("budget_after", row["budget_after"]),
        ("runtime_max_threads", row["runtime_max_threads"]),
        ("runtime_max_depth", row["runtime_max_depth"]),
        ("spawned_roles", row["spawned_roles"]),
        ("role_instances", row["role_instances"]),
        ("skipped_roles", row["skipped_roles"]),
        ("allowed_paths", row["allowed_paths"]),
        ("do_not_read", row["do_not_read"]),
        ("write_scope", row["write_scope"]),
        ("validation_route", row["validation_route"]),
        ("review_gate", row["review_gate"]),
        ("handoff_artifacts", row["handoff_artifacts"]),
        ("status", row["status"]),
    )
    return "- " + " ".join(f"{key}={value}" for key, value in fields)


def append_markdown_section_line(path: Path, heading: str, line: str) -> None:
    """Append one line to a level-2 Markdown section if it is not already present."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if line in text:
        return
    lines = text.splitlines()
    in_section = False
    insert_at = len(lines)
    for index, existing_line in enumerate(lines):
        stripped = existing_line.strip()
        if not stripped.startswith("## "):
            continue
        if in_section:
            insert_at = index
            break
        in_section = stripped == heading
    if not in_section:
        lines.extend(("", heading, "", line))
    else:
        while insert_at > 0 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_manifest(spec: RunBundleSpec) -> str:
    """Build the team manifest yaml."""
    workflow_family = None
    if spec.workflow_family_id:
        workflow_family = resolve_workflow_family(
            load_task_catalog(spec.config),
            spec.workflow_family_id,
        )
    lines = manifest_run_lines(spec, workflow_family)
    lines.extend(manifest_role_lines(spec, workflow_family))
    lines.extend(manifest_context_policy_lines(spec.config))
    lines.extend(manifest_quality_gate_lines(spec.config))
    lines.extend(manifest_artifact_lines(spec.config, spec.roles))
    return "\n".join(lines) + "\n"


def manifest_run_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
) -> list[str]:
    """Render run-level manifest fields."""
    lines = [
        "run:",
        f"  id: {spec.run_id}",
        f"  task: {spec.task!r}",
        f"  owner: {spec.owner!r}",
        f"  created_at_utc: {spec.created_at_iso}",
        f"  report_dir: {str(spec.report_dir)!r}",
        f"  workspace_root: {str(spec.workspace_root)!r}",
        f"  team_config: {str(TEAM_CONFIG_PATH)!r}",
        f"  team_runtime: {str(ROOT / 'tools' / 'agent_tools' / 'agent_team.py')!r}",
        f"  task_catalog: {str(ROOT / str(spec.config.team['task_catalog']))!r}",
        "  subagent_lifecycle_policy:",
        "    fresh_subagents_required: true",
        "    reuse_for_new_task: forbidden",
        "    previous_task_subagent_reuse: forbidden",
        "    mid_task_user_input_policy: parent_checkpoint_then_route_delta",
        "    same_task_delta_reuse: allowed_with_updated_packet",
        "    scope_change_reuse: forbidden_spawn_fresh_wave",
        "    new_task_reuse: forbidden_spawn_fresh_run",
        "    close_before_user_completion: true",
        "    closeout_gate_key: subagents_closed",
        "    closeout_evidence_section: 'Subagent Lifecycle Evidence'",
        "    handoff_rule: 'Do not send_input to agents from another user request; spawn a "
        "fresh run-local agent for each new task. Same-task user deltas require a parent "
        "checkpoint, updated packet path, wave-ledger entry, and unchanged role scope before "
        "send_input; scope changes spawn a fresh wave.'",
        "  handoff_context_policy:",
        "    inactive_profile_docs: not_applicable",
        "    broad_cross_cutting_packet: available_not_default_read",
        "  implementation_gate_defaults:",
        "    implementation_surface_route_status: pending",
        "    implementation_surface_route_command: 'tools/bin/agent-canon local-llm route-implementation-surface --request-file <request-or-design-question.txt> --format text'",
        "    tool_reuse_ledger_status: required_before_custom_implementation",
        "    pre_edit_rejection_prediction_status: pending",
        "    pre_edit_rejection_command: 'python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>'",
        "  standard_wave_sequence:",
        f"    source: {STANDARD_AGENT_WAVE_SEQUENCE_SOURCE!r}",
        "    stages:",
        *(f"      - {stage}" for stage in STANDARD_AGENT_WAVE_SEQUENCE),
        f"    gate_order: {STANDARD_AGENT_WAVE_SEQUENCE_GATE!r}",
        "    edit_handoff_rule: 'write-capable handoff は review gate 後の bounded write scope から開始し、read-only wave は read scope と次の review gate を記録する'",
        *manifest_user_facing_language_policy_lines(),
        *manifest_contract_complete_implementation_policy_lines(spec.task),
        *manifest_pre_handoff_scope_policy_lines(),
        *manifest_pre_handoff_gate_status_lines(),
        *manifest_repo_tool_routing_policy_lines(spec),
        *manifest_default_quality_check_policy_lines(spec),
        "  agent_report_collection:",
        "    status_command: 'python3 tools/agent_tools/runtime_log_archive_git.py status'",
        f"    archive_current_run_command: 'python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir {spec.report_dir}'",
        "    sync_command: 'python3 tools/agent_tools/runtime_log_archive_git.py sync'",
        "    archive_index: '.agent-canon/log-archive/agent-reports/<repo-key>/index.jsonl'",
    ]
    insert_index = (
        lines.index("    broad_cross_cutting_packet: available_not_default_read") + 1
    )
    lines.insert(insert_index, "    common_prompt_must_include:")
    insert_index += 1
    for field in COMMON_PROMPT_MUST_INCLUDE:
        lines.insert(insert_index, f"      - {field}")
        insert_index += 1
    communication_protocol = spec.config.team.get("communication_protocol")
    if communication_protocol is not None:
        lines.append(
            f"  communication_protocol: {str(ROOT / str(communication_protocol))!r}"
        )
    if workflow_family is not None:
        active_subagents, max_write_subagents = workflow_spawn_budget(
            load_task_catalog(spec.config),
            spec.workflow_family_id,
        )
        lines.append("  spawn_budget:")
        lines.append(
            "    source: 'agents/task_catalog.yaml workflow_families[].spawn_budget'"
        )
        lines.append(f"    active_subagents: {active_subagents}")
        lines.append(f"    max_write_subagents: {max_write_subagents}")
        lines.append(f"    runtime_max_threads: {codex_runtime_max_threads()}")
        lines.append(f"    runtime_max_depth: {codex_runtime_max_depth()}")
        lines.append("    initial_three_agent_intake_is_total_cap: false")
        lines.append("    max_write_subagents_scope: 'write-capable subagents only'")
        initial_wave = recommended_initial_subagent_wave(spec.roles, active_subagents)
        expansion_wave_slots = recommended_dynamic_expansion_wave_slots(
            spec.roles,
            active_subagents,
            initial_wave,
        )
        lines.append("  spawn_wave_recommendation:")
        lines.append(
            "    source: 'stage-ready AgentCanon wave policy filtered by workflow spawn budget'"
        )
        lines.append("    standard_sequence_ref: run.standard_wave_sequence")
        lines.append("    initial_wave_id: WAVE-1")
        lines.append("    initial_wave_agent_types:")
        for agent_type in initial_wave:
            lines.append(f"      - {agent_type}")
        lines.append("    dynamic_expansion_waves:")
        if expansion_wave_slots:
            for index, wave in enumerate(expansion_wave_slots, start=2):
                lines.append(f"      - wave_id: WAVE-{index}")
                lines.append(
                    "        standard_sequence_ref: run.standard_wave_sequence"
                )
                lines.append("        agent_types:")
                for slot in wave:
                    lines.append(f"          - {slot.agent_type}")
                lines.append("        role_instances:")
                for slot in wave:
                    lines.append(
                        "          - "
                        f"{slot.role_id}:{slot.instance_id}:team_manifest.yaml#roles.{slot.role_id}"
                    )
        else:
            lines.append("      - wave_id: none")
            lines.append("        standard_sequence_ref: run.standard_wave_sequence")
            lines.append("        agent_types: []")
            lines.append("        role_instances: []")
        lines.extend(render_role_topology(workflow_family, indent="    "))
        lines.append("  delegated_spawn_policy:")
        lines.append("    dynamic_mid_task_spawn: allowed")
        lines.append("    delegated_child_spawn: allowed_with_bounded_packet")
        lines.append("    owner: parent_or_delegated_stage_owner")
        lines.append(
            "    child_role_budget_inheritance: active_budget_remaining_after_parent_wave"
        )
        lines.append("    active_budget_source: 'run.spawn_budget.active_subagents'")
        lines.append(
            "    runtime_thread_ceiling_source: 'run.spawn_budget.runtime_max_threads'"
        )
        lines.append(
            "    runtime_depth_ceiling_source: 'run.spawn_budget.runtime_max_depth'"
        )
        lines.append(
            f"    wave_record_command: {subagent_wave_record_command(spec.report_dir)!r}"
        )
        lines.append("    expansion_triggers:")
        lines.append("      - new_independent_stage")
        lines.append("      - review_finding_opens_independent_scope")
        lines.append(f"      - {VALIDATION_FAILURE_TRIAGE_TRIGGER}")
        lines.append("      - disjoint_write_scope_available")
        lines.append("      - blocked_role_replacement")
        lines.append("    validation_failure_triage_policy:")
        lines.append(f"      trigger: {VALIDATION_FAILURE_TRIAGE_TRIGGER}")
        lines.append("      triage_write_scope: read_only_until_cause_identified")
        lines.append("      repair_required_fields:")
        for field in VALIDATION_FAILURE_REPAIR_REQUIRED_FIELDS:
            lines.append(f"        - {field}")
        lines.append("      intent_preservation_values:")
        for value in VALIDATION_FAILURE_INTENT_PRESERVATION_VALUES:
            lines.append(f"        - {value}")
        lines.append("    same_role_instances:")
        lines.append(f"      status: {SAME_ROLE_SUBAGENT_INSTANCE_POLICY['status']}")
        lines.append(
            f"      identity_key: {SAME_ROLE_SUBAGENT_INSTANCE_POLICY['identity_key']!r}"
        )
        lines.append(
            "      parallel_read_only: "
            f"{SAME_ROLE_SUBAGENT_INSTANCE_POLICY['parallel_read_only']}"
        )
        lines.append(
            "      parallel_write: "
            f"{SAME_ROLE_SUBAGENT_INSTANCE_POLICY['parallel_write']}"
        )
        lines.append(
            "      collision_policy: "
            f"{SAME_ROLE_SUBAGENT_INSTANCE_POLICY['collision_policy']}"
        )
        lines.append("      required_fields:")
        for field in SAME_ROLE_SUBAGENT_REQUIRED_FIELDS:
            lines.append(f"        - {field}")
        lines.append("    handoff_required_fields:")
        lines.append("      - owner")
        lines.append("      - child_role")
        lines.append("      - child_instance_id")
        lines.append("      - input_packet")
        lines.append("      - tool_route")
        lines.append("      - tool_commands")
        lines.append("      - tool_evidence")
        lines.append("      - allowed_paths")
        lines.append("      - do_not_read")
        lines.append("      - expected_output")
        lines.append("      - write_scope")
        lines.append("      - validation_route")
        lines.append("      - review_gate")
        lines.append("      - plan_artifact")
        lines.append("      - edit_handoff")
        lines.append("      - pre_handoff_gate_status")
        lines.append("      - remaining_spawn_budget")
        lines.append("    required_before_spawn:")
        lines.append(
            "      - plan artifact, review gate decision, and edit handoff evidence "
            "following run.standard_wave_sequence"
        )
        lines.append(
            "      - include run.default_quality_check_policy in review and edit "
            "handoff packets"
        )
        lines.append(
            "      - include run.pre_handoff_scope_policy and dependency-expanded "
            "handoff scope evidence"
        )
        lines.append(
            "      - include run.pre_handoff_gate_status before implementation or "
            "write-capable handoff when design_brief.md exists"
        )
        lines.append(
            "      - include run.repo_tool_routing_policy selected-skill command sequence, "
            "dynamic skill candidates, and tool evidence in every handoff packet"
        )
        lines.append(
            "      - validation_failure_requires_parallel_triage waves stay read-only "
            "until failing_contract, observation_level, cause_classification, "
            "intent_preservation, and evidence are recorded for same-intent repair "
            "or escalation"
        )
        lines.append(
            "      - run delegated_spawn_policy.wave_record_command after any "
            "actual parent or delegated child spawn; delegated child waves must "
            "include remaining_spawn_budget"
        )
        lines.append(
            "      - schedule.md Agent Wave Ledger row with spawn_authority, "
            "budget, runtime ceilings, paths, validation_route, review_gate, "
            "handoff_artifacts, and delegated policy ref"
        )
        lines.append(
            "      - workflow_monitoring.md intervention or behavior-event for spawned/skipped roles"
        )
        lines.append(
            "      - bounded handoff packet with allowed_paths, do_not_read, expected_output, and write_policy"
        )
        lines.append("    closeout_required_evidence:")
        lines.append(
            "      - closeout_gate.md Subagent Lifecycle Evidence planned-vs-actual wave status"
        )
        lines.append(
            "      - closed run-local agent ids or parent_direct_no_subagents with "
            "PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes and "
            "PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>"
        )
        lines.append("  write_scope_policy:")
        lines.append("    parent_managed: true")
        lines.append("    scope_source_ref: run.pre_handoff_scope_policy")
        lines.append("    handoff_scope_status: seed_then_expand_before_handoff")
        lines.append("    disjoint_write_scopes_required: true")
        lines.append("    overlapping_write_scopes: serialize_current_checkout_waves")
        lines.append(f"    max_write_subagents: {max_write_subagents}")
        lines.append("  workflow_family:")
        lines.append(f"    id: {spec.workflow_family_id}")
        lines.append(f"    name: {str(workflow_family['name'])!r}")
        lines.extend(render_subagent_prompt_packet(workflow_family, indent="  "))
    lines.append("  cross_cutting_document_packet:")
    cross_cutting_packet = resolve_cross_cutting_document_packet(spec.workspace_root)
    for entry in cross_cutting_packet:
        lines.append(f"    - path: {str(entry.path)!r}")
        lines.append(f"      rationale: {entry.rationale!r}")
    return lines


def manifest_contract_complete_implementation_policy_lines(
    task_text: str = "",
) -> list[str]:
    """Render contract-complete implementation policy lines."""
    lines = [
        "  contract_complete_implementation_policy:",
        "    enabled: true",
        f"    source: {CONTRACT_COMPLETE_IMPLEMENTATION_POLICY_SOURCE!r}",
        f"    scope_basis: {CONTRACT_COMPLETE_IMPLEMENTATION_SCOPE_BASIS!r}",
        f"    escalation: {CONTRACT_COMPLETE_IMPLEMENTATION_ESCALATION!r}",
        f"    rule: {CONTRACT_COMPLETE_IMPLEMENTATION_RULE!r}",
        "    required_inputs:",
    ]
    if implementation_handoff_required(task_text):
        lines[
            CONTRACT_COMPLETE_IMPLEMENTATION_HANDOFF_INSERT_INDEX:
            CONTRACT_COMPLETE_IMPLEMENTATION_HANDOFF_INSERT_INDEX
        ] = [
            f"    implementation_handoff_required: {IMPLEMENTATION_HANDOFF_REQUIRED!r}",
            f"    parent_repo_edits_allowed: {PARENT_REPO_EDITS_ALLOWED!r}",
            "    parent_direct_write_exception_required: "
            f"{PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED!r}",
            f"    parent_direct_write_exception: {PARENT_DIRECT_WRITE_EXCEPTION!r}",
        ]
    for field in CONTRACT_COMPLETE_IMPLEMENTATION_REQUIRED_INPUTS:
        lines.append(f"      - {field}")
    lines.append("    route_signals:")
    for field in CONTRACT_COMPLETE_IMPLEMENTATION_ROUTE_SIGNALS:
        lines.append(f"      - {field}")
    return lines


def manifest_user_facing_language_policy_lines() -> list[str]:
    """Render user-facing language policy lines."""
    lines = [
        "  user_facing_language_policy:",
        "    enabled: true",
        f"    language: {USER_FACING_LANGUAGE!r}",
        f"    source: {USER_FACING_LANGUAGE_POLICY_SOURCE!r}",
        f"    machine_fields: {USER_FACING_MACHINE_FIELDS!r}",
        f"    rule: {USER_FACING_LANGUAGE_RULE!r}",
        "    scope:",
    ]
    for field in USER_FACING_LANGUAGE_SCOPE:
        lines.append(f"      - {field}")
    return lines


def manifest_pre_handoff_scope_policy_lines() -> list[str]:
    """Render scope discovery policy lines."""
    lines = [
        "  pre_handoff_scope_policy:",
        "    enabled: true",
        f"    source: {PRE_HANDOFF_SCOPE_POLICY_SOURCE!r}",
        f"    status: {PRE_HANDOFF_SCOPE_STATUS!r}",
        "    sequence:",
    ]
    for stage in PRE_HANDOFF_SCOPE_SEQUENCE:
        lines.append(f"      - {stage}")
    lines.extend(
        [
            f"    handoff_rule: {PRE_HANDOFF_SCOPE_HANDOFF_RULE!r}",
            "    source_packet_seed: implementation_surface_route",
            "    expansion_artifacts:",
            "      - responsibility_search",
            "      - reuse_survey",
            "      - stale_surface_scan",
            "      - dependency_edit_scope",
            "      - dependency_graph",
            "    handoff_fields:",
            "      - allowed_paths",
            "      - do_not_read",
            "      - write_scope",
            "      - validation_route",
            "      - review_gate",
        ]
    )
    return lines


def manifest_pre_handoff_gate_status_lines() -> list[str]:
    """Render the pre-handoff gate status contract."""
    lines = [
        "  pre_handoff_gate_status:",
        "    enabled: true",
        f"    source: {PRE_HANDOFF_GATE_STATUS_SOURCE!r}",
        f"    status: {PRE_HANDOFF_GATE_STATUS_DEFAULT!r}",
        "    required_evidence:",
    ]
    for field in PRE_HANDOFF_GATE_STATUS_REQUIRED_EVIDENCE:
        lines.append(f"      - {field}")
    lines.extend(
        [
            "    design_gate_command: 'python3 tools/agent_tools/waterfall_gate_check.py --report-dir <report-dir> --gate design'",
            "    applies_when: design_brief.md_exists_before_implementation_or_handoff",
            "    document_flow_review: conditional_when_workflow_gate_active",
        ]
    )
    return lines


def manifest_repo_tool_routing_policy_lines(spec: RunBundleSpec) -> list[str]:
    """Render selected-skill repo tool routing policy lines."""
    selected_skills = spec.selected_skills or suggested_public_skills(
        None,
        spec.workflow_family_id or None,
    )
    skill_names = selected_skill_names(selected_skills)
    dynamic_candidates = dynamic_skill_candidate_names(selected_skills)
    lines = [
        "  repo_tool_routing_policy:",
        "    enabled: true",
        f"    source: {REPO_TOOL_ROUTING_POLICY_SOURCE!r}",
        f"    owner: {REPO_TOOL_ROUTING_OWNER!r}",
        f"    route_basis: {REPO_TOOL_ROUTING_ROUTE_BASIS!r}",
        f"    execution_mode: {REPO_TOOL_ROUTING_EXECUTION_MODE!r}",
        f"    check_command: {REPO_TOOL_ROUTING_CHECK_COMMAND!r}",
        "    sequence:",
    ]
    for stage in REPO_TOOL_ROUTING_SEQUENCE:
        lines.append(f"      - {stage}")
    lines.append("    stage_fields:")
    for field in REPO_TOOL_ROUTING_STAGE_FIELDS:
        lines.append(f"      - {field}")
    lines.append("    selected_skills:")
    for skill in skill_names:
        lines.append(f"      - ${skill}")
    lines.append("    dynamic_skill_routing:")
    lines.append(f"      status: {REPO_DYNAMIC_SKILL_ROUTING_STATUS!r}")
    lines.append(f"      prompt_route_command: {REPO_DYNAMIC_SKILL_ROUTING_COMMAND!r}")
    lines.append(f"      area_route_command: {REPO_DYNAMIC_SKILL_AREA_COMMAND!r}")
    lines.append(f"      next: {REPO_DYNAMIC_SKILL_ROUTING_NEXT!r}")
    lines.append("      candidates:")
    if dynamic_candidates:
        for candidate in dynamic_candidates:
            lines.append(f"        - ${candidate}")
    else:
        lines.append("        - none")
    lines.append("    sequential_tool_routes:")
    for packet in selected_skill_command_packets(selected_skills):
        lines.extend(manifest_one_skill_tool_route_lines(packet))
    return lines


def manifest_one_skill_tool_route_lines(packet: SkillCommandPacket) -> list[str]:
    """Render one selected skill's sequential tool route."""
    lines = [
        f"      - skill: {packet.skill}",
        f"        runtime_skill: {packet.runtime_skill!r}",
        f"        canonical_doc: {packet.canonical_doc!r}",
        f"        packet_command: {skill_tool_packet_command(packet.skill)!r}",
        "        related_skills:",
    ]
    if packet.related_skills:
        for skill in packet.related_skills:
            lines.append(f"          - ${skill}")
    else:
        lines.append("          - none")
    lines.append("        commands:")
    lines.append("          show_skill_packet:")
    lines.append(f"            - {skill_tool_packet_command(packet.skill)!r}")
    lines.append("          required_commands:")
    for command in packet.required_commands:
        lines.append(f"            - {command!r}")
    lines.append("          task_matching_conditional_commands:")
    for command in conditional_commands_for_packet(packet):
        lines.append(f"            - {command!r}")
    lines.append("          validation_commands:")
    for command in packet.validation_commands:
        lines.append(f"            - {command!r}")
    return lines


def manifest_default_quality_check_policy_lines(spec: RunBundleSpec) -> list[str]:
    """Render default quality-check routing policy lines."""
    role_ids = default_quality_check_role_ids(spec.roles)
    agent_types = default_quality_check_agent_types(spec.roles)
    review_pack_state = (
        "active" if spec.default_review_packs_enabled else "route_without_default_packs"
    )
    lines = [
        "  default_quality_check_policy:",
        "    enabled: true",
        f"    source: {DEFAULT_QUALITY_CHECK_POLICY_SOURCE!r}",
        "    wave_sequence_ref: run.standard_wave_sequence",
        "    role_topology_ref: 'agents/task_catalog.yaml#role_topology_defaults.role_families.review'",
        "    stages:",
    ]
    for stage in DEFAULT_QUALITY_CHECK_STAGES:
        lines.append(f"      - {stage}")
    if role_ids:
        lines.append("    roles:")
        for role_id in role_ids:
            lines.append(f"      - {role_id}")
    else:
        lines.append("    roles: []")
    if agent_types:
        lines.append("    codex_agent_types:")
        for agent_type in agent_types:
            lines.append(f"      - {agent_type}")
    else:
        lines.append("    codex_agent_types: []")
    lines.append("    provenance:")
    if spec.task_default_specialists:
        lines.append("      task_default_specialists:")
        for role_id in spec.task_default_specialists:
            lines.append(f"        - {role_id}")
    else:
        lines.append("      task_default_specialists: []")
    if spec.auto_specialists:
        lines.append("      auto_language_reviewers:")
        for role_id in spec.auto_specialists:
            lines.append(f"        - {role_id}")
    else:
        lines.append("      auto_language_reviewers: []")
    if spec.manual_specialists:
        lines.append("      manual_specialists:")
        for role_id in spec.manual_specialists:
            lines.append(f"        - {role_id}")
    else:
        lines.append("      manual_specialists: []")
    lines.append(f"      default_review_packs: {review_pack_state}")
    if spec.default_review_pack_ids:
        lines.append("      default_review_pack_ids:")
        for pack_id in spec.default_review_pack_ids:
            lines.append(f"        - {pack_id}")
    else:
        lines.append("      default_review_pack_ids: []")
    lines.append("    static_check_commands:")
    for command in DEFAULT_QUALITY_CHECK_STATIC_COMMANDS:
        lines.append(f"      - {command!r}")
    return lines


def manifest_role_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
) -> list[str]:
    """Render role entries for the team manifest."""
    lines = ["roles:"]
    for role in spec.roles:
        lines.extend(manifest_one_role_lines(spec, workflow_family, role))
    return lines


def manifest_one_role_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
    role: Role,
) -> list[str]:
    """Render one role entry for the team manifest."""
    lines = [
        f"  - id: {role.id}",
        f"    activation: {role.activation}",
        "    status: pending",
    ]
    if role.codex_agents:
        lines.append("    codex_agents:")
        for codex_agent in role.codex_agents:
            lines.append(f"      - {codex_agent}")
    lines.extend(manifest_prompt_contract_lines(role, workflow_family))
    lines.append("    owns:")
    for responsibility in role.owns:
        lines.append(f"      - {responsibility}")
    lines.append("    required_outputs:")
    for output in role.required_outputs:
        lines.append(f"      - {output}")
    lines.extend(manifest_write_policy_lines(spec, role))
    lines.extend(manifest_document_packet_lines(spec, role))
    return lines


def manifest_prompt_contract_lines(
    role: Role,
    workflow_family: dict[str, object] | None,
) -> list[str]:
    """Render prompt contract lines for one role."""
    lines = ["    prompt_contract:"]
    lines.append(
        "      assignment_prompt: "
        f"{compact_role_prompt_contract(role, workflow_family)!r}"
    )
    lines.append(
        "      assignment_prompt_source: "
        "'tools/agent_tools/agent_team.py#role_prompt_contract'"
    )
    lines.append(
        "      common_prompt_must_include_ref: run.handoff_context_policy.common_prompt_must_include"
    )
    lines.append("      role_prompt_must_include:")
    for item in role_prompt_must_include(role):
        lines.append(f"        - {item!r}")
    return lines


def manifest_write_policy_lines(spec: RunBundleSpec, role: Role) -> list[str]:
    """Render resolved write policy lines for one role."""
    scope = resolve_role_write_scope(
        config=spec.config,
        role=role,
        report_dir=spec.report_dir,
        workspace_root=spec.workspace_root,
    )
    lines = ["    write_policy:"]
    lines.append(f"      mode: {scope.mode}")
    lines.append(
        f"      requires_worktree_scope: {str(scope.requires_worktree_scope).lower()}"
    )
    if scope.notes:
        lines.append(f"      notes: {scope.notes!r}")
    if scope.worktree_scope_file is not None:
        lines.append(f"      worktree_scope_file: {str(scope.worktree_scope_file)!r}")
    if scope.unresolved_reason is not None:
        lines.append(f"      unresolved_reason: {scope.unresolved_reason!r}")
    lines.append("      allowed_files:")
    for path in scope.allowed_files:
        lines.append(f"        - {str(path)!r}")
    lines.append("      allowed_directories:")
    for path in scope.allowed_directories:
        lines.append(f"        - {str(path)!r}")
    return lines


def manifest_document_packet_lines(spec: RunBundleSpec, role: Role) -> list[str]:
    """Render explicit document packet lines for one role."""
    document_packet = resolve_role_document_packet(
        spec.config,
        role,
        spec.report_dir,
        spec.workspace_root,
    )
    lines = ["    document_packet:"]
    lines.append(
        f"      must_cite_before_edit: {str(document_packet.must_cite_before_edit).lower()}"
    )
    if document_packet.notes:
        lines.append(f"      notes: {document_packet.notes!r}")
    lines.append("      common_packet_ref: run.cross_cutting_document_packet")
    lines.append(
        "      common_packet_read_rule: active_when_route_or_review_gate_requires_it"
    )
    lines.append("      role_specific_read_before_work:")
    for entry in role_specific_document_entries(document_packet):
        lines.append(f"        - path: {str(entry.path)!r}")
        lines.append(f"          rationale: {entry.rationale!r}")
    return lines


def role_specific_document_entries(
    document_packet: RoleDocumentPacket,
) -> tuple[DocumentPacketEntry, ...]:
    """Return per-role document entries without repeating common packet paths."""
    return tuple(
        entry
        for entry in document_packet.read_before_work
        if not entry.rationale.startswith("cross_cutting_doc:")
    )


def manifest_context_policy_lines(config: TeamConfig) -> list[str]:
    """Render context-sharing policy lines."""
    lines = ["context_policies:"]
    for policy in config.context_policies:
        lines.append("  - roles:")
        for role_name in _as_string_tuple(policy.get("roles"), "context_policies.roles"):
            lines.append(f"      - {role_name}")
        mode = _as_required_string(policy.get("mode"), "context_policies.mode")
        lines.append(f"    mode: {mode}")
        lines.append("    share_only:")
        for artifact in _as_string_tuple(
            policy.get("share_only"), "context_policies.share_only"
        ):
            lines.append(f"      - {artifact}")
        lines.append("    do_not_share:")
        for artifact in _as_string_tuple(
            policy.get("do_not_share"), "context_policies.do_not_share"
        ):
            lines.append(f"      - {artifact}")
    return lines


def manifest_quality_gate_lines(config: TeamConfig) -> list[str]:
    """Render quality gate lines."""
    lines = ["quality_gates:"]
    for gate in config.quality_gates:
        lines.append(f"  - {gate}")
    return lines


def manifest_artifact_lines(config: TeamConfig, roles: tuple[Role, ...]) -> list[str]:
    """Render artifact lines."""
    lines = ["artifacts:"]
    for artifact in iter_artifacts(config, roles):
        lines.append(f"  - {artifact}")
    return lines


def render_role_topology(
    workflow_family: dict[str, object],
    indent: str,
) -> list[str]:
    """Render workflow role-family and same-role instance policy."""
    topology = workflow_family.get("role_topology")
    if not isinstance(topology, dict):
        return []
    topology = _as_object_mapping(cast(object, topology), "role_topology")
    lines = [f"{indent}role_topology:"]
    role_families = topology.get("role_families")
    if isinstance(role_families, dict):
        lines.append(f"{indent}  role_families:")
        for family_name, agent_types in _as_object_mapping(
            cast(object, role_families), "role_topology.role_families"
        ).items():
            lines.append(f"{indent}    {family_name}:")
            if isinstance(agent_types, list):
                for agent_type in _as_string_tuple(
                    cast(object, agent_types),
                    f"role_topology.role_families.{family_name}",
                ):
                    lines.append(f"{indent}      - {agent_type}")
            elif isinstance(agent_types, str):
                lines.append(f"{indent}      - {agent_types}")
            else:
                raise RuntimeError(
                    "role_topology.role_families entries must be strings or lists "
                    f"of strings: {family_name}"
                )
    same_role_instances = topology.get("same_role_parallel_instances")
    if isinstance(same_role_instances, dict):
        lines.append(f"{indent}  same_role_parallel_instances:")
        for key, value in _as_object_mapping(
            cast(object, same_role_instances),
            "role_topology.same_role_parallel_instances",
        ).items():
            if isinstance(value, bool):
                rendered_value = "true" if value else "false"
            elif isinstance(value, str):
                rendered_value = value
            else:
                raise RuntimeError(
                    "role_topology.same_role_parallel_instances values must be "
                    f"strings or booleans: {key}"
                )
            lines.append(f"{indent}    {key}: {rendered_value}")
    return lines


def render_subagent_prompt_packet(
    workflow_family: dict[str, object],
    indent: str,
) -> list[str]:
    """Render workflow-specific subagent prompt instructions for the manifest."""
    prompt = workflow_family.get("subagent_prompt")
    if not isinstance(prompt, dict):
        return []
    prompt = _as_object_mapping(cast(object, prompt), "subagent_prompt")
    lines = [f"{indent}subagent_prompt_packet:"]
    purpose = _as_optional_string(prompt.get("purpose"), "subagent_prompt.purpose")
    if purpose:
        lines.append(f"{indent}  purpose: {purpose!r}")
    lines.append(f"{indent}  subagent_startup_route: {SUBAGENT_STARTUP_ROUTE!r}")
    lines.append(f"{indent}  internal_skill_routes:")
    lines.append(f"{indent}    - {SUBAGENT_STARTUP_ROUTE!r}")
    lines.append(f"{indent}  tool_route: 'run.repo_tool_routing_policy'")
    lines.append(
        f"{indent}  tool_commands: 'run.repo_tool_routing_policy.sequential_tool_routes'"
    )
    lines.append(
        f"{indent}  tool_evidence: 'run.repo_tool_routing_policy.dynamic_skill_routing'"
    )
    lines.append(f"{indent}  tool_catalog_matches: 'tools/catalog.yaml'")
    lines.append(f"{indent}  required_tool_fields:")
    lines.append(f"{indent}    - tool_route")
    lines.append(f"{indent}    - tool_commands")
    lines.append(f"{indent}    - tool_evidence")
    lines.append(f"{indent}    - tool_rejection_prediction")
    for key in ("prompt_preamble", "workflow_focus", "reviewer_prompt"):
        lines.append(f"{indent}  {key}:")
        for value in _as_prompt_entry_tuple(prompt.get(key), f"subagent_prompt.{key}"):
            lines.append(f"{indent}    - {value!r}")
    return lines


def role_prompt_contract(role: Role, workflow_family: dict[str, object] | None) -> str:
    """Return the reusable prompt contract for one manifest role entry."""
    family_name = (
        str(workflow_family["name"])
        if workflow_family is not None
        else "the selected workflow"
    )
    write_scope = (
        "write only in the manifest write_policy scope and avoid paths assigned to other writers"
        if role.write_policy.mode != "read_only"
        else "do not edit repository files"
    )
    return (
        f"You are the {role.id} role for {family_name}. Start from structured context artifacts and the "
        "owned role_document_packet named in the handoff; load cross_cutting_document_packet "
        "entries only when the selected route or review gate makes them active, otherwise mark "
        f"them not_applicable. Use allowed_paths and do_not_read as ownership boundaries. {write_scope}. "
        "When run.subagent_prompt_packet.subagent_startup_route is present, carry that "
        "structural route field into the next handoff or review result without turning it "
        "into prompt keyword skill activation. "
        "Carry run.repo_tool_routing_policy tool_route, tool_commands, and tool_evidence into "
        "the next handoff or review result when repo-owned tools are part of the selected route. "
        "Return findings or outputs tied to request_clause_ids, artifact paths, dependency-file "
        "headers for every edited or created text file, remaining planned work, and the next "
        "required gate."
    )


def compact_role_prompt_contract(
    role: Role,
    workflow_family: dict[str, object] | None,
) -> str:
    """Return a short manifest copy of the role prompt contract."""
    family_name = (
        str(workflow_family["name"])
        if workflow_family is not None
        else "the selected workflow"
    )
    write_scope = (
        "read-only" if role.write_policy.mode == "read_only" else "bounded writer"
    )
    return (
        f"{role.id} for {family_name}; {write_scope}; use structured context artifacts, "
        "role-specific packet, common packet only when active, allowed paths, "
        "subagent startup route when present, repo tool route fields, and the listed "
        "output fields."
    )


def role_prompt_must_include(role: Role) -> tuple[str, ...]:
    """Return handoff fields every invocation prompt should include for one role."""
    common: list[str] = []
    if role.write_policy.mode != "read_only":
        common.extend(("write_policy", "allowed_files_or_directories"))
    if role.id == "designer":
        common.extend(
            (
                "abstract_design_frame",
                "responsibility_model",
                "concept_or_layer_model",
                "non_goals",
                "future_extension_layers",
                "evaluation_axes",
                "canonical_surface_relationships",
            )
        )
    if role.id == "design_reviewer":
        common.extend(
            (
                "abstract_design_frame_review",
                "adf_before_file_scope",
                "adf_to_implementation_trace",
                "revise_if_design_starts_from_files_or_current_findings",
            )
        )
    if role.id == "implementer":
        common.extend(
            (
                "abstract_design_frame",
                "implementation_source_packet",
                "design_to_implementation_trace",
                "test_plan_item",
                "remaining_planned_work_units",
            )
        )
    if role.id == "change_reviewer":
        common.extend(
            (
                "abstract_design_frame_trace",
                "implementation_source_packet_entry",
                "design_to_implementation_trace",
                "revise_if_slice_only_justified_by_nearest_file_helper_or_current_finding",
            )
        )
    if role.id == "final_reviewer":
        common.extend(
            (
                "abstract_design_frame_trace",
                "spec_to_product_trace",
                "review_finding_incorporation_trace",
            )
        )
    if role.id.endswith("_reviewer") or role.id in {
        "change_reviewer",
        "final_reviewer",
    }:
        common.extend(("findings_first_output", "approve_revise_or_escalate_decision"))
    return tuple(common)


def resolve_role_write_scope(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
    workspace_root: Path,
) -> RoleWriteScope:
    """Resolve concrete write paths for one role."""
    allowed_files = role_allowed_artifact_files(config, role, report_dir)
    allowed_directories = role_allowed_directories(role, workspace_root)
    unresolved_reason = role_write_scope_unresolved_reason(role, allowed_directories)
    return RoleWriteScope(
        role_id=role.id,
        mode=role.write_policy.mode,
        allowed_files=allowed_files,
        allowed_directories=allowed_directories,
        requires_worktree_scope=role.write_policy.requires_worktree_scope,
        worktree_scope_file=None,
        unresolved_reason=unresolved_reason,
        notes=role.write_policy.notes,
    )


def role_allowed_artifact_files(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
) -> tuple[Path, ...]:
    """Resolve generated artifact files one role may write."""
    return tuple(
        sorted(
            {
                (report_dir / config.artifacts[artifact_key]).resolve()
                for artifact_key in role.write_policy.allowed_artifacts
            },
            key=str,
        )
    )


def role_allowed_directories(
    role: Role,
    workspace_root: Path,
) -> tuple[Path, ...]:
    """Resolve configured current-checkout directories one role may write."""
    if role.write_policy.allowed_directories:
        return tuple(
            sorted(
                (
                    (workspace_root / directory).resolve()
                    for directory in role.write_policy.allowed_directories
                ),
                key=str,
            )
        )
    return ()


def role_write_scope_unresolved_reason(
    role: Role,
    allowed_directories: tuple[Path, ...],
) -> str | None:
    """Return why a configured current-checkout write policy is unresolved."""
    if not role.write_policy.requires_worktree_scope:
        return None
    if allowed_directories:
        return None
    return (
        "Legacy WORKTREE_SCOPE write scope is disabled; configure explicit "
        "write_policy.allowed_directories in agents/agents_config.json."
    )


def collect_changed_files(
    workspace_root: Path,
    ignored_roots: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    """Collect modified, staged, deleted, renamed, and untracked files."""
    changed: set[Path] = set()
    changed.update(
        _git_paths(
            workspace_root,
            ["diff", "--name-only", "--diff-filter=ACDMRTUXB"],
        )
    )
    changed.update(
        _git_paths(
            workspace_root,
            ["diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"],
        )
    )
    changed.update(
        _git_paths(workspace_root, ["ls-files", "--others", "--exclude-standard"])
    )
    ignored = tuple(root.resolve() for root in ignored_roots)
    filtered_paths = [
        path.resolve()
        for path in changed
        if not any(
            path.resolve() == root or root in path.resolve().parents for root in ignored
        )
    ]
    return tuple(sorted(filtered_paths, key=str))


def validate_role_write_scope(
    config: TeamConfig,
    role_name: str,
    report_dir: Path,
    workspace_root: Path,
    files: tuple[Path, ...] | None = None,
    report_dir_snapshot: dict[str, str] | None = None,
    workspace_snapshot: dict[str, str] | None = None,
    ignored_paths: tuple[Path, ...] = (),
) -> tuple[RoleWriteScope, tuple[Path, ...]]:
    """Validate changed files against the role's allowed write scope."""
    role = resolve_role(config, role_name)
    resolved_report_dir = report_dir.resolve()
    resolved_workspace_root = workspace_root.resolve()
    scope = resolve_role_write_scope(
        config, role, resolved_report_dir, resolved_workspace_root
    )
    resolved_ignored_paths = tuple(path.resolve() for path in ignored_paths)
    if workspace_snapshot is None:
        changed_files = set(
            collect_changed_files(
                resolved_workspace_root,
                ignored_roots=(resolved_report_dir,),
            )
        )
        changed_files = {
            path
            for path in changed_files
            if not any(
                _matches_ignored_path(path.resolve(), ignored_path)
                for ignored_path in resolved_ignored_paths
            )
        }
    else:
        changed_files = set(
            collect_workspace_change_delta(
                resolved_workspace_root,
                workspace_snapshot,
                ignored_roots=(resolved_report_dir,),
                ignored_paths=resolved_ignored_paths,
            )
        )
    if report_dir_snapshot is not None:
        changed_files.update(
            collect_directory_changes(resolved_report_dir, report_dir_snapshot)
        )
    changed_files.update(path.resolve() for path in (files or ()))
    violations = tuple(
        sorted(
            (
                path
                for path in changed_files
                if not _path_allowed(path.resolve(), scope)
            ),
            key=str,
        )
    )
    return scope, violations


def slugify(value: str) -> str:
    """Return an ASCII slug that is safe for file paths."""
    ascii_only = value.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    return slug or "task"


def make_run_id(task: str, created_at: datetime) -> str:
    """Build a stable default run id."""
    timestamp = created_at.strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{slugify(task)[:RUN_ID_TASK_SLUG_MAX_CHARS]}"


def _parse_role(raw_role: dict[str, object], default_activation: str) -> Role:
    """Parse a role from json."""
    role_id = _as_required_string(raw_role.get("id"), "role.id")
    raw_write_policy = _as_object_mapping(
        raw_role.get("write_policy"), f"roles[{role_id}].write_policy"
    )
    write_policy = WritePolicy(
        mode=_as_required_string(
            raw_write_policy.get("mode"), f"roles[{role_id}].write_policy.mode"
        ),
        allowed_artifacts=_as_string_tuple(
            raw_write_policy.get("allowed_artifacts"),
            f"roles[{role_id}].write_policy.allowed_artifacts",
        ),
        allowed_directories=_as_string_tuple(
            raw_write_policy.get("allowed_directories"),
            f"roles[{role_id}].write_policy.allowed_directories",
        ),
        requires_worktree_scope=_as_bool(
            raw_write_policy.get("requires_worktree_scope", False),
            f"roles[{role_id}].write_policy.requires_worktree_scope",
        ),
        notes=_as_optional_string(
            raw_write_policy.get("notes"), f"roles[{role_id}].write_policy.notes"
        ),
    )
    raw_activation = raw_role.get("activation")
    activation = (
        default_activation
        if raw_activation is None
        else _as_required_string(raw_activation, f"roles[{role_id}].activation")
    )
    return Role(
        id=role_id,
        owns=_as_string_tuple(raw_role.get("owns"), f"roles[{role_id}].owns"),
        required_outputs=_as_string_tuple(
            raw_role.get("required_outputs"), f"roles[{role_id}].required_outputs"
        ),
        activation=activation,
        write_policy=write_policy,
        codex_agents=_as_string_tuple(
            raw_role.get("codex_agents"), f"roles[{role_id}].codex_agents"
        ),
    )


def _git_paths(workspace_root: Path, args: list[str]) -> set[Path]:
    """Run git and convert stdout paths into absolute Paths."""
    result = subprocess.run(
        ["git", "-C", str(workspace_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    paths: set[Path] = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped:
            paths.add((workspace_root / stripped).resolve())
    return paths


def capture_directory_snapshot(root: Path) -> dict[str, str]:
    """Return a content-hash snapshot for every file below one directory."""
    resolved_root = root.resolve()
    if not resolved_root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in sorted(resolved_root.rglob("*")):
        if path.is_file():
            snapshot[str(path.resolve())] = _file_sha256(path)
    return snapshot


def load_directory_snapshot(path: Path) -> dict[str, str]:
    """Load a directory snapshot from json."""
    return {
        str(snapshot_path): str(digest)
        for snapshot_path, digest in json.loads(
            path.read_text(encoding="utf-8")
        ).items()
    }


def write_directory_snapshot(root: Path, output_path: Path) -> None:
    """Write the current directory snapshot to json."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(capture_directory_snapshot(root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def capture_workspace_change_snapshot(
    workspace_root: Path,
    ignored_roots: tuple[Path, ...] = (),
    ignored_paths: tuple[Path, ...] = (),
) -> dict[str, str]:
    """Return a snapshot for the workspace's current git-visible changes."""
    changed_paths = collect_changed_files(workspace_root, ignored_roots=ignored_roots)
    resolved_ignored_paths = tuple(path.resolve() for path in ignored_paths)
    snapshot: dict[str, str] = {}
    for path in changed_paths:
        resolved_path = path.resolve()
        if any(
            _matches_ignored_path(resolved_path, ignored_path)
            for ignored_path in resolved_ignored_paths
        ):
            continue
        snapshot[str(resolved_path)] = _path_snapshot_digest(resolved_path)
    return snapshot


def write_workspace_change_snapshot(
    workspace_root: Path,
    output_path: Path,
    ignored_roots: tuple[Path, ...] = (),
    ignored_paths: tuple[Path, ...] = (),
) -> None:
    """Write the current git-visible workspace change snapshot to json."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            capture_workspace_change_snapshot(
                workspace_root,
                ignored_roots=ignored_roots,
                ignored_paths=ignored_paths,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def collect_directory_changes(
    root: Path, before_snapshot: dict[str, str]
) -> tuple[Path, ...]:
    """Return files that changed within one directory since the captured snapshot."""
    after_snapshot = capture_directory_snapshot(root)
    changed_paths = {
        Path(raw_path).resolve()
        for raw_path in set(before_snapshot) | set(after_snapshot)
        if before_snapshot.get(raw_path) != after_snapshot.get(raw_path)
    }
    return tuple(sorted(changed_paths, key=str))


def collect_workspace_change_delta(
    workspace_root: Path,
    before_snapshot: dict[str, str],
    ignored_roots: tuple[Path, ...] = (),
    ignored_paths: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    """Return git-visible workspace paths that changed since the captured snapshot."""
    after_snapshot = capture_workspace_change_snapshot(
        workspace_root,
        ignored_roots=ignored_roots,
        ignored_paths=ignored_paths,
    )
    changed_paths = {
        Path(raw_path).resolve()
        for raw_path in set(before_snapshot) | set(after_snapshot)
        if before_snapshot.get(raw_path) != after_snapshot.get(raw_path)
    }
    return tuple(sorted(changed_paths, key=str))


def _path_allowed(path: Path, scope: RoleWriteScope) -> bool:
    """Return whether one path falls within the resolved write scope."""
    if path in scope.allowed_files:
        return True
    for directory in scope.allowed_directories:
        if path == directory or directory in path.parents:
            return True
    return False


def _matches_ignored_path(path: Path, ignored_path: Path) -> bool:
    """Return whether a path should be ignored during write-scope collection."""
    if path == ignored_path:
        return True
    return ignored_path.is_dir() and ignored_path in path.parents


def _file_sha256(path: Path) -> str:
    """Return the sha256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(SHA256_READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_snapshot_digest(path: Path) -> str:
    """Return a digest for one path, including deletions."""
    if path.is_file():
        return _file_sha256(path)
    return "__missing__"


def _as_mapping_tuple(value: object, field_name: str) -> tuple[dict[str, object], ...]:
    """Validate a list of mappings and return it as a tuple."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    normalized: list[dict[str, object]] = []
    for item in cast(list[object], value):
        normalized.append(_as_object_mapping(item, f"{field_name} entries"))
    return tuple(normalized)


def _as_object_mapping(value: object, field_name: str) -> dict[str, object]:
    """Validate a string-keyed mapping and return a typed copy."""
    if not isinstance(value, dict):
        raise RuntimeError(f"{field_name} must be a mapping")
    normalized: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            raise RuntimeError(f"{field_name} keys must be strings")
        normalized[key] = item
    return normalized


def _as_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Validate a list of strings and return it as a tuple."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    normalized: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise RuntimeError(f"{field_name} entries must be strings")
        normalized.append(item)
    return tuple(normalized)


def _as_prompt_entry_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Validate prompt entries and render them with the legacy manifest shape."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a list")
    return tuple(
        _render_prompt_entry(item, f"{field_name} entries")
        for item in cast(list[object], value)
    )


def _render_prompt_entry(value: object, field_name: str) -> str:
    """Render one prompt entry after validating supported YAML shapes."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        mapping = _as_object_mapping(cast(object, value), field_name)
        if not mapping:
            raise RuntimeError(f"{field_name} mapping entries must not be empty")
        rendered: dict[str, str] = {}
        for key, item in mapping.items():
            if not isinstance(item, str):
                raise RuntimeError(f"{field_name} mapping values must be strings")
            rendered[key] = item
        return str(rendered)
    raise RuntimeError(f"{field_name} entries must be strings or mappings")


def _as_required_string(value: object, field_name: str) -> str:
    """Validate one required string field."""
    if not isinstance(value, str):
        raise RuntimeError(f"{field_name} must be a string")
    return value


def _as_optional_string(value: object, field_name: str) -> str:
    """Validate one optional string field."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RuntimeError(f"{field_name} must be a string")
    return value


def _as_bool(value: object, field_name: str) -> bool:
    """Validate one boolean field."""
    if not isinstance(value, bool):
        raise RuntimeError(f"{field_name} must be a boolean")
    return value
