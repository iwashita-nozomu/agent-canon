# @dependency-start
# contract tool
# responsibility Owns fixed implementation dispatch and existing AgentTeam validation.
# upstream design ../../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# upstream implementation ./team_config.py owns shared configuration normalization.
# upstream implementation ./implementation_route.py owns implementation eligibility.
# upstream implementation ./model_profile_registry.py owns prompt/profile materialization.
# upstream implementation ../../runtime/values.py refines decoded packet containers.
# downstream implementation ./agent_team.py facade consumes role and dispatch APIs.
# @dependency-end
"""Own fixed implementation dispatch and role-type selection."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from tools.runtime.values import (
    is_string_object_mapping,
)

if __package__:
    from . import implementation_route, model_profile_registry
    from tools.runtime.authority.writer_target import (
        WriterTarget,
        WriterTargetError,
        validate_mathematical_writer_target,
        validate_writer_target_identity,
    )
    from tools.runtime.authority.checkout_identity import resolve_checkout_identity
else:
    from tools.agent.orchestration import implementation_route, model_profile_registry
    from tools.runtime.authority.writer_target import (  # type: ignore[no-redef]
        WriterTarget,
        WriterTargetError,
        validate_mathematical_writer_target,
        validate_writer_target_identity,
    )
    from tools.runtime.authority.checkout_identity import resolve_checkout_identity  # type: ignore[no-redef]


if __package__:
    from .team_config import (
        ROOT,
        AgentTypeSelection,
        Role,
        TeamConfig,
    )
else:
    from tools.agent.orchestration.team_config import (
        ROOT,
        AgentTypeSelection,
        Role,
        TeamConfig,
    )

if __package__:
    from .team_config import CODEX_AGENT_ROOT
else:
    from tools.agent.orchestration.team_config import CODEX_AGENT_ROOT

DEFAULT_QUALITY_CHECK_ROLE_IDS = (
    "docs_workflow_steward",
    "python_reviewer",
    "cpp_reviewer",
    "change_reviewer",
)


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


def dispatch_fixed_implementation(
    request: Mapping[str, object] | implementation_route.ImplementationRouteRequest,
    objective: str,
    spawn: Callable[[str, str], str | None],
    *,
    workspace_root: Path = ROOT,
    source_root: Path | None = None,
    writer_target: WriterTarget | Mapping[str, object] | None = None,
    checkout_identity: Mapping[str, object] | None = None,
    math_intent_route: str | None = None,
    math_intent_packet: Mapping[str, object] | object | None = None,
    selected_skills: Sequence[str] = (),
    role_id: str = "implementer",
) -> ImplementationDispatch:
    """Route, materialize, and launch exactly one fixed Spark implementation worker."""
    route_result = implementation_route.route_implementation(request)
    if route_result.status == "blocked":
        return ImplementationDispatch(
            route_result, None, None, None, route_result.next_gate, 1, 0, "blocked"
        )
    if (
        route_result.selected_agent_type != "spark_worker"
        or route_result.selected_profile_id != "spark_implementation_low"
        or route_result.failure is not None
    ):
        raise RuntimeError("implementation_dispatch:fixed_route_violation")
    if __package__:
        from .packets import (
            mathematical_intent_packet_mapping,
            math_intent_route_id_from_context,
            normalize_mathematical_intent_packet,
        )
    else:
        from tools.agent.orchestration.packets import (  # type: ignore[no-redef]
            mathematical_intent_packet_mapping,
            math_intent_route_id_from_context,
            normalize_mathematical_intent_packet,
        )
    selected_math_route = math_intent_route_id_from_context(
        selected_skills,
        (role_id,),
        packet_present=math_intent_packet is not None,
        explicit_route_id=math_intent_route,
    )
    normalized_math_packet: Mapping[str, object] | None = None
    if selected_math_route is not None and math_intent_packet is None:
        return ImplementationDispatch(
            route_result,
            None,
            None,
            None,
            "math_packet_missing",
            1,
            0,
            "blocked",
        )
    if selected_math_route is None and math_intent_packet is not None:
        return ImplementationDispatch(
            route_result,
            None,
            None,
            None,
            "math_packet_not_applicable",
            1,
            0,
            "blocked",
        )
    if selected_math_route is not None:
        normalized_math_packet = mathematical_intent_packet_mapping(
            normalize_mathematical_intent_packet(math_intent_packet)
        )
    if writer_target is None:
        return ImplementationDispatch(
            route_result,
            None,
            None,
            None,
            "writer_target:required_before_spawn",
            1,
            0,
            "blocked",
        )
    if checkout_identity is None:
        checkout_identity = resolve_checkout_identity(workspace_root).as_dict()
    try:
        parsed_writer_target = validate_writer_target_identity(
            writer_target,
            checkout_identity,
        )
    except WriterTargetError as exc:
        raise RuntimeError(str(exc)) from exc
    if selected_math_route is not None:
        try:
            validate_mathematical_writer_target(
                parsed_writer_target, normalized_math_packet
            )
        except WriterTargetError as exc:
            return ImplementationDispatch(
                route_result,
                None,
                None,
                None,
                str(exc),
                1,
                0,
                "blocked",
            )
    if isinstance(request, implementation_route.ImplementationRouteRequest):
        packet_payload: object = request.fixed_implementation_packet
    else:
        packet_payload = request.get("fixed_implementation_packet")
    if isinstance(packet_payload, implementation_route.FixedImplementationPacket):
        packet_context: dict[str, object] = {
            key: value for key, value in asdict(packet_payload).items()
        }
    elif is_string_object_mapping(packet_payload):
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
                    dict(checkout_identity),
                ),
                *(
                    (
                        model_profile_registry.ContextItem(
                            "mathematical_intent_packet",
                            dict(normalized_math_packet),
                        ),
                    )
                    if normalized_math_packet is not None
                    else ()
                ),
                model_profile_registry.ContextItem(
                    "writer_target", parsed_writer_target.as_dict()
                ),
                model_profile_registry.ContextItem(
                    "writer_target_environment", parsed_writer_target.environment()
                ),
            ),
            objective=objective,
        ),
        registry,
    )
    if route_result.resume_worker_agent_id is not None:
        worker_agent_id = route_result.resume_worker_agent_id
        spawn_count = 0
        status = "continued"
    else:
        worker_agent_id = spawn("spark_worker", prompt.body)
        spawn_count = 1
        if not worker_agent_id:
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
