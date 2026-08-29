# @dependency-start
# contract tool
# responsibility AgentTeam packets owner module.
# upstream design ../../documents/design/agent-team-module-boundaries.md RC-01..RC-08 approved module boundary.
# downstream implementation ./agent_team.py facade consumes packet APIs.
# downstream implementation ./bootstrap_agent_run.py consumes packet APIs.
# downstream implementation ./waterfall_gate_check.py consumes packet APIs.
# @dependency-end
"""Own AgentTeam packet identity, normalization, and document references."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast

if __package__:
    from tools.runtime.artifacts.artifact_identity import canonical_json_bytes
else:
    from tools.runtime.artifacts.artifact_identity import canonical_json_bytes


if __package__:
    from .team_config import (
        Role,
        RunBundleSpec,
        TaskCatalog,
        TeamConfig,
        _as_object_mapping,
        _as_required_string,
        _as_string_tuple,
    )
else:
    from tools.agent.orchestration.team_config import (
        Role,
        RunBundleSpec,
        TaskCatalog,
        TeamConfig,
        _as_object_mapping,
        _as_required_string,
        _as_string_tuple,
    )

if __package__:
    from tools.repository.workspace.workspace_scope import (
        resolve_report_bundle_artifact_path,
        resolve_workspace_document_path,
    )
else:
    from tools.repository.workspace.workspace_scope import (
        resolve_report_bundle_artifact_path,
        resolve_workspace_document_path,
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
    "mathematical_correctness_reviewer": {
        "artifact_keys": ["user_request_contract", "schedule", "change_review"],
        "workspace_paths": [
            "agents/skills/computational-optimization.md",
            "agents/skills/agent-orchestration.md",
        ],
        "notes": (
            "Math-intent review reads the normalized packet and its mapped scope; it does not "
            "authorize non-mathematical infrastructure edits."
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
    "documents/agent-canon/agent-canon-update-route.md",
    "documents/notes/guardrails/README.md",
    "documents/notes/guardrails/engineering_avoidances.md",
)

OPTIONAL_CROSS_CUTTING_DOCUMENT_PATHS: tuple[str, ...] = ("docker/README.md",)


MATHEMATICAL_INTENT_PACKET_SCHEMA = "agent-canon.mathematical-intent.v1"
MATHEMATICAL_INTENT_ROUTE_ID = "mathematical_correction"
MATHEMATICAL_INTENT_OWNER_SKILLS = frozenset(
    {
        "computational-optimization",
    }
)
MATHEMATICAL_INTENT_PACKET_TEXT_FIELDS = (
    "math_object",
    "problem",
    "variables",
    "domains",
    "units",
    "objective",
    "residual",
    "constraints",
    "equations",
    "definitions",
    "assumptions",
    "approximations",
    "derivation",
    "iteration_map",
    "update_map",
    "invariants",
    "limits",
    "stopping_scalar",
    "failure_semantics",
    "math_oracle",
    "counterexample",
)
MATHEMATICAL_INTENT_PACKET_FIELDS = frozenset(
    {
        "schema",
        *MATHEMATICAL_INTENT_PACKET_TEXT_FIELDS,
        "equation_to_code_map",
        "mathematical_definition_paths",
        "mathematical_oracle_paths",
        "mathematical_documentation_paths",
        "allowed_write_paths",
        "forbidden_surfaces",
        "separate_handoff_targets",
    }
)
MATHEMATICAL_INTENT_MAP_FIELDS = frozenset(
    {"equation", "code_path", "symbol_or_call_path"}
)
@dataclass(frozen=True)
class MathematicalIntentPacket:
    """Closed math-intent source packet for one mathematical route."""

    schema: str
    math_object: str
    problem: str
    variables: str
    domains: str
    units: str
    objective: str
    residual: str
    constraints: str
    equations: str
    definitions: str
    assumptions: str
    approximations: str
    derivation: str
    iteration_map: str
    update_map: str
    invariants: str
    limits: str
    stopping_scalar: str
    failure_semantics: str
    equation_to_code_map: tuple[Mapping[str, str], ...]
    mathematical_definition_paths: tuple[str, ...]
    mathematical_oracle_paths: tuple[str, ...]
    mathematical_documentation_paths: tuple[str, ...]
    math_oracle: str
    counterexample: str
    allowed_write_paths: tuple[str, ...]
    forbidden_surfaces: tuple[str, ...]
    separate_handoff_targets: tuple[str, ...]


def _math_packet_relative_paths(value: object, field: str, *, allow_empty: bool) -> tuple[str, ...]:
    """Validate canonical relative paths carried by a math packet."""
    if not isinstance(value, (list, tuple)) or (not allow_empty and not value):
        raise RuntimeError(f"mathematical_intent_packet.{field}:list_required")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(f"mathematical_intent_packet.{field}[{index}]:required")
        path = item.strip()
        parsed = PurePosixPath(path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or path.startswith("./")
            or "\\" in path
            or "//" in path
        ):
            raise RuntimeError(
                f"mathematical_intent_packet.{field}[{index}]:path_not_relative"
            )
        result.append(path)
    if len(result) != len(set(result)):
        raise RuntimeError(f"mathematical_intent_packet.{field}:duplicate")
    return tuple(result)


def _math_packet_strings(value: object, field: str, *, allow_empty: bool) -> tuple[str, ...]:
    """Validate a non-empty list of labels or handoff references."""
    if not isinstance(value, (list, tuple)) or (not allow_empty and not value):
        raise RuntimeError(f"mathematical_intent_packet.{field}:list_required")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(f"mathematical_intent_packet.{field}[{index}]:required")
        result.append(item.strip())
    if len(result) != len(set(result)):
        raise RuntimeError(f"mathematical_intent_packet.{field}:duplicate")
    return tuple(result)


def _math_packet_map(value: object) -> tuple[Mapping[str, str], ...]:
    """Validate the equation-to-code correspondence rows."""
    if not isinstance(value, list) or not value:
        raise RuntimeError("mathematical_intent_packet.equation_to_code_map:list_required")
    rows: list[Mapping[str, str]] = []
    for index, raw_row in enumerate(value):
        if not isinstance(raw_row, Mapping):
            raise RuntimeError(
                f"mathematical_intent_packet.equation_to_code_map[{index}]:mapping_required"
            )
        unknown = sorted(set(raw_row).difference(MATHEMATICAL_INTENT_MAP_FIELDS))
        missing = sorted(MATHEMATICAL_INTENT_MAP_FIELDS.difference(raw_row))
        if unknown:
            raise RuntimeError(
                "mathematical_intent_packet.equation_to_code_map"
                f"[{index}]:field_unknown:{','.join(unknown)}"
            )
        if missing:
            raise RuntimeError(
                "mathematical_intent_packet.equation_to_code_map"
                f"[{index}]:field_missing:{','.join(missing)}"
            )
        normalized = {
            field: _packet_text(raw_row, field, f"mathematical_intent_packet.equation_to_code_map[{index}]")
            for field in MATHEMATICAL_INTENT_MAP_FIELDS
        }
        rows.append(normalized)
    return tuple(rows)


def normalize_mathematical_intent_packet(
    raw_packet: object,
    field_prefix: str = "mathematical_intent_packet",
) -> MathematicalIntentPacket:
    """Normalize one math packet and fail closed on incomplete correspondence."""
    if not isinstance(raw_packet, Mapping):
        raise RuntimeError(f"{field_prefix}:mapping_required")
    unknown = sorted(set(raw_packet).difference(MATHEMATICAL_INTENT_PACKET_FIELDS))
    missing = sorted(MATHEMATICAL_INTENT_PACKET_FIELDS.difference(raw_packet))
    if unknown:
        raise RuntimeError(f"{field_prefix}:field_unknown:{','.join(unknown)}")
    if missing:
        raise RuntimeError(f"{field_prefix}:field_missing:{','.join(missing)}")
    if raw_packet["schema"] != MATHEMATICAL_INTENT_PACKET_SCHEMA:
        raise RuntimeError(f"{field_prefix}.schema:mismatch")
    texts = {
        field: _packet_text(raw_packet, field, field_prefix)
        for field in MATHEMATICAL_INTENT_PACKET_TEXT_FIELDS
    }
    equation_map = _math_packet_map(raw_packet["equation_to_code_map"])
    definition_paths = _math_packet_relative_paths(
        raw_packet["mathematical_definition_paths"],
        "mathematical_definition_paths",
        allow_empty=True,
    )
    oracle_paths = _math_packet_relative_paths(
        raw_packet["mathematical_oracle_paths"],
        "mathematical_oracle_paths",
        allow_empty=True,
    )
    documentation_paths = _math_packet_relative_paths(
        raw_packet["mathematical_documentation_paths"],
        "mathematical_documentation_paths",
        allow_empty=True,
    )
    allowed_paths = _math_packet_relative_paths(
        raw_packet["allowed_write_paths"], "allowed_write_paths", allow_empty=False
    )
    forbidden_surfaces = _math_packet_strings(
        raw_packet["forbidden_surfaces"], "forbidden_surfaces", allow_empty=False
    )
    separate_targets = _math_packet_strings(
        raw_packet["separate_handoff_targets"],
        "separate_handoff_targets",
        allow_empty=True,
    )
    code_paths = tuple(row["code_path"] for row in equation_map)
    expected_paths = set(
        (*definition_paths, *oracle_paths, *documentation_paths, *code_paths)
    )
    if set(allowed_paths) != expected_paths:
        extra = sorted(set(allowed_paths).difference(expected_paths))
        missing_paths = sorted(expected_paths.difference(allowed_paths))
        details = []
        if extra:
            details.append("extra=" + ",".join(extra))
        if missing_paths:
            details.append("missing=" + ",".join(missing_paths))
        raise RuntimeError(
            "mathematical_intent_packet.allowed_write_paths:union_mismatch:"
            + ";".join(details)
        )
    return MathematicalIntentPacket(
        schema=str(raw_packet["schema"]),
        equation_to_code_map=equation_map,
        mathematical_definition_paths=definition_paths,
        mathematical_oracle_paths=oracle_paths,
        mathematical_documentation_paths=documentation_paths,
        allowed_write_paths=allowed_paths,
        forbidden_surfaces=forbidden_surfaces,
        separate_handoff_targets=separate_targets,
        **texts,
    )


def mathematical_intent_packet_mapping(
    packet: MathematicalIntentPacket,
) -> dict[str, object]:
    """Serialize a normalized math packet for run manifests and spawn prompts."""
    return {
        "schema": packet.schema,
        **{field: getattr(packet, field) for field in MATHEMATICAL_INTENT_PACKET_TEXT_FIELDS},
        "equation_to_code_map": [dict(row) for row in packet.equation_to_code_map],
        "mathematical_definition_paths": list(packet.mathematical_definition_paths),
        "mathematical_oracle_paths": list(packet.mathematical_oracle_paths),
        "mathematical_documentation_paths": list(packet.mathematical_documentation_paths),
        "allowed_write_paths": list(packet.allowed_write_paths),
        "forbidden_surfaces": list(packet.forbidden_surfaces),
        "separate_handoff_targets": list(packet.separate_handoff_targets),
    }


def separate_nonmath_handoff_mapping(
    packet: MathematicalIntentPacket | Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    """Materialize deferred parent-owned handoffs without creating writer paths."""
    targets = (
        packet.separate_handoff_targets
        if isinstance(packet, MathematicalIntentPacket)
        else tuple(str(item) for item in packet.get("separate_handoff_targets", ()))
    )
    return tuple(
        {
            "target": target,
            "owner": "parent",
            "status": "deferred",
            "writer_tool_call": "none",
            "math_writer_paths": [],
        }
        for target in targets
    )


def mathematical_intent_route_for_task(
    catalog: TaskCatalog | None,
    task_id: str | None,
    selected_skills: Sequence[str] = (),
) -> str | None:
    """Return the task-declared math route only when its skill is selected."""
    if catalog is None or not task_id:
        return None
    task = next((item for item in catalog.tasks if item.get("id") == task_id), None)
    if task is None:
        return None
    normalized_skills = {str(skill).removeprefix("$") for skill in selected_skills}
    route_id = task.get("math_intent_route")
    if route_id is None and not normalized_skills.intersection(
        MATHEMATICAL_INTENT_OWNER_SKILLS
    ):
        return None
    if route_id is None:
        route_id = MATHEMATICAL_INTENT_ROUTE_ID
    if MATHEMATICAL_INTENT_ROUTE_ID not in {
        str(item.get("id"))
        for item in _math_intent_route_records(catalog)
    }:
        raise RuntimeError("mathematical_intent_route:canonical_id_missing")
    if not isinstance(route_id, str) or route_id != MATHEMATICAL_INTENT_ROUTE_ID:
        raise RuntimeError(f"mathematical_intent_route:unknown_id:{route_id}")
    route = mathematical_intent_route_config(catalog, route_id)
    if route is None:
        raise RuntimeError("mathematical_intent_route:catalog_record_missing")
    if str(route.get("owner_skill")) not in normalized_skills:
        return None
    return route_id


def math_intent_route_id_from_context(
    selected_skills: Sequence[str] = (),
    role_ids: Sequence[str] = (),
    *,
    packet_present: bool = False,
    explicit_route_id: str | None = None,
) -> str | None:
    """Derive math routing from explicit route, selected math owner, or packet."""
    if explicit_route_id is not None:
        return validate_mathematical_intent_route(explicit_route_id)
    normalized_skills = {str(skill).removeprefix("$") for skill in selected_skills}
    if packet_present or normalized_skills.intersection(MATHEMATICAL_INTENT_OWNER_SKILLS):
        return MATHEMATICAL_INTENT_ROUTE_ID
    return None


def _math_intent_route_records(catalog: TaskCatalog) -> tuple[Mapping[str, object], ...]:
    """Return the canonical task-catalog math route records."""
    raw_routes = catalog.raw.get("math_intent_routes")
    if not isinstance(raw_routes, Mapping):
        raise RuntimeError("mathematical_intent_route:catalog_records_missing")
    records: list[Mapping[str, object]] = []
    for route_id, raw_record in raw_routes.items():
        if not isinstance(raw_record, Mapping):
            raise RuntimeError(f"mathematical_intent_route:record_invalid:{route_id}")
        record = dict(raw_record)
        record.setdefault("id", route_id)
        records.append(record)
    return tuple(records)


def mathematical_intent_route_config(
    catalog: TaskCatalog | None,
    route_id: str | None,
) -> Mapping[str, object] | None:
    """Resolve one canonical math route ID from the task catalog."""
    if route_id is None:
        return None
    validate_mathematical_intent_route(route_id)
    if catalog is None:
        raise RuntimeError("mathematical_intent_route:catalog_required")
    records = _math_intent_route_records(catalog)
    for record in records:
        if record.get("id") == route_id:
            expected = {
                "id": MATHEMATICAL_INTENT_ROUTE_ID,
                "requires_math_intent": True,
                "activation": "mathematical_or_numerical_correction_evidence",
                "owner_skill": "computational-optimization",
                "reviewer": "mathematical_correctness_reviewer",
                "required_packet": "mathematical_intent_packet",
                "precedes": ["design", "benchmark_reviewer"],
            }
            if dict(record) != expected:
                raise RuntimeError("mathematical_intent_route:canonical_record_mismatch")
            return record
    raise RuntimeError(f"mathematical_intent_route:unknown_id:{route_id}")


def validate_mathematical_intent_route(
    route_id: str | None,
) -> str | None:
    """Validate the selected task/workflow route that makes math mandatory."""
    if route_id is None:
        return None
    if not isinstance(route_id, str) or route_id != MATHEMATICAL_INTENT_ROUTE_ID:
        raise RuntimeError(f"mathematical_intent_route:unknown_id:{route_id}")
    return route_id


def resolve_math_intent_packet_for_spec(
    spec: RunBundleSpec,
) -> MathematicalIntentPacket | None:
    """Validate the route/packet pair before manifest creation or spawn."""
    raw_packet = spec.math_intent_packet
    selected_route_id = math_intent_route_id_from_context(
        spec.selected_skills,
        tuple(role.id for role in spec.roles),
        packet_present=raw_packet is not None,
        explicit_route_id=spec.math_intent_route,
    )
    if selected_route_id is None:
        if raw_packet is not None:
            raise RuntimeError("math_packet_not_applicable")
        return None
    mathematical_intent_route_config(spec.task_catalog, selected_route_id)
    if raw_packet is None:
        raise RuntimeError("math_packet_missing")
    if isinstance(raw_packet, MathematicalIntentPacket):
        return raw_packet
    return normalize_mathematical_intent_packet(raw_packet)


def math_intent_route_id_for_spec(spec: RunBundleSpec) -> str | None:
    """Return the same canonical route used by run and spawn admission."""
    return math_intent_route_id_from_context(
        spec.selected_skills,
        tuple(role.id for role in spec.roles),
        packet_present=spec.math_intent_packet is not None,
        explicit_route_id=spec.math_intent_route,
    )


# These packet helpers deliberately remain stateless.  A receipt is addressed by
# the existing candidate/property/owner/plane/input tuple; no registry, counter,
# timestamp, or generated packet ID is introduced here.
OWNER_GUARANTEE_PACKET_SCHEMA = "agent-canon.owner-guarantee.v1"
OWNER_GUARANTEE_PACKET_FIELDS = frozenset(
    {
        "schema",
        "owner_ref",
        "candidate_digest",
        "property_ref",
        "mechanism_ref",
        "mechanism_transition",
        "mechanism_sufficiency",
        "not_guaranteed",
        "failure_semantics",
        "execution_plane",
        "tool_input_locator",
        "primary_observation_ref",
        "observation_outcome",
        "correspondence_state",
        "invalidation_inputs",
        "downstream_edges",
        "source_snapshot",
        "authority_ref",
    }
)
OWNER_OBSERVATION_OUTCOMES = frozenset(
    {"observed_pass", "observed_fail", "inconclusive", "not_applicable"}
)
OWNER_CORRESPONDENCE_STATES = frozenset(
    {"unmapped", "mapped", "observer_assigned", "verified", "unresolved", "refuted", "advisory"}
)
OWNER_INVALIDATION_PACKET_SCHEMA = "agent-canon.owner-invalidation.v1"
OWNER_INVALIDATION_PACKET_FIELDS = frozenset(
    {
        "schema",
        "from_owner",
        "to_owner",
        "candidate_digest",
        "changed_mechanism_ref",
        "invalidated_property_ref",
        "invalidated_receipt_ref",
        "reason",
        "affected_edge",
        "owner_action",
    }
)
OWNER_INVALIDATION_REASONS = frozenset(
    {"mechanism_changed", "effect_closure_changed", "input_changed", "source_snapshot_changed"}
)


def _packet_text(raw: Mapping[str, object], field: str, prefix: str) -> str:
    """Read one required packet text field without inventing defaults."""
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{prefix}.{field}:required")
    return value.strip()


def _packet_text_list(raw: Mapping[str, object], field: str, prefix: str, *, allow_empty: bool) -> tuple[str, ...]:
    """Read a bounded list of non-empty packet references."""
    value = raw.get(field)
    if not isinstance(value, list) or (not allow_empty and not value):
        raise RuntimeError(f"{prefix}.{field}:list_required")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(f"{prefix}.{field}[{index}]:required")
        normalized.append(item.strip())
    return tuple(normalized)


def normalize_owner_guarantee_packet(
    raw_packet: object,
    field_prefix: str = "owner_guarantee",
) -> dict[str, object]:
    """Normalize one owner-local guarantee/receipt packet.

    This validates packet shape and local correspondence state only.  It does
    not decide whether the authority is valid, whether the mechanism is
    sufficient, or whether a repository may be published.
    """
    if not isinstance(raw_packet, Mapping):
        raise RuntimeError(f"{field_prefix}:mapping_required")
    unknown = sorted(set(raw_packet).difference(OWNER_GUARANTEE_PACKET_FIELDS))
    missing = sorted(OWNER_GUARANTEE_PACKET_FIELDS.difference(raw_packet))
    if unknown:
        raise RuntimeError(f"{field_prefix}:field_unknown:{','.join(unknown)}")
    if missing:
        raise RuntimeError(f"{field_prefix}:field_missing:{','.join(missing)}")
    schema = _packet_text(raw_packet, "schema", field_prefix)
    if schema != OWNER_GUARANTEE_PACKET_SCHEMA:
        raise RuntimeError(f"{field_prefix}.schema:unknown:{schema}")
    observation_outcome = _packet_text(raw_packet, "observation_outcome", field_prefix)
    if observation_outcome not in OWNER_OBSERVATION_OUTCOMES:
        raise RuntimeError(f"{field_prefix}.observation_outcome:invalid")
    correspondence_state = _packet_text(raw_packet, "correspondence_state", field_prefix)
    if correspondence_state not in OWNER_CORRESPONDENCE_STATES:
        raise RuntimeError(f"{field_prefix}.correspondence_state:invalid")
    normalized: dict[str, object] = {
        "schema": schema,
        **{
            field: _packet_text(raw_packet, field, field_prefix)
            for field in (
                "owner_ref",
                "candidate_digest",
                "property_ref",
                "mechanism_ref",
                "mechanism_transition",
                "mechanism_sufficiency",
                "failure_semantics",
                "execution_plane",
                "tool_input_locator",
                "primary_observation_ref",
                "source_snapshot",
                "authority_ref",
            )
        },
        "not_guaranteed": list(
            _packet_text_list(raw_packet, "not_guaranteed", field_prefix, allow_empty=False)
        ),
        "invalidation_inputs": list(
            _packet_text_list(raw_packet, "invalidation_inputs", field_prefix, allow_empty=False)
        ),
        "downstream_edges": list(
            _packet_text_list(raw_packet, "downstream_edges", field_prefix, allow_empty=True)
        ),
        "observation_outcome": observation_outcome,
        "correspondence_state": correspondence_state,
    }
    if "candidate_digest" not in normalized["invalidation_inputs"]:
        raise RuntimeError(f"{field_prefix}.invalidation_inputs:candidate_digest_missing")
    return normalized


def owner_receipt_key(packet: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    """Return the existing lookup tuple used for receipt reuse/deduplication."""
    normalized = normalize_owner_guarantee_packet(packet)
    return tuple(
        str(normalized[field])
        for field in (
            "candidate_digest",
            "property_ref",
            "owner_ref",
            "execution_plane",
            "tool_input_locator",
        )
    )  # type: ignore[return-value]


def owner_receipt_is_compatible(
    packet: Mapping[str, object],
    *,
    candidate_digest: str | None = None,
    property_ref: str | None = None,
    owner_ref: str | None = None,
    execution_plane: str | None = None,
    tool_input_locator: str | None = None,
    mechanism_ref: str | None = None,
) -> bool:
    """Return whether one verified local receipt matches requested identity."""
    normalized = normalize_owner_guarantee_packet(packet)
    if normalized["correspondence_state"] != "verified":
        return False
    if normalized["observation_outcome"] != "observed_pass":
        return False
    for field, expected in (
        ("candidate_digest", candidate_digest),
        ("property_ref", property_ref),
        ("owner_ref", owner_ref),
        ("execution_plane", execution_plane),
        ("tool_input_locator", tool_input_locator),
        ("mechanism_ref", mechanism_ref),
    ):
        if expected is not None and normalized[field] != expected:
            return False
    return True


def normalize_owner_invalidation_packet(
    raw_packet: object,
    field_prefix: str = "owner_invalidation",
) -> dict[str, object]:
    """Normalize one bounded existing-DAG invalidation packet."""
    if not isinstance(raw_packet, Mapping):
        raise RuntimeError(f"{field_prefix}:mapping_required")
    unknown = sorted(set(raw_packet).difference(OWNER_INVALIDATION_PACKET_FIELDS))
    missing = sorted(OWNER_INVALIDATION_PACKET_FIELDS.difference(raw_packet))
    if unknown:
        raise RuntimeError(f"{field_prefix}:field_unknown:{','.join(unknown)}")
    if missing:
        raise RuntimeError(f"{field_prefix}:field_missing:{','.join(missing)}")
    normalized = {
        "schema": _packet_text(raw_packet, "schema", field_prefix),
        **{
            field: _packet_text(raw_packet, field, field_prefix)
            for field in (
                "from_owner",
                "to_owner",
                "candidate_digest",
                "changed_mechanism_ref",
                "invalidated_property_ref",
                "invalidated_receipt_ref",
                "reason",
                "affected_edge",
                "owner_action",
            )
        },
    }
    if normalized["schema"] != OWNER_INVALIDATION_PACKET_SCHEMA:
        raise RuntimeError(f"{field_prefix}.schema:unknown:{normalized['schema']}")
    if normalized["reason"] not in OWNER_INVALIDATION_REASONS:
        raise RuntimeError(f"{field_prefix}.reason:invalid")
    if normalized["owner_action"] != "reevaluate_local_correspondence":
        raise RuntimeError(f"{field_prefix}.owner_action:invalid")
    return normalized


def owner_receipt_is_invalidated(
    packet: Mapping[str, object],
    invalidation: Mapping[str, object],
) -> bool:
    """Return whether an existing-edge invalidation reaches one receipt."""
    receipt = normalize_owner_guarantee_packet(packet)
    event = normalize_owner_invalidation_packet(invalidation)
    if receipt["candidate_digest"] != event["candidate_digest"]:
        return False
    if event["invalidated_receipt_ref"] == receipt["primary_observation_ref"]:
        return True
    return (
        event["to_owner"] == receipt["owner_ref"]
        and event["invalidated_property_ref"] == receipt["property_ref"]
    )


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
    agentcanon_source_root: Path | None = None,
) -> tuple[DocumentPacketEntry, ...]:
    """Resolve the common cross-cutting document packet for one workspace."""
    if agentcanon_source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    required_entries = tuple(
        DocumentPacketEntry(
            path=resolve_workspace_document_path(
                workspace_root,
                relative_path,
                root_key="agentcanon",
                agentcanon_source_root=agentcanon_source_root,
            ),
            rationale=f"cross_cutting_doc:{relative_path}",
        )
        for relative_path in COMMON_CROSS_CUTTING_DOCUMENT_PATHS
    )
    optional_entries = tuple(
        DocumentPacketEntry(
            path=resolve_workspace_document_path(
                workspace_root,
                relative_path,
                root_key="agentcanon",
                agentcanon_source_root=agentcanon_source_root,
            ),
            rationale=f"cross_cutting_doc:{relative_path}",
        )
        for relative_path in OPTIONAL_CROSS_CUTTING_DOCUMENT_PATHS
        if resolve_workspace_document_path(
            workspace_root,
            relative_path,
            root_key="agentcanon",
            agentcanon_source_root=agentcanon_source_root,
        ).exists()
    )
    return required_entries + optional_entries


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
    "source_refs": ("workspace:", "agentcanon:", "artifact:"),
    "dependency_refs": ("entry:", "header:"),
    "output_refs": ("artifact:",),
    "reviewer_refs": ("role:",),
}

_LOCATOR_SEGMENT = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
_LOCATOR_RE = re.compile(
    rf"(?P<root>workspace|agentcanon|artifact):(?P<path>{_LOCATOR_SEGMENT}(?:/{_LOCATOR_SEGMENT})*)"
    rf"(?P<fragment>#(?:section|symbol):{_LOCATOR_SEGMENT})?"
)
_HEADER_RE = re.compile(
    rf"header:(?P<direction>{_LOCATOR_SEGMENT}):(?P<kind>{_LOCATOR_SEGMENT}):"
    rf"(?P<source>(?:workspace|agentcanon|artifact):{_LOCATOR_SEGMENT}(?:/{_LOCATOR_SEGMENT})*(?:#(?:section|symbol):{_LOCATOR_SEGMENT})?)"
    rf"->(?P<target>(?:workspace|agentcanon|artifact):{_LOCATOR_SEGMENT}(?:/{_LOCATOR_SEGMENT})*(?:#(?:section|symbol):{_LOCATOR_SEGMENT})?)"
)


def parse_typed_locator(value: str, *, field: str = "reference") -> dict[str, str | None]:
    """Parse a raw typed locator before path normalization or file access."""
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"active_design_packet_reference_invalid:syntax:{value}")
    if value.startswith("repo:"):
        raise RuntimeError(
            f"active_design_packet_reference_ambiguous_root:{value}"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise RuntimeError(f"active_design_packet_reference_invalid:syntax:{value}")
    if "\\" in value or "%2f" in value.lower() or "%5c" in value.lower():
        raise RuntimeError(f"active_design_packet_reference_invalid:syntax:{value}")
    match = _LOCATOR_RE.fullmatch(value)
    if match is None:
        raise RuntimeError(f"active_design_packet_reference_invalid:syntax:{value}")
    fragment = match.group("fragment")
    fragment_kind: str | None = None
    fragment_value: str | None = None
    if fragment:
        fragment_kind, fragment_value = fragment[1:].split(":", 1)
    return {
        "declared_ref": value,
        "root_key": match.group("root"),
        "relative_path": match.group("path"),
        "fragment_kind": fragment_kind,
        "fragment_value": fragment_value,
        "field": field,
    }


def _parse_typed_header(value: str) -> tuple[dict[str, str | None], dict[str, str | None], str, str]:
    """Parse a typed dependency header and return endpoint identities."""
    if not isinstance(value, str) or value.startswith("header:") is False:
        raise RuntimeError(f"active_design_packet_reference_invalid:dependency:{value}")
    if value.startswith("header:") and ("repo:" in value or "->repo:" in value):
        raise RuntimeError(
            f"active_design_packet_reference_ambiguous_root:{value}"
        )
    match = _HEADER_RE.fullmatch(value)
    if match is None:
        raise RuntimeError(f"active_design_packet_reference_invalid:dependency:{value}")
    source = parse_typed_locator(match.group("source"), field="dependency.source")
    target = parse_typed_locator(match.group("target"), field="dependency.target")
    return source, target, match.group("direction"), match.group("kind")

ACTIVE_PACKET_SCHEMA = ACTIVE_DESIGN_PACKET_SCHEMA


def _active_packet_reference_tuple(value: object, field: str) -> tuple[str, ...]:
    """Validate one non-empty typed reference list."""
    values = _as_string_tuple(value, field)
    if not values:
        raise RuntimeError(f"{field}:empty")
    for candidate in values:
        if candidate.startswith("repo:"):
            raise RuntimeError(
                f"active_design_packet_reference_ambiguous_root:{candidate}"
            )
    prefixes = ACTIVE_PACKET_REFERENCE_PREFIXES[field.rsplit(".", 1)[-1]]
    if prefixes and any(not candidate.startswith(prefixes) for candidate in values):
        raise RuntimeError(f"{field}:invalid_reference")
    leaf = field.rsplit(".", 1)[-1]
    if leaf == "source_refs":
        for candidate in values:
            parse_typed_locator(candidate, field=field)
    elif leaf == "dependency_refs":
        for candidate in values:
            if candidate.startswith("header:"):
                _parse_typed_header(candidate)
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
        raise RuntimeError(f"{field_prefix}:field_invalid:document_flow_required")
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
        clause_id = _as_required_string(
            clause["clause_id"], f"{clause_field}.clause_id"
        )
        source_ref = _as_required_string(
            clause["source_ref"], f"{clause_field}.source_ref"
        )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", clause_id):
            raise RuntimeError(f"{clause_field}.clause_id:invalid")
        if not source_ref.startswith(("workspace:", "agentcanon:", "artifact:")):
            raise RuntimeError(f"{clause_field}.source_ref:invalid")
        parse_typed_locator(source_ref, field=f"{clause_field}.source_ref")
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
        if dependency_entries != expected_dependencies[
            section
        ] or not dependency_entries.issubset(known_entry_ids):
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


def _spec_source_root(spec: RunBundleSpec) -> Path:
    """Return the explicit source root or fail closed."""
    candidate = spec.agentcanon_source_root
    if candidate is None and spec.repository_roots is not None:
        candidate = spec.repository_roots.agentcanon_source_root
    if candidate is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
    return candidate.resolve()


def _materialized_source_identity(
    spec: RunBundleSpec,
    reference: str,
) -> dict[str, object]:
    """Resolve one source reference and bind it to the current file bytes."""
    parsed = parse_typed_locator(reference, field="source")
    prefix = str(parsed["root_key"])
    relative_value = str(parsed["relative_path"])
    root = (
        spec.report_dir
        if prefix == "artifact"
        else spec.workspace_root
        if prefix == "workspace"
        else _spec_source_root(spec)
    )
    declared_candidate = root / relative_value
    if declared_candidate.is_symlink():
        raise RuntimeError(f"active_design_packet_reference_missing:{reference}")
    candidate = declared_candidate.resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"active_design_packet_reference_invalid:source:{reference}"
        ) from exc
    if not candidate.is_file() or candidate.is_symlink():
        raise RuntimeError(f"active_design_packet_reference_missing:{reference}")
    fragment_kind = str(parsed["fragment_kind"] or "none")
    fragment_value = parsed["fragment_value"]
    return {
        "declared_ref": reference,
        "root_key": prefix,
        "relative_path": relative_value,
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
    source, target, direction, kind = _parse_typed_header(reference)
    source_key = str(source["root_key"])
    target_key = str(target["root_key"])
    root_by_key = {
        "workspace": spec.workspace_root,
        "agentcanon": _spec_source_root(spec),
        "artifact": spec.report_dir,
    }
    source_declared_path = root_by_key[source_key] / str(source["relative_path"])
    target_declared_path = root_by_key[target_key] / str(target["relative_path"])
    if source_declared_path.is_symlink() or target_declared_path.is_symlink():
        raise RuntimeError(f"active_design_packet_reference_missing:{reference}")
    source_path = source_declared_path.resolve()
    target_path = target_declared_path.resolve()
    for path, root in ((source_path, root_by_key[source_key]), (target_path, root_by_key[target_key])):
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise RuntimeError(
                f"active_design_packet_reference_invalid:dependency:{reference}"
            ) from exc
    if not source_path.is_file() or not target_path.is_file():
        raise RuntimeError(f"active_design_packet_reference_missing:{reference}")
    normalized = (
        f"header:{direction}:{kind}:{source_key}:{source['relative_path']}"
        f"->{target_key}:{target['relative_path']}"
    )
    return {
        "declared_ref": reference,
        "normalized_key": normalized,
        "source_path": str(source["relative_path"]),
        "target_path": str(target["relative_path"]),
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
            "output_refs": [
                f"artifact:{output}"
                for output in selected_role_outputs(spec.config, role, packet)
            ],
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
            output
            for output in role_output_map.get(reviewer, [])
            if output in review_outputs
        ]
        if len(matches) == 1:
            reviewer_projections.append(
                {"reviewer_ref": reviewer, "review_artifact_ref": matches[0]}
            )
    planned_paths = tuple(PurePosixPath(path) for path in artifact_names)
    return {
        "schema": ACTIVE_DESIGN_PACKET_MATERIALIZATION_SCHEMA,
        "packet_sha256": hashlib.sha256(
            canonical_json_bytes(packet_mapping)
        ).hexdigest(),
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
    """Return core plus explicitly selected artifact filenames.

    Core run metadata is always materialized so a bundle remains usable.  Role
    outputs (including design and review documents) are opt-in: an inactive
    reviewer does not leave an empty template or an implicit optional-template
    state machine in the bundle.
    """
    packet = active_design_packet or resolve_active_design_packet_config(config)
    return tuple(
        dict.fromkeys(
            (
                *(config.artifacts[key] for key in STANDARD_RUN_ARTIFACT_KEYS),
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
    agentcanon_source_root: Path | None = None,
) -> RoleDocumentPacket:
    """Resolve explicit read-before-work packet for one role."""
    if agentcanon_source_root is None:
        raise RuntimeError("runtime_roots_invalid:agentcanon_source_root_missing")
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
        resolved_path = resolve_workspace_document_path(
            workspace_root,
            relative_path,
            root_key="agentcanon",
            agentcanon_source_root=agentcanon_source_root,
        )
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
    for entry in resolve_cross_cutting_document_packet(
        workspace_root,
        agentcanon_source_root,
    ):
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


def role_specific_document_entries(
    document_packet: RoleDocumentPacket,
) -> tuple[DocumentPacketEntry, ...]:
    """Return per-role document entries without repeating common packet paths."""
    return tuple(
        entry
        for entry in document_packet.read_before_work
        if not entry.rationale.startswith("cross_cutting_doc:")
    )
