#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns public skill-route catalog parsing, typed dependency-map validation, frozen rule/index values, root errors, and related-skill projections.
# upstream design ../../../agents/skills/oop-type-design.md approved OOP/type-design owner and module contract
# upstream implementation ../../../agents/skills/catalog.yaml complete public skill-route catalog and capability metadata
# upstream implementation ../../../agents/skills/skill-dependencies.yaml canonical public-skill dependency dictionary
# upstream implementation ../../validation/semantic/tools/visualization_contract.py owns the canonical visualization ToolCall schemas
# downstream implementation ../orchestration/capability_route.py immutable capability decision consumer
# downstream implementation ../orchestration/route.py public route composition and compatibility facade
# downstream implementation ../../validation/semantic/runtime/check_agent_runtime_alignment.py registration/path parity consumer
# downstream implementation ../../../tests/agent_tools/test_route.py catalog-owned route tests
# @dependency-end
"""Load AgentCanon skill-route catalog records and immutable indexes."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, cast

try:
    import yaml
except ModuleNotFoundError:  # clean host before the shared tool image exists
    try:
        from tools.runtime.container import stdlib_yaml as yaml
    except ImportError:
        import tools.runtime.container.stdlib_yaml as yaml  # type: ignore[no-redef]
from tools.validation.semantic.tools.visualization_contract import (
    TOOL_ARGUMENT_SCHEMAS,
    ArgumentSchemaID,
    ToolCall,
    ToolID,
    VisualizationSourceItem,
    serialize_tool_call,
)

__all__ = (
    "CapabilityId",
    "CapabilityCatalogError",
    "CapabilityRootError",
    "CapabilityRoute",
    "CapabilityIndex",
    "SkillToolCommandSpec",
    "SkillRoutingRule",
    "SkillDependencyRule",
    "SkillOrderConstraint",
    "VisualizationOwnerSkill",
    "VisualizationRejection",
    "VISUALIZATION_OWNER_SKILL",
    "VISUALIZATION_OWNER_TOOL_ID",
    "VISUALIZATION_OWNER_ARGUMENT_SCHEMA",
    "VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID",
    "VISUALIZATION_DEPENDENCY_ADAPTER_ARGUMENT_SCHEMA",
    "VISUALIZATION_ADAPTER_TOOL_IDS",
    "VISUALIZATION_CAPABILITY_ADAPTERS",
    "VISUALIZATION_ROLE_VALUES",
    "build_visualization_owner_tool_call",
    "build_visualization_adapter_tool_call",
    "visualization_adapter_for_capability",
    "visualization_rejection_from_error",
    "capability_id_from_raw",
    "capability_routes",
    "freeze_related_skill_mapping",
    "freeze_capability_route_mapping",
    "freeze_skill_rule_mapping",
    "load_skill_route_rules",
    "load_skill_route_rules_from_root",
    "load_skill_dependency_map",
    "build_skill_dependency_edges",
    "derive_skill_invocation_order",
    "load_skill_related_map",
    "load_skill_required_tool_commands",
    "load_skill_tool_commands",
    "build_capability_index",
    "ordered_unique",
    "related_skill_candidates",
    "validate_catalog_schemas",
)

JsonMapping = Mapping[str, object]
CapabilityId = str
SKILL_CATALOG_PATH = Path("agents/skills/catalog.yaml")
SKILL_DEPENDENCY_MAP_PATH = Path("agents/skills/skill-dependencies.yaml")
TOOL_CATALOG_PATH = Path("tools/catalog.yaml")
CATALOG_SCHEMA_ROOT = Path("schemas/agent-canon")
CATALOG_SCHEMA_PATHS = {
    SKILL_CATALOG_PATH: CATALOG_SCHEMA_ROOT / "skill-catalog.schema.json",
    SKILL_DEPENDENCY_MAP_PATH: CATALOG_SCHEMA_ROOT / "skill-dependencies.schema.json",
    TOOL_CATALOG_PATH: CATALOG_SCHEMA_ROOT / "tool-catalog.schema.json",
}
_SCHEMA_PREFLIGHT_CACHE: dict[
    Path, tuple[tuple[tuple[str, int, int], ...], tuple[Mapping[str, object], ...]]
] = {}
PRIVATE_SKILL_PREFIX = "_"
CAPABILITY_ID_RE = re.compile(r"^[a-z0-9_]+$")
VisualizationOwnerSkill = Literal["code-visualization"]
VisualizationRejection = Literal[
    "missing_owner",
    "invalid_tool_call",
    "prose_only",
    "schema_mismatch",
]
VISUALIZATION_OWNER_SKILL: VisualizationOwnerSkill = "code-visualization"
VISUALIZATION_ROLE_VALUES = ("owner", "adapter")
VISUALIZATION_OWNER_TOOL_ID: ToolID = "agent_canon.visualization.coverage"
VISUALIZATION_OWNER_ARGUMENT_SCHEMA: ArgumentSchemaID = (
    "agent_canon.visualization.arguments.coverage.v1"
)
VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID: ToolID = (
    "agent_canon.visualization.adapter.dependency_manifest"
)
VISUALIZATION_DEPENDENCY_ADAPTER_ARGUMENT_SCHEMA: ArgumentSchemaID = (
    "agent_canon.visualization.arguments.dependency_manifest.v1"
)
VISUALIZATION_ADAPTER_TOOL_IDS: tuple[ToolID, ...] = tuple(
    tool_id
    for tool_id in TOOL_ARGUMENT_SCHEMAS
    if tool_id != VISUALIZATION_OWNER_TOOL_ID
)
VISUALIZATION_CAPABILITY_ADAPTERS: MappingProxyType = MappingProxyType(
    {
        "dependency_manifest_graph": VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID,
    }
)
_VISUALIZATION_ADAPTER_LOCATORS: MappingProxyType = MappingProxyType(
    {
        "agent_canon.visualization.adapter.dependency_manifest": {
            "dependency_manifest_locator": (
                "tools/analysis/dependencies/render_dependency_manifest_graph.py"
            )
        },
        "agent_canon.visualization.adapter.algorithm_flowchart": {
            "jit_ir_locator": "tools/analysis/proof/jit_canonical_ir.py",
            "lean_evidence_locator": "tools/analysis/proof/operational_ir_to_lean.py",
            "theorem_graph_locator": "tools/analysis/proof/theorem_graph_board.py",
        },
        "agent_canon.visualization.adapter.document_mermaid": {
            "document_locator": "documents/runtime/skill-dependency-graph.md"
        },
        "agent_canon.visualization.adapter.repository_graph": {
            "repository_locator": "documents"
        },
        "agent_canon.visualization.adapter.knowledge_graph": {
            "graph_locator": "documents"
        },
    }
)


def _route_identity(*parts: str) -> str:
    """Return one deterministic route-owned identity."""
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _route_source_item(
    *,
    item_id: str,
    kind: Literal["identity", "module"],
    origin: Literal["literal_request", "owner_closure"],
    source_locator: str,
    ordinal: int,
    payload: Mapping[str, object],
) -> VisualizationSourceItem:
    """Build one exact route-stage source item for the owner ToolCall."""
    return {
        "item_id": item_id,
        "kind": kind,
        "origin": origin,
        "source_locator": source_locator,
        "source_start": None,
        "source_end": None,
        "ordinal": ordinal,
        "payload_json": json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
    }


def build_visualization_owner_tool_call(
    literal_request: str,
    source_locator: str,
) -> ToolCall:
    """Build and validate the sole route-owned visualization ToolCall."""
    request_id = _route_identity("visualization-route", literal_request)
    literal_item = _route_source_item(
        item_id=_route_identity("literal-request", literal_request),
        kind="identity",
        origin="literal_request",
        source_locator=source_locator,
        ordinal=0,
        payload={"literal_request": literal_request},
    )
    owner_item = _route_source_item(
        item_id=_route_identity("visualization-owner", VISUALIZATION_OWNER_SKILL),
        kind="module",
        origin="owner_closure",
        source_locator="agents/skills/code-visualization.md",
        ordinal=0,
        payload={"owner_skill": VISUALIZATION_OWNER_SKILL},
    )
    call: ToolCall = {
        "schema": "agent_canon.visualization_tool_call.v1",
        "tool_id": VISUALIZATION_OWNER_TOOL_ID,
        "argument_schema": VISUALIZATION_OWNER_ARGUMENT_SCHEMA,
        "arguments": {
            "request_id": request_id,
            "literal_request": literal_request,
            "literal_items": [literal_item],
            "owner_closure": [owner_item],
            "dependency_closure": [],
            "artifact_id": f"route-coverage-{request_id[:16]}",
            "renderer_id": "code-visualization-owner-route",
            "artifact_format": "graph_ir",
        },
    }
    serialize_tool_call(call)
    return call


def build_visualization_adapter_tool_call(
    owner_call: ToolCall,
    *,
    adapter_tool_id: ToolID = VISUALIZATION_DEPENDENCY_ADAPTER_TOOL_ID,
    adapter_arguments: Mapping[str, object] | None = None,
) -> ToolCall:
    """Build one selected adapter call after a validated owner call."""
    serialize_tool_call(owner_call)
    if adapter_tool_id not in VISUALIZATION_ADAPTER_TOOL_IDS:
        raise ValueError("invalid_visualization_adapter_tool_id")
    arguments = dict(owner_call["arguments"])
    locator_arguments = _VISUALIZATION_ADAPTER_LOCATORS[adapter_tool_id]
    for field, default in locator_arguments.items():
        arguments[field] = (
            adapter_arguments[field]
            if adapter_arguments is not None and field in adapter_arguments
            else default
        )
    adapter: ToolCall = {
        "schema": "agent_canon.visualization_tool_call.v1",
        "tool_id": adapter_tool_id,
        "argument_schema": TOOL_ARGUMENT_SCHEMAS[adapter_tool_id],
        "arguments": arguments,
    }
    serialize_tool_call(adapter)
    return adapter


def visualization_adapter_for_capability(capability_id: str) -> ToolID | None:
    """Return the catalog-owned adapter selected by one typed capability."""
    adapter = VISUALIZATION_CAPABILITY_ADAPTERS.get(capability_id)
    return cast(ToolID | None, adapter)


def visualization_rejection_from_error(error: ValueError) -> VisualizationRejection:
    """Map canonical ToolCall validation errors to the fixed route rejection."""
    if str(error).startswith("schema_mismatch:"):
        return "schema_mismatch"
    return "invalid_tool_call"


@dataclass(frozen=True)
class CapabilityRoute:
    """One catalog capability route owned by a public skill."""

    skill: str
    capability_id: CapabilityId
    owner: str
    phase: str
    activation: str
    exclusive: bool


@dataclass(frozen=True)
class SkillToolCommandSpec:
    """Structured command phases owned by one public skill catalog entry."""

    required: tuple[str, ...] = ()
    conditional: tuple[str, ...] = ()
    maintenance: tuple[str, ...] = ()
    structured: bool = True


@dataclass(frozen=True)
class SkillRoutingRule:
    """One catalog-backed prompt and capability routing rule."""

    skill: str
    reason: str
    stage_policy: str
    triggers: tuple[tuple[str, ...], ...]
    capabilities: tuple[CapabilityRoute, ...]
    related_skills: tuple[str, ...]
    visualization_owner_skill: VisualizationOwnerSkill | None = None
    visualization_tool_call: ToolCall | None = None
    visualization_rejection: VisualizationRejection | None = None
    visualization_role: str = ""
    tool_id: str = ""
    argument_schema: str = ""
    required_prerequisites: tuple[str, ...] = ()
    successors: tuple[str, ...] = ()
    order_constraints: tuple[SkillOrderConstraint, ...] = ()
    parallel_independent: tuple[str, ...] = ()
    responsibility_group: str = ""


@dataclass(frozen=True)
class SkillOrderConstraint:
    """One explicit ordering edge in the canonical skill dependency map."""

    before: str
    after: str
    reason: str


@dataclass(frozen=True)
class SkillDependencyRule:
    """One public skill's canonical dependency and parallel-work contract."""

    skill: str
    responsibility_group: str
    required_prerequisites: tuple[str, ...]
    routing_candidates: tuple[str, ...]
    successors: tuple[str, ...]
    order_constraints: tuple[SkillOrderConstraint, ...]
    parallel_independent: tuple[str, ...]


class CapabilityCatalogError(ValueError):
    """One fixed malformed catalog capability-record error."""

    def __init__(self, code: str) -> None:
        """Initialize with one stable catalog error code."""
        super().__init__(code)
        self.code = code


class CapabilityRootError(ValueError):
    """One fixed custom-root resolution or catalog-load error."""

    def __init__(self, code: str) -> None:
        """Initialize with one stable root error code."""
        super().__init__(code)
        self.code = code


def validate_catalog_schemas(root: Path) -> tuple[Mapping[str, object], ...]:
    """Run pinned native YAML and JSON Schema validation for catalog sources.

    This is an admission/preflight operation.  The loaders below intentionally
    consume its typed-compatible YAML values and retain only cross-document
    relations and projection checks.
    """
    root = root.resolve()
    fingerprint = tuple(
        (
            path.as_posix(),
            path.stat().st_mtime_ns,
            path.stat().st_size,
        )
        for path in tuple(root / path for path in CATALOG_SCHEMA_PATHS)
    )
    cached = _SCHEMA_PREFLIGHT_CACHE.get(root)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    yamllint = shutil.which("yamllint")
    check_jsonschema = shutil.which("check-jsonschema")
    if yamllint is None or check_jsonschema is None:
        missing = "yamllint" if yamllint is None else "check-jsonschema"
        raise CapabilityRootError(f"catalog-schema-tool-unavailable:{missing}")
    documents = tuple(root / path for path in CATALOG_SCHEMA_PATHS)
    config = root / CATALOG_SCHEMA_ROOT / "yamllint.yaml"
    if not config.is_file():
        raise CapabilityRootError("catalog-schema-config-missing")
    yaml_result = subprocess.run(
        [yamllint, "--strict", "--config-file", str(config), *(str(path) for path in documents)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if yaml_result.returncode != 0:
        raise CapabilityRootError("catalog-yaml-invalid")
    results: list[Mapping[str, object]] = []
    for document, schema in zip(documents, CATALOG_SCHEMA_PATHS.values()):
        schema_path = root / schema
        result = subprocess.run(
            [check_jsonschema, "--schemafile", str(schema_path), str(document)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CapabilityRootError(
                f"catalog-schema-invalid:{document.relative_to(root).as_posix()}"
            )
        results.append(
            {
                "tool": "check-jsonschema",
                "schema": schema.as_posix(),
                "document": document.relative_to(root).as_posix(),
                "argv": ["--schemafile", schema.as_posix(), document.relative_to(root).as_posix()],
                "exit_code": result.returncode,
            }
        )
    validated = tuple(results)
    _SCHEMA_PREFLIGHT_CACHE[root] = (fingerprint, validated)
    return validated


@dataclass(frozen=True)
class CapabilityIndex:
    """Catalog-ordered immutable capability index and diagnostics."""

    routes: Mapping[CapabilityId, CapabilityRoute]
    rules_by_skill: Mapping[str, SkillRoutingRule]
    owner_ambiguities: tuple[CapabilityId, ...]
    duplicate_definitions: tuple[CapabilityId, ...]

    def __post_init__(self) -> None:
        """Freeze mapping fields after dataclass construction."""
        object.__setattr__(
            self,
            "routes",
            freeze_capability_route_mapping(self.routes, "routes"),
        )
        object.__setattr__(
            self,
            "rules_by_skill",
            freeze_skill_rule_mapping(self.rules_by_skill, "rules_by_skill"),
        )


def object_mapping(value: object, field: str) -> JsonMapping:
    """Return one schema-validated mapping from parsed catalog data.

    Structural shape validation is owned by the local Draft 2020-12 schemas
    and ``check-jsonschema``.  This conversion deliberately performs no
    duplicate type/required/property checks; callers are the relational and
    typed-projection owners after native validation has completed.
    """
    del field
    return cast(JsonMapping, value)


def object_sequence(value: object, field: str) -> Sequence[object]:
    """Return one schema-validated sequence from parsed catalog data."""
    del field
    return cast(Sequence[object], value)


def load_skill_catalog(root: Path) -> JsonMapping:
    """Load the machine-readable public skill catalog."""
    path = root / SKILL_CATALOG_PATH
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{SKILL_CATALOG_PATH} YAML parse failed: {exc}") from exc
    return object_mapping(raw, str(SKILL_CATALOG_PATH))


def string_list(value: object, field: str) -> tuple[str, ...]:
    """Return one schema-validated string sequence as an immutable tuple."""
    del field
    return tuple(cast(Sequence[str], value))


def trigger_groups(value: object, field: str) -> tuple[tuple[str, ...], ...]:
    """Return schema-validated trigger term groups from YAML."""
    del field
    if value is None:
        return ()
    return tuple(tuple(cast(Sequence[str], group)) for group in cast(Sequence[object], value))


def optional_string_list(value: object, field: str) -> tuple[str, ...]:
    """Return an optional schema-validated string list."""
    del field
    if value is None:
        return ()
    return tuple(cast(Sequence[str], value))


def optional_metadata_string(value: object, field: str) -> str:
    """Return one optional schema-validated metadata string."""
    del field
    if value is None:
        return ""
    return cast(str, value)


def _skill_ids_from_catalog(data: JsonMapping) -> tuple[str, ...]:
    """Return public skill identities; uniqueness is a residual relation."""
    families = object_sequence(data.get("skill_families"), "skill_families")
    ids: list[str] = []
    for index, entry in enumerate(families):
        mapping = object_mapping(entry, f"skill_families[{index}]")
        skill_id = cast(str, mapping["id"])
        if skill_id.startswith(PRIVATE_SKILL_PREFIX):
            raise ValueError(f"skill_families[{index}].id must be public: {skill_id}")
        if skill_id in ids:
            raise ValueError(f"duplicate skill catalog id: {skill_id}")
        ids.append(skill_id)
    return tuple(ids)


def _dependency_string_list(value: object, field: str) -> tuple[str, ...]:
    """Project one schema-validated dependency string list."""
    del field
    return tuple(cast(Sequence[str], value))


def _dependency_order_constraints(
    value: object, skill: str
) -> tuple[SkillOrderConstraint, ...]:
    """Project schema-validated ordering constraints for graph checks."""
    del skill
    return tuple(
        SkillOrderConstraint(
            cast(str, cast(Mapping[str, object], item)["before"]),
            cast(str, cast(Mapping[str, object], item)["after"]),
            cast(str, cast(Mapping[str, object], item)["reason"]),
        )
        for item in cast(Sequence[object], value)
    )


def _dependency_edges(
    rules: Mapping[str, SkillDependencyRule],
) -> dict[str, set[str]]:
    """Build the directed dependency/order graph from one canonical map."""
    edges = {skill: set() for skill in rules}
    for rule in rules.values():
        for prerequisite in rule.required_prerequisites:
            edges[prerequisite].add(rule.skill)
        for successor in rule.successors:
            edges[rule.skill].add(successor)
        for constraint in rule.order_constraints:
            edges[constraint.before].add(constraint.after)
    return edges


def _reachable(edges: Mapping[str, set[str]], source: str, target: str) -> bool:
    """Return whether target is reachable from source in the directed graph."""
    pending = list(edges[source])
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(edges[current])
    return False


def _validate_dependency_graph(rules: Mapping[str, SkillDependencyRule]) -> None:
    """Reject cycles, contradictory order, and conflicting parallel relations."""
    edges = _dependency_edges(rules)
    for rule in rules.values():
        for constraint in rule.order_constraints:
            if constraint.before == constraint.after or _reachable(
                edges, constraint.after, constraint.before
            ):
                raise ValueError(
                    "skill-dependency-map-order-contradiction:"
                    f"{constraint.before}:{constraint.after}"
                )
    indegree = {skill: 0 for skill in rules}
    for targets in edges.values():
        for target in targets:
            indegree[target] += 1
    ready = [skill for skill, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for target in edges[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if visited != len(rules):
        raise ValueError("skill-dependency-map-cycle")
    for rule in rules.values():
        for parallel in rule.parallel_independent:
            if (
                parallel == rule.skill
                or _reachable(edges, rule.skill, parallel)
                or _reachable(edges, parallel, rule.skill)
            ):
                raise ValueError(
                    "skill-dependency-map-parallel-contradiction:"
                    f"{rule.skill}:{parallel}"
                )
            if rule.skill not in rules[parallel].parallel_independent:
                raise ValueError(
                    "skill-dependency-map-parallel-not-symmetric:"
                    f"{rule.skill}:{parallel}"
                )


def load_skill_dependency_map(
    root: Path, public_skill_ids: Sequence[str] | None = None
) -> Mapping[str, SkillDependencyRule]:
    """Load and validate the complete public-skill dependency dictionary."""
    path = root / SKILL_DEPENDENCY_MAP_PATH
    try:
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError("skill-dependency-map-unavailable") from exc
    data = object_mapping(raw, str(SKILL_DEPENDENCY_MAP_PATH))
    dependency_data = object_mapping(
        data.get("skill_dependencies"), "skill_dependencies"
    )
    expected_ids = tuple(
        public_skill_ids or _skill_ids_from_catalog(load_skill_catalog(root))
    )
    observed_ids = tuple(str(key) for key in dependency_data)
    missing = tuple(skill for skill in expected_ids if skill not in dependency_data)
    extra = tuple(skill for skill in observed_ids if skill not in expected_ids)
    if missing or extra:
        raise ValueError(
            "skill-dependency-map-key-mismatch:"
            f"missing={','.join(missing) or '-'}:extra={','.join(extra) or '-'}"
        )
    rules: dict[str, SkillDependencyRule] = {}
    for skill in expected_ids:
        mapping = object_mapping(dependency_data[skill], f"skill_dependencies.{skill}")
        group = cast(str, mapping["responsibility_group"])
        rules[skill] = SkillDependencyRule(
            skill=skill,
            responsibility_group=group,
            required_prerequisites=_dependency_string_list(
                mapping.get("required_prerequisites"),
                f"{skill}.required_prerequisites",
            ),
            routing_candidates=(
                _dependency_string_list(
                    mapping.get("routing_candidates"),
                    f"{skill}.routing_candidates",
                )
                if mapping.get("routing_candidates") is not None
                else ()
            ),
            successors=_dependency_string_list(
                mapping.get("successors"), f"{skill}.successors"
            ),
            order_constraints=_dependency_order_constraints(
                mapping.get("order_constraints"), skill
            ),
            parallel_independent=_dependency_string_list(
                mapping.get("parallel_independent"),
                f"{skill}.parallel_independent",
            ),
        )
    for rule in rules.values():
        for field, references in (
            ("required_prerequisites", rule.required_prerequisites),
            ("routing_candidates", rule.routing_candidates),
            ("successors", rule.successors),
            ("parallel_independent", rule.parallel_independent),
        ):
            for reference in references:
                if reference not in rules:
                    raise ValueError(
                        "skill-dependency-map-unknown-reference:"
                        f"{rule.skill}:{field}:{reference}"
                    )
                if reference == rule.skill:
                    raise ValueError(
                        f"skill-dependency-map-self-reference:{rule.skill}:{field}"
                    )
        for constraint in rule.order_constraints:
            for reference in (constraint.before, constraint.after):
                if reference not in rules:
                    raise ValueError(
                        "skill-dependency-map-unknown-reference:"
                        f"{rule.skill}:order_constraints:{reference}"
                    )
    _validate_dependency_graph(rules)
    return rules


def build_skill_dependency_edges(
    rules: Mapping[str, SkillDependencyRule],
) -> Mapping[str, tuple[str, ...]]:
    """Return catalog-ordered directed prerequisite and ordering edges."""
    edges = _dependency_edges(rules)
    return MappingProxyType(
        {
            skill: tuple(target for target in rules if target in edges[skill])
            for skill in rules
        }
    )


def derive_skill_invocation_order(
    skills: Sequence[str], rules: Sequence[SkillRoutingRule]
) -> tuple[str, ...]:
    """Expand required prerequisites and topologically order selected skills."""
    by_skill = {rule.skill: rule for rule in rules}
    selected = set(skills)
    pending = list(selected)
    while pending:
        skill = pending.pop()
        if skill not in by_skill:
            raise ValueError(f"unknown-skill:{skill}")
        for prerequisite in by_skill[skill].required_prerequisites:
            if prerequisite not in selected:
                selected.add(prerequisite)
                pending.append(prerequisite)
    order_index = {rule.skill: index for index, rule in enumerate(rules)}
    edges = {skill: set() for skill in selected}
    for skill in selected:
        rule = by_skill[skill]
        for prerequisite in rule.required_prerequisites:
            if prerequisite in selected:
                edges[prerequisite].add(skill)
        for successor in rule.successors:
            if successor in selected:
                edges[skill].add(successor)
        for constraint in rule.order_constraints:
            if constraint.before in selected and constraint.after in selected:
                edges[constraint.before].add(constraint.after)
    indegree = {skill: 0 for skill in selected}
    for targets in edges.values():
        for target in targets:
            indegree[target] += 1
    ready = sorted(
        (skill for skill, degree in indegree.items() if degree == 0),
        key=order_index.__getitem__,
    )
    result: list[str] = []
    while ready:
        current = ready.pop(0)
        result.append(current)
        for target in sorted(edges[current], key=order_index.__getitem__):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
        ready.sort(key=order_index.__getitem__)
    if len(result) != len(selected):
        raise ValueError("skill-dependency-map-cycle")
    return tuple(result)


def validate_visualization_metadata(rules: Sequence[SkillRoutingRule]) -> None:
    """Enforce one public visualization owner and complete adapter metadata."""
    visual_rules = tuple(
        rule
        for rule in rules
        if any(
            (
                rule.visualization_owner_skill,
                rule.visualization_tool_call,
                rule.visualization_rejection,
                rule.visualization_role,
                rule.tool_id,
                rule.argument_schema,
            )
        )
    )
    if not visual_rules:
        return
    owners = tuple(rule for rule in visual_rules if rule.visualization_role == "owner")
    if len(owners) != 1 or owners[0].skill != VISUALIZATION_OWNER_SKILL:
        raise ValueError("visualization-catalog-owner-must-be-code-visualization")
    for rule in visual_rules:
        if rule.visualization_role not in VISUALIZATION_ROLE_VALUES:
            raise ValueError(f"{rule.skill}.visualization_role invalid")
        if rule.visualization_owner_skill != VISUALIZATION_OWNER_SKILL:
            raise ValueError(f"{rule.skill}.visualization_owner invalid")
        if not rule.tool_id:
            raise ValueError(f"{rule.skill}.tool_id required")
        if not rule.argument_schema:
            raise ValueError(f"{rule.skill}.argument_schema required")
        if rule.tool_id not in TOOL_ARGUMENT_SCHEMAS:
            raise ValueError(f"{rule.skill}.tool_id invalid_tool_call")
        expected_schema = TOOL_ARGUMENT_SCHEMAS[cast(ToolID, rule.tool_id)]
        if rule.argument_schema != expected_schema:
            raise ValueError(f"{rule.skill}.argument_schema schema_mismatch")
        if rule.visualization_tool_call is None:
            raise ValueError(f"{rule.skill}.visualization_tool_call required")
        serialize_tool_call(rule.visualization_tool_call)
        if (
            rule.visualization_tool_call["tool_id"] != VISUALIZATION_OWNER_TOOL_ID
            or rule.visualization_tool_call["argument_schema"]
            != VISUALIZATION_OWNER_ARGUMENT_SCHEMA
        ):
            raise ValueError(f"{rule.skill}.visualization_tool_call invalid")
        if rule.visualization_rejection is not None:
            raise ValueError(f"{rule.skill}.visualization_rejection must be null")
        if rule.visualization_role == "owner" and (
            rule.tool_id != VISUALIZATION_OWNER_TOOL_ID
            or rule.argument_schema != VISUALIZATION_OWNER_ARGUMENT_SCHEMA
        ):
            raise ValueError("visualization-catalog-owner-tool-call-invalid")
        if (
            rule.visualization_role == "adapter"
            and rule.tool_id == VISUALIZATION_OWNER_TOOL_ID
        ):
            raise ValueError(f"{rule.skill}.adapter_tool_id invalid")
    observed_pairs = {(rule.tool_id, rule.argument_schema) for rule in visual_rules}
    required_pairs = set(TOOL_ARGUMENT_SCHEMAS.items())
    if observed_pairs != required_pairs:
        raise ValueError("visualization-catalog-tool-pairs-incomplete")


def capability_id_from_raw(value: str) -> CapabilityId:
    """Normalize and validate one explicit capability identifier."""
    raw = value.strip()
    if not raw or CAPABILITY_ID_RE.fullmatch(raw) is None:
        raise ValueError(f"invalid-capability-id:{value}")
    return raw


def _capability_catalog_error(skill: str, field: str) -> CapabilityCatalogError:
    return CapabilityCatalogError(f"capability-catalog-invalid:{skill}:{field}")


def capability_routes(
    value: object,
    field: str,
    skill: str,
) -> tuple[CapabilityRoute, ...]:
    """Parse one catalog capability sequence into frozen route records."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _capability_catalog_error(skill, field)
    routes: list[CapabilityRoute] = []
    required_keys = {"id", "owner", "phase", "activation", "exclusive"}
    for index, raw_record in enumerate(value):
        record_field = f"{field}[{index}]"
        if not isinstance(raw_record, Mapping):
            raise _capability_catalog_error(skill, record_field)
        record = cast(Mapping[object, object], raw_record)
        if set(record) != required_keys:
            raise _capability_catalog_error(skill, record_field)
        values = {key: record[key] for key in ("id", "owner", "phase", "activation")}
        if any(
            not isinstance(item, str)
            or not item.strip()
            or re.fullmatch(r"[a-z0-9_]+", item) is None
            for item in values.values()
        ):
            invalid_field = next(
                key
                for key, item in values.items()
                if not isinstance(item, str)
                or not item.strip()
                or re.fullmatch(r"[a-z0-9_]+", item) is None
            )
            raise _capability_catalog_error(skill, f"{record_field}.{invalid_field}")
        if not isinstance(record["exclusive"], bool):
            raise _capability_catalog_error(skill, f"{record_field}.exclusive")
        try:
            capability_id = capability_id_from_raw(cast(str, record["id"]))
        except ValueError as exc:
            raise _capability_catalog_error(skill, f"{record_field}.id") from exc
        routes.append(
            CapabilityRoute(
                skill=skill,
                capability_id=capability_id,
                owner=cast(str, record["owner"]),
                phase=cast(str, record["phase"]),
                activation=cast(str, record["activation"]),
                exclusive=cast(bool, record["exclusive"]),
            )
        )
    return tuple(routes)


def freeze_related_skill_mapping(
    value: Mapping[str, tuple[str, ...]],
    field: str,
) -> Mapping[str, tuple[str, ...]]:
    """Copy a related-skill mapping into an immutable insertion-ordered view."""
    if not isinstance(value, Mapping):
        raise TypeError(f"invalid-route-mapping:{field}")
    copied: dict[str, tuple[str, ...]] = {}
    for key, related in value.items():
        if (
            not isinstance(key, str)
            or not isinstance(related, tuple)
            or not all(isinstance(item, str) for item in related)
        ):
            raise TypeError(f"invalid-route-mapping:{field}")
        copied[key] = tuple(related)
    return MappingProxyType(copied)


def freeze_capability_route_mapping(
    value: Mapping[CapabilityId, CapabilityRoute],
    field: str,
) -> Mapping[CapabilityId, CapabilityRoute]:
    """Copy capability routes into an immutable insertion-ordered view."""
    if not isinstance(value, Mapping):
        raise TypeError(f"invalid-route-mapping:{field}")
    copied: dict[CapabilityId, CapabilityRoute] = {}
    for key, route in value.items():
        if not isinstance(key, str) or not isinstance(route, CapabilityRoute):
            raise TypeError(f"invalid-route-mapping:{field}")
        copied[key] = route
    return MappingProxyType(copied)


def freeze_skill_rule_mapping(
    value: Mapping[str, SkillRoutingRule],
    field: str,
) -> Mapping[str, SkillRoutingRule]:
    """Copy skill rules into an immutable insertion-ordered view."""
    if not isinstance(value, Mapping):
        raise TypeError(f"invalid-route-mapping:{field}")
    copied: dict[str, SkillRoutingRule] = {}
    for key, rule in value.items():
        if not isinstance(key, str) or not isinstance(rule, SkillRoutingRule):
            raise TypeError(f"invalid-route-mapping:{field}")
        copied[key] = rule
    return MappingProxyType(copied)


def load_skill_route_rules(root: Path) -> tuple[SkillRoutingRule, ...]:
    """Load prompt-routing rules from a natively schema-validated catalog."""
    validate_catalog_schemas(root)
    data = load_skill_catalog(root)
    families = object_sequence(data.get("skill_families"), "skill_families")
    public_skill_ids = _skill_ids_from_catalog(data)
    dependency_rules = load_skill_dependency_map(root, public_skill_ids)
    rules: list[SkillRoutingRule] = []
    observed_skill_ids: set[str] = set()
    for index, entry in enumerate(families):
        entry_mapping = object_mapping(entry, f"skill_families[{index}]")
        skill_id = cast(str, entry_mapping["id"])
        if skill_id.startswith(PRIVATE_SKILL_PREFIX):
            raise ValueError(f"skill_families[{index}].id must be public: {skill_id}")
        if skill_id in observed_skill_ids:
            raise ValueError(f"duplicate skill catalog id: {skill_id}")
        observed_skill_ids.add(skill_id)
        if "related_skills" in entry_mapping:
            raise ValueError(
                f"{skill_id}.related_skills must be declared in "
                f"{SKILL_DEPENDENCY_MAP_PATH}"
            )
        routing = entry_mapping.get("routing")
        routing_mapping: JsonMapping = (
            {} if routing is None else object_mapping(routing, f"{skill_id}.routing")
        )
        reason = routing_mapping.get("reason", "prompt explicitly names public skill")
        reason = cast(str, reason)
        stage_policy = routing_mapping.get("stage_policy", "deferred")
        stage_policy = cast(str, stage_policy)
        visualization_owner = optional_metadata_string(
            entry_mapping.get("visualization_owner"),
            f"{skill_id}.visualization_owner",
        )
        visualization_role = optional_metadata_string(
            entry_mapping.get("visualization_role"),
            f"{skill_id}.visualization_role",
        )
        tool_id = optional_metadata_string(
            entry_mapping.get("tool_id"),
            f"{skill_id}.tool_id",
        )
        argument_schema = optional_metadata_string(
            entry_mapping.get("argument_schema"),
            f"{skill_id}.argument_schema",
        )
        has_visualization_metadata = any(
            (visualization_owner, visualization_role, tool_id, argument_schema)
        )
        rules.append(
            SkillRoutingRule(
                skill=skill_id,
                reason=reason,
                stage_policy=stage_policy,
                triggers=trigger_groups(
                    routing_mapping.get("triggers"),
                    f"{skill_id}.routing.triggers",
                ),
                capabilities=capability_routes(
                    routing_mapping.get("capabilities"),
                    "routing.capabilities",
                    skill_id,
                ),
                related_skills=ordered_unique(
                    dependency_rules[skill_id].routing_candidates
                ),
                visualization_owner_skill=(
                    cast(VisualizationOwnerSkill, visualization_owner)
                    if visualization_owner
                    else None
                ),
                visualization_tool_call=(
                    build_visualization_owner_tool_call(
                        f"skill:{skill_id}",
                        f"agents/skills/catalog.yaml#skill:{skill_id}",
                    )
                    if has_visualization_metadata
                    else None
                ),
                visualization_rejection=None,
                visualization_role=visualization_role,
                tool_id=tool_id,
                argument_schema=argument_schema,
                required_prerequisites=dependency_rules[
                    skill_id
                ].required_prerequisites,
                successors=dependency_rules[skill_id].successors,
                order_constraints=dependency_rules[skill_id].order_constraints,
                parallel_independent=dependency_rules[skill_id].parallel_independent,
                responsibility_group=dependency_rules[skill_id].responsibility_group,
            )
        )
    validate_visualization_metadata(rules)
    return tuple(rules)


def load_skill_route_rules_from_root(
    resolved_root: Path,
) -> tuple[SkillRoutingRule, ...]:
    """Load complete rules from one resolved custom repository root."""
    if not resolved_root.exists():
        raise CapabilityRootError("capability-root-not-found")
    if not resolved_root.is_dir():
        raise CapabilityRootError("capability-root-not-directory")
    catalog_path = resolved_root / SKILL_CATALOG_PATH
    if not catalog_path.is_file():
        raise CapabilityRootError("capability-root-catalog-missing")
    try:
        return load_skill_route_rules(resolved_root)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise CapabilityRootError("capability-root-catalog-invalid") from exc


def load_skill_related_map(root: Path) -> dict[str, tuple[str, ...]]:
    """Return catalog-backed related-skill candidates keyed by public skill id."""
    return {rule.skill: rule.related_skills for rule in load_skill_route_rules(root)}


def load_skill_required_tool_commands(root: Path) -> dict[str, tuple[str, ...]]:
    """Return catalog-owned required commands keyed by public skill id."""
    return {
        skill: spec.required for skill, spec in load_skill_tool_commands(root).items()
    }


def load_skill_tool_commands(root: Path) -> dict[str, SkillToolCommandSpec]:
    """Return all catalog-owned command phases keyed by public skill id.

    A missing ``tool_commands`` block is retained as an unstructured fixture
    marker for legacy/minimal roots.  The canonical catalog contains a block
    for every public skill and therefore never falls back to prose discovery.
    """
    if not (root / SKILL_CATALOG_PATH).is_file():
        return {}
    data = load_skill_catalog(root)
    families = object_sequence(data.get("skill_families"), "skill_families")
    result: dict[str, SkillToolCommandSpec] = {}
    for index, entry in enumerate(families):
        entry_mapping = object_mapping(entry, f"skill_families[{index}]")
        skill_id = cast(str, entry_mapping["id"])
        if skill_id in result:
            raise ValueError(f"duplicate skill catalog id: {skill_id}")
        commands = entry_mapping.get("tool_commands")
        if commands is None:
            result[skill_id] = SkillToolCommandSpec(structured=False)
            continue
        command_mapping = object_mapping(commands, f"{skill_id}.tool_commands")
        phases = {
            phase: optional_string_list(
                command_mapping.get(phase),
                f"{skill_id}.tool_commands.{phase}",
            )
            for phase in ("required", "conditional", "maintenance")
        }
        commands_seen: set[str] = set()
        for phase, values in phases.items():
            duplicate = next(
                (command for command in values if command in commands_seen),
                None,
            )
            if duplicate is not None:
                raise ValueError(
                    f"{skill_id}.tool_commands.duplicate:{phase}:{duplicate}"
                )
            commands_seen.update(values)
        result[skill_id] = SkillToolCommandSpec(
            required=phases["required"],
            conditional=phases["conditional"],
            maintenance=phases["maintenance"],
        )
    return result


def build_capability_index(rules: Sequence[SkillRoutingRule]) -> CapabilityIndex:
    """Build the catalog-ordered capability index and duplicate diagnostics."""
    routes: dict[CapabilityId, CapabilityRoute] = {}
    rules_by_skill: dict[str, SkillRoutingRule] = {}
    owner_ambiguities: list[CapabilityId] = []
    duplicate_definitions: list[CapabilityId] = []
    for rule in rules:
        rules_by_skill[rule.skill] = rule
        for route in rule.capabilities:
            existing = routes.get(route.capability_id)
            if existing is None:
                routes[route.capability_id] = route
                continue
            if existing.skill == route.skill:
                if route.capability_id not in duplicate_definitions:
                    duplicate_definitions.append(route.capability_id)
            elif route.capability_id not in owner_ambiguities:
                owner_ambiguities.append(route.capability_id)
    return CapabilityIndex(
        routes=routes,
        rules_by_skill=rules_by_skill,
        owner_ambiguities=tuple(owner_ambiguities),
        duplicate_definitions=tuple(duplicate_definitions),
    )


def ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    """Return values in first-seen order without duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def related_skill_candidates(
    matched_skills: Sequence[str],
    rules_by_skill: Mapping[str, SkillRoutingRule],
    selected_skills: Sequence[str],
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Return related skills for matched skills without activating them."""
    related_by_source: dict[str, tuple[str, ...]] = {}
    candidates: list[str] = []
    selected = set(selected_skills)
    for skill in matched_skills:
        rule = rules_by_skill.get(skill)
        if rule is None or not rule.related_skills:
            continue
        pending_related = tuple(
            related_skill
            for related_skill in rule.related_skills
            if related_skill not in selected
        )
        if not pending_related:
            continue
        related_by_source[skill] = pending_related
        candidates.extend(pending_related)
    return related_by_source, ordered_unique(candidates)
