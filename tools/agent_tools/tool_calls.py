# @dependency-start
# contract tool
# responsibility AgentTeam tool calls owner module.
# upstream design ../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# upstream implementation ./update_lifecycle_contract.py owns gate and receipt validators.
# downstream implementation ./agent_team.py facade consumes ToolCall APIs.
# downstream implementation ./task_close.py consumes ToolCall APIs.
# @dependency-end
"""Own AgentTeam ToolCall materialization and close lifecycle receipts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

if __package__:
    from .artifact_identity import canonical_json_bytes
    from .writer_target import (
        WriterTarget,
        validate_mathematical_writer_target,
        validate_spawn_handoff,
    )
else:
    from artifact_identity import canonical_json_bytes
    from writer_target import (  # type: ignore[no-redef]
        WriterTarget,
        validate_mathematical_writer_target,
        validate_spawn_handoff,
    )

from update_lifecycle_contract import (
    materialize_close_agent_tool_call as materialize_lifecycle_close_agent_tool_call,
)
from update_lifecycle_contract import (
    materialize_gate_verdict,
    validate_cleanup_proof,
    validate_descendant_close_receipt,
    validate_durable_handback,
    validate_gate_chain,
    validate_record_binding,
    validate_reservation_release_receipt,
)

TOOL_CALL_SCHEMA = "agent-canon.tool-call.v1"

SKILL_TOOL_CALL_PHASES = (
    "required",
    "discovered",
    "conditional",
    "maintenance",
)

ROUTE_TOOL_CALL_ARGUMENT_SCHEMA = "agent-canon.route.args.v1"
SUBAGENT_SPAWN_TOOL_CALL_ARGUMENT_SCHEMA = "agent-canon.spawn-agent.args.v1"


def build_issue_receipt_stage_command(
    *,
    repository: str,
    runtime_root: str = "<runtime-root>",
    agentcanon_source_root: str = "<agentcanon-source-root>",
    target_root: str = "<target-root>",
    control_parent_root: str = "<control-parent-root>",
    checkout_identity: Mapping[str, object] | None = None,
    number: str = "<issue-number>",
    url: str = "<issue-url>",
    state: str = "<issue-state>",
    action: str = "<issue-action>",
    responsibility: Sequence[str] = (),
    occurrence_locations: Sequence[str] = (),
    source_finding_kind: str = "",
    execution: str = "run",
    bootstrap: str = "./bootstrap.sh",
    preflight: bool = False,
) -> tuple[str, ...]:
    """Build the canonical container command for post-publication staging."""
    if execution not in {"run", "exec"}:
        raise ValueError("receipt staging execution must be run or exec")
    if not repository.strip():
        raise ValueError("receipt staging repository is required")
    for value, field in (
        (agentcanon_source_root, "AgentCanon source root"),
        (target_root, "registered target root"),
    ):
        if value.startswith("<"):
            continue
        if not Path(value).expanduser().is_absolute():
            raise ValueError(f"receipt staging {field} must be absolute")
    if bootstrap == "./bootstrap.sh" and agentcanon_source_root != "<agentcanon-source-root>":
        bootstrap = str(
            Path(agentcanon_source_root).expanduser().resolve() / "bootstrap.sh"
        )
    if not Path(bootstrap).expanduser().is_absolute() and agentcanon_source_root != "<agentcanon-source-root>":
        raise ValueError("receipt staging bootstrap must be absolute")
    state_value = state.strip().casefold()
    if (
        state_value not in {"open", "closed"}
        and not state_value.startswith("<")
        and not preflight
    ):
        raise ValueError("receipt staging state must be open or closed")
    if (
        not preflight
        and action not in {"create", "update", "reopen", "reorganize", "noop"}
        and not action.startswith("<")
    ):
        raise ValueError("receipt staging action is invalid")
    command: list[str] = [
        bootstrap,
        "--control-parent-root",
        control_parent_root,
        "--runtime-root",
        runtime_root,
        "tool",
        execution,
        "--root",
        target_root,
        "issue-sync",
        "--",
        "--receipt-preflight" if preflight else "--stage-publication-receipt",
    ]
    if not preflight:
        command.extend(
            (
                "--repo",
                repository,
                "--receipt-number",
                number,
                "--receipt-url",
                url,
                "--receipt-state",
                state_value,
                "--receipt-action",
                action,
            )
        )
    identity = checkout_identity or {}
    checkout_head = str(identity.get("head") or "").strip()
    checkout_remote = str(identity.get("remote") or "").strip()
    if checkout_head:
        command.extend(("--checkout-head", checkout_head))
    if checkout_remote:
        command.extend(("--checkout-repository", checkout_remote))
    for value in responsibility:
        command.extend(("--receipt-responsibility", value))
    for value in occurrence_locations:
        command.extend(("--receipt-occurrence-location", value))
    if source_finding_kind:
        command.extend(("--receipt-source-finding-kind", source_finding_kind))
    return tuple(command)


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
    record["token_body_sha256"] = (
        "sha256:" + hashlib.sha256(canonical_json_bytes(record)).hexdigest()
    )
    return record


def materialize_skill_tool_call_token(
    skill: str, *, phase: str = "required"
) -> dict[str, object]:
    """Return the canonical, skill/phase-bound skill-command ToolCall identity."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill):
        raise RuntimeError("skill_tool_call_token invalid skill")
    if phase not in SKILL_TOOL_CALL_PHASES:
        raise RuntimeError("skill_tool_call_token invalid phase")
    token = materialize_tool_call_token(
        tool_id="skill-tool-commands",
        argument_schema_id=(f"agent-canon.skill-tool-commands.{skill}.{phase}.args.v1"),
        argument_properties={
            "skill": {"type": "string", "const": skill},
            "format": {"type": "string", "enum": ["json"]},
        },
        arguments={"skill": skill, "format": "json"},
        intent=(
            "Materialize the selected skill's canonical repository-tool packet "
            f"for its {phase} command phase."
        ),
        typed_failure_semantics=(
            {
                "code": f"skill_tool_route:{phase}:unknown_skill",
                "retryable": False,
                "next": "reject_route_packet",
            },
            {
                "code": f"skill_tool_route:{phase}:catalog_mismatch",
                "retryable": False,
                "next": "return_to_tool_catalog_owner",
            },
        ),
    )
    argument_schema = cast(Mapping[str, object], token["argument_schema"])
    token["identity"] = {
        "skill": skill,
        "phase": phase,
        "tool_id": token["tool_id"],
        "tool_call_token_id": token["token_id"],
        "tool_call_digest": token["token_body_sha256"],
        "argument_schema_id": argument_schema["$id"],
        "argument_schema_digest": "sha256:"
        + hashlib.sha256(canonical_json_bytes(argument_schema)).hexdigest(),
    }
    return token


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


def materialize_issue_worker_tool_call(
    *,
    handoff: Mapping[str, object],
    publisher_agent_id: str,
    checkout_repository: str,
    checkout_identity: Mapping[str, object] | None = None,
    runtime_root: str = "<runtime-root>",
    agentcanon_source_root: str = "<agentcanon-source-root>",
    target_root: str = "<target-root>",
    control_parent_root: str = "<control-parent-root>",
    publication_mode: str = "publish",
    publication_reason: str = "",
) -> dict[str, object]:
    """Return a host-publisher ToolCall for one typed IssueWorker handoff."""
    if not publisher_agent_id.strip() or not checkout_repository.strip():
        raise RuntimeError(
            "issue_worker_tool_call publisher agent and checkout repository are required"
        )
    if publication_mode not in {"publish", "investigate_only"}:
        raise RuntimeError("issue_worker_tool_call publication mode is invalid")
    identity = checkout_identity or {}
    identity_remote = str(identity.get("remote") or "").strip().casefold()
    handoff_repository = str(handoff.get("repository") or "").strip().casefold()
    checkout_repository_value = checkout_repository.strip().casefold()
    if identity_remote and identity_remote != checkout_repository_value:
        raise RuntimeError("issue_worker_tool_call:checkout_repository_mismatch")
    if handoff_repository and handoff_repository != checkout_repository_value:
        raise RuntimeError("issue_worker_tool_call:handoff_repository_mismatch")
    identity_target_root = str(identity.get("git_root") or "").strip()
    if identity_target_root in {"", "unknown"}:
        if target_root != "<target-root>" and publication_mode == "publish":
            raise RuntimeError("issue_worker_tool_call:target_root_unresolved")
    elif not Path(identity_target_root).expanduser().is_absolute():
        raise RuntimeError("issue_worker_tool_call:target_root_not_absolute")
    else:
        identity_target_root = str(Path(identity_target_root).expanduser().resolve())
        if target_root == "<target-root>":
            target_root = identity_target_root
        elif str(Path(target_root).expanduser().resolve()) != identity_target_root:
            raise RuntimeError("issue_worker_tool_call:target_root_mismatch")
    if target_root != "<target-root>":
        target_path = Path(target_root).expanduser().resolve(strict=False)
        if not target_path.is_dir():
            raise RuntimeError("issue_worker_tool_call:target_root_missing")
        target_root = str(target_path)
    bootstrap = "./bootstrap.sh"
    if agentcanon_source_root != "<agentcanon-source-root>":
        source_path = Path(agentcanon_source_root).expanduser().resolve()
        if not source_path.is_absolute():
            raise RuntimeError("issue_worker_tool_call:agentcanon_source_root_not_absolute")
        agentcanon_source_root = str(source_path)
        bootstrap_path = source_path / "bootstrap.sh"
        if not bootstrap_path.is_file():
            raise RuntimeError("issue_worker_tool_call:bootstrap_missing")
        bootstrap = str(bootstrap_path)
    preflight_command = build_issue_receipt_stage_command(
        repository=checkout_repository,
        runtime_root=runtime_root,
        agentcanon_source_root=agentcanon_source_root,
        target_root=target_root,
        control_parent_root=control_parent_root,
        checkout_identity=checkout_identity,
        bootstrap=bootstrap,
        preflight=True,
    )
    stage_command = build_issue_receipt_stage_command(
        repository=checkout_repository,
        runtime_root=runtime_root,
        agentcanon_source_root=agentcanon_source_root,
        target_root=target_root,
        control_parent_root=control_parent_root,
        checkout_identity=checkout_identity,
        bootstrap=bootstrap,
    )
    if publication_mode == "investigate_only":
        preflight_command = ()
        stage_command = ()
    return materialize_tool_call_token(
        tool_id="issue-worker",
        argument_schema_id="agent-canon.issue-worker.args.v1",
        argument_properties={
            "publisher_agent_id": {"type": "string", "minLength": 1},
            "checkout_repository": {"type": "string", "minLength": 1},
            "agentcanon_source_root": {"type": "string", "minLength": 1},
            "target_root": {"type": "string", "minLength": 1},
            "handoff": {"type": "object"},
            "publication_mode": {
                "type": "string",
                "enum": ["publish", "investigate_only"],
            },
            "publication_reason": {"type": "string"},
            "receipt_preflight_command": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "receipt_stage_command": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
        },
        arguments={
            "publisher_agent_id": publisher_agent_id,
            "checkout_repository": checkout_repository,
            "agentcanon_source_root": agentcanon_source_root,
            "target_root": target_root,
            "handoff": dict(handoff),
            "publication_mode": publication_mode,
            "publication_reason": publication_reason,
            "receipt_preflight_command": list(preflight_command),
            "receipt_stage_command": list(stage_command),
        },
        intent=(
            "Run IssueWorker plan and publication through the host publisher; "
            "execute receipt_preflight_command successfully before any GitHub "
            "mutation, read back URL, number, body, and state, then execute "
            "receipt_stage_command before pending packet consumption."
        ),
        typed_failure_semantics=(
            {
                "code": "issue_worker:publication_unavailable",
                "retryable": True,
                "next": "write_pending_packet_and_retry_issue_worker",
            },
            {
                "code": "issue_worker:readback_failed",
                "retryable": True,
                "next": "retain_packet_and_retry_issue_worker",
            },
        ),
    )


def materialize_subagent_spawn_tool_call(
    *,
    role: str,
    agent_type: str,
    input: str,
    checkout_identity: Mapping[str, object],
    workspace_write_capable: bool | None = None,
    writer_target: WriterTarget | Mapping[str, object] | None = None,
    math_intent_route: Mapping[str, object] | None = None,
    math_intent_packet: Mapping[str, object] | object | None = None,
) -> dict[str, object]:
    """Return the parent-runtime ToolCall for one stage-owner spawn handoff."""
    if not role.strip() or not agent_type.strip() or not input.strip():
        raise RuntimeError(
            "subagent_spawn_tool_call role, agent type, and input are required"
        )
    identity = dict(checkout_identity)
    if not identity:
        raise RuntimeError("subagent_spawn_tool_call checkout identity is required")
    workspace_write_capable = (
        role != "publisher"
        if workspace_write_capable is None
        else workspace_write_capable
    )
    normalized_math_packet = None
    if __package__:
        from .packets import (
            mathematical_intent_packet_mapping,
            normalize_mathematical_intent_packet,
            validate_mathematical_intent_route,
        )
    else:
        from packets import (  # type: ignore[no-redef]
            mathematical_intent_packet_mapping,
            normalize_mathematical_intent_packet,
            validate_mathematical_intent_route,
        )
    selected_math_route = validate_mathematical_intent_route(math_intent_route)
    if selected_math_route is not None:
        if math_intent_packet is None:
            raise RuntimeError("math_packet_missing")
        normalized_math_packet = mathematical_intent_packet_mapping(
            normalize_mathematical_intent_packet(math_intent_packet)
        )
    elif math_intent_packet is not None:
        raise RuntimeError("math_packet_not_applicable")
    targets = validate_spawn_handoff(
        role,
        workspace_write_capable=workspace_write_capable,
        writer_target=writer_target,
        checkout_identity=identity,
    )
    if selected_math_route is not None and targets:
        validate_mathematical_writer_target(targets[0], normalized_math_packet)
    argument_properties: dict[str, Mapping[str, object]] = {
        "role": {"type": "string", "minLength": 1},
        "agent_type": {"type": "string", "minLength": 1},
        "input": {"type": "string", "minLength": 1},
        "checkout_identity": {"type": "object"},
    }
    arguments: dict[str, object] = {
        "role": role,
        "agent_type": agent_type,
        "input": input,
        "checkout_identity": identity,
    }
    if targets:
        arguments["writer_target"] = targets[0].as_dict()
        argument_properties["writer_target"] = {"type": "object"}
    if normalized_math_packet is not None:
        arguments["mathematical_intent_packet"] = normalized_math_packet
        argument_properties["mathematical_intent_packet"] = {"type": "object"}
    return materialize_tool_call_token(
        tool_id="spawn_agent",
        argument_schema_id=SUBAGENT_SPAWN_TOOL_CALL_ARGUMENT_SCHEMA,
        argument_properties=argument_properties,
        arguments=arguments,
        intent=(
            "Ask the parent runtime to use the canonical AgentTeam dispatch route "
            "and writer-target validator for the selected stage owner; raw "
            "spawn_agent is not an admission path."
        ),
        typed_failure_semantics=(
            {
                "code": "spawn_agent:authorization_required",
                "retryable": True,
                "next": "retain_handoff_until_parent_runtime_authorizes_spawn",
            },
            {
                "code": "spawn_agent:launch_failed",
                "retryable": True,
                "next": "retain_handoff_and_retry_parent_runtime_spawn",
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
    observed_reservations = {cast(str, item["reservation_id"]) for item in reservations}
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
    expected_identity = tuple(
        checked_binding[field] for field in binding_identity_fields
    )
    handback_binding = cast(Mapping[str, object], handback["binding"])
    if handback_binding != checked_binding:
        raise ValueError("close_agent:identity_mismatch")
    if handback["agent_id"] != agent_id:
        raise ValueError("close_agent:agent_identity_mismatch")
    for item in [*descendants, *reservations]:
        item_binding = cast(Mapping[str, object], item["binding"])
        if (
            tuple(item_binding[field] for field in binding_identity_fields)
            != expected_identity
        ):
            raise ValueError("close_agent:identity_mismatch")
        if item["durable_handback_evidence_ref"] != handback["evidence_ref"]:
            raise ValueError("close_agent:durable_handback_mismatch")
    descendants_closed_evidence_ref = (
        "evidence:" + hashlib.sha256(canonical_json_bytes(descendants)).hexdigest()
    )
    reservations_released_evidence_ref = (
        "evidence:" + hashlib.sha256(canonical_json_bytes(reservations)).hexdigest()
    )
    cleanup = validate_cleanup_proof(evidence.cleanup_proof)
    cleanup_binding = cast(Mapping[str, object], cleanup["binding"])
    if (
        tuple(cleanup_binding[field] for field in binding_identity_fields)
        != expected_identity
    ):
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
