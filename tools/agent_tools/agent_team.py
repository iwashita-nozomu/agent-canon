#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides agent team agent workflow automation.
# upstream design ../README.md shared automation index
# upstream design ../../agents/task_catalog.yaml workflow topology and isolated skill-evaluation route
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared vendor-only document packet policy
# upstream implementation ./graph_client.py provides canonical dependency facts for packet references
# upstream implementation ./workflow_monitor.py renders initial monitoring artifacts for atomic publication
# upstream implementation ./skill_tool_commands.py builds selected skill command packets.
# downstream implementation ./task_start.py creates task-start run bundles
# downstream implementation ./bootstrap_agent_run.py creates bootstrap run bundles
# downstream implementation ./waterfall_gate_check.py consumes materialized active packets
# @dependency-end
"""Shared runtime helpers for the permanent agent team."""

from __future__ import annotations

import ast
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal, cast
from urllib.parse import quote

import yaml
from graph_client import CANONICAL_GRAPH_EXECUTABLE, GraphClient, GraphClientError
from report_artifact_checks import (
    is_placeholder_only_section,
    parse_review_identity,
    section_has_content,
)
from route import decide_skills, implementation_handoff_required, load_skill_route_rules
from skill_tool_commands import (
    PROMPT_PLACEHOLDER,
    SkillCommandPacket,
    packet_for_skill,
)
from task_authority import (
    AUTHORITY_FILE_NAME,
    authority_baseline_path,
    build_default_task_authority,
    hash_baseline_bytes,
)

if TYPE_CHECKING:
    from workflow_monitor import MonitoringEntries

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
VALIDATION_FAILURE_TAXONOMY_SOURCE = "documents/runtime-profiles-and-check-matrix.json"
RUNTIME_PROFILE_INVENTORY_PATH = ROOT / VALIDATION_FAILURE_TAXONOMY_SOURCE
_validation_failure_response_policy_cache: dict[str, object] | None = None
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
            raise ValueError(
                "validation_failure_response.required_fields must be strings"
            )
        if not isinstance(intent_preservation, list) or not all(
            isinstance(value, str)
            for value in cast("list[object]", intent_preservation)
        ):
            raise ValueError(
                "validation_failure_response.intent_preservation must be strings"
            )
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
    "final_review",
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
            "Gate 9. 最終受け入れ review",
        ),
        "agents/canonical/CODEX_WORKFLOW.md": (
            "4. Run Bootstrap",
            "5. Implementation",
        ),
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


class ReportBundleArtifactPathError(RuntimeError):
    """Report one rejected run-artifact path and its containment reason."""

    def __init__(self, declared_path: str, reason: str) -> None:
        """Record the rejected declaration and stable reason code."""
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
    """Resolve one lexical bundle path without following symlink components."""
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
        raise ReportBundleArtifactPathError(
            declared_path,
            "outside_bundle",
        ) from exc
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


@dataclass(frozen=True)
class ActiveDesignClause:
    """One packet clause and its canonical source reference."""

    clause_id: str
    source_ref: str


@dataclass(frozen=True)
class ActiveDesignPacketEntry:
    """Neutral reference record shared by all four design sections."""

    entry_id: str
    responsibility_id: str
    clause_refs: tuple[str, ...]
    owner_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    dependency_refs: tuple[str, ...]
    output_refs: tuple[str, ...]
    reviewer_refs: tuple[str, ...]


@dataclass(frozen=True)
class ActiveDesignPacketValue:
    """Complete four-section active design packet value."""

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
        """Return section/value pairs in canonical order."""
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


RUN_BUNDLE_FILE_MODE = 0o644
RUN_BUNDLE_DIRECTORY_MODE = 0o755
PRIVATE_STAGE_MODE = 0o700
PRIVATE_TEMP_MODE = 0o600
MATERIALIZATION_LOCK_MODE = 0o600
MATERIALIZATION_LOCK_SCHEMA = "agent_canon.run_bundle_materialization_lock.v1"
MATERIALIZATION_LOCK_NAME = ".run_bundle_materialization.lock"
RENAME_NOREPLACE = 1
RENAME_EXCHANGE = 2
AT_FDCWD = -100
GENERATED_NAME_ATTEMPTS = 8
CleanupStatus = Literal["not_required", "pass", "fail"]
MaterializationPhase = Literal[
    "decode",
    "reference_validation",
    "render",
    "stage",
    "publish",
    "activate",
    "rollback",
]
MaterializationErrorCode = Literal[
    "packet_invalid",
    "reference_invalid",
    "render_invalid",
    "artifact_set_invalid",
    "report_root_invalid",
    "materialization_lock_failed",
    "materialization_lock_busy",
    "materialization_lock_foreign",
    "materialization_lock_release_failed",
    "atomic_noreplace_unavailable",
    "atomic_exchange_unavailable",
    "staging_name_exhausted",
    "staging_write_failed",
    "staging_verify_failed",
    "run_bundle_target_exists",
    "run_bundle_cross_device",
    "run_bundle_publish_failed",
    "active_bookkeeping_nonregular",
    "bookkeeping_name_exhausted",
    "active_baseline_publish_failed",
    "active_pointer_publish_failed",
    "bookkeeping_restore_conflict",
    "run_bundle_rollback_failed",
]
LockReuseClass = Literal[
    "first_acquisition",
    "released_file_reuse",
    "crash_stale_reuse",
]


@dataclass(frozen=True)
class RenderedArtifact:
    """One fully rendered run-bundle artifact awaiting publication."""

    relative_path: PurePosixPath
    content: bytes
    mode: int


@dataclass(frozen=True)
class ArtifactDigest:
    """Stable digest for one rendered artifact."""

    relative_path: PurePosixPath
    sha256: str


@dataclass(frozen=True)
class SubagentPromptPacket:
    """Projected prompt inputs for one selected role."""

    role_id: str
    active_design_packet: ActiveDesignPacketValue
    document_packet: RoleDocumentPacket
    required_outputs: tuple[str, ...]


@dataclass(frozen=True)
class SourceReferenceResult:
    """Resolved source-reference evidence for the active design packet."""

    declared_ref: str
    root_key: Literal["workspace", "agent_canon", "artifact"]
    resolved_path: Path
    relative_path: PurePosixPath
    fragment_kind: Literal["none", "symbol", "section"]
    fragment_value: str | None
    sha256: str
    parser_match_count: int


@dataclass(frozen=True)
class DependencyReferenceResult:
    """Canonical dependency-edge evidence for one declared reference."""

    declared_ref: str
    dependency_root_key: Literal["workspace", "agent_canon"]
    normalized_key: str
    source_path: PurePosixPath
    target_path: PurePosixPath
    source_sha256: str
    target_sha256: str
    graph_match_count: int


@dataclass(frozen=True)
class RoleOutputProjection:
    """Exact selected output paths owned by one active role."""

    role_ref: str
    output_refs: tuple[str, ...]


@dataclass(frozen=True)
class ReviewerArtifactProjection:
    """Exact one-to-one join from a reviewer role to its review artifact."""

    reviewer_ref: str
    review_artifact_ref: str


@dataclass(frozen=True)
class ClauseReferenceResult:
    """Resolved clause identifier and its authoritative source reference."""

    clause_id: str
    source_ref: str


@dataclass(frozen=True)
class OutputReferenceResult:
    """Planned artifact-path evidence for one output reference."""

    output_ref: str
    relative_path: PurePosixPath
    planned_count: int


@dataclass(frozen=True)
class ActiveDesignReferenceContext:
    """Complete authoritative projection used by packet validation."""

    workspace_root: Path
    report_dir: Path
    source_results: tuple[SourceReferenceResult, ...]
    dependency_results: tuple[DependencyReferenceResult, ...]
    role_output_projections: tuple[RoleOutputProjection, ...]
    reviewer_artifact_projections: tuple[ReviewerArtifactProjection, ...]
    clause_results: tuple[ClauseReferenceResult, ...]
    output_results: tuple[OutputReferenceResult, ...]
    planned_output_paths: frozenset[PurePosixPath]


@dataclass(frozen=True)
class ManifestPacketViolation:
    """One typed manifest-shape violation."""

    kind: str
    field: str | None
    observed_schema: str | None
    order_key: tuple[int, int, int, int]


@dataclass(frozen=True)
class ReferencePacketViolation:
    """One typed active-packet reference violation."""

    section: ActiveDesignSection
    field: str
    input_index: int
    reason: str
    order_key: tuple[int, int, int, int]


@dataclass(frozen=True)
class DesignArtifactViolation:
    """One typed design-artifact validation violation."""

    artifact_path: PurePosixPath
    reason: str
    section_slug: str | None
    order_key: tuple[int, int, int, int]


@dataclass(frozen=True)
class ReviewArtifactViolation:
    """One typed design-review validation violation."""

    artifact_path: PurePosixPath
    reason: str
    order_key: tuple[int, int, int, int]


ActiveDesignPacketViolation = (
    ManifestPacketViolation
    | ReferencePacketViolation
    | DesignArtifactViolation
    | ReviewArtifactViolation
)


@dataclass(frozen=True)
class MaterializedActiveDesignPacketResult:
    """Loaded packet, persisted projection, and complete violation set."""

    value: ActiveDesignPacketValue | None
    context: ActiveDesignReferenceContext | None
    violations: tuple[ActiveDesignPacketViolation, ...]


@dataclass(frozen=True)
class RollbackResult:
    """Independent cleanup outcomes for a failed materialization."""

    staging_cleanup: CleanupStatus = "not_required"
    target_cleanup: CleanupStatus = "not_required"
    pointer_restore: CleanupStatus = "not_required"
    baseline_restore: CleanupStatus = "not_required"
    temp_cleanup: CleanupStatus = "not_required"
    failed_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileIdentity:
    """Filesystem identity fields used for compare-before-mutate checks."""

    st_dev: int
    st_ino: int
    st_uid: int
    st_gid: int
    st_mode: int
    st_nlink: int


@dataclass(frozen=True)
class BookkeepingFileState:
    """Exact prior or published state of one activation bookkeeping file."""

    name: Literal[".active_run", ".active_run.sha256"]
    existed: bool
    identity: FileIdentity | None
    permission_mode: int | None
    size: int | None
    sha256: str | None
    content: bytes | None


@dataclass(frozen=True)
class BookkeepingTempState:
    """Verified temporary bookkeeping artifact and its bytes."""

    path: Path
    identity: FileIdentity
    permission_mode: int
    size: int
    sha256: str
    content: bytes


@dataclass(frozen=True)
class MaterializationLockIdentity:
    """Canonical persistent lock payload and process identity."""

    schema_version: str
    state: Literal["held"]
    report_root_identity: FileIdentity
    lock_file_identity: FileIdentity
    effective_uid: int
    pid: int
    process_start_ticks: int
    boot_id: str
    nonce: str
    acquired_at: str
    run_id: str
    reuse_class: LockReuseClass
    payload_sha256: str


@dataclass(frozen=True)
class MaterializationLock:
    """Held persistent materialization lock and open descriptor."""

    path: Path
    descriptor: int
    identity: MaterializationLockIdentity


@dataclass(frozen=True)
class PriorBookkeepingState:
    """Snapshot and transaction state for pointer-last activation."""

    report_root_identity: FileIdentity
    lock_file_identity: FileIdentity
    lock_nonce: str
    pointer_prior: BookkeepingFileState
    baseline_prior: BookkeepingFileState
    pointer_temp: BookkeepingTempState | None = None
    baseline_temp: BookkeepingTempState | None = None
    pointer_quarantine: BookkeepingTempState | None = None
    baseline_quarantine: BookkeepingTempState | None = None
    pointer_published: BookkeepingFileState | None = None
    baseline_published: BookkeepingFileState | None = None


@dataclass(frozen=True)
class StagedArtifactSet:
    """Verified private staging directory awaiting publication."""

    path: Path
    identity: FileIdentity


@dataclass(frozen=True)
class PublishedTarget:
    """Published run-bundle identity and content-tree digest."""

    path: Path
    identity: FileIdentity
    tree_sha256: str


class RunBundleMaterializationError(RuntimeError):
    """Closed typed failure for bundle render, publication, and rollback."""

    def __init__(
        self,
        *,
        phase: MaterializationPhase,
        code: MaterializationErrorCode,
        cause_code: MaterializationErrorCode,
        target_path: Path,
        staging_path: Path | None = None,
        violations: tuple[ActiveDesignPacketViolation, ...] = (),
        rollback: RollbackResult | None = None,
    ) -> None:
        """Initialize one closed materialization failure."""
        self.phase = phase
        self.code = code
        self.cause_code = cause_code
        self.target_path = target_path
        self.staging_path = staging_path
        self.violations = violations
        self.rollback = rollback if rollback is not None else RollbackResult()
        super().__init__(f"run_bundle_materialization:{phase}:{code}")


@dataclass(frozen=True)
class RunActivationSpec:
    """Parent-owned activation inputs rendered in the atomic transaction."""

    report_root: Path
    monitoring_entries: MonitoringEntries


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
    active_design_packet: ActiveDesignPacketValue | None = None
    activation: RunActivationSpec | None = None
    workflow_family_id: str = ""
    manual_specialists: tuple[str, ...] = ()
    task_default_specialists: tuple[str, ...] = ()
    auto_specialists: tuple[str, ...] = ()
    default_review_packs_enabled: bool = False
    default_review_pack_ids: tuple[str, ...] = ()
    selected_skills: tuple[str, ...] = ()
    task_catalog: TaskCatalog | None = None
    agent_type_selections: tuple[AgentTypeSelection, ...] = ()


@dataclass(frozen=True)
class RunBundleMaterialization:
    """Published run-bundle result returned to every producer."""

    report_dir: Path
    created_files: tuple[str, ...]
    active_design_packet: ActiveDesignPacketValue
    role_document_packets: tuple[RoleDocumentPacket, ...]
    subagent_prompt_packets: tuple[SubagentPromptPacket, ...]
    artifact_digests: tuple[ArtifactDigest, ...]
    active_pointer: Path | None


def load_team_config(path: Path = TEAM_CONFIG_PATH) -> TeamConfig:
    """Load the canonical team config."""
    try:
        parsed: object = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except _DuplicateJsonKey as exc:
        raise RuntimeError(f"team_config:duplicate_key:{exc.key}") from exc
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


ActiveDesignPacketInputErrorCode = Literal[
    "json_invalid",
    "missing_field",
    "unknown_field",
    "wrong_type",
    "unknown_schema",
    "duplicate_id",
    "empty_reference_set",
    "malformed_reference",
]
ACTIVE_PACKET_VALUE_KEYS = (
    "schema",
    "design_artifact",
    "design_review_artifact",
    "document_flow_review_artifact",
    "document_flow_required",
    "clause_registry",
    *ACTIVE_DESIGN_SECTIONS,
)
ACTIVE_PACKET_ENTRY_KEYS = (
    "entry_id",
    "responsibility_id",
    *ACTIVE_DESIGN_REFERENCE_FIELDS,
)
ACTIVE_PACKET_ENTRY_IDS = {
    "abstract_design_frame": "abstract-design-frame",
    "implementation_source_packet": "implementation-source-packet",
    "design_side_effect_map": "design-side-effect-map",
    "design_to_implementation_trace": "design-to-implementation-trace",
}
SOURCE_REFERENCE_PATTERN = re.compile(
    r"^(?:repo|artifact):[^#]+(?:#(?:symbol|section):[^#]+)?$"
)
HEADER_REFERENCE_PATTERN = re.compile(
    r"^header:(?:upstream|downstream):(?:design|implementation|environment):"
    r"repo:[^#\x00]+->repo:[^#\x00]+$"
)
ROLE_REFERENCE_PATTERN = re.compile(r"^role:[A-Za-z0-9][A-Za-z0-9_-]*$")
CLAUSE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class ActiveDesignPacketInputError(ValueError):
    """One stable active-design-packet decoder failure."""

    def __init__(
        self,
        *,
        code: ActiveDesignPacketInputErrorCode,
        field: str,
    ) -> None:
        """Initialize one stable decoder failure."""
        self.code = code
        self.field = field
        super().__init__(f"active_design_packet:{code}:{field}")


class _DuplicateJsonKey(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _input_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ActiveDesignPacketInputError(code="wrong_type", field=field)
    mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        raise ActiveDesignPacketInputError(code="wrong_type", field=field)
    return cast(dict[str, object], mapping)


def _input_required_fields(
    mapping: Mapping[str, object],
    expected: tuple[str, ...],
    field: str,
) -> None:
    missing = [key for key in expected if key not in mapping]
    if missing:
        raise ActiveDesignPacketInputError(
            code="missing_field",
            field=f"{field}.{missing[0]}",
        )
    unknown = [key for key in mapping if key not in expected]
    if unknown:
        raise ActiveDesignPacketInputError(
            code="unknown_field",
            field=f"{field}.{unknown[0]}",
        )


def _input_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ActiveDesignPacketInputError(code="wrong_type", field=field)
    return value


def _validate_relative_posix_path(value: str, field: str) -> str:
    path = PurePosixPath(value)
    if (
        "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ActiveDesignPacketInputError(code="malformed_reference", field=field)
    return value


def _input_reference_tuple(
    value: object,
    field: str,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ActiveDesignPacketInputError(code="wrong_type", field=field)
    if not value:
        raise ActiveDesignPacketInputError(code="empty_reference_set", field=field)
    refs = tuple(
        _input_string(item, f"{field}[{index}]")
        for index, item in enumerate(cast(list[object], value))
    )
    if len(set(refs)) != len(refs):
        raise ActiveDesignPacketInputError(code="duplicate_id", field=field)
    return refs


def _validate_source_reference(reference: str, field: str) -> None:
    if SOURCE_REFERENCE_PATTERN.fullmatch(reference) is None:
        raise ActiveDesignPacketInputError(code="malformed_reference", field=field)
    root, _, fragment = reference.partition("#")
    _prefix, path = root.split(":", 1)
    _validate_relative_posix_path(path, field)
    if fragment and fragment.split(":", 1)[1] == "":
        raise ActiveDesignPacketInputError(code="malformed_reference", field=field)


def _validate_entry_reference(reference: str, field: str) -> None:
    if not reference.startswith("entry:") or not reference.removeprefix("entry:"):
        raise ActiveDesignPacketInputError(code="malformed_reference", field=field)


def _validate_reference_field(
    field_name: str, refs: tuple[str, ...], field: str
) -> None:
    for index, reference in enumerate(refs):
        item_field = f"{field}[{index}]"
        if field_name == "clause_refs":
            valid = CLAUSE_ID_PATTERN.fullmatch(reference) is not None
        elif field_name in {"owner_refs", "reviewer_refs"}:
            valid = ROLE_REFERENCE_PATTERN.fullmatch(reference) is not None
        elif field_name == "source_refs":
            _validate_source_reference(reference, item_field)
            valid = True
        elif field_name == "dependency_refs":
            if reference.startswith("entry:"):
                _validate_entry_reference(reference, item_field)
                valid = True
            else:
                valid = HEADER_REFERENCE_PATTERN.fullmatch(reference) is not None
                remainder = reference.split(":", 3)[3] if valid else ""
                valid = valid and remainder.count("->repo:") == 1
                if valid:
                    source, target = remainder.split("->", 1)
                    _validate_source_reference(source, item_field)
                    _validate_source_reference(target, item_field)
        else:
            valid = reference.startswith("artifact:") and "#" not in reference
            if valid:
                _validate_relative_posix_path(
                    reference.removeprefix("artifact:"),
                    item_field,
                )
        if not valid:
            raise ActiveDesignPacketInputError(
                code="malformed_reference",
                field=item_field,
            )


def _decode_packet_entry(
    raw: object,
    *,
    section: ActiveDesignSection,
    field_prefix: str,
) -> ActiveDesignPacketEntry:
    field = f"{field_prefix}.{section}"
    mapping = _input_mapping(raw, field)
    _input_required_fields(mapping, ACTIVE_PACKET_ENTRY_KEYS, field)
    entry_id = _input_string(mapping["entry_id"], f"{field}.entry_id")
    if entry_id != ACTIVE_PACKET_ENTRY_IDS[section]:
        raise ActiveDesignPacketInputError(
            code="malformed_reference",
            field=f"{field}.entry_id",
        )
    responsibility_id = _input_string(
        mapping["responsibility_id"],
        f"{field}.responsibility_id",
    )
    references = {
        name: _input_reference_tuple(mapping[name], f"{field}.{name}")
        for name in ACTIVE_DESIGN_REFERENCE_FIELDS
    }
    for name, refs in references.items():
        _validate_reference_field(name, refs, f"{field}.{name}")
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


def _decode_active_design_packet(
    raw: object,
    *,
    field_prefix: str,
) -> ActiveDesignPacketValue:
    """Decode the one complete active-design-packet input shape."""
    packet = _input_mapping(raw, field_prefix)
    _input_required_fields(packet, ACTIVE_PACKET_VALUE_KEYS, field_prefix)
    schema = _input_string(packet["schema"], f"{field_prefix}.schema")
    if schema != "waterfall.design_packet.v1":
        raise ActiveDesignPacketInputError(
            code="unknown_schema",
            field=f"{field_prefix}.schema",
        )
    artifact_values = {
        name: _validate_relative_posix_path(
            _input_string(packet[name], f"{field_prefix}.{name}"),
            f"{field_prefix}.{name}",
        )
        for name in (
            "design_artifact",
            "design_review_artifact",
            "document_flow_review_artifact",
        )
    }
    document_flow_required = packet["document_flow_required"]
    if not isinstance(document_flow_required, bool):
        raise ActiveDesignPacketInputError(
            code="wrong_type",
            field=f"{field_prefix}.document_flow_required",
        )
    raw_clauses = packet["clause_registry"]
    if not isinstance(raw_clauses, list):
        raise ActiveDesignPacketInputError(
            code="wrong_type",
            field=f"{field_prefix}.clause_registry",
        )
    if not raw_clauses:
        raise ActiveDesignPacketInputError(
            code="empty_reference_set",
            field=f"{field_prefix}.clause_registry",
        )
    clauses: list[ActiveDesignClause] = []
    for index, raw_clause in enumerate(cast(list[object], raw_clauses)):
        clause_field = f"{field_prefix}.clause_registry[{index}]"
        clause = _input_mapping(raw_clause, clause_field)
        _input_required_fields(clause, ("clause_id", "source_ref"), clause_field)
        clause_id = _input_string(clause["clause_id"], f"{clause_field}.clause_id")
        source_ref = _input_string(clause["source_ref"], f"{clause_field}.source_ref")
        if CLAUSE_ID_PATTERN.fullmatch(clause_id) is None:
            raise ActiveDesignPacketInputError(
                code="malformed_reference",
                field=f"{clause_field}.clause_id",
            )
        _validate_source_reference(source_ref, f"{clause_field}.source_ref")
        clauses.append(ActiveDesignClause(clause_id=clause_id, source_ref=source_ref))
    clause_ids = tuple(clause.clause_id for clause in clauses)
    if len(set(clause_ids)) != len(clause_ids):
        raise ActiveDesignPacketInputError(
            code="duplicate_id",
            field=f"{field_prefix}.clause_registry",
        )
    entries: dict[ActiveDesignSection, ActiveDesignPacketEntry] = {
        section: _decode_packet_entry(
            packet[section],
            section=section,
            field_prefix=field_prefix,
        )
        for section in ACTIVE_DESIGN_SECTIONS
    }
    responsibility_ids = {entry.responsibility_id for entry in entries.values()}
    if len(responsibility_ids) != 1:
        raise ActiveDesignPacketInputError(
            code="duplicate_id",
            field=f"{field_prefix}.responsibility_id",
        )
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
        if not set(entry.clause_refs).issubset(set(clause_ids)):
            raise ActiveDesignPacketInputError(
                code="malformed_reference",
                field=f"{field_prefix}.{section}.clause_refs",
            )
        joined = {
            value.removeprefix("entry:")
            for value in entry.dependency_refs
            if value.startswith("entry:")
        }
        if entry.entry_id in joined or not joined.issubset(known_entry_ids):
            raise ActiveDesignPacketInputError(
                code="malformed_reference",
                field=f"{field_prefix}.{section}.dependency_refs",
            )
        if joined != expected_dependencies[section]:
            raise ActiveDesignPacketInputError(
                code="malformed_reference",
                field=f"{field_prefix}.{section}.dependency_refs",
            )
    if referenced_clauses != set(clause_ids):
        raise ActiveDesignPacketInputError(
            code="malformed_reference",
            field=f"{field_prefix}.clause_registry",
        )
    return ActiveDesignPacketValue(
        schema=schema,
        design_artifact=artifact_values["design_artifact"],
        design_review_artifact=artifact_values["design_review_artifact"],
        document_flow_review_artifact=artifact_values["document_flow_review_artifact"],
        document_flow_required=document_flow_required,
        clause_registry=tuple(clauses),
        abstract_design_frame=entries["abstract_design_frame"],
        implementation_source_packet=entries["implementation_source_packet"],
        design_side_effect_map=entries["design_side_effect_map"],
        design_to_implementation_trace=entries["design_to_implementation_trace"],
    )


def parse_active_design_packet_input(
    value: str | None,
) -> ActiveDesignPacketValue | None:
    """Parse one atomic JSON packet supplied by a run entrypoint."""
    if value is None:
        return None
    try:
        parsed: object = json.loads(
            value, object_pairs_hook=_reject_duplicate_json_keys
        )
    except _DuplicateJsonKey as exc:
        raise ActiveDesignPacketInputError(
            code="duplicate_id",
            field=f"active_design_packet.{exc.key}",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ActiveDesignPacketInputError(
            code="json_invalid",
            field="active_design_packet",
        ) from exc
    return _decode_active_design_packet(parsed, field_prefix="active_design_packet")


def resolve_active_design_packet(
    config: TeamConfig,
    *,
    workflow_family: Mapping[str, object] | None,
    explicit: ActiveDesignPacketValue | None,
) -> ActiveDesignPacketValue:
    """Resolve exactly explicit, workflow, then standard packet precedence."""
    if explicit is not None:
        return explicit
    if workflow_family is not None and "active_design_packet" in workflow_family:
        raw_packet = workflow_family["active_design_packet"]
        field_prefix = "workflow_family.active_design_packet"
    else:
        raw_packet = config.artifact_registry.get("active_design_packet")
        field_prefix = "artifacts.active_design_packet"
    if raw_packet is None:
        raise ActiveDesignPacketInputError(
            code="missing_field",
            field="artifacts.active_design_packet",
        )
    return _decode_active_design_packet(raw_packet, field_prefix=field_prefix)


FORBIDDEN_ACTIVE_PACKET_AUTHORITY_NAMES = {
    "schedule.md",
    "workflow_monitoring.md",
    "work_log.md",
    "decision_log.md",
}


def _packet_references(
    packet: ActiveDesignPacketValue,
    field: str,
) -> tuple[tuple[ActiveDesignSection, int, str], ...]:
    return tuple(
        (section, index, reference)
        for section, entry in packet.section_entries()
        for index, reference in enumerate(cast(tuple[str, ...], getattr(entry, field)))
    )


def _source_reference_parts(
    reference: str,
) -> tuple[str, PurePosixPath, str, str | None]:
    root, separator, fragment = reference.partition("#")
    prefix, path_value = root.split(":", 1)
    fragment_kind = "none"
    fragment_value: str | None = None
    if separator:
        fragment_kind, fragment_value = fragment.split(":", 1)
    return prefix, PurePosixPath(path_value), fragment_kind, fragment_value


def _resolved_source_path(
    spec: RunBundleSpec,
    reference: str,
) -> tuple[Literal["workspace", "agent_canon", "artifact"], Path, PurePosixPath]:
    prefix, relative_path, _fragment_kind, _fragment_value = _source_reference_parts(
        reference
    )
    if relative_path.name in FORBIDDEN_ACTIVE_PACKET_AUTHORITY_NAMES:
        raise ValueError(f"forbidden packet authority source: {reference}")
    if prefix == "artifact":
        return (
            "artifact",
            resolve_report_bundle_artifact_path(
                spec.report_dir,
                relative_path.as_posix(),
            ),
            relative_path,
        )
    resolved = resolve_workspace_document_path(
        spec.workspace_root,
        relative_path.as_posix(),
    ).resolve()
    workspace = spec.workspace_root.resolve()
    canon = ROOT.resolve()
    if resolved.is_relative_to(workspace) and not resolved.is_relative_to(canon):
        return (
            "workspace",
            resolved,
            PurePosixPath(resolved.relative_to(workspace).as_posix()),
        )
    if resolved.is_relative_to(canon):
        return (
            "agent_canon",
            resolved,
            PurePosixPath(resolved.relative_to(canon).as_posix()),
        )
    raise ValueError(f"source reference escaped canonical roots: {reference}")


def _ast_symbol_match_count(path: Path, dotted_qualname: str) -> int:
    tree = ast.parse(path.read_bytes(), filename=path.as_posix())
    components = dotted_qualname.split(".")
    nodes: list[ast.AST] = [tree]
    for component in components:
        matched: list[ast.AST] = []
        for node in nodes:
            body = getattr(node, "body", ())
            matched.extend(
                child
                for child in body
                if isinstance(
                    child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                )
                and child.name == component
            )
        nodes = matched
    return len(nodes)


def _source_parser_match_count(
    path: Path,
    fragment_kind: str,
    fragment_value: str | None,
) -> int:
    if not path.is_file() or path.is_symlink():
        return 0
    if fragment_kind == "none":
        return 1
    if fragment_value is None:
        return 0
    if fragment_kind == "symbol":
        return _ast_symbol_match_count(path, fragment_value)
    if fragment_kind == "section":
        return sum(
            markdown_heading_anchor(heading) == fragment_value
            for heading in markdown_document_headings(path)
        )
    return 0


def _source_reference_result(
    spec: RunBundleSpec,
    reference: str,
) -> SourceReferenceResult:
    root_key, resolved_path, relative_path = _resolved_source_path(spec, reference)
    _prefix, _path, fragment_kind, fragment_value = _source_reference_parts(reference)
    match_count = _source_parser_match_count(
        resolved_path,
        fragment_kind,
        fragment_value,
    )
    digest = (
        hashlib.sha256(resolved_path.read_bytes()).hexdigest()
        if resolved_path.is_file()
        else ""
    )
    return SourceReferenceResult(
        declared_ref=reference,
        root_key=root_key,
        resolved_path=resolved_path,
        relative_path=relative_path,
        fragment_kind=cast(Literal["none", "symbol", "section"], fragment_kind),
        fragment_value=fragment_value,
        sha256=digest,
        parser_match_count=match_count,
    )


def _dependency_root_for_paths(
    spec: RunBundleSpec,
    source: Path,
    target: Path,
) -> tuple[Literal["workspace", "agent_canon"], Path]:
    canon = ROOT.resolve()
    workspace = spec.workspace_root.resolve()
    if source.is_relative_to(canon) and target.is_relative_to(canon):
        return "agent_canon", canon
    if source.is_relative_to(workspace) and target.is_relative_to(workspace):
        return "workspace", workspace
    raise ValueError("dependency endpoints resolve to different canonical roots")


def _canonical_dependency_rows(root: Path) -> tuple[tuple[str, str, str, str], ...]:
    client = GraphClient(root, CANONICAL_GRAPH_EXECUTABLE)
    try:
        status = client.status()
        integration = status.payload.get("integration_record")
        if status.status != "fresh" or not isinstance(integration, Mapping):
            raise RuntimeError(
                "canonical dependency graph is not verified and fresh: "
                f"status={status.status} reason={status.payload.get('reason')}"
            )
        integration_fields = cast(Mapping[str, object], integration)
        if (
            integration_fields.get("verified") is not True
            or integration_fields.get("profile") != "default"
            or integration_fields.get("source_snapshot_profile") != "parent"
        ):
            raise RuntimeError("canonical dependency graph integration is invalid")
        response = client.query(
            all=True,
            relation="dependency",
            direction="both",
            depth=0,
        )
        if response.status != "fresh":
            raise RuntimeError(
                "canonical dependency query is not fresh: "
                f"status={response.status} reason={response.payload.get('reason')}"
            )
        return tuple(
            (fact.direction, fact.kind, fact.source, fact.target)
            for fact in response.dependency_facts
        )
    except GraphClientError as error:
        raise RuntimeError(f"canonical dependency graph failed: {error}") from error


def _dependency_reference_result(
    spec: RunBundleSpec,
    reference: str,
    rows_by_root: dict[Path, tuple[tuple[str, str, str, str], ...]],
) -> DependencyReferenceResult:
    prefix, remainder = reference.split(":repo:", 1)
    direction, kind = prefix.removeprefix("header:").split(":", 1)
    source_value, target_value = remainder.split("->repo:", 1)
    source_ref = f"repo:{source_value}"
    target_ref = f"repo:{target_value}"
    _source_key, source, _source_relative = _resolved_source_path(spec, source_ref)
    _target_key, target, _target_relative = _resolved_source_path(spec, target_ref)
    root_key, dependency_root = _dependency_root_for_paths(spec, source, target)
    source_path = PurePosixPath(source.relative_to(dependency_root).as_posix())
    target_path = PurePosixPath(target.relative_to(dependency_root).as_posix())
    normalized_key = (
        f"header:{direction}:{kind}:repo:{source_path.as_posix()}"
        f"->repo:{target_path.as_posix()}"
    )
    rows = rows_by_root.get(dependency_root)
    if rows is None:
        rows = _canonical_dependency_rows(dependency_root)
        rows_by_root[dependency_root] = rows
    match_count = sum(
        row == (direction, kind, source_path.as_posix(), target_path.as_posix())
        for row in rows
    )
    return DependencyReferenceResult(
        declared_ref=reference,
        dependency_root_key=root_key,
        normalized_key=normalized_key,
        source_path=source_path,
        target_path=target_path,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()
        if source.is_file()
        else "",
        target_sha256=hashlib.sha256(target.read_bytes()).hexdigest()
        if target.is_file()
        else "",
        graph_match_count=match_count,
    )


def _distinct_packet_references(
    packet: ActiveDesignPacketValue,
    field: str,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            reference
            for _section, _index, reference in _packet_references(packet, field)
        )
    )


def build_active_design_reference_context(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
    workflow_family: Mapping[str, object] | None,
    *,
    artifact_names: tuple[str, ...],
) -> ActiveDesignReferenceContext:
    """Construct the sole authoritative active-design reference projection."""
    del workflow_family
    role_output_projections = tuple(
        RoleOutputProjection(
            role_ref=f"role:{role.id}",
            output_refs=tuple(
                f"artifact:{output}"
                for output in selected_role_outputs(spec.config, role, packet)
            ),
        )
        for role in spec.roles
    )
    role_outputs = {
        projection.role_ref: projection.output_refs
        for projection in role_output_projections
    }
    reviewer_refs = tuple(
        dict.fromkeys(
            reference
            for _section, _index, reference in _packet_references(
                packet,
                "reviewer_refs",
            )
        )
    )
    review_outputs = {
        f"artifact:{packet.design_review_artifact}",
        f"artifact:{packet.document_flow_review_artifact}",
    }
    reviewer_projections: list[ReviewerArtifactProjection] = []
    for reviewer_ref in reviewer_refs:
        matches = tuple(
            output
            for output in role_outputs.get(reviewer_ref, ())
            if output in review_outputs
        )
        if len(matches) == 1:
            reviewer_projections.append(
                ReviewerArtifactProjection(reviewer_ref, matches[0])
            )
    source_refs = list(_distinct_packet_references(packet, "source_refs"))
    source_refs.extend(
        clause.source_ref
        for clause in packet.clause_registry
        if clause.source_ref not in source_refs
    )
    source_results = tuple(_source_reference_result(spec, ref) for ref in source_refs)
    dependency_refs = tuple(
        reference
        for reference in _distinct_packet_references(packet, "dependency_refs")
        if reference.startswith("header:")
    )
    rows_by_root: dict[Path, tuple[tuple[str, str, str, str], ...]] = {}
    dependency_results = tuple(
        _dependency_reference_result(spec, reference, rows_by_root)
        for reference in dependency_refs
    )
    planned_paths = tuple(
        PurePosixPath(path)
        for path in (
            *artifact_names,
            AUTHORITY_FILE_NAME,
            authority_baseline_path(Path(AUTHORITY_FILE_NAME)).name,
        )
    )
    output_results = tuple(
        OutputReferenceResult(
            output_ref=reference,
            relative_path=PurePosixPath(reference.removeprefix("artifact:")),
            planned_count=planned_paths.count(
                PurePosixPath(reference.removeprefix("artifact:"))
            ),
        )
        for reference in _distinct_packet_references(packet, "output_refs")
    )
    return ActiveDesignReferenceContext(
        workspace_root=spec.workspace_root.resolve(),
        report_dir=spec.report_dir.resolve(),
        source_results=source_results,
        dependency_results=dependency_results,
        role_output_projections=role_output_projections,
        reviewer_artifact_projections=tuple(reviewer_projections),
        clause_results=tuple(
            ClauseReferenceResult(clause.clause_id, clause.source_ref)
            for clause in packet.clause_registry
        ),
        output_results=output_results,
        planned_output_paths=frozenset(planned_paths),
    )


def _packet_entry_mapping(entry: ActiveDesignPacketEntry) -> dict[str, object]:
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


def active_design_packet_mapping(packet: ActiveDesignPacketValue) -> dict[str, object]:
    """Return the exact manifest/config packet mapping."""
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
            section: _packet_entry_mapping(entry)
            for section, entry in packet.section_entries()
        },
    }


def active_design_reference_projection_mapping(
    context: ActiveDesignReferenceContext,
) -> dict[str, object]:
    """Return the exact persisted reference projection without absolute paths."""
    return {
        "source_results": [
            {
                "declared_ref": result.declared_ref,
                "root_key": result.root_key,
                "relative_path": result.relative_path.as_posix(),
                "fragment_kind": result.fragment_kind,
                "fragment_value": result.fragment_value,
                "sha256": result.sha256,
                "parser_match_count": result.parser_match_count,
            }
            for result in context.source_results
        ],
        "dependency_results": [
            {
                "declared_ref": result.declared_ref,
                "dependency_root_key": result.dependency_root_key,
                "normalized_key": result.normalized_key,
                "source_path": result.source_path.as_posix(),
                "target_path": result.target_path.as_posix(),
                "source_sha256": result.source_sha256,
                "target_sha256": result.target_sha256,
                "graph_match_count": result.graph_match_count,
            }
            for result in context.dependency_results
        ],
        "role_output_projections": [
            {
                "role_ref": result.role_ref,
                "output_refs": list(result.output_refs),
            }
            for result in context.role_output_projections
        ],
        "reviewer_artifact_projections": [
            {
                "reviewer_ref": result.reviewer_ref,
                "review_artifact_ref": result.review_artifact_ref,
            }
            for result in context.reviewer_artifact_projections
        ],
        "clause_results": [
            {"clause_id": result.clause_id, "source_ref": result.source_ref}
            for result in context.clause_results
        ],
        "output_results": [
            {
                "output_ref": result.output_ref,
                "relative_path": result.relative_path.as_posix(),
                "planned_count": result.planned_count,
            }
            for result in context.output_results
        ],
        "planned_output_paths": sorted(
            path.as_posix() for path in context.planned_output_paths
        ),
    }


def _encoded_violation_component(value: str) -> str:
    return quote(
        value, safe="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._/-"
    )


def render_active_design_packet_violation(
    violation: ActiveDesignPacketViolation,
) -> str:
    """Render the sole closed public active-packet blocker grammar."""
    if isinstance(violation, ManifestPacketViolation):
        if violation.kind == "manifest_missing":
            return "team_manifest.yaml:missing"
        if violation.kind == "manifest_invalid":
            return "team_manifest.yaml:active_design_packet_field_invalid:manifest"
        if violation.kind == "packet_missing":
            return "team_manifest.yaml:active_design_packet_missing"
        if violation.field is None:
            raise ValueError("manifest packet violation requires a field")
        field = _encoded_violation_component(violation.field)
        if violation.kind == "field_missing":
            return f"team_manifest.yaml:active_design_packet_field_missing:{field}"
        if violation.kind == "field_invalid":
            return f"team_manifest.yaml:active_design_packet_field_invalid:{field}"
        if violation.kind == "schema_unknown":
            if violation.observed_schema is None:
                raise ValueError("schema violation requires observed_schema")
            return (
                "team_manifest.yaml:active_design_packet_schema_unknown:"
                + _encoded_violation_component(violation.observed_schema)
            )
        if violation.kind == "path_outside_bundle":
            return (
                f"team_manifest.yaml:active_design_packet_path_outside_bundle:{field}"
            )
        raise ValueError(f"unknown manifest packet violation: {violation.kind}")
    if isinstance(violation, ReferencePacketViolation):
        return (
            "team_manifest.yaml:active_design_packet_reference_invalid:"
            f"{violation.section}:{violation.field}:{violation.input_index}:"
            f"{violation.reason}"
        )
    if isinstance(violation, DesignArtifactViolation):
        path = _encoded_violation_component(violation.artifact_path.as_posix())
        if violation.reason == "section_empty_or_missing":
            if violation.section_slug is None:
                raise ValueError("section violation requires section_slug")
            return f"{path}:section_empty_or_missing:{_encoded_violation_component(violation.section_slug)}"
        if violation.section_slug is not None:
            raise ValueError("non-section violation cannot carry section_slug")
        return f"{path}:{violation.reason}"
    return (
        f"{_encoded_violation_component(violation.artifact_path.as_posix())}:"
        f"{violation.reason}"
    )


def _reference_semantic_violations(
    packet: ActiveDesignPacketValue,
    context: ActiveDesignReferenceContext,
) -> list[ActiveDesignPacketViolation]:
    violations: list[ActiveDesignPacketViolation] = []
    clause_ids = {result.clause_id for result in context.clause_results}
    role_refs = {result.role_ref for result in context.role_output_projections}
    reviewer_map = {
        result.reviewer_ref: result.review_artifact_ref
        for result in context.reviewer_artifact_projections
    }
    distinct_reviewer_refs = _distinct_packet_references(packet, "reviewer_refs")
    role_output_map = {
        result.role_ref: result.output_refs
        for result in context.role_output_projections
    }
    review_artifacts = {
        f"artifact:{packet.design_review_artifact}",
        f"artifact:{packet.document_flow_review_artifact}",
    }
    invalid_reviewer_refs = {
        reviewer
        for reviewer in distinct_reviewer_refs
        if len(
            tuple(
                output
                for output in role_output_map.get(reviewer, ())
                if output in review_artifacts
            )
        )
        != 1
    }
    required_review_artifacts = [f"artifact:{packet.design_review_artifact}"]
    if packet.document_flow_required:
        required_review_artifacts.append(
            f"artifact:{packet.document_flow_review_artifact}"
        )
    for artifact in required_review_artifacts:
        matching_reviewers = tuple(
            reviewer
            for reviewer, projected_artifact in reviewer_map.items()
            if projected_artifact == artifact
        )
        if len(matching_reviewers) != 1:
            invalid_reviewer_refs.update(matching_reviewers or distinct_reviewer_refs)
    source_map = {result.declared_ref: result for result in context.source_results}
    dependency_map = {
        result.declared_ref: result for result in context.dependency_results
    }
    output_map = {result.output_ref: result for result in context.output_results}
    for section, entry in packet.section_entries():
        for index, clause in enumerate(entry.clause_refs):
            if clause not in clause_ids:
                violations.append(
                    ReferencePacketViolation(
                        section,
                        "clause_refs",
                        index,
                        "clause_unknown",
                        (1, ACTIVE_DESIGN_SECTIONS.index(section), 0, index),
                    )
                )
        for index, owner in enumerate(entry.owner_refs):
            if owner not in role_refs:
                violations.append(
                    ReferencePacketViolation(
                        section,
                        "owner_refs",
                        index,
                        "owner_unknown",
                        (1, ACTIVE_DESIGN_SECTIONS.index(section), 1, index),
                    )
                )
        for index, source in enumerate(entry.source_refs):
            result = source_map.get(source)
            reason = None
            if result is None or not result.sha256:
                reason = "source_missing"
            elif result.parser_match_count != 1:
                reason = "source_fragment_mismatch"
            if reason is not None:
                violations.append(
                    ReferencePacketViolation(
                        section,
                        "source_refs",
                        index,
                        reason,
                        (1, ACTIVE_DESIGN_SECTIONS.index(section), 2, index),
                    )
                )
        for index, dependency in enumerate(entry.dependency_refs):
            if dependency.startswith("entry:"):
                continue
            result = dependency_map.get(dependency)
            if result is None or result.graph_match_count != 1:
                violations.append(
                    ReferencePacketViolation(
                        section,
                        "dependency_refs",
                        index,
                        "dependency_edge_missing",
                        (1, ACTIVE_DESIGN_SECTIONS.index(section), 3, index),
                    )
                )
        for index, output in enumerate(entry.output_refs):
            result = output_map.get(output)
            if result is None or result.planned_count != 1:
                violations.append(
                    ReferencePacketViolation(
                        section,
                        "output_refs",
                        index,
                        "output_missing",
                        (1, ACTIVE_DESIGN_SECTIONS.index(section), 4, index),
                    )
                )
        for index, reviewer in enumerate(entry.reviewer_refs):
            if (
                reviewer in invalid_reviewer_refs
                or reviewer_map.get(reviewer) not in review_artifacts
            ):
                violations.append(
                    ReferencePacketViolation(
                        section,
                        "reviewer_refs",
                        index,
                        "reviewer_output_mismatch",
                        (1, ACTIVE_DESIGN_SECTIONS.index(section), 5, index),
                    )
                )
    return violations


def _design_artifact_violations(
    packet: ActiveDesignPacketValue,
    report_dir: Path,
) -> list[ActiveDesignPacketViolation]:
    path = report_dir / packet.design_artifact
    relative = PurePosixPath(packet.design_artifact)
    if not path.is_file() or path.is_symlink():
        return [DesignArtifactViolation(relative, "missing", None, (2, 0, 0, 0))]
    text = path.read_text(encoding="utf-8")
    violations: list[ActiveDesignPacketViolation] = []
    if is_placeholder_only_section(text):
        violations.append(
            DesignArtifactViolation(
                relative, "template_or_placeholder_remaining", None, (2, 0, 0, 0)
            )
        )
    for index, (heading, slug) in enumerate(
        (
            ("## Abstract Design Frame", "abstract_design_frame"),
            ("## Implementation Source Packet", "implementation_source_packet"),
            ("## Design Side-Effect Map", "design_side_effect_map"),
            ("## Design-To-Implementation Trace", "design-to-implementation_trace"),
        ),
        start=1,
    ):
        if not section_has_content(text, heading):
            violations.append(
                DesignArtifactViolation(
                    relative, "section_empty_or_missing", slug, (2, 0, index, 0)
                )
            )
    return violations


def _review_artifact_violations(
    report_dir: Path,
    packet: ActiveDesignPacketValue,
    review_artifact: str,
    order: int,
) -> list[ActiveDesignPacketViolation]:
    review_path = report_dir / review_artifact
    relative = PurePosixPath(review_artifact)
    if not review_path.is_file() or review_path.is_symlink():
        return [
            ReviewArtifactViolation(
                relative, "design_artifact_path_missing", (order, 0, 0, 0)
            )
        ]
    design_path = report_dir / packet.design_artifact
    expected_sha = (
        hashlib.sha256(design_path.read_bytes()).hexdigest()
        if design_path.is_file()
        else ""
    )
    identity = parse_review_identity(review_path.read_text(encoding="utf-8"))
    violations: list[ActiveDesignPacketViolation] = []
    if identity.design_artifact_path is None:
        violations.append(
            ReviewArtifactViolation(
                relative, "design_artifact_path_missing", (order, 0, 0, 0)
            )
        )
    elif identity.design_artifact_path != packet.design_artifact:
        violations.append(
            ReviewArtifactViolation(
                relative, "design_artifact_path_mismatch", (order, 0, 1, 0)
            )
        )
    if identity.review_target_sha256 is None:
        violations.append(
            ReviewArtifactViolation(
                relative, "review_target_sha256_missing", (order, 1, 0, 0)
            )
        )
    elif identity.review_target_sha256 != expected_sha:
        violations.append(
            ReviewArtifactViolation(
                relative, "review_target_sha256_mismatch", (order, 1, 1, 0)
            )
        )
    if not identity.decision_approved:
        violations.append(
            ReviewArtifactViolation(relative, "decision_not_approve", (order, 2, 0, 0))
        )
    return violations


def validate_materialized_active_design_packet(
    value: ActiveDesignPacketValue,
    context: ActiveDesignReferenceContext,
    *,
    gate: Literal["materialization", "design", "document_flow", "implementation"],
) -> tuple[ActiveDesignPacketViolation, ...]:
    """Validate shared packet semantics without decoding or reparsing its projection."""
    violations = _reference_semantic_violations(value, context)
    if gate in {"design", "implementation"}:
        violations.extend(_design_artifact_violations(value, context.report_dir))
        if not any(
            isinstance(item, DesignArtifactViolation) and item.reason == "missing"
            for item in violations
        ):
            violations.extend(
                _review_artifact_violations(
                    context.report_dir,
                    value,
                    value.design_review_artifact,
                    3,
                )
            )
            if value.document_flow_required:
                violations.extend(
                    _review_artifact_violations(
                        context.report_dir,
                        value,
                        value.document_flow_review_artifact,
                        4,
                    )
                )
    elif gate == "document_flow" and value.document_flow_required:
        violations.extend(
            _review_artifact_violations(
                context.report_dir,
                value,
                value.document_flow_review_artifact,
                4,
            )
        )
    return tuple(sorted(violations, key=lambda item: item.order_key))


def _manifest_violation(
    kind: str,
    field: str | None = None,
    observed_schema: str | None = None,
    order: int = 0,
) -> ManifestPacketViolation:
    return ManifestPacketViolation(kind, field, observed_schema, (0, order, 0, 0))


def _projection_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(field)
    mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        raise ValueError(field)
    return cast(dict[str, object], mapping)


def _projection_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(field)
    return cast(list[object], value)


def _projection_string(mapping: Mapping[str, object], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str):
        raise ValueError(field)
    return value


def _projection_int(mapping: Mapping[str, object], field: str) -> int:
    value = mapping.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(field)
    return value


def _projection_optional_string(
    mapping: Mapping[str, object],
    field: str,
) -> str | None:
    value = mapping.get(field)
    if value is not None and not isinstance(value, str):
        raise ValueError(field)
    return value


def _loader_reference_violation(
    packet: ActiveDesignPacketValue,
    declared_ref: str,
    reason: str,
) -> ReferencePacketViolation:
    for field in ("source_refs", "dependency_refs", "output_refs"):
        for section, index, reference in _packet_references(packet, field):
            if reference == declared_ref:
                return ReferencePacketViolation(
                    section,
                    field,
                    index,
                    reason,
                    (
                        1,
                        ACTIVE_DESIGN_SECTIONS.index(section),
                        ACTIVE_DESIGN_REFERENCE_FIELDS.index(field),
                        index,
                    ),
                )
    clause = next(
        (item for item in packet.clause_registry if item.source_ref == declared_ref),
        None,
    )
    if clause is not None:
        for section, entry in packet.section_entries():
            if clause.clause_id in entry.clause_refs:
                index = entry.clause_refs.index(clause.clause_id)
                return ReferencePacketViolation(
                    section,
                    "clause_refs",
                    index,
                    reason,
                    (1, ACTIVE_DESIGN_SECTIONS.index(section), 0, index),
                )
    return ReferencePacketViolation(
        "abstract_design_frame",
        "source_refs",
        0,
        "projection_mismatch",
        (1, 0, 2, 0),
    )


def _load_source_results(
    packet: ActiveDesignPacketValue,
    rows: object,
    workspace_root: Path,
    report_dir: Path,
) -> tuple[tuple[SourceReferenceResult, ...], list[ActiveDesignPacketViolation]]:
    results: list[SourceReferenceResult] = []
    violations: list[ActiveDesignPacketViolation] = []
    for raw in _projection_list(rows, "source_results"):
        row = _projection_mapping(raw, "source_results[]")
        declared_ref = _projection_string(row, "declared_ref")
        root_key = _projection_string(row, "root_key")
        relative = PurePosixPath(_projection_string(row, "relative_path"))
        if root_key == "workspace":
            base = workspace_root
        elif root_key == "agent_canon":
            base = ROOT.resolve()
        elif root_key == "artifact":
            base = report_dir
        else:
            raise ValueError("source_results[].root_key")
        resolved = (base / Path(relative.as_posix())).resolve()
        if not resolved.is_relative_to(base.resolve()) or resolved.is_symlink():
            violations.append(
                _loader_reference_violation(packet, declared_ref, "source_missing")
            )
        persisted_sha = _projection_string(row, "sha256")
        current_sha = (
            hashlib.sha256(resolved.read_bytes()).hexdigest()
            if resolved.is_file()
            else ""
        )
        if current_sha != persisted_sha:
            violations.append(
                _loader_reference_violation(
                    packet,
                    declared_ref,
                    "source_digest_mismatch" if current_sha else "source_missing",
                )
            )
        fragment_kind = _projection_string(row, "fragment_kind")
        if fragment_kind not in {"none", "symbol", "section"}:
            raise ValueError("source_results[].fragment_kind")
        results.append(
            SourceReferenceResult(
                declared_ref=declared_ref,
                root_key=root_key,
                resolved_path=resolved,
                relative_path=relative,
                fragment_kind=cast(Literal["none", "symbol", "section"], fragment_kind),
                fragment_value=_projection_optional_string(row, "fragment_value"),
                sha256=persisted_sha,
                parser_match_count=_projection_int(row, "parser_match_count"),
            )
        )
    return tuple(results), violations


def _load_dependency_results(
    packet: ActiveDesignPacketValue,
    rows: object,
    workspace_root: Path,
) -> tuple[tuple[DependencyReferenceResult, ...], list[ActiveDesignPacketViolation]]:
    results: list[DependencyReferenceResult] = []
    violations: list[ActiveDesignPacketViolation] = []
    for raw in _projection_list(rows, "dependency_results"):
        row = _projection_mapping(raw, "dependency_results[]")
        declared_ref = _projection_string(row, "declared_ref")
        root_key = _projection_string(row, "dependency_root_key")
        if root_key == "workspace":
            base = workspace_root
        elif root_key == "agent_canon":
            base = ROOT.resolve()
        else:
            raise ValueError("dependency_results[].dependency_root_key")
        source_path = PurePosixPath(_projection_string(row, "source_path"))
        target_path = PurePosixPath(_projection_string(row, "target_path"))
        source = (base / source_path.as_posix()).resolve()
        target = (base / target_path.as_posix()).resolve()
        source_sha = _projection_string(row, "source_sha256")
        target_sha = _projection_string(row, "target_sha256")
        current_source = (
            hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else ""
        )
        current_target = (
            hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else ""
        )
        if current_source != source_sha or current_target != target_sha:
            violations.append(
                _loader_reference_violation(
                    packet, declared_ref, "source_digest_mismatch"
                )
            )
        results.append(
            DependencyReferenceResult(
                declared_ref=declared_ref,
                dependency_root_key=root_key,
                normalized_key=_projection_string(row, "normalized_key"),
                source_path=source_path,
                target_path=target_path,
                source_sha256=source_sha,
                target_sha256=target_sha,
                graph_match_count=_projection_int(row, "graph_match_count"),
            )
        )
    return tuple(results), violations


def _load_role_projections(rows: object) -> tuple[RoleOutputProjection, ...]:
    results: list[RoleOutputProjection] = []
    for raw in _projection_list(rows, "role_output_projections"):
        row = _projection_mapping(raw, "role_output_projections[]")
        outputs = tuple(
            _projection_string({"value": value}, "value")
            for value in _projection_list(row.get("output_refs"), "output_refs")
        )
        results.append(
            RoleOutputProjection(_projection_string(row, "role_ref"), outputs)
        )
    return tuple(results)


def _load_reviewer_projections(rows: object) -> tuple[ReviewerArtifactProjection, ...]:
    return tuple(
        ReviewerArtifactProjection(
            _projection_string(row, "reviewer_ref"),
            _projection_string(row, "review_artifact_ref"),
        )
        for raw in _projection_list(rows, "reviewer_artifact_projections")
        if (row := _projection_mapping(raw, "reviewer_artifact_projections[]"))
    )


def _load_clause_results(rows: object) -> tuple[ClauseReferenceResult, ...]:
    return tuple(
        ClauseReferenceResult(
            _projection_string(row, "clause_id"),
            _projection_string(row, "source_ref"),
        )
        for raw in _projection_list(rows, "clause_results")
        if (row := _projection_mapping(raw, "clause_results[]"))
    )


def _load_output_results(rows: object) -> tuple[OutputReferenceResult, ...]:
    return tuple(
        OutputReferenceResult(
            _projection_string(row, "output_ref"),
            PurePosixPath(_projection_string(row, "relative_path")),
            _projection_int(row, "planned_count"),
        )
        for raw in _projection_list(rows, "output_results")
        if (row := _projection_mapping(raw, "output_results[]"))
    )


def load_materialized_active_design_packet(
    report_dir: Path,
) -> MaterializedActiveDesignPacketResult:
    """Load one persisted packet and projection without consulting live config."""
    manifest_path = report_dir / "team_manifest.yaml"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return MaterializedActiveDesignPacketResult(
            None,
            None,
            (_manifest_violation("manifest_missing"),),
        )
    try:
        parsed: object = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return MaterializedActiveDesignPacketResult(
            None,
            None,
            (_manifest_violation("manifest_invalid"),),
        )
    if not isinstance(parsed, dict):
        return MaterializedActiveDesignPacketResult(
            None,
            None,
            (_manifest_violation("manifest_invalid"),),
        )
    parsed_mapping = cast(dict[object, object], parsed)
    raw_run = parsed_mapping.get("run")
    if not isinstance(raw_run, dict):
        return MaterializedActiveDesignPacketResult(
            None,
            None,
            (_manifest_violation("manifest_invalid"),),
        )
    run_mapping = cast(dict[object, object], raw_run)
    if not all(isinstance(key, str) for key in run_mapping):
        return MaterializedActiveDesignPacketResult(
            None,
            None,
            (_manifest_violation("manifest_invalid"),),
        )
    run = cast(dict[str, object], run_mapping)
    if "active_design_packet" not in run:
        return MaterializedActiveDesignPacketResult(
            None,
            None,
            (_manifest_violation("packet_missing"),),
        )
    try:
        packet = _decode_active_design_packet(
            run["active_design_packet"],
            field_prefix="run.active_design_packet",
        )
    except ActiveDesignPacketInputError as error:
        field = error.field.removeprefix("run.active_design_packet.")
        kind = {
            "missing_field": "field_missing",
            "unknown_schema": "schema_unknown",
        }.get(error.code, "field_invalid")
        observed_schema = None
        if error.code == "unknown_schema" and isinstance(
            run["active_design_packet"], dict
        ):
            schema = cast(dict[str, object], run["active_design_packet"]).get("schema")
            observed_schema = schema if isinstance(schema, str) else ""
        return MaterializedActiveDesignPacketResult(
            None,
            None,
            (_manifest_violation(kind, field, observed_schema),),
        )
    try:
        workspace_root = Path(_projection_string(run, "workspace_root")).resolve()
        persisted_report_dir = Path(_projection_string(run, "report_dir")).resolve()
        if persisted_report_dir != report_dir.resolve():
            raise ValueError("run.report_dir")
        projection = _projection_mapping(
            run.get("active_design_packet_reference_projection"),
            "active_design_packet_reference_projection",
        )
        expected_keys = {
            "source_results",
            "dependency_results",
            "role_output_projections",
            "reviewer_artifact_projections",
            "clause_results",
            "output_results",
            "planned_output_paths",
        }
        if set(projection) != expected_keys:
            raise ValueError("active_design_packet_reference_projection")
        source_results, source_violations = _load_source_results(
            packet,
            projection["source_results"],
            workspace_root,
            persisted_report_dir,
        )
        dependency_results, dependency_violations = _load_dependency_results(
            packet,
            projection["dependency_results"],
            workspace_root,
        )
        context = ActiveDesignReferenceContext(
            workspace_root=workspace_root,
            report_dir=persisted_report_dir,
            source_results=source_results,
            dependency_results=dependency_results,
            role_output_projections=_load_role_projections(
                projection["role_output_projections"]
            ),
            reviewer_artifact_projections=_load_reviewer_projections(
                projection["reviewer_artifact_projections"]
            ),
            clause_results=_load_clause_results(projection["clause_results"]),
            output_results=_load_output_results(projection["output_results"]),
            planned_output_paths=frozenset(
                PurePosixPath(_projection_string({"path": value}, "path"))
                for value in _projection_list(
                    projection["planned_output_paths"],
                    "planned_output_paths",
                )
            ),
        )
    except (OSError, UnicodeError, ValueError, TypeError):
        return MaterializedActiveDesignPacketResult(
            packet,
            None,
            (
                _manifest_violation(
                    "field_invalid",
                    "active_design_packet_reference_projection",
                ),
            ),
        )
    violations = tuple(
        sorted(
            [*source_violations, *dependency_violations],
            key=lambda item: item.order_key,
        )
    )
    return MaterializedActiveDesignPacketResult(packet, context, violations)


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
    skill_list = format_public_skill_list(skill_names)
    dynamic_candidates = dynamic_skill_candidate_names(selected_skills)
    return (
        "REPO_TOOL_ROUTING_POLICY=run.repo_tool_routing_policy",
        f"REPO_TOOL_COMMAND_PACKET_COMMAND={REPO_TOOL_ROUTING_SHOW_COMMAND_TEMPLATE}",
        f"REPO_TOOL_SELECTED_SKILLS={skill_list}",
        f"REPO_TOOL_DYNAMIC_CANDIDATES={format_public_skill_list(dynamic_candidates)}",
        f"REPO_TOOL_ROUTING_SOURCE={REPO_TOOL_ROUTING_POLICY_SOURCE}",
        f"REPO_TOOL_ROUTING_OWNER={REPO_TOOL_ROUTING_OWNER}",
        f"REPO_TOOL_ROUTING_ROUTE_BASIS={REPO_TOOL_ROUTING_ROUTE_BASIS}",
        f"REPO_TOOL_ROUTING_EXECUTION_MODE={REPO_TOOL_ROUTING_EXECUTION_MODE}",
        f"REPO_TOOL_ROUTING_SEQUENCE={','.join(REPO_TOOL_ROUTING_SEQUENCE)}",
        f"REPO_TOOL_ROUTING_STAGE_FIELDS={','.join(REPO_TOOL_ROUTING_STAGE_FIELDS)}",
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
            isinstance(role_id, str) for role_id in cast(list[object], always_on_raw)
        ):
            violations.append((family_id, "malformed-always-on"))
            continue
        if not isinstance(specialists_raw, list) or not all(
            isinstance(role_id, str) for role_id in cast(list[object], specialists_raw)
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
            expected_budget = (1, 1)
        elif family_id == "owner_bounded_change":
            if always_on != owner_bounded_always_on:
                violations.append((family_id, "owner-bounded-producer-core"))
            if "change_reviewer" not in specialists:
                violations.append((family_id, "change-reviewer-not-deferred"))
            expected_budget = (4, 2)
        else:
            if always_on != delivery_always_on:
                violations.append((family_id, "delivery-producer-core"))
            missing_reviews = deferred_delivery_reviews - set(specialists)
            if missing_reviews:
                violations.append((family_id, "reviewers-not-deferred"))
            expected_budget = (4, 2)
        if workflow_spawn_budget(catalog, family_id) != expected_budget:
            violations.append((family_id, "spawn-budget"))
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


def parse_agent_type_selections(
    raw_values: tuple[str, ...],
) -> tuple[AgentTypeSelection, ...]:
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
    waves = _as_mapping_tuple(
        topology.get("stage_waves"), "role_topology_defaults.stage_waves"
    )
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
    return tuple(slot for slot in slots if slot.role_id not in {"verifier", "auditor"})[
        :active_subagents
    ]


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
        f"WAVE-{index + 2}=" + ",".join(slot.executable_identity for slot in wave)
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


def selected_packet_artifact_paths(
    config: TeamConfig,
    packet: ActiveDesignPacketValue,
) -> dict[str, str]:
    """Map standard design artifact names to the selected packet outputs."""
    return {
        config.artifacts["design_brief"]: packet.design_artifact,
        config.artifacts["design_review"]: packet.design_review_artifact,
        config.artifacts["document_flow_review"]: packet.document_flow_review_artifact,
    }


def selected_role_outputs(
    config: TeamConfig,
    role: Role,
    packet: ActiveDesignPacketValue,
) -> tuple[str, ...]:
    """Return role outputs aligned with the selected design packet."""
    artifact_map = selected_packet_artifact_paths(config, packet)
    return tuple(artifact_map.get(output, output) for output in role.required_outputs)


def selected_artifact_name(
    config: TeamConfig,
    artifact_key: str,
    packet: ActiveDesignPacketValue,
) -> str:
    """Resolve one logical artifact key through the selected design packet."""
    artifact_name = config.artifacts[artifact_key]
    return selected_packet_artifact_paths(config, packet).get(
        artifact_name,
        artifact_name,
    )


def iter_artifacts(
    config: TeamConfig,
    roles: tuple[Role, ...],
    packet: ActiveDesignPacketValue,
) -> tuple[str, ...]:
    """Return unique artifact filenames in deterministic order."""
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
    active_design_packet: ActiveDesignPacketValue,
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
    active_packet = active_design_packet
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
                        f"run artifact:{artifact_key}; source=run.active_design_packet"
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
    """Return the workflow-family record selected for one run."""
    if not spec.workflow_family_id:
        return None
    if spec.task_catalog is None:
        raise RuntimeError("task catalog is required for workflow manifest rendering")
    return resolve_workflow_family(spec.task_catalog, spec.workflow_family_id)


def rendered_text_artifact(relative_path: str, text: str) -> RenderedArtifact:
    """Create one canonical UTF-8 run-bundle text artifact."""
    return RenderedArtifact(
        relative_path=PurePosixPath(relative_path),
        content=text.encode("utf-8"),
        mode=RUN_BUNDLE_FILE_MODE,
    )


def project_role_document_packets(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
) -> tuple[RoleDocumentPacket, ...]:
    """Project every selected role's immutable document packet."""
    return tuple(
        resolve_role_document_packet(
            spec.config,
            role,
            spec.report_dir,
            spec.workspace_root,
            packet,
        )
        for role in spec.roles
    )


def project_subagent_prompt_packets(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
    role_packets: tuple[RoleDocumentPacket, ...],
) -> tuple[SubagentPromptPacket, ...]:
    """Project one packet-bearing prompt value for every selected role."""
    documents_by_role = {value.role_id: value for value in role_packets}
    if tuple(documents_by_role) != tuple(role.id for role in spec.roles):
        raise RuntimeError(
            "role document packet projection disagrees with selected roles"
        )
    return tuple(
        SubagentPromptPacket(
            role_id=role.id,
            active_design_packet=packet,
            document_packet=documents_by_role[role.id],
            required_outputs=selected_role_outputs(spec.config, role, packet),
        )
        for role in spec.roles
    )


def project_template_artifacts(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
    *,
    artifact_names: tuple[str, ...],
    role_packets: tuple[RoleDocumentPacket, ...],
    prompt_packets: tuple[SubagentPromptPacket, ...],
) -> tuple[RenderedArtifact, ...]:
    """Render every template-owned run artifact entirely in memory."""
    role_ids = tuple(role.id for role in spec.roles)
    if tuple(value.role_id for value in role_packets) != role_ids:
        raise RuntimeError("role document packet order disagrees with selected roles")
    if tuple(value.role_id for value in prompt_packets) != role_ids:
        raise RuntimeError("subagent prompt packet order disagrees with selected roles")
    replacements = {
        "RUN_ID": spec.run_id,
        "TASK": spec.task,
        "OWNER": spec.owner,
        "CREATED_AT": spec.created_at_iso,
    }
    selected_templates = {
        packet.design_artifact: spec.config.artifacts["design_brief"],
        packet.design_review_artifact: spec.config.artifacts["design_review"],
        packet.document_flow_review_artifact: spec.config.artifacts[
            "document_flow_review"
        ],
    }
    return tuple(
        rendered_text_artifact(
            artifact,
            render_template(selected_templates.get(artifact, artifact), replacements),
        )
        for artifact in artifact_names
        if has_template(selected_templates.get(artifact, artifact))
    )


def project_verification_artifact(spec: RunBundleSpec) -> RenderedArtifact:
    """Project the canonical pending verification record."""
    return rendered_text_artifact(
        spec.config.artifacts["verification"],
        "\n".join(
            (
                f"run_id={spec.run_id}",
                f"task={spec.task}",
                f"owner={spec.owner}",
                f"created_at_utc={spec.created_at_iso}",
                "status=pending",
                "user_completion_report=locked",
                "closeout_gate_status=pending",
                "",
            )
        ),
    )


def project_authority_artifacts(
    spec: RunBundleSpec,
) -> tuple[RenderedArtifact, RenderedArtifact]:
    """Project task authority and its hash baseline from the same bytes."""
    authority_roles = {
        role.id: role.write_policy.mode not in {"read_only", "artifacts_only"}
        for role in spec.roles
    }
    authority_bytes = build_default_task_authority(
        run_id=spec.run_id,
        task=spec.task,
        roles=authority_roles,
    ).encode("utf-8")
    authority = RenderedArtifact(
        PurePosixPath(AUTHORITY_FILE_NAME),
        authority_bytes,
        RUN_BUNDLE_FILE_MODE,
    )
    baseline_name = authority_baseline_path(Path(AUTHORITY_FILE_NAME)).name
    baseline = RenderedArtifact(
        PurePosixPath(baseline_name),
        hash_baseline_bytes(authority_bytes),
        RUN_BUNDLE_FILE_MODE,
    )
    return authority, baseline


def project_initial_wave_row(
    spec: RunBundleSpec,
) -> Mapping[str, str] | None:
    """Project the sole initial wave row without mutating run artifacts."""
    if not spec.workflow_family_id:
        return None
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
        return None
    return initial_wave_gate_fields(
        initial_wave=initial_wave,
        active_subagents=active_subagents,
    )


def project_wave_ledger_artifacts(
    spec: RunBundleSpec,
    template_artifacts: tuple[RenderedArtifact, ...],
    *,
    monitoring_entries: MonitoringEntries,
    initial_wave_row: Mapping[str, str] | None,
) -> tuple[RenderedArtifact, ...]:
    """Project schedule and monitoring replacements through the shared renderer."""
    from workflow_monitor import render_monitoring_artifacts

    schedule_name = spec.config.artifacts["schedule"]
    monitoring_name = spec.config.artifacts["workflow_monitoring"]
    by_path = {value.relative_path.as_posix(): value for value in template_artifacts}
    try:
        schedule_text = by_path[schedule_name].content.decode("utf-8")
        monitoring_text = by_path[monitoring_name].content.decode("utf-8")
    except KeyError as exc:
        raise RuntimeError(
            f"missing monitoring template artifact: {exc.args[0]}"
        ) from exc
    schedule_text, monitoring_text = render_monitoring_artifacts(
        schedule_text=schedule_text,
        workflow_monitoring_text=monitoring_text,
        entries=monitoring_entries,
        initial_wave_row=initial_wave_row,
    )
    return (
        rendered_text_artifact(schedule_name, schedule_text),
        rendered_text_artifact(monitoring_name, monitoring_text),
    )


def enrich_runtime_measurement_input(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
    context: ActiveDesignReferenceContext,
    entries: MonitoringEntries,
) -> MonitoringEntries:
    """Attach immutable packet/source identity to the monitor-owned record."""
    packet_bytes = json.dumps(
        active_design_packet_mapping(packet),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    source_bytes = {
        result.declared_ref: len(result.resolved_path.read_bytes())
        for result in context.source_results
    }
    reviewer_ids = tuple(
        sorted(
            role.id
            for role in spec.roles
            if role.id.endswith("_reviewer")
            or role.id
            in {"reviewer", "verifier", "auditor", "docs_workflow_steward"}
        )
    )
    writer_ids = tuple(
        sorted(
            role.id
            for role in spec.roles
            if role.write_policy.mode not in {"read_only", "artifacts_only"}
        )
    )
    return replace(
        entries,
        responsibility_unit_id=entries.responsibility_unit_id or spec.run_id,
        packet_hash=hashlib.sha256(packet_bytes).hexdigest(),
        context_bytes_by_source=tuple(sorted(source_bytes.items())),
        writer_ids=entries.writer_ids or writer_ids,
        reviewer_ids=entries.reviewer_ids or reviewer_ids,
    )


def format_start_declaration(
    workflow_family_name: str,
    active_skills: tuple[str, ...],
    review_roles: tuple[str, ...],
) -> str:
    """Format the one start declaration shared by publication and CLI output."""
    return (
        f"workflow={workflow_family_name or 'Unspecified'}, "
        f"skills={','.join(active_skills) or '-'}, "
        f"review={','.join(review_roles) or '-'}"
    )


def create_run_bundle(spec: RunBundleSpec) -> RunBundleMaterialization:
    """Materialize one complete run bundle through the sole public delegator."""
    return _materialize_run_bundle(spec)


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


def _file_identity(value: os.stat_result) -> FileIdentity:
    return FileIdentity(
        st_dev=value.st_dev,
        st_ino=value.st_ino,
        st_uid=value.st_uid,
        st_gid=value.st_gid,
        st_mode=value.st_mode,
        st_nlink=value.st_nlink,
    )


def _same_report_root_identity(left: FileIdentity, right: FileIdentity) -> bool:
    """Compare stable root authority while allowing child-directory link changes."""
    return (
        left.st_dev,
        left.st_ino,
        left.st_uid,
        left.st_gid,
        left.st_mode,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_uid,
        right.st_gid,
        right.st_mode,
    )


def _identity_mapping(value: FileIdentity) -> dict[str, int]:
    return {
        "st_dev": value.st_dev,
        "st_ino": value.st_ino,
        "st_uid": value.st_uid,
        "st_gid": value.st_gid,
        "st_mode": value.st_mode,
        "st_nlink": value.st_nlink,
    }


def _identity_from_mapping(value: object) -> FileIdentity:
    if not isinstance(value, dict):
        raise ValueError("identity must be a mapping")
    mapping = cast(dict[object, object], value)
    expected = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink")
    if set(mapping) != set(expected):
        raise ValueError("identity fields disagree")
    fields: list[int] = []
    for key in expected:
        field = mapping[key]
        if not isinstance(field, int) or isinstance(field, bool):
            raise ValueError(f"identity field is not an integer: {key}")
        fields.append(field)
    return FileIdentity(*fields)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short write")
        offset += written


def _read_descriptor_bytes(descriptor: int, expected_size: int | None = None) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = expected_size
    while True:
        request_size = SHA256_READ_CHUNK_BYTES
        if remaining is not None:
            request_size = min(request_size, remaining + 1)
            if request_size == 0:
                break
        chunk = os.read(descriptor, request_size)
        if not chunk:
            break
        chunks.append(chunk)
        if remaining is not None:
            remaining -= len(chunk)
            if remaining < 0:
                break
    return b"".join(chunks)


def _canonical_lock_payload(identity: MaterializationLockIdentity) -> bytes:
    value = {
        "schema_version": identity.schema_version,
        "state": identity.state,
        "report_root_identity": _identity_mapping(identity.report_root_identity),
        "lock_file_identity": _identity_mapping(identity.lock_file_identity),
        "effective_uid": identity.effective_uid,
        "pid": identity.pid,
        "process_start_ticks": identity.process_start_ticks,
        "boot_id": identity.boot_id,
        "nonce": identity.nonce,
        "acquired_at": identity.acquired_at,
        "run_id": identity.run_id,
        "reuse_class": identity.reuse_class,
    }
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _process_start_ticks(pid: int) -> int | None:
    try:
        line = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return None
    close = line.rfind(")")
    if close < 0:
        raise RuntimeError("process stat is malformed")
    fields = line[close + 2 :].split()
    if len(fields) <= 19:
        raise RuntimeError("process stat lacks start ticks")
    return int(fields[19])


def _boot_id() -> str:
    value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    if not value:
        raise RuntimeError("kernel boot id is empty")
    return value


def _validate_lock_inode(
    identity: FileIdentity,
    *,
    report_root_identity: FileIdentity,
) -> None:
    if (
        not stat.S_ISREG(identity.st_mode)
        or identity.st_nlink != 1
        or identity.st_uid != os.geteuid()
        or stat.S_IMODE(identity.st_mode) != MATERIALIZATION_LOCK_MODE
        or identity.st_dev != report_root_identity.st_dev
    ):
        raise ValueError("foreign lock inode")


def _open_stable_report_root(report_root: Path) -> tuple[int, FileIdentity]:
    before = os.lstat(report_root)
    if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise ValueError("report root is not a direct directory")
    descriptor = os.open(
        report_root,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    try:
        opened = os.fstat(descriptor)
        after = os.lstat(report_root)
        if _file_identity(before) != _file_identity(opened) or _file_identity(
            opened
        ) != _file_identity(after):
            raise ValueError("report root identity changed")
        return descriptor, _file_identity(opened)
    except BaseException:
        os.close(descriptor)
        raise


def _materialization_failure(
    *,
    phase: MaterializationPhase,
    code: MaterializationErrorCode,
    target: Path,
    staging: Path | None = None,
    cause_code: MaterializationErrorCode | None = None,
    violations: tuple[ActiveDesignPacketViolation, ...] = (),
    rollback: RollbackResult | None = None,
) -> RunBundleMaterializationError:
    return RunBundleMaterializationError(
        phase=phase,
        code=code,
        cause_code=cause_code or code,
        target_path=target,
        staging_path=staging,
        violations=violations,
        rollback=rollback,
    )


def _lock_payload_reuse_class(
    payload: bytes,
    *,
    report_root_identity: FileIdentity,
    lock_identity: FileIdentity,
) -> LockReuseClass:
    try:
        decoded: object = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
        if not isinstance(decoded, dict):
            raise ValueError("lock payload is not a mapping")
        mapping = cast(dict[str, object], decoded)
        expected = {
            "schema_version",
            "state",
            "report_root_identity",
            "lock_file_identity",
            "effective_uid",
            "pid",
            "process_start_ticks",
            "boot_id",
            "nonce",
            "acquired_at",
            "run_id",
            "reuse_class",
        }
        if set(mapping) != expected:
            raise ValueError("lock payload fields disagree")
        root_value = _identity_from_mapping(mapping["report_root_identity"])
        lock_value = _identity_from_mapping(mapping["lock_file_identity"])
        if (
            not _same_report_root_identity(root_value, report_root_identity)
            or lock_value != lock_identity
        ):
            raise ValueError("lock payload identities disagree")
        if mapping["schema_version"] != MATERIALIZATION_LOCK_SCHEMA:
            raise ValueError("lock payload schema disagrees")
        if mapping["state"] != "held" or mapping["effective_uid"] != os.geteuid():
            raise ValueError("lock payload owner state disagrees")
        pid = mapping["pid"]
        start_ticks = mapping["process_start_ticks"]
        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or pid <= 0
            or not isinstance(start_ticks, int)
            or isinstance(start_ticks, bool)
            or start_ticks <= 0
        ):
            raise ValueError("lock process identity is invalid")
        nonce = mapping["nonce"]
        if not isinstance(nonce, str) or re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
            raise ValueError("lock nonce is invalid")
        reuse_class = mapping["reuse_class"]
        if not isinstance(reuse_class, str) or reuse_class not in {
            "first_acquisition",
            "released_file_reuse",
            "crash_stale_reuse",
        }:
            raise ValueError("lock reuse class is invalid")
        run_id = mapping["run_id"]
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("lock run id is invalid")
        acquired_at = mapping["acquired_at"]
        if not isinstance(acquired_at, str):
            raise ValueError("lock acquisition time is invalid")
        datetime.fromisoformat(acquired_at.replace("Z", "+00:00"))
        stored_boot_id = mapping["boot_id"]
        if not isinstance(stored_boot_id, str) or not stored_boot_id:
            raise ValueError("lock boot id is invalid")
        reconstructed = MaterializationLockIdentity(
            schema_version=MATERIALIZATION_LOCK_SCHEMA,
            state="held",
            report_root_identity=root_value,
            lock_file_identity=lock_value,
            effective_uid=os.geteuid(),
            pid=pid,
            process_start_ticks=start_ticks,
            boot_id=stored_boot_id,
            nonce=nonce,
            acquired_at=acquired_at,
            run_id=run_id,
            reuse_class=cast(LockReuseClass, reuse_class),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
        )
        if _canonical_lock_payload(reconstructed) != payload:
            raise ValueError("lock payload is not canonical")
        current_boot_id = _boot_id()
        live_ticks = (
            _process_start_ticks(pid) if stored_boot_id == current_boot_id else None
        )
        if (
            stored_boot_id != current_boot_id
            or live_ticks is None
            or live_ticks != start_ticks
        ):
            return "crash_stale_reuse"
        raise ValueError("held lock payload still names a live process")
    except (OSError, UnicodeError, ValueError, _DuplicateJsonKey, RuntimeError) as exc:
        raise ValueError("foreign lock payload") from exc


def _acquire_materialization_lock(
    *,
    report_root: Path,
    run_id: str,
) -> MaterializationLock:
    """Acquire and identify the persistent canonical materialization lock."""
    target = report_root / run_id
    root_descriptor: int | None = None
    descriptor: int | None = None
    try:
        root_descriptor, root_identity = _open_stable_report_root(report_root)
        reuse_class: LockReuseClass
        try:
            descriptor = os.open(
                MATERIALIZATION_LOCK_NAME,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                MATERIALIZATION_LOCK_MODE,
                dir_fd=root_descriptor,
            )
            reuse_class = "first_acquisition"
        except FileExistsError:
            before = os.stat(
                MATERIALIZATION_LOCK_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            descriptor = os.open(
                MATERIALIZATION_LOCK_NAME,
                os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=root_descriptor,
            )
            opened = os.fstat(descriptor)
            after = os.stat(
                MATERIALIZATION_LOCK_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            before_identity = _file_identity(before)
            opened_identity = _file_identity(opened)
            if before_identity != opened_identity or opened_identity != _file_identity(
                after
            ):
                raise ValueError("lock identity changed during open")
            _validate_lock_inode(opened_identity, report_root_identity=root_identity)
            reuse_class = "released_file_reuse"
        lock_identity = _file_identity(os.fstat(descriptor))
        _validate_lock_inode(lock_identity, report_root_identity=root_identity)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            code: MaterializationErrorCode = (
                "materialization_lock_busy"
                if exc.errno in {errno.EACCES, errno.EAGAIN}
                else "materialization_lock_failed"
            )
            raise _materialization_failure(
                phase="stage", code=code, target=target
            ) from exc
        path_identity = _file_identity(
            os.stat(
                MATERIALIZATION_LOCK_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        )
        descriptor_identity = _file_identity(os.fstat(descriptor))
        if path_identity != lock_identity or descriptor_identity != lock_identity:
            raise ValueError("lock identity changed after flock")
        payload = _read_descriptor_bytes(descriptor)
        if payload:
            reuse_class = _lock_payload_reuse_class(
                payload,
                report_root_identity=root_identity,
                lock_identity=lock_identity,
            )
        start_ticks = _process_start_ticks(os.getpid())
        if start_ticks is None:
            raise RuntimeError("current process start ticks are unavailable")
        acquired_at = (
            datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        )
        provisional = MaterializationLockIdentity(
            schema_version=MATERIALIZATION_LOCK_SCHEMA,
            state="held",
            report_root_identity=root_identity,
            lock_file_identity=lock_identity,
            effective_uid=os.geteuid(),
            pid=os.getpid(),
            process_start_ticks=start_ticks,
            boot_id=_boot_id(),
            nonce=secrets.token_hex(16),
            acquired_at=acquired_at,
            run_id=run_id,
            reuse_class=reuse_class,
            payload_sha256="",
        )
        held_payload = _canonical_lock_payload(provisional)
        identity = replace(
            provisional,
            payload_sha256=hashlib.sha256(held_payload).hexdigest(),
        )
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        _write_all(descriptor, held_payload)
        os.fsync(descriptor)
        if _read_descriptor_bytes(descriptor, len(held_payload)) != held_payload:
            raise RuntimeError("held lock payload verification failed")
        return MaterializationLock(
            path=report_root / MATERIALIZATION_LOCK_NAME,
            descriptor=descriptor,
            identity=identity,
        )
    except RunBundleMaterializationError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except ValueError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise _materialization_failure(
            phase="stage",
            code="materialization_lock_foreign",
            target=target,
        ) from exc
    except (OSError, RuntimeError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise _materialization_failure(
            phase="stage",
            code="materialization_lock_failed",
            target=target,
        ) from exc
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)


def _release_materialization_lock(lock: MaterializationLock) -> None:
    """Release an exact held lock while retaining its empty persistent inode."""
    descriptor = lock.descriptor
    try:
        root_descriptor, root_identity = _open_stable_report_root(lock.path.parent)
        try:
            path_identity = _file_identity(
                os.stat(
                    lock.path.name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
            )
            descriptor_identity = _file_identity(os.fstat(descriptor))
            if (
                not _same_report_root_identity(
                    root_identity, lock.identity.report_root_identity
                )
                or path_identity != lock.identity.lock_file_identity
                or descriptor_identity != lock.identity.lock_file_identity
            ):
                raise ValueError("lock release identity changed")
            _validate_lock_inode(path_identity, report_root_identity=root_identity)
            payload = _read_descriptor_bytes(descriptor)
            if (
                hashlib.sha256(payload).hexdigest() != lock.identity.payload_sha256
                or payload != _canonical_lock_payload(lock.identity)
            ):
                raise ValueError("lock release payload changed")
            os.ftruncate(descriptor, 0)
            os.fsync(descriptor)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(root_descriptor)
    except BaseException as exc:
        os.close(descriptor)
        raise RuntimeError("materialization lock release failed") from exc
    os.close(descriptor)


def _normalized_artifact_path(value: str | PurePosixPath) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or "\\" in path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"invalid run artifact path: {value}")
    return path


def _build_in_memory_artifact_set(
    *,
    planned_paths: tuple[str, ...],
    projected_artifacts: tuple[RenderedArtifact, ...],
) -> tuple[RenderedArtifact, ...]:
    """Validate and sort the complete in-memory artifact set."""
    normalized_planned = tuple(
        _normalized_artifact_path(path) for path in planned_paths
    )
    if len(set(normalized_planned)) != len(normalized_planned):
        raise ValueError("planned run artifact paths are not unique")
    by_path: dict[PurePosixPath, RenderedArtifact] = {}
    for artifact in projected_artifacts:
        path = _normalized_artifact_path(artifact.relative_path)
        if path in by_path:
            raise ValueError(f"duplicate projected artifact: {path.as_posix()}")
        if artifact.mode != RUN_BUNDLE_FILE_MODE:
            raise ValueError(f"invalid projected artifact mode: {path.as_posix()}")
        try:
            artifact.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"projected artifact is not UTF-8 text: {path.as_posix()}"
            ) from exc
        by_path[path] = replace(artifact, relative_path=path)
    planned_set = set(normalized_planned)
    if set(by_path) != planned_set:
        missing = sorted(path.as_posix() for path in planned_set - set(by_path))
        unexpected = sorted(path.as_posix() for path in set(by_path) - planned_set)
        raise ValueError(
            f"projected artifact set disagrees: missing={missing} unexpected={unexpected}"
        )
    return tuple(by_path[path] for path in sorted(by_path, key=PurePosixPath.as_posix))


def _artifact_digests(
    artifacts: tuple[RenderedArtifact, ...],
) -> tuple[ArtifactDigest, ...]:
    return tuple(
        ArtifactDigest(
            relative_path=artifact.relative_path,
            sha256=hashlib.sha256(artifact.content).hexdigest(),
        )
        for artifact in artifacts
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _tree_records(path: Path) -> tuple[tuple[str, int, int, str], ...]:
    records: list[tuple[str, int, int, str]] = []
    for candidate in sorted(
        path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()
    ):
        relative = candidate.relative_to(path).as_posix()
        status = os.lstat(candidate)
        if stat.S_ISDIR(status.st_mode):
            continue
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise ValueError(f"nonregular staged artifact: {relative}")
        payload = candidate.read_bytes()
        records.append(
            (
                relative,
                stat.S_IMODE(status.st_mode),
                len(payload),
                hashlib.sha256(payload).hexdigest(),
            )
        )
    return tuple(records)


def _tree_sha256(path: Path) -> str:
    lines = "".join(
        f"{relative}\t{mode:o}\t{size}\t{digest}\n"
        for relative, mode, size, digest in _tree_records(path)
    )
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _verify_staged_artifacts(
    stage: Path,
    artifacts: tuple[RenderedArtifact, ...],
) -> str:
    expected = tuple(
        (
            artifact.relative_path.as_posix(),
            artifact.mode,
            len(artifact.content),
            hashlib.sha256(artifact.content).hexdigest(),
        )
        for artifact in artifacts
    )
    observed = _tree_records(stage)
    if observed != expected:
        raise ValueError("staged artifact path/mode/size/digest verification failed")
    return _tree_sha256(stage)


class _StageArtifactSetError(RuntimeError):
    def __init__(
        self,
        *,
        code: Literal["staging_write_failed", "staging_verify_failed"],
        path: Path,
        cleanup: CleanupStatus,
    ) -> None:
        self.code: Literal["staging_write_failed", "staging_verify_failed"] = code
        self.path = path
        self.cleanup: CleanupStatus = cleanup
        super().__init__(code)


def _stage_artifact_set(
    *,
    report_root: Path,
    target: Path,
    run_id: str,
    artifacts: tuple[RenderedArtifact, ...],
) -> StagedArtifactSet:
    """Write and verify one complete private sibling staging tree."""
    del target
    stage: Path | None = None
    for _attempt in range(GENERATED_NAME_ATTEMPTS):
        candidate = report_root / (
            f".{run_id}.stage.{os.getpid()}.{secrets.token_hex(16)}"
        )
        try:
            candidate.mkdir(mode=PRIVATE_STAGE_MODE)
        except FileExistsError:
            continue
        stage = candidate
        break
    if stage is None:
        raise FileExistsError(errno.EEXIST, "staging name exhausted")
    phase: Literal["write", "verify"] = "write"
    initial_identity = _file_identity(os.lstat(stage))
    try:
        created_directories = {stage}
        for artifact in artifacts:
            output = stage.joinpath(*artifact.relative_path.parts)
            parent = output.parent
            missing: list[Path] = []
            while parent != stage and not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir(mode=PRIVATE_STAGE_MODE)
                created_directories.add(directory)
            with output.open("xb") as handle:
                handle.write(artifact.content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(output, artifact.mode, follow_symlinks=False)
        for directory in sorted(
            created_directories,
            key=lambda item: len(item.relative_to(stage).parts),
            reverse=True,
        ):
            os.chmod(directory, RUN_BUNDLE_DIRECTORY_MODE, follow_symlinks=False)
            _fsync_directory(directory)
        phase = "verify"
        _verify_staged_artifacts(stage, artifacts)
        return StagedArtifactSet(path=stage, identity=_file_identity(os.lstat(stage)))
    except BaseException as exc:
        cleanup: CleanupStatus = "pass"
        try:
            current = _file_identity(os.lstat(stage))
            if (
                current.st_dev != initial_identity.st_dev
                or current.st_ino != initial_identity.st_ino
            ):
                cleanup = "fail"
            else:
                shutil.rmtree(stage)
        except FileNotFoundError:
            cleanup = "pass"
        except OSError:
            cleanup = "fail"
        raise _StageArtifactSetError(
            code="staging_verify_failed"
            if phase == "verify"
            else "staging_write_failed",
            path=stage,
            cleanup=cleanup,
        ) from exc


def _renameat2_function() -> Any:
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        function = libc.renameat2
    except AttributeError as exc:
        raise OSError(errno.ENOSYS, os.strerror(errno.ENOSYS)) from exc
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    return function


def _renameat2(source: Path, target: Path, flag: int) -> None:
    function = _renameat2_function()
    result = function(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(target),
        flag,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(source), str(target))


def _require_renameat2_capability(report_root: Path, flag: int) -> None:
    nonce = secrets.token_hex(16)
    source = report_root / f".renameat2.probe.source.{nonce}"
    target = report_root / f".renameat2.probe.target.{nonce}"
    try:
        _renameat2(source, target, flag)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return
        raise
    raise RuntimeError("renameat2 capability probe unexpectedly mutated a path")


def _rename_directory_noreplace(
    staging: StagedArtifactSet,
    target: Path,
) -> PublishedTarget:
    """Publish one staged directory through the sole kernel no-replace path."""
    staged_tree_sha = _tree_sha256(staging.path)
    _renameat2(staging.path, target, RENAME_NOREPLACE)
    identity = _file_identity(os.lstat(target))
    if identity != staging.identity:
        raise OSError(errno.EIO, "published target identity disagrees")
    target_tree_sha = _tree_sha256(target)
    if target_tree_sha != staged_tree_sha:
        raise OSError(errno.EIO, "published target tree digest disagrees")
    return PublishedTarget(path=target, identity=identity, tree_sha256=target_tree_sha)


def _remove_staging_tree(staging: StagedArtifactSet) -> bool:
    try:
        current = _file_identity(os.lstat(staging.path))
    except FileNotFoundError:
        return True
    if current != staging.identity:
        return False
    shutil.rmtree(staging.path)
    return not staging.path.exists()


def _remove_published_target(published: PublishedTarget) -> bool:
    try:
        current = _file_identity(os.lstat(published.path))
    except FileNotFoundError:
        return True
    if (
        current != published.identity
        or _tree_sha256(published.path) != published.tree_sha256
    ):
        return False
    shutil.rmtree(published.path)
    _fsync_directory(published.path.parent)
    return not published.path.exists()


def _assert_materialization_lock_owned(
    report_root: Path,
    lock: MaterializationLock,
) -> None:
    root_descriptor, root_identity = _open_stable_report_root(report_root)
    try:
        path_identity = _file_identity(
            os.stat(
                MATERIALIZATION_LOCK_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        )
        descriptor_identity = _file_identity(os.fstat(lock.descriptor))
        if (
            not _same_report_root_identity(
                root_identity, lock.identity.report_root_identity
            )
            or path_identity != lock.identity.lock_file_identity
            or descriptor_identity != lock.identity.lock_file_identity
        ):
            raise ValueError("materialization lock identity drift")
        payload = _read_descriptor_bytes(lock.descriptor)
        if (
            hashlib.sha256(payload).hexdigest() != lock.identity.payload_sha256
            or payload != _canonical_lock_payload(lock.identity)
        ):
            raise ValueError("materialization lock payload drift")
    finally:
        os.close(root_descriptor)


def _capture_bookkeeping_file(
    *,
    report_root: Path,
    lock: MaterializationLock,
    name: Literal[".active_run", ".active_run.sha256"],
) -> BookkeepingFileState:
    _assert_materialization_lock_owned(report_root, lock)
    root_descriptor, root_identity = _open_stable_report_root(report_root)
    try:
        try:
            before = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return BookkeepingFileState(name, False, None, None, None, None, None)
        before_identity = _file_identity(before)
        mode = stat.S_IMODE(before.st_mode)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
            or before.st_dev != root_identity.st_dev
            or mode not in {PRIVATE_TEMP_MODE, RUN_BUNDLE_FILE_MODE}
        ):
            raise ValueError(f"nonregular active bookkeeping: {name}")
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=root_descriptor,
        )
        try:
            opened = os.fstat(descriptor)
            payload = _read_descriptor_bytes(descriptor, opened.st_size)
        finally:
            os.close(descriptor)
        after = os.stat(name, dir_fd=root_descriptor, follow_symlinks=False)
        if (
            _file_identity(opened) != before_identity
            or _file_identity(after) != before_identity
            or len(payload) != opened.st_size
        ):
            raise ValueError(f"active bookkeeping identity changed: {name}")
        return BookkeepingFileState(
            name=name,
            existed=True,
            identity=before_identity,
            permission_mode=mode,
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            content=payload,
        )
    finally:
        os.close(root_descriptor)


def _capture_regular_path(
    path: Path,
) -> tuple[FileIdentity, int, bytes, str]:
    before = os.lstat(path)
    identity = _file_identity(before)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_uid != os.geteuid()
    ):
        raise ValueError(f"nonregular private bookkeeping path: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        payload = _read_descriptor_bytes(descriptor, opened.st_size)
    finally:
        os.close(descriptor)
    after = os.lstat(path)
    if (
        _file_identity(opened) != identity
        or _file_identity(after) != identity
        or len(payload) != opened.st_size
    ):
        raise ValueError(f"private bookkeeping identity changed: {path}")
    return (
        identity,
        stat.S_IMODE(opened.st_mode),
        payload,
        hashlib.sha256(payload).hexdigest(),
    )


def _create_bookkeeping_temp(
    *,
    report_root: Path,
    lock: MaterializationLock,
    name: Literal[".active_run", ".active_run.sha256"],
    content: bytes,
    final_mode: int = PRIVATE_TEMP_MODE,
) -> BookkeepingTempState:
    _assert_materialization_lock_owned(report_root, lock)
    root_descriptor, _root_identity = _open_stable_report_root(report_root)
    try:
        for _attempt in range(GENERATED_NAME_ATTEMPTS):
            path = report_root / f"{name}.tmp.{os.getpid()}.{secrets.token_hex(16)}"
            try:
                descriptor = os.open(
                    path.name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                    PRIVATE_TEMP_MODE,
                    dir_fd=root_descriptor,
                )
            except FileExistsError:
                continue
            try:
                _write_all(descriptor, content)
                os.fsync(descriptor)
                if final_mode != PRIVATE_TEMP_MODE:
                    os.fchmod(descriptor, final_mode)
                    os.fsync(descriptor)
            finally:
                os.close(descriptor)
            identity, mode, observed, digest = _capture_regular_path(path)
            if observed != content or mode != final_mode:
                raise ValueError(f"bookkeeping temp verification failed: {path}")
            return BookkeepingTempState(
                path=path,
                identity=identity,
                permission_mode=mode,
                size=len(content),
                sha256=digest,
                content=content,
            )
    finally:
        os.close(root_descriptor)
    raise FileExistsError(errno.EEXIST, "bookkeeping name exhausted")


def _bookkeeping_matches(
    observed: BookkeepingFileState,
    expected: BookkeepingFileState,
    *,
    require_identity: bool = True,
) -> bool:
    if observed.existed != expected.existed:
        return False
    if not observed.existed:
        return True
    return (
        (not require_identity or observed.identity == expected.identity)
        and observed.permission_mode == expected.permission_mode
        and observed.size == expected.size
        and observed.sha256 == expected.sha256
        and observed.content == expected.content
    )


def _temp_matches(path: Path, expected: BookkeepingTempState) -> bool:
    try:
        identity, mode, payload, digest = _capture_regular_path(path)
    except (FileNotFoundError, OSError, ValueError):
        return False
    return (
        identity == expected.identity
        and mode == expected.permission_mode
        and len(payload) == expected.size
        and digest == expected.sha256
        and payload == expected.content
    )


def _publish_temp_over_bookkeeping(
    *,
    report_root: Path,
    lock: MaterializationLock,
    temp: BookkeepingTempState,
    prior: BookkeepingFileState,
) -> BookkeepingFileState:
    current = _capture_bookkeeping_file(
        report_root=report_root,
        lock=lock,
        name=prior.name,
    )
    if not _bookkeeping_matches(current, prior):
        raise ValueError(f"bookkeeping compare-before-publish failed: {prior.name}")
    if temp.permission_mode != RUN_BUNDLE_FILE_MODE or not _temp_matches(
        temp.path, temp
    ):
        raise ValueError(f"bookkeeping temp is not publication-ready: {temp.path}")
    root_descriptor, _root_identity = _open_stable_report_root(report_root)
    try:
        os.replace(
            temp.path.name,
            prior.name,
            src_dir_fd=root_descriptor,
            dst_dir_fd=root_descriptor,
        )
    finally:
        os.close(root_descriptor)
    published = _capture_bookkeeping_file(
        report_root=report_root,
        lock=lock,
        name=prior.name,
    )
    if (
        not published.existed
        or published.permission_mode != RUN_BUNDLE_FILE_MODE
        or published.content != temp.content
        or published.sha256 != temp.sha256
    ):
        raise ValueError(f"bookkeeping publish verification failed: {prior.name}")
    return published


def _promote_bookkeeping_temp(
    *,
    report_root: Path,
    lock: MaterializationLock,
    temp: BookkeepingTempState,
) -> BookkeepingTempState:
    _assert_materialization_lock_owned(report_root, lock)
    if not _temp_matches(temp.path, temp):
        raise ValueError(f"bookkeeping temp changed before promotion: {temp.path}")
    root_descriptor, _root_identity = _open_stable_report_root(report_root)
    try:
        os.chmod(
            temp.path.name,
            RUN_BUNDLE_FILE_MODE,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        _fsync_directory(report_root)
    finally:
        os.close(root_descriptor)
    identity, mode, payload, digest = _capture_regular_path(temp.path)
    if (
        identity != temp.identity
        or payload != temp.content
        or mode != RUN_BUNDLE_FILE_MODE
    ):
        raise ValueError(f"bookkeeping temp promotion failed: {temp.path}")
    return replace(
        temp,
        permission_mode=mode,
        size=len(payload),
        sha256=digest,
    )


def _publish_active_bookkeeping(
    *,
    report_root: Path,
    lock: MaterializationLock,
    published_target: PublishedTarget,
) -> tuple[Path, PriorBookkeepingState]:
    """Publish active baseline then pointer and rollback any activation failure."""
    pointer_bytes = (str(published_target.path.resolve()) + "\n").encode("utf-8")
    baseline_bytes = hash_baseline_bytes(pointer_bytes)
    prior: PriorBookkeepingState | None = None
    failure_code: MaterializationErrorCode = "active_bookkeeping_nonregular"
    try:
        pointer_prior = _capture_bookkeeping_file(
            report_root=report_root,
            lock=lock,
            name=".active_run",
        )
        baseline_prior = _capture_bookkeeping_file(
            report_root=report_root,
            lock=lock,
            name=".active_run.sha256",
        )
        prior = PriorBookkeepingState(
            report_root_identity=lock.identity.report_root_identity,
            lock_file_identity=lock.identity.lock_file_identity,
            lock_nonce=lock.identity.nonce,
            pointer_prior=pointer_prior,
            baseline_prior=baseline_prior,
        )
        failure_code = "bookkeeping_name_exhausted"
        baseline_temp = _create_bookkeeping_temp(
            report_root=report_root,
            lock=lock,
            name=".active_run.sha256",
            content=baseline_bytes,
        )
        prior = replace(prior, baseline_temp=baseline_temp)
        pointer_temp = _create_bookkeeping_temp(
            report_root=report_root,
            lock=lock,
            name=".active_run",
            content=pointer_bytes,
        )
        prior = replace(prior, pointer_temp=pointer_temp)
        failure_code = "active_baseline_publish_failed"
        baseline_temp = _promote_bookkeeping_temp(
            report_root=report_root,
            lock=lock,
            temp=baseline_temp,
        )
        prior = replace(prior, baseline_temp=baseline_temp)
        baseline_published = _publish_temp_over_bookkeeping(
            report_root=report_root,
            lock=lock,
            temp=baseline_temp,
            prior=baseline_prior,
        )
        prior = replace(
            prior,
            baseline_temp=None,
            baseline_published=baseline_published,
        )
        failure_code = "active_pointer_publish_failed"
        pointer_temp = _promote_bookkeeping_temp(
            report_root=report_root,
            lock=lock,
            temp=pointer_temp,
        )
        prior = replace(prior, pointer_temp=pointer_temp)
        pointer_published = _publish_temp_over_bookkeeping(
            report_root=report_root,
            lock=lock,
            temp=pointer_temp,
            prior=pointer_prior,
        )
        prior = replace(prior, pointer_temp=None, pointer_published=pointer_published)
        _fsync_directory(report_root)
        return report_root / ".active_run", prior
    except BaseException as exc:
        rollback = _rollback_publication(
            report_root=report_root,
            lock=lock,
            published_target=published_target,
            staging=None,
            prior=prior,
        )
        failed = bool(rollback.failed_paths)
        raise _materialization_failure(
            phase="rollback" if failed else "activate",
            code="run_bundle_rollback_failed" if failed else failure_code,
            cause_code=failure_code,
            target=published_target.path,
            rollback=rollback,
        ) from exc


def _bookkeeping_state_from_regular_path(
    *,
    path: Path,
    name: Literal[".active_run", ".active_run.sha256"],
) -> BookkeepingFileState:
    identity, mode, payload, digest = _capture_regular_path(path)
    return BookkeepingFileState(
        name=name,
        existed=True,
        identity=identity,
        permission_mode=mode,
        size=len(payload),
        sha256=digest,
        content=payload,
    )


def _unlink_exact_bookkeeping_temp(
    path: Path,
    expected: BookkeepingFileState | BookkeepingTempState,
) -> bool:
    try:
        identity, mode, payload, digest = _capture_regular_path(path)
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        return False
    expected_identity = expected.identity
    return_value = (
        expected_identity is not None
        and identity == expected_identity
        and mode == expected.permission_mode
        and len(payload) == expected.size
        and digest == expected.sha256
        and payload == expected.content
    )
    if not return_value:
        return False
    path.unlink()
    return not path.exists()


def _unique_bookkeeping_quarantine(
    report_root: Path,
    name: Literal[".active_run", ".active_run.sha256"],
) -> Path:
    for _attempt in range(GENERATED_NAME_ATTEMPTS):
        candidate = report_root / (
            f"{name}.quarantine.{os.getpid()}.{secrets.token_hex(16)}"
        )
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise FileExistsError(errno.EEXIST, "bookkeeping quarantine name exhausted")


def _restore_one_bookkeeping_file(
    *,
    report_root: Path,
    lock: MaterializationLock,
    prior: BookkeepingFileState,
    published: BookkeepingFileState,
) -> None:
    current = _capture_bookkeeping_file(
        report_root=report_root,
        lock=lock,
        name=prior.name,
    )
    if not _bookkeeping_matches(current, published):
        raise ValueError(f"bookkeeping_restore_conflict:{prior.name}")
    destination = report_root / prior.name
    if prior.existed:
        if prior.content is None or prior.permission_mode is None:
            raise ValueError(f"bookkeeping_restore_conflict:{prior.name}")
        restore_temp = _create_bookkeeping_temp(
            report_root=report_root,
            lock=lock,
            name=prior.name,
            content=prior.content,
            final_mode=prior.permission_mode,
        )
        _renameat2(destination, restore_temp.path, RENAME_EXCHANGE)
        try:
            restored = _capture_bookkeeping_file(
                report_root=report_root,
                lock=lock,
                name=prior.name,
            )
            exchanged = _bookkeeping_state_from_regular_path(
                path=restore_temp.path,
                name=prior.name,
            )
            if not _bookkeeping_matches(restored, prior, require_identity=False):
                raise ValueError(f"bookkeeping_restore_conflict:{prior.name}")
            if not _bookkeeping_matches(exchanged, published):
                raise ValueError(f"bookkeeping_restore_conflict:{prior.name}")
            if not _unlink_exact_bookkeeping_temp(restore_temp.path, exchanged):
                raise ValueError(
                    f"bookkeeping_restore_conflict:{restore_temp.path.name}"
                )
        except BaseException:
            try:
                destination_identity = _file_identity(os.lstat(destination))
                temp_identity = _file_identity(os.lstat(restore_temp.path))
                if (
                    destination_identity == restore_temp.identity
                    and temp_identity == published.identity
                ):
                    _renameat2(destination, restore_temp.path, RENAME_EXCHANGE)
            except (FileNotFoundError, OSError, ValueError):
                pass
            raise
    else:
        quarantine = _unique_bookkeeping_quarantine(report_root, prior.name)
        _renameat2(destination, quarantine, RENAME_NOREPLACE)
        try:
            quarantined = _bookkeeping_state_from_regular_path(
                path=quarantine,
                name=prior.name,
            )
            if not _bookkeeping_matches(quarantined, published):
                raise ValueError(f"bookkeeping_restore_conflict:{prior.name}")
            if not _unlink_exact_bookkeeping_temp(quarantine, quarantined):
                raise ValueError(f"bookkeeping_restore_conflict:{quarantine.name}")
        except BaseException:
            try:
                if not destination.exists() and quarantine.exists():
                    _renameat2(quarantine, destination, RENAME_NOREPLACE)
            except OSError:
                pass
            raise
        absent = _capture_bookkeeping_file(
            report_root=report_root,
            lock=lock,
            name=prior.name,
        )
        if absent.existed:
            raise ValueError(f"bookkeeping_restore_conflict:{prior.name}")
    _fsync_directory(report_root)


def _cleanup_prior_temps(
    prior: PriorBookkeepingState | None,
) -> tuple[CleanupStatus, list[str]]:
    if prior is None:
        return "not_required", []
    states = tuple(
        state
        for state in (
            prior.pointer_temp,
            prior.baseline_temp,
            prior.pointer_quarantine,
            prior.baseline_quarantine,
        )
        if state is not None
    )
    if not states:
        return "not_required", []
    failed: list[str] = []
    for state in states:
        if not _unlink_exact_bookkeeping_temp(state.path, state):
            failed.append(str(state.path))
    return ("fail" if failed else "pass"), failed


def _rollback_publication(
    *,
    report_root: Path,
    lock: MaterializationLock,
    published_target: PublishedTarget | None,
    staging: StagedArtifactSet | None,
    prior: PriorBookkeepingState | None,
) -> RollbackResult:
    """Rollback only identity- and digest-bound state owned by this call."""
    pointer_restore: CleanupStatus = "not_required"
    baseline_restore: CleanupStatus = "not_required"
    target_cleanup: CleanupStatus = "not_required"
    staging_cleanup: CleanupStatus = "not_required"
    failed_paths: list[str] = []
    try:
        _assert_materialization_lock_owned(report_root, lock)
    except (OSError, RuntimeError, ValueError):
        return RollbackResult(
            pointer_restore="fail"
            if prior and prior.pointer_published
            else "not_required",
            baseline_restore="not_required",
            target_cleanup="not_required",
            staging_cleanup="not_required",
            temp_cleanup="not_required",
            failed_paths=("materialization_lock_identity",),
        )
    if prior is not None and prior.pointer_published is not None:
        try:
            _restore_one_bookkeeping_file(
                report_root=report_root,
                lock=lock,
                prior=prior.pointer_prior,
                published=prior.pointer_published,
            )
            pointer_restore = "pass"
        except (OSError, RuntimeError, ValueError):
            pointer_restore = "fail"
            failed_paths.append(
                f"bookkeeping_restore_conflict:{prior.pointer_prior.name}"
            )
    if (
        pointer_restore != "fail"
        and prior is not None
        and prior.baseline_published is not None
    ):
        try:
            _restore_one_bookkeeping_file(
                report_root=report_root,
                lock=lock,
                prior=prior.baseline_prior,
                published=prior.baseline_published,
            )
            baseline_restore = "pass"
        except (OSError, RuntimeError, ValueError):
            baseline_restore = "fail"
            failed_paths.append(
                f"bookkeeping_restore_conflict:{prior.baseline_prior.name}"
            )
    if pointer_restore != "fail" and baseline_restore != "fail":
        if published_target is not None:
            try:
                target_cleanup = (
                    "pass" if _remove_published_target(published_target) else "fail"
                )
            except (OSError, ValueError):
                target_cleanup = "fail"
            if target_cleanup == "fail":
                failed_paths.append(str(published_target.path))
        elif staging is not None:
            try:
                staging_cleanup = "pass" if _remove_staging_tree(staging) else "fail"
            except OSError:
                staging_cleanup = "fail"
            if staging_cleanup == "fail":
                failed_paths.append(str(staging.path))
    temp_cleanup, temp_failures = _cleanup_prior_temps(prior)
    failed_paths.extend(temp_failures)
    return RollbackResult(
        staging_cleanup=staging_cleanup,
        target_cleanup=target_cleanup,
        pointer_restore=pointer_restore,
        baseline_restore=baseline_restore,
        temp_cleanup=temp_cleanup,
        failed_paths=tuple(sorted(set(failed_paths))),
    )


def _validated_publication_paths(spec: RunBundleSpec) -> tuple[Path, Path]:
    root_input = (
        spec.activation.report_root
        if spec.activation is not None
        else spec.report_dir.parent
    )
    report_root = root_input.absolute()
    target = spec.report_dir.absolute()
    try:
        root_descriptor, _identity = _open_stable_report_root(report_root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise ValueError("report root is invalid") from exc
    else:
        os.close(root_descriptor)
    if target.parent != report_root or target.name != spec.run_id:
        raise ValueError("report target parent or run id disagrees")
    return report_root, target


def _publish_error_code(error: OSError) -> MaterializationErrorCode:
    if error.errno in {errno.EEXIST, errno.ENOTEMPTY}:
        return "run_bundle_target_exists"
    if error.errno in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
        return "atomic_noreplace_unavailable"
    if error.errno == errno.EXDEV:
        return "run_bundle_cross_device"
    return "run_bundle_publish_failed"


def _error_after_rollback(
    *,
    phase: MaterializationPhase,
    cause_code: MaterializationErrorCode,
    target: Path,
    rollback: RollbackResult,
    staging: Path | None = None,
) -> RunBundleMaterializationError:
    failed = bool(rollback.failed_paths)
    return _materialization_failure(
        phase="rollback" if failed else phase,
        code="run_bundle_rollback_failed" if failed else cause_code,
        cause_code=cause_code,
        target=target,
        staging=staging,
        rollback=rollback,
    )


def _materialize_run_bundle(spec: RunBundleSpec) -> RunBundleMaterialization:
    """Validate, render, stage, publish, and optionally activate one run bundle."""
    target_for_error = spec.report_dir.absolute()
    try:
        workflow_family = run_workflow_family(spec)
        packet = resolve_active_design_packet(
            spec.config,
            workflow_family=workflow_family,
            explicit=spec.active_design_packet,
        )
    except ActiveDesignPacketInputError as exc:
        raise _materialization_failure(
            phase="decode",
            code="packet_invalid",
            target=target_for_error,
        ) from exc
    artifact_names = iter_artifacts(spec.config, spec.roles, packet)
    try:
        context = build_active_design_reference_context(
            spec,
            packet,
            workflow_family,
            artifact_names=artifact_names,
        )
        violations = validate_materialized_active_design_packet(
            packet,
            context,
            gate="materialization",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise _materialization_failure(
            phase="reference_validation",
            code="reference_invalid",
            target=target_for_error,
        ) from exc
    if violations:
        raise _materialization_failure(
            phase="reference_validation",
            code="reference_invalid",
            target=target_for_error,
            violations=violations,
        )
    try:
        role_packets = project_role_document_packets(spec, packet)
        prompt_packets = project_subagent_prompt_packets(spec, packet, role_packets)
        template_artifacts = project_template_artifacts(
            spec,
            packet,
            artifact_names=artifact_names,
            role_packets=role_packets,
            prompt_packets=prompt_packets,
        )
        verification = project_verification_artifact(spec)
        authority_artifacts = project_authority_artifacts(spec)
        initial_wave_row = project_initial_wave_row(spec)
        if spec.activation is None:
            from workflow_monitor import EMPTY_MONITORING_ENTRIES

            monitoring_entries = EMPTY_MONITORING_ENTRIES
        else:
            monitoring_entries = enrich_runtime_measurement_input(
                spec,
                packet,
                context,
                spec.activation.monitoring_entries,
            )
        wave_artifacts = project_wave_ledger_artifacts(
            spec,
            template_artifacts,
            monitoring_entries=monitoring_entries,
            initial_wave_row=initial_wave_row,
        )
        manifest = rendered_text_artifact(
            spec.config.artifacts["team_manifest"],
            build_manifest(
                spec,
                packet,
                context,
                artifact_names=artifact_names,
                role_packets=role_packets,
                prompt_packets=prompt_packets,
            ),
        )
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise _materialization_failure(
            phase="render",
            code="render_invalid",
            target=target_for_error,
        ) from exc
    wave_paths = {artifact.relative_path for artifact in wave_artifacts}
    projected = (
        *(
            artifact
            for artifact in template_artifacts
            if artifact.relative_path not in wave_paths
        ),
        *wave_artifacts,
        verification,
        *authority_artifacts,
        manifest,
    )
    authority_paths = tuple(
        artifact.relative_path.as_posix() for artifact in authority_artifacts
    )
    planned_paths = (*artifact_names, *authority_paths)
    try:
        artifacts = _build_in_memory_artifact_set(
            planned_paths=planned_paths,
            projected_artifacts=projected,
        )
    except ValueError as exc:
        raise _materialization_failure(
            phase="render",
            code="artifact_set_invalid",
            target=target_for_error,
        ) from exc
    digests = _artifact_digests(artifacts)
    try:
        report_root, target = _validated_publication_paths(spec)
    except ValueError as exc:
        raise _materialization_failure(
            phase="reference_validation",
            code="report_root_invalid",
            target=target_for_error,
        ) from exc

    lock = _acquire_materialization_lock(report_root=report_root, run_id=spec.run_id)
    lock_released = False
    staged: StagedArtifactSet | None = None
    published: PublishedTarget | None = None
    active_pointer: Path | None = None
    try:
        try:
            _require_renameat2_capability(report_root, RENAME_NOREPLACE)
        except OSError as exc:
            code: MaterializationErrorCode = "atomic_noreplace_unavailable"
            raise _materialization_failure(
                phase="publish", code=code, target=target
            ) from exc
        if spec.activation is not None:
            try:
                _require_renameat2_capability(report_root, RENAME_EXCHANGE)
            except OSError as exc:
                raise _materialization_failure(
                    phase="activate",
                    code="atomic_exchange_unavailable",
                    target=target,
                ) from exc
        if os.path.lexists(target):
            raise _materialization_failure(
                phase="publish",
                code="run_bundle_target_exists",
                target=target,
            )
        try:
            staged = _stage_artifact_set(
                report_root=report_root,
                target=target,
                run_id=spec.run_id,
                artifacts=artifacts,
            )
        except FileExistsError as exc:
            raise _materialization_failure(
                phase="stage",
                code="staging_name_exhausted",
                target=target,
            ) from exc
        except _StageArtifactSetError as exc:
            rollback = RollbackResult(
                staging_cleanup=exc.cleanup,
                failed_paths=(str(exc.path),) if exc.cleanup == "fail" else (),
            )
            raise _error_after_rollback(
                phase="stage",
                cause_code=exc.code,
                target=target,
                staging=exc.path,
                rollback=rollback,
            ) from exc
        if os.path.lexists(target):
            rollback = _rollback_publication(
                report_root=report_root,
                lock=lock,
                published_target=None,
                staging=staged,
                prior=None,
            )
            raise _error_after_rollback(
                phase="publish",
                cause_code="run_bundle_target_exists",
                target=target,
                staging=staged.path,
                rollback=rollback,
            )
        try:
            published = _rename_directory_noreplace(staged, target)
            staged = None
            _fsync_directory(report_root)
        except OSError as exc:
            cause_code = _publish_error_code(exc)
            if published is None and staged is not None and os.path.lexists(target):
                try:
                    target_identity = _file_identity(os.lstat(target))
                    if target_identity == staged.identity:
                        published = PublishedTarget(
                            path=target,
                            identity=target_identity,
                            tree_sha256=_tree_sha256(target),
                        )
                        staged = None
                except (OSError, ValueError):
                    published = None
            rollback = _rollback_publication(
                report_root=report_root,
                lock=lock,
                published_target=cast(PublishedTarget, published),
                staging=staged,
                prior=None,
            )
            raise _error_after_rollback(
                phase="publish",
                cause_code=cause_code,
                target=target,
                staging=staged.path if staged is not None else None,
                rollback=rollback,
            ) from exc
        if spec.activation is not None:
            active_pointer, _prior = _publish_active_bookkeeping(
                report_root=report_root,
                lock=lock,
                published_target=published,
            )
        try:
            _release_materialization_lock(lock)
            lock_released = True
        except RuntimeError as release_error:
            lock_released = True
            raise _materialization_failure(
                phase="rollback",
                code="materialization_lock_release_failed",
                target=target,
            ) from release_error
    except RunBundleMaterializationError as exc:
        if not lock_released:
            try:
                _release_materialization_lock(lock)
                lock_released = True
            except RuntimeError as release_error:
                raise _materialization_failure(
                    phase="rollback",
                    code="materialization_lock_release_failed",
                    target=target,
                    cause_code="materialization_lock_release_failed",
                    rollback=exc.rollback,
                ) from release_error
        raise
    except RuntimeError as exc:
        if not lock_released:
            try:
                _release_materialization_lock(lock)
                lock_released = True
            except RuntimeError as release_error:
                raise _materialization_failure(
                    phase="rollback",
                    code="materialization_lock_release_failed",
                    target=target,
                ) from release_error
        raise _materialization_failure(
            phase="rollback",
            code="materialization_lock_release_failed",
            target=target,
        ) from exc
    return RunBundleMaterialization(
        report_dir=target,
        created_files=tuple(
            artifact.relative_path.as_posix() for artifact in artifacts
        ),
        active_design_packet=packet,
        role_document_packets=role_packets,
        subagent_prompt_packets=prompt_packets,
        artifact_digests=digests,
        active_pointer=active_pointer,
    )


def _indented_yaml_mapping_lines(key: str, value: object) -> list[str]:
    rendered = yaml.safe_dump(
        {key: value},
        allow_unicode=True,
        sort_keys=False,
    ).rstrip()
    return [f"  {line}" for line in rendered.splitlines()]


def build_manifest(
    spec: RunBundleSpec,
    packet: ActiveDesignPacketValue,
    context: ActiveDesignReferenceContext,
    *,
    artifact_names: tuple[str, ...],
    role_packets: tuple[RoleDocumentPacket, ...],
    prompt_packets: tuple[SubagentPromptPacket, ...],
) -> str:
    """Build the team manifest yaml."""
    workflow_family = run_workflow_family(spec)
    lines = manifest_run_lines(spec, workflow_family, packet, context)
    lines.extend(
        manifest_role_lines(
            spec,
            workflow_family,
            packet,
            role_packets,
            prompt_packets,
        )
    )
    lines.extend(manifest_context_policy_lines(spec.config, packet))
    lines.extend(manifest_quality_gate_lines(spec.config))
    lines.extend(manifest_artifact_lines(artifact_names))
    return "\n".join(lines) + "\n"


def manifest_run_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
    active_design_packet: ActiveDesignPacketValue,
    context: ActiveDesignReferenceContext,
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
        *_indented_yaml_mapping_lines(
            "active_design_packet",
            active_design_packet_mapping(active_design_packet),
        ),
        *_indented_yaml_mapping_lines(
            "active_design_packet_reference_projection",
            active_design_reference_projection_mapping(context),
        ),
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
        *manifest_pre_handoff_gate_status_lines(active_design_packet),
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
        lines.append("      - tool_route")
        lines.append("      - tool_command_packet_command")
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
            "write-capable handoff when run.active_design_packet.design_artifact "
            f"({active_design_packet.design_artifact}) exists"
        )
        lines.append(
            "      - include run.repo_tool_routing_policy selected-skill packet commands, "
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
            CONTRACT_COMPLETE_IMPLEMENTATION_HANDOFF_INSERT_INDEX:CONTRACT_COMPLETE_IMPLEMENTATION_HANDOFF_INSERT_INDEX
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
    active_design_packet: ActiveDesignPacketValue,
) -> list[str]:
    """Render the pre-handoff gate status contract."""
    applies_when = (
        "run.active_design_packet.design_artifact="
        f"{active_design_packet.design_artifact};"
        "condition=exists_before_implementation_or_handoff"
    )
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
            f"    applies_when: {applies_when!r}",
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
    active_design_packet: ActiveDesignPacketValue,
    role_packets: tuple[RoleDocumentPacket, ...],
    prompt_packets: tuple[SubagentPromptPacket, ...],
) -> list[str]:
    """Render role entries for the team manifest."""
    documents_by_role = {packet.role_id: packet for packet in role_packets}
    prompts_by_role = {packet.role_id: packet for packet in prompt_packets}
    lines = ["roles:"]
    for role in spec.roles:
        lines.extend(
            manifest_one_role_lines(
                spec,
                workflow_family,
                active_design_packet,
                role,
                documents_by_role[role.id],
                prompts_by_role[role.id],
            )
        )
    return lines


def manifest_one_role_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
    active_design_packet: ActiveDesignPacketValue,
    role: Role,
    document_packet: RoleDocumentPacket,
    prompt_packet: SubagentPromptPacket,
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
    for output in prompt_packet.required_outputs:
        lines.append(f"      - {output}")
    lines.extend(manifest_write_policy_lines(spec, role, active_design_packet))
    lines.extend(manifest_document_packet_lines(document_packet))
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
    active_design_packet: ActiveDesignPacketValue,
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
    document_packet: RoleDocumentPacket,
) -> list[str]:
    """Render explicit document packet lines for one role."""
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
                lines.append(f"              required: {str(section.required).lower()}")
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
    active_design_packet: ActiveDesignPacketValue,
) -> list[str]:
    """Render context-sharing policy lines."""
    packet_artifacts = selected_packet_artifact_paths(
        config,
        active_design_packet,
    )
    lines = ["context_policies:"]
    for policy in config.context_policies:
        lines.append("  - roles:")
        for role_name in _as_string_tuple(
            policy.get("roles"), "context_policies.roles"
        ):
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


def manifest_artifact_lines(artifact_names: tuple[str, ...]) -> list[str]:
    """Render artifact lines."""
    lines = ["artifacts:"]
    for artifact in artifact_names:
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
            lines.append(
                f"{indent}    - id: {_as_required_string(wave.get('id'), 'stage_waves[].id')}"
            )
            lines.append(
                f"{indent}      stage_class: "
                f"{_as_required_string(wave.get('stage_class'), 'stage_waves[].stage_class')}"
            )
            lines.append(f"{indent}      role_ids:")
            for role_id in _as_string_tuple(
                wave.get("role_ids"), "stage_waves[].role_ids"
            ):
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
    lines.append(f"{indent}  tool_route: 'run.repo_tool_routing_policy'")
    lines.append(
        f"{indent}  tool_command_packet_command: {REPO_TOOL_ROUTING_SHOW_COMMAND_TEMPLATE!r}"
    )
    lines.append(
        f"{indent}  tool_evidence: 'run.repo_tool_routing_policy.dynamic_skill_routing'"
    )
    lines.append(f"{indent}  tool_catalog_matches: 'tools/catalog.yaml'")
    lines.append(f"{indent}  required_tool_fields:")
    lines.append(f"{indent}    - tool_route")
    lines.append(f"{indent}    - tool_command_packet_command")
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
        "Carry run.repo_tool_routing_policy tool_route, tool_command_packet_command, and tool_evidence into "
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
    active_design_packet: ActiveDesignPacketValue,
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
    active_design_packet: ActiveDesignPacketValue,
) -> tuple[Path, ...]:
    """Resolve generated artifact files one role may write."""
    return tuple(
        sorted(
            {
                resolve_report_bundle_artifact_path(
                    report_dir,
                    selected_artifact_name(config, artifact_key, active_design_packet),
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
    loaded_packet = load_materialized_active_design_packet(resolved_report_dir)
    if loaded_packet.value is None or loaded_packet.violations:
        blockers = ",".join(
            render_active_design_packet_violation(violation)
            for violation in loaded_packet.violations
        )
        raise RuntimeError(f"active design packet is invalid: {blockers or 'missing'}")
    scope = resolve_role_write_scope(
        config,
        role,
        resolved_report_dir,
        resolved_workspace_root,
        loaded_packet.value,
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
