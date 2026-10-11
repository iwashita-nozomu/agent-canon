# @dependency-start
# contract tool
# responsibility Owns run bootstrap, graph readiness transitions, selected Skill loading, and host-result re-entry.
# upstream design ../../../README.md shared automation index
# upstream implementation ../values.py refines decoded command payloads
# upstream implementation ../../agent/skills/skill_document_reader.py supplies bounded canonical Skill text to file EOF
# upstream implementation ../../agent/skills/skill_route_catalog.py owns selected Skill prerequisite order and canonical documents
# @dependency-end

"""Bootstrap a persistent agent-team run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

UTC = timezone.utc
from pathlib import Path

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.agent.orchestration.agent_team import (
    ExecutionGraphTransition,
    PreparedRunBundle,
    ToolExecutionResult,
    advance_execution_graph,
    dispatch_issue_worker,
    dispatch_subagent_wave,
    materialize_subagent_spawn_tool_call,
    parse_tool_execution_result,
    prepare_run_bundle,
)
from tools.agent.orchestration.implementation_dispatch import (
    capacity_start_output_lines,
    codex_runtime_max_depth,
    codex_runtime_max_threads,
    format_agent_type_selections,
    parse_agent_type_selections,
    recommended_dynamic_expansion_wave_slots,
    recommended_initial_subagent_wave_slots,
    validate_agent_type_selections,
    workflow_spawn_budget,
)
from tools.agent.orchestration.packets import (
    ACTIVE_DESIGN_PACKET_SCHEMA,
    MATHEMATICAL_INTENT_PACKET_SCHEMA,
    ActiveDesignPacketConfig,
    MathematicalIntentPacket,
    math_intent_route_id_from_context,
    mathematical_intent_route_config,
    mathematical_intent_route_for_task,
    normalize_mathematical_intent_packet,
    parse_active_design_packet_input,
    resolve_cross_cutting_document_packet,
    resolve_role_document_packet,
    role_specific_document_entries,
)
from tools.runtime.values import is_string_object_dict, is_string_object_mapping
from tools.agent.orchestration.team_config import (
    AgentTypeSelection,
    Role,
    RunBundleSpec,
    SubagentWaveSlot,
    TaskCatalog,
    TeamConfig,
    codex_agent_model_matrix_for_roles,
    current_stage_skills,
    default_review_pack_ids_for_task,
    default_specialists_for_task,
    deferred_stage_skills,
    enable_choices,
    expand_enabled_specialists,
    load_task_catalog,
    load_team_config,
    resolve_task_spec,
    resolve_workflow_family,
    select_roles,
    task_ids,
    workflow_child_handoff_required,
)
from tools.agent.skills.skill_document_reader import (
    SkillDocumentError,
    SkillDocumentReader,
)
from tools.agent.skills.skill_route_catalog import (
    derive_skill_invocation_order,
    load_skill_route_rules,
)
from tools.runtime.authority.checkout_identity import resolve_checkout_identity
from tools.agent.orchestration.workflow_context import (
    StoreResult,
    context_from_workflows,
    store_workflow_context,
)
from tools.repository.workspace.workspace_scope import (
    make_run_id,
    resolve_report_root,
    resolve_repository_roots,
)
from tools.runtime.artifacts.runtime_artifacts import (
    RuntimeArtifactBoundary,
    runtime_artifact_boundary,
)
from tools.runtime.authority.task_authority import (
    AUTHORITY_FILE_NAME,
    hash_baseline_bytes,
)
from tools.runtime.authority.writer_target import (
    WriterTarget,
    WriterTargetError,
    parse_writer_target,
)
from tools.runtime.lifecycle.workflow_monitor import append_monitoring
from tools.runtime.manifest.manifest_rendering import (
    checkout_identity_policy_output_lines,
    contract_complete_implementation_policy_output_lines,
    coordination_capability_policy_output_lines,
    default_quality_check_policy_output_lines,
    language_review_candidates,
    pre_handoff_gate_status_output_lines,
    pre_handoff_scope_policy_output_lines,
    public_command_for_layout,
    repo_tool_routing_policy_output_lines,
    suggested_public_skills,
    user_facing_language_policy_output_lines,
)
from tools.runtime.source.agent_canon_source_root import (
    RepositoryRoots,
    resolve_agent_canon_source_root,
)


@dataclass(frozen=True)
class BootstrapRunContext:
    """Resolved run metadata for bootstrap output and bundle creation."""

    created_at_iso: str
    report_root: Path
    run_id: str
    report_dir: Path
    manual_specialists: tuple[str, ...]
    enabled_specialists: tuple[str, ...]
    task_default_specialists: tuple[str, ...]
    language_review_candidates: tuple[str, ...]
    default_review_pack_ids: tuple[str, ...]
    workflow_family_id: str | None
    workflow_family_name: str | None
    workflow_active_spawn_budget: int | None
    workflow_max_write_subagents: int | None
    adversarial_required: bool = False
    math_intent_route: str | None = None
    issue_worker_candidate: Mapping[str, object] | None = None
    repository_roots: RepositoryRoots | None = None


@dataclass(frozen=True)
class BootstrapRuntime:
    """Runtime objects created by bootstrap before output."""

    roles: tuple[Role, ...]
    created_files: tuple[str, ...]
    active_pointer: Path
    agent_type_selections: tuple[AgentTypeSelection, ...]
    active_design_packet: ActiveDesignPacketConfig
    math_intent_packet: MathematicalIntentPacket | None = None
    issue_worker_dispatch: Mapping[str, object] | None = None
    skill_documents: tuple[tuple[str, str, str], ...] = ()
    selected_skills: tuple[str, ...] = ()
    active_skills: tuple[str, ...] = ()
    deferred_skills: tuple[str, ...] = ()
    execution_transition: ExecutionGraphTransition | None = None
    execution_tool_calls: tuple[dict[str, object], ...] = ()
    execution_spawn_results: tuple[tuple[str, str], ...] = ()


def suggested_skills(
    task_id: str | None,
    workflow_family_id: str | None,
    task_text: str = "",
    *,
    source_root: Path | None = None,
    issue_worker_candidate: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Return the public skills that should be read before work starts."""
    return suggested_public_skills(
        task_id,
        workflow_family_id,
        task_text,
        source_root=source_root,
        issue_worker_candidate=issue_worker_candidate,
    )


def parse_execution_results(
    value: str | None,
) -> dict[str, dict[str, ToolExecutionResult]]:
    """Parse actual host ToolCall results keyed by existing role-instance identity."""
    if value is None:
        return {}
    try:
        raw: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("execution_results:invalid_json") from exc
    if not is_string_object_dict(raw):
        raise RuntimeError("execution_results:must_be_mapping")
    results: dict[str, dict[str, ToolExecutionResult]] = {}
    for identity, raw_result in raw.items():
        if not identity.strip() or not is_string_object_mapping(raw_result):
            raise RuntimeError("execution_results:invalid_role_result")
        if set(raw_result) - {
            "spawn_result",
            "completion_result",
            "publication_result",
        }:
            raise RuntimeError(f"execution_results:invalid_fields:{identity}")
        if "spawn_result" not in raw_result:
            raise RuntimeError(f"execution_results:spawn_result_missing:{identity}")
        parsed: dict[str, ToolExecutionResult] = {
            "spawn_result": parse_tool_execution_result(raw_result["spawn_result"])
        }
        if "completion_result" in raw_result:
            parsed["completion_result"] = parse_tool_execution_result(
                raw_result["completion_result"]
            )
        if "publication_result" in raw_result:
            parsed["publication_result"] = parse_tool_execution_result(
                raw_result["publication_result"]
            )
        results[identity] = parsed
    return results


def merge_execution_results(
    prior: Mapping[str, Mapping[str, ToolExecutionResult]],
    incoming: Mapping[str, Mapping[str, ToolExecutionResult]],
) -> dict[str, dict[str, ToolExecutionResult]]:
    """Reuse this run's completed result nodes and reject changed readback."""
    merged = {identity: dict(fields) for identity, fields in prior.items()}
    for identity, fields in incoming.items():
        current = merged.setdefault(identity, {})
        for field, result in fields.items():
            prior_result = current.get(field)
            if prior_result is not None and prior_result != result:
                raise RuntimeError(
                    f"execution_result:previous_result_changed:{identity}:{field}"
                )
            current[field] = result
    return merged


def persisted_execution_results(
    run: Mapping[str, object],
) -> dict[str, dict[str, ToolExecutionResult]]:
    """Load actual results from the existing run graph node state."""
    graph = run.get("execution_graph")
    if not is_string_object_mapping(graph):
        raise RuntimeError("execution_result:execution_graph_missing")
    state = graph.get("result_readback")
    if not is_string_object_mapping(state):
        raise RuntimeError("execution_result:result_readback_missing")
    raw_results = state.get("role_results")
    if not is_string_object_dict(raw_results):
        raise RuntimeError("execution_result:role_results_invalid")
    results: dict[str, dict[str, ToolExecutionResult]] = {}
    for identity, raw_fields in raw_results.items():
        if not isinstance(identity, str) or not is_string_object_mapping(raw_fields):
            raise RuntimeError("execution_result:role_results_invalid")
        parsed_fields: dict[str, ToolExecutionResult] = {}
        for field, raw_result in raw_fields.items():
            if field not in {
                "spawn_result",
                "completion_result",
                "publication_result",
            } or not is_string_object_mapping(raw_result):
                raise RuntimeError(f"execution_result:role_result_invalid:{identity}")
            is_error = raw_result.get("is_error")
            text = raw_result.get("text")
            if not isinstance(is_error, bool) or not isinstance(text, str):
                raise RuntimeError(f"execution_result:role_result_invalid:{identity}")
            parsed_fields[field] = ToolExecutionResult(is_error=is_error, text=text)
        results[identity] = parsed_fields
    return results


def serialized_execution_results(
    results: Mapping[str, Mapping[str, ToolExecutionResult]],
) -> dict[str, object]:
    """Serialize host result values in the same shape accepted on re-entry."""
    return {
        identity: {
            field: {
                "is_error": result.is_error,
                "text": result.text,
            }
            for field, result in sorted(fields.items())
        }
        for identity, fields in sorted(results.items())
    }


def completed_execution_wave_ids(
    waves: tuple[tuple[SubagentWaveSlot, ...], ...],
    results: Mapping[str, Mapping[str, ToolExecutionResult]],
) -> list[str]:
    """Return only graph waves whose actual launch and completion results pass."""
    completed: list[str] = []
    for index, wave in enumerate(waves, start=1):
        if not wave:
            continue
        if not all(
            (result := results.get(slot.executable_identity)) is not None
            and (spawn := result.get("spawn_result")) is not None
            and not spawn.is_error
            and bool(spawn.text.strip())
            and (completion := result.get("completion_result")) is not None
            and not completion.is_error
            and bool(completion.text.strip())
            for slot in wave
        ):
            break
        completed.append(f"WAVE-{index}")
    return completed


def read_selected_skill_documents(
    skills: Sequence[str],
    source_root: Path,
    *,
    existing_graph: Mapping[str, object] | None = None,
) -> tuple[tuple[str, str, str], ...]:
    """Read selected skills and hard prerequisites from canonical files to EOF."""
    selected = tuple(skill.removeprefix("$") for skill in skills)
    if not selected:
        return ()
    rules = load_skill_route_rules(source_root)
    order = derive_skill_invocation_order(selected, rules)
    rules_by_skill = {rule.skill: rule for rule in rules}
    previous_reads: dict[str, Mapping[str, object]] = {}
    if existing_graph is not None:
        raw_reads = existing_graph.get("skill_document_reads")
        if not is_string_object_mapping(raw_reads):
            raise RuntimeError("skill_readback:existing_state_invalid")
        for skill_id, raw_read in raw_reads.items():
            if not is_string_object_mapping(raw_read):
                raise RuntimeError(f"skill_readback:entry_invalid:{skill_id}")
            previous_reads[skill_id] = raw_read
    documents: list[tuple[str, str, str]] = []
    root = source_root.resolve()
    for skill in order:
        relative = Path(rules_by_skill[skill].canonical_doc)
        if relative.is_absolute() or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            raise SkillDocumentError("canonical_path_invalid", relative.as_posix())
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise SkillDocumentError(
                "canonical_path_outside_source", str(path)
            ) from exc
        relative_name = relative.as_posix()
        current_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        previous = previous_reads.get(skill)
        previous_body = previous.get("content") if previous is not None else None
        if (
            previous is not None
            and previous.get("canonical_doc") == relative_name
            and previous.get("content_sha256") == current_digest
            and previous.get("read_to_eof") is True
            and isinstance(previous_body, str)
            and hashlib.sha256(previous_body.encode("utf-8")).hexdigest()
            == current_digest
        ):
            body = previous_body
        else:
            body = SkillDocumentReader(path).read_document()
            if hashlib.sha256(body.encode("utf-8")).hexdigest() != current_digest:
                raise RuntimeError(f"skill_readback:source_changed_during_read:{skill}")
        documents.append((skill, relative_name, body))
    return tuple(documents)


def serialized_skill_document_reads(
    documents: Sequence[tuple[str, str, str]],
) -> dict[str, object]:
    """Persist full bodies and EOF identity as the graph's reader-node state."""
    return {
        skill: {
            "canonical_doc": path,
            "content_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "read_to_eof": True,
            "content": body,
        }
        for skill, path, body in documents
    }


def skill_document_context(
    documents: tuple[tuple[str, str, str], ...],
) -> str:
    """Render the already-read canonical bodies for one host/agent context."""
    return "\n\n".join(
        f"===== Canonical Skill: ${skill} ({path}; read through file EOF) =====\n{body}"
        for skill, path, body in documents
    )


def role_document_packet_context(
    *,
    config: TeamConfig,
    role: Role,
    report_dir: Path,
    workspace_root: Path,
    agentcanon_source_root: Path,
    prepared: PreparedRunBundle,
    skill_documents: tuple[tuple[str, str, str], ...],
    existing_run: bool,
) -> str:
    """Render this role's selected document packet without container paths."""
    packet = resolve_role_document_packet(
        config,
        role,
        report_dir,
        workspace_root,
        prepared.active_design_packet,
        agentcanon_source_root,
    )
    prepared_files = dict(prepared.files)
    report_root = report_dir.resolve(strict=False)
    source_root = agentcanon_source_root.resolve()
    selected_skill_paths = {
        (source_root / Path(path)).resolve() for _, path, _ in skill_documents
    }
    entries: list[str] = []
    for entry in role_specific_document_entries(packet):
        path = entry.path.resolve()
        if path.is_relative_to(report_root):
            relative_path = path.relative_to(report_root).as_posix()
            if existing_run:
                content = (
                    path.read_text(encoding="utf-8")
                    if path.is_file()
                    else "(not present in this run bundle; no file content supplied)"
                )
            else:
                content_bytes = prepared_files.get(relative_path)
                content = (
                    content_bytes.decode("utf-8")
                    if content_bytes is not None
                    else "(not emitted by this prepared run bundle; no file content supplied)"
                )
        elif path.is_relative_to(source_root):
            if path in selected_skill_paths:
                continue
            relative_path = path.relative_to(source_root).as_posix()
            reader = SkillDocumentReader(path)
            if entry.sections:
                content = "\n\n".join(
                    "".join(
                        chunk.text for chunk in reader.read_section(section.heading)
                    )
                    for section in entry.sections
                )
            else:
                content = reader.read_document()
        else:
            raise RuntimeError(f"execution_graph:role_document_root_invalid:{role.id}")
        entries.append(
            f"===== Role document: {role.id}/{relative_path} =====\n{content}"
        )
    if not entries:
        return f"===== Role document packet: {role.id} (no role-specific entries) ====="
    return "\n\n".join(
        (
            f"===== Role document packet: {role.id} =====\n"
            f"must_cite_before_edit: {str(packet.must_cite_before_edit).lower()}\n"
            f"notes: {packet.notes or '(none)'}",
            *entries,
        )
    )


def materialize_execution_tool_calls(
    *,
    transition: ExecutionGraphTransition,
    roles: tuple[Role, ...],
    task: str,
    run_id: str,
    workspace_root: Path,
    workflow_family_id: str | None,
    catalog: TaskCatalog,
    skill_documents: tuple[tuple[str, str, str], ...],
    completed_results: tuple[tuple[str, str], ...],
    writer_targets: Mapping[str, WriterTarget | Mapping[str, object] | None],
    math_intent_route: str | None,
    math_intent_packet: MathematicalIntentPacket | None,
    role_document_contexts: Mapping[str, str] | None = None,
) -> tuple[dict[str, object], ...]:
    """Materialize actual host spawn ToolCalls for the graph's ready wave."""
    if not transition.ready_slots:
        return ()
    from tools.agent.orchestration.agent_team import validate_writer_handoff_waves
    from tools.runtime.manifest.manifest_rendering import role_prompt_contract

    validate_writer_handoff_waves((transition.ready_slots,), writer_targets)
    roles_by_id = {role.id: role for role in roles}
    family = (
        resolve_workflow_family(catalog, workflow_family_id)
        if workflow_family_id is not None
        else None
    )
    identity = resolve_checkout_identity(workspace_root).as_dict()
    target_root = os.environ.get("AGENT_CANON_TARGET_ROOT")
    host_root = os.environ.get("AGENT_CANON_TARGET_HOST_ROOT")
    if (
        target_root
        and host_root
        and workspace_root == Path(target_root).resolve(strict=False)
    ):
        host_root = str(Path(host_root).resolve(strict=False))
        identity["cwd"] = host_root
        identity["git_root"] = host_root
    skill_context = skill_document_context(skill_documents)
    host_identity_context = (
        "Host checkout_identity for native filesystem access:\n"
        + json.dumps(identity, ensure_ascii=False, sort_keys=True)
        + "\nUse the host paths in this identity; container-only paths are unavailable."
    )
    role_document_contexts = role_document_contexts or {}
    result_context = "\n\n".join(
        f"===== Completed role instance {role_identity} =====\n{output}"
        for role_identity, output in completed_results
    )
    calls: list[dict[str, object]] = []
    for slot in transition.ready_slots:
        role = roles_by_id.get(slot.role_id)
        if role is None:
            raise RuntimeError(f"execution_graph:role_missing:{slot.role_id}")
        target = writer_targets.get(
            slot.executable_identity,
            writer_targets.get(slot.role_id, slot.writer_target),
        )
        prompt = (
            f"Run {run_id}; task: {task}\n"
            f"Selected role: {slot.role_id}; agent type: {slot.agent_type}.\n"
            f"{role_prompt_contract(role, family)}\n\n"
            f"{host_identity_context}\n\n"
            f"{role_document_contexts.get(slot.role_id, '')}\n\n"
            f"{skill_context}\n\n"
            f"Prior completed graph-node results:\n{result_context or '(none)'}"
        )
        calls.append(
            materialize_subagent_spawn_tool_call(
                role=slot.role_id,
                agent_type=slot.agent_type,
                input=prompt,
                checkout_identity=identity,
                workspace_write_capable=slot.write_capable,
                writer_target=target,
                math_intent_route=math_intent_route,
                math_intent_packet=math_intent_packet,
            )
        )
    return tuple(calls)


def codex_agents_for_role(config: TeamConfig, role_id: str) -> tuple[str, ...]:
    """Return Codex subagent candidates for one permanent role."""
    for role in config.always_on_roles + config.specialist_roles:
        if role.id == role_id:
            return role.codex_agents
    return ()


def document_packet_output(
    config: TeamConfig,
    role_id: str,
    report_dir: Path,
    workspace_root: Path,
    active_design_packet: ActiveDesignPacketConfig | None = None,
    agentcanon_source_root: Path | None = None,
) -> str:
    """Render one role's explicit document packet as a CSV-like path list."""
    role = next(
        role
        for role in config.always_on_roles + config.specialist_roles
        if role.id == role_id
    )
    packet = resolve_role_document_packet(
        config,
        role,
        report_dir,
        workspace_root,
        active_design_packet,
        agentcanon_source_root,
    )
    return ",".join(str(entry.path) for entry in packet.read_before_work)


def cross_cutting_document_packet_output(
    workspace_root: Path,
    agentcanon_source_root: Path | None = None,
) -> str:
    """Render the common cross-cutting document packet."""
    return ",".join(
        str(entry.path)
        for entry in resolve_cross_cutting_document_packet(
            workspace_root,
            agentcanon_source_root,
        )
    )


def build_parser(
    enable_names: tuple[str, ...], task_choices: tuple[str, ...]
) -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Create a standard external-runtime reports/agents/<run-id> bundle "
            "for one agent-team run."
        )
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Short task description for the run.",
    )
    parser.add_argument(
        "--owner",
        required=True,
        help="Human or agent responsible for the run.",
    )
    parser.add_argument(
        "--task-id",
        choices=task_choices,
        help=(
            "Optional task catalog id. Expands default specialists and review packs "
            "for that task."
        ),
    )
    parser.add_argument(
        "--issue-worker-candidate",
        metavar="JSON",
        help=(
            "Explicit JSON IssueWorker candidate that activates the T15 publisher "
            "initial wave. Other workflows ignore this input."
        ),
    )
    parser.add_argument(
        "--run-id",
        help=(
            "Optional explicit run id. Defaults to a timestamped slug. Reuse this "
            "same id when returning actual host ToolCall results to advance the graph."
        ),
    )
    parser.add_argument(
        "--execution-results",
        metavar="JSON",
        help=(
            "Actual host ToolCall results keyed by existing role-instance identity. "
            "Each entry contains spawn_result and, once the child returns, "
            "completion_result; this advances the same run without a new bundle."
        ),
    )
    parser.add_argument(
        "--active-design-packet",
        metavar="JSON",
        help=(
            f"Atomic {ACTIVE_DESIGN_PACKET_SCHEMA} JSON object. All schema, path, "
            "document_flow_required, clause_registry, and graph-entry fields are required."
        ),
    )
    parser.add_argument(
        "--math-intent-packet",
        metavar="JSON",
        help=(
            f"Atomic {MATHEMATICAL_INTENT_PACKET_SCHEMA} JSON object. Required when "
            "the selected task declares a mathematical intent route."
        ),
    )
    parser.add_argument(
        "--writer-targets",
        metavar="JSON",
        help=(
            "JSON object mapping role/instance identities to repository-topic-clone "
            "writer_target values. Required before spawning write-capable waves."
        ),
    )
    parser.add_argument(
        "--enable",
        action="append",
        choices=enable_names,
        default=[],
        help="Enable a specialist role or review pack. Repeat the flag to enable multiple entries.",
    )
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        help=(
            "Optional changed path hint. Repeat to populate explicit language-review "
            "candidates."
        ),
    )
    parser.add_argument(
        "--select-agent-type",
        action="append",
        default=[],
        metavar="ROLE_ID=AGENT_TYPE:EVIDENCE",
        help=(
            "Optional native pre-route role-to-agent selection with evidence; "
            "preserved in the selected route readback."
        ),
    )
    parser.add_argument(
        "--no-language-review-candidates",
        action="store_true",
        help=(
            "Disable language-review candidate discovery from changed paths or git status."
        ),
    )
    parser.add_argument(
        "--full-team",
        action="store_true",
        help="Enable every specialist role for this run.",
    )
    parser.add_argument(
        "--no-default-review-packs",
        action="store_true",
        help=(
            "When --task-id is set, skip review packs whose default_for_tasks "
            "contains that task."
        ),
    )
    parser.add_argument(
        "--report-root",
        help=(
            "Optional external directory that will contain per-run report folders. "
            "Defaults below --runtime-root."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        help=(
            "Explicit external runtime root for reports, active-run state, "
            "ledgers, and receipts. Defaults to AGENT_CANON_RUNTIME_ROOT."
        ),
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root used to resolve run-local reports and current-checkout path authority.",
    )
    return parser


def parse_issue_worker_candidate(value: str | None) -> Mapping[str, object] | None:
    """Parse one explicit IssueWorker candidate without inferring candidates."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("issue_worker_candidate:invalid_json") from exc
    if not is_string_object_dict(parsed) or not parsed:
        raise RuntimeError("issue_worker_candidate:must_be_nonempty_object")
    return parsed


def parse_math_intent_packet_input(value: str | None) -> Mapping[str, object] | None:
    """Parse one explicit math packet without inferring mathematical content."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError("mathematical_intent_packet:invalid_json") from exc
    if not is_string_object_dict(parsed) or not parsed:
        raise RuntimeError("mathematical_intent_packet:must_be_nonempty_object")
    return parsed


def resolve_bootstrap_context(
    args: argparse.Namespace,
    config: TeamConfig,
    catalog: TaskCatalog,
    workspace_root: Path,
    repository_roots: RepositoryRoots | None = None,
    issue_worker_candidate: Mapping[str, object] | None = None,
) -> BootstrapRunContext:
    """Resolve workflow family, specialists, and report paths for one run."""
    created_at = datetime.now(UTC).replace(microsecond=0)
    created_at_iso = created_at.isoformat().replace("+00:00", "Z")
    # The parent capability authorizes the eventual write; it does not replace
    # the caller's logical workspace/report-root selection.
    report_root = (
        repository_roots.report_root
        if repository_roots is not None
        else resolve_report_root(
            args.report_root,
            runtime_root=args.runtime_root,
        )
    )
    run_id = args.run_id or make_run_id(args.task, created_at)
    report_dir = report_root / run_id
    manual_specialists = expand_enabled_specialists(config, catalog, tuple(args.enable))
    enabled_specialists = list(manual_specialists)
    task_default_specialists: tuple[str, ...] = ()
    default_review_pack_ids: tuple[str, ...] = ()
    workflow_family_id: str | None = None
    workflow_family_name: str | None = None
    workflow_active_spawn_budget: int | None = None
    workflow_max_write_subagents: int | None = None
    adversarial_required = False
    if args.task_id is not None:
        task_spec = resolve_task_spec(catalog, args.task_id)
        workflow_family_id = str(task_spec["family"])
        workflow_family = resolve_workflow_family(catalog, workflow_family_id)
        workflow_family_name = str(workflow_family["name"])
        workflow_active_spawn_budget, workflow_max_write_subagents = (
            workflow_spawn_budget(
                catalog,
                workflow_family_id,
            )
        )
        # The comprehensive family is the catalog-owned cross-owner route.
        # Bounded routes enable Terra explicitly through --enable terra.
        adversarial_required = workflow_family_id == "comprehensive_development"
        task_default_specialists = default_specialists_for_task(
            config=config,
            catalog=catalog,
            task_id=args.task_id,
            include_default_review_packs=not args.no_default_review_packs,
        )
        if not args.no_default_review_packs:
            default_review_pack_ids = default_review_pack_ids_for_task(
                catalog,
                args.task_id,
            )
        # Task-catalog specialists and default review packs remain candidates;
        # explicit enablement or an owner-critical route activates them.
    if workflow_child_handoff_required(
        config,
        catalog,
        workflow_family_id,
        issue_worker_candidate,
    ):
        write_roles = [
            role
            for role in (*config.always_on_roles, *config.specialist_roles)
            if role.write_policy.mode not in {"read_only", "artifacts_only"}
            and role.codex_agents
        ]
        if not write_roles:
            raise RuntimeError(
                "WRITE_SUBAGENT_AUTHORIZATION=required;"
                "PARENT_BLOCKED_ROUTE=typed_blocked_retry_or_user_report"
            )
    selected_route_skills = suggested_skills(
        args.task_id,
        workflow_family_id,
        args.task,
        source_root=(
            repository_roots.agentcanon_source_root if repository_roots else None
        ),
        issue_worker_candidate=issue_worker_candidate,
    )
    math_route = mathematical_intent_route_for_task(
        catalog,
        args.task_id,
        selected_route_skills,
    )
    math_route = math_intent_route_id_from_context(
        selected_route_skills,
        packet_present=bool(args.math_intent_packet),
        explicit_route_id=math_route,
    )
    if math_route is not None and workflow_family_id is not None:
        workflow_active_spawn_budget, workflow_max_write_subagents = (
            workflow_spawn_budget(
                catalog,
                workflow_family_id,
                include_math_intent=True,
            )
        )
    if math_route is not None and args.math_intent_packet:
        reviewer = str(
            (mathematical_intent_route_config(catalog, math_route) or {}).get(
                "reviewer", ""
            )
        ).strip()
        if reviewer and reviewer not in enabled_specialists:
            enabled_specialists.append(reviewer)
    language_candidates: tuple[str, ...] = ()
    if not args.no_language_review_candidates:
        language_candidates = language_review_candidates(
            workspace_root=workspace_root,
            changed_paths=tuple(args.changed_path),
        )
    return BootstrapRunContext(
        created_at_iso=created_at_iso,
        report_root=report_root,
        run_id=run_id,
        report_dir=report_dir,
        manual_specialists=tuple(manual_specialists),
        enabled_specialists=tuple(enabled_specialists),
        task_default_specialists=task_default_specialists,
        language_review_candidates=language_candidates,
        default_review_pack_ids=default_review_pack_ids,
        workflow_family_id=workflow_family_id,
        workflow_family_name=workflow_family_name,
        workflow_active_spawn_budget=workflow_active_spawn_budget,
        workflow_max_write_subagents=workflow_max_write_subagents,
        adversarial_required=adversarial_required,
        math_intent_route=math_route,
        issue_worker_candidate=issue_worker_candidate,
        repository_roots=repository_roots,
    )


def selected_review_roles(roles: tuple[Role, ...]) -> tuple[str, ...]:
    """Return role ids that should appear in the review declaration."""
    fixed_review_roles = {
        "reviewer",
        "verifier",
        "auditor",
        "docs_workflow_steward",
    }
    return tuple(
        role.id
        for role in roles
        if role.id.endswith("_reviewer")
        or role.id in fixed_review_roles
        or "adversarial_contradiction_validation" in role.owns
    )


def emit_bootstrap_output(
    *,
    args: argparse.Namespace,
    config: TeamConfig,
    catalog: TaskCatalog,
    context: BootstrapRunContext,
    workspace_root: Path,
    runtime: BootstrapRuntime,
) -> None:
    """Print the machine-readable bootstrap summary."""
    repository_roots = context.repository_roots
    if repository_roots is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    source_root = repository_roots.agentcanon_source_root
    selected_skills = runtime.selected_skills
    active_skills = runtime.active_skills
    deferred_skills = runtime.deferred_skills
    review_roles = selected_review_roles(runtime.roles)
    public_layout = getattr(repository_roots, "layout", None)
    if public_layout is None:
        raise RuntimeError("runtime_roots_invalid:layout_missing")
    print(f"RUN_ID={context.run_id}")
    print(f"REPORT_DIR={context.report_dir}")
    print(f"TASK_AUTHORITY={context.report_dir / 'task_authority.yaml'}")
    print(f"WORKSPACE_ROOT={workspace_root}")
    for line in capacity_start_output_lines(catalog, workspace_root, context.run_id):
        print(line)
    print(f"REQUEST_CONTRACT={context.report_dir / 'user_request_contract.md'}")
    print("REQUEST_CONTRACT_REQUIRED=yes")
    print(f"RUNTIME_MAX_THREADS={codex_runtime_max_threads(workspace_root)}")
    print(f"RUNTIME_MAX_DEPTH={codex_runtime_max_depth(workspace_root)}")
    print(f"SUGGESTED_SKILLS={','.join(selected_skills)}")
    print(f"ACTIVE_SKILLS={','.join(active_skills)}")
    print(f"DEFERRED_SKILLS={','.join(deferred_skills) or '-'}")
    print(
        "ACTIVE_SKILL_DOCUMENTS_JSON="
        + json.dumps(
            [
                {"skill": skill, "canonical_doc": path, "content": content}
                for skill, path, content in runtime.skill_documents
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    if context.math_intent_route is None:
        print("MATH_INTENT_ROUTE_STATUS=not_applicable")
        print("MATH_INTENT_PACKET=absent")
    else:
        print("MATH_INTENT_ROUTE_STATUS=active")
        print(f"MATH_INTENT_PACKET_SCHEMA={MATHEMATICAL_INTENT_PACKET_SCHEMA}")
        math_route_config = mathematical_intent_route_config(
            catalog, context.math_intent_route
        )
        if math_route_config is None:
            raise RuntimeError("mathematical_intent_route:catalog_record_missing")
        print(f"MATH_INTENT_ROUTE_ID={context.math_intent_route}")
        print(f"MATH_INTENT_REVIEWER={math_route_config.get('reviewer', 'unknown')}")
        print("MATH_INTENT_PACKET=present")
    print(
        "START_DECLARATION="
        f"workflow={context.workflow_family_name or 'Unspecified'}, "
        f"skills={','.join(active_skills) or '-'}, "
        f"review={','.join(review_roles) or '-'}"
    )
    if args.task_id is not None:
        print(f"TASK_ID={args.task_id}")
        print("TASK_ID_ROUTE_STATUS=explicit")
        print(f"WORKFLOW_FAMILY={context.workflow_family_id}")
        print(f"WORKFLOW_FAMILY_NAME={context.workflow_family_name}")
        print(
            "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet"
        )
        print(f"WORKFLOW_ACTIVE_SPAWN_BUDGET={context.workflow_active_spawn_budget}")
        print(f"WORKFLOW_MAX_WRITE_SUBAGENTS={context.workflow_max_write_subagents}")
        print(
            "ADVERSARIAL_REQUIRED=" + ("yes" if context.adversarial_required else "no")
        )
        print("INITIAL_THREE_AGENT_INTAKE_IS_TOTAL_CAP=no")
        print("DYNAMIC_SUBAGENT_EXPANSION=graph_controlled")
        if context.workflow_family_id == "issue_worker_publication":
            print(
                "ISSUE_WORKER_CANDIDATE_STATUS="
                + ("explicit" if context.issue_worker_candidate else "absent")
            )
            if runtime.issue_worker_dispatch is not None:
                dispatch_status = runtime.issue_worker_dispatch.get("status", "unknown")
                print(f"ISSUE_WORKER_DISPATCH_STATUS={dispatch_status}")
            print(
                "ISSUE_WORKER_DISPATCH_ROUTE="
                "tools/agent/orchestration/agent_team.py#dispatch_issue_worker"
            )
            print("ISSUE_WORKER_EXECUTION_ROLE=publisher")
            print(
                "ISSUE_WORKER_TOOL_CALL_ROUTE="
                "tools/agent/orchestration/tool_calls.py#materialize_issue_worker_tool_call"
            )
            print("ISSUE_WORKER_READBACK=URL,number,body,state")
        print(
            "SUBAGENT_AGENT_TYPE_SELECTIONS="
            f"{format_agent_type_selections(runtime.agent_type_selections)}"
        )
        transition = runtime.execution_transition
        if transition is None:
            raise RuntimeError("execution_graph:transition_missing")
        print(f"EXECUTION_GRAPH_STATUS={transition.status}")
        print(
            "EXECUTION_GRAPH_WAVE_INDEX="
            + (
                str(transition.wave_index + 1)
                if transition.wave_index is not None
                else "none"
            )
        )
        print(
            "EXECUTION_GRAPH_READY_TOOL_CALLS_JSON="
            + json.dumps(
                list(runtime.execution_tool_calls),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        print(
            "EXECUTION_GRAPH_SPAWN_RESULTS_JSON="
            + json.dumps(
                {
                    identity: {
                        "spawn_result": {
                            "isError": False,
                            "content": [{"type": "text", "text": agent_id}],
                        }
                    }
                    for identity, agent_id in runtime.execution_spawn_results
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        print(
            "EXECUTION_GRAPH_WAITING_ROLE_INSTANCES="
            + ",".join(transition.waiting_identities or ())
        )
        print(
            "EXECUTION_GRAPH_FAILED_ROLE_INSTANCES="
            + ",".join(transition.failed_identities or ())
        )
        print(
            "EXECUTION_GRAPH_COMPLETED_ROLE_INSTANCES="
            + ",".join(identity for identity, _ in transition.completed_results)
        )
        print(
            "EXECUTION_GRAPH_RESULT_INPUT=--run-id <same-run-id> --execution-results <actual-host-tool-results-json>"
        )
        print(f"TASK_DEFAULT_SPECIALISTS={','.join(context.task_default_specialists)}")
        print(f"PLANNED_ACTIVE_ROLE_COUNT={len(runtime.roles)}")
    else:
        print("TASK_ID_ROUTE_STATUS=missing")
        print("TASK_ID_ROUTE_REQUIRED_FOR_MULTI_AGENT=yes")
        print("SUBAGENT_FANOUT_STATUS=not_selected_without_task_id")
    for line in pre_handoff_scope_policy_output_lines():
        print(line)
    for line in checkout_identity_policy_output_lines():
        print(line)
    for line in coordination_capability_policy_output_lines():
        print(line)
    for line in pre_handoff_gate_status_output_lines():
        print(line)
    for line in user_facing_language_policy_output_lines():
        print(line)
    for line in contract_complete_implementation_policy_output_lines(
        args.task,
        child_handoff_required=workflow_child_handoff_required(
            config,
            catalog,
            context.workflow_family_id,
            context.issue_worker_candidate,
        ),
    ):
        print(line)
    for line in repo_tool_routing_policy_output_lines(
        selected_skills,
        source_root=source_root,
    ):
        print(line)
    for line in default_quality_check_policy_output_lines(
        runtime.roles,
        manual_specialists=context.manual_specialists,
        task_default_specialists=context.task_default_specialists,
        language_review_candidates=context.language_review_candidates,
        default_review_packs_enabled=False,
        default_review_pack_ids=context.default_review_pack_ids,
        layout=public_layout,
    ):
        print(line)
    if not args.no_language_review_candidates:
        print(
            f"LANGUAGE_REVIEW_CANDIDATES={','.join(context.language_review_candidates)}"
        )
    print(
        "IMPLEMENTATION_CODEX_AGENTS="
        f"{','.join(codex_agents_for_role(config, 'implementer'))}"
    )
    print(
        f"ROLE_MODEL_MATRIX={';'.join(codex_agent_model_matrix_for_roles(runtime.roles))}"
    )
    print("IMPLEMENTATION_SURFACE_ROUTE_STATUS=pending")
    print(
        "IMPLEMENTATION_SURFACE_ROUTE_COMMAND="
        + public_command_for_layout(
            "python3 tools/analysis/search/search.py "
            "--query-file <request-or-design-question.txt> "
            "--providers semantic "
            "--format json",
            public_layout,
        )
    )
    print("TOOL_REUSE_LEDGER_STATUS=required_before_custom_implementation")
    print("PRE_EDIT_REJECTION_PREDICTION_STATUS=optional_diagnostic")
    print(
        "PRE_EDIT_REJECTION_COMMAND="
        + public_command_for_layout(
            "python3 tools/validation/semantic/tools/tool_rejection_preflight.py --root . <planned-edit-paths>",
            public_layout,
        )
    )
    print("AGENT_REPORT_COLLECTION_STATUS=available")
    print(
        "AGENT_REPORT_COLLECTION_STATUS_COMMAND="
        + public_command_for_layout(
            "python3 tools/runtime/archive/runtime_log_archive_git.py status",
            public_layout,
        )
    )
    print(
        "AGENT_REPORT_ARCHIVE_RUN_COMMAND="
        + public_command_for_layout(
            f"python3 tools/runtime/archive/runtime_log_archive_git.py archive-agent-report --report-dir {context.report_dir}",
            public_layout,
        )
    )
    print(
        "AGENT_REPORT_COLLECTION_SYNC_COMMAND="
        + public_command_for_layout(
            "python3 tools/runtime/archive/runtime_log_archive_git.py sync",
            public_layout,
        )
    )
    print(
        "CROSS_CUTTING_DOCUMENT_PACKET="
        f"{cross_cutting_document_packet_output(workspace_root, source_root)}"
    )
    print(
        "DESIGN_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'designer', context.report_dir, workspace_root, runtime.active_design_packet, source_root)}"
    )
    print(
        "IMPLEMENTATION_DOCUMENT_PACKET="
        f"{document_packet_output(config, 'implementer', context.report_dir, workspace_root, runtime.active_design_packet, source_root)}"
    )
    print(f"ACTIVE_ROLES={','.join(role.id for role in runtime.roles)}")
    print(f"CREATED_FILES={','.join(runtime.created_files)}")
    print(f"AGENT_CANON_ACTIVE_RUN_POINTER={runtime.active_pointer}")


def record_bootstrap_monitoring(
    context: BootstrapRunContext,
    roles: tuple[Role, ...],
    selected_skills: tuple[str, ...],
    review_roles: tuple[str, ...],
    task_text: str,
    source_root: Path | None = None,
) -> None:
    """Record bootstrap monitoring evidence."""
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    selected_source_root = source_root
    append_monitoring(
        context.report_dir,
        signals=[
            (
                f"workflow={context.workflow_family_name or 'Unspecified'}, "
                f"skills={','.join(current_stage_skills(selected_skills, task_text, source_root=selected_source_root)) or '-'}, "
                f"review={','.join(review_roles) or '-'}"
            ),
            f"stage owner routing active_roles={','.join(role.id for role in roles)}",
            "web_research_not_required: bootstrap does not decide external research",
        ],
        interventions=[
            f"created run bundle and workflow_monitoring.md at {context.report_dir}"
        ],
        behavior_events=["token_efficiency_not_required reason=bootstrap_default"],
    )


def _read_optional_bytes(path: Path) -> bytes | None:
    """Read one prior file exactly, preserving absent state as ``None``."""
    return path.read_bytes() if path.is_file() else None


def _restore_runtime_file(
    boundary: RuntimeArtifactBoundary,
    path: Path,
    prior: bytes | None,
    purpose: str,
) -> None:
    """Restore one captured runtime file without touching source state."""
    del purpose
    if prior is not None:
        boundary.atomic_write_bytes(path, prior)
        return
    if not path.exists():
        return
    path.unlink()


def validate_execution_run_readback(
    report_dir: Path, report_root: Path, run_id: str, task: str, owner: str
) -> Mapping[str, object]:
    """Bind result re-entry to the already-published run, without a new bundle."""
    pointer = report_root / ".active_run"
    manifest_path = report_dir / "team_manifest.yaml"
    if not pointer.is_file() or not manifest_path.is_file():
        raise RuntimeError("execution_result:existing_run_artifacts_missing")
    if (
        Path(pointer.read_text(encoding="utf-8").strip()).resolve()
        != report_dir.resolve()
    ):
        raise RuntimeError("execution_result:active_run_mismatch")
    try:
        raw: object = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError("execution_result:run_manifest_invalid") from exc
    if not is_string_object_mapping(raw) or not is_string_object_mapping(
        raw.get("run")
    ):
        raise RuntimeError("execution_result:run_manifest_invalid")
    run = raw["run"]
    if (
        run.get("id") != run_id
        or run.get("task") != task
        or run.get("owner") != owner
        or Path(str(run.get("report_dir", ""))).resolve() != report_dir.resolve()
    ):
        raise RuntimeError("execution_result:run_identity_mismatch")
    return run


def persist_execution_graph_readback(
    source_root: Path,
    runtime_root: Path | None,
    report_dir: Path,
    waves: tuple[tuple[SubagentWaveSlot, ...], ...],
    results: Mapping[str, Mapping[str, ToolExecutionResult]],
    transition: ExecutionGraphTransition,
    skill_documents: Sequence[tuple[str, str, str]],
    issue_worker_dispatch: Mapping[str, object] | None,
) -> None:
    """Persist actual result nodes in the existing run manifest for closeout."""
    manifest_path = report_dir / "team_manifest.yaml"
    try:
        payload: object = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError("execution_result:run_manifest_invalid") from exc
    if not is_string_object_mapping(payload) or not is_string_object_mapping(
        payload.get("run")
    ):
        raise RuntimeError("execution_result:run_manifest_invalid")
    run = dict(payload["run"])
    raw_graph = run.get("execution_graph")
    if not is_string_object_mapping(raw_graph):
        raise RuntimeError("execution_result:execution_graph_missing")
    graph = dict(raw_graph)
    graph["result_readback"] = {
        "status": transition.status,
        "completed_wave_ids": completed_execution_wave_ids(waves, results),
        "role_results": serialized_execution_results(results),
    }
    graph["skill_document_reads"] = serialized_skill_document_reads(skill_documents)
    run["execution_graph"] = graph
    if issue_worker_dispatch is not None:
        run["issue_worker_dispatch"] = {
            key: value
            for key, value in issue_worker_dispatch.items()
            if key not in {"tool_call", "spawn_tool_call"} or value is None
        }
    updated = dict(payload)
    updated["run"] = run
    try:
        boundary = runtime_artifact_boundary(
            source_root,
            runtime_root,
            create=True,
        )
        resolved_manifest = boundary.resolve(manifest_path)
        boundary.atomic_write_text(
            resolved_manifest,
            yaml.safe_dump(
                updated,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            ),
        )
        readback: object = yaml.safe_load(resolved_manifest.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, RuntimeError) as exc:
        raise RuntimeError("execution_result:run_manifest_write_failed") from exc
    if (
        not is_string_object_mapping(readback)
        or not is_string_object_mapping(readback.get("run"))
        or not is_string_object_mapping(readback["run"].get("execution_graph"))
        or readback["run"]["execution_graph"].get("result_readback")
        != graph["result_readback"]
    ):
        raise RuntimeError("execution_result:run_manifest_readback_mismatch")


def validate_execution_graph_readback(
    run: Mapping[str, object],
    *,
    workflow_family_id: str | None,
    task_id: str | None,
    math_intent_route: str | None,
    roles: tuple[Role, ...],
    issue_worker_dispatch: Mapping[str, object] | None,
    selected_skills: tuple[str, ...],
    agent_type_selections: tuple[AgentTypeSelection, ...],
    waves: tuple[tuple[SubagentWaveSlot, ...], ...],
    writer_targets: Mapping[str, WriterTarget | Mapping[str, object] | None],
) -> None:
    """Reject resume inputs that would change the already-published graph."""
    raw_graph = run.get("execution_graph")
    if not is_string_object_mapping(raw_graph):
        raise RuntimeError("execution_result:execution_graph_missing")
    graph = raw_graph
    initial = waves[0] if waves else ()
    expected_role_ids = [slot.role_id for slot in initial]
    expected_agent_types = [slot.agent_type for slot in initial]
    if (
        graph.get("initial_wave_role_ids") != expected_role_ids
        or graph.get("initial_wave_role_instances")
        != [slot.executable_identity for slot in initial]
        or graph.get("initial_wave_agent_types") != expected_agent_types
    ):
        raise RuntimeError("execution_result:initial_graph_mismatch")
    if graph.get("task_id") != (task_id or "none"):
        raise RuntimeError("execution_result:task_id_mismatch")
    if graph.get("math_intent_route_id") != (math_intent_route or "none"):
        raise RuntimeError("execution_result:math_route_mismatch")
    if graph.get("selected_role_ids") != [role.id for role in roles]:
        raise RuntimeError("execution_result:selected_roles_mismatch")
    observed_issue = run.get("issue_worker_dispatch")
    observed_handoff = (
        observed_issue.get("handoff") if isinstance(observed_issue, Mapping) else None
    )
    expected_handoff = (
        issue_worker_dispatch.get("handoff")
        if issue_worker_dispatch is not None
        else None
    )
    if observed_handoff != expected_handoff:
        raise RuntimeError("execution_result:issue_worker_candidate_mismatch")
    raw_later_waves = graph.get("later_stage_waves")
    expected_later = [
        {
            "wave_id": f"WAVE-{index}",
            "depends_on": f"WAVE-{index - 1}",
            "agent_types": [slot.agent_type for slot in wave],
            "role_instances": [
                f"{slot.executable_identity}:team_manifest.yaml#roles.{slot.role_id}"
                for slot in wave
            ],
        }
        for index, wave in enumerate(waves[1:], start=2)
        if wave
    ]
    if not isinstance(raw_later_waves, list):
        raise RuntimeError("execution_result:later_graph_missing")
    observed_later = [
        {
            "wave_id": wave.get("wave_id"),
            "depends_on": wave.get("depends_on"),
            "agent_types": wave.get("agent_types"),
            "role_instances": wave.get("role_instances"),
        }
        for wave in raw_later_waves
        if isinstance(wave, Mapping) and wave.get("wave_id") != "none"
    ]
    if observed_later != expected_later:
        raise RuntimeError("execution_result:later_graph_mismatch")
    raw_family = run.get("workflow_family")
    observed_family = raw_family.get("id") if isinstance(raw_family, Mapping) else None
    if observed_family != workflow_family_id:
        raise RuntimeError("execution_result:workflow_family_mismatch")
    raw_routing = run.get("repo_tool_routing_policy")
    if not is_string_object_mapping(raw_routing):
        raise RuntimeError("execution_result:skill_route_missing")
    expected_skills = [f"${skill.removeprefix('$')}" for skill in selected_skills]
    if raw_routing.get("selected_skills") != expected_skills:
        raise RuntimeError("execution_result:selected_skills_mismatch")
    raw_selections = graph.get("agent_type_selections")
    expected_selections = [
        {
            "role_id": selection.role_id,
            "agent_type": selection.agent_type,
            "evidence": selection.evidence,
        }
        for selection in agent_type_selections
    ]
    if raw_selections != expected_selections:
        raise RuntimeError("execution_result:agent_type_selections_mismatch")
    raw_targets = graph.get("writer_targets")
    if not isinstance(raw_targets, list):
        raise RuntimeError("execution_result:writer_targets_missing")
    expected_targets = [
        {"owner": owner, "target": parse_writer_target(target).as_dict()}
        for owner, target in sorted(writer_targets.items())
    ]
    observed_targets: list[dict[str, object]] = []
    for entry in raw_targets:
        if not is_string_object_mapping(entry) or not is_string_object_mapping(
            entry.get("target")
        ):
            raise RuntimeError("execution_result:writer_target_invalid")
        observed_targets.append(
            {"owner": entry.get("owner"), "target": dict(entry["target"])}
        )
    if observed_targets != expected_targets:
        raise RuntimeError("execution_result:writer_targets_mismatch")


def execution_wave_readback_rows(
    waves: tuple[tuple[SubagentWaveSlot, ...], ...],
    results: Mapping[str, Mapping[str, ToolExecutionResult]],
    *,
    active_budget: int,
    workspace_root: Path,
    writer_targets: Mapping[str, WriterTarget | Mapping[str, object] | None],
) -> tuple[str, ...]:
    """Project successful host results into the existing actual-wave readback."""
    rows: list[str] = []
    for index, wave in enumerate(waves, start=1):
        if not wave:
            continue
        if not all(
            (entry := results.get(slot.executable_identity)) is not None
            and entry.get("completion_result") is not None
            and not entry["spawn_result"].is_error
            and not entry["completion_result"].is_error
            for slot in wave
        ):
            break
        allowed_paths = sorted(
            {
                path
                for slot in wave
                for target in (
                    writer_targets.get(
                        slot.executable_identity,
                        writer_targets.get(slot.role_id, slot.writer_target),
                    ),
                )
                if target is not None
                for path in parse_writer_target(target).allowed_paths
            }
        )
        fields = {
            "wave_id": f"WAVE-{index}",
            "parent_or_delegate": "parent",
            "spawn_authority": "parent_runtime_tool_call",
            "trigger": "execution_graph_ready_set",
            "budget_before": f"{active_budget}/{active_budget}",
            "budget_after": f"{max(0, active_budget - len(wave))}/{active_budget}",
            "runtime_max_threads": str(codex_runtime_max_threads(workspace_root)),
            "runtime_max_depth": str(codex_runtime_max_depth(workspace_root)),
            "spawned_roles": ",".join(slot.role_id for slot in wave),
            "role_instances": ",".join(slot.executable_identity for slot in wave),
            "skipped_roles": "none",
            "allowed_paths": ",".join(allowed_paths) or "none",
            "do_not_read": "none",
            "write_scope": "write_capable" if allowed_paths else "read_only",
            "validation_route": "execution_graph_tool_result",
            "review_gate": "task_close",
            "handoff_artifacts": "team_manifest.yaml#run.execution_graph",
            "status": "completed",
        }
        rows.append(" ".join(f"{key}={value}" for key, value in fields.items()))
    return tuple(rows)


def publish_prepared_run(
    spec: RunBundleSpec,
    prepared: PreparedRunBundle,
    report_root: Path,
    post_move: Callable[[], None] | None = None,
) -> tuple[str, ...]:
    """Stage one prepared byte map, move it once, publish sidecars, and rollback."""
    report_root = report_root.resolve(strict=False)
    configured_runtime = os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip() or None
    runtime_base = configured_runtime or report_root.parent
    source_root = spec.agentcanon_source_root
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    boundary = runtime_artifact_boundary(
        source_root,
        runtime_base,
        create=True,
    )
    report_root = boundary.resolve(report_root)
    boundary.ensure_directory(report_root.relative_to(boundary.root))
    final_run = spec.report_dir.resolve()
    expected_final_run = (report_root / spec.run_id).resolve()
    if final_run != expected_final_run:
        raise RuntimeError("runtime_roots_invalid:report_dir_mismatch")
    if final_run.exists():
        raise RuntimeError(f"bootstrap_run_id_collision:{spec.run_id}")
    pointer = report_root / ".active_run"
    pointer_baseline = report_root / ".active_run.sha256"
    authority_baseline = final_run / f"{AUTHORITY_FILE_NAME}.sha256"
    prior_files = {
        pointer: _read_optional_bytes(pointer),
        pointer_baseline: _read_optional_bytes(pointer_baseline),
        authority_baseline: _read_optional_bytes(authority_baseline),
    }
    prior_children: set[str] = (
        {child.name for child in report_root.iterdir()}
        if report_root.is_dir()
        else set()
    )
    stage_dir: Path | None = None
    moved = False
    try:
        stage_dir = Path(tempfile.mkdtemp(prefix=".stage-run-", dir=str(report_root)))
        for relative, payload in prepared.files:
            relative_path = Path(relative)
            if (
                relative_path.is_absolute()
                or not relative
                or any(part in {"", ".", ".."} for part in relative_path.parts)
            ):
                raise RuntimeError(f"runtime_artifact_path_invalid:stage:{relative}")
            target = stage_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            if target.read_bytes() != payload:
                raise RuntimeError(f"bootstrap_stage_readback_failed:{relative}")
        os.replace(stage_dir, final_run)
        stage_dir = None
        moved = True
        pointer_bytes = (str(final_run.resolve()) + "\n").encode("utf-8")
        boundary.atomic_write_bytes(pointer, pointer_bytes)
        boundary.atomic_write_bytes(
            pointer_baseline, hash_baseline_bytes(pointer_bytes)
        )
        authority_path = final_run / AUTHORITY_FILE_NAME
        if authority_path.is_file():
            boundary.atomic_write_bytes(
                authority_baseline,
                hash_baseline_bytes(authority_path.read_bytes()),
            )
        if post_move is not None:
            post_move()
        for relative, payload in prepared.files:
            if relative == "workflow_monitoring.md":
                continue
            if (final_run / relative).read_bytes() != payload:
                raise RuntimeError(f"bootstrap_final_readback_failed:{relative}")
        monitoring_path = final_run / "workflow_monitoring.md"
        if not monitoring_path.is_file() or not monitoring_path.read_bytes().startswith(
            dict(prepared.files).get("workflow_monitoring.md", b"")
        ):
            raise RuntimeError("bootstrap_monitoring_readback_failed")
        if pointer.read_bytes() != pointer_bytes:
            raise RuntimeError("bootstrap_pointer_readback_failed")
        if pointer_baseline.read_bytes() != hash_baseline_bytes(pointer_bytes):
            raise RuntimeError("bootstrap_pointer_baseline_readback_failed")
        if (
            authority_path.is_file()
            and authority_baseline.read_bytes()
            != hash_baseline_bytes(authority_path.read_bytes())
        ):
            raise RuntimeError("bootstrap_authority_baseline_readback_failed")
        return prepared.created_files
    except Exception as primary_error:
        rollback_errors: list[str] = []
        try:
            if stage_dir is not None and stage_dir.exists():
                shutil.rmtree(stage_dir)
            if moved and final_run.exists():
                shutil.rmtree(final_run)
            for path, prior in prior_files.items():
                _restore_runtime_file(
                    boundary,
                    path,
                    prior,
                    "bootstrap-publish-rollback",
                )
            observed_children: set[str] = (
                {child.name for child in report_root.iterdir()}
                if report_root.is_dir()
                else set()
            )
            if observed_children != prior_children:
                raise RuntimeError(
                    f"child_delta:{sorted(observed_children ^ prior_children)}"
                )
            for path, prior in prior_files.items():
                if _read_optional_bytes(path) != prior:
                    raise RuntimeError(f"prior_bytes:{path}")
        except Exception as rollback_error:
            rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise RuntimeError(
                "bootstrap_publish_rollback_failed:"
                f"{primary_error}:{';'.join(rollback_errors)}"
            ) from primary_error
        raise


PublisherSpawn = Callable[[str, str], str | None]


def main(
    argv: Sequence[str] | None = None,
    *,
    spawn: PublisherSpawn | None = None,
) -> int:
    """Run the bootstrap command."""
    # Source resolution itself uses the external runtime boundary.  Parse only
    # that capability before loading source-owned config so an unrelated
    # caller TMPDIR cannot be mistaken for this run's artifact root.
    runtime_parser = argparse.ArgumentParser(add_help=False)
    runtime_parser.add_argument("--runtime-root")
    runtime_args, _ = runtime_parser.parse_known_args()
    selected_runtime = (
        runtime_args.runtime_root
        or os.environ.get("AGENT_CANON_RUNTIME_ROOT", "").strip()
    )
    if selected_runtime:
        os.environ["AGENT_CANON_RUNTIME_ROOT"] = selected_runtime
        for name in (
            "TMPDIR",
            "TEMP",
            "TMP",
            "XDG_CACHE_HOME",
            "PYTHONPYCACHEPREFIX",
            "AGENT_CANON_TOOLS_HOME",
            "CARGO_HOME",
            "CARGO_TARGET_DIR",
            "AGENT_CANON_CLI_TARGET_DIR",
            "RUSTUP_HOME",
            "ELAN_HOME",
        ):
            os.environ.pop(name, None)
    try:
        source_resolution = resolve_agent_canon_source_root(Path(__file__).resolve())
        source_root = source_resolution.source_root
        config = load_team_config(source_root / "agents" / "agents_config.json")
        catalog = load_task_catalog(config, root=source_root)
    except (RuntimeError, OSError) as exc:
        print(str(exc), flush=True)
        return 1
    args = build_parser(enable_choices(config, catalog), task_ids(catalog)).parse_args(
        argv
    )
    try:
        issue_worker_candidate = parse_issue_worker_candidate(
            args.issue_worker_candidate
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 2
    try:
        explicit_active_design_packet = parse_active_design_packet_input(
            args.active_design_packet
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 2
    try:
        writer_targets: dict[str, WriterTarget] = {}
        if args.writer_targets:
            parsed_targets = json.loads(args.writer_targets)
            if not is_string_object_dict(parsed_targets):
                raise WriterTargetError("writer_targets:must_be_mapping")
            for owner, target in parsed_targets.items():
                if not is_string_object_mapping(target):
                    raise WriterTargetError(
                        "writer_targets:owner_target_must_be_mapping"
                    )
                writer_targets[owner] = parse_writer_target(target)
    except (TypeError, json.JSONDecodeError, WriterTargetError) as exc:
        print(str(exc), flush=True)
        return 2
    if args.execution_results is not None and not args.run_id:
        print("execution_result:run_id_required", flush=True)
        return 2
    try:
        execution_results = parse_execution_results(args.execution_results)
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 2
    workspace_root = Path(args.workspace_root).resolve()
    try:
        repository_roots = resolve_repository_roots(
            workspace_root,
            args.report_root,
            source_root=source_root,
            canon_root=source_resolution.canon_root,
            runtime_root=args.runtime_root,
        )
    except (RuntimeError, OSError) as exc:
        print(str(exc), flush=True)
        return 1
    context = resolve_bootstrap_context(
        args,
        config,
        catalog,
        workspace_root,
        repository_roots,
        issue_worker_candidate,
    )
    resuming_run = context.report_dir.exists()
    if resuming_run and args.execution_results is None:
        print(f"bootstrap_run_id_collision:{context.run_id}", flush=True)
        return 1
    if not resuming_run and args.execution_results is not None:
        print("execution_result:run_not_found", flush=True)
        return 1
    existing_run: Mapping[str, object] | None = None
    prior_execution_results: dict[str, dict[str, ToolExecutionResult]] = {}
    if resuming_run:
        try:
            existing_run = validate_execution_run_readback(
                context.report_dir,
                context.report_root,
                context.run_id,
                args.task,
                args.owner,
            )
        except (RuntimeError, OSError) as exc:
            print(str(exc), flush=True)
            return 1
        try:
            prior_execution_results = persisted_execution_results(existing_run)
            execution_results = merge_execution_results(
                prior_execution_results,
                execution_results,
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            print(str(exc), flush=True)
            return 1
    try:
        math_packet_input = parse_math_intent_packet_input(args.math_intent_packet)
        if context.math_intent_route is not None and math_packet_input is None:
            raise RuntimeError("math_packet_missing")
        if context.math_intent_route is None and math_packet_input is not None:
            raise RuntimeError("math_packet_not_applicable")
        math_intent_packet = (
            normalize_mathematical_intent_packet(math_packet_input)
            if math_packet_input is not None
            else None
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 2
    roles = select_roles(
        config,
        list(context.enabled_specialists),
        args.full_team,
        catalog=catalog,
        workflow_family_id=context.workflow_family_id,
        issue_worker_candidate=context.issue_worker_candidate,
        adversarial_required=context.adversarial_required,
    )
    try:
        agent_type_selections = validate_agent_type_selections(
            config,
            roles,
            parse_agent_type_selections(tuple(args.select_agent_type)),
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        return 1
    issue_worker_dispatch: Mapping[str, object] | None = None
    if (
        context.workflow_family_id == "issue_worker_publication"
        and context.issue_worker_candidate
    ):
        try:
            dispatched = dispatch_issue_worker(
                context.issue_worker_candidate,
                args.task,
                None,
                workspace_root=workspace_root,
                agentcanon_source_root=repository_roots.agentcanon_source_root,
            )
            issue_worker_dispatch = dispatched.as_dict()
        except (RuntimeError, OSError) as exc:
            print(str(exc), flush=True)
            return 1
    selected_skills = suggested_skills(
        args.task_id,
        context.workflow_family_id,
        args.task,
        source_root=repository_roots.agentcanon_source_root,
        issue_worker_candidate=context.issue_worker_candidate,
    )
    typed_route_required = workflow_child_handoff_required(
        config,
        catalog,
        context.workflow_family_id,
        context.issue_worker_candidate,
    )
    active_skills = current_stage_skills(
        selected_skills,
        args.task,
        source_root=repository_roots.agentcanon_source_root,
        typed_route_required=typed_route_required,
    )
    deferred_skills = deferred_stage_skills(
        selected_skills,
        args.task,
        source_root=repository_roots.agentcanon_source_root,
        typed_route_required=typed_route_required,
    )
    try:
        existing_graph: Mapping[str, object] | None = None
        if existing_run is not None:
            raw_existing_graph = existing_run.get("execution_graph")
            if not is_string_object_mapping(raw_existing_graph):
                raise RuntimeError("execution_result:execution_graph_missing")
            existing_graph = raw_existing_graph
        skill_documents = read_selected_skill_documents(
            active_skills,
            repository_roots.agentcanon_source_root,
            existing_graph=existing_graph,
        )
    except (OSError, RuntimeError, SkillDocumentError, ValueError) as exc:
        print(f"skill_execution_graph_read_failed:{exc}", flush=True)
        return 1
    execution_waves: tuple[tuple[SubagentWaveSlot, ...], ...] = ()
    graph_issue_worker_candidate = context.issue_worker_candidate
    if (
        context.workflow_family_id == "issue_worker_publication"
        and issue_worker_dispatch is not None
        and issue_worker_dispatch.get("status") not in {"pending", "spawned"}
    ):
        graph_issue_worker_candidate = None
    if context.workflow_family_id is not None and context.workflow_active_spawn_budget:
        active_budget = context.workflow_active_spawn_budget
        initial_slots = recommended_initial_subagent_wave_slots(
            roles,
            active_budget,
            catalog,
            agent_type_selections,
            repository_roots.agentcanon_source_root / ".codex" / "agents",
            workflow_family_id=context.workflow_family_id,
            issue_worker_candidate=graph_issue_worker_candidate,
            writer_targets=writer_targets,
            math_intent_route_id=context.math_intent_route,
        )
        initial_wave = tuple(slot.agent_type for slot in initial_slots)
        expansion_waves = recommended_dynamic_expansion_wave_slots(
            roles,
            active_budget,
            initial_wave,
            catalog,
            agent_type_selections,
            repository_roots.agentcanon_source_root / ".codex" / "agents",
            workflow_family_id=context.workflow_family_id,
            issue_worker_candidate=graph_issue_worker_candidate,
            writer_targets=writer_targets,
            math_intent_route_id=context.math_intent_route,
        )
        execution_waves = (initial_slots, *expansion_waves)
    if existing_run is not None:
        try:
            validate_execution_graph_readback(
                existing_run,
                workflow_family_id=context.workflow_family_id,
                task_id=args.task_id,
                math_intent_route=context.math_intent_route,
                roles=roles,
                issue_worker_dispatch=issue_worker_dispatch,
                selected_skills=selected_skills,
                agent_type_selections=agent_type_selections,
                waves=execution_waves,
                writer_targets=writer_targets,
            )
        except (RuntimeError, ValueError, WriterTargetError) as exc:
            print(str(exc), flush=True)
            return 1
    try:
        execution_transition = advance_execution_graph(
            execution_waves,
            execution_results,
        )
        if context.workflow_family_id != "issue_worker_publication" and any(
            "publication_result" in result for result in execution_results.values()
        ):
            raise RuntimeError("execution_result:publication_not_applicable")
        execution_tool_calls: tuple[dict[str, object], ...] = ()
        execution_spawn_results: tuple[tuple[str, str], ...] = ()
        deferred_tool_call_transition: ExecutionGraphTransition | None = None
        if execution_transition.ready_slots:
            if (
                context.workflow_family_id == "issue_worker_publication"
                and issue_worker_dispatch is not None
                and issue_worker_dispatch.get("status") != "pending"
            ):
                execution_transition = ExecutionGraphTransition(
                    status="waiting",
                    wave_index=execution_transition.wave_index,
                    waiting_identities=("publisher",),
                )
            else:
                issue_spawn_call = (
                    issue_worker_dispatch.get("spawn_tool_call")
                    if issue_worker_dispatch is not None
                    and context.workflow_family_id == "issue_worker_publication"
                    else None
                )
                if is_string_object_mapping(issue_spawn_call):
                    if spawn is None:
                        issue_call = dict(issue_spawn_call)
                        issue_arguments = issue_call.get("arguments")
                        if not is_string_object_mapping(
                            issue_arguments
                        ) or not isinstance(issue_arguments.get("input"), str):
                            raise RuntimeError(
                                "execution_graph:issue_worker_prompt_missing"
                            )
                        issue_arguments = dict(issue_arguments)
                        issue_arguments["input"] += "\n\n" + skill_document_context(
                            skill_documents
                        )
                        issue_call["arguments"] = issue_arguments
                        execution_tool_calls = (issue_call,)
                    else:
                        if len(execution_transition.ready_slots) != 1:
                            raise RuntimeError(
                                "execution_graph:issue_worker_wave_must_be_singleton"
                            )
                        issue_spawn = dispatch_issue_worker(
                            context.issue_worker_candidate or {},
                            args.task,
                            lambda role, prompt: spawn(
                                role,
                                prompt
                                + "\n\n"
                                + skill_document_context(skill_documents),
                            ),
                            workspace_root=workspace_root,
                            agentcanon_source_root=repository_roots.agentcanon_source_root,
                        )
                        if (
                            issue_spawn.status != "spawned"
                            or not issue_spawn.publisher_agent_id
                        ):
                            raise RuntimeError(
                                "execution_graph:issue_worker_spawn_failed:"
                                + issue_spawn.status
                            )
                        issue_worker_dispatch = issue_spawn.as_dict()
                        publisher_slot = execution_transition.ready_slots[0]
                        publisher_id = issue_spawn.publisher_agent_id
                        execution_spawn_results = (
                            (publisher_slot.executable_identity, publisher_id),
                        )
                        execution_results = {
                            **execution_results,
                            publisher_slot.executable_identity: {
                                "spawn_result": ToolExecutionResult(
                                    is_error=False,
                                    text=publisher_id,
                                )
                            },
                        }
                        execution_transition = advance_execution_graph(
                            execution_waves,
                            execution_results,
                        )
                        execution_tool_calls = ()
                else:
                    if spawn is None:
                        deferred_tool_call_transition = execution_transition
                    else:
                        execution_tool_calls = materialize_execution_tool_calls(
                            transition=execution_transition,
                            roles=roles,
                            task=args.task,
                            run_id=context.run_id,
                            workspace_root=workspace_root,
                            workflow_family_id=context.workflow_family_id,
                            catalog=catalog,
                            skill_documents=skill_documents,
                            completed_results=execution_transition.completed_results,
                            writer_targets=writer_targets,
                            math_intent_route=context.math_intent_route,
                            math_intent_packet=math_intent_packet,
                        )
        if spawn is not None and execution_transition.ready_slots:
            prompts: dict[str, str] = {}
            for slot, call in zip(
                execution_transition.ready_slots, execution_tool_calls, strict=True
            ):
                arguments = call.get("arguments")
                if not is_string_object_mapping(arguments) or not isinstance(
                    arguments.get("input"), str
                ):
                    raise RuntimeError("execution_graph:tool_call_input_missing")
                prompts[slot.executable_identity] = arguments["input"]
            spawned_ids = dispatch_subagent_wave(
                execution_transition.ready_slots,
                prompts,
                spawn,
                writer_targets,
                math_intent_packet=math_intent_packet,
            )
            execution_spawn_results = tuple(
                (slot.executable_identity, agent_id)
                for slot, agent_id in zip(
                    execution_transition.ready_slots, spawned_ids, strict=True
                )
            )
            updated_results = dict(execution_results)
            updated_results.update(
                {
                    identity: {
                        "spawn_result": ToolExecutionResult(
                            is_error=False,
                            text=agent_id,
                        )
                    }
                    for identity, agent_id in execution_spawn_results
                }
            )
            execution_results = updated_results
            execution_transition = advance_execution_graph(
                execution_waves,
                execution_results,
            )
            execution_tool_calls = ()
            if issue_worker_dispatch is not None:
                issue_worker_dispatch = {
                    **issue_worker_dispatch,
                    "status": "spawned",
                    "publisher_agent_id": spawned_ids[0],
                }
        if context.workflow_family_id == "issue_worker_publication":
            if any(
                "publication_result" in result for result in execution_results.values()
            ):
                if not all(
                    "completion_result" in result
                    for result in execution_results.values()
                ):
                    raise RuntimeError(
                        "execution_result:publication_before_publisher_completion"
                    )
                publication_results = [
                    result["publication_result"]
                    for result in execution_results.values()
                    if "publication_result" in result
                ]
                if any(result.is_error for result in publication_results):
                    if issue_worker_dispatch is not None:
                        issue_worker_dispatch = {
                            **issue_worker_dispatch,
                            "status": "failed",
                            "publisher_agent_id": next(
                                iter(execution_results.values())
                            )["spawn_result"].text,
                        }
                    execution_transition = ExecutionGraphTransition(
                        status="failed",
                        wave_index=len(execution_waves),
                        failed_identities=tuple(execution_results),
                    )
                else:
                    if issue_worker_dispatch is not None:
                        issue_worker_dispatch = {
                            **issue_worker_dispatch,
                            "status": "result_received",
                            "publisher_agent_id": next(
                                iter(execution_results.values())
                            )["spawn_result"].text,
                        }
                    execution_transition = ExecutionGraphTransition(
                        status="awaiting_closeout",
                        wave_index=None,
                        completed_results=execution_transition.completed_results,
                    )
            elif (
                execution_transition.status == "awaiting_closeout" and execution_results
            ):
                publisher_result = next(iter(execution_results.values()))
                publisher_agent_id = publisher_result["spawn_result"].text
                dispatched = dispatch_issue_worker(
                    context.issue_worker_candidate or {},
                    args.task,
                    lambda _agent_type, _prompt: publisher_agent_id,
                    workspace_root=workspace_root,
                    agentcanon_source_root=repository_roots.agentcanon_source_root,
                )
                issue_worker_dispatch = dispatched.as_dict()
                issue_call = dispatched.tool_call
                if issue_call is None:
                    raise RuntimeError("execution_graph:issue_worker_tool_call_missing")
                execution_tool_calls = (issue_call,)
                execution_transition = ExecutionGraphTransition(
                    status="ready",
                    wave_index=len(execution_waves),
                )
    except (RuntimeError, OSError, WriterTargetError) as exc:
        print(str(exc), flush=True)
        return 1
    manifest_issue_worker_dispatch = None
    if issue_worker_dispatch is not None:
        manifest_issue_worker_dispatch = {
            key: value
            for key, value in issue_worker_dispatch.items()
            if key not in {"tool_call", "spawn_tool_call"} or value is None
        }
    run_spec = RunBundleSpec(
        config=config,
        report_dir=context.report_dir,
        run_id=context.run_id,
        task=args.task,
        owner=args.owner,
        created_at_iso=context.created_at_iso,
        roles=roles,
        workspace_root=workspace_root,
        agentcanon_source_root=repository_roots.agentcanon_source_root,
        report_root=repository_roots.report_root,
        repository_roots=repository_roots,
        active_design_packet=explicit_active_design_packet,
        workflow_family_id=context.workflow_family_id or "",
        issue_worker_candidate=context.issue_worker_candidate,
        issue_worker_dispatch=manifest_issue_worker_dispatch,
        manual_specialists=context.manual_specialists,
        task_default_specialists=context.task_default_specialists,
        language_review_candidates=context.language_review_candidates,
        default_review_packs_enabled=False,
        default_review_pack_ids=context.default_review_pack_ids,
        selected_skills=selected_skills,
        task_catalog=catalog,
        task_id=args.task_id,
        math_intent_route=context.math_intent_route,
        math_intent_packet=math_intent_packet,
        agent_type_selections=agent_type_selections,
        writer_targets=writer_targets,
    )
    try:
        prepared = prepare_run_bundle(run_spec)
        active_design_packet = prepared.active_design_packet
    except (RuntimeError, OSError, WriterTargetError) as exc:
        print(str(exc), flush=True)
        return 1
    if deferred_tool_call_transition is not None:
        try:
            roles_by_id = {role.id: role for role in roles}
            role_document_contexts: dict[str, str] = {}
            for slot in deferred_tool_call_transition.ready_slots:
                role = roles_by_id.get(slot.role_id)
                if role is None:
                    raise RuntimeError(f"execution_graph:role_missing:{slot.role_id}")
                role_document_contexts[slot.role_id] = role_document_packet_context(
                    config=config,
                    role=role,
                    report_dir=context.report_dir,
                    workspace_root=workspace_root,
                    agentcanon_source_root=repository_roots.agentcanon_source_root,
                    prepared=prepared,
                    skill_documents=skill_documents,
                    existing_run=resuming_run,
                )
            execution_tool_calls = materialize_execution_tool_calls(
                transition=deferred_tool_call_transition,
                roles=roles,
                task=args.task,
                run_id=context.run_id,
                workspace_root=workspace_root,
                workflow_family_id=context.workflow_family_id,
                catalog=catalog,
                skill_documents=skill_documents,
                completed_results=deferred_tool_call_transition.completed_results,
                writer_targets=writer_targets,
                math_intent_route=context.math_intent_route,
                math_intent_packet=math_intent_packet,
                role_document_contexts=role_document_contexts,
            )
        except (
            RuntimeError,
            OSError,
            SkillDocumentError,
            ValueError,
            WriterTargetError,
        ) as exc:
            print(str(exc), flush=True)
            return 1
    active_pointer = context.report_root / ".active_run"
    review_roles = selected_review_roles(roles)
    workflow_context_result: StoreResult | None = None

    def post_move() -> None:
        nonlocal workflow_context_result
        if context.workflow_family_id is not None:
            workflow_context_result = store_workflow_context(
                context.report_dir / "skill_usage_context.json",
                context_from_workflows(
                    (context.workflow_family_id,), "bootstrap_agent_run.task_id"
                ),
            )
        record_bootstrap_monitoring(
            context,
            roles,
            selected_skills,
            review_roles,
            args.task,
            repository_roots.agentcanon_source_root,
        )

    if resuming_run:
        try:
            prior_completed_wave_ids = set(
                completed_execution_wave_ids(execution_waves, prior_execution_results)
            )
            current_completed_wave_ids = set(
                completed_execution_wave_ids(execution_waves, execution_results)
            )
            newly_completed_wave_ids = (
                current_completed_wave_ids - prior_completed_wave_ids
            )
            readback_rows = execution_wave_readback_rows(
                execution_waves,
                execution_results,
                active_budget=context.workflow_active_spawn_budget or 0,
                workspace_root=workspace_root,
                writer_targets=writer_targets,
            )
            readback_rows = tuple(
                row
                for row in readback_rows
                if row.partition(" ")[0].removeprefix("wave_id=")
                in newly_completed_wave_ids
            )
            if readback_rows:
                append_monitoring(
                    context.report_dir,
                    subagent_waves=readback_rows,
                    runtime_root=args.runtime_root,
                )
        except (RuntimeError, OSError, ValueError) as exc:
            print(str(exc), flush=True)
            return 1
        created_files: tuple[str, ...] = ()
    else:
        try:
            publish_prepared_run(
                run_spec,
                prepared,
                context.report_root,
                post_move=post_move,
            )
        except (RuntimeError, OSError) as exc:
            print(str(exc), flush=True)
            return 1
        created_files = prepared.created_files
        if (
            workflow_context_result is not None
            and workflow_context_result.status == "stored"
        ):
            created_files = (*created_files, "skill_usage_context.json")
    try:
        persist_execution_graph_readback(
            repository_roots.agentcanon_source_root,
            args.runtime_root,
            context.report_dir,
            execution_waves,
            execution_results,
            execution_transition,
            skill_documents,
            issue_worker_dispatch,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(str(exc), flush=True)
        return 1
    runtime = BootstrapRuntime(
        roles=roles,
        created_files=created_files,
        active_pointer=active_pointer,
        agent_type_selections=agent_type_selections,
        active_design_packet=active_design_packet,
        math_intent_packet=math_intent_packet,
        issue_worker_dispatch=issue_worker_dispatch,
        skill_documents=skill_documents,
        selected_skills=selected_skills,
        active_skills=active_skills,
        deferred_skills=deferred_skills,
        execution_transition=execution_transition,
        execution_tool_calls=execution_tool_calls,
        execution_spawn_results=execution_spawn_results,
    )
    emit_bootstrap_output(
        args=args,
        config=config,
        catalog=catalog,
        context=context,
        workspace_root=workspace_root,
        runtime=runtime,
    )
    return 1 if execution_transition.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
