#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the closed model-profile registry, prompt/token materialization, and generated role projections.
# upstream implementation ../../agents/model_profiles.toml declares canonical profiles and explicit role bindings
# upstream implementation ../../.codex/config.toml declares registered role descriptions
# downstream implementation ./implementation_route.py selects the fixed Spark profile
# downstream implementation ./implementation_dispatch.py materializes implementation prompts and close tokens
# downstream implementation ./check_agent_runtime_alignment.py validates generated projections
# downstream implementation ../../tests/agent_tools/test_model_profile_registry.py tests closed registry behavior
# @dependency-end
"""Closed model-profile registry and canonical runtime materializers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Iterable, Mapping, Sequence, cast

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

SCHEMA_IDS = {
    "registry": "model_profile_registry_v1",
    "registry_cli": "model_profile_registry_cli_v1",
    "execution_contract": "implementation_execution_contract_v1",
    "role_instruction_clause": "role_instruction_clause_v1",
    "role_instruction_template": "role_instruction_template_v1",
    "tool_call_token": "tool_call_token_v1",
    "generated_role_view": "generated_role_view_v1",
    "consumer_static_clause_projection": "consumer_static_clause_projection_v1",
    "consumer_static_obligation": "consumer_static_obligation_v1",
    "common_return": "claim_evidence_v1",
}

COMMON_RETURN_SCHEMA_ID = SCHEMA_IDS["common_return"]

_ROOT_FIELDS = {
    "schema_id",
    "registry_id",
    "registry_version",
    "writer_isolation_policy",
    "role_profile_bindings",
    "role_sandbox_bindings",
    "role_instruction_templates",
    "standalone_role_metadata",
    "model_profiles",
}
_PROFILE_FIELDS = {
    "id",
    "model_alias",
    "model",
    "reasoning_effort",
    "owner",
    "capabilities",
    "allowed_context",
    "forbidden_context",
    "return_schema_id",
    "checkpoint_policy",
    "continuation_policy",
    "projection_digest",
    "role_template",
    "prompt_capsule_schema_id",
    "prompt_capsule_template",
    "prompt_capsule_required_context",
    "close_skill_id",
    "close_tool_id",
    "close_tool_argument_schema_id",
    "close_tool_failure_schema_id",
    "close_tool_target_binding",
    "role_instructions",
}
_CLAUSE_FIELDS = {"id", "text", "priority", "consumer_static_text", "static_obligations"}

# These are exact, case-normalized producer prefixes.  The static projection
# uses the same boundary as the exporter and consumer checker, while keeping
# the source registry itself available to the live renderer.
STATIC_FORBIDDEN_PREFIXES = (
    "agents/skills/",
    "agents/model_profiles.toml",
    "tools/agent_tools/",
    "../../agents/",
    "../../tools/",
)


@dataclass(frozen=True)
class StaticObligation:
    """One closed, path-free consumer-static obligation fragment."""

    schema_id: str
    obligation_id: str
    fragment: str


STATIC_OBLIGATION_TABLE: tuple[StaticObligation, ...] = (
    StaticObligation(
        schema_id=SCHEMA_IDS["consumer_static_obligation"],
        obligation_id="validation_owner",
        fragment="follow the selected closed validation route",
    ),
    StaticObligation(
        schema_id=SCHEMA_IDS["consumer_static_obligation"],
        obligation_id="parent_assignment",
        fragment="act only on the assigned child packet and scope",
    ),
    StaticObligation(
        schema_id=SCHEMA_IDS["consumer_static_obligation"],
        obligation_id="parent_authority",
        fragment="respect child-owned integration publication and final-review decisions",
    ),
    StaticObligation(
        schema_id=SCHEMA_IDS["consumer_static_obligation"],
        obligation_id="stop_handback",
        fragment="return branch/head/check evidence or the role result and stop",
    ),
)
_STATIC_OBLIGATIONS_BY_ID = {item.obligation_id: item for item in STATIC_OBLIGATION_TABLE}
REQUIRED_STATIC_OBLIGATION_SETS: Mapping[str, frozenset[str]] = {
    "python_solid_boundary": frozenset({"validation_owner", "parent_assignment"}),
    "luna_impl": frozenset(
        {"validation_owner", "parent_assignment", "parent_authority", "stop_handback"}
    ),
    "spark_impl": frozenset(
        {"validation_owner", "parent_assignment", "parent_authority", "stop_handback"}
    ),
}

CHECKOUT_IDENTITY_PROMPT = (
    "Carry one checkout_identity block with cwd, git_root, branch (or detached), head, "
    "and normalized remote owner/repository at bounded workflow transitions; do not "
    "repeat it for ordinary commands."
)


def _contains_static_forbidden_prefix(text: str) -> bool:
    lowered = text.casefold()
    return any(prefix in lowered for prefix in STATIC_FORBIDDEN_PREFIXES)


def _validated_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ModelProfileRegistryError(f"{field}:must_be_string_list")
    result: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str) or not item:
            raise ModelProfileRegistryError(f"{field}:must_be_string_list")
        result.append(item)
    return result


def _static_projection(
    clause: Mapping[str, Any],
    *,
    clause_id: str,
    field: str,
) -> ConsumerStaticClauseProjection | None:
    """Parse and validate one optional consumer-static clause projection."""
    has_text = "consumer_static_text" in clause
    has_obligations = "static_obligations" in clause
    if not has_text and not has_obligations:
        if _contains_static_forbidden_prefix(_text(clause["text"], f"{field}.text")):
            raise ModelProfileRegistryError(
                f"{field}:{clause_id}:consumer_static_projection_required"
            )
        return None
    if not has_text or not has_obligations:
        raise ModelProfileRegistryError(
            f"{field}:{clause_id}:consumer_static_projection_incomplete"
        )
    consumer_static_text = _text(
        clause["consumer_static_text"], f"{field}.consumer_static_text"
    )
    if _contains_static_forbidden_prefix(consumer_static_text):
        raise ModelProfileRegistryError(
            f"{field}:{clause_id}:consumer_static_text_contains_forbidden_prefix"
        )
    obligations = tuple(
        _validated_string_list(
            clause["static_obligations"],
            f"{field}:{clause_id}:static_obligations",
        )
    )
    if len(set(obligations)) != len(obligations):
        raise ModelProfileRegistryError(
            f"{field}:{clause_id}:static_obligations_duplicate"
        )
    unknown = sorted(set(obligations) - set(_STATIC_OBLIGATIONS_BY_ID))
    if unknown:
        raise ModelProfileRegistryError(
            f"{field}:{clause_id}:unknown_static_obligations:{','.join(unknown)}"
        )
    required = REQUIRED_STATIC_OBLIGATION_SETS.get(clause_id)
    if required is not None and set(obligations) != set(required):
        raise ModelProfileRegistryError(
            f"{field}:{clause_id}:required_static_obligations_mismatch"
        )
    return ConsumerStaticClauseProjection(
        clause_id=clause_id,
        consumer_static_text=consumer_static_text,
        static_obligations=obligations,
    )


class StructuralDesignGap(Exception):
    """An input contract contradicts the fixed implementation boundary."""


class ImplementationFeedback(Exception):
    """Implementation-repairable runtime feedback."""


class ModelProfileRegistryError(ImplementationFeedback):
    """Malformed closed registry or materialization input."""


def _closed_mapping(
    value: object,
    *,
    fields: set[str],
    required: set[str] | None = None,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelProfileRegistryError(f"{label}:must_be_mapping")
    keys = set(value)
    unknown = sorted(str(key) for key in keys - fields)
    if unknown:
        raise ModelProfileRegistryError(f"{label}:unknown_fields:{','.join(unknown)}")
    missing = sorted((required or fields) - keys)
    if missing:
        raise ModelProfileRegistryError(f"{label}:missing_fields:{','.join(missing)}")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelProfileRegistryError(f"{field}:must_be_nonempty_string")
    return value


def _string_tuple(value: object, field: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ModelProfileRegistryError(f"{field}:must_be_string_list")
    result = tuple(value)
    if nonempty and not result:
        raise ModelProfileRegistryError(f"{field}:must_be_nonempty")
    if len(set(result)) != len(result):
        raise ModelProfileRegistryError(f"{field}:duplicate")
    return result


def _stable_digest(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ContextItem:
    key: str
    value: Any


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    location: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    schema_id: str
    valid: bool
    issues: tuple[ValidationIssue, ...] = ()

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(SCHEMA_IDS["execution_contract"], True, ())

    @classmethod
    def fail(cls, issues: Iterable[ValidationIssue]) -> "ValidationResult":
        return cls(SCHEMA_IDS["execution_contract"], False, tuple(issues))


def validate_claim_evidence_result(value: object) -> ValidationResult:
    """Validate the one common claim/evidence return contract for all roles."""
    issues: list[ValidationIssue] = []
    if not isinstance(value, Mapping):
        return ValidationResult.fail(
            [ValidationIssue("return_contract.type", "claim/evidence result must be a mapping")]
        )
    status = value.get("status")
    if status not in {"pass", "revise", "escalate", "blocked"}:
        issues.append(
            ValidationIssue(
                "return_contract.status",
                "status must be pass, revise, escalate, or blocked",
                "status",
            )
        )
    claim = value.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        issues.append(ValidationIssue("return_contract.claim", "claim must be non-empty text", "claim"))
    evidence = value.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or not all(isinstance(item, str) and item.strip() for item in evidence)
    ):
        issues.append(
            ValidationIssue(
                "return_contract.evidence",
                "evidence must be a non-empty list of text references",
                "evidence",
            )
        )
    return ValidationResult.fail(issues) if issues else ValidationResult(
        COMMON_RETURN_SCHEMA_ID, True, ()
    )


def validate_common_return_schema(registry: "ModelProfileRegistry") -> ValidationResult:
    """Ensure every canonical profile advertises the common return contract."""
    profile_ids = {profile.return_schema_id for profile in registry.model_profiles}
    if profile_ids != {COMMON_RETURN_SCHEMA_ID}:
        return ValidationResult.fail(
            [
                ValidationIssue(
                    "return_contract.schema_ids",
                    f"all profiles must use {COMMON_RETURN_SCHEMA_ID}",
                    "model_profiles.return_schema_id",
                )
            ]
        )
    return ValidationResult(COMMON_RETURN_SCHEMA_ID, True, ())


@dataclass(frozen=True)
class ConsumerStaticClauseProjection:
    """Typed source-neutral projection for one live instruction clause."""

    clause_id: str
    consumer_static_text: str
    static_obligations: tuple[str, ...]
    schema_id: ClassVar[str] = SCHEMA_IDS["consumer_static_clause_projection"]


@dataclass(frozen=True)
class RoleInstructionClause:
    clause_id: str
    text: str
    priority: int = 0
    schema_id: str = SCHEMA_IDS["role_instruction_clause"]
    consumer_static_projection: ConsumerStaticClauseProjection | None = None


@dataclass(frozen=True)
class RoleInstructionTemplate:
    profile_id: str
    clauses: tuple[RoleInstructionClause, ...]
    template_text: str
    schema_id: str = SCHEMA_IDS["role_instruction_template"]


@dataclass(frozen=True)
class PromptCapsuleSchema:
    schema_id: str
    profile_id: str
    template: str
    required_context: tuple[str, ...]


@dataclass(frozen=True)
class ToolArgumentSchema:
    schema_id: str
    target: str
    properties: tuple[str, ...]


@dataclass(frozen=True)
class ToolCallToken:
    """Closed ToolCall token: a tool id and target-only arguments."""

    tool_id: str
    arguments: Mapping[str, str]

    @property
    def schema_id(self) -> str:
        return SCHEMA_IDS["tool_call_token"]


@dataclass(frozen=True)
class PromptMaterializationRequest:
    profile_id: str
    role_id: str
    context: tuple[ContextItem, ...]
    objective: str


@dataclass(frozen=True)
class ToolCallMaterializationRequest:
    profile_id: str
    terminal_agent_id: str


@dataclass(frozen=True)
class MaterializedPromptCapsule:
    schema_id: str
    profile_id: str
    role_id: str
    body: str
    context: tuple[ContextItem, ...]
    materialization_id: str
    return_schema_id: str
    projection_digest: str


@dataclass(frozen=True)
class MaterializedRoutePacket:
    schema_id: str
    route_id: str
    profile_id: str
    role_id: str
    prompt_capsule: MaterializedPromptCapsule
    tool_call_token: ToolCallToken
    generated_view_id: str


@dataclass(frozen=True)
class GeneratedViewDefinition:
    view_id: str
    role_id: str
    profile_id: str
    clauses: tuple[RoleInstructionClause, ...]


@dataclass(frozen=True)
class GeneratedRoleView:
    schema_id: str
    view_id: str
    role_id: str
    profile_id: str
    name: str
    description: str
    nickname_candidates: tuple[str, ...]
    sandbox_mode: str
    approval_policy: str
    rendered_instructions: str
    model: str
    reasoning_effort: str
    capabilities: tuple[str, ...]
    allowed_context: tuple[str, ...]
    forbidden_context: tuple[str, ...]
    return_schema_id: str
    checkpoint_policy: str
    continuation_policy: str
    source_canonical_digest: str
    logical_role_id: str
    role_contract_ref: str
    capsule_schema_id: str


@dataclass(frozen=True)
class TargetStateContract:
    contract_id: str
    unit_id: str
    owner: str
    exact_owner: str
    schema_id: str
    profiles: tuple[str, ...]
    configured_supported_profiles: tuple[str, ...]


@dataclass(frozen=True)
class ImplementationExecutionContract:
    contract_id: str
    schema_id: str = SCHEMA_IDS["execution_contract"]
    generated_views: tuple[GeneratedRoleView, ...] = ()
    tool_tokens: tuple[ToolCallToken, ...] = ()


@dataclass(frozen=True)
class ModelProfile:
    id: str
    model_alias: str
    model: str
    reasoning_effort: str
    owner: str
    capabilities: tuple[str, ...]
    allowed_context: tuple[str, ...]
    forbidden_context: tuple[str, ...]
    return_schema_id: str
    checkpoint_policy: str
    continuation_policy: str
    projection_digest: str
    role_template: str
    prompt_capsule_schema: PromptCapsuleSchema
    role_instruction_template: RoleInstructionTemplate
    tool_argument_schema: ToolArgumentSchema
    tool_argument_schema_id: str
    tool_failure_schema_id: str
    close_skill_id: str
    close_tool_id: str


@dataclass(frozen=True)
class ModelProfileRegistry:
    schema_id: str
    registry_id: str
    registry_version: int
    model_profiles: tuple[ModelProfile, ...]
    role_profile_bindings: Mapping[str, str]
    role_sandbox_bindings: Mapping[str, str]
    role_instruction_templates: Mapping[str, tuple[RoleInstructionClause, ...]]
    standalone_role_metadata: Mapping[str, tuple[str, str, str]]
    writer_isolation_policy: Mapping[str, object]

    def by_profile(self, profile_id: str) -> ModelProfile:
        matches = [profile for profile in self.model_profiles if profile.id == profile_id]
        if len(matches) != 1:
            raise ModelProfileRegistryError(f"model_profile:{profile_id}:not_found")
        return matches[0]

    def profile_for_role(self, role_id: str) -> ModelProfile:
        try:
            profile_id = self.role_profile_bindings[role_id]
        except KeyError as exc:
            raise ModelProfileRegistryError(f"role_profile:{role_id}:not_found") from exc
        return self.by_profile(profile_id)

    def instruction_clauses_for_role(
        self, role_id: str, profile_id: str | None = None
    ) -> tuple[RoleInstructionClause, ...]:
        """Return one closed ordered profile-plus-role instruction projection."""
        profile = self.profile_for_role(role_id)
        if profile_id is not None and profile.id != profile_id:
            raise ModelProfileRegistryError(
                f"role_profile:{role_id}:profile_mismatch:{profile_id}"
            )
        clauses = (
            *profile.role_instruction_template.clauses,
            *self.role_instruction_templates.get(role_id, ()),
        )
        clause_ids = [clause.clause_id for clause in clauses]
        if len(clause_ids) != len(set(clause_ids)):
            raise ModelProfileRegistryError(f"role_instruction:{role_id}:duplicate")
        return tuple(sorted(clauses, key=lambda value: (value.priority, value.clause_id)))

    def projection_digest_for_role(self, role_id: str, profile_id: str) -> str:
        """Bind both live and consumer-static views to one canonical clause digest."""
        profile = self.profile_for_role(role_id)
        clauses = self.instruction_clauses_for_role(role_id, profile_id)
        return _stable_digest(
            {
                "profile_id": profile.id,
                "role_id": role_id,
                "clauses": [
                    {
                        "id": clause.clause_id,
                        "priority": clause.priority,
                        "live_text": clause.text,
                        "consumer_static_text": (
                            clause.consumer_static_projection.consumer_static_text
                            if clause.consumer_static_projection is not None
                            else clause.text
                        ),
                        "static_obligations": list(
                            clause.consumer_static_projection.static_obligations
                            if clause.consumer_static_projection is not None
                            else ()
                        ),
                    }
                    for clause in clauses
                ],
            }
        )


def _read_toml_file(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ModelProfileRegistryError(f"registry_unreadable:{path}:{exc}") from exc
    if not isinstance(value, Mapping):
        raise ModelProfileRegistryError(f"registry:{path}:must_be_mapping")
    return value


def _profile_digest_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in sorted(_PROFILE_FIELDS - {"projection_digest"})
    }


def load_model_profile_registry(
    root: os.PathLike[str] | str = ".",
    *,
    source_root: os.PathLike[str] | str | None = None,
) -> ModelProfileRegistry:
    """Load the registry from an explicit AgentCanon source root.

    ``root`` remains the standalone positional API.  Derived callers pass
    ``source_root`` so a parent workspace can never silently become the source
    registry root.
    """
    root_path = Path(source_root if source_root is not None else root).resolve()
    registry_path = root_path / "agents" / "model_profiles.toml"
    if not registry_path.is_file():
        raise ModelProfileRegistryError(
            f"model_profile_registry_source_missing:{registry_path.relative_to(root_path)}"
        )
    data = _closed_mapping(
        _read_toml_file(registry_path),
        fields=_ROOT_FIELDS,
        required=_ROOT_FIELDS - {"writer_isolation_policy"},
        label="registry",
    )
    if _text(data["schema_id"], "schema_id") != SCHEMA_IDS["registry"]:
        raise ModelProfileRegistryError("schema_id:mismatch")
    version = data["registry_version"]
    if not isinstance(version, int) or version <= 0:
        raise ModelProfileRegistryError("registry_version:must_be_positive_int")
    raw_writer_policy = _closed_mapping(
        data.get(
            "writer_isolation_policy",
            {
                "current_checkout_mode": "legacy_unspecified",
                "parallel_requirements": ["disjoint_paths"],
                "collision_action": "serialize_current_checkout_waves",
                "isolated_worktree_mode": "explicit_only",
            },
        ),
        fields={
            "current_checkout_mode",
            "parallel_requirements",
            "collision_action",
            "isolated_worktree_mode",
        },
        required={
            "current_checkout_mode",
            "parallel_requirements",
            "collision_action",
            "isolated_worktree_mode",
        },
        label="writer_isolation_policy",
    )
    current_checkout_mode = _text(
        raw_writer_policy["current_checkout_mode"],
        "writer_isolation_policy.current_checkout_mode",
    )
    collision_action = _text(
        raw_writer_policy["collision_action"],
        "writer_isolation_policy.collision_action",
    )
    isolated_worktree_mode = _text(
        raw_writer_policy["isolated_worktree_mode"],
        "writer_isolation_policy.isolated_worktree_mode",
    )
    parallel_requirements = _string_tuple(
        raw_writer_policy["parallel_requirements"],
        "writer_isolation_policy.parallel_requirements",
    )
    writer_policy = {
        "current_checkout_mode": current_checkout_mode,
        "parallel_requirements": parallel_requirements,
        "collision_action": collision_action,
        "isolated_worktree_mode": isolated_worktree_mode,
    }
    raw_bindings = data["role_profile_bindings"]
    if not isinstance(raw_bindings, Mapping) or not raw_bindings:
        raise ModelProfileRegistryError("role_profile_bindings:must_be_nonempty_mapping")
    bindings: dict[str, str] = {}
    for role_id, profile_id in raw_bindings.items():
        role = _text(role_id, "role_profile_bindings.role_id")
        bindings[role] = _text(profile_id, f"role_profile_bindings.{role}")
    raw_sandboxes = data["role_sandbox_bindings"]
    if not isinstance(raw_sandboxes, Mapping) or set(raw_sandboxes) != set(bindings):
        raise ModelProfileRegistryError("role_sandbox_bindings:must_exactly_match_role_bindings")
    sandboxes: dict[str, str] = {}
    for role_id, sandbox_value in raw_sandboxes.items():
        sandbox = _text(sandbox_value, f"role_sandbox_bindings.{role_id}")
        if sandbox not in {"read-only", "workspace-write"}:
            raise ModelProfileRegistryError(f"role_sandbox_bindings.{role_id}:invalid")
        sandboxes[str(role_id)] = sandbox
    raw_role_templates = data["role_instruction_templates"]
    if not isinstance(raw_role_templates, Mapping):
        raise ModelProfileRegistryError("role_instruction_templates:must_be_mapping")
    unknown_role_templates = sorted(set(raw_role_templates) - set(bindings))
    if unknown_role_templates:
        raise ModelProfileRegistryError(
            "role_instruction_templates:unknown_roles:"
            + ",".join(str(role_id) for role_id in unknown_role_templates)
        )
    role_templates: dict[str, tuple[RoleInstructionClause, ...]] = {}
    for role_id, raw_clauses in raw_role_templates.items():
        role = _text(role_id, "role_instruction_templates.role_id")
        if not isinstance(raw_clauses, list) or not raw_clauses:
            raise ModelProfileRegistryError(
                f"role_instruction_templates.{role}:must_be_nonempty_list"
            )
        clauses: list[RoleInstructionClause] = []
        seen_clauses: set[str] = set()
        for clause_index, raw_clause in enumerate(raw_clauses):
            clause = _closed_mapping(
                raw_clause,
                fields=_CLAUSE_FIELDS,
                required={"id", "text", "priority"},
                label=f"role_instruction_templates.{role}[{clause_index}]",
            )
            clause_id = _text(clause["id"], "role_instruction.id")
            if clause_id in seen_clauses:
                raise ModelProfileRegistryError(
                    f"role_instruction:{role}:{clause_id}:duplicate"
                )
            seen_clauses.add(clause_id)
            priority = clause["priority"]
            if not isinstance(priority, int):
                raise ModelProfileRegistryError(
                    f"role_instruction:{role}:{clause_id}:priority_must_be_int"
                )
            clauses.append(
                RoleInstructionClause(
                    clause_id,
                    _text(clause["text"], "role_instruction.text"),
                    priority,
                    consumer_static_projection=_static_projection(
                        clause,
                        clause_id=clause_id,
                        field=f"role_instruction_templates.{role}[{clause_index}]",
                    ),
                )
            )
        role_templates[role] = tuple(
            sorted(clauses, key=lambda value: (value.priority, value.clause_id))
        )
    raw_standalone = data["standalone_role_metadata"]
    if not isinstance(raw_standalone, Mapping):
        raise ModelProfileRegistryError("standalone_role_metadata:must_be_mapping")
    standalone: dict[str, tuple[str, str, str]] = {}
    for role_id, raw_metadata in raw_standalone.items():
        metadata = _closed_mapping(
            raw_metadata,
            fields={"logical_role_id", "role_contract_ref", "sandbox_mode"},
            label=f"standalone_role_metadata.{role_id}",
        )
        standalone[_text(role_id, "standalone_role_metadata.role_id")] = (
            _text(metadata["logical_role_id"], "standalone_role_metadata.logical_role_id"),
            _text(metadata["role_contract_ref"], "standalone_role_metadata.role_contract_ref"),
            _text(metadata["sandbox_mode"], "standalone_role_metadata.sandbox_mode"),
        )

    raw_profiles = data["model_profiles"]
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ModelProfileRegistryError("model_profiles:must_be_nonempty_list")
    profiles: list[ModelProfile] = []
    profile_ids: set[str] = set()
    for index, raw_item in enumerate(raw_profiles):
        item = _closed_mapping(raw_item, fields=_PROFILE_FIELDS, label=f"model_profiles[{index}]")
        profile_id = _text(item["id"], f"model_profiles[{index}].id")
        if profile_id in profile_ids:
            raise ModelProfileRegistryError(f"model_profile:{profile_id}:duplicate")
        profile_ids.add(profile_id)
        clauses_raw = item["role_instructions"]
        if not isinstance(clauses_raw, list) or not clauses_raw:
            raise ModelProfileRegistryError(f"model_profile:{profile_id}:missing_role_instructions")
        clauses: list[RoleInstructionClause] = []
        seen_clauses: set[str] = set()
        for clause_index, raw_clause in enumerate(clauses_raw):
            clause = _closed_mapping(
                raw_clause,
                fields=_CLAUSE_FIELDS,
                required={"id", "text", "priority"},
                label=f"model_profile:{profile_id}.role_instructions[{clause_index}]",
            )
            clause_id = _text(clause["id"], "role_instruction.id")
            if clause_id in seen_clauses:
                raise ModelProfileRegistryError(f"role_instruction:{clause_id}:duplicate")
            seen_clauses.add(clause_id)
            priority = clause["priority"]
            if not isinstance(priority, int):
                raise ModelProfileRegistryError(f"role_instruction:{clause_id}:priority_must_be_int")
            clauses.append(
                RoleInstructionClause(
                    clause_id,
                    _text(clause["text"], "role_instruction.text"),
                    priority,
                    consumer_static_projection=_static_projection(
                        clause,
                        clause_id=clause_id,
                        field=f"model_profile:{profile_id}.role_instructions[{clause_index}]",
                    ),
                )
            )
        allowed = _string_tuple(item["allowed_context"], f"{profile_id}.allowed_context")
        forbidden = _string_tuple(item["forbidden_context"], f"{profile_id}.forbidden_context")
        if set(allowed) & set(forbidden):
            raise ModelProfileRegistryError(f"model_profile:{profile_id}:context_overlap")
        required_context = _string_tuple(
            item["prompt_capsule_required_context"],
            f"{profile_id}.prompt_capsule_required_context",
        )
        if not set(required_context).issubset(allowed):
            raise ModelProfileRegistryError(f"model_profile:{profile_id}:required_context_not_allowed")
        if item["projection_digest"] != "computed_sha256_v1":
            raise ModelProfileRegistryError(f"model_profile:{profile_id}:projection_digest_policy_invalid")
        digest = _stable_digest(_profile_digest_payload(item))
        target = _text(item["close_tool_target_binding"], f"{profile_id}.close_tool_target_binding")
        if target != "terminal_agent_id":
            raise ModelProfileRegistryError(f"model_profile:{profile_id}:close_target_mismatch")
        sorted_clauses = tuple(sorted(clauses, key=lambda value: (value.priority, value.clause_id)))
        profiles.append(
            ModelProfile(
                id=profile_id,
                model_alias=_text(item["model_alias"], f"{profile_id}.model_alias"),
                model=_text(item["model"], f"{profile_id}.model"),
                reasoning_effort=_text(item["reasoning_effort"], f"{profile_id}.reasoning_effort"),
                owner=_text(item["owner"], f"{profile_id}.owner"),
                capabilities=_string_tuple(item["capabilities"], f"{profile_id}.capabilities"),
                allowed_context=allowed,
                forbidden_context=forbidden,
                return_schema_id=_text(item["return_schema_id"], f"{profile_id}.return_schema_id"),
                checkpoint_policy=_text(item["checkpoint_policy"], f"{profile_id}.checkpoint_policy"),
                continuation_policy=_text(item["continuation_policy"], f"{profile_id}.continuation_policy"),
                projection_digest=digest,
                role_template=_text(item["role_template"], f"{profile_id}.role_template"),
                prompt_capsule_schema=PromptCapsuleSchema(
                    schema_id=_text(item["prompt_capsule_schema_id"], f"{profile_id}.prompt_capsule_schema_id"),
                    profile_id=profile_id,
                    template=_text(item["prompt_capsule_template"], f"{profile_id}.prompt_capsule_template"),
                    required_context=required_context,
                ),
                role_instruction_template=RoleInstructionTemplate(
                    profile_id=profile_id,
                    clauses=sorted_clauses,
                    template_text=_text(item["role_template"], f"{profile_id}.role_template"),
                ),
                tool_argument_schema=ToolArgumentSchema(
                    schema_id=_text(item["close_tool_argument_schema_id"], f"{profile_id}.close_tool_argument_schema_id"),
                    target=target,
                    properties=(target,),
                ),
                tool_argument_schema_id=_text(item["close_tool_argument_schema_id"], f"{profile_id}.close_tool_argument_schema_id"),
                tool_failure_schema_id=_text(item["close_tool_failure_schema_id"], f"{profile_id}.close_tool_failure_schema_id"),
                close_skill_id=_text(item["close_skill_id"], f"{profile_id}.close_skill_id"),
                close_tool_id=_text(item["close_tool_id"], f"{profile_id}.close_tool_id"),
            )
        )
    unknown_profiles = sorted(set(bindings.values()) - profile_ids)
    if unknown_profiles:
        raise ModelProfileRegistryError(f"role_profile_bindings:unknown_profiles:{','.join(unknown_profiles)}")
    registry = ModelProfileRegistry(
        schema_id=SCHEMA_IDS["registry"],
        registry_id=_text(data["registry_id"], "registry_id"),
        registry_version=version,
        model_profiles=tuple(profiles),
        role_profile_bindings=bindings,
        role_sandbox_bindings=sandboxes,
        role_instruction_templates=role_templates,
        standalone_role_metadata=standalone,
        writer_isolation_policy=writer_policy,
    )
    for role_id in role_templates:
        registry.instruction_clauses_for_role(role_id)
    return registry


def _context_block(context: tuple[ContextItem, ...]) -> str:
    return "\n".join(f"- {item.key}: {item.value}" for item in context)


def materialize_prompt_capsule(
    request: PromptMaterializationRequest,
    registry: ModelProfileRegistry,
) -> MaterializedPromptCapsule:
    profile = registry.profile_for_role(request.role_id)
    if profile.id != request.profile_id:
        raise ModelProfileRegistryError(
            f"prompt_request:role_profile_mismatch:{request.role_id}:{request.profile_id}"
        )
    if not request.role_id or not request.objective.strip():
        raise ModelProfileRegistryError("prompt_request:role_and_objective_required")
    keys = [item.key for item in request.context]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ModelProfileRegistryError("prompt_context:empty_or_duplicate_key")
    provided = set(keys)
    unknown = sorted(provided - set(profile.allowed_context))
    forbidden = sorted(provided & set(profile.forbidden_context))
    missing = sorted(set(profile.prompt_capsule_schema.required_context) - provided)
    if unknown:
        raise ModelProfileRegistryError(f"prompt_context:unknown:{','.join(unknown)}")
    if forbidden:
        raise ModelProfileRegistryError(f"prompt_context:forbidden:{','.join(forbidden)}")
    if missing:
        raise ModelProfileRegistryError(f"prompt_context:missing:{','.join(missing)}")
    role_clauses = registry.instruction_clauses_for_role(
        request.role_id, request.profile_id
    )
    clauses = " ".join(clause.text for clause in role_clauses)
    clauses = f"{clauses} {CHECKOUT_IDENTITY_PROMPT}".strip()
    projection_digest = registry.projection_digest_for_role(
        request.role_id, request.profile_id
    )
    base_prompt = profile.role_template.format(
        role_id=request.role_id,
        model_alias=profile.model_alias,
        base_prompt=clauses,
    )
    body = profile.prompt_capsule_schema.template.format(
        role_id=request.role_id,
        model_alias=profile.model_alias,
        base_prompt=base_prompt,
        objective=request.objective,
        context_block=_context_block(request.context),
    ).strip()
    materialization_id = _stable_digest(
        {
            "profile_id": profile.id,
            "projection_digest": projection_digest,
            "role_id": request.role_id,
            "context": [(item.key, item.value) for item in request.context],
            "objective": request.objective,
        }
    )
    return MaterializedPromptCapsule(
        schema_id=profile.prompt_capsule_schema.schema_id,
        profile_id=profile.id,
        role_id=request.role_id,
        body=body,
        context=request.context,
        materialization_id=materialization_id,
        return_schema_id=profile.return_schema_id,
        projection_digest=projection_digest,
    )


def materialize_tool_call_token(
    request: ToolCallMaterializationRequest,
    profile: ModelProfile | str,
    registry: ModelProfileRegistry,
) -> ToolCallToken:
    profile_obj = registry.by_profile(profile) if isinstance(profile, str) else profile
    if not isinstance(profile_obj, ModelProfile):
        raise StructuralDesignGap("tool_call_token_request.profile.type")
    if request.profile_id != profile_obj.id:
        raise ModelProfileRegistryError("tool_call_token_request:profile_mismatch")
    if not isinstance(request.terminal_agent_id, str) or not request.terminal_agent_id.strip():
        raise ModelProfileRegistryError("terminal_agent_id:must_be_nonempty")
    return ToolCallToken(
        tool_id=profile_obj.close_tool_id,
        arguments={profile_obj.tool_argument_schema.target: request.terminal_agent_id},
    )


def materialize_route_packet(
    role_id: str,
    profile_id: str,
    objective: str,
    root: os.PathLike[str] | str = ".",
    terminal_agent_id: str = "agent-0",
    context: Iterable[ContextItem] | None = None,
) -> MaterializedRoutePacket:
    registry = load_model_profile_registry(root)
    prompt = materialize_prompt_capsule(
        PromptMaterializationRequest(profile_id, role_id, tuple(context or ()), objective),
        registry,
    )
    token = materialize_tool_call_token(
        ToolCallMaterializationRequest(profile_id, terminal_agent_id),
        profile_id,
        registry,
    )
    route_id = "route:" + _stable_digest(
        {
            "role_id": role_id,
            "profile_id": profile_id,
            "objective": objective,
            "terminal_agent_id": terminal_agent_id,
            "prompt_materialization_id": prompt.materialization_id,
        }
    )
    return MaterializedRoutePacket(
        schema_id=SCHEMA_IDS["execution_contract"],
        route_id=route_id,
        profile_id=profile_id,
        role_id=role_id,
        prompt_capsule=prompt,
        tool_call_token=token,
        generated_view_id=f"generated-view:{role_id}:{profile_id}",
    )


def _team_role_metadata(root: Path) -> dict[str, tuple[str, str, str]]:
    try:
        raw = json.loads((root / "agents" / "agents_config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelProfileRegistryError(f"agents_config:unreadable:{exc}") from exc
    if not isinstance(raw, dict):
        raise ModelProfileRegistryError("agents_config:must_be_mapping")
    result: dict[str, tuple[str, str, str]] = {}
    for section in ("always_on_roles", "specialist_roles"):
        entries = raw.get(section)
        if not isinstance(entries, list):
            raise ModelProfileRegistryError(f"agents_config:{section}:must_be_list")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ModelProfileRegistryError(f"agents_config:{section}[{index}]:must_be_mapping")
            logical_role = _text(entry.get("id"), f"agents_config:{section}[{index}].id")
            agent_ids = entry.get("codex_agents")
            if agent_ids is None:
                continue
            if not isinstance(agent_ids, list) or not all(isinstance(value, str) and value for value in agent_ids):
                raise ModelProfileRegistryError(f"agents_config:{section}[{index}].codex_agents:invalid")
            write_policy = entry.get("write_policy")
            if not isinstance(write_policy, dict):
                raise ModelProfileRegistryError(f"agents_config:{section}[{index}].write_policy:invalid")
            mode = _text(write_policy.get("mode"), f"agents_config:{section}[{index}].write_policy.mode")
            sandbox = "read-only" if mode == "read_only" else "workspace-write"
            for agent_id in agent_ids:
                if agent_id in result:
                    prior_roles, prior_refs, prior_sandbox = result[agent_id]
                    if prior_sandbox != sandbox:
                        raise ModelProfileRegistryError(
                            f"agents_config:shared_codex_agent_sandbox_conflict:{agent_id}"
                        )
                    result[agent_id] = (
                        "+".join((*prior_roles.split("+"), logical_role)),
                        "+".join((*prior_refs.split("+"), f"agents/agents_config.json#/{section}/{index}")),
                        sandbox,
                    )
                    continue
                result[agent_id] = (
                    logical_role,
                    f"agents/agents_config.json#/{section}/{index}",
                    sandbox,
                )
    return result


def _registered_role_descriptions(root: Path) -> dict[str, str]:
    config = _read_toml_file(root / ".codex" / "config.toml")
    agents = config.get("agents")
    if not isinstance(agents, Mapping):
        raise ModelProfileRegistryError("codex_config:agents_missing")
    result: dict[str, str] = {}
    for role_id, value in agents.items():
        if not isinstance(value, Mapping):
            continue
        result[str(role_id)] = _text(value.get("description"), f"codex_config.agents.{role_id}.description")
    return result


def _validate_projection_mode(projection: str) -> str:
    if projection not in {"live", "consumer-static"}:
        raise ModelProfileRegistryError(
            f"role_projection:unsupported_projection:{projection}"
        )
    return projection


STATIC_EXECUTABLE_ROLE_IDS = frozenset({"skill_evaluator"})


def _executable_projection(role_id: str, requested: str) -> str:
    """Return the executable projection allowed for one role.

    The mini skill evaluator is an intentionally source-free, artifact-only
    consumer.  It must not receive producer paths or live team instructions;
    all other executable role views follow the requested live/static mode.
    """
    return "consumer-static" if role_id in STATIC_EXECUTABLE_ROLE_IDS else requested


def compose_consumer_static_clause(
    clause: RoleInstructionClause,
) -> tuple[str, tuple[str, ...]]:
    """Compose one source-neutral clause and return its selected obligation IDs."""
    projection = clause.consumer_static_projection
    if projection is None:
        if _contains_static_forbidden_prefix(clause.text):
            raise ModelProfileRegistryError(
                f"role_instruction:{clause.clause_id}:consumer_static_projection_required"
            )
        return clause.text, ()
    selected = tuple(
        _STATIC_OBLIGATIONS_BY_ID[obligation_id].fragment
        for obligation_id in projection.static_obligations
    )
    return " ".join((projection.consumer_static_text, *selected)), projection.static_obligations


def _render_instruction_clauses(
    clauses: Sequence[RoleInstructionClause],
    projection: str,
) -> str:
    mode = _validate_projection_mode(projection)
    if mode == "live":
        return " ".join(clause.text for clause in clauses)
    return " ".join(compose_consumer_static_clause(clause)[0] for clause in clauses)


def generate_role_views(
    registry: ModelProfileRegistry,
    root: os.PathLike[str] | str = ".",
    target_state_contract: Mapping[str, Any] | TargetStateContract | None = None,
    projection: str = "live",
) -> tuple[GeneratedRoleView, ...]:
    projection = _validate_projection_mode(projection)
    root_path = Path(root)
    metadata = _team_role_metadata(root_path)
    if set(metadata) & set(registry.standalone_role_metadata):
        raise ModelProfileRegistryError("role_projection:standalone_metadata_overlaps_team_binding")
    metadata.update(registry.standalone_role_metadata)
    if set(metadata) != set(registry.role_sandbox_bindings):
        raise ModelProfileRegistryError("role_projection:sandbox_binding_set_mismatch")
    metadata = {
        role_id: (logical_role, contract_ref, registry.role_sandbox_bindings[role_id])
        for role_id, (logical_role, contract_ref, _derived_sandbox) in metadata.items()
    }
    descriptions = _registered_role_descriptions(root_path)
    expected_roles = set(metadata) | set(descriptions)
    if set(metadata) != set(descriptions) or set(registry.role_profile_bindings) != expected_roles:
        raise ModelProfileRegistryError("role_projection:binding_registration_set_mismatch")
    if isinstance(target_state_contract, Mapping):
        explicit = target_state_contract.get("supported_role_profiles")
        if explicit is not None and explicit != registry.role_profile_bindings:
            raise ModelProfileRegistryError("target_state_contract:role_profile_binding_mismatch")
    views: list[GeneratedRoleView] = []
    for role_id in sorted(expected_roles):
        profile = registry.profile_for_role(role_id)
        logical_role, contract_ref, sandbox = metadata[role_id]
        role_clauses = registry.instruction_clauses_for_role(role_id, profile.id)
        clauses = _render_instruction_clauses(role_clauses, projection)
        clauses = f"{clauses} {CHECKOUT_IDENTITY_PROMPT}".strip()
        instructions = profile.role_template.format(
            role_id=role_id,
            model_alias=profile.model_alias,
            base_prompt=clauses,
        ).strip()
        views.append(
            GeneratedRoleView(
                schema_id=SCHEMA_IDS["generated_role_view"],
                view_id=f"generated-view:{role_id}:{profile.id}",
                role_id=role_id,
                profile_id=profile.id,
                name=role_id,
                description=descriptions[role_id],
                nickname_candidates=(role_id,),
                sandbox_mode=sandbox,
                approval_policy="never",
                rendered_instructions=instructions,
                model=profile.model,
                reasoning_effort=profile.reasoning_effort,
                capabilities=profile.capabilities,
                allowed_context=profile.allowed_context,
                forbidden_context=profile.forbidden_context,
                return_schema_id=profile.return_schema_id,
                checkpoint_policy=profile.checkpoint_policy,
                continuation_policy=profile.continuation_policy,
                source_canonical_digest=registry.projection_digest_for_role(
                    role_id, profile.id
                ),
                logical_role_id=logical_role,
                role_contract_ref=contract_ref,
                capsule_schema_id=profile.prompt_capsule_schema.schema_id,
            )
        )
    if not views:
        raise ModelProfileRegistryError("generated_role_views:empty")
    return tuple(views)


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_role_view(view: GeneratedRoleView, projection: str = "live") -> str:
    projection = _validate_projection_mode(projection)
    nicknames = ", ".join(_toml_string(value) for value in view.nickname_candidates)
    if projection == "consumer-static":
        comments = (
            "# generated role view: generated_role_view_v1",
            f"# source canonical digest: {view.source_canonical_digest}",
        )
    else:
        comments = (
            "# @dependency-start",
            "# contract configuration",
            f"# responsibility Projects the canonical {view.role_id} model profile into executable Codex settings.",
            "# upstream implementation ../../agents/model_profiles.toml owns model/profile authority",
            "# upstream implementation ../../tools/agent_tools/model_profile_registry.py materializes this view",
            "# downstream implementation ../../tools/agent_tools/check_agent_runtime_alignment.py validates projection parity",
            "# @dependency-end",
            "# generated role view: generated_role_view_v1",
            "# generated from agents/model_profiles.toml plus canonical team/runtime role metadata",
            "# materializer: tools/agent_tools/model_profile_registry.py",
            f"# source canonical digest: {view.source_canonical_digest}",
        )
    return "\n".join(
        (
            *comments,
            "",
            f"name = {_toml_string(view.name)}",
            f"description = {_toml_string(view.description)}",
            f"nickname_candidates = [{nicknames}]",
            f"sandbox_mode = {_toml_string(view.sandbox_mode)}",
            f"approval_policy = {_toml_string(view.approval_policy)}",
            f"model = {_toml_string(view.model)}",
            f"model_reasoning_effort = {_toml_string(view.reasoning_effort)}",
            "",
            f"developer_instructions = {_toml_string(view.rendered_instructions)}",
            "",
        )
    )


def _projection_records(views: Sequence[GeneratedRoleView]) -> tuple[dict[str, object], list[dict[str, object]]]:
    agent_views: dict[str, object] = {}
    roles: list[dict[str, object]] = []
    for view in views:
        agent_views[view.role_id] = {
            "name": view.name,
            "description": view.description,
            "nickname_candidates": list(view.nickname_candidates),
            "sandbox_mode": view.sandbox_mode,
            "approval_policy": view.approval_policy,
            "model": view.model,
            "model_reasoning_effort": view.reasoning_effort,
            "developer_instructions": view.rendered_instructions,
            "logical_role_id": view.logical_role_id,
            "role_contract_ref": view.role_contract_ref,
            "profile_id": view.profile_id,
            "capsule_schema_id": view.capsule_schema_id,
            "capabilities": list(view.capabilities),
            "allowed_context": list(view.allowed_context),
            "forbidden_context": list(view.forbidden_context),
            "return_schema_id": view.return_schema_id,
            "checkpoint_policy": view.checkpoint_policy,
            "continuation_policy": view.continuation_policy,
            "projection_digest": view.source_canonical_digest,
        }
        roles.append(
            {
                "id": view.role_id,
                "profile_id": view.profile_id,
                "capsule_schema_id": view.capsule_schema_id,
                "capabilities": list(view.capabilities),
                "allowed_context": list(view.allowed_context),
                "forbidden_context": list(view.forbidden_context),
                "return_schema_id": view.return_schema_id,
                "checkpoint_policy": view.checkpoint_policy,
                "continuation_policy": view.continuation_policy,
                "projection_digest": view.source_canonical_digest,
            }
        )
    return agent_views, roles


def write_role_views(
    root: os.PathLike[str] | str = ".",
    projection: str = "live",
) -> tuple[GeneratedRoleView, ...]:
    root_path = Path(root)
    registry = load_model_profile_registry(root_path)
    projection = _validate_projection_mode(projection)
    views = generate_role_views(registry, root_path, projection=projection)
    for view in views:
        path = root_path / ".codex" / "agents" / f"{view.role_id}.toml"
        path.write_text(
            _render_role_view(view, _executable_projection(view.role_id, projection)),
            encoding="utf-8",
        )
    # Executable Codex views may contain source-bearing live clauses, while
    # agents_config.json is the source-free consumer projection.
    consumer_static_views = generate_role_views(
        registry, root_path, projection="consumer-static"
    )
    config_path = root_path / "agents" / "agents_config.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ModelProfileRegistryError("agents_config:must_be_mapping")
    agent_views, roles = _projection_records(consumer_static_views)
    raw["generated_profile_projection"] = {
        "schema_id": "generated_role_profile_projection_v1",
        "materializer": "tools/agent_tools/model_profile_registry.py",
        "registry_ref": "agents/model_profiles.toml",
        "role_count": len(consumer_static_views),
        "projection_digest": _stable_digest(
            {view.role_id: view.source_canonical_digest for view in views}
        ),
    }
    raw["agent_views"] = agent_views
    raw["roles"] = roles
    config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return views


def validate_target_state_contract(
    target_state_contract: Mapping[str, Any],
    registry: ModelProfileRegistry,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    for field in ("contract_id", "unit_id", "owner", "exact_owner", "profiles", "configured_supported_profiles"):
        if field not in target_state_contract:
            issues.append(ValidationIssue("missing_field", f"{field}:missing", field))
    profiles = target_state_contract.get("configured_supported_profiles")
    if not isinstance(profiles, list):
        issues.append(ValidationIssue("profiles", "configured_supported_profiles:must_be_list", "profiles"))
    else:
        known = {profile.id for profile in registry.model_profiles}
        for profile_id in profiles:
            if not isinstance(profile_id, str) or profile_id not in known:
                issues.append(ValidationIssue("unknown_profile", f"configured_profile:{profile_id}:not_in_registry", "profiles"))
    return ValidationResult.fail(issues) if issues else ValidationResult.ok()


def materialize_contract_projection(
    target_state_contract: Mapping[str, Any],
    root: os.PathLike[str] | str = ".",
    projection: str = "live",
) -> ImplementationExecutionContract:
    registry = load_model_profile_registry(root)
    result = validate_target_state_contract(target_state_contract, registry)
    if not result.valid:
        raise ModelProfileRegistryError("target_state_contract_validation_failed")
    contract_id = _text(target_state_contract.get("contract_id"), "target_state_contract.contract_id")
    return ImplementationExecutionContract(
        contract_id=contract_id,
        generated_views=generate_role_views(
            registry,
            root,
            target_state_contract,
            projection=projection,
        ),
    )


def _role_view_issues(root: Path, projection: str = "live") -> tuple[ValidationIssue, ...]:
    projection = _validate_projection_mode(projection)
    registry = load_model_profile_registry(root)
    views = generate_role_views(registry, root, projection=projection)
    issues: list[ValidationIssue] = []
    for view in views:
        path = root / ".codex" / "agents" / f"{view.role_id}.toml"
        expected = _render_role_view(
            view, _executable_projection(view.role_id, projection)
        ).encode("utf-8")
        try:
            actual = path.read_bytes()
        except OSError:
            actual = b""
        if actual != expected:
            issues.append(ValidationIssue("role_view.content_drift", "generated role projection differs", path.relative_to(root).as_posix()))
    config_path = root / "agents" / "agents_config.json"
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = None
    expected_views, expected_roles = _projection_records(
        generate_role_views(registry, root, projection="consumer-static")
    )
    if not isinstance(raw, dict) or raw.get("agent_views") != expected_views or raw.get("roles") != expected_roles:
        issues.append(ValidationIssue("role_view.config_projection_drift", "agents_config generated projection differs", "agents/agents_config.json"))
    return tuple(sorted(issues, key=lambda item: (item.location or "", item.code)))


def _print_role_view_issue(issue: ValidationIssue) -> None:
    print(
        "MODEL_PROFILE_ROLE_VIEW_ISSUE="
        + json.dumps(
            {
                "code": issue.code,
                "location": issue.location,
                "message": issue.message,
                "schema_id": SCHEMA_IDS["registry_cli"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="model_profile_registry.py")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument(
        "--projection",
        choices=("live", "consumer-static"),
        default="consumer-static",
        help="In-memory role projection mode; generated schema fields remain unchanged.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate-role-views", action="store_true")
    mode.add_argument("--check-role-views", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.generate_role_views:
            views = write_role_views(args.root, args.projection)
            print(f"MODEL_PROFILE_ROLE_VIEWS=generated:{len(views)}")
            return 0
        issues = _role_view_issues(args.root, args.projection)
    except (ModelProfileRegistryError, OSError, ValueError) as exc:
        issues = (ValidationIssue("role_view.schema_drift", str(exc), "agents/model_profiles.toml"),)
    if issues:
        for issue in issues:
            _print_role_view_issue(issue)
        return 1
    print("MODEL_PROFILE_ROLE_VIEWS=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
