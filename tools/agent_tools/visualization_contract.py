#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Owns the exact executable typed visualization universe, ToolCall, artifact readback, and projection coverage contract.
# upstream design ../../agents/skills/code-visualization.md visualization ownership and projection semantics
# downstream implementation ../../tests/agent_tools/test_visualization_contract.py contract and checker test coverage
# downstream implementation ../../tools/agent_tools/render_dependency_manifest_graph.py consumes exact source, adapter, marker, and readback records
# @dependency-end
"""Exact D2.4 typed visualization contract and deterministic coverage checker."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal, TypeAlias, TypedDict, TypeVar, cast

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
SourceItemKind: TypeAlias = Literal[
    "identity",
    "edge",
    "field",
    "phase",
    "branch",
    "module",
    "evidence",
    "time",
]
SourceItemOrigin: TypeAlias = Literal[
    "literal_request",
    "owner_closure",
    "dependency_closure",
]
ArtifactFormat: TypeAlias = Literal[
    "tsv",
    "graph_ir",
    "markdown_mermaid",
    "dot",
    "html",
]
ManifestStatus: TypeAlias = Literal["pass", "fail"]
FilterMode: TypeAlias = Literal["view_only"]
ViewState: TypeAlias = Literal["visible", "hidden_view_only"]
ToolID: TypeAlias = Literal[
    "agent_canon.visualization.coverage",
    "agent_canon.visualization.adapter.dependency_manifest",
    "agent_canon.visualization.adapter.algorithm_flowchart",
    "agent_canon.visualization.adapter.document_mermaid",
    "agent_canon.visualization.adapter.repository_graph",
    "agent_canon.visualization.adapter.knowledge_graph",
]
ArgumentSchemaID: TypeAlias = Literal[
    "agent_canon.visualization.arguments.coverage.v1",
    "agent_canon.visualization.arguments.dependency_manifest.v1",
    "agent_canon.visualization.arguments.algorithm_flowchart.v1",
    "agent_canon.visualization.arguments.document_mermaid.v1",
    "agent_canon.visualization.arguments.repository_graph.v1",
    "agent_canon.visualization.arguments.knowledge_graph.v1",
]
ViolationCode: TypeAlias = Literal[
    "missing_source_mapping",
    "duplicate_source_mapping",
    "orphan_rendered_identity",
    "source_kind_mismatch",
    "aggregated_source",
    "representative_only",
    "main_path_only",
    "hidden_helper",
    "filter_deleted",
    "count_mismatch",
    "fingerprint_mismatch",
    "readback_mismatch",
    "invalid_identity",
    "invalid_payload",
    "missing_marker",
    "malformed_marker",
    "missing_token",
    "missing_sidecar",
    "artifact_mismatch",
    "diagram_count_mismatch",
    "table_fallback",
    "marker_only_identity",
    "visible_surface_missing",
    "visible_identity_missing",
    "visible_identity_duplicate",
    "ir_surface_mismatch",
    "external_resource",
    "script_network_api",
    "malformed_resource_locator",
]
class FilterRecord(TypedDict):
    """One reversible visualization filter."""

    filter_id: str
    mode: FilterMode
    enabled: bool
    selected_item_ids: list[str]


class _OptionalFilters(TypedDict, total=False):
    filters: list[FilterRecord]


class VisualizationSourceItem(TypedDict):
    """One immutable source identity."""

    item_id: str
    kind: SourceItemKind
    origin: SourceItemOrigin
    source_locator: str
    source_start: int | None
    source_end: int | None
    ordinal: int
    payload_json: str


class VisualizationSourceUniverse(TypedDict):
    """Complete literal, owner, and dependency source universe."""

    schema: Literal["agent_canon.visualization_source_universe.v1"]
    request_id: str
    literal_request: str
    owner_closure: list[VisualizationSourceItem]
    dependency_closure: list[VisualizationSourceItem]
    items: list[VisualizationSourceItem]
    source_fingerprint: str
    filters: list[FilterRecord]


class ProjectionCoverageEntry(TypedDict):
    """One source-to-rendered-to-readback identity record."""

    source_item_id: str
    source_kind: SourceItemKind
    rendered_identity: str
    artifact_locator: list[str]
    renderer_id: str
    readback_identity: str
    payload_json: str
    view_state: ViewState


class CoverageViolation(TypedDict):
    """One complete typed coverage violation."""

    code: ViolationCode
    source_item_id: str | None
    rendered_identity: str | None
    artifact_locator: str | None
    detail: str


class ProjectionCoverageManifest(TypedDict):
    """Canonical projection coverage manifest."""

    schema: Literal["agent_canon.projection_coverage_manifest.v1"]
    universe_fingerprint: str
    artifact_id: str
    renderer_id: str
    artifact_format: ArtifactFormat
    entries: list[ProjectionCoverageEntry]
    source_counts: dict[SourceItemKind, int]
    rendered_counts: dict[SourceItemKind, int]
    readback_counts: dict[SourceItemKind, int]
    omitted_item_ids: list[str]
    violations: list[CoverageViolation]
    filters: list[FilterRecord]
    coverage_digest: str
    status: ManifestStatus


class CoverageReport(TypedDict):
    """Final deterministic coverage decision."""

    status: ManifestStatus
    missing_item_ids: list[str]
    orphan_rendered_ids: list[str]
    violations: list[CoverageViolation]
    coverage_digest: str
    source_counts: dict[SourceItemKind, int]
    rendered_counts: dict[SourceItemKind, int]
    readback_counts: dict[SourceItemKind, int]


class ReadbackProjection(TypedDict):
    """Identities reconstructed from one final formatted artifact."""

    artifact_id: str
    artifact_format: ArtifactFormat
    renderer_id: str
    identities: dict[str, ProjectionCoverageEntry]
    readback_counts: dict[SourceItemKind, int]
    coverage_digest: str
    status: ManifestStatus
    violations: list[CoverageViolation]


class ToolCall(TypedDict):
    """Canonical visualization owner or adapter ToolCall."""

    schema: Literal["agent_canon.visualization_tool_call.v1"]
    tool_id: ToolID
    argument_schema: ArgumentSchemaID
    arguments: dict[str, JsonValue]


class CoverageArguments(_OptionalFilters):
    """Canonical coverage-owner ToolCall arguments."""

    request_id: str
    literal_request: str
    literal_items: list[VisualizationSourceItem]
    owner_closure: list[VisualizationSourceItem]
    dependency_closure: list[VisualizationSourceItem]
    artifact_id: str
    renderer_id: str
    artifact_format: ArtifactFormat


class DependencyManifestArguments(_OptionalFilters):
    """Dependency-manifest adapter ToolCall arguments."""

    request_id: str
    literal_request: str
    literal_items: list[VisualizationSourceItem]
    owner_closure: list[VisualizationSourceItem]
    dependency_closure: list[VisualizationSourceItem]
    artifact_id: str
    renderer_id: str
    artifact_format: ArtifactFormat
    dependency_manifest_locator: str


class AlgorithmFlowchartArguments(_OptionalFilters):
    """Algorithm-flowchart adapter ToolCall arguments."""

    request_id: str
    literal_request: str
    literal_items: list[VisualizationSourceItem]
    owner_closure: list[VisualizationSourceItem]
    dependency_closure: list[VisualizationSourceItem]
    artifact_id: str
    renderer_id: str
    artifact_format: ArtifactFormat
    jit_ir_locator: str
    lean_evidence_locator: str
    theorem_graph_locator: str


class DocumentMermaidArguments(_OptionalFilters):
    """Document-Mermaid adapter ToolCall arguments."""

    request_id: str
    literal_request: str
    literal_items: list[VisualizationSourceItem]
    owner_closure: list[VisualizationSourceItem]
    dependency_closure: list[VisualizationSourceItem]
    artifact_id: str
    renderer_id: str
    artifact_format: ArtifactFormat
    document_locator: str


class RepositoryGraphArguments(_OptionalFilters):
    """Repository-graph adapter ToolCall arguments."""

    request_id: str
    literal_request: str
    literal_items: list[VisualizationSourceItem]
    owner_closure: list[VisualizationSourceItem]
    dependency_closure: list[VisualizationSourceItem]
    artifact_id: str
    renderer_id: str
    artifact_format: ArtifactFormat
    repository_locator: str


class KnowledgeGraphArguments(_OptionalFilters):
    """Knowledge-graph adapter ToolCall arguments."""

    request_id: str
    literal_request: str
    literal_items: list[VisualizationSourceItem]
    owner_closure: list[VisualizationSourceItem]
    dependency_closure: list[VisualizationSourceItem]
    artifact_id: str
    renderer_id: str
    artifact_format: ArtifactFormat
    graph_locator: str


VISUALIZATION_SOURCE_UNIVERSE_SCHEMA = "agent_canon.visualization_source_universe.v1"
PROJECTION_COVERAGE_SCHEMA = "agent_canon.projection_coverage_manifest.v1"
TOOL_CALL_SCHEMA = "agent_canon.visualization_tool_call.v1"
COVERAGE_MARKER_PREFIX = "agent_canon_visualization_coverage_v1:"
IDENTITY_TOKEN_PREFIX = "agent_canon_visualization_identity_v1:"
SOURCE_ITEM_KINDS: tuple[SourceItemKind, ...] = (
    "identity",
    "edge",
    "field",
    "phase",
    "branch",
    "module",
    "evidence",
    "time",
)
ARTIFACT_FORMATS: tuple[ArtifactFormat, ...] = (
    "tsv",
    "graph_ir",
    "markdown_mermaid",
    "dot",
    "html",
)
TOOL_ARGUMENT_SCHEMAS: dict[ToolID, ArgumentSchemaID] = {
    "agent_canon.visualization.coverage": "agent_canon.visualization.arguments.coverage.v1",
    "agent_canon.visualization.adapter.dependency_manifest": "agent_canon.visualization.arguments.dependency_manifest.v1",
    "agent_canon.visualization.adapter.algorithm_flowchart": "agent_canon.visualization.arguments.algorithm_flowchart.v1",
    "agent_canon.visualization.adapter.document_mermaid": "agent_canon.visualization.arguments.document_mermaid.v1",
    "agent_canon.visualization.adapter.repository_graph": "agent_canon.visualization.arguments.repository_graph.v1",
    "agent_canon.visualization.adapter.knowledge_graph": "agent_canon.visualization.arguments.knowledge_graph.v1",
}
_ORIGIN_RANK: dict[SourceItemOrigin, int] = {
    "literal_request": 0,
    "owner_closure": 1,
    "dependency_closure": 2,
}
_SOURCE_ITEM_KIND_BY_VALUE: dict[str, SourceItemKind] = {
    value: value for value in SOURCE_ITEM_KINDS
}
_SOURCE_ITEM_ORIGIN_BY_VALUE: dict[str, SourceItemOrigin] = {
    value: value for value in _ORIGIN_RANK
}
_ARTIFACT_FORMAT_BY_VALUE: dict[str, ArtifactFormat] = {
    value: value for value in ARTIFACT_FORMATS
}
_VIEW_STATE_BY_VALUE: dict[str, ViewState] = {
    "visible": "visible",
    "hidden_view_only": "hidden_view_only",
}
_MANIFEST_STATUS_BY_VALUE: dict[str, ManifestStatus] = {
    "pass": "pass",
    "fail": "fail",
}
_VIOLATION_CODES: tuple[ViolationCode, ...] = (
    "missing_source_mapping",
    "duplicate_source_mapping",
    "orphan_rendered_identity",
    "source_kind_mismatch",
    "aggregated_source",
    "representative_only",
    "main_path_only",
    "hidden_helper",
    "filter_deleted",
    "count_mismatch",
    "fingerprint_mismatch",
    "readback_mismatch",
    "invalid_identity",
    "invalid_payload",
    "missing_marker",
    "malformed_marker",
    "missing_token",
    "missing_sidecar",
    "artifact_mismatch",
    "diagram_count_mismatch",
    "table_fallback",
    "marker_only_identity",
    "visible_surface_missing",
    "visible_identity_missing",
    "visible_identity_duplicate",
    "ir_surface_mismatch",
    "external_resource",
    "script_network_api",
    "malformed_resource_locator",
)
_VIOLATION_CODE_BY_VALUE: dict[str, ViolationCode] = {
    value: value for value in _VIOLATION_CODES
}
_TOOL_ID_BY_VALUE: dict[str, ToolID] = {
    value: value for value in TOOL_ARGUMENT_SCHEMAS
}
_LiteralValue = TypeVar("_LiteralValue")
_SHARED_ARGUMENT_FIELDS = {
    "request_id",
    "literal_request",
    "literal_items",
    "owner_closure",
    "dependency_closure",
    "artifact_id",
    "renderer_id",
    "artifact_format",
}
_TOOL_LOCATOR_FIELDS: dict[ToolID, frozenset[str]] = {
    "agent_canon.visualization.coverage": frozenset(),
    "agent_canon.visualization.adapter.dependency_manifest": frozenset(
        {"dependency_manifest_locator"}
    ),
    "agent_canon.visualization.adapter.algorithm_flowchart": frozenset(
        {"jit_ir_locator", "lean_evidence_locator", "theorem_graph_locator"}
    ),
    "agent_canon.visualization.adapter.document_mermaid": frozenset(
        {"document_locator"}
    ),
    "agent_canon.visualization.adapter.repository_graph": frozenset(
        {"repository_locator"}
    ),
    "agent_canon.visualization.adapter.knowledge_graph": frozenset({"graph_locator"}),
}


def _typed_literal(
    value: object,
    values: Mapping[str, _LiteralValue],
) -> _LiteralValue | None:
    if not isinstance(value, str):
        return None
    return values.get(value)


def _normalize_json(value: object, field: str = "value") -> JsonValue:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"invalid_payload:{field}:non-finite")
        return value
    if isinstance(value, list):
        items = cast(list[object], value)
        return [_normalize_json(item, f"{field}[]") for item in items]
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        mapping = cast(Mapping[object, object], value)
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise ValueError(f"invalid_payload:{field}:non-string-key")
            normalized[key] = _normalize_json(item, f"{field}.{key}")
        return normalized
    raise ValueError(f"invalid_payload:{field}:{type(value).__name__}")


def _canonical_json(value: object) -> str:
    return json.dumps(
        _normalize_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_json(value: str) -> JsonValue:
    try:
        parsed: object = json.loads(
            value,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite:{token}")
            ),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid_payload:payload_json") from exc
    return _normalize_json(parsed, "payload_json")


def _copy_source_item(
    item: Mapping[str, object],
    expected_origin: SourceItemOrigin | None = None,
) -> VisualizationSourceItem:
    item_id = item.get("item_id")
    kind = item.get("kind")
    origin = item.get("origin")
    locator = item.get("source_locator")
    start = item.get("source_start")
    end = item.get("source_end")
    ordinal = item.get("ordinal")
    payload_json = item.get("payload_json")
    if not isinstance(item_id, str) or not item_id:
        raise ValueError("invalid_identity:source_item")
    copied_kind = _typed_literal(kind, _SOURCE_ITEM_KIND_BY_VALUE)
    if copied_kind is None:
        raise ValueError(f"invalid_payload:{item_id}:kind")
    copied_origin = _typed_literal(origin, _SOURCE_ITEM_ORIGIN_BY_VALUE)
    if copied_origin is None:
        raise ValueError(f"invalid_payload:{item_id}:origin")
    if expected_origin is not None and copied_origin != expected_origin:
        raise ValueError(f"invalid_payload:{item_id}:origin-bucket")
    if not isinstance(locator, str) or not locator:
        raise ValueError(f"invalid_payload:{item_id}:source_locator")
    copied_start: int | None
    copied_end: int | None
    if start is None and end is None:
        copied_start = None
        copied_end = None
    elif (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and start >= 0
        and end >= start
    ):
        copied_start = start
        copied_end = end
    else:
        raise ValueError(f"invalid_payload:{item_id}:source_offsets")
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
        raise ValueError(f"invalid_payload:{item_id}:ordinal")
    if not isinstance(payload_json, str):
        raise ValueError(f"invalid_payload:{item_id}:payload_json")
    payload = _parse_json(payload_json)
    if not isinstance(payload, dict) or payload_json != _canonical_json(payload):
        raise ValueError(f"invalid_payload:{item_id}:payload_json")
    return {
        "item_id": item_id,
        "kind": copied_kind,
        "origin": copied_origin,
        "source_locator": locator,
        "source_start": copied_start,
        "source_end": copied_end,
        "ordinal": ordinal,
        "payload_json": payload_json,
    }


def _item_sort_key(item: VisualizationSourceItem) -> tuple[object, ...]:
    return (
        _ORIGIN_RANK[item["origin"]],
        item["source_locator"],
        -1 if item["source_start"] is None else item["source_start"],
        -1 if item["source_end"] is None else item["source_end"],
        item["kind"],
        item["item_id"],
        item["ordinal"],
    )


def _copy_filter(record: Mapping[str, object], item_ids: set[str]) -> FilterRecord:
    filter_id = record.get("filter_id")
    mode = record.get("mode")
    enabled = record.get("enabled")
    selected = record.get("selected_item_ids")
    if not isinstance(filter_id, str) or not filter_id:
        raise ValueError("invalid_payload:filter_id")
    if mode != "view_only" or not isinstance(enabled, bool):
        raise ValueError(f"invalid_payload:filter:{filter_id}")
    if not isinstance(selected, list):
        raise ValueError(f"invalid_payload:filter:{filter_id}:selected_item_ids")
    copied_selected: list[str] = []
    for selected_item_id in cast(list[object], selected):
        if not isinstance(selected_item_id, str) or not selected_item_id:
            raise ValueError(f"invalid_payload:filter:{filter_id}:selected_item_ids")
        copied_selected.append(selected_item_id)
    if len(set(copied_selected)) != len(copied_selected) or not set(
        copied_selected
    ).issubset(item_ids):
        raise ValueError(f"filter_deleted:{filter_id}")
    return {
        "filter_id": filter_id,
        "mode": "view_only",
        "enabled": enabled,
        "selected_item_ids": sorted(copied_selected),
    }


def _empty_counts() -> dict[SourceItemKind, int]:
    return {
        "identity": 0,
        "edge": 0,
        "field": 0,
        "phase": 0,
        "branch": 0,
        "module": 0,
        "evidence": 0,
        "time": 0,
    }


def _counts_from_items(
    items: Sequence[VisualizationSourceItem],
) -> dict[SourceItemKind, int]:
    counts = _empty_counts()
    for item in items:
        counts[item["kind"]] += 1
    return counts


def _counts_from_entries(
    entries: Sequence[ProjectionCoverageEntry],
) -> dict[SourceItemKind, int]:
    counts = _empty_counts()
    for entry in entries:
        kind = entry.get("source_kind")
        if kind in SOURCE_ITEM_KINDS:
            counts[kind] += 1
    return counts


def _violation(
    code: ViolationCode,
    detail: str,
    *,
    source_item_id: str | None = None,
    rendered_identity: str | None = None,
    artifact_locator: str | None = None,
) -> CoverageViolation:
    return {
        "code": code,
        "source_item_id": source_item_id,
        "rendered_identity": rendered_identity,
        "artifact_locator": artifact_locator,
        "detail": detail,
    }


def _sorted_violations(
    violations: Sequence[CoverageViolation],
) -> list[CoverageViolation]:
    unique: dict[tuple[object, ...], CoverageViolation] = {}
    for violation in violations:
        key = (
            violation["code"],
            violation["source_item_id"] or "",
            violation["rendered_identity"] or "",
            violation["artifact_locator"] or "",
            violation["detail"],
        )
        unique[key] = violation
    return [unique[key] for key in sorted(unique)]


def _copy_entry(
    entry: Mapping[str, object],
    renderer_id: str,
    violations: list[CoverageViolation],
) -> ProjectionCoverageEntry | None:
    source_item_id = entry.get("source_item_id")
    source_kind = entry.get("source_kind")
    rendered_identity = entry.get("rendered_identity")
    locators = entry.get("artifact_locator")
    entry_renderer = entry.get("renderer_id")
    readback_identity = entry.get("readback_identity")
    payload_json = entry.get("payload_json")
    view_state = entry.get("view_state")
    if not isinstance(source_item_id, str) or not source_item_id:
        violations.append(_violation("invalid_identity", "invalid source item identity"))
        return None
    copied_source_kind = _typed_literal(source_kind, _SOURCE_ITEM_KIND_BY_VALUE)
    if copied_source_kind is None:
        violations.append(
            _violation(
                "source_kind_mismatch",
                "invalid source kind",
                source_item_id=source_item_id,
            )
        )
        return None
    if not isinstance(rendered_identity, str) or not rendered_identity:
        violations.append(
            _violation(
                "invalid_identity",
                "invalid rendered identity",
                source_item_id=source_item_id,
            )
        )
        return None
    if not isinstance(readback_identity, str) or not readback_identity:
        violations.append(
            _violation(
                "invalid_identity",
                "invalid readback identity",
                source_item_id=source_item_id,
                rendered_identity=rendered_identity,
            )
        )
        return None
    if not isinstance(locators, list) or not locators:
        violations.append(
            _violation(
                "missing_token",
                "artifact_locator must contain every final syntax token",
                source_item_id=source_item_id,
                rendered_identity=rendered_identity,
            )
        )
        return None
    copied_locators: list[str] = []
    for locator in cast(list[object], locators):
        if not isinstance(locator, str) or not locator:
            violations.append(
                _violation(
                    "missing_token",
                    "artifact_locator must contain every final syntax token",
                    source_item_id=source_item_id,
                    rendered_identity=rendered_identity,
                )
            )
            return None
        copied_locators.append(locator)
    if entry_renderer != renderer_id:
        violations.append(
            _violation(
                "artifact_mismatch",
                "entry renderer does not match manifest renderer",
                source_item_id=source_item_id,
                rendered_identity=rendered_identity,
            )
        )
    copied_view_state = _typed_literal(view_state, _VIEW_STATE_BY_VALUE)
    if copied_view_state is None:
        violations.append(
            _violation(
                "filter_deleted",
                "view state must preserve the serialized identity",
                source_item_id=source_item_id,
                rendered_identity=rendered_identity,
            )
        )
        return None
    if not isinstance(payload_json, str):
        violations.append(
            _violation(
                "invalid_payload",
                "entry payload_json must be canonical JSON",
                source_item_id=source_item_id,
                rendered_identity=rendered_identity,
            )
        )
        return None
    try:
        payload = _parse_json(payload_json)
    except ValueError:
        violations.append(
            _violation(
                "invalid_payload",
                "entry payload_json is malformed",
                source_item_id=source_item_id,
                rendered_identity=rendered_identity,
            )
        )
        return None
    if not isinstance(payload, dict) or payload_json != _canonical_json(payload):
        violations.append(
            _violation(
                "invalid_payload",
                "entry payload_json is not one canonical JSON object",
                source_item_id=source_item_id,
                rendered_identity=rendered_identity,
            )
        )
        return None
    semantic_flags: tuple[tuple[str, ViolationCode], ...] = (
        ("aggregated_source", "aggregated_source"),
        ("representative_only", "representative_only"),
        ("main_path_only", "main_path_only"),
        ("hidden_helper", "hidden_helper"),
    )
    for field, code in semantic_flags:
        if payload.get(field) is True:
            violations.append(
                _violation(
                    code,
                    f"forbidden projection semantic: {field}",
                    source_item_id=source_item_id,
                    rendered_identity=rendered_identity,
                )
            )
    return {
        "source_item_id": source_item_id,
        "source_kind": copied_source_kind,
        "rendered_identity": rendered_identity,
        "artifact_locator": copied_locators,
        "renderer_id": renderer_id,
        "readback_identity": readback_identity,
        "payload_json": payload_json,
        "view_state": copied_view_state,
    }


def _mapping_violations(
    universe: VisualizationSourceUniverse,
    entries: Sequence[ProjectionCoverageEntry],
    readback: ReadbackProjection,
) -> list[CoverageViolation]:
    violations: list[CoverageViolation] = []
    source_by_id = {item["item_id"]: item for item in universe["items"]}
    source_seen: dict[str, int] = {}
    rendered_seen: dict[str, str] = {}
    readback_seen: dict[str, str] = {}
    for entry in entries:
        source_id = entry["source_item_id"]
        rendered_id = entry["rendered_identity"]
        readback_id = entry["readback_identity"]
        source_seen[source_id] = source_seen.get(source_id, 0) + 1
        if source_seen[source_id] > 1:
            violations.append(
                _violation(
                    "duplicate_source_mapping",
                    "source item has more than one projection entry",
                    source_item_id=source_id,
                    rendered_identity=rendered_id,
                )
            )
        existing_source = rendered_seen.get(rendered_id)
        if existing_source is not None and existing_source != source_id:
            violations.append(
                _violation(
                    "aggregated_source",
                    "one rendered identity maps multiple source items",
                    source_item_id=source_id,
                    rendered_identity=rendered_id,
                )
            )
        rendered_seen[rendered_id] = source_id
        existing_readback = readback_seen.get(readback_id)
        if existing_readback is not None and existing_readback != source_id:
            violations.append(
                _violation(
                    "aggregated_source",
                    "one readback identity maps multiple source items",
                    source_item_id=source_id,
                    rendered_identity=rendered_id,
                )
            )
        readback_seen[readback_id] = source_id
        source = source_by_id.get(source_id)
        if source is None:
            violations.append(
                _violation(
                    "orphan_rendered_identity",
                    "projection entry has no source item",
                    source_item_id=source_id,
                    rendered_identity=rendered_id,
                )
            )
        elif source["kind"] != entry["source_kind"]:
            violations.append(
                _violation(
                    "source_kind_mismatch",
                    "projection source kind differs from universe",
                    source_item_id=source_id,
                    rendered_identity=rendered_id,
                )
            )
        reconstructed = readback["identities"].get(readback_id)
        if reconstructed is None:
            violations.append(
                _violation(
                    "readback_mismatch",
                    "projection identity is absent from final-artifact readback",
                    source_item_id=source_id,
                    rendered_identity=rendered_id,
                )
            )
        elif (
            reconstructed["source_item_id"] != source_id
            or reconstructed["source_kind"] != entry["source_kind"]
            or reconstructed["rendered_identity"] != rendered_id
        ):
            violations.append(
                _violation(
                    "readback_mismatch",
                    "readback identity does not reproduce the projection entry",
                    source_item_id=source_id,
                    rendered_identity=rendered_id,
                )
            )
    for source_id in sorted(set(source_by_id) - set(source_seen)):
        violations.append(
            _violation(
                "missing_source_mapping",
                "source item has no projection entry",
                source_item_id=source_id,
            )
        )
    expected_readback_ids = {entry["readback_identity"] for entry in entries}
    for readback_id, reconstructed in sorted(readback["identities"].items()):
        if readback_id not in expected_readback_ids:
            violations.append(
                _violation(
                    "orphan_rendered_identity",
                    "final artifact contains an identity outside the manifest",
                    source_item_id=reconstructed["source_item_id"],
                    rendered_identity=reconstructed["rendered_identity"],
                )
            )
    violations.extend(readback["violations"])
    return _sorted_violations(violations)


def _manifest_digest_fields(
    manifest: ProjectionCoverageManifest,
    *,
    entries: Sequence[ProjectionCoverageEntry] | None = None,
    readback_counts: Mapping[SourceItemKind, int] | None = None,
) -> dict[str, object]:
    return {
        "schema": manifest["schema"],
        "universe_fingerprint": manifest["universe_fingerprint"],
        "artifact_id": manifest["artifact_id"],
        "renderer_id": manifest["renderer_id"],
        "artifact_format": manifest["artifact_format"],
        "entries": list(manifest["entries"] if entries is None else entries),
        "source_counts": dict(manifest["source_counts"]),
        "rendered_counts": dict(manifest["rendered_counts"]),
        "readback_counts": dict(
            manifest["readback_counts"] if readback_counts is None else readback_counts
        ),
        "omitted_item_ids": list(manifest["omitted_item_ids"]),
        "filters": list(manifest["filters"]),
        "violations": list(manifest["violations"]),
    }


def _coverage_digest(
    manifest: ProjectionCoverageManifest,
    *,
    entries: Sequence[ProjectionCoverageEntry] | None = None,
    readback_counts: Mapping[SourceItemKind, int] | None = None,
) -> str:
    return _sha256(
        _manifest_digest_fields(
            manifest,
            entries=entries,
            readback_counts=readback_counts,
        )
    )


def build_source_universe(
    *,
    request_id: str,
    literal_request: str,
    literal_items: Sequence[VisualizationSourceItem],
    owner_closure: Sequence[VisualizationSourceItem],
    dependency_closure: Sequence[VisualizationSourceItem],
    filters: Sequence[FilterRecord] = (),
) -> VisualizationSourceUniverse:
    """Build the exact immutable source universe in canonical identity order."""
    if not request_id:
        raise ValueError("invalid_identity:request_id")
    literal = [
        _copy_source_item(item, "literal_request") for item in literal_items
    ]
    owner = [_copy_source_item(item, "owner_closure") for item in owner_closure]
    dependency = [
        _copy_source_item(item, "dependency_closure")
        for item in dependency_closure
    ]
    items = sorted((*literal, *owner, *dependency), key=_item_sort_key)
    item_ids = [item["item_id"] for item in items]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("invalid_identity:duplicate_item_id")
    item_id_set = set(item_ids)
    copied_filters = sorted(
        (_copy_filter(record, item_id_set) for record in filters),
        key=lambda record: record["filter_id"],
    )
    if len({record["filter_id"] for record in copied_filters}) != len(copied_filters):
        raise ValueError("invalid_identity:duplicate_filter_id")
    fingerprint_payload = {
        "schema": VISUALIZATION_SOURCE_UNIVERSE_SCHEMA,
        "request_id": request_id,
        "literal_request": literal_request,
        "literal_items": sorted(literal, key=_item_sort_key),
        "owner_closure": sorted(owner, key=_item_sort_key),
        "dependency_closure": sorted(dependency, key=_item_sort_key),
        "items": items,
    }
    return {
        "schema": "agent_canon.visualization_source_universe.v1",
        "request_id": request_id,
        "literal_request": literal_request,
        "owner_closure": sorted(owner, key=_item_sort_key),
        "dependency_closure": sorted(dependency, key=_item_sort_key),
        "items": items,
        "source_fingerprint": _sha256(fingerprint_payload),
        "filters": copied_filters,
    }


def build_projection_coverage_manifest(
    universe: VisualizationSourceUniverse,
    *,
    artifact_id: str,
    renderer_id: str,
    artifact_format: ArtifactFormat,
    entries: Sequence[ProjectionCoverageEntry],
    readback: ReadbackProjection,
) -> ProjectionCoverageManifest:
    """Build a complete manifest without truncating any identity or violation."""
    if not artifact_id:
        raise ValueError("invalid_identity:artifact_id")
    if not renderer_id:
        raise ValueError("invalid_identity:renderer_id")
    if artifact_format not in ARTIFACT_FORMATS:
        raise ValueError("invalid_payload:artifact_format")
    copy_violations: list[CoverageViolation] = []
    copied_entries = [
        copied
        for entry in entries
        if (copied := _copy_entry(entry, renderer_id, copy_violations)) is not None
    ]
    copied_entries.sort(
        key=lambda entry: (
            entry["source_item_id"],
            entry["rendered_identity"],
            entry["readback_identity"],
        )
    )
    violations = _sorted_violations(
        (
            *copy_violations,
            *_mapping_violations(universe, copied_entries, readback),
        )
    )
    source_ids = {item["item_id"] for item in universe["items"]}
    mapped_ids = {entry["source_item_id"] for entry in copied_entries}
    omitted = sorted(source_ids - mapped_ids)
    source_counts = _counts_from_items(universe["items"])
    rendered_counts = _counts_from_entries(copied_entries)
    readback_counts = dict(readback["readback_counts"])
    if set(readback_counts) != set(SOURCE_ITEM_KINDS):
        violations.append(
            _violation("count_mismatch", "readback count map must have eight kinds")
        )
        readback_counts = _empty_counts()
    manifest: ProjectionCoverageManifest = {
        "schema": "agent_canon.projection_coverage_manifest.v1",
        "universe_fingerprint": universe["source_fingerprint"],
        "artifact_id": artifact_id,
        "renderer_id": renderer_id,
        "artifact_format": artifact_format,
        "entries": copied_entries,
        "source_counts": source_counts,
        "rendered_counts": rendered_counts,
        "readback_counts": readback_counts,
        "omitted_item_ids": omitted,
        "violations": _sorted_violations(violations),
        "filters": [
            {
                "filter_id": record["filter_id"],
                "mode": record["mode"],
                "enabled": record["enabled"],
                "selected_item_ids": list(record["selected_item_ids"]),
            }
            for record in universe["filters"]
        ],
        "coverage_digest": "",
        "status": "fail" if violations or omitted else "pass",
    }
    manifest["coverage_digest"] = _coverage_digest(manifest)
    return manifest


def validate_projection_coverage(
    universe: VisualizationSourceUniverse,
    manifest: ProjectionCoverageManifest,
    *,
    readback: ReadbackProjection,
) -> CoverageReport:
    """Validate every source, rendered, and final-artifact readback identity."""
    violations = list(_mapping_violations(universe, manifest["entries"], readback))
    if manifest.get("schema") != PROJECTION_COVERAGE_SCHEMA:
        violations.append(_violation("fingerprint_mismatch", "invalid manifest schema"))
    if manifest["universe_fingerprint"] != universe["source_fingerprint"]:
        violations.append(
            _violation("fingerprint_mismatch", "universe fingerprint mismatch")
        )
    if (
        readback["artifact_id"] != manifest["artifact_id"]
        or readback["artifact_format"] != manifest["artifact_format"]
        or readback["renderer_id"] != manifest["renderer_id"]
    ):
        violations.append(
            _violation("artifact_mismatch", "readback artifact metadata mismatch")
        )
    source_counts = _counts_from_items(universe["items"])
    rendered_counts = _counts_from_entries(manifest["entries"])
    readback_counts = dict(readback["readback_counts"])
    if (
        manifest["source_counts"] != source_counts
        or manifest["rendered_counts"] != rendered_counts
        or manifest["readback_counts"] != readback_counts
        or set(source_counts) != set(SOURCE_ITEM_KINDS)
        or set(rendered_counts) != set(SOURCE_ITEM_KINDS)
        or set(readback_counts) != set(SOURCE_ITEM_KINDS)
    ):
        violations.append(_violation("count_mismatch", "coverage count map mismatch"))
    expected_digest = _coverage_digest(manifest)
    if manifest["coverage_digest"] != expected_digest:
        violations.append(
            _violation("fingerprint_mismatch", "manifest coverage digest mismatch")
        )
    if readback["coverage_digest"] != manifest["coverage_digest"]:
        violations.append(
            _violation("readback_mismatch", "final-artifact coverage digest mismatch")
        )
    violations.extend(manifest["violations"])
    violations.extend(readback["violations"])
    complete_violations = _sorted_violations(violations)
    source_ids = {item["item_id"] for item in universe["items"]}
    mapped_ids = {entry["source_item_id"] for entry in manifest["entries"]}
    missing = sorted(source_ids - mapped_ids)
    expected_readback = {entry["readback_identity"] for entry in manifest["entries"]}
    orphan = sorted(set(readback["identities"]) - expected_readback)
    return {
        "status": "fail" if complete_violations or missing or orphan else "pass",
        "missing_item_ids": missing,
        "orphan_rendered_ids": orphan,
        "violations": complete_violations,
        "coverage_digest": manifest["coverage_digest"],
        "source_counts": source_counts,
        "rendered_counts": rendered_counts,
        "readback_counts": readback_counts,
    }


def _validate_argument_items(
    value: object,
    origin: SourceItemOrigin,
    field: str,
) -> list[VisualizationSourceItem]:
    if not isinstance(value, list):
        raise ValueError(f"invalid_tool_call:{field}")
    copied: list[VisualizationSourceItem] = []
    for item in cast(list[object], value):
        if not isinstance(item, Mapping):
            raise ValueError(f"invalid_tool_call:{field}")
        try:
            copied.append(_copy_source_item(cast(Mapping[str, object], item), origin))
        except (TypeError, ValueError):
            raise ValueError(f"invalid_tool_call:{field}") from None
    return copied


def _validate_tool_call(tool_call: object) -> ToolCall:
    if not isinstance(tool_call, Mapping):
        raise ValueError("invalid_tool_call:tool_call")
    tool_call_record = cast(Mapping[str, object], tool_call)
    try:
        fields: set[str] = set(tool_call_record)
    except TypeError:
        raise ValueError("invalid_tool_call:fields") from None
    if fields != {"schema", "tool_id", "argument_schema", "arguments"}:
        raise ValueError("invalid_tool_call:fields")
    schema = tool_call_record.get("schema")
    if not isinstance(schema, str):
        raise ValueError("invalid_tool_call:schema")
    if schema != TOOL_CALL_SCHEMA:
        raise ValueError("schema_mismatch:tool_call")
    raw_tool_id = tool_call_record.get("tool_id")
    tool_id = _typed_literal(raw_tool_id, _TOOL_ID_BY_VALUE)
    if tool_id is None:
        raise ValueError("invalid_tool_call:tool_id")
    argument_schema = tool_call_record.get("argument_schema")
    if not isinstance(argument_schema, str):
        raise ValueError("invalid_tool_call:argument_schema")
    expected_argument_schema = TOOL_ARGUMENT_SCHEMAS[tool_id]
    if argument_schema != expected_argument_schema:
        raise ValueError("schema_mismatch:argument_schema")
    arguments = tool_call_record.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("invalid_tool_call:arguments")
    argument_record = cast(dict[str, object], arguments)
    required = _SHARED_ARGUMENT_FIELDS | set(_TOOL_LOCATOR_FIELDS[tool_id])
    allowed = required | {"filters"}
    if set(argument_record) != required and set(argument_record) != allowed:
        raise ValueError("invalid_tool_call:argument_fields")
    for field in ("request_id", "artifact_id", "renderer_id"):
        if not isinstance(argument_record.get(field), str) or not argument_record[field]:
            raise ValueError(f"invalid_tool_call:{field}")
    if not isinstance(argument_record.get("literal_request"), str):
        raise ValueError("invalid_tool_call:literal_request")
    if argument_record.get("artifact_format") not in ARTIFACT_FORMATS:
        raise ValueError("invalid_tool_call:artifact_format")
    literal_items = _validate_argument_items(
        argument_record.get("literal_items"),
        "literal_request",
        "literal_items",
    )
    owner_items = _validate_argument_items(
        argument_record.get("owner_closure"),
        "owner_closure",
        "owner_closure",
    )
    dependency_items = _validate_argument_items(
        argument_record.get("dependency_closure"),
        "dependency_closure",
        "dependency_closure",
    )
    for locator in _TOOL_LOCATOR_FIELDS[tool_id]:
        if not isinstance(argument_record.get(locator), str) or not argument_record[locator]:
            raise ValueError(f"invalid_tool_call:{locator}")
    filters = argument_record.get("filters", [])
    if not isinstance(filters, list):
        raise ValueError("invalid_tool_call:filters")
    item_ids = {
        item["item_id"] for item in (*literal_items, *owner_items, *dependency_items)
    }
    for record in cast(list[object], filters):
        if not isinstance(record, Mapping):
            raise ValueError("invalid_tool_call:filters")
        try:
            _copy_filter(cast(Mapping[str, object], record), item_ids)
        except (TypeError, ValueError):
            raise ValueError("invalid_tool_call:filters") from None
    try:
        normalized_arguments = _normalize_json(argument_record, "arguments")
    except (TypeError, ValueError):
        raise ValueError("invalid_tool_call:arguments") from None
    if not isinstance(normalized_arguments, dict):
        raise ValueError("invalid_tool_call:arguments")
    validated: ToolCall = {
        "schema": "agent_canon.visualization_tool_call.v1",
        "tool_id": tool_id,
        "argument_schema": expected_argument_schema,
        "arguments": normalized_arguments,
    }
    return validated


def serialize_tool_call(tool_call: object) -> str:
    """Validate and canonically serialize one exact owner or adapter ToolCall."""
    return _canonical_json(_validate_tool_call(tool_call))


def _coverage_marker(manifest: ProjectionCoverageManifest) -> str:
    payload = base64.urlsafe_b64encode(
        _canonical_json(manifest).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return COVERAGE_MARKER_PREFIX + payload


def _identity_token(identity: str) -> str:
    payload = base64.urlsafe_b64encode(identity.encode("utf-8")).decode("ascii").rstrip("=")
    return IDENTITY_TOKEN_PREFIX + payload


def serialize_projection_identity(identity: object) -> str:
    """Serialize one non-empty projection identity to its canonical token."""
    if not isinstance(identity, str) or not identity:
        raise ValueError("invalid_identity:projection")
    return _identity_token(identity)


def serialize_projection_coverage_manifest(
    manifest: ProjectionCoverageManifest,
    *,
    owner_tool_call: ToolCall,
    adapter_tool_call: ToolCall,
) -> str:
    """Serialize one complete manifest after the owner-first adapter gate."""
    manifest_fields = {
        "schema",
        "universe_fingerprint",
        "artifact_id",
        "renderer_id",
        "artifact_format",
        "entries",
        "source_counts",
        "rendered_counts",
        "readback_counts",
        "omitted_item_ids",
        "violations",
        "filters",
        "coverage_digest",
        "status",
    }
    if set(manifest) != manifest_fields:
        raise ValueError("invalid_payload:projection_manifest")
    owner = _validate_tool_call(owner_tool_call)
    adapter = _validate_tool_call(adapter_tool_call)
    if owner["tool_id"] != "agent_canon.visualization.coverage":
        raise ValueError("invalid_tool_call:owner_tool_id")
    if adapter["tool_id"] == "agent_canon.visualization.coverage":
        raise ValueError("invalid_tool_call:adapter_tool_id")
    if adapter["tool_id"] == "agent_canon.visualization.adapter.algorithm_flowchart":
        if manifest["artifact_format"] != "markdown_mermaid":
            raise ValueError("invalid_tool_call:artifact_format")
        if manifest["renderer_id"] != adapter["tool_id"]:
            raise ValueError("invalid_tool_call:renderer_id")

    owner_arguments = owner["arguments"]
    adapter_arguments = adapter["arguments"]
    for field in (
        "request_id",
        "literal_request",
        "literal_items",
        "owner_closure",
        "dependency_closure",
    ):
        if owner_arguments[field] != adapter_arguments[field]:
            raise ValueError("invalid_tool_call:shared_arguments")
    if owner_arguments.get("filters", []) != adapter_arguments.get("filters", []):
        raise ValueError("invalid_tool_call:shared_arguments")
    for field in ("artifact_id", "renderer_id", "artifact_format"):
        if (
            owner_arguments[field] != adapter_arguments[field]
            or owner_arguments[field] != manifest[field]
        ):
            raise ValueError(f"invalid_tool_call:{field}")

    universe = build_source_universe(
        request_id=cast(str, owner_arguments["request_id"]),
        literal_request=cast(str, owner_arguments["literal_request"]),
        literal_items=cast(list[VisualizationSourceItem], owner_arguments["literal_items"]),
        owner_closure=cast(list[VisualizationSourceItem], owner_arguments["owner_closure"]),
        dependency_closure=cast(
            list[VisualizationSourceItem], owner_arguments["dependency_closure"]
        ),
        filters=cast(list[FilterRecord], owner_arguments.get("filters", [])),
    )
    source_counts = _counts_from_items(universe["items"])
    if (
        manifest.get("schema") != PROJECTION_COVERAGE_SCHEMA
        or manifest["universe_fingerprint"] != universe["source_fingerprint"]
        or manifest["source_counts"] != source_counts
        or manifest["source_counts"] != manifest["rendered_counts"]
        or manifest["source_counts"] != manifest["readback_counts"]
        or sum(source_counts.values()) != len(manifest["entries"])
        or manifest["omitted_item_ids"]
        or manifest["violations"]
        or manifest["status"] != "pass"
        or manifest["coverage_digest"] != _coverage_digest(manifest)
    ):
        raise ValueError("invalid_payload:projection_manifest")
    return _coverage_marker(manifest)


def _decode_identity_token(token: str) -> str | None:
    if not token.startswith(IDENTITY_TOKEN_PREFIX):
        return None
    payload = token[len(IDENTITY_TOKEN_PREFIX) :]
    try:
        return base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode(
            "utf-8"
        )
    except (ValueError, UnicodeDecodeError):
        return None


def _readback_failure(
    artifact_id: str,
    artifact_format: ArtifactFormat,
    renderer_id: str,
    violations: Sequence[CoverageViolation],
) -> ReadbackProjection:
    complete = _sorted_violations(violations)
    return {
        "artifact_id": artifact_id,
        "artifact_format": artifact_format,
        "renderer_id": renderer_id,
        "identities": {},
        "readback_counts": _empty_counts(),
        "coverage_digest": _sha256(
            {
                "artifact_id": artifact_id,
                "artifact_format": artifact_format,
                "renderer_id": renderer_id,
                "violations": complete,
            }
        ),
        "status": "fail",
        "violations": complete,
    }


def _artifact_text(artifact: bytes | str | Path) -> str:
    payload = artifact.read_bytes() if isinstance(artifact, Path) else artifact
    if isinstance(payload, bytes):
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("artifact is not UTF-8") from exc
    return payload


class _CoverageMarkerHTMLParser(HTMLParser):
    """Extract the first canonical coverage-marker script payload."""

    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self._parts: list[str] = []
        self.contents: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "script" or self._capturing or self.contents:
            return
        attributes = {name.casefold(): value for name, value in attrs}
        if (
            attributes.get("type") == "application/json"
            and attributes.get("id") == "agent-canon-visualization-coverage"
        ):
            self._capturing = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capturing and tag.casefold() == "script":
            self.contents.append("".join(self._parts))
            self._capturing = False


@dataclass
class _HTMLFrame:
    """Small deterministic DOM frame used by HTML readback."""

    tag: str
    attrs: dict[str, str | None]
    source: str
    hidden: bool
    non_rendered: bool
    svg_context: bool
    text_parts: list[str] = dataclass_field(default_factory=lambda: list[str]())
    cells: list[str] = dataclass_field(default_factory=lambda: list[str]())
    child_tags: list[str] = dataclass_field(default_factory=lambda: list[str]())
    titles: list[str] = dataclass_field(default_factory=lambda: list[str]())

    @property
    def text(self) -> str:
        return " ".join("".join(self.text_parts).split())


@dataclass(frozen=True)
class _HTMLVisibleRecord:
    """One structural visible/readable source record."""

    surface: str
    source_id: str
    text: str
    cells: tuple[str, ...]
    titles: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class _HTMLScriptBlock:
    """One executable or data script block."""

    attrs: dict[str, str | None]
    text: str
    source: str


def _html_source(parser: HTMLParser) -> str:
    line, column = parser.getpos()
    return f"line:{line}:column:{column}"


def _inline_hidden(attrs: Mapping[str, str | None]) -> bool:
    if "hidden" in attrs:
        return True
    if (attrs.get("aria-hidden") or "").casefold() == "true":
        return True
    style = (attrs.get("style") or "").casefold()
    return bool(
        re.search(r"(?:^|[;\s])display\s*:\s*none(?:\s*;|\s*$)", style)
        or re.search(r"(?:^|[;\s])visibility\s*:\s*hidden(?:\s*;|\s*$)", style)
    )


def _css_unescape(value: str) -> str:
    value = re.sub(r"\\\r?\n", "", value)
    return re.sub(r"\\([0-9a-fA-F]{1,6})(?:\s)?", lambda m: chr(int(m.group(1), 16)), value)


def _resource_violation(
    code: ViolationCode,
    value: str,
    source: str,
    context: str,
) -> CoverageViolation:
    return _violation(code, f"{context} resource {value!r} at {source}", artifact_locator=source)


def _check_local_resource(
    value: str,
    *,
    source: str,
    context: str,
) -> CoverageViolation | None:
    candidate = _css_unescape(value).strip().strip('"\'')
    if not candidate:
        return _resource_violation(
            "malformed_resource_locator", candidate, source, context
        )
    if candidate.startswith("#") or candidate.casefold().startswith("data:"):
        return None
    return _resource_violation("external_resource", candidate, source, context)


def _scan_css_resources(text: str, *, source: str) -> list[CoverageViolation]:
    """Scan only CSS url()/@import resource syntax, ignoring comments/strings."""
    violations: list[CoverageViolation] = []
    index = 0
    length = len(text)

    def skip_comment(position: int) -> int:
        end = text.find("*/", position + 2)
        if end < 0:
            violations.append(
                _resource_violation(
                    "malformed_resource_locator", "/*", source, "CSS comment"
                )
            )
            return length
        return end + 2

    def skip_quoted(position: int, quote: str) -> int:
        position += 1
        while position < length:
            if text[position] == "\\":
                position += 2
            elif text[position] == quote:
                return position + 1
            else:
                position += 1
        violations.append(
            _resource_violation(
                "malformed_resource_locator", quote, source, "CSS string"
            )
        )
        return length

    def read_url(position: int) -> int:
        opening = text.find("(", position)
        if opening < 0:
            violations.append(
                _resource_violation(
                    "malformed_resource_locator", text[position:], source, "CSS url"
                )
            )
            return length
        cursor = opening + 1
        quote = text[cursor] if cursor < length and text[cursor] in "'\"" else None
        if quote is not None:
            end = cursor + 1
            value_parts: list[str] = []
            while end < length:
                if text[end] == "\\" and end + 1 < length:
                    value_parts.append(text[end : end + 2])
                    end += 2
                elif text[end] == quote:
                    end += 1
                    break
                else:
                    value_parts.append(text[end])
                    end += 1
            else:
                violations.append(
                    _resource_violation(
                        "malformed_resource_locator", text[position:], source, "CSS url"
                    )
                )
                return length
            while end < length and text[end].isspace():
                end += 1
            if end >= length or text[end] != ")":
                violations.append(
                    _resource_violation(
                        "malformed_resource_locator", text[position:], source, "CSS url"
                    )
                )
                return length
            value = "".join(value_parts)
            end += 1
        else:
            end = cursor
            while end < length and text[end] != ")":
                if text[end] == "\\" and end + 1 < length:
                    end += 2
                else:
                    end += 1
            if end >= length:
                violations.append(
                    _resource_violation(
                        "malformed_resource_locator", text[position:], source, "CSS url"
                    )
                )
                return length
            value = text[cursor:end].strip()
            end += 1
        resource_violation = _check_local_resource(
            value, source=source, context="CSS"
        )
        if resource_violation is not None:
            violations.append(resource_violation)
        return end

    while index < length:
        if text.startswith("/*", index):
            index = skip_comment(index)
            continue
        if text[index] in "'\"":
            index = skip_quoted(index, text[index])
            continue
        if text[index : index + 4].casefold() == "url(" and (
            index == 0 or not (text[index - 1].isalnum() or text[index - 1] in "_-"
            )
        ):
            index = read_url(index)
            continue
        if text[index] == "@" and text[index : index + 7].casefold() == "@import":
            index += 7
            while index < length and text[index].isspace():
                index += 1
            if text[index : index + 4].casefold() == "url(":
                index = read_url(index)
                continue
            if index < length and text[index] in "'\"":
                quote = text[index]
                start = index + 1
                index = skip_quoted(index, quote)
                value = text[start : max(start, index - 1)]
                resource_violation = _check_local_resource(
                    value, source=source, context="CSS @import"
                )
                if resource_violation is not None:
                    violations.append(resource_violation)
                continue
            violations.append(
                _resource_violation(
                    "malformed_resource_locator", text[index:], source, "CSS @import"
                )
            )
            continue
        index += 1
    return violations


def _scan_javascript_network(
    text: str,
    *,
    source: str,
    module_script: bool = False,
) -> list[CoverageViolation]:
    """Reject executable network APIs without scanning strings, comments, or regex data."""
    violations: list[CoverageViolation] = []
    length = len(text)
    index = 0
    previous_significant = ""
    previous_word = ""
    control_parens: list[bool] = []
    regex_after_control_close = False
    regex_prefix_words = {
        "case", "delete", "do", "else", "in", "instanceof", "of",
        "return", "throw", "typeof", "void", "yield", "await",
    }
    control_words = {"catch", "for", "if", "switch", "while", "with"}

    def skip_quoted(position: int, quote: str) -> int:
        position += 1
        while position < length:
            if text[position] == "\\":
                position += 2
            elif text[position] == quote:
                return position + 1
            else:
                position += 1
        violations.append(
            _resource_violation(
                "malformed_resource_locator", quote, source, "JavaScript string"
            )
        )
        return length

    def skip_regex(position: int) -> int:
        position += 1
        in_class = False
        while position < length:
            character = text[position]
            if character == "\\":
                position += 2
                continue
            if character == "[":
                in_class = True
            elif character == "]":
                in_class = False
            elif character == "/" and not in_class:
                position += 1
                while position < length and text[position].isalpha():
                    position += 1
                return position
            position += 1
        violations.append(
            _resource_violation(
                "malformed_resource_locator", "/", source, "JavaScript regex"
            )
        )
        return length

    def skip_template(position: int) -> int:
        position += 1
        while position < length:
            if text[position] == "\\":
                position += 2
                continue
            if text[position] == "`":
                return position + 1
            if text.startswith("${", position):
                depth = 1
                cursor = position + 2
                while cursor < length and depth:
                    if text[cursor] in "'\"`":
                        cursor = skip_quoted(cursor, text[cursor]) if text[cursor] != "`" else skip_template(cursor)
                        continue
                    if text[cursor] == "{":
                        depth += 1
                    elif text[cursor] == "}":
                        depth -= 1
                    cursor += 1
                if depth:
                    violations.append(
                        _resource_violation(
                            "malformed_resource_locator", "${", source, "JavaScript template"
                        )
                    )
                    return length
                violations.extend(
                    _scan_javascript_network(
                        text[position + 2 : cursor - 1],
                        source=source,
                        module_script=module_script,
                    )
                )
                position = cursor
                continue
            position += 1
        violations.append(
            _resource_violation(
                "malformed_resource_locator", "`", source, "JavaScript template"
            )
        )
        return length

    def next_word(position: int) -> tuple[str, int]:
        end = position
        while end < length and (text[end].isalnum() or text[end] in "_$"):
            end += 1
        return text[position:end], end

    while index < length:
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = length if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                violations.append(
                    _resource_violation(
                        "malformed_resource_locator", "/*", source, "JavaScript comment"
                    )
                )
                break
            index = end + 2
            continue
        if character in "'\"":
            index = skip_quoted(index, character)
            previous_word = ""
            regex_after_control_close = False
            continue
        if character == "`":
            index = skip_template(index)
            previous_word = ""
            regex_after_control_close = False
            continue
        if character == "/" and (
            previous_significant in "=(\\[{!?:;," or previous_significant in {"", "}"}
            or previous_word in regex_prefix_words
            or regex_after_control_close
        ):
            index = skip_regex(index)
            previous_significant = "/"
            previous_word = ""
            regex_after_control_close = False
            continue
        if character == "(":
            control_parens.append(previous_word in control_words)
            previous_word = ""
            regex_after_control_close = False
            previous_significant = character
            index += 1
            continue
        if character == ")":
            regex_after_control_close = bool(control_parens.pop()) if control_parens else False
            previous_word = ""
            previous_significant = character
            index += 1
            continue
        if character.isalpha() or character in "_$":
            word, end = next_word(index)
            cursor = end
            while cursor < length and text[cursor].isspace():
                cursor += 1
            if word in {
                "fetch", "XMLHttpRequest", "WebSocket", "EventSource", "import"
            } and cursor < length and text[cursor] == "(":
                violations.append(
                    _resource_violation(
                        "script_network_api", word, source, "JavaScript"
                    )
                )
            elif (
                module_script
                and word == "import"
                and cursor < length
                and text[cursor] != "."
                and previous_significant != "."
            ):
                violations.append(
                    _resource_violation(
                        "script_network_api", "static import", source, "JavaScript"
                    )
                )
            elif word == "navigator":
                dot = cursor
                if dot < length and text[dot] == ".":
                    dot += 1
                    while dot < length and text[dot].isspace():
                        dot += 1
                    member, member_end = next_word(dot)
                    call = member_end
                    while call < length and text[call].isspace():
                        call += 1
                    if member == "sendBeacon" and call < length and text[call] == "(":
                        violations.append(
                            _resource_violation(
                                "script_network_api", "navigator.sendBeacon", source, "JavaScript"
                            )
                        )
            previous_word = word
            regex_after_control_close = False
            previous_significant = word[-1:] or previous_significant
            index = end
            continue
        previous_word = ""
        regex_after_control_close = False
        previous_significant = character
        index += 1
    return violations


class _HTMLReadbackParser(HTMLParser):
    """Parse visible evidence and resource-bearing contexts in one HTML pass."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.frames: list[_HTMLFrame] = []
        self.records: list[_HTMLVisibleRecord] = []
        self.scripts: list[_HTMLScriptBlock] = []
        self.styles: list[tuple[str, str]] = []
        self.violations: list[CoverageViolation] = []
        self.tables: set[str] = set()
        self.svg_ids: set[str] = set()
        self._script_frame: _HTMLFrame | None = None
        self._style_frame: _HTMLFrame | None = None

    @property
    def _hidden_parent(self) -> bool:
        return bool(self.frames and (self.frames[-1].hidden or self.frames[-1].non_rendered))

    def _resource_attribute(
        self,
        tag: str,
        name: str,
        value: str | None,
        source: str,
        *,
        svg_context: bool,
    ) -> None:
        if value is None:
            return
        lowered = name.casefold()
        if lowered == "srcset":
            candidates = [part.strip().split()[0] for part in value.split(",") if part.strip()]
            for candidate in candidates:
                violation = _check_local_resource(candidate, source=source, context=f"HTML {name}")
                if violation is not None:
                    self.violations.append(violation)
            return
        resource_attrs = {
            "src", "href", "xlink:href", "poster", "cite", "action", "formaction",
            "background", "manifest", "data",
        }
        svg_resource_attrs = {
            "fill", "stroke", "marker-start", "marker-mid", "marker-end",
            "clip-path", "mask", "filter", "cursor",
        }
        if svg_context and lowered in svg_resource_attrs:
            scalar = value.strip()
            if scalar.casefold().startswith("url("):
                css_violations = _scan_css_resources(value, source=source)
                self.violations.extend(css_violations)
            elif scalar.startswith("#"):
                violation = _check_local_resource(value, source=source, context=f"HTML {name}")
                if violation is not None:
                    self.violations.append(violation)
            return
        if lowered in resource_attrs:
            if lowered == "content" and tag == "meta":
                return
            violation = _check_local_resource(value, source=source, context=f"HTML {name}")
            if violation is not None:
                self.violations.append(violation)
        if tag == "meta" and lowered == "content":
            refresh = ""  # The http-equiv check is applied in handle_starttag.
            del refresh

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = {name.casefold(): value for name, value in attrs}
        source = _html_source(self)
        inherited_hidden = self._hidden_parent
        non_rendered = bool(
            inherited_hidden
            or tag.casefold() in {"script", "template", "style", "noscript"}
        )
        frame = _HTMLFrame(
            tag=tag.casefold(),
            attrs=normalized,
            source=source,
            hidden=inherited_hidden or _inline_hidden(normalized),
            non_rendered=non_rendered,
            svg_context=bool(
                tag.casefold() == "svg"
                or (self.frames and self.frames[-1].svg_context)
            ),
        )
        self.frames.append(frame)
        element_id = normalized.get("id")
        if element_id in {"node-table", "edge-table", "directory-node-table", "directory-edge-table"}:
            self.tables.add(str(element_id))
        if tag.casefold() == "svg" and element_id:
            self.svg_ids.add(element_id)
        for name, value in attrs:
            self._resource_attribute(
                tag.casefold(),
                name,
                value,
                source,
                svg_context=frame.svg_context,
            )
        if tag.casefold() == "meta" and (normalized.get("http-equiv") or "").casefold() == "refresh":
            content = normalized.get("content") or ""
            match = re.search(r"(?:^|;)\s*url\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^;\s]*))", content, re.I)
            if match is None:
                self.violations.append(
                    _resource_violation("malformed_resource_locator", content, source, "HTML refresh")
                )
            else:
                value = next(part for part in match.groups() if part is not None)
                violation = _check_local_resource(value, source=source, context="HTML refresh")
                if violation is not None:
                    self.violations.append(violation)
        style = normalized.get("style")
        if style:
            self.violations.extend(_scan_css_resources(style, source=source))
        if tag.casefold() == "script":
            self._script_frame = frame
        if tag.casefold() == "style":
            self._style_frame = frame
        if tag.casefold() in {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr",
        }:
            self.frames.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if not self.frames:
            return
        for frame in self.frames:
            frame.text_parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")

    def _surface_for(self, frame: _HTMLFrame) -> str | None:
        if frame.hidden or frame.non_rendered or "data-agent-canon-source-id" not in frame.attrs:
            return None
        source_id = frame.attrs.get("data-agent-canon-source-id")
        if not source_id:
            return None
        ancestors = self.frames[:-1]
        static_graph = any(parent.attrs.get("id") == "static-graph" for parent in ancestors)
        if static_graph and "static-node" in (frame.attrs.get("class") or "").split() and frame.tag == "g":
            return "static-node"
        if static_graph and "static-edge" in (frame.attrs.get("class") or "").split() and frame.tag == "path":
            return "static-edge"
        table_id = next((parent.attrs.get("id") for parent in ancestors if parent.tag == "table"), None)
        if frame.tag == "tr" and table_id in {
            "node-table", "edge-table", "directory-node-table", "directory-edge-table"
        }:
            return str(table_id)
        return None

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        frame_index = next((index for index in range(len(self.frames) - 1, -1, -1) if self.frames[index].tag == tag), None)
        if frame_index is None:
            return
        frame = self.frames.pop(frame_index)
        if self.frames:
            parent = self.frames[-1]
            parent.child_tags.append(frame.tag)
            if frame.tag in {"td", "th"}:
                parent.cells.append(frame.text)
        if frame.tag == "script":
            self.scripts.append(_HTMLScriptBlock(frame.attrs, frame.text, frame.source))
            self._script_frame = None
        elif frame.tag == "style":
            self.styles.append((frame.text, frame.source))
            self._style_frame = None
        if self.frames:
            parent = self.frames[-1]
            if frame.tag == "title":
                parent.titles.append(frame.text)
        surface = self._surface_for(frame)
        if surface is not None:
            if frame.tag == "g" and "static-node" in (frame.attrs.get("class") or "").split() and "rect" not in frame.child_tags:
                return
            if frame.tag == "path" and "static-edge" in (frame.attrs.get("class") or "").split() and "title" not in frame.child_tags:
                return
            self.records.append(
                _HTMLVisibleRecord(
                    surface=surface,
                    source_id=str(frame.attrs["data-agent-canon-source-id"]),
                    text=frame.text,
                    cells=tuple(frame.cells),
                    titles=tuple(frame.titles),
                    source=frame.source,
                )
            )

    def close(self) -> None:
        super().close()
        if self.frames:
            self.violations.append(
                _resource_violation(
                    "malformed_resource_locator", self.frames[-1].tag, self.frames[-1].source, "HTML"
                )
            )
        for text, source in self.styles:
            self.violations.extend(_scan_css_resources(text, source=source))
        for script in self.scripts:
            script_type = (script.attrs.get("type") or "").casefold().split(";", 1)[0].strip()
            if script.attrs.get("id") in {
                "agent-canon-visualization-coverage", "graph-data"
            } or script_type not in {"", "text/javascript", "application/javascript", "module"}:
                continue
            self.violations.extend(
                _scan_javascript_network(
                    script.text,
                    source=script.source,
                    module_script=script_type == "module",
                )
            )


def _extract_marker(
    text: str,
    artifact_format: ArtifactFormat,
) -> tuple[str | None, CoverageViolation | None]:
    marker: str | None = None
    if artifact_format == "graph_ir":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None, _violation("malformed_marker", "GraphIR is not valid JSON")
        if isinstance(payload, dict):
            payload_record = cast(dict[str, object], payload)
            marker_object = payload_record.get("visualization_coverage")
            if isinstance(marker_object, dict):
                marker_record = cast(dict[str, object], marker_object)
                candidate = marker_record.get("marker")
                marker = candidate if isinstance(candidate, str) else None
    elif artifact_format == "markdown_mermaid":
        match = re.search(
            rf"<!--\s*({re.escape(COVERAGE_MARKER_PREFIX)}[A-Za-z0-9_-]+)\s*-->\s*```mermaid",
            text,
        )
        marker = match.group(1) if match else None
    elif artifact_format == "dot":
        match = re.search(
            rf"(?m)^\s*//\s*({re.escape(COVERAGE_MARKER_PREFIX)}[A-Za-z0-9_-]+)\s*$",
            text,
        )
        marker = match.group(1) if match else None
    elif artifact_format == "html":
        parser = _CoverageMarkerHTMLParser()
        parser.feed(text)
        parser.close()
        if parser.contents:
            content = parser.contents[0].strip()
            try:
                decoded = json.loads(content)
            except json.JSONDecodeError:
                decoded = content
            marker = decoded if isinstance(decoded, str) else None
    if marker is None:
        return None, _violation("missing_marker", "final artifact has no coverage marker")
    return marker, None


def _decode_marker(marker: str) -> ProjectionCoverageManifest:
    if not marker.startswith(COVERAGE_MARKER_PREFIX):
        raise ValueError("marker prefix mismatch")
    payload = marker[len(COVERAGE_MARKER_PREFIX) :]
    try:
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode(
            "utf-8"
        )
        raw: object = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("marker payload is malformed") from exc
    if not isinstance(raw, dict):
        raise ValueError("marker manifest schema mismatch")
    raw = cast(dict[str, object], raw)
    if raw.get("schema") != PROJECTION_COVERAGE_SCHEMA:
        raise ValueError("marker manifest schema mismatch")
    required = {
        "schema",
        "universe_fingerprint",
        "artifact_id",
        "renderer_id",
        "artifact_format",
        "entries",
        "source_counts",
        "rendered_counts",
        "readback_counts",
        "omitted_item_ids",
        "violations",
        "filters",
        "coverage_digest",
        "status",
    }
    if set(raw) != required:
        raise ValueError("marker manifest fields mismatch")

    universe_fingerprint = raw.get("universe_fingerprint")
    artifact_id = raw.get("artifact_id")
    renderer_id = raw.get("renderer_id")
    if (
        not isinstance(universe_fingerprint, str)
        or len(universe_fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in universe_fingerprint)
    ):
        raise ValueError("marker universe fingerprint mismatch")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ValueError("marker artifact identity mismatch")
    if not isinstance(renderer_id, str) or not renderer_id:
        raise ValueError("marker renderer identity mismatch")
    artifact_format = _typed_literal(raw.get("artifact_format"), _ARTIFACT_FORMAT_BY_VALUE)
    if artifact_format is None:
        raise ValueError("marker artifact format mismatch")

    raw_entries_value = raw.get("entries")
    raw_entries = cast(list[object], raw_entries_value) if isinstance(raw_entries_value, list) else None
    if not isinstance(raw_entries, list):
        raise ValueError("marker entries mismatch")
    entries: list[ProjectionCoverageEntry] = []
    entry_violations: list[CoverageViolation] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            raise ValueError("marker entry mismatch")
        entry = _copy_entry(cast(Mapping[str, object], raw_entry), renderer_id, entry_violations)
        if entry is None:
            raise ValueError("marker entry mismatch")
        entries.append(entry)
    if len({entry["source_item_id"] for entry in entries}) != len(entries):
        raise ValueError("marker duplicate source identity")

    def decode_counts(value: object, field: str) -> dict[SourceItemKind, int]:
        if not isinstance(value, Mapping):
            raise ValueError(f"marker {field} mismatch")
        value_record = cast(Mapping[str, object], value)
        if set(value_record) != set(SOURCE_ITEM_KINDS):
            raise ValueError(f"marker {field} mismatch")
        counts = _empty_counts()
        for kind in SOURCE_ITEM_KINDS:
            count = value_record.get(kind)
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"marker {field} mismatch")
            counts[kind] = count
        return counts

    source_counts = decode_counts(raw.get("source_counts"), "source counts")
    rendered_counts = decode_counts(raw.get("rendered_counts"), "rendered counts")
    readback_counts = decode_counts(raw.get("readback_counts"), "readback counts")

    raw_omitted_value = raw.get("omitted_item_ids")
    raw_omitted = cast(list[object], raw_omitted_value) if isinstance(raw_omitted_value, list) else None
    if not isinstance(raw_omitted, list):
        raise ValueError("marker omitted identities mismatch")
    omitted_item_ids: list[str] = []
    for item_id in raw_omitted:
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("marker omitted identity mismatch")
        omitted_item_ids.append(item_id)
    if omitted_item_ids != sorted(set(omitted_item_ids)):
        raise ValueError("marker omitted identities are not canonical")

    raw_violations_value = raw.get("violations")
    raw_violations = cast(list[object], raw_violations_value) if isinstance(raw_violations_value, list) else None
    if not isinstance(raw_violations, list):
        raise ValueError("marker violations mismatch")
    violations: list[CoverageViolation] = []
    violation_fields = {
        "code",
        "source_item_id",
        "rendered_identity",
        "artifact_locator",
        "detail",
    }
    for raw_violation in raw_violations:
        if not isinstance(raw_violation, Mapping):
            raise ValueError("marker violation mismatch")
        violation_record = cast(Mapping[str, object], raw_violation)
        if set(violation_record) != violation_fields:
            raise ValueError("marker violation mismatch")
        code = _typed_literal(violation_record.get("code"), _VIOLATION_CODE_BY_VALUE)
        source_item_id = violation_record.get("source_item_id")
        rendered_identity = violation_record.get("rendered_identity")
        artifact_locator = violation_record.get("artifact_locator")
        detail = violation_record.get("detail")
        if code is None or not isinstance(detail, str) or not detail:
            raise ValueError("marker violation mismatch")
        if source_item_id is not None and not isinstance(source_item_id, str):
            raise ValueError("marker violation source identity mismatch")
        if rendered_identity is not None and not isinstance(rendered_identity, str):
            raise ValueError("marker violation rendered identity mismatch")
        if artifact_locator is not None and not isinstance(artifact_locator, str):
            raise ValueError("marker violation artifact locator mismatch")
        violations.append(
            {
                "code": code,
                "source_item_id": source_item_id,
                "rendered_identity": rendered_identity,
                "artifact_locator": artifact_locator,
                "detail": detail,
            }
        )
    if violations != _sorted_violations(violations):
        raise ValueError("marker violations are not canonical")
    if any(violation not in violations for violation in entry_violations):
        raise ValueError("marker entry violations are incomplete")

    raw_filters_value = raw.get("filters")
    raw_filters = cast(list[object], raw_filters_value) if isinstance(raw_filters_value, list) else None
    if not isinstance(raw_filters, list):
        raise ValueError("marker filters mismatch")
    source_item_ids = {
        *(entry["source_item_id"] for entry in entries),
        *omitted_item_ids,
    }
    filters: list[FilterRecord] = []
    for raw_filter in raw_filters:
        if not isinstance(raw_filter, Mapping):
            raise ValueError("marker filter mismatch")
        filters.append(_copy_filter(cast(Mapping[str, object], raw_filter), source_item_ids))
    filters.sort(key=lambda record: record["filter_id"])
    if len({record["filter_id"] for record in filters}) != len(filters):
        raise ValueError("marker duplicate filter identity")

    coverage_digest = raw.get("coverage_digest")
    if (
        not isinstance(coverage_digest, str)
        or len(coverage_digest) != 64
        or any(character not in "0123456789abcdef" for character in coverage_digest)
    ):
        raise ValueError("marker coverage digest mismatch")
    status = _typed_literal(raw.get("status"), _MANIFEST_STATUS_BY_VALUE)
    if status is None:
        raise ValueError("marker status mismatch")

    manifest: ProjectionCoverageManifest = {
        "schema": "agent_canon.projection_coverage_manifest.v1",
        "universe_fingerprint": universe_fingerprint,
        "artifact_id": artifact_id,
        "renderer_id": renderer_id,
        "artifact_format": artifact_format,
        "entries": entries,
        "source_counts": source_counts,
        "rendered_counts": rendered_counts,
        "readback_counts": readback_counts,
        "omitted_item_ids": omitted_item_ids,
        "violations": violations,
        "filters": filters,
        "coverage_digest": coverage_digest,
        "status": status,
    }
    return manifest


def _html_entry_payload(
    entry: ProjectionCoverageEntry,
) -> Mapping[str, JsonValue] | None:
    try:
        payload = _parse_json(entry["payload_json"])
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _html_identity_class(source_id: str) -> str | None:
    if re.fullmatch(r"node:.+", source_id):
        return "native_node"
    if re.fullmatch(r"edge:\d+:[^:]+:[^:]+:.+:.+", source_id):
        return "dependency_edge"
    if re.fullmatch(r"dir:.+", source_id):
        return "directory_node"
    if re.fullmatch(r"contains:\d+", source_id):
        return "containment_edge"
    return None


def _html_entry_ordinal(source_id: str, prefix: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(prefix)}:(\d+)(?::.*)?", source_id)
    return int(match.group(1)) if match else None


def _html_normalize(value: object) -> str:
    return " ".join(str(value).split()).casefold()


def _html_visible_record_valid(
    record: _HTMLVisibleRecord,
    entry: ProjectionCoverageEntry,
) -> bool:
    source_id = entry["readback_identity"]
    identity_class = _html_identity_class(source_id)
    payload = _html_entry_payload(entry)
    if identity_class is None or payload is None:
        return False
    if identity_class == "native_node":
        path = source_id[len("node:") :]
        expected = _html_normalize(path)
        if record.surface == "static-node":
            return expected in {_html_normalize(title) for title in record.titles}
        return len(record.cells) >= 4 and _html_normalize(record.cells[3]) == expected
    if identity_class == "directory_node":
        path = source_id[len("dir:") :]
        return len(record.cells) >= 2 and _html_normalize(record.cells[1]) == _html_normalize(path)
    if identity_class == "dependency_edge":
        expected = (
            _html_normalize(payload.get("direction")),
            _html_normalize(payload.get("kind")),
            _html_normalize(payload.get("source")),
            _html_normalize(payload.get("target")),
        )
        if record.surface == "static-edge":
            title = f"{payload.get('direction')}/{payload.get('kind')}: {payload.get('source')} -> {payload.get('target')}"
            return _html_normalize(title) in {
                _html_normalize(candidate) for candidate in record.titles
            }
        return len(record.cells) >= 4 and tuple(
            _html_normalize(cell) for cell in record.cells[:4]
        ) == expected
    expected = (
        _html_normalize(payload.get("parent_path")),
        _html_normalize(payload.get("child_path")),
        _html_normalize(payload.get("child_kind")),
    )
    return len(record.cells) >= 3 and tuple(
        _html_normalize(cell) for cell in record.cells[:3]
    ) == expected


def _html_resource_and_ir_violations(
    parser: _HTMLReadbackParser,
    manifest: ProjectionCoverageManifest,
) -> list[CoverageViolation]:
    """Validate the embedded GraphIR/source mapping for the dependency HTML owner."""
    violations = list(parser.violations)
    graph_data = next(
        (script.text for script in parser.scripts if script.attrs.get("id") == "graph-data"),
        None,
    )
    if graph_data is None:
        return [
            *violations,
            _violation("ir_surface_mismatch", "HTML has no embedded graph-data IR"),
        ]
    try:
        raw_ir: object = json.loads(graph_data)
    except (TypeError, json.JSONDecodeError):
        return [
            *violations,
            _violation("ir_surface_mismatch", "embedded graph-data is malformed"),
        ]
    if not isinstance(raw_ir, dict):
        return [
            *violations,
            _violation("ir_surface_mismatch", "embedded graph-data schema mismatch"),
        ]
    raw_ir_record = cast(dict[str, object], raw_ir)
    if raw_ir_record.get("schema") != "agent_canon.graph_ir.v2":
        return [
            *violations,
            _violation("ir_surface_mismatch", "embedded graph-data schema mismatch"),
        ]
    raw_nodes_value = raw_ir_record.get("nodes")
    raw_edges_value = raw_ir_record.get("edges")
    raw_nodes = cast(list[object], raw_nodes_value) if isinstance(raw_nodes_value, list) else None
    raw_edges = cast(list[object], raw_edges_value) if isinstance(raw_edges_value, list) else None
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return [
            *violations,
            _violation("ir_surface_mismatch", "embedded graph-data node/edge arrays are malformed"),
        ]
    entries = {entry["readback_identity"]: entry for entry in manifest["entries"]}
    native_nodes = {
        source_id[len("node:") :]: source_id
        for source_id in entries
        if _html_identity_class(source_id) == "native_node"
    }
    directory_nodes = {
        source_id[len("dir:") :]: source_id
        for source_id in entries
        if _html_identity_class(source_id) == "directory_node"
    }
    dependency_edges = {
        ordinal: source_id
        for source_id in entries
        if (ordinal := _html_entry_ordinal(source_id, "edge")) is not None
        and _html_identity_class(source_id) == "dependency_edge"
    }
    containment_edges = {
        ordinal: source_id
        for source_id in entries
        if (ordinal := _html_entry_ordinal(source_id, "contains")) is not None
        and _html_identity_class(source_id) == "containment_edge"
    }
    seen_node_ids: set[str] = set()
    seen_native: set[str] = set()
    seen_directories: set[str] = set()
    for node in raw_nodes:
        if not isinstance(node, Mapping):
            violations.append(_violation("ir_surface_mismatch", "GraphIR node is malformed"))
            continue
        node_record = cast(Mapping[str, object], node)
        node_id = node_record.get("id")
        kind = node_record.get("kind")
        if isinstance(node_id, str):
            if node_id in seen_node_ids:
                violations.append(
                    _violation(
                        "ir_surface_mismatch",
                        "GraphIR contains a duplicate node ID",
                        rendered_identity=node_id,
                    )
                )
            seen_node_ids.add(node_id)
        if kind == "repo_path":
            payload = node_record.get("payload_json")
            payload_record = cast(Mapping[str, object], payload) if isinstance(payload, Mapping) else None
            path = payload_record.get("path") if payload_record is not None else None
            if (
                not isinstance(node_id, str)
                or node_id not in native_nodes
                or path != node_id
            ):
                violations.append(_violation("ir_surface_mismatch", "GraphIR has unknown native node", rendered_identity=str(node_id)))
            else:
                seen_native.add(node_id)
        elif kind == "directory":
            payload = node_record.get("payload_json")
            payload_record = cast(Mapping[str, object], payload) if isinstance(payload, Mapping) else None
            path = payload_record.get("path") if payload_record is not None else None
            if not isinstance(node_id, str) or not isinstance(path, str) or node_id != f"dir:{path}" or path not in directory_nodes:
                violations.append(_violation("ir_surface_mismatch", "GraphIR directory mapping mismatch", rendered_identity=str(node_id)))
            else:
                seen_directories.add(path)
        else:
            violations.append(_violation("ir_surface_mismatch", "GraphIR has unknown node kind", rendered_identity=str(node_id)))
    for path in sorted(set(native_nodes) - seen_native):
        violations.append(_violation("ir_surface_mismatch", "GraphIR native node is missing", rendered_identity=f"node:{path}"))
    for path in sorted(set(directory_nodes) - seen_directories):
        violations.append(_violation("ir_surface_mismatch", "GraphIR directory node is missing", rendered_identity=f"dir:{path}"))

    seen_edge_ids: set[str] = set()
    seen_dependencies: set[int] = set()
    seen_containment: set[int] = set()
    for edge in raw_edges:
        if not isinstance(edge, Mapping):
            violations.append(_violation("ir_surface_mismatch", "GraphIR edge is malformed"))
            continue
        edge_record = cast(Mapping[str, object], edge)
        edge_id = edge_record.get("id")
        payload = edge_record.get("payload_json")
        if not isinstance(edge_id, str):
            violations.append(
                _violation(
                    "ir_surface_mismatch",
                    "GraphIR edge has no string ID",
                    rendered_identity=str(edge_id),
                )
            )
            continue
        if edge_id in seen_edge_ids:
            violations.append(
                _violation(
                    "ir_surface_mismatch",
                    "GraphIR contains a duplicate edge ID",
                    rendered_identity=edge_id,
                )
            )
        seen_edge_ids.add(edge_id)
        if edge_record.get("relation") == "contains":
            match = re.fullmatch(r"contains:(\d+)", edge_id)
            ordinal = int(match.group(1)) if match else None
            expected_id = containment_edges.get(ordinal) if ordinal is not None else None
            expected_payload = _html_entry_payload(entries[expected_id]) if expected_id else None
            if expected_id is None or expected_payload is None or not isinstance(payload, Mapping) or ordinal is None:
                violations.append(_violation("ir_surface_mismatch", "GraphIR containment mapping mismatch", rendered_identity=str(edge_id)))
                continue
            payload_record = cast(Mapping[str, object], payload)
            expected = {
                "source": expected_payload.get("source"),
                "target": expected_payload.get("target"),
                "parentPath": expected_payload.get("parent_path"),
                "childPath": expected_payload.get("child_path"),
                "childKind": expected_payload.get("child_kind"),
            }
            if (
                edge_id != f"contains:{ordinal:06d}"
                or edge_record.get("kind") != "contains"
                or edge_record.get("from_node_id") != expected["source"]
                or edge_record.get("to_node_id") != expected["target"]
                or set(payload_record) != set(expected)
                or any(payload_record.get(key) != value for key, value in expected.items())
            ):
                violations.append(_violation("ir_surface_mismatch", "GraphIR containment payload mismatch", rendered_identity=str(edge_id)))
            else:
                seen_containment.add(ordinal)
        else:
            match = re.fullmatch(r"edge:(\d+)", edge_id)
            ordinal = int(match.group(1)) if match else None
            expected_id = dependency_edges.get(ordinal) if ordinal is not None else None
            expected_payload = _html_entry_payload(entries[expected_id]) if expected_id else None
            if expected_id is None or expected_payload is None or not isinstance(payload, Mapping) or ordinal is None:
                violations.append(_violation("ir_surface_mismatch", "GraphIR dependency mapping mismatch", rendered_identity=str(edge_id)))
                continue
            payload_record = cast(Mapping[str, object], payload)
            expected_values = {
                "direction": expected_payload.get("direction"),
                "kind": expected_payload.get("kind"),
                "source": expected_payload.get("source"),
                "target": expected_payload.get("target"),
                "row": ordinal,
            }
            if (
                edge_id != f"edge:{ordinal:06d}"
                or edge_record.get("relation") != expected_values["direction"]
                or edge_record.get("kind") != expected_values["kind"]
                or edge_record.get("from_node_id") != expected_values["source"]
                or edge_record.get("to_node_id") != expected_values["target"]
                or set(payload_record) != set(expected_values)
                or any(payload_record.get(key) != value for key, value in expected_values.items())
            ):
                violations.append(_violation("ir_surface_mismatch", "GraphIR dependency payload mismatch", rendered_identity=str(edge_id)))
            else:
                seen_dependencies.add(ordinal)
    for ordinal in sorted(set(dependency_edges) - seen_dependencies):
        violations.append(_violation("ir_surface_mismatch", "GraphIR dependency edge is missing", rendered_identity=f"edge:{ordinal:06d}"))
    for ordinal in sorted(set(containment_edges) - seen_containment):
        violations.append(_violation("ir_surface_mismatch", "GraphIR containment edge is missing", rendered_identity=f"contains:{ordinal:06d}"))
    return violations


def _html_readback(
    artifact_text: str,
    manifest: ProjectionCoverageManifest,
    *,
    artifact_id: str,
    artifact_format: ArtifactFormat,
    renderer_id: str,
) -> ReadbackProjection:
    parser = _HTMLReadbackParser()
    try:
        parser.feed(artifact_text)
        parser.close()
    except (TypeError, ValueError) as exc:
        return _readback_failure(
            artifact_id,
            artifact_format,
            renderer_id,
            [_violation("malformed_resource_locator", str(exc))],
        )
    violations = _html_resource_and_ir_violations(parser, manifest)
    required_surfaces = {
        "static-graph", "node-table", "edge-table", "directory-node-table", "directory-edge-table"
    }
    missing_surfaces = sorted(required_surfaces - parser.svg_ids - parser.tables)
    for surface in missing_surfaces:
        violations.append(_violation("visible_surface_missing", f"required visible surface is absent: {surface}", artifact_locator=surface))
    entries = {entry["readback_identity"]: entry for entry in manifest["entries"]}
    by_surface: dict[str, dict[str, _HTMLVisibleRecord]] = {}
    for record in parser.records:
        if record.source_id not in entries:
            violations.append(_violation("orphan_rendered_identity", "visible surface contains an unknown identity", rendered_identity=record.source_id, artifact_locator=record.source))
            continue
        surface_entries = by_surface.setdefault(record.surface, {})
        if record.source_id in surface_entries:
            violations.append(_violation("visible_identity_duplicate", "identity occurs more than once on one visible surface", rendered_identity=record.source_id, artifact_locator=record.surface))
            continue
        if not _html_visible_record_valid(record, entries[record.source_id]):
            violations.append(_violation("ir_surface_mismatch", "visible identity payload does not match its source ID", rendered_identity=record.source_id, artifact_locator=record.surface))
            continue
        surface_entries[record.source_id] = record

    native_ids = {source_id for source_id in entries if _html_identity_class(source_id) == "native_node"}
    dependency_ids = {source_id for source_id in entries if _html_identity_class(source_id) == "dependency_edge"}
    directory_ids = {source_id for source_id in entries if _html_identity_class(source_id) == "directory_node"}
    containment_ids = {source_id for source_id in entries if _html_identity_class(source_id) == "containment_edge"}
    required_by_surface = {
        "static-node": native_ids,
        "static-edge": dependency_ids,
        "node-table": native_ids,
        "edge-table": dependency_ids,
        "directory-node-table": directory_ids,
        "directory-edge-table": containment_ids,
    }
    for surface, expected_ids in required_by_surface.items():
        actual = set(by_surface.get(surface, {}))
        for source_id in sorted(expected_ids - actual):
            violations.append(_violation("visible_identity_missing", "required visible identity is absent", rendered_identity=source_id, artifact_locator=surface))

    identities: dict[str, ProjectionCoverageEntry] = {}
    for source_id, entry in entries.items():
        if any(source_id in surface_records for surface_records in by_surface.values()):
            identities[entry["readback_identity"]] = entry
        elif source_id in entries:
            violations.append(_violation("marker_only_identity", "identity exists only in non-visible marker/IR content", source_item_id=entry["source_item_id"], rendered_identity=entry["rendered_identity"]))
    counts = _counts_from_entries(tuple(identities.values()))
    reconstructed_entries = sorted(
        identities.values(),
        key=lambda entry: (entry["source_item_id"], entry["rendered_identity"], entry["readback_identity"]),
    )
    digest = _coverage_digest(manifest, entries=reconstructed_entries, readback_counts=counts)
    if digest != manifest["coverage_digest"]:
        violations.append(_violation("readback_mismatch", "reconstructed coverage digest mismatch"))
    complete = _sorted_violations((*manifest["violations"], *violations))
    return {
        "artifact_id": artifact_id,
        "artifact_format": artifact_format,
        "renderer_id": renderer_id,
        "identities": identities,
        "readback_counts": counts,
        "coverage_digest": digest,
        "status": "fail" if complete else "pass",
        "violations": complete,
    }


def _markdown_projection_shape(artifact_text: str) -> tuple[int, bool]:
    """Return Mermaid block count and table-fallback presence outside fences."""
    fence_character: str | None = None
    fence_length = 0
    mermaid_count = 0
    table_fallback = False
    for line in artifact_text.splitlines():
        stripped = line.lstrip()
        if fence_character is not None:
            if stripped.startswith(fence_character * fence_length):
                fence_character = None
                fence_length = 0
            continue
        fence_match = re.match(r"^(`{3,}|~{3,})([^\s`]*)", stripped)
        if fence_match is not None:
            marker = fence_match.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            if fence_match.group(2).lower() == "mermaid":
                mermaid_count += 1
            continue
        table_line = stripped.strip()
        if "|" not in table_line:
            continue
        cells = [cell.strip() for cell in table_line.strip("|").split("|")]
        if cells and all(
            re.fullmatch(r":?-{3,}:?", cell) is not None for cell in cells
        ):
            table_fallback = True
    return mermaid_count, table_fallback


def readback_projection(
    artifact: bytes | str | Path,
    artifact_format: ArtifactFormat,
    *,
    artifact_id: str,
    renderer_id: str,
) -> ReadbackProjection:
    """Parse coverage and identity tokens from one final formatted artifact."""
    if artifact_format not in ARTIFACT_FORMATS:
        raise ValueError("invalid_payload:artifact_format")
    if not artifact_id or not renderer_id:
        raise ValueError("invalid_identity:readback")
    marker: str | None
    artifact_text: str
    if artifact_format == "tsv":
        sidecar = artifact if isinstance(artifact, Path) else Path(str(artifact))
        expected_name = f"{artifact_id}.coverage.json"
        if sidecar.name != expected_name or not sidecar.is_file():
            return _readback_failure(
                artifact_id,
                artifact_format,
                renderer_id,
                [_violation("missing_sidecar", f"required sidecar: {expected_name}")],
            )
        final_tsv = sidecar.with_name(f"{artifact_id}.tsv")
        if not final_tsv.is_file():
            return _readback_failure(
                artifact_id,
                artifact_format,
                renderer_id,
                [_violation("artifact_mismatch", f"required final TSV: {final_tsv.name}")],
            )
        try:
            sidecar_payload: object = json.loads(sidecar.read_text(encoding="utf-8"))
            marker = sidecar_payload if isinstance(sidecar_payload, str) else None
            artifact_text = final_tsv.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _readback_failure(
                artifact_id,
                artifact_format,
                renderer_id,
                [_violation("malformed_marker", "TSV sidecar is malformed")],
            )
        if marker is None:
            return _readback_failure(
                artifact_id,
                artifact_format,
                renderer_id,
                [_violation("malformed_marker", "TSV sidecar must be one marker string")],
            )
    else:
        try:
            artifact_text = _artifact_text(artifact)
        except (OSError, ValueError):
            return _readback_failure(
                artifact_id,
                artifact_format,
                renderer_id,
                [_violation("artifact_mismatch", "final artifact cannot be read")],
            )
        marker, marker_violation = _extract_marker(artifact_text, artifact_format)
        if marker_violation is not None or marker is None:
            return _readback_failure(
                artifact_id,
                artifact_format,
                renderer_id,
                [marker_violation or _violation("missing_marker", "missing marker")],
            )
    try:
        manifest = _decode_marker(marker)
    except ValueError as exc:
        return _readback_failure(
            artifact_id,
            artifact_format,
            renderer_id,
            [_violation("malformed_marker", str(exc))],
        )
    violations: list[CoverageViolation] = []
    if (
        manifest["artifact_id"] != artifact_id
        or manifest["artifact_format"] != artifact_format
        or manifest["renderer_id"] != renderer_id
    ):
        violations.append(
            _violation("artifact_mismatch", "marker artifact metadata mismatch")
        )
    if (
        artifact_format == "markdown_mermaid"
        and manifest["renderer_id"]
        == "agent_canon.visualization.adapter.algorithm_flowchart"
    ):
        diagram_count, table_fallback = _markdown_projection_shape(artifact_text)
        if diagram_count != 1:
            violations.append(
                _violation(
                    "diagram_count_mismatch",
                    f"algorithm projection requires one Mermaid diagram; found {diagram_count}",
                    artifact_locator=artifact_id,
                )
            )
        if table_fallback:
            violations.append(
                _violation(
                    "table_fallback",
                    "algorithm projection contains a Markdown table outside fences",
                    artifact_locator=artifact_id,
                )
            )
    if artifact_format == "html" and renderer_id == "dependency-manifest-graph":
        html_readback = _html_readback(
            artifact_text,
            manifest,
            artifact_id=artifact_id,
            artifact_format=artifact_format,
            renderer_id=renderer_id,
        )
        if violations:
            complete = _sorted_violations((*html_readback["violations"], *violations))
            html_readback["violations"] = complete
            html_readback["status"] = "fail" if complete else "pass"
        return html_readback
    identities: dict[str, ProjectionCoverageEntry] = {}
    for entry in manifest["entries"]:
        copied = _copy_entry(entry, renderer_id, violations)
        if copied is None:
            continue
        missing_tokens = [
            locator
            for locator in copied["artifact_locator"]
            if locator not in artifact_text
        ]
        if missing_tokens:
            for locator in missing_tokens:
                violations.append(
                    _violation(
                        "missing_token",
                        "listed final-artifact token is absent",
                        source_item_id=copied["source_item_id"],
                        rendered_identity=copied["rendered_identity"],
                        artifact_locator=locator,
                    )
                )
            continue
        readback_id = copied["readback_identity"]
        if readback_id in identities:
            violations.append(
                _violation(
                    "aggregated_source",
                    "duplicate readback identity in marker",
                    source_item_id=copied["source_item_id"],
                    rendered_identity=copied["rendered_identity"],
                )
            )
            continue
        identities[readback_id] = copied
    token_pattern = re.compile(
        rf"{re.escape(IDENTITY_TOKEN_PREFIX)}[A-Za-z0-9_-]+"
    )
    expected_rendered = {entry["rendered_identity"] for entry in manifest["entries"]}
    for token in sorted(set(token_pattern.findall(artifact_text))):
        identity = _decode_identity_token(token)
        if identity is not None and identity not in expected_rendered:
            violations.append(
                _violation(
                    "orphan_rendered_identity",
                    "final syntax contains an identity outside the marker",
                    rendered_identity=identity,
                    artifact_locator=token,
                )
            )
    counts = _counts_from_entries(tuple(identities.values()))
    reconstructed_entries = sorted(
        identities.values(),
        key=lambda entry: (
            entry["source_item_id"],
            entry["rendered_identity"],
            entry["readback_identity"],
        ),
    )
    digest = _coverage_digest(
        manifest,
        entries=reconstructed_entries,
        readback_counts=counts,
    )
    if digest != manifest["coverage_digest"]:
        violations.append(
            _violation("readback_mismatch", "reconstructed coverage digest mismatch")
        )
    complete = _sorted_violations((*manifest["violations"], *violations))
    return {
        "artifact_id": artifact_id,
        "artifact_format": artifact_format,
        "renderer_id": renderer_id,
        "identities": identities,
        "readback_counts": counts,
        "coverage_digest": digest,
        "status": "fail" if complete else "pass",
        "violations": complete,
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--readback", required=True)
    parser.add_argument("--tool-call")
    args = parser.parse_args(argv)
    universe_raw: object = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    manifest_raw: object = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    readback_raw: object = json.loads(Path(args.readback).read_text(encoding="utf-8"))
    if not isinstance(universe_raw, dict) or not isinstance(manifest_raw, dict) or not isinstance(readback_raw, dict):
        parser.error("universe, manifest, and readback must be JSON objects")
    if args.tool_call:
        tool_call_raw: object = json.loads(Path(args.tool_call).read_text(encoding="utf-8"))
        serialize_tool_call(tool_call_raw)
    report = validate_projection_coverage(
        cast(VisualizationSourceUniverse, universe_raw),
        cast(ProjectionCoverageManifest, manifest_raw),
        readback=cast(ReadbackProjection, readback_raw),
    )
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
