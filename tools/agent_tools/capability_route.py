#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns capability raw-argv preflight and immutable route decisions.
# upstream design ../../agents/skills/oop-type-design.md approved OOP/type-design owner and module contract
# upstream implementation ./skill_route_catalog.py immutable catalog/index and decision-support API
# downstream implementation ./route.py public route composition and rendering
# downstream implementation ../../tests/agent_tools/test_route.py capability-owned route tests
# @dependency-end
"""Normalize explicit capability arguments and build stable decisions."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from skill_route_catalog import (
    CapabilityId,
    CapabilityIndex,
    capability_id_from_raw,
    freeze_related_skill_mapping,
    ordered_unique,
    related_skill_candidates,
)

__all__ = (
    "FORMAT_VALUES",
    "MODE_VALUES",
    "RISK_VALUES",
    "CAPABILITY_SCHEMA",
    "CapabilityRouteError",
    "CapabilityMatch",
    "CapabilityPreflight",
    "CapabilityRouteDecision",
    "capability_text_from_args",
    "capability_flag_conflict",
    "preflight_capability_argv",
    "capability_skill_routes",
    "capability_error_code",
    "capability_failure_decision",
    "decide_capabilities",
)

FORMAT_VALUES = ("text", "json", "markdown")
MODE_VALUES = ("routing-only", "repo-changing")
RISK_VALUES = ("routine", "focused", "profile", "shared", "large")
CAPABILITY_SCHEMA = "agent_canon.route.capability_route.v1"


class CapabilityRouteError(ValueError):
    """One fixed invalid direct capability-match precondition error."""

    def __init__(self, code: str) -> None:
        """Initialize with one stable direct-route error code."""
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CapabilityMatch:
    """One exact capability match copied from the catalog."""

    skill: str
    capability_id: CapabilityId
    owner: str
    phase: str
    activation: str
    exclusive: bool


@dataclass(frozen=True)
class CapabilityPreflight:
    """Raw-argv capability validation result."""

    capability_ids: tuple[CapabilityId, ...]
    mode: str
    output_format: str
    error_code: str
    root: Path | None


@dataclass(frozen=True)
class CapabilityRouteDecision:
    """Capability-selection result with a stable success/failure envelope."""

    schema: str
    route: str
    mode: str
    status: str
    error_code: str
    capability_ids: tuple[CapabilityId, ...]
    matches: tuple[CapabilityMatch, ...]
    skills: tuple[str, ...]
    active_skills: tuple[str, ...]
    deferred_skills: tuple[str, ...]
    related_skill_candidates: tuple[str, ...]
    related_skills: Mapping[str, tuple[str, ...]]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        """Freeze the related-skill mapping after dataclass construction."""
        object.__setattr__(
            self,
            "related_skills",
            freeze_related_skill_mapping(self.related_skills, "related_skills"),
        )


CAPABILITY_VALUE_OPTIONS: Mapping[str, str] = {
    "--capability": "--capability",
    "--format": "--format",
    "--mode": "--mode",
    "--risk": "--risk",
    "--root": "--root",
    "--name": "--name",
    "--area": "--area",
    "--prompt": "--prompt",
    "--request": "--prompt",
    "--purpose": "--prompt",
    "--task": "--prompt",
    "--prompt-file": "--prompt-file",
    "--request-file": "--prompt-file",
    "--query-file": "--prompt-file",
}
CAPABILITY_BOOLEAN_OPTIONS: Mapping[str, str] = {
    "--prompt-stdin": "--prompt-stdin",
    "--request-stdin": "--prompt-stdin",
    "--query-stdin": "--prompt-stdin",
    "--list": "--list",
}


def capability_text_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    """Return normalized explicit capability IDs from parsed arguments."""
    return tuple(capability_id_from_raw(str(value)) for value in args.capability)


def capability_flag_conflict(
    argv: Sequence[str],
    args: argparse.Namespace,
) -> str | None:
    """Return the first forbidden capability-mode raw-argv conflict."""
    del args
    capability_present = any(
        token == "--capability" or token.startswith("--capability=")
        for token in argv
    )
    if not capability_present:
        return None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--capability" or token.startswith("--capability="):
            index += 1
            if (
                token == "--capability"
                and index < len(argv)
                and not argv[index].startswith("--")
            ):
                index += 1
            continue
        if "=" in token and token.startswith("--"):
            option = token.split("=", maxsplit=1)[0]
            if option in CAPABILITY_VALUE_OPTIONS:
                canonical = CAPABILITY_VALUE_OPTIONS[option]
                if canonical not in {"--format", "--mode", "--risk", "--root"}:
                    return f"capability-input-conflict:{canonical}"
                index += 1
                continue
            if option in CAPABILITY_BOOLEAN_OPTIONS:
                return f"capability-input-conflict:{CAPABILITY_BOOLEAN_OPTIONS[option]}"
            if option == "--changed":
                return "capability-input-conflict:--changed"
            return f"capability-unsupported-option:{token}"
        if token in CAPABILITY_VALUE_OPTIONS:
            canonical = CAPABILITY_VALUE_OPTIONS[token]
            if canonical not in {
                "--capability",
                "--format",
                "--mode",
                "--risk",
                "--root",
            }:
                return f"capability-input-conflict:{canonical}"
            index += 1
            if index >= len(argv) or argv[index].startswith("--"):
                if canonical not in {"--format", "--mode", "--risk", "--root"}:
                    return f"capability-input-conflict:{canonical}"
                index -= 1
            else:
                index += 1
            continue
        if token in CAPABILITY_BOOLEAN_OPTIONS:
            return f"capability-input-conflict:{CAPABILITY_BOOLEAN_OPTIONS[token]}"
        if token == "--changed" or token.startswith("--changed="):
            return "capability-input-conflict:--changed"
        if token.startswith("--"):
            return f"capability-unsupported-option:{token}"
        return "capability-input-conflict:--prompt"
    return None


def preflight_capability_argv(argv: Sequence[str]) -> CapabilityPreflight:
    """Validate capability-mode argv before argparse or catalog access."""
    values: list[str] = []
    output_format = "text"
    mode = "repo-changing"
    root: Path | None = None
    format_raw: str | None = None
    mode_raw: str | None = None
    risk_raw: str | None = None
    root_raw: str | None = None
    capability_present = False
    index = 0
    while index < len(argv):
        token = str(argv[index])
        if token == "--capability" or token.startswith("--capability="):
            capability_present = True
            if token == "--capability":
                if index + 1 >= len(argv) or str(argv[index + 1]).startswith("--"):
                    return CapabilityPreflight(
                        (), mode, output_format, "missing-capability-value", root
                    )
                values.append(str(argv[index + 1]))
                index += 2
                continue
            values.append(token.split("=", maxsplit=1)[1])
            index += 1
            continue
        option = token.split("=", maxsplit=1)[0] if token.startswith("--") else ""
        has_equals = token.startswith("--") and "=" in token
        if option in {"--format", "--mode", "--risk", "--root"}:
            if has_equals:
                value = token.split("=", maxsplit=1)[1]
            elif index + 1 >= len(argv) or str(argv[index + 1]).startswith("--"):
                error_code = {
                    "--format": "missing-format-value",
                    "--mode": "missing-mode-value",
                    "--risk": "missing-risk-value",
                    "--root": "missing-root-value",
                }[option]
                return CapabilityPreflight((), mode, output_format, error_code, root)
            else:
                value = str(argv[index + 1])
                index += 1
            if option == "--format":
                format_raw = value
                output_format = value if value in FORMAT_VALUES else "text"
            elif option == "--mode":
                mode_raw = value
                mode = value if value in MODE_VALUES else "repo-changing"
            elif option == "--risk":
                risk_raw = value
            else:
                root_raw = value
            index += 1
            continue
        index += 1
    if not capability_present:
        return CapabilityPreflight((), mode, output_format, "", root)
    try:
        normalized_ids = tuple(capability_id_from_raw(value) for value in values)
    except ValueError as exc:
        return CapabilityPreflight((), mode, output_format, str(exc), root)
    if len(set(normalized_ids)) != len(normalized_ids):
        duplicate = next(
            capability_id
            for position, capability_id in enumerate(normalized_ids)
            if capability_id in normalized_ids[:position]
        )
        return CapabilityPreflight(
            normalized_ids,
            mode,
            output_format,
            f"duplicate-capability:{duplicate}",
            root,
        )
    conflict = capability_flag_conflict(argv, argparse.Namespace())
    if conflict:
        return CapabilityPreflight(normalized_ids, mode, output_format, conflict, root)
    if format_raw is not None and format_raw not in FORMAT_VALUES:
        return CapabilityPreflight(
            normalized_ids,
            mode,
            "text",
            f"invalid-capability-format:{format_raw}",
            root,
        )
    if mode_raw is not None and mode_raw not in MODE_VALUES:
        return CapabilityPreflight(
            normalized_ids,
            "repo-changing",
            output_format,
            f"invalid-capability-mode:{mode_raw}",
            root,
        )
    if risk_raw is not None:
        if risk_raw not in RISK_VALUES or risk_raw != "focused":
            return CapabilityPreflight(
                normalized_ids,
                mode,
                output_format,
                "capability-risk-conflict",
                root,
            )
    if root_raw is not None:
        root = Path(root_raw).expanduser().resolve(strict=False)
    return CapabilityPreflight(normalized_ids, mode, output_format, "", root)


def capability_skill_routes(
    capability_ids: Sequence[str],
    index: CapabilityIndex,
) -> tuple[CapabilityMatch, ...]:
    """Resolve exactly one validated capability ID to one copied match."""
    if not capability_ids:
        raise CapabilityRouteError("unknown-capability:")
    normalized: list[CapabilityId] = []
    for raw in capability_ids:
        try:
            capability_id = capability_id_from_raw(raw)
        except (AttributeError, ValueError) as exc:
            raise CapabilityRouteError(f"invalid-capability-id:{raw}") from exc
        if capability_id in normalized:
            raise CapabilityRouteError(f"duplicate-capability:{capability_id}")
        normalized.append(capability_id)
    if len(normalized) > 1:
        raise CapabilityRouteError("multiple-capabilities-not-supported")
    route = index.routes.get(normalized[0])
    if route is None:
        raise CapabilityRouteError(f"unknown-capability:{normalized[0]}")
    return (
        CapabilityMatch(
            skill=route.skill,
            capability_id=route.capability_id,
            owner=route.owner,
            phase=route.phase,
            activation=route.activation,
            exclusive=route.exclusive,
        ),
    )


def capability_error_code(
    capability_ids: Sequence[str],
    preflight: CapabilityPreflight,
    index: CapabilityIndex,
) -> str:
    """Return the sole deterministic capability diagnostic."""
    if preflight.error_code:
        return preflight.error_code
    for capability_id in index.owner_ambiguities:
        if capability_id in capability_ids:
            return f"capability-owner-ambiguity:{capability_id}"
    for capability_id in index.duplicate_definitions:
        if capability_id in capability_ids:
            return f"duplicate-capability-definition:{capability_id}"
    normalized: list[CapabilityId] = []
    for raw in capability_ids:
        try:
            capability_id = capability_id_from_raw(raw)
        except (AttributeError, ValueError):
            return f"invalid-capability-id:{raw}"
        if capability_id in normalized:
            return f"duplicate-capability:{capability_id}"
        normalized.append(capability_id)
    if len(normalized) > 1:
        return "multiple-capabilities-not-supported"
    if normalized and normalized[0] not in index.routes:
        return f"unknown-capability:{normalized[0]}"
    return ""


def capability_failure_decision(
    error_code: str,
    capability_ids: Sequence[str],
    mode: str,
) -> CapabilityRouteDecision:
    """Build one deterministic failure envelope without rendering."""
    ids = () if error_code.startswith("invalid-capability-id:") else tuple(capability_ids)
    return CapabilityRouteDecision(
        schema=CAPABILITY_SCHEMA,
        route="capability-selection",
        mode=mode if mode in MODE_VALUES else "repo-changing",
        status="fail",
        error_code=error_code,
        capability_ids=ids,
        matches=(),
        skills=(),
        active_skills=(),
        deferred_skills=(),
        related_skill_candidates=(),
        related_skills={},
        reasons=(),
    )


def decide_capabilities(
    capability_ids: Sequence[str],
    mode: str,
    index: CapabilityIndex,
    preflight: CapabilityPreflight,
) -> CapabilityRouteDecision:
    """Create a capability-owned route decision without prompt inference."""
    error_code = capability_error_code(capability_ids, preflight, index)
    if error_code:
        return capability_failure_decision(error_code, capability_ids, mode)
    matches = capability_skill_routes(capability_ids, index)
    match = matches[0]
    skills = ordered_unique(
        (
            "agent-orchestration",
            *( ("codex-task-workflow",) if mode == "repo-changing" else () ),
            match.skill,
        )
    )
    active_skills = ordered_unique(("agent-orchestration", match.skill))
    related_by_source, related_candidates = related_skill_candidates(
        (match.skill,),
        index.rules_by_skill,
        (match.skill,),
    )
    reason = (
        f"capability={match.capability_id};owner={match.owner};phase={match.phase};"
        f"activation={match.activation}"
    )
    return CapabilityRouteDecision(
        schema=CAPABILITY_SCHEMA,
        route="capability-selection",
        mode=mode,
        status="pass",
        error_code="",
        capability_ids=tuple(capability_ids),
        matches=matches,
        skills=skills,
        active_skills=active_skills,
        deferred_skills=tuple(skill for skill in skills if skill not in active_skills),
        related_skill_candidates=related_candidates,
        related_skills=related_by_source,
        reasons=(f"{match.skill}:{reason}",),
    )
