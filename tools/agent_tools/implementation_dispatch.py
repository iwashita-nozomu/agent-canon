# @dependency-start
# contract tool
# responsibility AgentTeam implementation dispatch owner module.
# upstream design ../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# upstream implementation ./capacity_handshake.py owns provider capacity transitions.
# upstream implementation ./implementation_route.py owns implementation eligibility.
# upstream implementation ./model_profile_registry.py owns prompt/profile materialization.
# downstream implementation ./agent_team.py facade consumes capacity APIs.
# downstream implementation ./bootstrap_agent_run.py consumes capacity APIs.
# @dependency-end
"""Own AgentTeam capacity derivation and implementation dispatch."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import cast

try:
    import tomllib  # pyright: ignore[reportMissingImports]
except ModuleNotFoundError:  # Python < 3.11 compatibility.
    import tomli as tomllib  # type: ignore[no-redef]

if __package__:
    from . import capacity_handshake, implementation_route, model_profile_registry
    from .checkout_identity import resolve_checkout_identity
else:
    import capacity_handshake
    import implementation_route
    import model_profile_registry
    from checkout_identity import resolve_checkout_identity  # type: ignore[no-redef]


if __package__:
    from .team_config import (
        ROOT,
        AgentTypeSelection,
        Role,
        RunBundleSpec,
        SubagentWaveSlot,
        TaskCatalog,
        TeamConfig,
        _as_mapping_tuple,
        _as_object_mapping,
        _as_required_string,
        _as_string_tuple,
        catalog_stage_waves,
    )
else:
    from team_config import (
        ROOT,
        AgentTypeSelection,
        Role,
        RunBundleSpec,
        SubagentWaveSlot,
        TaskCatalog,
        TeamConfig,
        _as_mapping_tuple,
        _as_object_mapping,
        _as_required_string,
        _as_string_tuple,
        catalog_stage_waves,
    )

if __package__:
    from .team_config import CODEX_AGENT_ROOT
else:
    from team_config import CODEX_AGENT_ROOT

DEFAULT_QUALITY_CHECK_ROLE_IDS = (
    "docs_workflow_steward",
    "python_reviewer",
    "cpp_reviewer",
    "change_reviewer",
)
NON_SPAWN_WAVE_ROLE_IDS = {"manager", "verifier", "auditor"}


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
        """Return the stable consumer-binding schema identifier."""
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


def _capacity_family_record(
    family: dict[str, object],
) -> capacity_handshake.DeclaredFamilyCapacity:
    """Derive one family capacity record from its declared stage topology."""
    family_id = _as_required_string(family.get("id"), "workflow_family.id")
    roles = _as_object_mapping(
        cast(object, family.get("roles", {})), "workflow_family.roles"
    )
    declared_roles = set(
        _as_string_tuple(roles.get("always_on"), "workflow_family.roles.always_on")
        + _as_string_tuple(
            roles.get("specialists"), "workflow_family.roles.specialists"
        )
    )
    topology = _as_object_mapping(
        cast(object, family.get("role_topology", {})),
        "workflow_family.role_topology",
    )
    waves = _as_mapping_tuple(
        topology.get("stage_waves"), "workflow_family.stage_waves"
    )

    def stage_roles(stage_class: str) -> tuple[str, ...]:
        selected: list[str] = []
        for wave in waves:
            if wave.get("stage_class") != stage_class:
                continue
            for role_id in _as_string_tuple(
                wave.get("role_ids"), "stage_wave.role_ids"
            ):
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
        nested_reservation_count=len(
            tuple(role_id for role_id in nested if role_id not in isolated)
        ),
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
        topology=capacity_handshake.DescendantTopologyReadback(
            parent_work_id=spec.run_id
        )
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


def _json_capacity_record(
    record: capacity_handshake.DescendantLifecycleRecord,
) -> dict[str, object]:
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


def _capacity_projection(
    runtime: _CapacityRuntime, spec: RunBundleSpec
) -> dict[str, object]:
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
        "reload_state": "restart_required"
        if configured != runtime.requested_capacity
        else "current",
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
            "descendants": [
                _json_capacity_record(record)
                for record in runtime.ledger.topology.descendants
            ],
            "reservations": [
                {
                    "parent_work_id": edge.parent_work_id,
                    "child_work_id": edge.child_work_id,
                }
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
    source_root = spec.agentcanon_source_root
    if source_root is None and spec.repository_roots is not None:
        source_root = spec.repository_roots.agentcanon_source_root
    if source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    registry = model_profile_registry.load_model_profile_registry(
        spec.workspace_root,
        source_root=source_root,
    )
    for record in runtime.ledger.topology.descendants:
        if record.status not in {
            capacity_handshake.LifecycleStatus.READBACK_VERIFIED,
            capacity_handshake.LifecycleStatus.RESERVATION_RELEASED,
        }:
            continue
        if not record.profile_id:
            raise RuntimeError(
                f"closeout record lacks profile identity: {record.work_id}"
            )
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
    source_root: Path | None = None,
    capacity_runtime: _CapacityRuntime | None = None,
) -> ImplementationDispatch:
    """Route, materialize, and launch exactly one fixed Spark implementation worker."""
    route_result = implementation_route.route_implementation(request)
    if route_result.status == "blocked":
        return ImplementationDispatch(
            route_result, None, None, None, route_result.next_gate, 1, 0, "blocked"
        )
    if route_result.status == "queued":
        return ImplementationDispatch(
            route_result, None, None, None, route_result.next_gate, 1, 0, "queued"
        )
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
    registry = model_profile_registry.load_model_profile_registry(
        workspace_root,
        source_root=source_root,
    )
    prompt = model_profile_registry.materialize_prompt_capsule(
        model_profile_registry.PromptMaterializationRequest(
            profile_id=route_result.selected_profile_id,
            role_id="spark_worker",
            context=(
                model_profile_registry.ContextItem("objective", objective),
                model_profile_registry.ContextItem(
                    "context", "fixed_packet_direct_materialization"
                ),
                model_profile_registry.ContextItem(
                    "fixed_implementation_packet", packet_context
                ),
                model_profile_registry.ContextItem(
                    "implementation_route_result", asdict(route_result)
                ),
                model_profile_registry.ContextItem(
                    "owner_gate", route_result.next_gate
                ),
                model_profile_registry.ContextItem(
                    "checkout_identity",
                    resolve_checkout_identity(workspace_root).as_dict(),
                ),
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
            readiness = capacity_handshake.request_slot(
                capacity_runtime.snapshot, capacity_runtime.ledger, item
            )
            if readiness.status != "ready":
                return ImplementationDispatch(
                    route_result,
                    prompt,
                    None,
                    None,
                    route_result.next_gate,
                    1,
                    0,
                    "queued",
                )
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
            return ImplementationDispatch(
                route_result,
                prompt,
                None,
                None,
                "WRITE_SUBAGENT_AUTHORIZATION=required",
                1,
                spawn_count,
                "blocked",
            )
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
    reload_state = (
        "restart_required"
        if configured != witness.requested_total_capacity
        else "current"
    )
    return (
        "CAPACITY_REQUEST_SCHEMA=team_manifest_capacity_request_v1",
        f"REQUESTED_TOTAL_CAPACITY={witness.requested_total_capacity}",
        "CAPACITY_TOPOLOGY_PROOF_REF=agents/task_catalog.yaml",
        f"CAPACITY_TOPOLOGY_PROOF_SHA256={witness.declared_team_topology_sha256}",
        "CAPACITY_POLICY_REF=agents/capacity_policy.toml",
        f"CAPACITY_POLICY_DIGEST={contract.capacity_policy.topology_proof_sha256}",
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
        record
        for record in derivation.family_records
        if record.workflow_family_id == family_id
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


def codex_runtime_max_threads(root: Path = ROOT) -> int:
    """Return the configured runtime max_threads from .codex/config.toml."""
    return codex_runtime_agent_int("max_threads", root=root)


def codex_runtime_max_depth(root: Path = ROOT) -> int:
    """Return the configured runtime max_depth from .codex/config.toml."""
    return codex_runtime_agent_int("max_depth", root=root)


def codex_runtime_agent_int(key: str, *, root: Path = ROOT) -> int:
    """Return one configured integer from the Codex [agents] runtime section."""
    config_path = root.resolve() / ".codex" / "config.toml"
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
