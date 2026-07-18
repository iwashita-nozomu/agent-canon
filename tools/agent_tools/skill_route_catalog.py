#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns public skill-route catalog parsing, frozen rule/index values, root errors, and related-skill projections.
# upstream design ../../agents/skills/oop-type-design.md approved OOP/type-design owner and module contract
# upstream implementation ../../agents/skills/catalog.yaml complete public skill-route catalog and capability metadata
# downstream implementation ./capability_route.py immutable capability decision consumer
# downstream implementation ./route.py public route composition and compatibility facade
# downstream implementation ./check_agent_runtime_alignment.py registration/path parity consumer
# downstream implementation ../../tests/agent_tools/test_route.py catalog-owned route tests
# @dependency-end
"""Load AgentCanon skill-route catalog records and immutable indexes."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

import yaml

__all__ = (
    "CapabilityId",
    "CapabilityCatalogError",
    "CapabilityRootError",
    "CapabilityRoute",
    "CapabilityIndex",
    "SkillRoutingRule",
    "capability_id_from_raw",
    "capability_routes",
    "freeze_related_skill_mapping",
    "freeze_capability_route_mapping",
    "freeze_skill_rule_mapping",
    "load_skill_route_rules",
    "load_skill_route_rules_from_root",
    "load_skill_related_map",
    "build_capability_index",
    "ordered_unique",
    "related_skill_candidates",
)

JsonMapping = Mapping[str, object]
CapabilityId = str
SKILL_CATALOG_PATH = Path("agents/skills/catalog.yaml")
STAGE_POLICY_VALUES = ("active", "deferred")
PRIVATE_SKILL_PREFIX = "_"
CAPABILITY_ID_RE = re.compile(r"^[a-z0-9_]+$")


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
class SkillRoutingRule:
    """One catalog-backed prompt and capability routing rule."""

    skill: str
    reason: str
    stage_policy: str
    triggers: tuple[tuple[str, ...], ...]
    capabilities: tuple[CapabilityRoute, ...]
    related_skills: tuple[str, ...]


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
    """Return one string-keyed mapping from parsed catalog data."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    return cast(JsonMapping, value)


def object_sequence(value: object, field: str) -> Sequence[object]:
    """Return one sequence from parsed catalog data."""
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
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
    """Return a tuple of non-empty strings from one YAML sequence."""
    result: list[str] = []
    for item in object_sequence(value, field):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} entries must be non-empty strings")
        result.append(item)
    return tuple(result)


def trigger_groups(value: object, field: str) -> tuple[tuple[str, ...], ...]:
    """Return normalized trigger term groups from YAML."""
    if value is None:
        return ()
    groups: list[tuple[str, ...]] = []
    for index, group in enumerate(object_sequence(value, field)):
        groups.append(string_list(group, f"{field}[{index}]"))
    return tuple(groups)


def optional_string_list(value: object, field: str) -> tuple[str, ...]:
    """Return a tuple of strings from an optional YAML list."""
    if value is None:
        return ()
    return string_list(value, field)


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
        values = {
            key: record[key]
            for key in ("id", "owner", "phase", "activation")
        }
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
        if not isinstance(key, str) or not isinstance(related, tuple) or not all(
            isinstance(item, str) for item in related
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
    """Load prompt-routing rules from the public skill catalog."""
    data = load_skill_catalog(root)
    families = object_sequence(data.get("skill_families"), "skill_families")
    rules: list[SkillRoutingRule] = []
    observed_skill_ids: set[str] = set()
    for index, entry in enumerate(families):
        entry_mapping = object_mapping(entry, f"skill_families[{index}]")
        skill_id = entry_mapping.get("id")
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise ValueError(f"skill_families[{index}].id must be a non-empty string")
        if skill_id.startswith(PRIVATE_SKILL_PREFIX):
            raise ValueError(f"skill_families[{index}].id must be public: {skill_id}")
        if skill_id in observed_skill_ids:
            raise ValueError(f"duplicate skill catalog id: {skill_id}")
        observed_skill_ids.add(skill_id)
        routing = entry_mapping.get("routing")
        if routing is None:
            routing_mapping: JsonMapping = {}
        else:
            routing_mapping = object_mapping(routing, f"{skill_id}.routing")
        reason = routing_mapping.get("reason", "prompt explicitly names public skill")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{skill_id}.routing.reason must be a non-empty string")
        stage_policy = routing_mapping.get("stage_policy", "deferred")
        if stage_policy not in STAGE_POLICY_VALUES:
            raise ValueError(
                f"{skill_id}.routing.stage_policy must be one of {STAGE_POLICY_VALUES}"
            )
        rules.append(
            SkillRoutingRule(
                skill=skill_id,
                reason=reason,
                stage_policy=str(stage_policy),
                triggers=trigger_groups(
                    routing_mapping.get("triggers"),
                    f"{skill_id}.routing.triggers",
                ),
                capabilities=capability_routes(
                    routing_mapping.get("capabilities"),
                    "routing.capabilities",
                    skill_id,
                ),
                related_skills=optional_string_list(
                    entry_mapping.get("related_skills"),
                    f"{skill_id}.related_skills",
                ),
            )
        )
    for rule in rules:
        for related_skill in rule.related_skills:
            if related_skill == rule.skill:
                raise ValueError(f"{rule.skill}.related_skills must not include itself")
            if related_skill.startswith(PRIVATE_SKILL_PREFIX):
                raise ValueError(
                    f"{rule.skill}.related_skills must be public: {related_skill}"
                )
            if related_skill not in observed_skill_ids:
                raise ValueError(
                    f"{rule.skill}.related_skills unknown skill: {related_skill}"
                )
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
