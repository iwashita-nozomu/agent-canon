#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides agent team agent workflow automation.
# upstream design ../README.md shared automation index
# upstream design ../../agents/task_catalog.yaml workflow topology and isolated skill-evaluation route
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md active design packet schema contract
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md shared vendor-only document packet policy
# upstream implementation ./skill_tool_commands.py builds selected skill command packets.
# upstream implementation ./implementation_route.py owns fixed-packet Spark eligibility
# upstream implementation ./model_profile_registry.py owns profile prompt/token materialization
# upstream implementation ./capacity_handshake.py owns capacity reservations and lifecycle state
# upstream implementation ./update_lifecycle_contract.py preserves owner-produced Decision Sufficiency verdicts and owns the terminal close token.
# downstream implementation ./workflow_monitor.py records Decision Sufficiency and lifecycle evidence references.
# @dependency-end
"""Shared runtime helpers for the permanent agent team."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Literal, Mapping, cast

import yaml
if __package__:
    from . import capacity_handshake
    from . import implementation_route
    from . import model_profile_registry
    from .artifact_identity import canonical_json_bytes
else:
    import capacity_handshake
    import implementation_route
    import model_profile_registry
    from artifact_identity import canonical_json_bytes
from route import decide_skills, implementation_handoff_required, load_skill_route_rules
from skill_tool_commands import SkillCommandPacket, packet_for_skill
from task_authority import AUTHORITY_FILE_NAME, build_default_task_authority
from update_lifecycle_contract import (
    import_decision_sufficiency_verdict,
    materialize_close_agent_tool_call as materialize_lifecycle_close_agent_tool_call,
    materialize_gate_verdict,
    validate_cleanup_proof,
    validate_descendant_close_receipt,
    validate_durable_handback,
    validate_gate_chain,
    validate_reservation_release_receipt,
    validate_record_binding,
)

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
STANDARD_AGENT_WAVE_SEQUENCE = ("selected_stages_only",)
STANDARD_AGENT_WAVE_SEQUENCE_SOURCE = (
    "agents/canonical/CODEX_SUBAGENTS.md#Wave Plan Contract"
)
STANDARD_AGENT_WAVE_SEQUENCE_GATE = "selected_stage_evidence"
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
REPO_TOOL_ROUTING_STATUS = "selected_skill_tool_call_tokens"
REPO_TOOL_ROUTING_ROUTE_BASIS = "selected_public_skills"
REPO_TOOL_ROUTING_EXECUTION_MODE = "sequential_by_skill_and_stage"
REPO_TOOL_ROUTING_SEQUENCE = (
    "materialize_tool_call_token",
    "execute_canonical_tool_id",
    "record_typed_result",
)
REPO_TOOL_ROUTING_STAGE_FIELDS = (
    "tool_call_token",
    "intent",
    "typed_failure_semantics",
)
REPO_DYNAMIC_SKILL_ROUTING_STATUS = "related_skill_candidates"
REPO_DYNAMIC_SKILL_ROUTING_NEXT = "add_skill_then_regenerate_repo_tool_routes"
TOOL_CALL_SCHEMA = "agent-canon.tool-call.v1"
SKILL_TOOL_CALL_ARGUMENT_SCHEMA = "agent-canon.skill-tool-commands.args.v1"
ROUTE_TOOL_CALL_ARGUMENT_SCHEMA = "agent-canon.route.args.v1"
DECISION_SUFFICIENCY_OWNER = "agents/skills/agent-orchestration.md#Decision Sufficiency Packet"
DECISION_SUFFICIENCY_VALIDATOR = "semantic_decision_sufficiency"
DECISION_SUFFICIENCY_MACHINE_FIELDS = (
    "owner",
    "replaceable_unit",
    "implementation_mechanism",
    "validation_route",
    "unresolved_branch",
)
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
VALIDATION_FAILURE_TAXONOMY_SOURCE = "documents/runtime/runtime-profiles-and-check-matrix.json"
RUNTIME_PROFILE_INVENTORY_PATH = ROOT / VALIDATION_FAILURE_TAXONOMY_SOURCE
_validation_failure_response_policy_cache: dict[str, object] | None = None
CONTRACT_COMPLETE_IMPLEMENTATION_HANDOFF_INSERT_INDEX = 6
DEFAULT_QUALITY_CHECK_POLICY_SOURCE = (
    "agents/canonical/CODEX_SUBAGENTS.md#Quality Check Default"
)
DEFAULT_QUALITY_CHECK_ROLE_IDS = (
    "docs_workflow_steward",
    "python_reviewer",
    "cpp_reviewer",
    "change_reviewer",
)
DEFAULT_QUALITY_CHECK_STAGES = ("selected_stages_only",)
DEFAULT_QUALITY_CHECK_STATIC_COMMANDS = (
    "tools/bin/agent-canon docs check <changed-markdown-paths>",
    "python3 tools/agent_tools/check_convention_compliance.py",
    "python3 tools/agent_tools/check_dependency_headers.py --changed",
    "bash tools/agent_tools/scan_dependency_headers.sh --changed --fail-missing",
    "bash tools/agent_tools/check_dependency_header_format.sh --changed --require-header",
)
CANONICAL_FORMAT_CHECK_ROUTE = "tools/bin/agent-canon docs check <changed-markdown-paths>"
OFFICIAL_HOOK_DISPATCHER = ".codex/hooks/hook_dispatcher.py"
OFFICIAL_HOOK_SCHEMA = "agent-canon.posttooluse-stop.v1"
OOP_EVIDENCE_DIMENSIONS = (
    "owner_overlap",
    "state_ownership",
    "api_boundary",
    "dependency_boundary",
)
def validation_failure_response_policy() -> dict[str, object]:
    """Return validation-failure response taxonomy from the JSON owner."""
    global _validation_failure_response_policy_cache
    if _validation_failure_response_policy_cache is None:
        raw_data = cast(
            "dict[str, object]",
            json.loads(RUNTIME_PROFILE_INVENTORY_PATH.read_text(encoding="utf-8")),
        )
        raw_policy = raw_data.get("validation_failure_response")
        if not isinstance(raw_policy, dict):
            raise ValueError("validation_failure_response must be an object")
        policy = cast("dict[str, object]", raw_policy)
        required_fields = policy.get("required_fields")
        intent_preservation = policy.get("intent_preservation")
        if not isinstance(required_fields, list) or not all(
            isinstance(field, str) for field in cast("list[object]", required_fields)
        ):
            raise ValueError("validation_failure_response.required_fields must be strings")
        if not isinstance(intent_preservation, list) or not all(
            isinstance(value, str) for value in cast("list[object]", intent_preservation)
        ):
            raise ValueError("validation_failure_response.intent_preservation must be strings")
        _validation_failure_response_policy_cache = {
            "taxonomy_source": VALIDATION_FAILURE_TAXONOMY_SOURCE,
            "required_fields": tuple(cast("list[str]", required_fields)),
            "intent_preservation": tuple(cast("list[str]", intent_preservation)),
        }
    return {
        "taxonomy_source": _validation_failure_response_policy_cache["taxonomy_source"],
        "required_fields": _validation_failure_response_policy_cache["required_fields"],
        "intent_preservation": _validation_failure_response_policy_cache[
            "intent_preservation"
        ],
    }


NON_SPAWN_WAVE_ROLE_IDS = {"manager", "verifier", "auditor"}
SAME_ROLE_SUBAGENT_INSTANCE_POLICY = {
    "status": "allowed_with_distinct_packets",
    "identity_key": "role_id+instance_id+agent_type",
    "parallel_read_only": "allowed_when_input_packets_or_review_focus_are_distinct",
    "parallel_write": "allowed_only_with_disjoint_write_scopes_and_parent_integration_order",
    "collision_policy": "serialize_current_checkout_waves",
}
SAME_ROLE_SUBAGENT_REQUIRED_FIELDS = (
    "role_id",
    "instance_id",
    "agent_type",
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
    "spawned_roles=<roles-or-none> role_instances=<role_id:instance_id:agent_type:packet> "
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
EVALUATOR_PROMPT_MUST_INCLUDE = (
    "current_scenario_packet",
    "packet_listed_evaluation_files",
    "do_not_read",
    "expected_output_schema",
)
STANDARD_RUN_ARTIFACT_KEYS = (
    "user_request_contract",
    "schedule",
    "work_log",
    "team_manifest",
    "verification",
    "closeout_gate",
    "agent_evaluation",
    "workflow_monitoring",
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
        "workspace_paths": ["documents/conventions/REVIEW_PROCESS.md"],
        "notes": "Design review checks the same upstream packet and the resulting design brief.",
    },
    "test_designer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
            "work_log",
        ],
        "workspace_paths": ["agents/workflows/implementation-waterfall-workflow.md"],
        "notes": (
            "Conditional test design starts from the implemented mechanism, approved design, "
            "and recorded unresolved risk."
        ),
    },
    "implementer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
            "document_flow_review",
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
            "change_review",
        ],
        "workspace_paths": ["documents/conventions/REVIEW_PROCESS.md"],
        "notes": (
            "Checkpoint review is the selected owning gate; test_plan is read only when "
            "post-implementation test design was activated."
        ),
    },
    "final_reviewer": {
        "artifact_keys": [
            "user_request_contract",
            "schedule",
            "design_brief",
            "design_review",
            "final_review",
        ],
        "workspace_paths": ["documents/conventions/REVIEW_PROCESS.md"],
        "notes": (
            "Final review is a selected escalation gate; test_plan is read only when "
            "post-implementation test design was activated."
        ),
    },
    "scheduler": {
        "artifact_keys": ["user_request_contract", "schedule"],
        "workspace_paths": ["agents/workflows/implementation-waterfall-workflow.md"],
        "notes": "Scheduling reads explicit requirement and plan surfaces.",
    },
}
ROLE_DOCUMENT_PACKET_SECTION_SPECS: dict[str, dict[str, tuple[str, ...]]] = {
    "designer": {
        "agents/workflows/implementation-waterfall-workflow.md": (
            "Gate 5. 詳細設計",
            "Gate 6. 詳細設計レビュー",
            "Gate 7. 文書通読レビュー",
        ),
        "agents/canonical/CODEX_WORKFLOW.md": (
            "4. Run Bootstrap",
            "5. Implementation",
        ),
    },
    "implementer": {
        "agents/workflows/implementation-waterfall-workflow.md": (
            "Gate 5. 詳細設計",
            "Gate 6. 詳細設計レビュー",
            "Gate 7. 文書通読レビュー",
            "Gate 8. 実装",
            "Gate 8.5. 実装後の条件付きテストケース設計",
            "Gate 9. 条件付き受け入れ review",
        ),
        "agents/canonical/CODEX_WORKFLOW.md": (
            "4. Run Bootstrap",
            "5. Implementation",
        ),
    },
}
COMMON_CROSS_CUTTING_DOCUMENT_PATHS: tuple[str, ...] = (
    "documents/conventions/REVIEW_PROCESS.md",
    "documents/codex/AGENTS_COORDINATION.md",
    "documents/conventions/coding-conventions-python.md",
    "documents/operations/notes-lifecycle.md",
    "agents/workflows/agent-learning-workflow.md",
    "documents/agent-canon/agent-canon-subtree-migration.md",
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


class ReportBundleArtifactPathError(RuntimeError):
    """Report one rejected run-artifact path and its containment reason."""

    def __init__(self, declared_path: str, reason: str) -> None:
        self.declared_path = declared_path
        self.reason = reason
        super().__init__(
            f"report_bundle_artifact_path_invalid:{reason}:{declared_path}"
        )


def resolve_report_bundle_artifact_path(
    report_dir: Path,
    declared_path: str,
    *,
    require_existing_regular_file: bool = False,
) -> Path:
    """Resolve a lexical bundle path without following symlink components."""
    relative_path = Path(declared_path)
    if not declared_path or relative_path.is_absolute():
        raise ReportBundleArtifactPathError(declared_path, "not_relative")
    parts = tuple(part for part in relative_path.parts if part not in {"", "."})
    if not parts:
        raise ReportBundleArtifactPathError(declared_path, "not_relative")
    report_root = report_dir.resolve()
    lexical_path = report_root
    for index, component in enumerate(parts):
        if component == "..":
            raise ReportBundleArtifactPathError(declared_path, "outside_bundle")
        lexical_path = lexical_path / component
        if lexical_path.is_symlink():
            raise ReportBundleArtifactPathError(declared_path, "symlink_component")
        if not lexical_path.exists():
            continue
        is_final_component = index == len(parts) - 1
        if is_final_component and not lexical_path.is_file():
            raise ReportBundleArtifactPathError(declared_path, "nonregular_target")
        if not is_final_component and not lexical_path.is_dir():
            raise ReportBundleArtifactPathError(declared_path, "non_directory_parent")
    candidate = lexical_path.resolve()
    try:
        candidate.relative_to(report_root)
    except ValueError as exc:
        raise ReportBundleArtifactPathError(declared_path, "outside_bundle") from exc
    if require_existing_regular_file and not candidate.is_file():
        raise ReportBundleArtifactPathError(declared_path, "missing_regular_file")
    return candidate


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
    instance_id: str
    agent_type: str

    def __post_init__(self) -> None:
        """Default the role instance id from the selected executable agent."""
        if not self.instance_id:
            object.__setattr__(self, "instance_id", f"{self.role_id}_{self.agent_type}")

    @property
    def executable_identity(self) -> str:
        """Return the authoritative executable role identity."""
        return f"{self.role_id}:{self.instance_id}:{self.agent_type}"


@dataclass(frozen=True)
class AgentTypeSelection:
    """Explicit parent-packet selection of one executable agent for a role."""

    role_id: str
    agent_type: str
    evidence: str


@dataclass(frozen=True)
class StageWave:
    """One catalog-owned subagent stage wave."""

    id: str
    stage_class: str
    role_ids: tuple[str, ...]


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
class DocumentSectionLocator:
    """One exact markdown section a role must read within a document."""

    heading: str
    anchor: str
    required: bool = True


@dataclass(frozen=True)
class DocumentPacketEntry:
    """One explicit path a role must read before work."""

    path: Path
    rationale: str
    sections: tuple[DocumentSectionLocator, ...] = ()


@dataclass(frozen=True)
class RoleDocumentPacket:
    """Resolved explicit document packet for one role."""

    role_id: str
    read_before_work: tuple[DocumentPacketEntry, ...]
    must_cite_before_edit: bool
    notes: str


ActiveDesignSection = Literal[
    "abstract_design_frame",
    "implementation_source_packet",
    "design_side_effect_map",
    "design_to_implementation_trace",
]
ACTIVE_DESIGN_SECTIONS: tuple[ActiveDesignSection, ...] = (
    "abstract_design_frame",
    "implementation_source_packet",
    "design_side_effect_map",
    "design_to_implementation_trace",
)
ACTIVE_DESIGN_REFERENCE_FIELDS = (
    "clause_refs",
    "owner_refs",
    "source_refs",
    "dependency_refs",
    "output_refs",
    "reviewer_refs",
)
ACTIVE_PACKET_ENTRY_IDS = {
    "abstract_design_frame": "abstract-design-frame",
    "implementation_source_packet": "implementation-source-packet",
    "design_side_effect_map": "design-side-effect-map",
    "design_to_implementation_trace": "design-to-implementation-trace",
}


@dataclass(frozen=True)
class ActiveDesignClause:
    """One closed packet clause and its canonical source reference."""

    clause_id: str
    source_ref: str


@dataclass(frozen=True)
class ActiveDesignPacketEntry:
    """One typed graph edge set for an active design packet entry."""

    entry_id: str
    responsibility_id: str
    clause_refs: tuple[str, ...]
    owner_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    dependency_refs: tuple[str, ...]
    output_refs: tuple[str, ...]
    reviewer_refs: tuple[str, ...]


@dataclass(frozen=True)
class ActiveDesignPacketConfig:
    """Typed active packet plus its closed graph/reference projection contract."""

    schema: str
    design_artifact: str
    design_review_artifact: str
    document_flow_review_artifact: str
    document_flow_required: bool
    clause_registry: tuple[ActiveDesignClause, ...]
    abstract_design_frame: ActiveDesignPacketEntry
    implementation_source_packet: ActiveDesignPacketEntry
    design_side_effect_map: ActiveDesignPacketEntry
    design_to_implementation_trace: ActiveDesignPacketEntry

    def section_entries(
        self,
    ) -> tuple[tuple[ActiveDesignSection, ActiveDesignPacketEntry], ...]:
        """Return graph entries in their canonical dependency order."""
        return tuple((name, getattr(self, name)) for name in ACTIVE_DESIGN_SECTIONS)


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
    artifact_registry: dict[str, object]
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
    language_review_candidates: tuple[str, ...] = ()
    default_review_packs_enabled: bool = False
    default_review_pack_ids: tuple[str, ...] = ()
    selected_skills: tuple[str, ...] = ()
    task_catalog: TaskCatalog | None = None
    agent_type_selections: tuple[AgentTypeSelection, ...] = ()
    parent_lineage_id: str = ""
    decision_sufficiency_packet: dict[str, object] | None = None
    decision_sufficiency_packet_ref: str = ""
    active_design_packet: ActiveDesignPacketConfig | None = None


@dataclass(frozen=True)
class CapacityHandshakeConsumerBinding:
    """Closed consumer projection for the provider-owned capacity ledger."""

    binding_version: int = 1
    provider_owner_id: str = "capacity_handshake"
    consumer_owner_ids: tuple[str, ...] = ("agent_team", "task_close")
    allowed_api_ids: tuple[str, ...] = (
        "reserve_capacity",
        "enqueue_ready_work",
        "record_lifecycle_transition",
        "materialize_closeout_packet",
    )
    provider_type_ids: tuple[str, ...] = (
        "LifecycleStatus",
        "DescendantLifecycleRecord",
        "CapacityLedger",
        "LifecycleTransitionRecord",
        "LedgerWriteResult",
        "ParentChildEdge",
        "DescendantTopologyReadback",
        "CloseoutPacket",
        "CloseAgentCallRecord",
        "LifecycleCloseoutFailure",
    )
    duplicate_definition_policy: str = "forbidden"

    @property
    def shape_id(self) -> str:
        return "capacity_handshake_consumer_binding_v1"


@dataclass
class _CapacityRuntime:
    """Runtime-owned objects shared by parent and nested lifecycle consumers."""

    binding: CapacityHandshakeConsumerBinding
    snapshot: capacity_handshake.CapacitySnapshot
    ledger: capacity_handshake.CapacityLedger
    parent_lineage_id: str
    topology_proof_sha256: str
    requested_capacity: int
    write_scope_cap: int


@dataclass(frozen=True)
class ImplementationDispatch:
    """One executable fixed-packet dispatch and its single owning gate."""

    route_result: implementation_route.ImplementationRouteResult
    prompt_capsule: model_profile_registry.MaterializedPromptCapsule | None
    close_agent_token: model_profile_registry.ToolCallToken | None
    worker_agent_id: str | None
    owner_gate_id: str
    owner_gate_count: int
    spawn_count: int
    status: str


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
    artifact_registry = _as_object_mapping(raw.get("artifacts"), "artifacts")
    artifacts = {
        key: _as_required_string(value, f"artifacts.{key}")
        for key, value in artifact_registry.items()
        if key != "active_design_packet"
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
        artifact_registry=artifact_registry,
        artifacts=artifacts,
    )


ACTIVE_DESIGN_PACKET_SCHEMA = "waterfall.design_packet.v1"
ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS = (
    "design_artifact",
    "design_review_artifact",
    "document_flow_review_artifact",
)
ACTIVE_DESIGN_PACKET_FIELDS = (
    "schema",
    *ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS,
    "document_flow_required",
    "clause_registry",
    *ACTIVE_DESIGN_SECTIONS,
)

ACTIVE_PACKET_ENTRY_FIELDS = (
    "entry_id",
    "responsibility_id",
    *ACTIVE_DESIGN_REFERENCE_FIELDS,
)
ACTIVE_PACKET_REFERENCE_PREFIXES = {
    "clause_refs": (),
    "owner_refs": ("role:",),
    "source_refs": ("repo:", "artifact:"),
    "dependency_refs": ("entry:", "header:"),
    "output_refs": ("artifact:",),
    "reviewer_refs": ("role:",),
}
ACTIVE_PACKET_SCHEMA = ACTIVE_DESIGN_PACKET_SCHEMA


def _active_packet_reference_tuple(value: object, field: str) -> tuple[str, ...]:
    """Validate one non-empty typed reference list."""
    values = _as_string_tuple(value, field)
    if not values:
        raise RuntimeError(f"{field}:empty")
    prefixes = ACTIVE_PACKET_REFERENCE_PREFIXES[field.rsplit(".", 1)[-1]]
    if prefixes and any(not candidate.startswith(prefixes) for candidate in values):
        raise RuntimeError(f"{field}:invalid_reference")
    if field.rsplit(".", 1)[-1] == "clause_refs" and any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", candidate) is None
        for candidate in values
    ):
        raise RuntimeError(f"{field}:invalid_reference")
    return values


def _normalize_active_packet_entry(
    raw_entry: object,
    section: ActiveDesignSection,
    field_prefix: str,
) -> ActiveDesignPacketEntry:
    """Normalize one graph entry with explicit closed fields and dependencies."""
    entry_field = f"{field_prefix}.{section}"
    entry = _as_object_mapping(raw_entry, entry_field)
    unknown = sorted(set(entry).difference(ACTIVE_PACKET_ENTRY_FIELDS))
    if unknown:
        raise RuntimeError(f"{entry_field}:field_unknown:" + ",".join(unknown))
    missing = [field for field in ACTIVE_PACKET_ENTRY_FIELDS if field not in entry]
    if missing:
        raise RuntimeError(f"{entry_field}:field_missing:" + ",".join(missing))
    entry_id = _as_required_string(entry["entry_id"], f"{entry_field}.entry_id")
    if entry_id != ACTIVE_PACKET_ENTRY_IDS[section]:
        raise RuntimeError(f"{entry_field}.entry_id:invalid")
    responsibility_id = _as_required_string(
        entry["responsibility_id"], f"{entry_field}.responsibility_id"
    )
    references = {
        field: _active_packet_reference_tuple(entry[field], f"{entry_field}.{field}")
        for field in ACTIVE_DESIGN_REFERENCE_FIELDS
    }
    return ActiveDesignPacketEntry(
        entry_id=entry_id,
        responsibility_id=responsibility_id,
        clause_refs=references["clause_refs"],
        owner_refs=references["owner_refs"],
        source_refs=references["source_refs"],
        dependency_refs=references["dependency_refs"],
        output_refs=references["output_refs"],
        reviewer_refs=references["reviewer_refs"],
    )


def normalize_active_design_packet_config(
    raw_packet: object,
    field_prefix: str,
) -> ActiveDesignPacketConfig:
    """Normalize one complete packet record at the typed runtime boundary."""
    packet = _as_object_mapping(raw_packet, field_prefix)
    unknown = sorted(set(packet).difference(ACTIVE_DESIGN_PACKET_FIELDS))
    if unknown:
        raise RuntimeError(f"{field_prefix}:field_unknown:" + ",".join(unknown))
    missing = [field for field in ACTIVE_DESIGN_PACKET_FIELDS if field not in packet]
    if missing:
        raise RuntimeError(f"{field_prefix}:field_missing:" + ",".join(missing))
    schema = _as_required_string(packet["schema"], f"{field_prefix}.schema")
    if schema != ACTIVE_DESIGN_PACKET_SCHEMA:
        raise RuntimeError(f"{field_prefix}:schema_unknown:{schema}")
    paths: dict[str, str] = {}
    for field in ACTIVE_DESIGN_PACKET_ARTIFACT_FIELDS:
        value = _as_required_string(packet[field], f"{field_prefix}.{field}")
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"{field_prefix}:field_invalid:{field}")
        paths[field] = value
    document_flow_required = packet["document_flow_required"]
    if not isinstance(document_flow_required, bool):
        raise RuntimeError(
            f"{field_prefix}:field_invalid:document_flow_required"
        )
    raw_clauses = packet["clause_registry"]
    if not isinstance(raw_clauses, list) or not raw_clauses:
        raise RuntimeError(f"{field_prefix}.clause_registry:field_invalid")
    clauses: list[ActiveDesignClause] = []
    for index, raw_clause in enumerate(raw_clauses):
        clause_field = f"{field_prefix}.clause_registry[{index}]"
        clause = _as_object_mapping(raw_clause, clause_field)
        if set(clause) != {"clause_id", "source_ref"}:
            unknown = sorted(set(clause).difference({"clause_id", "source_ref"}))
            if unknown:
                raise RuntimeError(f"{clause_field}:field_unknown:" + ",".join(unknown))
            missing = sorted({"clause_id", "source_ref"}.difference(clause))
            raise RuntimeError(f"{clause_field}:field_missing:" + ",".join(missing))
        clause_id = _as_required_string(clause["clause_id"], f"{clause_field}.clause_id")
        source_ref = _as_required_string(clause["source_ref"], f"{clause_field}.source_ref")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", clause_id):
            raise RuntimeError(f"{clause_field}.clause_id:invalid")
        if not source_ref.startswith(("repo:", "artifact:")):
            raise RuntimeError(f"{clause_field}.source_ref:invalid")
        clauses.append(ActiveDesignClause(clause_id, source_ref))
    clause_ids = tuple(clause.clause_id for clause in clauses)
    if len(set(clause_ids)) != len(clause_ids):
        raise RuntimeError(f"{field_prefix}.clause_registry:duplicate_id")
    entries = {
        section: _normalize_active_packet_entry(packet[section], section, field_prefix)
        for section in ACTIVE_DESIGN_SECTIONS
    }
    responsibility_ids = {entry.responsibility_id for entry in entries.values()}
    if len(responsibility_ids) != 1:
        raise RuntimeError(f"{field_prefix}:responsibility_id:inconsistent")
    known_entry_ids = {entry.entry_id for entry in entries.values()}
    expected_dependencies: dict[ActiveDesignSection, set[str]] = {
        "abstract_design_frame": set(),
        "implementation_source_packet": {"abstract-design-frame"},
        "design_side_effect_map": {"abstract-design-frame"},
        "design_to_implementation_trace": {
            "abstract-design-frame",
            "implementation-source-packet",
            "design-side-effect-map",
        },
    }
    referenced_clauses: set[str] = set()
    for section, entry in entries.items():
        referenced_clauses.update(entry.clause_refs)
        if not referenced_clauses.issubset(set(clause_ids)):
            raise RuntimeError(f"{field_prefix}.{section}.clause_refs:invalid")
        dependency_entries = {
            value.removeprefix("entry:")
            for value in entry.dependency_refs
            if value.startswith("entry:")
        }
        if dependency_entries != expected_dependencies[section] or not dependency_entries.issubset(
            known_entry_ids
        ):
            raise RuntimeError(f"{field_prefix}.{section}.dependency_refs:invalid")
    if referenced_clauses != set(clause_ids):
        raise RuntimeError(f"{field_prefix}.clause_registry:unreferenced_clause")
    return ActiveDesignPacketConfig(
        schema=schema,
        design_artifact=paths["design_artifact"],
        design_review_artifact=paths["design_review_artifact"],
        document_flow_review_artifact=paths["document_flow_review_artifact"],
        document_flow_required=document_flow_required,
        clause_registry=tuple(clauses),
        abstract_design_frame=entries["abstract_design_frame"],
        implementation_source_packet=entries["implementation_source_packet"],
        design_side_effect_map=entries["design_side_effect_map"],
        design_to_implementation_trace=entries["design_to_implementation_trace"],
    )


def parse_active_design_packet_input(
    value: str | None,
) -> ActiveDesignPacketConfig | None:
    """Parse one atomic JSON packet supplied by a run entrypoint."""
    if value is None:
        return None
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("active_design_packet:json_invalid") from exc
    return normalize_active_design_packet_config(parsed, "active_design_packet")


def _active_packet_entry_mapping(entry: ActiveDesignPacketEntry) -> dict[str, object]:
    """Serialize one typed graph entry for manifest materialization."""
    return {
        "entry_id": entry.entry_id,
        "responsibility_id": entry.responsibility_id,
        "clause_refs": list(entry.clause_refs),
        "owner_refs": list(entry.owner_refs),
        "source_refs": list(entry.source_refs),
        "dependency_refs": list(entry.dependency_refs),
        "output_refs": list(entry.output_refs),
        "reviewer_refs": list(entry.reviewer_refs),
    }


def active_design_packet_mapping(
    packet: ActiveDesignPacketConfig,
) -> dict[str, object]:
    """Serialize the exact closed active packet and graph entries."""
    return {
        "schema": packet.schema,
        "design_artifact": packet.design_artifact,
        "design_review_artifact": packet.design_review_artifact,
        "document_flow_review_artifact": packet.document_flow_review_artifact,
        "document_flow_required": packet.document_flow_required,
        "clause_registry": [
            {"clause_id": clause.clause_id, "source_ref": clause.source_ref}
            for clause in packet.clause_registry
        ],
        **{
            section: _active_packet_entry_mapping(entry)
            for section, entry in packet.section_entries()
        },
    }


ACTIVE_DESIGN_PACKET_MATERIALIZATION_SCHEMA = (
    "waterfall.active_design_packet_materialization.v1"
)


def _distinct_active_packet_references(
    packet: ActiveDesignPacketConfig,
    field: str,
) -> tuple[str, ...]:
    """Return packet references once, preserving the declared order."""
    values: list[str] = []
    for _section, entry in packet.section_entries():
        for reference in cast(tuple[str, ...], getattr(entry, field)):
            if reference not in values:
                values.append(reference)
    return tuple(values)


def _materialized_source_identity(
    spec: RunBundleSpec,
    reference: str,
) -> dict[str, object]:
    """Resolve one source reference and bind it to the current file bytes."""
    root_name, separator, fragment = reference.partition("#")
    prefix, delimiter, relative_value = root_name.partition(":")
    if not delimiter or prefix not in {"repo", "artifact"}:
        raise RuntimeError(f"active_design_packet_reference_invalid:source:{reference}")
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"active_design_packet_reference_invalid:source:{reference}")
    root = spec.report_dir if prefix == "artifact" else spec.workspace_root
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"active_design_packet_reference_invalid:source:{reference}"
        ) from exc
    if not candidate.is_file() or candidate.is_symlink():
        raise RuntimeError(f"active_design_packet_reference_missing:{reference}")
    fragment_kind = "none"
    fragment_value = None
    if separator:
        fragment_kind, fragment_value = fragment.split(":", 1)
        if fragment_kind not in {"section", "symbol"} or not fragment_value:
            raise RuntimeError(f"active_design_packet_reference_invalid:source:{reference}")
    return {
        "declared_ref": reference,
        "root_key": prefix,
        "relative_path": relative.as_posix(),
        "fragment_kind": fragment_kind,
        "fragment_value": fragment_value,
        "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "parser_match_count": 1,
    }


def _materialized_dependency_identity(
    spec: RunBundleSpec,
    reference: str,
) -> dict[str, object]:
    """Bind one declared dependency edge to endpoint bytes without reparsing prose."""
    match = re.fullmatch(
        r"header:(?P<direction>[^:]+):(?P<kind>[^:]+):repo:(?P<source>[^#]+)->repo:(?P<target>[^#]+)",
        reference,
    )
    if match is None:
        raise RuntimeError(f"active_design_packet_reference_invalid:dependency:{reference}")
    source = Path(match.group("source"))
    target = Path(match.group("target"))
    if source.is_absolute() or target.is_absolute() or ".." in source.parts or ".." in target.parts:
        raise RuntimeError(f"active_design_packet_reference_invalid:dependency:{reference}")
    source_path = (spec.workspace_root / source).resolve()
    target_path = (spec.workspace_root / target).resolve()
    if not source_path.is_file() or not target_path.is_file():
        raise RuntimeError(f"active_design_packet_reference_missing:{reference}")
    normalized = (
        f"header:{match.group('direction')}:{match.group('kind')}:repo:"
        f"{source.as_posix()}->repo:{target.as_posix()}"
    )
    return {
        "declared_ref": reference,
        "normalized_key": normalized,
        "source_path": source.as_posix(),
        "target_path": target.as_posix(),
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "target_sha256": hashlib.sha256(target_path.read_bytes()).hexdigest(),
        "verification": "declared_header_identity",
    }


def active_design_packet_reference_projection(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketConfig,
    artifact_names: tuple[str, ...],
) -> dict[str, object]:
    """Materialize the selected packet's graph identity for downstream readers."""
    packet_mapping = active_design_packet_mapping(packet)
    source_refs = list(_distinct_active_packet_references(packet, "source_refs"))
    for clause in packet.clause_registry:
        if clause.source_ref not in source_refs:
            source_refs.append(clause.source_ref)
    dependency_refs = tuple(
        reference
        for reference in _distinct_active_packet_references(packet, "dependency_refs")
        if reference.startswith("header:")
    )
    output_refs = _distinct_active_packet_references(packet, "output_refs")
    role_output_projections = [
        {
            "role_ref": f"role:{role.id}",
            "output_refs": [f"artifact:{output}" for output in selected_role_outputs(spec.config, role, packet)],
        }
        for role in spec.roles
    ]
    reviewer_refs = _distinct_active_packet_references(packet, "reviewer_refs")
    review_outputs = {
        f"artifact:{packet.design_review_artifact}",
        f"artifact:{packet.document_flow_review_artifact}",
    }
    reviewer_projections = []
    role_output_map = {
        item["role_ref"]: cast(list[str], item["output_refs"])
        for item in role_output_projections
    }
    for reviewer in reviewer_refs:
        matches = [
            output for output in role_output_map.get(reviewer, []) if output in review_outputs
        ]
        if len(matches) == 1:
            reviewer_projections.append(
                {"reviewer_ref": reviewer, "review_artifact_ref": matches[0]}
            )
    planned_paths = tuple(PurePosixPath(path) for path in artifact_names)
    return {
        "schema": ACTIVE_DESIGN_PACKET_MATERIALIZATION_SCHEMA,
        "packet_sha256": hashlib.sha256(canonical_json_bytes(packet_mapping)).hexdigest(),
        "source_results": [
            _materialized_source_identity(spec, reference) for reference in source_refs
        ],
        "dependency_results": [
            _materialized_dependency_identity(spec, reference)
            for reference in dependency_refs
        ],
        "role_output_projections": role_output_projections,
        "reviewer_artifact_projections": reviewer_projections,
        "clause_results": [
            {"clause_id": clause.clause_id, "source_ref": clause.source_ref}
            for clause in packet.clause_registry
        ],
        "output_results": [
            {
                "output_ref": reference,
                "relative_path": reference.removeprefix("artifact:"),
                "planned_count": planned_paths.count(
                    PurePosixPath(reference.removeprefix("artifact:"))
                ),
            }
            for reference in output_refs
        ],
        "planned_output_paths": sorted(path.as_posix() for path in planned_paths),
    }


def resolve_active_design_packet_config(
    config: TeamConfig,
    workflow_family: Mapping[str, object] | None = None,
) -> ActiveDesignPacketConfig:
    """Resolve workflow-selected packet, falling back to the config registry."""
    if workflow_family is not None and "active_design_packet" in workflow_family:
        raw_packet = workflow_family["active_design_packet"]
        field_prefix = "workflow_family.active_design_packet"
    else:
        raw_packet = config.artifact_registry.get("active_design_packet")
        field_prefix = "artifacts.active_design_packet"
    if raw_packet is None:
        raise RuntimeError("artifacts.active_design_packet:missing")
    return normalize_active_design_packet_config(raw_packet, field_prefix)


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


def selected_skill_command_packets(
    selected_skills: tuple[str, ...],
) -> tuple[SkillCommandPacket, ...]:
    """Build repo tool command packets for selected public skills."""
    return tuple(
        packet_for_skill(ROOT, skill) for skill in selected_skill_names(selected_skills)
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
    skill_list = format_public_skill_list(skill_names)
    dynamic_candidates = dynamic_skill_candidate_names(selected_skills)
    return (
        "REPO_TOOL_ROUTING_POLICY=run.repo_tool_routing_policy",
        "REPO_TOOL_CALL_TOKEN_SCHEMA=agent-canon.tool-call.v1",
        f"REPO_TOOL_SELECTED_SKILLS={skill_list}",
        f"REPO_TOOL_DYNAMIC_CANDIDATES={format_public_skill_list(dynamic_candidates)}",
        f"REPO_TOOL_ROUTING_SOURCE={REPO_TOOL_ROUTING_POLICY_SOURCE}",
        f"REPO_TOOL_ROUTING_OWNER={REPO_TOOL_ROUTING_OWNER}",
        f"REPO_TOOL_ROUTING_ROUTE_BASIS={REPO_TOOL_ROUTING_ROUTE_BASIS}",
        f"REPO_TOOL_ROUTING_EXECUTION_MODE={REPO_TOOL_ROUTING_EXECUTION_MODE}",
        f"REPO_TOOL_ROUTING_SEQUENCE={','.join(REPO_TOOL_ROUTING_SEQUENCE)}",
        f"REPO_TOOL_ROUTING_STAGE_FIELDS={','.join(REPO_TOOL_ROUTING_STAGE_FIELDS)}",
        "REPO_TOOL_ROUTING_CHECK_TOOL_ID=skill-tool-commands",
        f"REPO_DYNAMIC_SKILL_ROUTING_POLICY={REPO_DYNAMIC_SKILL_ROUTING_STATUS}",
        "REPO_DYNAMIC_SKILL_ROUTING_TOOL_CALL="
        + json.dumps(
            materialize_dynamic_route_tool_call_token(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        f"REPO_DYNAMIC_SKILL_ROUTING_CANDIDATES={format_public_skill_list(dynamic_candidates)}",
        f"REPO_DYNAMIC_SKILL_ROUTING_NEXT={REPO_DYNAMIC_SKILL_ROUTING_NEXT}",
    )


def materialize_tool_call_token(
    *,
    tool_id: str,
    argument_schema_id: str,
    argument_properties: Mapping[str, Mapping[str, object]],
    arguments: Mapping[str, object],
    intent: str,
    typed_failure_semantics: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Materialize one canonical, directly executable route-packet ToolCall."""
    if not tool_id or not argument_schema_id or not intent:
        raise RuntimeError("tool_call_token requires tool_id, schema, and intent")
    if set(arguments) != set(argument_properties):
        raise RuntimeError("tool_call_token arguments do not match argument schema")
    failures: list[dict[str, object]] = []
    for index, failure in enumerate(typed_failure_semantics):
        if set(failure) != {"code", "retryable", "next"}:
            raise RuntimeError(
                "tool_call_token typed failure must contain code, retryable, and next: "
                f"{index}"
            )
        if not isinstance(failure["code"], str) or not failure["code"]:
            raise RuntimeError("tool_call_token failure code must be non-empty")
        if not isinstance(failure["retryable"], bool):
            raise RuntimeError("tool_call_token failure retryable must be boolean")
        if not isinstance(failure["next"], str) or not failure["next"]:
            raise RuntimeError("tool_call_token failure next must be non-empty")
        failures.append(dict(failure))
    record: dict[str, object] = {
        "schema": TOOL_CALL_SCHEMA,
        "tool_id": tool_id,
        "argument_schema": {
            "$id": argument_schema_id,
            "type": "object",
            "required": list(argument_properties),
            "properties": {
                key: dict(value) for key, value in argument_properties.items()
            },
            "additionalProperties": False,
        },
        "arguments": dict(arguments),
        "intent": intent,
        "typed_failure_semantics": failures,
    }
    token_digest = hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    record["token_id"] = f"tool-call:{token_digest}"
    record["token_body_sha256"] = "sha256:" + hashlib.sha256(
        canonical_json_bytes(record)
    ).hexdigest()
    return record


def materialize_skill_tool_call_token(skill: str) -> dict[str, object]:
    """Return the canonical skill-command materializer call without prose argv."""
    return materialize_tool_call_token(
        tool_id="skill-tool-commands",
        argument_schema_id=SKILL_TOOL_CALL_ARGUMENT_SCHEMA,
        argument_properties={
            "skill": {"type": "string", "minLength": 1},
            "format": {"type": "string", "enum": ["json"]},
        },
        arguments={"skill": skill, "format": "json"},
        intent="Materialize the selected skill's canonical repository-tool packet.",
        typed_failure_semantics=(
            {
                "code": "skill_tool_route:unknown_skill",
                "retryable": False,
                "next": "reject_route_packet",
            },
            {
                "code": "skill_tool_route:catalog_mismatch",
                "retryable": False,
                "next": "return_to_tool_catalog_owner",
            },
        ),
    )


def materialize_dynamic_route_tool_call_token() -> dict[str, object]:
    """Return a canonical route call bound to the run's request artifact."""
    return materialize_tool_call_token(
        tool_id="route",
        argument_schema_id=ROUTE_TOOL_CALL_ARGUMENT_SCHEMA,
        argument_properties={
            "prompt_ref": {"type": "string", "minLength": 1},
            "format": {"type": "string", "enum": ["json"]},
        },
        arguments={"prompt_ref": "run.user_request_contract", "format": "json"},
        intent="Resolve a changed request into the canonical public-skill route.",
        typed_failure_semantics=(
            {
                "code": "route:request_artifact_missing",
                "retryable": False,
                "next": "reject_route_packet",
            },
            {
                "code": "route:no_matching_skill",
                "retryable": False,
                "next": "return_typed_no_match",
            },
        ),
    )


@dataclass(frozen=True)
class CloseAgentLifecycleEvidence:
    """Validated-input domain for G6 and terminal close materialization."""

    gate_verdicts: Sequence[Mapping[str, object]]
    cleanup_proof: Mapping[str, object]
    durable_handback: Mapping[str, object]
    descendant_close_receipts: Sequence[Mapping[str, object]]
    reservation_release_receipts: Sequence[Mapping[str, object]]


def materialize_close_agent_tool_call(
    *,
    run_id: str,
    agent_id: str,
    evidence: CloseAgentLifecycleEvidence,
) -> dict[str, object]:
    """Own G6 by validating closure receipts before issuing the terminal token."""
    handback = validate_durable_handback(evidence.durable_handback)
    checked_binding = validate_record_binding(handback["binding"])
    gates = list(
        validate_gate_chain(
            list(evidence.gate_verdicts),
            expected_gate_ids=("G1", "G2", "G3", "G4", "G5"),
            require_pass=True,
        )
    )
    descendants = [
        validate_descendant_close_receipt(item)
        for item in evidence.descendant_close_receipts
    ]
    reservations = [
        validate_reservation_release_receipt(item)
        for item in evidence.reservation_release_receipts
    ]
    declared_descendants = set(cast(Sequence[str], handback["descendant_ids"]))
    observed_descendants = {cast(str, item["agent_id"]) for item in descendants}
    if observed_descendants != declared_descendants:
        raise ValueError("close_agent:unknown_descendant")
    declared_reservations = set(cast(Sequence[str], handback["reservation_ids"]))
    observed_reservations = {
        cast(str, item["reservation_id"]) for item in reservations
    }
    if observed_reservations != declared_reservations:
        raise ValueError("close_agent:reservation_leak")
    binding_identity_fields = (
        "transaction_id",
        "snapshot_id",
        "candidate_sha",
        "tree_sha",
        "input_digest",
        "tool_id",
        "tool_version",
    )
    expected_identity = tuple(checked_binding[field] for field in binding_identity_fields)
    handback_binding = cast(Mapping[str, object], handback["binding"])
    if handback_binding != checked_binding:
        raise ValueError("close_agent:identity_mismatch")
    if handback["agent_id"] != agent_id:
        raise ValueError("close_agent:agent_identity_mismatch")
    for item in [*descendants, *reservations]:
        item_binding = cast(Mapping[str, object], item["binding"])
        if tuple(item_binding[field] for field in binding_identity_fields) != expected_identity:
            raise ValueError("close_agent:identity_mismatch")
        if item["durable_handback_evidence_ref"] != handback["evidence_ref"]:
            raise ValueError("close_agent:durable_handback_mismatch")
    descendants_closed_evidence_ref = "evidence:" + hashlib.sha256(
        canonical_json_bytes(descendants)
    ).hexdigest()
    reservations_released_evidence_ref = "evidence:" + hashlib.sha256(
        canonical_json_bytes(reservations)
    ).hexdigest()
    cleanup = validate_cleanup_proof(evidence.cleanup_proof)
    cleanup_binding = cast(Mapping[str, object], cleanup["binding"])
    if tuple(cleanup_binding[field] for field in binding_identity_fields) != expected_identity:
        raise ValueError("close_agent:identity_mismatch")
    gate_refs = [
        cast(str, cast(Mapping[str, object], gate["binding"])["evidence_ref"])
        for gate in gates
    ]
    if cleanup["remote_readback_evidence_ref"] != gate_refs[4]:
        raise ValueError("close_agent:cleanup_before_remote_readback")
    g6 = materialize_gate_verdict(
        binding=checked_binding,
        gate_id="G6",
        ordered_input_evidence_refs=[
            *gate_refs,
            cast(str, handback["evidence_ref"]),
            descendants_closed_evidence_ref,
            reservations_released_evidence_ref,
            cast(str, cleanup["evidence_ref"]),
        ],
        invariant="nested_lifecycle_cleanup",
        output_digest="sha256:"
        + hashlib.sha256(
            canonical_json_bytes(
                {
                    "durable_handback": handback,
                    "descendants": descendants,
                    "reservations": reservations,
                    "cleanup": cleanup,
                }
            )
        ).hexdigest(),
        owner=f"{Path(__file__).resolve()}#materialize_close_agent_tool_call",
        verdict="pass",
    )
    token = materialize_lifecycle_close_agent_tool_call(
        binding=checked_binding,
        run_id=run_id,
        agent_id=agent_id,
        gate_verdicts=[*gates, g6],
        cleanup_proof=cleanup,
        durable_handback=handback,
        descendants_closed_evidence_ref=descendants_closed_evidence_ref,
        reservations_released_evidence_ref=reservations_released_evidence_ref,
    )
    return {
        "schema": "agent-canon.close-agent-materialization.v1",
        "g6_gate": g6,
        "descendants_closed_evidence_ref": descendants_closed_evidence_ref,
        "reservations_released_evidence_ref": reservations_released_evidence_ref,
        "close_agent_tool_call": token,
    }


def default_quality_check_role_ids(roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return active role ids that provide the default quality-check path."""
    active_role_ids = {role.id for role in roles}
    return tuple(
        role_id
        for role_id in DEFAULT_QUALITY_CHECK_ROLE_IDS
        if role_id in active_role_ids
    )


def default_quality_check_agent_types(roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return default Codex agent types for active quality-check responsibilities."""
    roles_by_id = {role.id: role for role in roles}
    available_agents = registered_codex_agent_types()
    agent_types: list[str] = []
    for role_id in DEFAULT_QUALITY_CHECK_ROLE_IDS:
        role = roles_by_id.get(role_id)
        if role is None:
            continue
        agent_type = _select_codex_agent_candidate(role, available_agents, {})
        if agent_type is not None and agent_type not in agent_types:
            agent_types.append(agent_type)
    return tuple(agent_types)


def default_quality_check_policy_output_lines(
    roles: tuple[Role, ...],
    *,
    manual_specialists: tuple[str, ...] = (),
    task_default_specialists: tuple[str, ...] = (),
    language_review_candidates: tuple[str, ...] = (),
    default_review_packs_enabled: bool = False,
    default_review_pack_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return machine-readable stdout lines for default quality-check routing."""
    review_pack_state = (
        "active" if default_review_packs_enabled else "candidate_only"
    )
    return (
        "DEFAULT_QUALITY_CHECKS=candidate_only",
        f"DEFAULT_QUALITY_CHECK_SOURCE={DEFAULT_QUALITY_CHECK_POLICY_SOURCE}",
        "DEFAULT_QUALITY_CHECK_ROLE_CANDIDATES="
        f"{','.join(default_quality_check_role_ids(roles)) or '-'}",
        "DEFAULT_QUALITY_CHECK_AGENT_TYPE_CANDIDATES="
        f"{','.join(default_quality_check_agent_types(roles)) or '-'}",
        f"DEFAULT_QUALITY_CHECK_STAGES={','.join(DEFAULT_QUALITY_CHECK_STAGES)}",
        f"DEFAULT_QUALITY_CHECK_EVIDENCE={','.join(OOP_EVIDENCE_DIMENSIONS)}",
        f"DEFAULT_FORMAT_CHECK_ROUTE={CANONICAL_FORMAT_CHECK_ROUTE}",
        f"OFFICIAL_HOOK_DISPATCHER={OFFICIAL_HOOK_DISPATCHER}",
        f"OFFICIAL_HOOK_SCHEMA={OFFICIAL_HOOK_SCHEMA}",
        "DEFAULT_QUALITY_CHECK_TASK_DEFAULT_SPECIALISTS="
        f"{','.join(task_default_specialists) or '-'}",
        "DEFAULT_QUALITY_CHECK_LANGUAGE_REVIEW_CANDIDATES="
        f"{','.join(language_review_candidates) or '-'}",
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


def language_review_candidates(
    workspace_root: Path,
    changed_paths: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return explicit language-review candidates from changed paths."""
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


def _capacity_family_record(
    family: dict[str, object],
) -> capacity_handshake.DeclaredFamilyCapacity:
    """Derive one family capacity record from its declared stage topology."""
    family_id = _as_required_string(family.get("id"), "workflow_family.id")
    roles = _as_object_mapping(cast(object, family.get("roles", {})), "workflow_family.roles")
    declared_roles = set(
        _as_string_tuple(roles.get("always_on"), "workflow_family.roles.always_on")
        + _as_string_tuple(roles.get("specialists"), "workflow_family.roles.specialists")
    )
    topology = _as_object_mapping(
        cast(object, family.get("role_topology", {})),
        "workflow_family.role_topology",
    )
    waves = _as_mapping_tuple(topology.get("stage_waves"), "workflow_family.stage_waves")

    def stage_roles(stage_class: str) -> tuple[str, ...]:
        selected: list[str] = []
        for wave in waves:
            if wave.get("stage_class") != stage_class:
                continue
            for role_id in _as_string_tuple(wave.get("role_ids"), "stage_wave.role_ids"):
                if role_id in declared_roles and role_id not in selected:
                    selected.append(role_id)
        return tuple(selected)

    direct = list(stage_roles("reviewer"))
    isolated = {"skill_evaluator"} & declared_roles
    for role_id in sorted(isolated):
        if role_id not in direct:
            direct.append(role_id)
    nested = stage_roles("producer")
    final = stage_roles("final")
    return capacity_handshake.DeclaredFamilyCapacity(
        workflow_family_id=family_id,
        direct_frontier_role_ids=tuple(direct),
        nested_owner_role_ids=tuple(
            role_id for role_id in nested if role_id not in isolated
        ),
        final_frontier_role_ids=tuple(final),
        direct_frontier_count=len(direct),
        nested_reservation_count=len(tuple(role_id for role_id in nested if role_id not in isolated)),
        final_frontier_count=len(final),
    )


def declared_team_capacity_derivation(
    catalog: TaskCatalog,
) -> capacity_handshake.DeclaredTeamTopologyDerivation:
    """Materialize the canonical topology-derived capacity witness input."""
    return capacity_handshake.DeclaredTeamTopologyDerivation(
        derivation_version=1,
        topology_source="agents/task_catalog.yaml::role_topology_defaults",
        workflow_role_source="agents/task_catalog.yaml::workflow_families[].roles",
        direct_frontier_stage_class="reviewer",
        nested_owner_stage_class="producer",
        final_stage_class="final",
        excluded_nested_role_ids=("skill_evaluator",),
        isolated_direct_role_ids=("skill_evaluator",),
        family_records=tuple(
            _capacity_family_record(family) for family in catalog.workflow_families
        ),
    )


def _capacity_write_scope_cap(
    family: capacity_handshake.DeclaredFamilyCapacity,
) -> int:
    """Derive write capacity from the selected nested owner frontier."""
    return max(1, len(family.nested_owner_role_ids))


def _capacity_topology_witness(
    derivation: capacity_handshake.DeclaredTeamTopologyDerivation,
    target_state_contract_sha256: str = "",
) -> capacity_handshake.TopologyCapacityWitness:
    """Build the serializable topology witness consumed by the handshake owner."""
    nodes: list[capacity_handshake.TopologyCapacityNode] = []
    for family in derivation.family_records:
        family_node = f"workflow:{family.workflow_family_id}"
        nodes.append(
            capacity_handshake.TopologyCapacityNode(
                node_id=family_node,
                node_kind="workflow_family",
                predecessor_ids=(),
                descendant_parent_id=None,
                total_slot_weight=1,
                write_slot_weight=0,
                allowed_write_paths=(),
                exclusion_ids=(),
            )
        )
        for role_id in family.nested_owner_role_ids:
            nodes.append(
                capacity_handshake.TopologyCapacityNode(
                    node_id=f"{family_node}:{role_id}",
                    node_kind="descendant",
                    predecessor_ids=(family_node,),
                    descendant_parent_id=family_node,
                    total_slot_weight=1,
                    write_slot_weight=1,
                    allowed_write_paths=(f"role:{role_id}",),
                    exclusion_ids=(),
                )
            )
    peak = derivation.peak_family
    requested = derivation.requested_max_threads()
    write_cap = _capacity_write_scope_cap(peak)
    proof_payload = {
        "families": [
            {
                "id": family.workflow_family_id,
                "direct": list(family.direct_frontier_role_ids),
                "nested": list(family.nested_owner_role_ids),
                "final": list(family.final_frontier_role_ids),
            }
            for family in derivation.family_records
        ],
        "requested_total_capacity": requested,
        "write_scope_cap": write_cap,
    }
    proof_sha256 = hashlib.sha256(
        json.dumps(proof_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return capacity_handshake.TopologyCapacityWitness(
        target_state_contract_sha256=target_state_contract_sha256,
        declared_team_topology_ref="agents/task_catalog.yaml",
        declared_team_topology_sha256=proof_sha256,
        node_records=tuple(nodes),
        legal_frontier_ids=tuple(node.node_id for node in nodes),
        peak_frontier_node_ids=tuple(
            f"workflow:{peak.workflow_family_id}:{role_id}"
            for role_id in peak.direct_frontier_role_ids
        ),
        peak_write_frontier_node_ids=tuple(
            f"workflow:{peak.workflow_family_id}:{role_id}"
            for role_id in peak.nested_owner_role_ids
        ),
        requested_total_capacity=requested,
        workflow_dag_peak_demand=peak.direct_frontier_count,
        nested_reservation_count=peak.nested_reservation_count,
        workflow_dag_budget=peak.direct_frontier_count,
        write_scope_cap=write_cap,
        derivation=derivation,
    )


def capacity_runtime_for_spec(spec: RunBundleSpec) -> _CapacityRuntime:
    """Create one provider-owned ledger and snapshot for a run bundle."""
    if spec.task_catalog is None:
        raise RuntimeError("task catalog is required for capacity handshake")
    derivation = declared_team_capacity_derivation(spec.task_catalog)
    witness = _capacity_topology_witness(derivation)
    config_path = spec.workspace_root / ".codex" / "config.toml"
    contract = capacity_handshake.load_startup_contract(
        derivation,
        witness,
        config_path=str(config_path),
        contract_id=f"capacity:{spec.run_id}",
    )
    peak = derivation.peak_family
    write_cap = _capacity_write_scope_cap(peak)
    snapshot = capacity_handshake.make_session_snapshot(
        contract=contract,
        requested_capacity=witness.requested_total_capacity,
        configured_max_threads=contract.input_evidence.max_threads_loader.configured_max_threads,
        workflow_dag_demand=peak.direct_frontier_count,
        nested_capacity_reservation=peak.nested_reservation_count,
        write_scope_cap=write_cap,
        requested_write_capacity=write_cap,
        workflow_dag_write_demand=write_cap,
    )
    parent_lineage_id = spec.parent_lineage_id or f"run:{spec.run_id}"
    ledger = capacity_handshake.CapacityLedger(
        topology=capacity_handshake.DescendantTopologyReadback(parent_work_id=spec.run_id)
    )
    return _CapacityRuntime(
        binding=CapacityHandshakeConsumerBinding(),
        snapshot=snapshot,
        ledger=ledger,
        parent_lineage_id=parent_lineage_id,
        topology_proof_sha256=witness.declared_team_topology_sha256,
        requested_capacity=witness.requested_total_capacity,
        write_scope_cap=write_cap,
    )


def _json_capacity_record(record: capacity_handshake.DescendantLifecycleRecord) -> dict[str, object]:
    return {
        "work_id": record.work_id,
        "parent_work_id": record.parent_work_id,
        "profile_id": record.profile_id,
        "status": record.status.value,
        "durable_result_evidence_ref": record.durable_result_evidence_ref,
        "durable_handback": record.durable_handback,
        "descendants_closed": record.descendants_closed,
        "close_readback": record.close_readback,
        "reserved_slots": record.reserved_slots,
        "reserved_write_slots": record.reserved_write_slots,
        "transition_generation": record.transition_generation,
    }


def _capacity_projection(runtime: _CapacityRuntime, spec: RunBundleSpec) -> dict[str, object]:
    """Return the machine-readable manifest projection for shared runtime state."""
    configured = runtime.snapshot.configured_max_threads
    return {
        "schema_id": "team_manifest_capacity_request_v1",
        "requested_total_capacity": runtime.requested_capacity,
        "effective_total_capacity": runtime.snapshot.effective_total_capacity,
        "available_total_capacity": runtime.snapshot.available_total_capacity,
        "requested_write_capacity": runtime.snapshot.requested_write_capacity,
        "effective_write_capacity": runtime.snapshot.effective_write_capacity,
        "available_write_capacity": runtime.snapshot.available_write_capacity,
        "topology_proof_ref": "agents/task_catalog.yaml",
        "topology_proof_sha256": runtime.topology_proof_sha256,
        "capacity_policy_ref": "agents/capacity_policy.toml",
        "capacity_policy_sha256": runtime.snapshot.contract.capacity_policy.topology_proof_sha256,
        "loader_evidence_ref": runtime.snapshot.contract.input_evidence.max_threads_loader.evidence_ref,
        "configured_max_threads_loader_value": configured,
        "reload_state": "restart_required" if configured != runtime.requested_capacity else "current",
        "requested_capacity_loader_status": "completed",
        "input_provenance": [
            {
                "input_id": item.input_id,
                "value": item.value,
                "source_ref": item.source_ref,
                "loader_id": item.loader_id,
                "readback_value": item.readback_value,
                "status": item.status,
            }
            for item in runtime.snapshot.input_provenance
        ],
        "parent_lineage_id": runtime.parent_lineage_id,
        "ledger_ref": f"runtime://ledger/{spec.run_id}",
        "capacity_handshake_binding": {
            "shape_id": runtime.binding.shape_id,
            "binding_version": runtime.binding.binding_version,
            "provider_owner_id": runtime.binding.provider_owner_id,
            "consumer_owner_ids": list(runtime.binding.consumer_owner_ids),
            "allowed_api_ids": list(runtime.binding.allowed_api_ids),
            "provider_type_ids": list(runtime.binding.provider_type_ids),
            "duplicate_definition_policy": runtime.binding.duplicate_definition_policy,
        },
        "ledger": {
            "shape_id": runtime.ledger.shape_id,
            "parent_work_id": runtime.ledger.topology.parent_work_id,
            "descendants": [_json_capacity_record(record) for record in runtime.ledger.topology.descendants],
            "reservations": [
                {"parent_work_id": edge.parent_work_id, "child_work_id": edge.child_work_id}
                for edge in runtime.ledger.reservations.values()
            ],
            "ready_queue": [],
        },
        "lineage": {
            "parent_lineage_id": runtime.parent_lineage_id,
            "ancestor_agent_ids": [],
            "run_id": spec.run_id,
            "work_id": spec.run_id,
            "role_ids": [role.id for role in spec.roles],
        },
    }


def _closeout_projection(
    runtime: _CapacityRuntime,
    spec: RunBundleSpec,
) -> dict[str, object]:
    """Materialize the provider closeout state with canonical close-agent tokens."""
    tokens: dict[str, dict[str, object]] = {}
    registry = model_profile_registry.load_model_profile_registry(spec.workspace_root)
    for record in runtime.ledger.topology.descendants:
        if record.status not in {
            capacity_handshake.LifecycleStatus.READBACK_VERIFIED,
            capacity_handshake.LifecycleStatus.RESERVATION_RELEASED,
        }:
            continue
        if not record.profile_id:
            raise RuntimeError(f"closeout record lacks profile identity: {record.work_id}")
        token = model_profile_registry.materialize_tool_call_token(
            model_profile_registry.ToolCallMaterializationRequest(
                profile_id=record.profile_id,
                terminal_agent_id=record.work_id,
            ),
            record.profile_id,
            registry,
        )
        token_projection = {
            "tool_id": token.tool_id,
            "arguments": dict(token.arguments),
        }
        tokens[record.work_id] = token_projection
    provider_packet = capacity_handshake.materialize_closeout_packet(
        parent_work_id=spec.run_id,
        ledger=runtime.ledger,
        descendants=(runtime.ledger.topology,),
        close_agent_tokens=tokens,
    )
    calls = [
        {
            "agent_id": call.work_id,
            "tool_call_token": dict(call.close_agent_call_token),
        }
        for call in provider_packet.close_agent_calls
    ]
    failures = [
        {"work_id": failure.work_id, "detail": failure.detail}
        for failure in provider_packet.failures
    ]
    return {
        "schema_id": "closeout_tool_call_projection_v1",
        "parent_work_id": spec.run_id,
        "parent_lineage_id": runtime.parent_lineage_id,
        "ledger_ref": f"runtime://ledger/{spec.run_id}",
        "close_agent_tool_calls": calls,
        "failures": failures,
        "status": "completed" if not failures else "failed",
        "natural_language_intent": "close terminal descendants in postorder and release reservations after readback",
    }


def dispatch_fixed_implementation(
    request: Mapping[str, object] | implementation_route.ImplementationRouteRequest,
    objective: str,
    spawn: Callable[[str, str], str | None],
    *,
    workspace_root: Path = ROOT,
    capacity_runtime: _CapacityRuntime | None = None,
) -> ImplementationDispatch:
    """Route, materialize, and launch exactly one fixed Spark implementation worker."""
    route_result = implementation_route.route_implementation(request)
    if route_result.status == "blocked":
        return ImplementationDispatch(route_result, None, None, None, route_result.next_gate, 1, 0, "blocked")
    if route_result.status == "queued":
        return ImplementationDispatch(route_result, None, None, None, route_result.next_gate, 1, 0, "queued")
    if (
        route_result.selected_agent_type != "spark_worker"
        or route_result.selected_profile_id != "spark_implementation_low"
        or route_result.failure is not None
    ):
        raise RuntimeError("implementation_dispatch:fixed_route_violation")
    if isinstance(request, implementation_route.ImplementationRouteRequest):
        packet_payload: object = request.fixed_implementation_packet
    else:
        packet_payload = request.get("fixed_implementation_packet")
    if is_dataclass(packet_payload):
        packet_context = asdict(packet_payload)
    elif isinstance(packet_payload, Mapping):
        packet_context = dict(packet_payload)
    else:
        raise RuntimeError("implementation_dispatch:fixed_packet_missing")
    registry = model_profile_registry.load_model_profile_registry(workspace_root)
    prompt = model_profile_registry.materialize_prompt_capsule(
        model_profile_registry.PromptMaterializationRequest(
            profile_id=route_result.selected_profile_id,
            role_id="spark_worker",
            context=(
                model_profile_registry.ContextItem("objective", objective),
                model_profile_registry.ContextItem("context", "fixed_packet_direct_materialization"),
                model_profile_registry.ContextItem("fixed_implementation_packet", packet_context),
                model_profile_registry.ContextItem("implementation_route_result", asdict(route_result)),
                model_profile_registry.ContextItem("owner_gate", route_result.next_gate),
            ),
            objective=objective,
        ),
        registry,
    )
    if route_result.capacity_action == "continue_existing":
        worker_agent_id = route_result.resume_worker_agent_id
        spawn_count = 0
        status = "continued"
    else:
        planned_id = f"{route_result.packet_sha256}:spark"
        item = capacity_handshake.ReadyWorkItem(
            work_id=planned_id,
            packet_sha256=route_result.packet_sha256 or "",
            profile_id=route_result.selected_profile_id,
            required_slots=1,
            required_write_slots=1,
            model=registry.by_profile(route_result.selected_profile_id).model,
        )
        if capacity_runtime is not None:
            readiness = capacity_handshake.request_slot(capacity_runtime.snapshot, capacity_runtime.ledger, item)
            if readiness.status != "ready":
                return ImplementationDispatch(route_result, prompt, None, None, route_result.next_gate, 1, 0, "queued")
        worker_agent_id = spawn("spark_worker", prompt.body)
        spawn_count = 1
        if not worker_agent_id:
            if capacity_runtime is not None:
                capacity_handshake.record_successful_spawn(
                    capacity_runtime.snapshot,
                    capacity_runtime.ledger,
                    item,
                    spawn_succeeded=False,
                )
            return ImplementationDispatch(route_result, prompt, None, None, route_result.next_gate, 1, spawn_count, "queued")
        if capacity_runtime is not None:
            spawned_item = capacity_handshake.ReadyWorkItem(
                work_id=worker_agent_id,
                packet_sha256=item.packet_sha256,
                profile_id=item.profile_id,
                required_slots=item.required_slots,
                required_write_slots=item.required_write_slots,
                model=item.model,
            )
            capacity_handshake.record_successful_spawn(
                capacity_runtime.snapshot,
                capacity_runtime.ledger,
                spawned_item,
                spawn_succeeded=True,
            )
        status = "spawned"
    if not worker_agent_id:
        raise RuntimeError("implementation_dispatch:worker_identity_missing")
    token = model_profile_registry.materialize_tool_call_token(
        model_profile_registry.ToolCallMaterializationRequest(
            route_result.selected_profile_id,
            worker_agent_id,
        ),
        route_result.selected_profile_id,
        registry,
    )
    return ImplementationDispatch(
        route_result,
        prompt,
        token,
        worker_agent_id,
        route_result.next_gate,
        1,
        spawn_count,
        status,
    )


def capacity_manifest_output_lines(
    spec: RunBundleSpec,
    runtime: _CapacityRuntime | None = None,
) -> tuple[str, ...]:
    """Return task-start/bootstrap fields projected from one typed capacity runtime."""
    runtime = runtime or capacity_runtime_for_spec(spec)
    projection = _capacity_projection(runtime, spec)
    return (
        "CAPACITY_REQUEST_SCHEMA=team_manifest_capacity_request_v1",
        f"REQUESTED_TOTAL_CAPACITY={projection['requested_total_capacity']}",
        f"CAPACITY_TOPOLOGY_PROOF_REF={projection['topology_proof_ref']}",
        f"CAPACITY_TOPOLOGY_PROOF_SHA256={projection['topology_proof_sha256']}",
        f"CAPACITY_POLICY_REF={projection['capacity_policy_ref']}",
        f"CAPACITY_LOADER_EVIDENCE_REF={projection['loader_evidence_ref']}",
        f"CAPACITY_RELOAD_STATE={projection['reload_state']}",
        f"PARENT_LINEAGE_ID={runtime.parent_lineage_id}",
        f"CAPACITY_LEDGER_REF={projection['ledger_ref']}",
    )


def capacity_start_output_lines(
    catalog: TaskCatalog,
    workspace_root: Path,
    run_id: str,
) -> tuple[str, ...]:
    """Return startup fields from the same topology-derived capacity owner."""
    derivation = declared_team_capacity_derivation(catalog)
    witness = _capacity_topology_witness(derivation)
    contract = capacity_handshake.load_startup_contract(
        derivation,
        witness,
        config_path=str(workspace_root / ".codex" / "config.toml"),
        contract_id=f"capacity:{run_id}",
    )
    configured = contract.input_evidence.max_threads_loader.configured_max_threads
    parent_lineage_id = f"run:{run_id}"
    reload_state = "restart_required" if configured != witness.requested_total_capacity else "current"
    return (
        "CAPACITY_REQUEST_SCHEMA=team_manifest_capacity_request_v1",
        f"REQUESTED_TOTAL_CAPACITY={witness.requested_total_capacity}",
        "CAPACITY_TOPOLOGY_PROOF_REF=agents/task_catalog.yaml",
        f"CAPACITY_TOPOLOGY_PROOF_SHA256={witness.declared_team_topology_sha256}",
        "CAPACITY_POLICY_REF=agents/capacity_policy.toml",
        "CAPACITY_POLICY_DIGEST="
        f"{contract.capacity_policy.topology_proof_sha256}",
        "CAPACITY_LOADER_EVIDENCE_REF="
        f"{contract.input_evidence.max_threads_loader.evidence_ref}",
        f"CAPACITY_LOADED_CONFIGURED_VALUE={configured}",
        f"CAPACITY_RELOAD_STATE={reload_state}",
        f"PARENT_LINEAGE_ID={parent_lineage_id}",
        f"CAPACITY_LEDGER_REF=runtime://ledger/{run_id}",
    )


def workflow_spawn_budget(catalog: TaskCatalog, family_id: str) -> tuple[int, int]:
    """Return the active and write-capable spawn budget for one workflow family."""
    derivation = declared_team_capacity_derivation(catalog)
    family = next(
        record for record in derivation.family_records if record.workflow_family_id == family_id
    )
    return family.workflow_thread_request, _capacity_write_scope_cap(family)


def workflow_topology_policy_violations(
    catalog: TaskCatalog,
) -> tuple[tuple[str, str], ...]:
    """Return lean-topology violations without duplicating catalog role lists."""
    owner_bounded_always_on = ("manager", "implementer", "verifier", "auditor")
    delivery_always_on = (
        "manager",
        "designer",
        "implementer",
        "verifier",
        "auditor",
    )
    deferred_delivery_reviews = {
        "manager_reviewer",
        "design_reviewer",
        "document_flow_reviewer",
        "change_reviewer",
        "final_reviewer",
    }
    violations: list[tuple[str, str]] = []
    for family in catalog.workflow_families:
        family_id = family.get("id")
        if not isinstance(family_id, str):
            violations.append(("<unknown>", "missing-family-id"))
            continue
        roles_raw = family.get("roles")
        if not isinstance(roles_raw, dict):
            violations.append((family_id, "malformed-roles"))
            continue
        roles = cast(dict[str, object], roles_raw)
        always_on_raw = roles.get("always_on")
        specialists_raw = roles.get("specialists")
        if not isinstance(always_on_raw, list) or not all(
            isinstance(role_id, str)
            for role_id in cast(list[object], always_on_raw)
        ):
            violations.append((family_id, "malformed-always-on"))
            continue
        if not isinstance(specialists_raw, list) or not all(
            isinstance(role_id, str)
            for role_id in cast(list[object], specialists_raw)
        ):
            violations.append((family_id, "malformed-specialists"))
            continue
        always_on = tuple(cast(list[str], always_on_raw))
        specialists = tuple(cast(list[str], specialists_raw))
        if len(always_on) != len(set(always_on)) or len(specialists) != len(
            set(specialists)
        ):
            violations.append((family_id, "duplicate-role-id"))
        if set(always_on) & set(specialists):
            violations.append((family_id, "always-on-specialist-overlap"))
        if family_id != "skill_evaluation" and "skill_evaluator" in (
            *always_on,
            *specialists,
        ):
            violations.append((family_id, "skill-evaluator-only-in-skill-evaluation"))

        if family_id == "skill_evaluation":
            if always_on or specialists != ("skill_evaluator",):
                violations.append((family_id, "evaluator-only-topology"))
        elif family_id == "owner_bounded_change":
            if always_on != owner_bounded_always_on:
                violations.append((family_id, "owner-bounded-producer-core"))
            if "change_reviewer" not in specialists:
                violations.append((family_id, "change-reviewer-not-deferred"))
        else:
            if always_on != delivery_always_on:
                violations.append((family_id, "delivery-producer-core"))
            missing_reviews = deferred_delivery_reviews - set(specialists)
            if missing_reviews:
                violations.append((family_id, "reviewers-not-deferred"))
        active_budget, write_budget = workflow_spawn_budget(catalog, family_id)
        if active_budget < 1 or write_budget < 1 or write_budget > active_budget:
            violations.append((family_id, "derived-spawn-budget"))
    return tuple(violations)


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


def parse_agent_type_selections(raw_values: tuple[str, ...]) -> tuple[AgentTypeSelection, ...]:
    """Parse explicit role-to-agent selections from parent-packet CLI values."""
    selections: list[AgentTypeSelection] = []
    for raw_value in raw_values:
        role_id, has_role_separator, remainder = raw_value.partition("=")
        agent_type, has_evidence_separator, evidence = remainder.partition(":")
        if (
            not has_role_separator
            or not has_evidence_separator
            or not role_id.strip()
            or not agent_type.strip()
            or not evidence.strip()
        ):
            raise RuntimeError(
                "agent type selections must use ROLE_ID=AGENT_TYPE:EVIDENCE"
            )
        selections.append(
            AgentTypeSelection(
                role_id=role_id.strip(),
                agent_type=agent_type.strip(),
                evidence=evidence.strip(),
            )
        )
    return tuple(selections)


def format_agent_type_selections(selections: tuple[AgentTypeSelection, ...]) -> str:
    """Render explicit role-to-agent selections for stdout."""
    if not selections:
        return "none"
    return ",".join(
        f"{selection.role_id}={selection.agent_type}:{selection.evidence}"
        for selection in selections
    )


def validate_agent_type_selections(
    config: TeamConfig,
    active_roles: tuple[Role, ...],
    selections: tuple[AgentTypeSelection, ...],
    registered_agents: set[str] | None = None,
) -> tuple[AgentTypeSelection, ...]:
    """Validate explicit non-default candidate selections against active roles."""
    if not selections:
        return ()
    configured_roles = {
        role.id: role for role in config.always_on_roles + config.specialist_roles
    }
    active_roles_by_id = {role.id: role for role in active_roles}
    available_agents = (
        registered_codex_agent_types()
        if registered_agents is None
        else registered_agents
    )
    seen_roles: set[str] = set()
    for selection in selections:
        if selection.role_id in seen_roles:
            raise RuntimeError(
                f"duplicate agent type selection for role: {selection.role_id}"
            )
        seen_roles.add(selection.role_id)
        role = configured_roles.get(selection.role_id)
        if role is None:
            raise RuntimeError(
                f"agent type selection references unknown role: {selection.role_id}"
            )
        if selection.role_id not in active_roles_by_id:
            raise RuntimeError(
                f"agent type selection references inactive role: {selection.role_id}"
            )
        if selection.agent_type not in role.codex_agents:
            raise RuntimeError(
                f"agent type selection for {selection.role_id} must be one of "
                f"{','.join(role.codex_agents)}"
            )
        if selection.agent_type not in available_agents:
            raise RuntimeError(
                f"agent type selection references unregistered Codex agent: {selection.agent_type}"
            )
    return selections


def agent_type_selection_map(
    selections: tuple[AgentTypeSelection, ...],
) -> dict[str, AgentTypeSelection]:
    """Return validated selections keyed by role id."""
    return {selection.role_id: selection for selection in selections}


def catalog_stage_waves(catalog: TaskCatalog) -> tuple[StageWave, ...]:
    """Return catalog-owned role topology stages."""
    topology = _as_object_mapping(
        catalog.raw.get("role_topology_defaults"),
        "role_topology_defaults",
    )
    waves = _as_mapping_tuple(topology.get("stage_waves"), "role_topology_defaults.stage_waves")
    return tuple(
        StageWave(
            id=_as_required_string(wave.get("id"), "stage_waves[].id"),
            stage_class=_as_required_string(
                wave.get("stage_class"),
                "stage_waves[].stage_class",
            ),
            role_ids=_as_string_tuple(wave.get("role_ids"), "stage_waves[].role_ids"),
        )
        for wave in waves
    )


def _select_codex_agent_candidate(
    role: Role,
    available_agents: set[str],
    selections: dict[str, AgentTypeSelection],
) -> str | None:
    """Select the executable Codex agent candidate for one active role."""
    if role.id != "skill_evaluator" and "skill_evaluator" in role.codex_agents:
        raise RuntimeError(
            f"{role.id} codex_agents must not include skill_evaluator; "
            "the evaluator candidate is reserved for the skill_evaluator role"
        )
    selection = selections.get(role.id)
    if selection is not None:
        if selection.agent_type not in role.codex_agents:
            raise RuntimeError(
                f"agent type selection for {role.id} must be one of "
                f"{','.join(role.codex_agents)}"
            )
        if selection.agent_type not in available_agents:
            raise RuntimeError(
                f"agent type selection references unregistered Codex agent: {selection.agent_type}"
            )
        return selection.agent_type
    return next(
        (
            agent_type
            for agent_type in role.codex_agents
            if agent_type in available_agents
        ),
        None,
    )


def _materialize_stage_wave_slots(
    roles_by_id: dict[str, Role],
    role_ids: tuple[str, ...],
    available_agents: set[str],
    used_role_ids: set[str],
    selections: dict[str, AgentTypeSelection],
) -> tuple[SubagentWaveSlot, ...]:
    """Return one default executable slot for each active role in the stage."""
    slots: list[SubagentWaveSlot] = []
    for role_id in role_ids:
        role = roles_by_id.get(role_id)
        if role is None or role.id in used_role_ids:
            continue
        agent_type = _select_codex_agent_candidate(role, available_agents, selections)
        if agent_type is None:
            continue
        slots.append(
            SubagentWaveSlot(
                role_id=role.id,
                instance_id=f"{role.id}_{agent_type}",
                agent_type=agent_type,
            )
        )
    return tuple(slots)


def _initial_stage_wave_slots(
    roles: tuple[Role, ...],
    active_subagents: int,
    catalog: TaskCatalog,
    agent_type_selections: tuple[AgentTypeSelection, ...] = (),
    agent_root: Path = CODEX_AGENT_ROOT,
) -> tuple[SubagentWaveSlot, ...]:
    """Return intake-stage slots derived from active roles and catalog topology."""
    if active_subagents < 1:
        return ()
    stage_waves = catalog_stage_waves(catalog)
    roles_by_id = {role.id: role for role in roles}
    stage_id = (
        "skill_evaluation"
        if "skill_evaluator" in roles_by_id and "manager" not in roles_by_id
        else "intake"
    )
    intake_wave = next((wave for wave in stage_waves if wave.id == stage_id), None)
    if intake_wave is None:
        raise RuntimeError(
            f"role_topology_defaults.stage_waves must include {stage_id} stage"
        )
    available_agents = registered_codex_agent_types(agent_root)
    selections = agent_type_selection_map(agent_type_selections)
    slots = _materialize_stage_wave_slots(
        roles_by_id,
        intake_wave.role_ids,
        available_agents,
        set(),
        selections,
    )
    return tuple(
        slot
        for slot in slots
        if slot.role_id not in {"verifier", "auditor"}
    )[:active_subagents]


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
    catalog: TaskCatalog,
    agent_type_selections: tuple[AgentTypeSelection, ...] = (),
    agent_root: Path = CODEX_AGENT_ROOT,
) -> tuple[str, ...]:
    """Return executable agent_type values for active catalog intake roles."""
    return tuple(
        slot.agent_type
        for slot in _initial_stage_wave_slots(
            roles,
            active_subagents,
            catalog,
            agent_type_selections,
            agent_root,
        )
    )


def recommended_dynamic_expansion_waves(
    roles: tuple[Role, ...],
    active_subagents: int,
    initial_wave: tuple[str, ...],
    catalog: TaskCatalog,
    agent_type_selections: tuple[AgentTypeSelection, ...] = (),
    agent_root: Path = CODEX_AGENT_ROOT,
) -> tuple[tuple[str, ...], ...]:
    """Return executable follow-up stage waves inside the active budget."""
    return tuple(
        tuple(slot.agent_type for slot in wave)
        for wave in recommended_dynamic_expansion_wave_slots(
            roles,
            active_subagents,
            initial_wave,
            catalog,
            agent_type_selections,
            agent_root,
        )
    )


def recommended_dynamic_expansion_wave_slots(
    roles: tuple[Role, ...],
    active_subagents: int,
    initial_wave: tuple[str, ...],
    catalog: TaskCatalog,
    agent_type_selections: tuple[AgentTypeSelection, ...] = (),
    agent_root: Path = CODEX_AGENT_ROOT,
) -> tuple[tuple[SubagentWaveSlot, ...], ...]:
    """Return executable follow-up role-instance waves inside the active budget."""
    initial_slots = _initial_stage_wave_slots(
        roles,
        active_subagents,
        catalog,
        agent_type_selections,
        agent_root,
    )
    expected_initial_wave = tuple(slot.agent_type for slot in initial_slots)
    if initial_wave != expected_initial_wave:
        raise RuntimeError(
            "initial_wave does not match target registry materialization: "
            f"expected {expected_initial_wave}, got {initial_wave}"
        )
    if active_subagents < 1:
        return ()
    initial_role_ids = {slot.role_id for slot in initial_slots}
    available_agents = registered_codex_agent_types(agent_root)
    roles_by_id = {role.id: role for role in roles}
    stage_waves = catalog_stage_waves(catalog)
    selections = agent_type_selection_map(agent_type_selections)
    used_role_ids: set[str] = set()
    waves: list[tuple[SubagentWaveSlot, ...]] = []
    for stage_wave in stage_waves:
        stage_slots = _materialize_stage_wave_slots(
            roles_by_id,
            stage_wave.role_ids,
            available_agents,
            used_role_ids,
            selections,
        )
        stage_slots = tuple(
            slot
            for slot in stage_slots
            if slot.role_id not in NON_SPAWN_WAVE_ROLE_IDS
            and slot.role_id not in initial_role_ids
        )
        used_role_ids.update(slot.role_id for slot in stage_slots)
        waves.extend(_chunk_wave_slots(stage_slots, active_subagents))
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
            slot.executable_identity for slot in wave
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
        all_roles = config.always_on_roles + config.specialist_roles
        if workflow_family_id == "skill_evaluation":
            return tuple(role for role in all_roles if role.id == "skill_evaluator")
        return tuple(role for role in all_roles if role.id != "skill_evaluator")
    always_on_roles = workflow_always_on_roles(config, catalog, workflow_family_id)
    enabled_roles = tuple(resolve_role(config, name) for name in enabled_specialists)
    selected_roles = list(always_on_roles)
    selected_ids = {role.id for role in selected_roles}
    for role in enabled_roles:
        if role.id not in selected_ids:
            selected_roles.append(role)
            selected_ids.add(role.id)
    enabled_set = {role.id for role in enabled_roles}
    selected_specialists = tuple(
        role
        for role in config.specialist_roles
        if role.id in enabled_set
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
    if "always_on" not in family_roles:
        return config.always_on_roles
    role_ids = _as_string_tuple(
        family_roles.get("always_on"),
        f"workflow_families[{workflow_family_id}].roles.always_on",
    )
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


def active_design_packet_artifact_map(
    config: TeamConfig,
    packet: ActiveDesignPacketConfig,
) -> dict[str, str]:
    """Map canonical design artifact names to the selected packet outputs."""
    return {
        config.artifacts["design_brief"]: packet.design_artifact,
        config.artifacts["design_review"]: packet.design_review_artifact,
        config.artifacts["document_flow_review"]: packet.document_flow_review_artifact,
    }


def selected_role_outputs(
    config: TeamConfig,
    role: Role,
    packet: ActiveDesignPacketConfig,
) -> tuple[str, ...]:
    """Return role outputs aligned with the selected design packet."""
    artifact_map = active_design_packet_artifact_map(config, packet)
    return tuple(artifact_map.get(output, output) for output in role.required_outputs)


def selected_artifact_name(
    config: TeamConfig,
    artifact_key: str,
    packet: ActiveDesignPacketConfig,
) -> str:
    """Resolve one logical artifact key through the selected packet."""
    artifact_name = config.artifacts[artifact_key]
    return active_design_packet_artifact_map(config, packet).get(
        artifact_name,
        artifact_name,
    )


def iter_artifacts(
    config: TeamConfig,
    roles: tuple[Role, ...],
    active_design_packet: ActiveDesignPacketConfig | None = None,
) -> tuple[str, ...]:
    """Return unique artifact filenames in deterministic order."""
    packet = active_design_packet or resolve_active_design_packet_config(config)
    return tuple(
        dict.fromkeys(
            (
                *(config.artifacts[key] for key in STANDARD_RUN_ARTIFACT_KEYS),
                packet.design_artifact,
                packet.design_review_artifact,
                packet.document_flow_review_artifact,
                *(
                    output
                    for role in roles
                    for output in selected_role_outputs(config, role, packet)
                ),
            )
        )
    )


def resolve_role_document_packet(
    config: TeamConfig,
    role: Role,
    report_dir: Path,
    workspace_root: Path,
    active_design_packet: ActiveDesignPacketConfig | None = None,
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
    active_packet = active_design_packet or resolve_active_design_packet_config(config)
    active_packet_paths = {
        "design_brief": active_packet.design_artifact,
        "design_review": active_packet.design_review_artifact,
        "document_flow_review": active_packet.document_flow_review_artifact,
    }

    def add_entry(entry: DocumentPacketEntry) -> None:
        resolved_path = entry.path.resolve()
        if resolved_path in seen_paths:
            return
        seen_paths.add(resolved_path)
        entries.append(
            DocumentPacketEntry(
                path=resolved_path,
                rationale=entry.rationale,
                sections=entry.sections,
            )
        )

    for artifact_key in artifact_keys:
        if artifact_key in active_packet_paths:
            add_entry(
                DocumentPacketEntry(
                    path=resolve_report_bundle_artifact_path(
                        report_dir,
                        active_packet_paths[artifact_key],
                    ),
                    rationale=(
                        f"run artifact:{artifact_key}; "
                        "source=run.active_design_packet"
                    ),
                )
            )
            continue
        if artifact_key not in config.artifacts:
            raise RuntimeError(
                f"document packet artifact key missing for role {role.id}: {artifact_key}"
            )
        add_entry(
            DocumentPacketEntry(
                path=resolve_report_bundle_artifact_path(
                    report_dir,
                    config.artifacts[artifact_key],
                ),
                rationale=f"run artifact:{artifact_key}",
            )
        )
    for relative_path in workspace_paths:
        resolved_path = resolve_workspace_document_path(workspace_root, relative_path)
        add_entry(
            DocumentPacketEntry(
                path=resolved_path,
                rationale=f"workspace doc:{relative_path}",
                sections=resolve_document_section_locators(
                    role.id,
                    relative_path,
                    resolved_path,
                ),
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


def markdown_heading_anchor(heading: str) -> str:
    """Return the stable markdown anchor for one exact heading."""
    lowered = heading.strip().lower()
    stripped = re.sub(r"[^\w\s.-]", "", lowered, flags=re.UNICODE)
    dashed = re.sub(r"\s+", "-", stripped)
    return dashed.strip("-")


def markdown_document_headings(path: Path) -> tuple[str, ...]:
    """Return exact markdown heading text without leading hash marks."""
    if not path.exists():
        return ()
    headings: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match is not None:
            headings.append(match.group(2).strip())
    return tuple(headings)


def resolve_document_section_locators(
    role_id: str,
    relative_path: str,
    resolved_path: Path,
) -> tuple[DocumentSectionLocator, ...]:
    """Return validated section locators for one role document path."""
    requested_headings = ROLE_DOCUMENT_PACKET_SECTION_SPECS.get(role_id, {}).get(
        relative_path,
        (),
    )
    if not requested_headings:
        return ()
    headings = set(markdown_document_headings(resolved_path))
    locators: list[DocumentSectionLocator] = []
    for heading in requested_headings:
        if heading not in headings:
            raise RuntimeError(
                f"section_locator_heading_missing:{resolved_path}:{heading}"
            )
        locators.append(
            DocumentSectionLocator(
                heading=heading,
                anchor=markdown_heading_anchor(heading),
                required=True,
            )
        )
    return tuple(locators)


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


def run_workflow_family(spec: RunBundleSpec) -> dict[str, object] | None:
    """Resolve the selected workflow family for one run specification."""
    if not spec.workflow_family_id:
        return None
    if spec.task_catalog is None:
        raise RuntimeError("task catalog is required for workflow manifest rendering")
    return resolve_workflow_family(spec.task_catalog, spec.workflow_family_id)


def run_active_design_packet(
    spec: RunBundleSpec,
    workflow_family: Mapping[str, object] | None = None,
) -> ActiveDesignPacketConfig:
    """Resolve explicit run, workflow, or registry packet precedence."""
    if spec.active_design_packet is not None:
        return spec.active_design_packet
    selected_workflow = workflow_family if workflow_family is not None else run_workflow_family(spec)
    return resolve_active_design_packet_config(
        spec.config,
        workflow_family=selected_workflow,
    )


def create_run_bundle(spec: RunBundleSpec) -> tuple[str, ...]:
    """Create the standard files for a run."""
    replacements = {
        "RUN_ID": spec.run_id,
        "TASK": spec.task,
        "OWNER": spec.owner,
        "CREATED_AT": spec.created_at_iso,
    }
    capacity_runtime = capacity_runtime_for_spec(spec)
    spec.report_dir.mkdir(parents=True, exist_ok=True)
    active_design_packet = run_active_design_packet(spec)
    created_files = list(iter_artifacts(spec.config, spec.roles, active_design_packet))
    selected_templates = {
        active_design_packet.design_artifact: spec.config.artifacts["design_brief"],
        active_design_packet.design_review_artifact: spec.config.artifacts["design_review"],
        active_design_packet.document_flow_review_artifact: spec.config.artifacts[
            "document_flow_review"
        ],
    }
    for artifact in created_files:
        template_name = selected_templates.get(artifact, artifact)
        if has_template(template_name):
            output_path = resolve_report_bundle_artifact_path(spec.report_dir, artifact)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                render_template(template_name, replacements),
                encoding="utf-8",
            )
    (spec.report_dir / spec.config.artifacts["team_manifest"]).write_text(
        build_manifest(spec, capacity_runtime),
        encoding="utf-8",
    )
    (spec.report_dir / "closeout_packet.json").write_text(
        json.dumps(
            {
                "capacity_request": _capacity_projection(capacity_runtime, spec),
                "closeout_packet": _closeout_projection(capacity_runtime, spec),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    created_files.append("closeout_packet.json")
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
    if spec.task_catalog is None:
        raise RuntimeError("task catalog is required for initial wave materialization")
    active_subagents, _max_write_subagents = workflow_spawn_budget(
        spec.task_catalog,
        spec.workflow_family_id,
    )
    initial_wave = recommended_initial_subagent_wave(
        spec.roles,
        active_subagents,
        spec.task_catalog,
        spec.agent_type_selections,
    )
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


def build_manifest(
    spec: RunBundleSpec,
    capacity_runtime: _CapacityRuntime | None = None,
) -> str:
    """Build the team manifest yaml."""
    workflow_family = run_workflow_family(spec)
    active_design_packet = run_active_design_packet(spec, workflow_family)
    lines = manifest_run_lines(spec, workflow_family, capacity_runtime)
    lines.extend(manifest_role_lines(spec, workflow_family, active_design_packet))
    lines.extend(manifest_context_policy_lines(spec.config, active_design_packet))
    lines.extend(manifest_quality_gate_lines(spec.config))
    lines.extend(manifest_artifact_lines(spec.config, spec.roles, active_design_packet))
    return "\n".join(lines) + "\n"


def manifest_run_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
    capacity_runtime: _CapacityRuntime | None = None,
) -> list[str]:
    """Render run-level manifest fields."""
    capacity_runtime = capacity_runtime or capacity_runtime_for_spec(spec)
    capacity_projection = _capacity_projection(capacity_runtime, spec)
    closeout_projection = _closeout_projection(capacity_runtime, spec)
    active_design_packet = run_active_design_packet(spec, workflow_family)
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
        "  active_design_packet:",
    ]
    packet_yaml = yaml.safe_dump(
        active_design_packet_mapping(active_design_packet),
        sort_keys=False,
        default_flow_style=False,
    ).splitlines()
    lines.extend(f"    {line}" for line in packet_yaml)
    projection = active_design_packet_reference_projection(
        spec,
        active_design_packet,
        iter_artifacts(spec.config, spec.roles, active_design_packet),
    )
    lines.append("  active_design_packet_reference_projection:")
    projection_yaml = yaml.safe_dump(
        projection,
        sort_keys=False,
        default_flow_style=False,
    ).splitlines()
    lines.extend(f"    {line}" for line in projection_yaml)
    lines.extend(
        [
        "  parent_lineage_id: " + repr(capacity_runtime.parent_lineage_id),
        "  implementation_execution:",
        "    schema_id: 'implementation_execution_contract_v1'",
        "    route_owner: 'implementation_route'",
        "    route_import: 'tools.agent_tools.implementation_route'",
        "    profile_registry_import: 'tools.agent_tools.model_profile_registry'",
        "    dispatch: 'immediate_one_pass'",
        "    same_spark_gap_continuation: 'resume_same_spark_after_gap'",
        "    deterministic_search_route: 'python3 tools/agent_tools/search.py --query-file <request-or-design-question.txt> --providers text,semantic,vector,tool,header-deps,code-deps --format json'",
        "  capacity_request:",
        ]
    )
    capacity_yaml = yaml.safe_dump(
        capacity_projection,
        sort_keys=False,
        default_flow_style=False,
    ).splitlines()
    for line in capacity_yaml:
        lines.append(f"    {line}")
    lines.extend(
        [
            "  closeout_packet:",
        ]
    )
    closeout_yaml = yaml.safe_dump(
        closeout_projection,
        sort_keys=False,
        default_flow_style=False,
    ).splitlines()
    for line in closeout_yaml:
        lines.append(f"    {line}")
    lines.extend(
        [
        "  subagent_lifecycle_policy:",
        "    fresh_subagents_required: conditional",
        "    reuse_for_new_task: allowed_when_owner_context_compatible",
        "    previous_task_subagent_reuse: allowed_when_owner_context_compatible",
        "    mid_task_user_input_policy: classify_then_reuse_or_route_fresh",
        "    same_task_delta_reuse: allowed_when_owner_context_compatible",
        "    scope_change_reuse: evaluate_owner_context_compatibility",
        "    new_task_reuse: evaluate_owner_context_compatibility",
        "    close_before_user_completion: true",
        "    closeout_gate_key: subagents_closed",
        "    closeout_evidence_section: 'Subagent Lifecycle Evidence'",
        "    handoff_rule: 'Reuse an active agent when owner, responsibility, context, write "
        "authority, and validation route remain compatible, including revised scope. Use a "
        "fresh agent only for independent review, disjoint write authority, incompatible "
        "owner/context, or failed context integrity. Durable checkpoints and packet paths "
        "are conditional on coordination or resumption.'",
        "  handoff_context_policy:",
        "    inactive_profile_docs: not_applicable",
        "    broad_cross_cutting_packet: available_not_default_read",
        "  implementation_gate_defaults:",
        "    implementation_surface_route_status: pending",
        "    implementation_surface_route_command: 'python3 tools/agent_tools/search.py --query-file <request-or-design-question.txt> --providers text,semantic,vector,tool,header-deps,code-deps --format json'",
        "    tool_reuse_ledger_status: required_before_custom_implementation",
        "    pre_edit_rejection_prediction_status: pending",
        "    pre_edit_rejection_command: 'python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>'",
        "  standard_wave_sequence:",
        "    activation: candidate_sequence_selected_per_wave",
        f"    source: {STANDARD_AGENT_WAVE_SEQUENCE_SOURCE!r}",
        "    stages:",
        *(f"      - {stage}" for stage in STANDARD_AGENT_WAVE_SEQUENCE),
        "    gate_order: 'selected_stages_only'",
        "    edit_handoff_rule: 'selected owner-critical edit stage only; no fixed plan-review-edit sequence'",
        *manifest_user_facing_language_policy_lines(),
        *manifest_contract_complete_implementation_policy_lines(spec.task),
        *manifest_pre_handoff_scope_policy_lines(),
        *manifest_pre_handoff_gate_status_lines(active_design_packet),
        *manifest_decision_sufficiency_lines(spec),
        *manifest_repo_tool_routing_policy_lines(spec),
        *manifest_default_quality_check_policy_lines(spec),
        "  agent_report_collection:",
        "    status_command: 'python3 tools/agent_tools/runtime_log_archive_git.py status'",
        f"    archive_current_run_command: 'python3 tools/agent_tools/runtime_log_archive_git.py archive-agent-report --report-dir {spec.report_dir}'",
        "    sync_command: 'python3 tools/agent_tools/runtime_log_archive_git.py sync'",
        "    archive_index: '.agent-canon/log-archive/agent-reports/<repo-key>/index.jsonl'",
        ]
    )
    insert_index = (
        lines.index("    broad_cross_cutting_packet: available_not_default_read") + 1
    )
    lines.insert(insert_index, "    common_prompt_must_include:")
    insert_index += 1
    for field in COMMON_PROMPT_MUST_INCLUDE:
        lines.insert(insert_index, f"      - {field}")
        insert_index += 1
    lines.insert(insert_index, "    evaluator_prompt_must_include:")
    insert_index += 1
    for field in EVALUATOR_PROMPT_MUST_INCLUDE:
        lines.insert(insert_index, f"      - {field}")
        insert_index += 1
    communication_protocol = spec.config.team.get("communication_protocol")
    if communication_protocol is not None:
        lines.append(
            f"  communication_protocol: {str(ROOT / str(communication_protocol))!r}"
        )
    if workflow_family is not None:
        if spec.task_catalog is None:
            raise RuntimeError("task catalog is required for spawn wave recommendation")
        active_subagents, max_write_subagents = workflow_spawn_budget(
            spec.task_catalog,
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
        initial_wave = recommended_initial_subagent_wave(
            spec.roles,
            active_subagents,
            spec.task_catalog,
            spec.agent_type_selections,
        )
        expansion_wave_slots = recommended_dynamic_expansion_wave_slots(
            spec.roles,
            active_subagents,
            initial_wave,
            spec.task_catalog,
            spec.agent_type_selections,
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
        if spec.agent_type_selections:
            lines.append("    agent_type_selections:")
            for selection in spec.agent_type_selections:
                lines.append(f"      - role_id: {selection.role_id}")
                lines.append(f"        agent_type: {selection.agent_type}")
                lines.append(f"        evidence: {selection.evidence!r}")
        else:
            lines.append("    agent_type_selections: []")
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
                        f"{slot.executable_identity}:team_manifest.yaml#roles.{slot.role_id}"
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
        validation_policy = validation_failure_response_policy()
        lines.append(f"      taxonomy_source: {validation_policy['taxonomy_source']}")
        lines.append("      repair_required_fields:")
        for field in cast("tuple[str, ...]", validation_policy["required_fields"]):
            lines.append(f"        - {field}")
        lines.append("      intent_preservation_values:")
        for value in cast("tuple[str, ...]", validation_policy["intent_preservation"]):
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
        lines.append("      - replaceable_unit")
        lines.append("      - implementation_mechanism")
        lines.append("      - validation_route")
        lines.append("      - tool_route")
        lines.append("      - tool_call_token")
        lines.append("      - tool_evidence")
        lines.append("      - allowed_paths")
        lines.append("      - do_not_read")
        lines.append("      - expected_output")
        lines.append("      - write_scope")
        lines.append("      - remaining_spawn_budget")
        lines.append("    handoff_optional_fields:")
        lines.append("      - decision_sufficiency_packet_ref")
        lines.append("      - unresolved_branch")
        lines.append("      - review_gate")
        lines.append("      - plan_artifact")
        lines.append("      - edit_handoff")
        lines.append("      - pre_handoff_gate_status")
        lines.append("    required_before_spawn:")
        lines.append(
            "      - owner, replaceable unit, implementation mechanism, validation "
            "route, and any unresolved branch that can change them"
        )
        lines.append(
            "      - include run.default_quality_check_policy only when a selected "
            "review or edit route consumes it"
        )
        lines.append(
            "      - include run.pre_handoff_scope_policy and dependency-expanded "
            "handoff scope evidence"
        )
        lines.append(
            "      - include run.pre_handoff_gate_status only before the selected "
            "implementation or write-capable handoff when design_brief.md exists"
        )
        lines.append(
            "      - include run.repo_tool_routing_policy selected-skill ToolCall tokens, "
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
            "      - selected schedule.md Agent Wave Ledger row with spawn_authority, "
            "budget, runtime ceilings, paths, validation_route, review_gate, "
            "handoff_artifacts, and delegated policy ref"
        )
        lines.append(
            "      - workflow_monitoring.md intervention or behavior-event for spawned/skipped roles"
        )
        lines.append(
            "      - structured handoff with allowed_paths, do_not_read, expected_output, "
            "and write_policy; durable packet transport is conditional"
        )
        lines.append("    closeout_required_evidence:")
        lines.append(
            "      - closeout_gate.md Subagent Lifecycle Evidence planned-vs-actual wave status"
        )
        lines.append(
            "      - closed selected run-local agent ids, or the applicable structured "
            "parent handoff / recorded parent-direct exception evidence"
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


def manifest_pre_handoff_gate_status_lines(
    active_design_packet: ActiveDesignPacketConfig,
) -> list[str]:
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
            "    applies_when: "
            f"run.active_design_packet.design_artifact={active_design_packet.design_artifact};"
            "condition=exists_before_implementation_or_handoff",
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
        f"    tool_call_schema: {TOOL_CALL_SCHEMA!r}",
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
    lines.append("      tool_call_token:")
    lines.extend(
        _yaml_mapping_lines(materialize_dynamic_route_tool_call_token(), indent=8)
    )
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
        "        tool_call_token:",
        *_yaml_mapping_lines(
            materialize_skill_tool_call_token(packet.skill), indent=10
        ),
        "        related_skills:",
    ]
    if packet.related_skills:
        for skill in packet.related_skills:
            lines.append(f"          - ${skill}")
    else:
        lines.append("          - none")
    return lines


def _yaml_mapping_lines(value: Mapping[str, object], *, indent: int) -> list[str]:
    """Render one machine object as indented manifest YAML."""
    prefix = " " * indent
    rendered = yaml.safe_dump(
        dict(value),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    return [prefix + line if line else line for line in rendered.splitlines()]


def manifest_decision_sufficiency_lines(spec: RunBundleSpec) -> list[str]:
    """Render semantic decision sufficiency and optional durable transport."""
    lines = [
        "  decision_sufficiency:",
        f"    owner: {DECISION_SUFFICIENCY_OWNER!r}",
        f"    validator: {DECISION_SUFFICIENCY_VALIDATOR!r}",
        "    consumer_policy: 'consume_semantic_record_without_second_form'",
        "    semantic_fields:",
    ]
    for field in DECISION_SUFFICIENCY_MACHINE_FIELDS:
        lines.append(f"      - {field}")
    lines.extend(
        [
            "    transport_fields_optional:",
            "      - packet_ref",
            "      - packet",
            "      - digest",
        ]
    )
    if spec.decision_sufficiency_packet is None:
        lines.extend(
            [
                "    status: semantic_record_required",
                "    packet_ref: null",
            ]
        )
        return lines
    packet = import_decision_sufficiency_verdict(spec.decision_sufficiency_packet)
    fixed_spark_legacy_fields = {
        "H",
        "possible_branches",
        "route_verdict",
    }
    transport_scope = (
        "fixed_spark_route_only"
        if fixed_spark_legacy_fields.intersection(packet)
        else "semantic_record_only"
    )
    lines.extend(
        [
            "    status: semantic_record_with_optional_transport",
            f"    packet_ref: {spec.decision_sufficiency_packet_ref or None!r}",
            f"    optional_packet_scope: {transport_scope!r}",
            "    optional_packet:",
            *_yaml_mapping_lines(packet, indent=6),
        ]
    )
    return lines


def manifest_default_quality_check_policy_lines(spec: RunBundleSpec) -> list[str]:
    """Render default quality-check routing policy lines."""
    role_ids = default_quality_check_role_ids(spec.roles)
    agent_types = default_quality_check_agent_types(spec.roles)
    review_pack_state = (
        "active" if spec.default_review_packs_enabled else "candidate_not_activated"
    )
    lines = [
        "  default_quality_check_policy:",
        "    enabled: false",
        f"    source: {DEFAULT_QUALITY_CHECK_POLICY_SOURCE!r}",
        "    activation: owner_critical_or_distinct_unresolved_claim_or_risk",
        "    wave_sequence_ref: run.standard_wave_sequence (selected stages only)",
        "    role_topology_ref: 'agents/task_catalog.yaml#role_topology_defaults.role_families.review'",
        "    stages:",
    ]
    for stage in DEFAULT_QUALITY_CHECK_STAGES:
        lines.append(f"      - {stage}")
    if role_ids:
        lines.append("    candidate_roles:")
        for role_id in role_ids:
            lines.append(f"      - {role_id}")
    else:
        lines.append("    candidate_roles: []")
    if agent_types:
        lines.append("    candidate_codex_agent_types:")
        for agent_type in agent_types:
            lines.append(f"      - {agent_type}")
    else:
        lines.append("    candidate_codex_agent_types: []")
    lines.append("    provenance:")
    if spec.task_default_specialists:
        lines.append("      task_default_specialists:")
        for role_id in spec.task_default_specialists:
            lines.append(f"        - {role_id}")
    else:
        lines.append("      task_default_specialists: []")
    if spec.language_review_candidates:
        lines.append("      language_review_candidates:")
        for role_id in spec.language_review_candidates:
            lines.append(f"        - {role_id}")
    else:
        lines.append("      language_review_candidates: []")
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
    active_design_packet: ActiveDesignPacketConfig,
) -> list[str]:
    """Render role entries for the team manifest."""
    lines = ["roles:"]
    for role in spec.roles:
        lines.extend(
            manifest_one_role_lines(
                spec,
                workflow_family,
                active_design_packet,
                role,
            )
        )
    return lines


def manifest_one_role_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
    active_design_packet: ActiveDesignPacketConfig,
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
    for output in selected_role_outputs(spec.config, role, active_design_packet):
        lines.append(f"      - {output}")
    lines.extend(manifest_write_policy_lines(spec, role, active_design_packet))
    lines.extend(manifest_document_packet_lines(spec, role, active_design_packet))
    return lines


def manifest_prompt_contract_lines(
    role: Role,
    workflow_family: dict[str, object] | None,
) -> list[str]:
    """Render prompt contract lines for one role."""
    lines = ["    prompt_contract:"]
    if role.id == "implementer":
        lines.append(
            "      assignment_prompt: "
            "'runtime_materialized_fixed_packet_prompt_only'"
        )
        lines.append(
            "      assignment_prompt_source: "
            "'tools/agent_tools/agent_team.py#dispatch_fixed_implementation->model_profile_registry.materialize_prompt_capsule'"
        )
    else:
        lines.append(
            "      assignment_prompt: "
            f"{compact_role_prompt_contract(role, workflow_family)!r}"
        )
        lines.append(
            "      assignment_prompt_source: "
            "'tools/agent_tools/agent_team.py#role_prompt_contract'"
        )
    if role.id == "skill_evaluator":
        lines.append("      common_prompt_must_include_ref: 'not_applicable'")
        lines.append(
            "      evaluator_prompt_must_include_ref: "
            "run.handoff_context_policy.evaluator_prompt_must_include"
        )
    else:
        lines.append(
            "      common_prompt_must_include_ref: "
            "run.handoff_context_policy.common_prompt_must_include"
        )
    lines.append("      role_prompt_must_include:")
    for item in role_prompt_must_include(role):
        lines.append(f"        - {item!r}")
    return lines


def manifest_write_policy_lines(
    spec: RunBundleSpec,
    role: Role,
    active_design_packet: ActiveDesignPacketConfig,
) -> list[str]:
    """Render resolved write policy lines for one role."""
    scope = resolve_role_write_scope(
        config=spec.config,
        role=role,
        report_dir=spec.report_dir,
        workspace_root=spec.workspace_root,
        active_design_packet=active_design_packet,
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


def manifest_document_packet_lines(
    spec: RunBundleSpec,
    role: Role,
    active_design_packet: ActiveDesignPacketConfig,
) -> list[str]:
    """Render explicit document packet lines for one role."""
    document_packet = resolve_role_document_packet(
        spec.config,
        role,
        spec.report_dir,
        spec.workspace_root,
        active_design_packet,
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
        if entry.sections:
            lines.append("          sections:")
            for section in entry.sections:
                lines.append(f"            - heading: {section.heading!r}")
                lines.append(f"              anchor: {section.anchor!r}")
                lines.append(
                    f"              required: {str(section.required).lower()}"
                )
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


def manifest_context_policy_lines(
    config: TeamConfig,
    active_design_packet: ActiveDesignPacketConfig,
) -> list[str]:
    """Render context-sharing policy lines."""
    lines = ["context_policies:"]
    packet_artifacts = active_design_packet_artifact_map(config, active_design_packet)
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
            lines.append(f"      - {packet_artifacts.get(artifact, artifact)}")
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


def manifest_artifact_lines(
    config: TeamConfig,
    roles: tuple[Role, ...],
    active_design_packet: ActiveDesignPacketConfig,
) -> list[str]:
    """Render artifact lines."""
    lines = ["artifacts:"]
    for artifact in iter_artifacts(config, roles, active_design_packet):
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
    stage_waves = topology.get("stage_waves")
    if isinstance(stage_waves, list):
        lines.append(f"{indent}  stage_waves:")
        for wave in _as_mapping_tuple(
            cast(object, stage_waves),
            "role_topology.stage_waves",
        ):
            lines.append(f"{indent}    - id: {_as_required_string(wave.get('id'), 'stage_waves[].id')}")
            lines.append(
                f"{indent}      stage_class: "
                f"{_as_required_string(wave.get('stage_class'), 'stage_waves[].stage_class')}"
            )
            lines.append(f"{indent}      role_ids:")
            for role_id in _as_string_tuple(wave.get("role_ids"), "stage_waves[].role_ids"):
                lines.append(f"{indent}        - {role_id}")
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
    lines.append(
        f"{indent}  decision_sufficiency_packet_ref: "
        "'run.decision_sufficiency.packet_ref'"
    )
    lines.append(f"{indent}  tool_route: 'run.repo_tool_routing_policy'")
    lines.append(f"{indent}  tool_call_tokens: 'run.repo_tool_routing_policy.sequential_tool_routes[].tool_call_token'")
    lines.append(
        f"{indent}  tool_evidence: 'run.repo_tool_routing_policy.dynamic_skill_routing'"
    )
    lines.append(f"{indent}  tool_catalog_matches: 'tools/catalog.yaml'")
    lines.append(f"{indent}  required_tool_fields:")
    lines.append(f"{indent}    - tool_route")
    lines.append(f"{indent}    - tool_call_tokens")
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
        "Carry the owner-produced DecisionSufficiencyPacket reference and "
        "run.repo_tool_routing_policy tool_route, machine-readable ToolCall tokens, and tool_evidence into "
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
    if role.id == "skill_evaluator":
        return (
            "skill_evaluator for the frozen Scenario Packet; fresh and read-only; "
            "use only current_scenario_packet, packet_listed_evaluation_files, "
            "do_not_read, and expected_output_schema; do not receive common or "
            "cross-cutting run context."
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
    if role.id == "skill_evaluator":
        return (
            "fresh_evaluator",
            "read_only",
            "no_nested_agents",
            "fixed_output_grammar",
        )
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
    active_design_packet: ActiveDesignPacketConfig | None = None,
) -> RoleWriteScope:
    """Resolve concrete write paths for one role."""
    allowed_files = role_allowed_artifact_files(
        config,
        role,
        report_dir,
        active_design_packet,
    )
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
    active_design_packet: ActiveDesignPacketConfig | None = None,
) -> tuple[Path, ...]:
    """Resolve generated artifact files one role may write."""
    packet = active_design_packet or resolve_active_design_packet_config(config)
    return tuple(
        sorted(
            {
                resolve_report_bundle_artifact_path(
                    report_dir,
                    selected_artifact_name(config, artifact_key, packet),
                )
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
