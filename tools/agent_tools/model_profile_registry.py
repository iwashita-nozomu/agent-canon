from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import toml as tomllib

SCHEMA_IDS = {
    "registry": "model_profile_registry_v1",
    "registry_cli": "model_profile_registry_cli_v1",
    "execution_contract": "implementation_execution_contract_v1",
    "role_instruction_clause": "role_instruction_clause_v1",
    "role_instruction_template": "role_instruction_template_v1",
    "tool_call_token": "tool_call_token_v1",
    "generated_role_view": "generated_role_view_v1",
}


def _to_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModelProfileRegistryError(f"{field}:must_be_nonempty_string")
    return value


def _as_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ModelProfileRegistryError(f"{field}:must_be_string_list")
    return list(value)


class StructuralDesignGap(Exception):
    """Raised when an input contract contradicts the fixed implementation boundary."""


class ImplementationFeedback(Exception):
    """Raised for implementation-repairable runtime feedback."""


class ModelProfileRegistryError(ImplementationFeedback):
    """Malformed registry or materialization input."""


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
        return cls(schema_id=SCHEMA_IDS["execution_contract"], valid=True, issues=())

    @classmethod
    def fail(cls, issues: Iterable[ValidationIssue]) -> "ValidationResult":
        issues = tuple(issues)
        return cls(schema_id=SCHEMA_IDS["execution_contract"], valid=False, issues=issues)


@dataclass(frozen=True)
class RoleInstructionClause:
    clause_id: str
    text: str
    priority: int = 0
    schema_id: str = SCHEMA_IDS["role_instruction_clause"]


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
    schema_id: str
    skill_id: str
    tool_id: str
    arguments: Mapping[str, str]
    argument_schema_id: str
    failure_schema_id: str
    target: str


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
    route_id: str | None = None
    metadata: Mapping[str, str] | None = None


@dataclass(frozen=True)
class MaterializedPromptCapsule:
    schema_id: str
    profile_id: str
    role_id: str
    body: str
    context: tuple[ContextItem, ...]
    materialization_id: str


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
    rendered_instructions: str
    source_canonical_digest: str


@dataclass(frozen=True)
class EvidenceRequest:
    evidence_request_id: str
    target_state_id: str
    rationale: str


@dataclass(frozen=True)
class EvidenceRequestDecision:
    evidence_request_id: str
    authorized: bool
    rationale: str


@dataclass(frozen=True)
class DecisionSufficiencyRecord:
    plausible_state_ids: tuple[str, ...]
    current_state_id: str
    requested_state_id: str


@dataclass(frozen=True)
class OwnerEditValidationAction:
    owner: str
    edit: str
    validation: str


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
    owner: str
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

    def by_profile(self, profile_id: str) -> ModelProfile:
        for profile in self.model_profiles:
            if profile.id == profile_id:
                return profile
        raise ModelProfileRegistryError(f"model_profile:{profile_id}:not_found")


def _read_toml_file(path: Path) -> Mapping[str, Any]:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError as exc:
        raise ModelProfileRegistryError(f"file_not_found:{path}") from exc
    if not isinstance(data, Mapping):
        raise ModelProfileRegistryError(f"file:{path}:must_be_mapping")
    return data


def _read_json_file(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _load_role_profiles(path: Path) -> dict[str, str]:
    data = _read_json_file(path)
    roles = data.get("roles", []) if isinstance(data, Mapping) else []
    resolved: dict[str, str] = {}
    if not isinstance(roles, list):
        return resolved
    for role in roles:
        if not isinstance(role, Mapping):
            continue
        role_id = role.get("id") or role.get("role_id")
        profile_id = role.get("model_profile") or role.get("profile") or role.get("model_profile_id")
        if isinstance(role_id, str) and role_id and isinstance(profile_id, str) and profile_id:
            resolved[role_id] = profile_id
    return resolved


def _load_supported_profiles_from_tomls(path: Path, fallback: Iterable[str]) -> tuple[str, ...]:
    values: list[str] = []
    if not path.is_dir():
        return tuple(dict.fromkeys(fallback))
    seen: set[str] = set()
    for file in sorted(path.glob("*.toml")):
        if file.name == "README.toml":
            continue
        name = file.stem
        if name and name not in seen:
            seen.add(name)
            values.append(name)
    if values:
        return tuple(values)
    return tuple(dict.fromkeys(fallback))


def load_model_profile_registry(root: os.PathLike[str] | str = ".") -> ModelProfileRegistry:
    root_path = Path(root)
    data = _read_toml_file(root_path / "agents" / "model_profiles.toml")

    schema_id = _to_str(data.get("schema_id"), "schema_id")
    if schema_id != SCHEMA_IDS["registry"]:
        raise ModelProfileRegistryError("schema_id:mismatch")

    registry_id = _to_str(data.get("registry_id"), "registry_id")
    registry_version = data.get("registry_version")
    if not isinstance(registry_version, int):
        raise ModelProfileRegistryError("registry_version:must_be_int")

    raw_profiles = data.get("model_profiles")
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ModelProfileRegistryError("model_profiles:must_be_nonempty_list")

    profiles: list[ModelProfile] = []
    seen: set[str] = set()
    for item in raw_profiles:
        if not isinstance(item, Mapping):
            raise ModelProfileRegistryError("model_profiles_item:must_be_mapping")
        pid = _to_str(item.get("id"), "model_profile.id")
        if pid in seen:
            raise ModelProfileRegistryError(f"model_profile:{pid}:duplicate")
        seen.add(pid)
        model_alias = _to_str(item.get("model_alias"), "model_profile.model_alias")
        owner = _to_str(item.get("owner"), "model_profile.owner")
        role_template = _to_str(item.get("role_template"), "model_profile.role_template")
        close_skill_id = _to_str(item.get("close_skill_id"), "model_profile.close_skill_id")
        close_tool_id = _to_str(item.get("close_tool_id"), "model_profile.close_tool_id")
        close_arg_schema = _to_str(
            item.get("close_tool_argument_schema_id"), "model_profile.close_tool_argument_schema_id"
        )
        close_fail_schema = _to_str(
            item.get("close_tool_failure_schema_id"), "model_profile.close_tool_failure_schema_id"
        )
        close_binding = _to_str(item.get("close_tool_target_binding"), "model_profile.close_tool_target_binding")
        prompt_schema_id = _to_str(
            item.get("prompt_capsule_schema_id"), "model_profile.prompt_capsule_schema_id"
        )
        prompt_template = _to_str(
            item.get("prompt_capsule_template"), "model_profile.prompt_capsule_template"
        )
        prompt_required = _as_list(item.get("prompt_capsule_required_context"), "prompt_capsule_required_context")

        raw_clauses = item.get("role_instructions")
        if not isinstance(raw_clauses, list) or not raw_clauses:
            raise ModelProfileRegistryError(f"model_profile:{pid}:missing_role_instructions")
        clauses: list[RoleInstructionClause] = []
        for clause in raw_clauses:
            if not isinstance(clause, Mapping):
                raise ModelProfileRegistryError(f"model_profile:{pid}:invalid_clause")
            clauses.append(
                RoleInstructionClause(
                    clause_id=_to_str(clause.get("id"), "clause.id"),
                    text=_to_str(clause.get("text"), "clause.text"),
                    priority=int(clause.get("priority", 0) or 0),
                )
            )

        sorted_clauses = tuple(sorted(clauses, key=lambda c: (c.priority, c.clause_id)))
        role_template_obj = RoleInstructionTemplate(
            profile_id=pid,
            clauses=sorted_clauses,
            template_text=role_template,
        )

        profiles.append(
            ModelProfile(
                id=pid,
                model_alias=model_alias,
                owner=owner,
                role_template=role_template,
                prompt_capsule_schema=PromptCapsuleSchema(
                    schema_id=prompt_schema_id,
                    profile_id=pid,
                    template=prompt_template,
                    required_context=tuple(prompt_required),
                ),
                role_instruction_template=role_template_obj,
                tool_argument_schema=ToolArgumentSchema(
                    schema_id=close_arg_schema,
                    target=close_binding,
                    properties=("terminal_agent_id", "reason", "notes"),
                ),
                tool_argument_schema_id=close_arg_schema,
                tool_failure_schema_id=close_fail_schema,
                close_skill_id=close_skill_id,
                close_tool_id=close_tool_id,
            )
        )

    return ModelProfileRegistry(
        schema_id=schema_id,
        registry_id=registry_id,
        registry_version=registry_version,
        model_profiles=tuple(profiles),
    )


def _stable_digest(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(serialized).hexdigest()


def _context_block(context: tuple[ContextItem, ...]) -> str:
    if not context:
        return "- none"
    lines = [f"- {item.key}: {item.value}" for item in context]
    return "\n".join(lines)


def materialize_prompt_capsule(
    request: PromptMaterializationRequest,
    registry: ModelProfileRegistry,
) -> MaterializedPromptCapsule:
    profile = registry.by_profile(request.profile_id)
    required = set(profile.prompt_capsule_schema.required_context)
    provided = {c.key for c in request.context}
    if not required.issubset(provided):
        missing = ", ".join(sorted(required - provided))
        raise ModelProfileRegistryError(f"missing_context:{missing}")

    base_prompt = profile.role_instruction_template.template_text.format(
        role_id=request.role_id,
        model_alias=profile.model_alias,
        base_prompt=" ".join(c.text for c in profile.role_instruction_template.clauses),
    )
    body = profile.prompt_capsule_schema.template.format(
        role_id=request.role_id,
        model_alias=profile.model_alias,
        base_prompt=base_prompt,
        objective=request.objective,
        context_block=_context_block(request.context),
    )
    capsule_body = body.strip()
    materialization_id = _stable_digest(
        {
            "profile_id": request.profile_id,
            "role_id": request.role_id,
            "context": [(c.key, c.value) for c in request.context],
            "objective": request.objective,
        }
    )
    return MaterializedPromptCapsule(
        schema_id=profile.prompt_capsule_schema.schema_id,
        profile_id=request.profile_id,
        role_id=request.role_id,
        body=capsule_body,
        context=request.context,
        materialization_id=materialization_id,
    )


def materialize_tool_call_token(
    request: ToolCallMaterializationRequest, profile: ModelProfile | str, registry: ModelProfileRegistry
) -> ToolCallToken:
    if isinstance(profile, str):
        profile_obj = registry.by_profile(profile)
    elif isinstance(profile, ModelProfile):
        profile_obj = profile
    else:
        raise StructuralDesignGap("tool_call_token_request.profile.type")

    if request.terminal_agent_id.strip() == "":
        raise ModelProfileRegistryError("terminal_agent_id:must_be_nonempty")

    arguments = {
        profile_obj.tool_argument_schema.target: request.terminal_agent_id,
    }
    if request.route_id:
        arguments["route_id"] = request.route_id
    if request.metadata:
        arguments.update(request.metadata)

    return ToolCallToken(
        schema_id=SCHEMA_IDS["tool_call_token"],
        skill_id=profile_obj.close_skill_id,
        tool_id=profile_obj.close_tool_id,
        arguments=arguments,
        argument_schema_id=profile_obj.tool_argument_schema_id,
        failure_schema_id=profile_obj.tool_failure_schema_id,
        target=request.terminal_agent_id,
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
    context_items = tuple(context or ())
    prompt = materialize_prompt_capsule(
        PromptMaterializationRequest(
            profile_id=profile_id,
            role_id=role_id,
            context=context_items,
            objective=objective,
        ),
        registry,
    )
    token = materialize_tool_call_token(
        ToolCallMaterializationRequest(
            profile_id=profile_id,
            terminal_agent_id=terminal_agent_id,
            route_id=f"route:{role_id}:{profile_id}",
        ),
        profile_id,
        registry,
    )
    route_digest = _stable_digest(
        {
            "role_id": role_id,
            "profile_id": profile_id,
            "objective": objective,
            "terminal_agent_id": terminal_agent_id,
        }
    )
    return MaterializedRoutePacket(
        schema_id=SCHEMA_IDS["execution_contract"],
        route_id=f"route:{route_digest}",
        profile_id=profile_id,
        role_id=role_id,
        prompt_capsule=prompt,
        tool_call_token=token,
        generated_view_id=f"role-view:{role_id}:{profile_id}",
    )


def generate_role_views(
    registry: ModelProfileRegistry,
    root: os.PathLike[str] | str = ".",
    target_state_contract: Mapping[str, Any] | TargetStateContract | None = None,
) -> tuple[GeneratedRoleView, ...]:
    root_path = Path(root)
    role_profiles = _load_role_profiles(root_path / "agents" / "agents_config.json")
    if not role_profiles:
        role_profiles = _load_supported_profiles_from_tomls(
            root_path / ".codex" / "agents",
            [p.id for p in registry.model_profiles],
        )
        role_profiles = {role: list(role_profiles)[0] for role in role_profiles}

    views: list[GeneratedRoleView] = []
    for role_id, profile_id in role_profiles.items():
        model_profile = registry.by_profile(profile_id)
        clauses = " ".join(c.text for c in sorted(model_profile.role_instruction_template.clauses, key=lambda c: c.priority))
        view_id = f"generated-view:{role_id}:{profile_id}"
        content = model_profile.role_instruction_template.template_text.format(
            role_id=role_id,
            model_alias=model_profile.model_alias,
            base_prompt=clauses,
        )
        digest = _stable_digest({"view_id": view_id, "role_id": role_id, "profile_id": profile_id})
        views.append(
            GeneratedRoleView(
                schema_id=SCHEMA_IDS["generated_role_view"],
                view_id=view_id,
                role_id=role_id,
                profile_id=profile_id,
                rendered_instructions=content,
                source_canonical_digest=digest,
            )
        )

    # If contract supplies explicit role_profiles, merge with runtime-derived mapping.
    if isinstance(target_state_contract, Mapping):
        explicit = target_state_contract.get("supported_role_profiles")
        if isinstance(explicit, Mapping):
            for role_id, profile_id in explicit.items():
                if not isinstance(role_id, str) or not isinstance(profile_id, str):
                    continue
                model_profile = registry.by_profile(profile_id)
                clauses = " ".join(c.text for c in sorted(model_profile.role_instruction_template.clauses, key=lambda c: c.priority))
                view_id = f"generated-view:{role_id}:{profile_id}:contract"
                content = model_profile.role_instruction_template.template_text.format(
                    role_id=role_id,
                    model_alias=model_profile.model_alias,
                    base_prompt=clauses,
                )
                digest = _stable_digest(
                    {"view_id": view_id, "role_id": role_id, "profile_id": profile_id, "contract": True}
                )
                views.append(
                    GeneratedRoleView(
                        schema_id=SCHEMA_IDS["generated_role_view"],
                        view_id=view_id,
                        role_id=role_id,
                        profile_id=profile_id,
                        rendered_instructions=content,
                        source_canonical_digest=digest,
                    )
                )

    if not views:
        raise ModelProfileRegistryError("generated_role_views:empty")
    return tuple(views)


def validate_target_state_contract(
    target_state_contract: Mapping[str, Any],
    registry: ModelProfileRegistry,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    for pid in ("contract_id", "unit_id", "exact_owner", "owner", "profiles"):
        if pid not in target_state_contract:
            issues.append(ValidationIssue(code="missing_field", message=f"{pid}:missing", location=pid))

    profiles = target_state_contract.get("configured_supported_profiles")
    if profiles is None:
        profiles = target_state_contract.get("profiles")
    if not isinstance(profiles, list):
        issues.append(ValidationIssue(code="profiles", message="profiles:must_be_list", location="profiles"))
        return ValidationResult.fail(tuple(issues))

    profile_ids = {p.id for p in registry.model_profiles}
    for entry in profiles:
        if not isinstance(entry, str):
            issues.append(ValidationIssue(code="profiles", message="profiles:non_string_entry", location="profiles"))
            continue
        if entry not in profile_ids:
            issues.append(
                ValidationIssue(
                    code="unknown_profile",
                    message=f"configured_profile:{entry}:not_in_registry",
                    location="profiles",
                )
            )

    if issues:
        return ValidationResult.fail(tuple(issues))
    return ValidationResult.ok()


def validate_decision_sufficiency(
    record: DecisionSufficiencyRecord,
    request: EvidenceRequest | None = None,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    if record.current_state_id not in record.plausible_state_ids:
        issues.append(
            ValidationIssue(
                code="decision_sufficiency.current_state_invalid",
                message="current_state_id_not_plausible",
                location="current_state_id",
            )
        )
    if record.requested_state_id not in record.plausible_state_ids:
        issues.append(
            ValidationIssue(
                code="decision_sufficiency.requested_state_invalid",
                message="requested_state_id_not_plausible",
                location="requested_state_id",
            )
        )
    if request is not None and request.target_state_id not in record.plausible_state_ids:
        issues.append(
            ValidationIssue(
                code="evidence_request.target_state_invalid",
                message="evidence_request_target_state_invalid",
                location="evidence_request.target_state_id",
            )
        )

    if issues:
        return ValidationResult.fail(tuple(issues))
    return ValidationResult.ok()


def authorize_evidence_request(
    record: DecisionSufficiencyRecord,
    request: EvidenceRequest,
) -> EvidenceRequestDecision:
    authorized = (
        record.current_state_id in record.plausible_state_ids
        and request.target_state_id in record.plausible_state_ids
        and request.evidence_request_id is not None
    )
    reason = (
        "authorized" if authorized else "evidence_request_state_not_plausible"
    )
    if not authorized:
        raise ModelProfileRegistryError("evidence_request:unauthorized")
    return EvidenceRequestDecision(
        evidence_request_id=request.evidence_request_id,
        authorized=authorized,
        rationale=reason,
    )


def _as_target_state_projection(registry: ModelProfileRegistry, target_state_contract: Mapping[str, Any]) -> TargetStateContract:
    profiles = tuple(str(p) for p in target_state_contract.get("profiles", ()))
    configured = tuple(str(p) for p in target_state_contract.get("configured_supported_profiles", ()))
    return TargetStateContract(
        contract_id=_to_str(target_state_contract.get("contract_id"), "target_state_contract.contract_id"),
        unit_id=_to_str(target_state_contract.get("unit_id"), "target_state_contract.unit_id"),
        owner=_to_str(target_state_contract.get("owner"), "target_state_contract.owner"),
        exact_owner=_to_str(target_state_contract.get("exact_owner"), "target_state_contract.exact_owner"),
        schema_id=_to_str(target_state_contract.get("schema_id", "implementation_execution_contract_v1"), "target_state_contract.schema_id"),
        profiles=profiles,
        configured_supported_profiles=configured,
    )


def materialize_contract_projection(
    target_state_contract: Mapping[str, Any],
    root: os.PathLike[str] | str = ".",
) -> ImplementationExecutionContract:
    registry = load_model_profile_registry(root)
    result = validate_target_state_contract(target_state_contract, registry)
    if not result.valid:
        issues = ", ".join(issue.code for issue in result.issues)
        raise ModelProfileRegistryError(f"target_state_contract_validation_failed:{issues}")

    views = generate_role_views(registry, root=root, target_state_contract=target_state_contract)
    contract = _as_target_state_projection(registry, target_state_contract)
    return ImplementationExecutionContract(
        contract_id=contract.contract_id,
        generated_views=views,
        tool_tokens=tuple(),
    )


def _role_view_issues(root: Path) -> tuple[ValidationIssue, ...]:
    registry = load_model_profile_registry(root)
    views = generate_role_views(registry, root=root)
    issues: list[ValidationIssue] = []

    for view in sorted(views, key=lambda item: (item.role_id, item.profile_id, item.view_id)):
        relative_path = Path(".codex") / "agents" / f"{view.role_id}.toml"
        executable_path = root / relative_path
        location = relative_path.as_posix()
        try:
            executable_bytes = executable_path.read_bytes()
        except FileNotFoundError:
            issues.append(
                ValidationIssue(
                    code="role_view.missing",
                    message="declared executable role view is missing",
                    location=location,
                )
            )
            continue

        try:
            executable_data = tomllib.loads(executable_bytes.decode("utf-8"))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            issues.append(
                ValidationIssue(
                    code="role_view.schema_drift",
                    message="executable role view is not valid UTF-8 TOML",
                    location=location,
                )
            )
            continue

        if executable_data.get("name") != view.role_id:
            issues.append(
                ValidationIssue(
                    code="role_view.schema_drift",
                    message=f"name must equal declared role_id {view.role_id}",
                    location=location,
                )
            )

        executable_instructions = executable_data.get("developer_instructions")
        if not isinstance(executable_instructions, str):
            issues.append(
                ValidationIssue(
                    code="role_view.schema_drift",
                    message="developer_instructions must be a string",
                    location=location,
                )
            )
            continue

        generated_bytes = view.rendered_instructions.encode("utf-8")
        executable_instruction_bytes = executable_instructions.encode("utf-8")
        if generated_bytes != executable_instruction_bytes:
            issues.append(
                ValidationIssue(
                    code="role_view.content_drift",
                    message="generated instructions differ from executable role view",
                    location=location,
                )
            )

    return tuple(sorted(issues, key=lambda issue: (issue.location or "", issue.code, issue.message)))


def _print_role_view_issue(issue: ValidationIssue) -> None:
    payload = {
        "code": issue.code,
        "location": issue.location,
        "message": issue.message,
        "schema_id": SCHEMA_IDS["registry_cli"],
    }
    print(
        "MODEL_PROFILE_ROLE_VIEW_ISSUE="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="model_profile_registry.py")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--check-role-views", required=True, action="store_true")
    args = parser.parse_args(argv)

    try:
        issues = _role_view_issues(args.root)
    except (ModelProfileRegistryError, OSError) as exc:
        issues = (
            ValidationIssue(
                code="role_view.schema_drift",
                message=str(exc),
                location="agents/model_profiles.toml",
            ),
        )

    if issues:
        for issue in issues:
            _print_role_view_issue(issue)
        return 1

    print("MODEL_PROFILE_ROLE_VIEWS=pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
