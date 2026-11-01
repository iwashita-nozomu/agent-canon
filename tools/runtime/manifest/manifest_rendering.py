# @dependency-start
# contract tool
# responsibility AgentTeam manifest rendering owner module.
# upstream design ../../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# upstream design ../../../agents/COMMUNICATION_PROTOCOL.md owns coordination capability and receipt semantics.
# upstream implementation ../../agent/orchestration/team_config.py provides rendering configuration inputs.
# upstream implementation ../../agent/orchestration/packets.py provides rendering packet inputs.
# upstream implementation ../values.py refines decoded rendering containers.
# upstream implementation ../../repository/workspace/workspace_scope.py provides rendering paths.
# downstream implementation ../../agent/orchestration/agent_team.py facade consumes rendering APIs.
# downstream implementation ../../agent/templates/code_template_rendering.py owns package-safe code source rendering.
# downstream implementation ../lifecycle/bootstrap_agent_run.py consumes rendering APIs.
# @dependency-end
"""Own AgentTeam manifest, template, and output rendering."""

from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

import yaml

from tools.runtime.values import is_object_list, is_string_object_dict

from tools.runtime.authority.checkout_identity import resolve_checkout_identity

from tools.agent.orchestration.route import decide_skills, load_skill_route_rules
from tools.runtime.lifecycle.update_lifecycle_contract import (
    import_decision_sufficiency_verdict,
)

from tools.agent.orchestration.packets import (
    ActiveDesignPacketConfig,
    active_design_packet_artifact_map,
    active_design_packet_mapping,
    active_design_packet_reference_projection,
    iter_artifacts,
    mathematical_intent_packet_mapping,
    mathematical_intent_route_config,
    math_intent_route_id_for_spec,
    resolve_math_intent_packet_for_spec,
    resolve_active_design_packet_config,
    resolve_cross_cutting_document_packet,
    resolve_role_document_packet,
    role_specific_document_entries,
    selected_role_outputs,
)

from tools.repository.workspace.workspace_scope import resolve_role_write_scope

from tools.agent.orchestration.subagent_selection import COLLABORATION_OPERATIONS
from tools.agent.orchestration.team_config import (
    ROOT,
    Role,
    RunBundleSpec,
    TeamConfig,
    as_optional_string,
    as_required_string,
    as_string_tuple,
    normalized_public_skill_name,
    load_task_catalog,
    load_team_config,
    resolve_workflow_family,
)

from tools.agent.orchestration.tool_calls import (
    TOOL_CALL_SCHEMA,
)

from tools.agent.orchestration.implementation_dispatch import (
    default_quality_check_agent_types,
    default_quality_check_role_ids,
)


def _as_prompt_entry_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Validate prompt entries and render them with the legacy manifest shape."""
    if value is None:
        return ()
    if not is_object_list(value):
        raise RuntimeError(f"{field_name} must be a list")
    return tuple(_render_prompt_entry(item, f"{field_name} entries") for item in value)


def _render_prompt_entry(value: object, field_name: str) -> str:
    """Render one prompt entry after validating supported YAML shapes."""
    if isinstance(value, str):
        return value
    if not is_string_object_dict(value):
        if isinstance(value, dict):
            raise RuntimeError(f"{field_name} must be a mapping")
        raise RuntimeError(f"{field_name} entries must be strings or mappings")
    mapping = dict(value)
    if not mapping:
        raise RuntimeError(f"{field_name} mapping entries must not be empty")
    rendered: dict[str, str] = {}
    for key, item in mapping.items():
        if not isinstance(item, str):
            raise RuntimeError(f"{field_name} mapping values must be strings")
        rendered[key] = item
    return str(rendered)


TEMPLATE_ROOT = ROOT / "templates" / "agents"

CODE_TEMPLATE_ROOT = ROOT / "templates" / "code"

TEMPLATE_PARTIAL_ROOT = TEMPLATE_ROOT / "_partials"

TEMPLATE_PARTIAL_RE = re.compile(r"\{\{>\s*([A-Za-z0-9_-]+)\s*\}\}")


def _required_spec_source_root(spec: RunBundleSpec) -> Path:
    """Return the source root carried by a run spec, without guessing."""
    source_root = spec.agentcanon_source_root
    if source_root is None and spec.repository_roots is not None:
        source_root = spec.repository_roots.agentcanon_source_root
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    return source_root.resolve()


DEPENDENCY_MANIFEST_CLOSE_MARKER = "-->"

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
    "cpp/CMakeLists.txt",
    "cpp/cmake/",
    "cpp/src/",
    "cpp/include/",
    "tests/cpp/",
    "cpp/experiments/",
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
    "documents/notes/knowledge/",
    "documents/notes/",
    "tools/catalog.yaml",
)

SUBAGENT_STARTUP_ROUTE = "agents/internal-routines/subagent-startup.md"

CHECKOUT_IDENTITY_FIELDS = (
    "cwd",
    "git_root",
    "branch",
    "head",
    "remote",
)

CHECKOUT_IDENTITY_BOUNDARIES = (
    "agent_or_work_unit_start",
    "after_cwd_or_checkout_change",
    "before_conflict_resolution",
    "before_commit_push_or_pr",
    "before_cleanup_or_destructive_git",
    "subagent_handoff_and_final_handback",
)

CHECKOUT_IDENTITY_COMMAND = (
    "python3 tools/runtime/authority/checkout_identity.py --format lines"
)

DEFERRED_SPAWN_ROLE_IDS = {
    "implementer",
    "change_reviewer",
    "final_reviewer",
    "verifier",
    "auditor",
}

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
    "agents/canonical/CODEX_IMPLEMENTATION.md#5-implementation"
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
    "見た目の広さ、Owner-Bounded Change、MVP、thin slice は暫定的な routing "
    "signal に留め、owner boundary や "
    "impact surface が違うと分かった時点で route を更新する。contract gap、"
    "責務境界、API shape、依存方向、runtime contract の不足は "
    "design_issue_blocker として Gate 5-6 へ戻す。"
)

REPO_TOOL_ROUTING_POLICY_SOURCE = "agents/skills/task-routing.md#Standard Command"

REPO_TOOL_ROUTING_OWNER = "tools/runtime/dispatch/tool_dispatch.py"

REPO_TOOL_ROUTING_STATUS = "selected_native_argv"

REPO_TOOL_ROUTING_ROUTE_BASIS = "selected_public_skills"

REPO_TOOL_ROUTING_EXECUTION_MODE = "selected_skill_then_native_command"

REPO_TOOL_ROUTING_SEQUENCE = (
    "select_existing_entrypoint",
    "execute_native_argv",
    "record_process_result",
)

REPO_TOOL_ROUTING_RESULT_FIELDS = (
    "tool_route",
    "argv",
    "cwd",
    "env",
    "exit",
    "stdout",
    "stderr",
)

# DECISION_SUFFICIENCY_OWNER = "agents/skills/agent-orchestration.md#Decision Sufficiency Packet"
DECISION_SUFFICIENCY_OWNER = (
    "agents/skills/agent-orchestration.md#Decision Sufficiency Packet"
)

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
    "reuse survey、stale-surface scan、dependency expansion から導く handoff 制約。"
    "known な reuse survey asset context から重複する責務 slice を統合する"
)

PRE_HANDOFF_GATE_STATUS_SOURCE = "agents/COMMUNICATION_PROTOCOL.md#Handoff Packet"

PRE_HANDOFF_GATE_STATUS_DEFAULT = "pending_design_review_gate_check"

PRE_HANDOFF_GATE_STATUS_REQUIRED_EVIDENCE = (
    "current_design_brief",
    "design_review_artifact_under_review",
    "design_review_decision_approve",
    "waterfall_gate_check_design_pass",
    "document_flow_review_when_active",
)

VALIDATION_FAILURE_TRIAGE_TRIGGER = "validation_failure_requires_parallel_triage"

VALIDATION_FAILURE_TAXONOMY_SOURCE = (
    "documents/runtime/runtime-profiles-and-check-matrix.json"
)

RUNTIME_PROFILE_INVENTORY_PATH = ROOT / VALIDATION_FAILURE_TAXONOMY_SOURCE


class ValidationFailureResponsePolicy(TypedDict):
    """Owner projection read from the validation-failure taxonomy."""

    taxonomy_source: str
    required_fields: tuple[str, ...]
    intent_preservation: tuple[str, ...]


_validation_failure_response_policy_cache: ValidationFailureResponsePolicy | None = None

DEFAULT_QUALITY_CHECK_POLICY_SOURCE = (
    "agents/canonical/CODEX_SUBAGENTS.md#Quality Check Default"
)

DEFAULT_QUALITY_CHECK_STATIC_COMMANDS = (
    ("tools/bin/agent-canon", "docs", "check", "<changed-markdown-paths>"),
    ("python3", "tools/validation/semantic/convention/check_convention_compliance.py"),
)

CANONICAL_FORMAT_CHECK_ROUTE = DEFAULT_QUALITY_CHECK_STATIC_COMMANDS[0]

OFFICIAL_HOOK_DISPATCHER = "tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs"

OFFICIAL_HOOK_SCHEMA = "agent-canon.posttooluse-stop.v1"

OOP_EVIDENCE_DIMENSIONS = (
    "owner_overlap",
    "state_ownership",
    "api_boundary",
    "dependency_boundary",
)


def validation_failure_response_policy(
    source_root: Path | None = None,
) -> ValidationFailureResponsePolicy:
    """Return validation-failure response taxonomy from the JSON owner."""
    global _validation_failure_response_policy_cache
    if _validation_failure_response_policy_cache is None or source_root is not None:
        raw_data: object = json.loads(
            ((source_root or ROOT) / VALIDATION_FAILURE_TAXONOMY_SOURCE).read_text(
                encoding="utf-8"
            )
        )
        if not is_string_object_dict(raw_data):
            raise ValueError("validation failure response taxonomy must be an object")
        raw_policy = raw_data.get("validation_failure_response")
        if not is_string_object_dict(raw_policy):
            raise ValueError("validation_failure_response must be an object")
        policy = raw_policy
        required_fields = policy.get("required_fields")
        intent_preservation = policy.get("intent_preservation")
        if not is_object_list(required_fields):
            raise ValueError(
                "validation_failure_response.required_fields must be strings"
            )
        required_field_values = tuple(
            field for field in required_fields if isinstance(field, str)
        )
        if len(required_field_values) != len(required_fields):
            raise ValueError(
                "validation_failure_response.required_fields must be strings"
            )
        if not is_object_list(intent_preservation):
            raise ValueError(
                "validation_failure_response.intent_preservation must be strings"
            )
        intent_preservation_values = tuple(
            value for value in intent_preservation if isinstance(value, str)
        )
        if len(intent_preservation_values) != len(intent_preservation):
            raise ValueError(
                "validation_failure_response.intent_preservation must be strings"
            )
        policy_cache: ValidationFailureResponsePolicy = {
            "taxonomy_source": VALIDATION_FAILURE_TAXONOMY_SOURCE,
            "required_fields": required_field_values,
            "intent_preservation": intent_preservation_values,
        }
        if source_root is None:
            _validation_failure_response_policy_cache = policy_cache
    else:
        policy_cache = _validation_failure_response_policy_cache
    return {
        "taxonomy_source": policy_cache["taxonomy_source"],
        "required_fields": policy_cache["required_fields"],
        "intent_preservation": policy_cache["intent_preservation"],
    }


SAME_ROLE_SUBAGENT_INSTANCE_POLICY = {
    "status": "allowed_with_distinct_packets",
    "identity_key": "role_id+instance_id+agent_type",
    "parallel_read_only": "allowed_when_input_packets_or_review_focus_are_distinct",
    "parallel_write": "allowed_only_with_disjoint_writer_targets",
    "collision_policy": "reject_same_checkout_root_before_spawn",
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
    "writer_target",
)

WRITER_TARGET_REQUIRED_FIELDS = (
    "checkout_root",
    "branch",
    "remote",
    "allowed_paths",
)

COORDINATION_CAPABILITY_CONTRACT_REF = (
    "agents/COMMUNICATION_PROTOCOL.md#Runtime Collaboration Capability Handshake"
)
COORDINATION_RECEIPT_CONTRACT_REF = (
    "agents/COMMUNICATION_PROTOCOL.md#Coordination Receipt"
)
COORDINATION_OPERATION_OBSERVATION = COLLABORATION_OPERATIONS


COMMON_PROMPT_MUST_INCLUDE = (
    "request_clause_ids",
    "run_report_dir",
    "team_manifest_path",
    "user_facing_language_policy",
    "contract_complete_implementation_policy",
    "pre_handoff_scope_policy",
    "reuse_survey",
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
    "dependency_files_header_plan",
    "next_review_gate",
    "checkout_identity",
)

REUSE_SURVEY_PROMPT_INSTRUCTION = (
    "For code split/extraction or a missing suspected predecessor, the splitter must "
    "investigate current and git-history assets before decomposition or prototyping. "
    "Carry the existing optional reuse_survey with known current/historical asset "
    "paths, dispositions, reasons, and test paths; derive allowed_paths and "
    "responsibility slices from the same known context, consolidate overlapping "
    "responsibility/asset slices before child prompts, and pass that context to "
    "applicable writers and children. Missing context is non-blocking."
)

REUSE_SURVEY_PROMPT_ROLES = frozenset(
    {"designer", "implementer", "integration_executor", "change_reviewer"}
)
REUSE_SURVEY_PROMPT_FAMILIES = frozenset({"owner_bounded_change", "scoped_change"})

EVALUATOR_PROMPT_MUST_INCLUDE = (
    "current_scenario_packet",
    "packet_listed_evaluation_files",
    "do_not_read",
    "expected_output_schema",
)


def same_role_subagent_policy_output_lines() -> tuple[str, ...]:
    """Return machine-readable stdout lines for same-role subagent instances."""
    return (
        f"SAME_ROLE_SUBAGENT_INSTANCES={SAME_ROLE_SUBAGENT_INSTANCE_POLICY['status']}",
        f"SAME_ROLE_SUBAGENT_INSTANCE_KEY={SAME_ROLE_SUBAGENT_INSTANCE_POLICY['identity_key']}",
        "SAME_ROLE_SUBAGENT_REQUIRED_FIELDS="
        f"{','.join(SAME_ROLE_SUBAGENT_REQUIRED_FIELDS)}",
    )


def writer_target_policy_output_lines() -> tuple[str, ...]:
    """Return the pre-spawn writer-target contract."""
    return (
        "WRITER_TARGET_POLICY=required_for_write_capable_handoffs",
        "WRITER_TARGET_PREPARED_BY=repository-topic-clone.prepare",
        "WRITER_TARGET_COLLISION=reject_same_checkout_root_before_spawn",
        f"WRITER_TARGET_FIELDS={','.join(WRITER_TARGET_REQUIRED_FIELDS)}",
        "WRITER_TARGET_PRETOOLUSE_ENV=AGENT_CANON_CHECKOUT_ROOT,AGENT_CANON_CHECKOUT_BRANCH,AGENT_CANON_WRITER_ALLOWED_PATHS(JSON)",
        "WRITER_TARGET_READERS=target_omitted_and_shareable",
        "WRITER_TARGET_REGISTRY=none",
    )


def checkout_identity_policy_output_lines() -> tuple[str, ...]:
    """Return the bounded checkout readback contract for run output."""
    return (
        "CHECKOUT_IDENTITY_POLICY=bounded_transition_readback",
        f"CHECKOUT_IDENTITY_FIELDS={','.join(CHECKOUT_IDENTITY_FIELDS)}",
        f"CHECKOUT_IDENTITY_BOUNDARIES={','.join(CHECKOUT_IDENTITY_BOUNDARIES)}",
        f"CHECKOUT_IDENTITY_COMMAND={CHECKOUT_IDENTITY_COMMAND}",
        "CHECKOUT_IDENTITY_AUTHORITY=observational_only",
        "CHECKOUT_IDENTITY_REPETITION=do_not_repeat_unchanged_state",
    )


def coordination_capability_policy_output_lines() -> tuple[str, ...]:
    """Return manifest lines for the explicit runtime capability handshake."""
    return (
        "COORDINATION_CAPABILITY_SOURCE=direct_runtime_collaboration_namespace",
        "COORDINATION_CAPABILITY_STATUS=unverified",
        "COORDINATION_CAPABILITY_EFFECTIVE_OPERATIONS=none",
        "COORDINATION_CAPABILITY_EVIDENCE_REF=none",
        "COORDINATION_CAPABILITY_TRANSPORT=durable_artifact",
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
    del task_text
    return (
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


def selected_skill_names(selected_skills: tuple[str, ...]) -> tuple[str, ...]:
    """Return selected public skill names in stable first-seen order."""
    return tuple(
        dict.fromkeys(
            skill
            for raw_skill in selected_skills
            if (skill := normalized_public_skill_name(raw_skill))
        )
    )


def repo_tool_routing_policy_output_lines(
    selected_skills: tuple[str, ...],
    *,
    source_root: Path | None = None,
) -> tuple[str, ...]:
    """Return stdout lines for selected-skill repo tool routing."""
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    skill_names = selected_skill_names(selected_skills)
    skill_list = ",".join(f"${skill}" for skill in skill_names) or "-"
    return (
        "REPO_TOOL_ROUTING_POLICY=run.repo_tool_routing_policy",
        "REPO_TOOL_CALL_TOKEN_SCHEMA=agent-canon.tool-call.v1",
        f"REPO_TOOL_SELECTED_SKILLS={skill_list}",
        f"REPO_TOOL_ROUTING_SOURCE={REPO_TOOL_ROUTING_POLICY_SOURCE}",
        f"REPO_TOOL_ROUTING_OWNER={REPO_TOOL_ROUTING_OWNER}",
        f"REPO_TOOL_ROUTING_ROUTE_BASIS={REPO_TOOL_ROUTING_ROUTE_BASIS}",
        f"REPO_TOOL_ROUTING_EXECUTION_MODE={REPO_TOOL_ROUTING_EXECUTION_MODE}",
        f"REPO_TOOL_ROUTING_SEQUENCE={','.join(REPO_TOOL_ROUTING_SEQUENCE)}",
        f"REPO_TOOL_ROUTING_RESULT_FIELDS={','.join(REPO_TOOL_ROUTING_RESULT_FIELDS)}",
    )


def default_quality_check_policy_output_lines(
    roles: tuple[Role, ...],
    *,
    manual_specialists: tuple[str, ...] = (),
    task_default_specialists: tuple[str, ...] = (),
    language_review_candidates: tuple[str, ...] = (),
    default_review_packs_enabled: bool = False,
    default_review_pack_ids: tuple[str, ...] = (),
    layout: str = "standalone",
) -> tuple[str, ...]:
    """Return machine-readable stdout lines for default quality-check routing."""
    review_pack_state = "active" if default_review_packs_enabled else "candidate_only"
    return (
        "DEFAULT_QUALITY_CHECKS=candidate_only",
        f"DEFAULT_QUALITY_CHECK_SOURCE={DEFAULT_QUALITY_CHECK_POLICY_SOURCE}",
        "DEFAULT_QUALITY_CHECK_ROLE_CANDIDATES="
        f"{','.join(default_quality_check_role_ids(roles)) or '-'}",
        "DEFAULT_QUALITY_CHECK_AGENT_TYPE_CANDIDATES="
        f"{','.join(default_quality_check_agent_types(roles)) or '-'}",
        f"DEFAULT_QUALITY_CHECK_EVIDENCE={','.join(OOP_EVIDENCE_DIMENSIONS)}",
        "DEFAULT_FORMAT_CHECK_ROUTE="
        + public_command_for_layout(CANONICAL_FORMAT_CHECK_ROUTE, layout),
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
    *,
    source_root: Path | None = None,
    issue_worker_candidate: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Return task-specific Skill links as guidance, never as a start gate."""
    selected = ["$agent-orchestration", "$codex-task-workflow"]
    del issue_worker_candidate
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
            "routing-only",
            load_skill_route_rules(source_root or ROOT),
        )
        selected.extend(f"${skill}" for skill in decision.skills)
    return tuple(dict.fromkeys(selected))


def public_command_for_layout(
    command: Sequence[str] | str,
    layout: str,
) -> str:
    """Render structured argv with shell quoting for display only."""
    del layout
    if isinstance(command, str):
        # Compatibility callers still provide documentation-only constants;
        # they are returned verbatim and never parsed or executed.
        return command
    else:
        argv = tuple(command)
    return shlex.join(argv)


def public_command_for_spec(
    spec: RunBundleSpec,
    command: Sequence[str] | str,
) -> str:
    """Render one command through the selected source/public layout owner."""
    roots = spec.repository_roots
    layout = (
        getattr(roots, "layout", "standalone") if roots is not None else "standalone"
    )
    return public_command_for_layout(command, layout)


def language_review_candidates(
    workspace_root: Path,
    changed_paths: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Return explicit language-review candidates from changed paths."""
    candidate_paths = changed_paths
    normalized_paths = tuple(
        raw_path.replace("\\", "/").lstrip("./") for raw_path in candidate_paths
    )
    has_python = any(
        normalized.startswith("python/")
        or (normalized.startswith("tests/") and not normalized.startswith("tests/cpp/"))
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


def render_template_partial(
    partial_name: str,
    seen: tuple[str, ...] = (),
    *,
    source_root: Path | None = None,
) -> str:
    """Load one reusable template partial without leaking its manifest into output."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", partial_name):
        raise RuntimeError(f"invalid template partial name: {partial_name}")
    if partial_name in seen:
        chain = " -> ".join((*seen, partial_name))
        raise RuntimeError(f"recursive template partial include: {chain}")
    template_root = (source_root or ROOT) / "templates" / "agents"
    path = template_root / "_partials" / f"{partial_name}.md"
    if not path.is_file():
        raise RuntimeError(f"template partial not found: {partial_name}")
    content = strip_dependency_manifest(path.read_text(encoding="utf-8"))
    return expand_template_partials(
        content, (*seen, partial_name), source_root=source_root
    )


def expand_template_partials(
    content: str,
    seen: tuple[str, ...] = (),
    *,
    source_root: Path | None = None,
) -> str:
    """Expand reusable partial markers in one template body."""
    return TEMPLATE_PARTIAL_RE.sub(
        lambda match: render_template_partial(
            match.group(1), seen, source_root=source_root
        ),
        content,
    )


def apply_template_replacements(content: str, replacements: dict[str, str]) -> str:
    """Apply run-specific replacements to one rendered template."""
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
        content = content.replace(f"{{\\{{{key}}}}}", value)
    return content


def render_template(
    template_name: str,
    replacements: dict[str, str],
    *,
    source_root: Path | None = None,
) -> str:
    """Load and fill a text template from templates/agents."""
    template_root = (source_root or ROOT) / "templates" / "agents"
    content = (template_root / template_name).read_text(encoding="utf-8")
    content = expand_template_partials(content, source_root=source_root)
    content = apply_template_replacements(content, replacements)
    return content


def render_code_template(template_name: str) -> str:
    """互換 facade から package-safe code-template renderer を呼び出します."""
    from tools.agent.templates.code_template_rendering import (
        render_code_template as render_source,
    )

    return render_source(template_name)


def has_template(artifact_name: str, *, source_root: Path | None = None) -> bool:
    """Return whether a template exists for one artifact filename."""
    template_root = (source_root or ROOT) / "templates" / "agents"
    return (template_root / artifact_name).is_file()


def required_output_templates_missing(
    config: TeamConfig,
    roles: tuple[Role, ...],
    allowed_missing: tuple[str, ...] = (),
    *,
    source_root: Path | None = None,
) -> tuple[str, ...]:
    """Return required output templates that are missing from templates/agents."""
    return tuple(
        dict.fromkeys(
            output
            for role in roles
            for output in role.required_outputs
            if output not in allowed_missing
            and not has_template(output, source_root=source_root)
        )
    )


def build_manifest(spec: RunBundleSpec) -> str:
    """Build the team manifest yaml."""
    workflow_family = None
    if spec.workflow_family_id:
        if spec.task_catalog is None:
            raise RuntimeError(
                "task catalog is required for workflow manifest rendering"
            )
        workflow_family = resolve_workflow_family(
            spec.task_catalog, spec.workflow_family_id
        )
    active_design_packet = (
        spec.active_design_packet
        or resolve_active_design_packet_config(
            spec.config,
            workflow_family=workflow_family,
        )
    )
    lines = manifest_run_lines(spec, workflow_family)
    lines.extend(manifest_role_lines(spec, workflow_family, active_design_packet))
    lines.extend(manifest_context_policy_lines(spec.config, active_design_packet))
    lines.extend(manifest_quality_gate_lines(spec.config))
    lines.extend(manifest_artifact_lines(spec.config, spec.roles, active_design_packet))
    return "\n".join(lines) + "\n"


def manifest_run_lines(
    spec: RunBundleSpec,
    workflow_family: dict[str, object] | None,
) -> list[str]:
    """Render run-level manifest fields."""
    active_design_packet = (
        spec.active_design_packet
        or resolve_active_design_packet_config(
            spec.config,
            workflow_family=workflow_family,
        )
    )
    source_root = _required_spec_source_root(spec)
    lines = [
        "run:",
        f"  id: {spec.run_id}",
        f"  task: {spec.task!r}",
        f"  owner: {spec.owner!r}",
        f"  created_at_utc: {spec.created_at_iso}",
        f"  report_dir: {str(spec.report_dir)!r}",
        f"  workspace_root: {str(spec.workspace_root)!r}",
        f"  team_config: {str(source_root / 'agents' / 'agents_config.json')!r}",
        f"  team_runtime: {str(source_root / 'tools' / 'agent' / 'orchestration' / 'agent_team.py')!r}",
        f"  task_catalog: {str(source_root / str(spec.config.team['task_catalog']))!r}",
        "  checkout_identity:",
        *(
            f"    {field}: {value!r}"
            for field, value in resolve_checkout_identity(spec.workspace_root)
            .as_dict()
            .items()
        ),
    ]
    if spec.issue_worker_dispatch is not None:
        lines.append("  issue_worker_dispatch:")
        lines.extend(_yaml_mapping_lines(spec.issue_worker_dispatch, indent=4))
    lines.append("  active_design_packet:")
    packet_yaml = yaml.safe_dump(
        active_design_packet_mapping(active_design_packet),
        sort_keys=False,
        default_flow_style=False,
    ).splitlines()
    lines.extend(f"    {line}" for line in packet_yaml)
    math_intent_packet = resolve_math_intent_packet_for_spec(spec)
    math_intent_route_id = math_intent_route_id_for_spec(spec)
    if math_intent_route_id is not None:
        if math_intent_packet is None:
            raise RuntimeError("math_packet_missing")
        lines.append(f"  math_intent_route_id: {math_intent_route_id!r}")
        lines.append("  math_intent_route:")
        route_yaml = yaml.safe_dump(
            dict(
                mathematical_intent_route_config(
                    spec.task_catalog, math_intent_route_id
                )
                or {}
            ),
            sort_keys=False,
            default_flow_style=False,
        ).splitlines()
        lines.extend(f"    {line}" for line in route_yaml)
        lines.append("  mathematical_intent_packet:")
        math_yaml = yaml.safe_dump(
            mathematical_intent_packet_mapping(math_intent_packet),
            sort_keys=False,
            default_flow_style=False,
        ).splitlines()
        lines.extend(f"    {line}" for line in math_yaml)
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
            "  subagent_lifecycle_policy:",
            "    fresh_subagents_required: conditional",
            "    reuse_for_new_task: allowed_when_owner_context_compatible",
            "    previous_task_subagent_reuse: allowed_when_owner_context_compatible",
            "    same_task_delta_reuse: allowed_when_owner_context_compatible",
            "    scope_change_reuse: evaluate_owner_context_compatibility",
            "    new_task_reuse: evaluate_owner_context_compatibility",
            "    close_before_user_completion: true",
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
            f"    implementation_surface_route_command: {public_command_for_spec(spec, ('tools/bin/agent-canon', 'agent-search', '--query-file', '<request-or-design-question.txt>', '--providers', 'semantic', '--format', 'json'))!r}",
            "    pre_edit_rejection_prediction_status: optional_diagnostic",
            f"    pre_edit_rejection_command: {public_command_for_spec(spec, ('tools/bin/agent-canon', 'tool-rejection-preflight', '--root', '.', '<planned-edit-paths>'))!r}",
            *manifest_user_facing_language_policy_lines(),
            *manifest_contract_complete_implementation_policy_lines(
                spec.task,
            ),
            *manifest_pre_handoff_scope_policy_lines(),
            *manifest_pre_handoff_gate_status_lines(
                active_design_packet,
                layout=getattr(spec.repository_roots, "layout", "standalone"),
            ),
            *manifest_decision_sufficiency_lines(spec),
            *manifest_repo_tool_routing_policy_lines(spec),
            *manifest_default_quality_check_policy_lines(spec),
            "  agent_report_collection:",
            f"    status_command: {public_command_for_spec(spec, ('python3', 'tools/runtime/archive/runtime_log_archive_git.py', 'status'))!r}",
            f"    archive_current_run_command: {public_command_for_spec(spec, ('python3', 'tools/runtime/archive/runtime_log_archive_git.py', 'archive-agent-report', '--report-dir', str(spec.report_dir)))!r}",
            f"    sync_command: {public_command_for_spec(spec, ('python3', 'tools/runtime/archive/runtime_log_archive_git.py', 'sync'))!r}",
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
    lines.extend(
        [
            "  coordination_capability_handshake:",
            f"    contract_ref: {COORDINATION_CAPABILITY_CONTRACT_REF!r}",
            "    source: direct_runtime_collaboration_namespace",
            "    status: unverified",
            "    effective_operations: []",
            "    evidence_ref: ''",
            "    matcher_is_not_capability_evidence: true",
            "    forbidden_capability_source: functions.exec.ALL_TOOLS",
            "    transport_by_status:",
            "      available: direct_peer",
            "      unavailable: parent_relay_or_durable_artifact",
            "      unverified: parent_relay_or_durable_artifact",
            "  coordination_receipt_policy:",
            f"    contract_ref: {COORDINATION_RECEIPT_CONTRACT_REF!r}",
            "    operation_observation:",
            *(
                f"      - {operation}"
                for operation in COORDINATION_OPERATION_OBSERVATION
            ),
            "    direct_peer_requires: available_status_and_operation_evidence",
            "    parent_relay_is_not_direct_peer: true",
        ]
    )
    communication_protocol = spec.config.team.get("communication_protocol")
    if communication_protocol is not None:
        lines.append(
            f"  communication_protocol: {str(source_root / str(communication_protocol))!r}"
        )
    if workflow_family is not None:
        lines.append("  workflow_family:")
        lines.append(f"    id: {spec.workflow_family_id}")
        lines.append(f"    name: {str(workflow_family['name'])!r}")
        lines.extend(render_role_topology(workflow_family, indent="    "))
        lines.extend(render_subagent_prompt_packet(workflow_family, indent="  "))
    lines.append("  write_scope_policy:")
    lines.append("    parent_managed: true")
    lines.append("    scope_source_ref: run.pre_handoff_scope_policy")
    lines.append("    handoff_scope_status: seed_then_expand_before_handoff")
    lines.append("    disjoint_write_scopes_required: true")
    lines.append("    overlapping_write_scopes: reject_same_checkout_root_before_spawn")
    lines.append("  writer_target_policy:")
    lines.append("    required_for: write_capable_handoffs")
    lines.append("    prepared_by: repository-topic-clone.prepare")
    lines.append("    collision: reject_same_checkout_root_before_spawn")
    lines.append(
        "    pretooluse_environment: "
        "AGENT_CANON_CHECKOUT_ROOT,AGENT_CANON_CHECKOUT_BRANCH,AGENT_CANON_WRITER_ALLOWED_PATHS(JSON)"
    )
    lines.append("    fields:")
    for field in WRITER_TARGET_REQUIRED_FIELDS:
        lines.append(f"      - {field}")
    lines.append("    readers: target_omitted_and_shareable")
    lines.append("    registry: none")
    lines.append("  same_role_instances:")
    lines.append(f"    status: {SAME_ROLE_SUBAGENT_INSTANCE_POLICY['status']}")
    lines.append(
        f"    identity_key: {SAME_ROLE_SUBAGENT_INSTANCE_POLICY['identity_key']!r}"
    )
    lines.append(
        "    parallel_read_only: "
        f"{SAME_ROLE_SUBAGENT_INSTANCE_POLICY['parallel_read_only']}"
    )
    lines.append(
        f"    parallel_write: {SAME_ROLE_SUBAGENT_INSTANCE_POLICY['parallel_write']}"
    )
    lines.append(
        "    collision_policy: "
        f"{SAME_ROLE_SUBAGENT_INSTANCE_POLICY['collision_policy']}"
    )
    lines.append("    required_fields:")
    for field in SAME_ROLE_SUBAGENT_REQUIRED_FIELDS:
        lines.append(f"      - {field}")
    lines.append("  validation_failure_response_policy:")
    lines.append(f"    trigger: {VALIDATION_FAILURE_TRIAGE_TRIGGER}")
    lines.append("    triage_write_scope: read_only_until_cause_identified")
    validation_policy = validation_failure_response_policy(spec.agentcanon_source_root)
    lines.append(f"    taxonomy_source: {validation_policy['taxonomy_source']}")
    lines.append("    repair_required_fields:")
    for field in validation_policy["required_fields"]:
        lines.append(f"      - {field}")
    lines.append("    intent_preservation_values:")
    for value in validation_policy["intent_preservation"]:
        lines.append(f"      - {value}")
    lines.append("  cross_cutting_document_packet:")
    cross_cutting_packet = resolve_cross_cutting_document_packet(
        spec.workspace_root,
        _required_spec_source_root(spec),
    )
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
    *,
    layout: str = "standalone",
) -> list[str]:
    """Render the pre-handoff gate status contract."""
    design_argv = (
        "tools/bin/agent-canon",
        "waterfall-gate-check",
        "--report-dir",
        "<report-dir>",
        "--gate",
        "design",
    )
    del layout
    design_command = shlex.join(list(design_argv))
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
            f"    design_gate_command: {design_command!r}",
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
        source_root=_required_spec_source_root(spec),
        issue_worker_candidate=spec.issue_worker_candidate,
    )
    skill_names = selected_skill_names(selected_skills)
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
    lines.append("    result_fields:")
    for field in REPO_TOOL_ROUTING_RESULT_FIELDS:
        lines.append(f"      - {field}")
    lines.append("    selected_skills:")
    for skill in skill_names:
        lines.append(f"      - ${skill}")
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
        "    role_topology_ref: 'agents/task_catalog.yaml#role_topology_defaults.role_families.review'",
    ]
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
        lines.append(f"      - {public_command_for_spec(spec, command)!r}")
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
    if math_intent_route_id_for_spec(spec) is not None and role.id in {
        "implementer",
        "mathematical_correctness_reviewer",
    }:
        lines.append(
            "    mathematical_intent_packet_ref: run.mathematical_intent_packet"
        )
        lines.append("    math_intent_write_scope: mapped_allowed_paths_only")
        lines.append(
            "    math_intent_forbidden_surfaces: architecture,framework,jit,compiler,backend,runtime,container,docker,routing,environment,proof,ir"
        )
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
            "      assignment_prompt: 'runtime_materialized_fixed_packet_prompt_only'"
        )
        lines.append(
            "      assignment_prompt_source: "
            "'tools/agent/orchestration/agent_team.py#dispatch_fixed_implementation->model_profile_registry.materialize_prompt_capsule'"
        )
    else:
        lines.append(
            "      assignment_prompt: "
            f"{compact_role_prompt_contract(role, workflow_family)!r}"
        )
        lines.append(
            "      assignment_prompt_source: "
            "'tools/agent/orchestration/agent_team.py#role_prompt_contract'"
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


def reuse_survey_prompt_instruction(
    role: Role,
    workflow_family: dict[str, object] | None,
) -> str:
    """Return optional reuse context guidance for applicable role prompts."""
    if workflow_family is None:
        return ""
    if workflow_family.get("id") not in REUSE_SURVEY_PROMPT_FAMILIES:
        return ""
    if role.id not in REUSE_SURVEY_PROMPT_ROLES:
        return ""
    return REUSE_SURVEY_PROMPT_INSTRUCTION


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
    if role.write_policy.conditional_artifacts:
        lines.append("      conditional_artifacts:")
        for condition, artifact_keys in sorted(
            role.write_policy.conditional_artifacts.items()
        ):
            lines.append(f"        {condition}:")
            for artifact_key in artifact_keys:
                lines.append(
                    f"          - {artifact_key!r}: {spec.config.artifacts[artifact_key]!r}"
                )
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
        _required_spec_source_root(spec),
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
                lines.append(f"              required: {str(section.required).lower()}")
    return lines


def manifest_context_policy_lines(
    config: TeamConfig,
    active_design_packet: ActiveDesignPacketConfig,
) -> list[str]:
    """Render context-sharing policy lines."""
    lines = ["context_policies:"]
    packet_artifacts = active_design_packet_artifact_map(config, active_design_packet)
    for policy in config.context_policies:
        lines.append("  - roles:")
        for role_name in as_string_tuple(policy.get("roles"), "context_policies.roles"):
            lines.append(f"      - {role_name}")
        mode = as_required_string(policy.get("mode"), "context_policies.mode")
        lines.append(f"    mode: {mode}")
        lines.append("    share_only:")
        for artifact in as_string_tuple(
            policy.get("share_only"), "context_policies.share_only"
        ):
            lines.append(f"      - {packet_artifacts.get(artifact, artifact)}")
        lines.append("    do_not_share:")
        for artifact in as_string_tuple(
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
    if not is_string_object_dict(topology):
        if not isinstance(topology, dict):
            return []
        raise RuntimeError("role_topology must be a mapping")
    lines = [f"{indent}role_topology:"]
    role_families = topology.get("role_families")
    if is_string_object_dict(role_families):
        lines.append(f"{indent}  role_families:")
        for family_name, agent_types in role_families.items():
            lines.append(f"{indent}    {family_name}:")
            if is_object_list(agent_types):
                for agent_type in as_string_tuple(
                    agent_types,
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
    elif isinstance(role_families, dict):
        raise RuntimeError("role_topology.role_families must be a mapping")
    same_role_instances = topology.get("same_role_parallel_instances")
    if is_string_object_dict(same_role_instances):
        lines.append(f"{indent}  same_role_parallel_instances:")
        for key, value in same_role_instances.items():
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
    elif isinstance(same_role_instances, dict):
        raise RuntimeError(
            "role_topology.same_role_parallel_instances must be a mapping"
        )
    return lines


def render_subagent_prompt_packet(
    workflow_family: dict[str, object],
    indent: str,
) -> list[str]:
    """Render workflow-specific subagent prompt instructions for the manifest."""
    prompt = workflow_family.get("subagent_prompt")
    if not is_string_object_dict(prompt):
        if not isinstance(prompt, dict):
            return []
        raise RuntimeError("subagent_prompt must be a mapping")
    lines = [f"{indent}subagent_prompt_packet:"]
    purpose = as_optional_string(prompt.get("purpose"), "subagent_prompt.purpose")
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
    lines.append(f"{indent}  native_argv: 'run.repo_tool_routing_policy'")
    lines.append(f"{indent}  tool_evidence: 'run.repo_tool_routing_policy'")
    lines.append(f"{indent}  tool_catalog_matches: 'tools/catalog.yaml'")
    for key in ("dispatch_route", "execution_role", "tool_call_route"):
        value = as_optional_string(
            prompt.get(key),
            f"subagent_prompt.{key}",
        )
        if value:
            lines.append(f"{indent}  {key}: {value!r}")
    lines.append(f"{indent}  required_tool_fields:")
    lines.append(f"{indent}    - tool_route")
    lines.append(f"{indent}    - native_argv")
    lines.append(f"{indent}    - tool_evidence")
    lines.append(f"{indent}  checkout_identity:")
    lines.append(f"{indent}    command: {CHECKOUT_IDENTITY_COMMAND!r}")
    lines.append(f"{indent}    fields:")
    for field in CHECKOUT_IDENTITY_FIELDS:
        lines.append(f"{indent}      - {field}")
    lines.append(f"{indent}    readback_boundaries:")
    for boundary in CHECKOUT_IDENTITY_BOUNDARIES:
        lines.append(f"{indent}      - {boundary}")
    lines.append(
        f"{indent}    repetition: 'reuse the same block until checkout state changes'"
    )
    for key in ("prompt_preamble", "workflow_focus", "reviewer_prompt"):
        lines.append(f"{indent}  {key}:")
        for value in _as_prompt_entry_tuple(prompt.get(key), f"subagent_prompt.{key}"):
            lines.append(f"{indent}    - {value!r}")
        if (
            key == "workflow_focus"
            and workflow_family.get("id") in REUSE_SURVEY_PROMPT_FAMILIES
        ):
            lines.append(f"{indent}    - {REUSE_SURVEY_PROMPT_INSTRUCTION!r}")
    return lines


def role_prompt_contract(role: Role, workflow_family: dict[str, object] | None) -> str:
    """Return the reusable prompt contract for one manifest role entry."""
    family_name = (
        str(workflow_family["name"])
        if workflow_family is not None
        else "the selected workflow"
    )
    write_scope = (
        "when the physical sandbox and handoff permit writes, write only in the manifest "
        "write_policy scope and avoid paths assigned to other writers; otherwise return "
        "the assigned result inline without editing files"
        if role.write_policy.mode != "read_only"
        else "do not edit repository files; return the assigned result inline"
    )
    writer_target = (
        " Carry writer_target with absolute checkout_root, fixed branch, normalized remote, "
        "and allowed_paths; start in that checkout and do not switch/checkout/rename branches "
        "or create worktrees."
        if role.id in {"implementer", "integration_executor"}
        else ""
    )
    reuse_instruction = reuse_survey_prompt_instruction(role, workflow_family)
    return (
        f"You are the {role.id} role for {family_name}. Start from structured context artifacts and the "
        "owned role_document_packet named in the handoff when supplied; load cross_cutting_document_packet "
        "entries only when the selected route or review gate makes them active, otherwise mark "
        "them not_applicable. Respect allowed_paths and do_not_read when supplied by the handoff. "
        f"{write_scope}. "
        f"{writer_target} "
        f"{reuse_instruction} "
        "When run.subagent_prompt_packet.subagent_startup_route is present, carry that "
        "structural route field into the next handoff or review result without turning it "
        "into prompt keyword skill activation. "
        "The parent owns choosing the next instruction from linked task guidance and "
        "actual run evidence. Complete the assigned role task and return its actual "
        "result inline; a launch or monitor row alone is not completion. For requirements and intake "
        "assignments, include the objective, non-goals, constraints, and completion "
        "conditions in that handoff. "
        "Carry the owner-produced DecisionSufficiencyPacket reference and "
        "run.repo_tool_routing_policy tool_route, native argv, process result, and tool_evidence into "
        "the next handoff or review result when repo-owned tools are part of the selected route. "
        "Carry one checkout_identity block with cwd, git_root, branch (or detached), head, "
        "and normalized remote owner/repository at the bounded transition points; do not "
        "repeat it for ordinary commands. Do not delegate unless the handoff explicitly "
        "explicitly authorizes a native child call; do not launch an unselected child. "
        "Return findings or outputs tied to "
        "request_clause_ids, include artifact paths and dependency-file headers when files "
        "are created, and report remaining planned work or a next gate only when assigned."
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
        "bounded writer when the physical sandbox and handoff permit writes; otherwise inline handoff"
        if role.write_policy.mode != "read_only"
        else "read-only; return assigned result inline"
    )
    writer_target = (
        " carry writer_target (absolute checkout_root, fixed branch, normalized remote, allowed_paths); "
        "do not switch or rename branches or create worktrees"
        if role.id in {"implementer", "integration_executor"}
        else ""
    )
    reuse_instruction = reuse_survey_prompt_instruction(role, workflow_family)
    return (
        f"{role.id} for {family_name}; {write_scope}; use supplied handoff context and "
        "named accessible packets, respect supplied path boundaries, and use the "
        "subagent startup route and repo tool route fields when present. The parent "
        "chooses the next step from linked guidance and actual outcomes; return the "
        "assigned result inline. For "
        "requirements and intake assignments, include the objective, non-goals, "
        "constraints, and completion conditions in that handoff."
        f" Include checkout_identity in every handoff where Git state matters;{writer_target}."
        f" {reuse_instruction}"
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
    common.append("checkout_identity")
    if role.write_policy.mode != "read_only":
        common.extend(("write_policy", "allowed_files_or_directories"))
    if role.id in {"implementer", "integration_executor"}:
        common.append("writer_target")
    if role.id in REUSE_SURVEY_PROMPT_ROLES:
        common.append("reuse_survey")
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
    if role.id == "mathematical_correctness_reviewer":
        common.extend(
            (
                "mathematical_intent_packet",
                "equation_to_code_map",
                "math_oracle_or_counterexample",
                "mapped_math_allowed_paths",
                "forbidden_non_math_surfaces",
                "separate_handoff_targets",
            )
        )
    if role.id.endswith("_reviewer") or role.id in {
        "change_reviewer",
        "final_reviewer",
    }:
        common.extend(("findings_first_output", "approve_revise_or_escalate_decision"))
    return tuple(common)
