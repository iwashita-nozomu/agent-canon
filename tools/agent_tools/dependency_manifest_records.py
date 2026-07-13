"""Decode the current Rust normalized-record wire and produce registry evidence."""

# @dependency-start
# contract implementation
# responsibility Owns the exact current Rust normalized-record decoder/projector and generic relation-registry conformance producer.
# upstream design ../../reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_brief.md current Rust wire mapping and registry artifact contract
# upstream design ../../documents/dependency-manifest-design.md generic dependency manifest transport
# upstream design ../../documents/structured-analysis/graph-dsl.md reusable graph-layer boundary
# downstream implementation ../../tests/agent_tools/test_dependency_manifest_tools.py validates decoder and producer behavior
# downstream implementation ../../tools/agent_tools/bind_r2_scope.py binds this artifact into review evidence
# @dependency-end

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TypedDict, cast

MANIFEST_SCHEMA_VERSION = "dependency_manifest.normalized.v1"
NORMALIZED_RECORD_SET_VERSION = "normalized_record_set.v1"
SNAPSHOT_SCHEMA_VERSION = "source_snapshot.v1"
REGISTRY_VERSION = "relation_registry.v1"
TOOL_VERSION = "agent-canon 0.1.0"
# The producer baseline is conformance evidence, never runtime decision authority.
EXPECTED_REGISTRY_FINGERPRINT = "1308cf12d7d9c2aa8d67b3cff250484d905e70304a6fb3dafdd7da94a7925624"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")

FAMILY_RANK = {
    "source_snapshot.v1": 1,
    "source_identity.v1": 2,
    "dependency_declaration.v1": 3,
    "attestation.v1": 4,
    "normalized_relation.v1": 5,
    "observed_evidence.v1": 6,
    "surface_relation.v1": 7,
    "source_exclusion.v1": 8,
    "ambiguity_a.v1": 9,
    "extractor_capability.v1": 10,
    "normalization_summary.v1": 11,
}

PAYLOAD_KEYS = {
    "source_identity.v1": {
        "identity_id", "logical_id", "repo_rel_path", "canonical_locator",
        "alternate_locators", "locator_kind", "path_role", "file_mode", "exists",
        "is_dirty", "content_hash", "git_blob_or_gitlink", "submodule_commit",
        "snapshot_id",
    },
    "dependency_declaration.v1": {
        "declaration_id", "source_identity_id", "declared_direction", "declared_kind",
        "declared_target", "resolved_target_identity_id", "source_span", "reason",
        "raw_line_hash", "attestation_key", "snapshot_id",
    },
    "attestation.v1": {
        "attestation_id", "attestation_key", "evidence_type", "evidence_id",
        "declaring_identity_id", "dependent_identity_id", "prerequisite_identity_id",
        "declared_direction", "relation_kind", "source_span", "reason", "raw_line_hash",
        "accepted", "rejection_reason", "snapshot_id",
    },
    "normalized_relation.v1": {
        "fact_id", "from_identity_id", "to_identity_id", "relation_kind",
        "semantic_direction", "pair_identity", "attestation_ids", "observation_ids",
        "authority", "accepted", "reconciliation_status", "source_snapshot_id",
        "source_content_hashes",
    },
    "observed_evidence.v1": {
        "observation_id", "extractor_id", "extractor_version", "capability_id",
        "relation_kind", "from_locator", "to_locator", "from_identity_id",
        "to_identity_id", "source_span", "payload_hash", "classification", "accepted",
        "snapshot_id",
    },
    "surface_relation.v1": {
        "relation_id", "relation_type", "source_identity_id", "target_identity_id",
        "source_path", "target_path", "owner_class", "surface_mode", "content_hash_equal",
        "evidence_id", "status", "snapshot_id",
    },
    "source_exclusion.v1": {
        "source_exclusion_id", "source_identity_id", "repo_rel_path", "reason_code",
        "rule_id", "scope", "evidence_id", "covered", "snapshot_id",
    },
    "ambiguity_a.v1": {
        "ambiguity_id", "source_identity_id", "candidate_fact_ids", "candidate_targets",
        "relation_kind", "reason_code", "evidence_ids", "resolution_required", "covered",
        "snapshot_id",
    },
    "extractor_capability.v1": {
        "capability_id", "extractor_id", "extractor_version", "relation_kinds",
        "input_scope", "supported_file_kinds", "unsupported_behavior", "dynamic_behavior",
        "provenance_fields", "completeness_claim",
    },
}

SOURCE_SPAN_KEYS = {"path", "start_line", "start_column", "end_line", "end_column"}
ENVELOPE_KEYS = {"schema_version", "record_type", "record_id", "snapshot_id", "payload"}
HEADER_KEYS = {
    "schema_version", "snapshot_schema_version", "manifest_schema_version",
    "relation_schema_version", "snapshot_id", "source_fingerprint", "tool_version", "profile",
}
SNAPSHOT_KEYS = {
    "snapshot_id", "parent_repo_id", "root_realpath", "git_head", "git_index_tree",
    "git_worktree_dirty", "git_status_hash", "dirty_paths", "agentcanon_pin", "schema_version",
    "tool_version", "path_sort", "captured_before_hash", "captured_after_hash",
    "snapshot_consistent",
}
SUMMARY_KEYS = {
    "snapshot_id", "record_counts", "accepted_fact_count", "rejected_declaration_count",
    "rejected_observation_count", "ambiguity_count", "source_exclusion_count",
    "normalized_record_fingerprint",
}

PAYLOAD_STRING_FIELDS = {
    "identity_id", "logical_id", "repo_rel_path", "canonical_locator", "locator_kind",
    "path_role", "file_mode", "content_hash", "git_blob_or_gitlink", "submodule_commit",
    "snapshot_id", "declaration_id", "source_identity_id", "declared_direction",
    "declared_kind", "declared_target", "reason", "raw_line_hash", "attestation_key",
    "attestation_id", "attestation_key", "evidence_type", "evidence_id",
    "declaring_identity_id", "dependent_identity_id", "prerequisite_identity_id",
    "relation_kind", "rejection_reason", "fact_id", "from_identity_id", "to_identity_id",
    "target_identity_id",
    "semantic_direction", "pair_identity", "authority", "reconciliation_status",
    "source_snapshot_id", "extractor_id", "extractor_version", "capability_id",
    "from_locator", "to_locator", "payload_hash", "classification", "relation_id",
    "relation_type", "source_path", "target_path", "owner_class", "surface_mode",
    "status", "source_exclusion_id", "repo_rel_path", "reason_code", "rule_id", "scope",
    "ambiguity_id", "relation_kind", "extractor_id", "extractor_version", "input_scope",
    "unsupported_behavior", "dynamic_behavior", "completeness_claim",
}
PAYLOAD_BOOL_FIELDS = {
    "exists", "is_dirty", "accepted", "content_hash_equal", "covered", "resolution_required",
}
PAYLOAD_STRING_LIST_FIELDS = {
    "alternate_locators", "attestation_ids", "observation_ids", "source_content_hashes",
    "candidate_fact_ids", "candidate_targets", "evidence_ids", "relation_kinds",
    "supported_file_kinds", "provenance_fields",
}
FAMILY_ID_FIELDS = {
    "source_identity.v1": "identity_id",
    "dependency_declaration.v1": "declaration_id",
    "attestation.v1": "attestation_id",
    "normalized_relation.v1": "fact_id",
    "observed_evidence.v1": "observation_id",
    "surface_relation.v1": "relation_id",
    "source_exclusion.v1": "source_exclusion_id",
    "ambiguity_a.v1": "ambiguity_id",
    "extractor_capability.v1": "capability_id",
}
FAMILY_SNAPSHOT_FIELDS = {
    "source_identity.v1": "snapshot_id",
    "dependency_declaration.v1": "snapshot_id",
    "attestation.v1": "snapshot_id",
    "normalized_relation.v1": "source_snapshot_id",
    "observed_evidence.v1": "snapshot_id",
    "surface_relation.v1": "snapshot_id",
    "source_exclusion.v1": "snapshot_id",
    "ambiguity_a.v1": "snapshot_id",
}
HEX64_RECORD_TYPES = {
    "source_snapshot.v1",
    "source_identity.v1",
    "dependency_declaration.v1",
    "attestation.v1",
    "normalized_relation.v1",
    "surface_relation.v1",
    "source_exclusion.v1",
    "ambiguity_a.v1",
    "normalization_summary.v1",
}
SUMMARY_COUNT_KEYS = {
    "source_snapshot.v1",
    *PAYLOAD_KEYS,
    "matched_count",
    "declared_only_count",
    "observed_only_count",
    "accepted_direct_fact_count",
    "rejected_declaration_count",
    "rejected_observation_count",
    "excluded_count",
    "unresolved_count",
    "duplicate_evidence_count",
    "x_core_count",
}

JsonObject = dict[str, object]
JsonMapping = Mapping[str, object]


class RelationRegistryEntryV1(TypedDict):
    """One exact relation-registry conformance entry."""

    capability_id: str
    discriminator: str
    family: str
    layer: str
    raw_kind: str
    stored_kind: str


class RelationRegistryArtifactV1(TypedDict):
    """Canonical relation-registry conformance artifact."""

    entries: list[RelationRegistryEntryV1]
    registry_fingerprint: str
    registry_version: str


@dataclass(frozen=True)
class ValidatedRelationRegistryEntryV1:
    """One immutable semantic entry loaded from the caller-owned artifact."""

    capability_id: str
    discriminator: str
    family: str
    layer: str
    raw_kind: str
    stored_kind: str


@dataclass(frozen=True)
class ValidatedRelationRegistryV1:
    """Canonical caller-owned registry used as the sole semantic authority."""

    entries: tuple[ValidatedRelationRegistryEntryV1, ...]
    registry_fingerprint: str
    registry_version: str


class TransportInvalid(ValueError):
    """Raised when current Rust transport bytes or fields are invalid."""


@dataclass(frozen=True)
class NormalizedRecordSetV1:
    """Deeply immutable mirror of every current Rust NormalizedRecordSet field."""

    header: JsonMapping
    source_identities: tuple[JsonMapping, ...]
    declarations: tuple[JsonMapping, ...]
    attestations: tuple[JsonMapping, ...]
    relations: tuple[JsonMapping, ...]
    observations: tuple[JsonMapping, ...]
    surface_relations: tuple[JsonMapping, ...]
    source_exclusions: tuple[JsonMapping, ...]
    ambiguities: tuple[JsonMapping, ...]
    capabilities: tuple[JsonMapping, ...]
    source_universe: JsonMapping
    summary: JsonMapping


def _deep_freeze(value: object) -> object:
    if isinstance(value, dict):
        raw_value = cast(dict[object, object], value)
        frozen: dict[str, object] = {}
        for key, item in raw_value.items():
            if not isinstance(key, str):
                raise TransportInvalid("verified JSON object contains a non-string key")
            frozen[key] = _deep_freeze(item)
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in cast(list[object], value))
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TransportInvalid("verified JSON contains an unsupported runtime value")


def _freeze_mapping(value: JsonMapping) -> JsonMapping:
    frozen = _deep_freeze(value)
    if not isinstance(frozen, Mapping):
        raise TransportInvalid("verified JSON projection is not an object")
    return cast(JsonMapping, frozen)


def _strict_object(pairs: list[tuple[str, object]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise TransportInvalid(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise TransportInvalid(f"canonical JSON serialization failed: {error}") from error


def _hash_parts(parts: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_object(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TransportInvalid(f"{label} must be an object with string keys")
    raw_object = cast(dict[object, object], value)
    for key in raw_object:
        if not isinstance(key, str):
            raise TransportInvalid(f"{label} must be an object with string keys")
    return cast(JsonObject, raw_object)


def _exact_keys(value: object, expected: set[str], label: str) -> JsonObject:
    object_value = _json_object(value, label)
    if set(object_value) != expected:
        actual = sorted(object_value)
        raise TransportInvalid(f"{label} fields mismatch: expected {sorted(expected)}, actual {actual}")
    return object_value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TransportInvalid(f"{label} must be a string")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise TransportInvalid(f"{label} must be boolean")
    return value


def _strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise TransportInvalid(f"{label} must be an array of strings")
    raw_values = cast(list[object], value)
    if any(not isinstance(item, str) for item in raw_values):
        raise TransportInvalid(f"{label} must be an array of strings")
    return cast(list[str], raw_values)


def _nonnegative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TransportInvalid(f"{label} must be a non-negative integer")
    return value


def _hex64(value: object, label: str, *, allow_empty: bool = False) -> str:
    text = _string(value, label)
    if allow_empty and not text:
        return text
    if not HEX64.fullmatch(text):
        raise TransportInvalid(f"{label} must be lowercase 64-hex")
    return text


def _observation_id(value: object, label: str) -> str:
    text = _string(value, label)
    if not text.startswith("O-") or not HEX64.fullmatch(text[2:]):
        raise TransportInvalid(f"{label} must be O- followed by lowercase 64-hex")
    return text


def _evidence_id(value: object, label: str) -> str:
    text = _string(value, label)
    if HEX64.fullmatch(text):
        return text
    return _observation_id(text, label)


def _span(value: object, label: str) -> JsonObject:
    span = _exact_keys(value, SOURCE_SPAN_KEYS, label)
    _string(span["path"], f"{label}.path")
    for field in ("start_line", "start_column", "end_line", "end_column"):
        position = span[field]
        if not isinstance(position, int) or isinstance(position, bool) or position < 1:
            raise TransportInvalid(f"{label}.{field} must be a positive integer")
    return span


def _validate_payload(record_type: str, payload: object) -> JsonObject:
    payload = _exact_keys(payload, PAYLOAD_KEYS[record_type], f"{record_type} payload")
    for key, value in payload.items():
        if key == "source_span":
            _span(value, f"{record_type}.source_span")
        elif key in PAYLOAD_BOOL_FIELDS:
            _bool(value, f"{record_type}.{key}")
        elif key in PAYLOAD_STRING_LIST_FIELDS:
            _strings(value, f"{record_type}.{key}")
        elif key == "resolved_target_identity_id":
            if value is not None and not isinstance(value, str):
                raise TransportInvalid(f"{record_type}.{key} must be string or null")
        elif key in PAYLOAD_STRING_FIELDS:
            _string(value, f"{record_type}.{key}")
        else:
            raise TransportInvalid(f"{record_type}.{key} has no declared transport type")
    return payload


def _validate_header_payload(payload: object, expected_snapshot_id: str) -> JsonObject:
    payload = _exact_keys(payload, HEADER_KEYS, "normalized header payload")
    for field in HEADER_KEYS:
        _string(payload[field], f"normalized_header.{field}")
    if (
        payload["schema_version"] != NORMALIZED_RECORD_SET_VERSION
        or payload["snapshot_schema_version"] != SNAPSHOT_SCHEMA_VERSION
        or payload["manifest_schema_version"] != MANIFEST_SCHEMA_VERSION
        or payload["relation_schema_version"] != "relation.v1"
        or payload["snapshot_id"] != expected_snapshot_id
        or payload["tool_version"] != TOOL_VERSION
        or payload["profile"] != "parent"
    ):
        raise TransportInvalid("normalized header protocol mismatch")
    _hex64(payload["source_fingerprint"], "normalized_header.source_fingerprint")
    return payload


def _validate_snapshot_payload(payload: object, expected_snapshot_id: str) -> JsonObject:
    payload = _exact_keys(payload, SNAPSHOT_KEYS, "source snapshot payload")
    for field in (
        "snapshot_id", "parent_repo_id", "root_realpath", "git_head", "git_index_tree",
        "git_status_hash", "agentcanon_pin", "schema_version", "tool_version", "path_sort",
        "captured_before_hash", "captured_after_hash",
    ):
        _string(payload[field], f"source_snapshot.{field}")
    _strings(payload["dirty_paths"], "source_snapshot.dirty_paths")
    for field in ("git_worktree_dirty", "snapshot_consistent"):
        _bool(payload[field], f"source_snapshot.{field}")
    if payload["snapshot_id"] != expected_snapshot_id or payload["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise TransportInvalid("source snapshot schema or snapshot mismatch")
    if payload["tool_version"] != TOOL_VERSION or payload["path_sort"] != "utf8-bytewise":
        raise TransportInvalid("source snapshot tool or path-sort mismatch")
    dirty_paths = _strings(payload["dirty_paths"], "source_snapshot.dirty_paths")
    if dirty_paths != sorted(set(dirty_paths)):
        raise TransportInvalid("source snapshot dirty paths are not unique and sorted")
    if not _bool(payload["snapshot_consistent"], "source_snapshot.snapshot_consistent"):
        raise TransportInvalid("source snapshot is inconsistent")
    for field in ("parent_repo_id", "git_status_hash", "captured_before_hash", "captured_after_hash"):
        _hex64(payload[field], f"source_snapshot.{field}")
    for field in ("git_head", "git_index_tree", "agentcanon_pin"):
        value = _string(payload[field], f"source_snapshot.{field}")
        if not HEX40.fullmatch(value):
            raise TransportInvalid(f"source snapshot {field} is not lowercase 40-hex")
    return payload


def _validate_summary_payload(payload: object, expected_snapshot_id: str) -> JsonObject:
    payload = _exact_keys(payload, SUMMARY_KEYS, "normalization summary payload")
    if _string(payload["snapshot_id"], "normalization_summary.snapshot_id") != expected_snapshot_id:
        raise TransportInvalid("normalization summary snapshot mismatch")
    counts = _json_object(payload["record_counts"], "normalization_summary.record_counts")
    if set(counts) != SUMMARY_COUNT_KEYS:
        raise TransportInvalid("normalization summary record-count keys mismatch")
    for key, count in counts.items():
        _nonnegative_int(count, f"normalization_summary.record_counts.{key}")
    for field in (
        "accepted_fact_count", "rejected_declaration_count", "rejected_observation_count",
        "ambiguity_count", "source_exclusion_count",
    ):
        _nonnegative_int(payload[field], f"normalization_summary.{field}")
    _hex64(
        payload["normalized_record_fingerprint"],
        "normalization_summary.normalized_record_fingerprint",
    )
    return payload


def _parse_line(raw_line: bytes, line_number: int) -> JsonObject:
    if not raw_line.endswith(b"\n") or raw_line.endswith(b"\r\n"):
        raise TransportInvalid(f"line {line_number} is not one canonical LF-terminated record")
    if raw_line == b"\n":
        raise TransportInvalid(f"blank normalized JSONL line {line_number}")
    try:
        text = raw_line[:-1].decode("utf-8")
    except UnicodeDecodeError as error:
        raise TransportInvalid(f"line {line_number} is not UTF-8: {error}") from error
    if line_number == 1 and text.startswith("\ufeff"):
        raise TransportInvalid("normalized JSONL must not contain a UTF-8 BOM")
    try:
        value = cast(object, json.loads(text, object_pairs_hook=_strict_object))
    except (json.JSONDecodeError, TransportInvalid) as error:
        raise TransportInvalid(f"normalized line {line_number}: {error}") from error
    if _canonical_bytes(value) != raw_line[:-1]:
        raise TransportInvalid(f"normalized line {line_number} is not canonical Rust JSON")
    return _exact_keys(value, ENVELOPE_KEYS, f"line {line_number} envelope")


def _validate_record_id(record_type: str, record_id: str) -> None:
    if record_type == "observed_evidence.v1":
        _observation_id(record_id, f"{record_type}.record_id")
    elif record_type == "extractor_capability.v1":
        if not record_id:
            raise TransportInvalid("extractor_capability.v1.record_id must not be empty")
    elif record_type in HEX64_RECORD_TYPES:
        _hex64(record_id, f"{record_type}.record_id")


def _validate_payload_linkage(
    record_type: str,
    payload: JsonMapping,
    expected_snapshot_id: str,
) -> None:
    snapshot_field = FAMILY_SNAPSHOT_FIELDS.get(record_type)
    if snapshot_field is not None and _string(
        payload[snapshot_field], f"{record_type}.{snapshot_field}"
    ) != expected_snapshot_id:
        raise TransportInvalid(f"{record_type} snapshot mismatch")

    id_field = FAMILY_ID_FIELDS[record_type]
    record_id = _string(payload[id_field], f"{record_type}.{id_field}")
    _validate_record_id(record_type, record_id)

    hex_fields = {
        "source_identity.v1": ("logical_id",),
        "dependency_declaration.v1": (
            "source_identity_id", "raw_line_hash", "attestation_key",
        ),
        "attestation.v1": (
            "attestation_key", "declaring_identity_id", "raw_line_hash",
        ),
        "normalized_relation.v1": (
            "from_identity_id", "to_identity_id", "pair_identity",
        ),
        "observed_evidence.v1": (
            "from_identity_id", "to_identity_id", "payload_hash",
        ),
        "surface_relation.v1": ("source_identity_id", "target_identity_id"),
        "source_exclusion.v1": ("source_identity_id",),
        "ambiguity_a.v1": ("source_identity_id",),
        "extractor_capability.v1": (),
    }[record_type]
    for field in hex_fields:
        _hex64(
            payload[field],
            f"{record_type}.{field}",
            allow_empty=record_type == "ambiguity_a.v1" and field == "source_identity_id",
        )

    optional_hex_fields = {
        "dependency_declaration.v1": ("resolved_target_identity_id",),
        "attestation.v1": ("dependent_identity_id", "prerequisite_identity_id"),
    }.get(record_type, ())
    for field in optional_hex_fields:
        value = payload[field]
        if value is not None:
            _hex64(value, f"{record_type}.{field}", allow_empty=True)

    for field in {
        "normalized_relation.v1": ("attestation_ids",),
        "ambiguity_a.v1": ("candidate_fact_ids",),
    }.get(record_type, ()):
        for index, value in enumerate(_strings(payload[field], f"{record_type}.{field}")):
            _hex64(value, f"{record_type}.{field}[{index}]")

    if record_type == "normalized_relation.v1":
        for index, value in enumerate(
            _strings(payload["observation_ids"], "normalized_relation.v1.observation_ids")
        ):
            _observation_id(value, f"normalized_relation.v1.observation_ids[{index}]")
    elif record_type == "ambiguity_a.v1":
        for index, value in enumerate(
            _strings(payload["evidence_ids"], "ambiguity_a.v1.evidence_ids")
        ):
            _evidence_id(value, f"ambiguity_a.v1.evidence_ids[{index}]")
    elif record_type == "attestation.v1":
        evidence_type = _string(payload["evidence_type"], "attestation.v1.evidence_type")
        evidence_id = payload["evidence_id"]
        if evidence_type == "declaration":
            _hex64(evidence_id, "attestation.v1.evidence_id")
        elif evidence_type == "observation":
            _observation_id(evidence_id, "attestation.v1.evidence_id")
        else:
            raise TransportInvalid("attestation.v1.evidence_type is invalid")


def _validated_registry_entry_value(
    entry: ValidatedRelationRegistryEntryV1,
) -> RelationRegistryEntryV1:
    return {
        "capability_id": entry.capability_id,
        "discriminator": entry.discriminator,
        "family": entry.family,
        "layer": entry.layer,
        "raw_kind": entry.raw_kind,
        "stored_kind": entry.stored_kind,
    }


def _validated_registry_sort_key(
    entry: ValidatedRelationRegistryEntryV1,
) -> tuple[str, str, str, str, str, str]:
    return (
        entry.capability_id,
        entry.raw_kind,
        entry.discriminator,
        entry.stored_kind,
        entry.layer,
        entry.family,
    )


def load_relation_registry_artifact(path: Path) -> ValidatedRelationRegistryV1:
    """Load one canonical caller-owned relation_registry.v1 authority artifact."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise TransportInvalid(f"relation registry artifact: {error}") from error
    if (
        not raw.endswith(b"\n")
        or raw.endswith(b"\r\n")
        or raw.endswith(b"\n\n")
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        raise TransportInvalid("relation registry artifact byte contract mismatch")
    try:
        value = cast(
            object,
            json.loads(
                raw[:-1].decode("utf-8"),
                object_pairs_hook=_strict_object,
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TransportInvalid) as error:
        raise TransportInvalid(f"relation registry artifact JSON: {error}") from error
    if _canonical_bytes(value) + b"\n" != raw:
        raise TransportInvalid("relation registry artifact is not canonical JSON")
    artifact = _exact_keys(
        value,
        {"entries", "registry_fingerprint", "registry_version"},
        "relation registry artifact",
    )
    version = _string(artifact["registry_version"], "registry_version")
    if version != REGISTRY_VERSION:
        raise TransportInvalid(f"unsupported relation registry version {version}")
    raw_entries = artifact["entries"]
    if not isinstance(raw_entries, list):
        raise TransportInvalid("relation registry entries must be an array")
    entries: list[ValidatedRelationRegistryEntryV1] = []
    semantic_keys: set[tuple[str, str, str]] = set()
    for index, value_entry in enumerate(cast(list[object], raw_entries)):
        entry = _exact_keys(
            value_entry,
            {"capability_id", "discriminator", "family", "layer", "raw_kind", "stored_kind"},
            f"relation registry entry {index}",
        )
        validated = ValidatedRelationRegistryEntryV1(
            capability_id=_string(entry["capability_id"], f"entry {index}.capability_id"),
            discriminator=_string(entry["discriminator"], f"entry {index}.discriminator"),
            family=_string(entry["family"], f"entry {index}.family"),
            layer=_string(entry["layer"], f"entry {index}.layer"),
            raw_kind=_string(entry["raw_kind"], f"entry {index}.raw_kind"),
            stored_kind=_string(entry["stored_kind"], f"entry {index}.stored_kind"),
        )
        if not all(
            (
                validated.capability_id,
                validated.family,
                validated.layer,
                validated.raw_kind,
                validated.stored_kind,
            )
        ):
            raise TransportInvalid("relation registry entry has an empty required field")
        semantic_key = (
            validated.capability_id,
            validated.raw_kind,
            validated.discriminator,
        )
        if semantic_key in semantic_keys:
            raise TransportInvalid("relation registry has a duplicate semantic key")
        semantic_keys.add(semantic_key)
        entries.append(validated)
    if not entries or entries != sorted(entries, key=_validated_registry_sort_key):
        raise TransportInvalid("relation registry entries are empty or not canonical")
    fingerprint = _hex64(
        artifact["registry_fingerprint"],
        "relation registry fingerprint",
    )
    computed = _sha256_bytes(
        _canonical_bytes(
            {
                "entries": [_validated_registry_entry_value(entry) for entry in entries],
                "registry_version": version,
            }
        )
    )
    if fingerprint != computed:
        raise TransportInvalid("relation registry fingerprint mismatch")
    return ValidatedRelationRegistryV1(
        entries=tuple(entries),
        registry_fingerprint=fingerprint,
        registry_version=version,
    )


def _source_universe(
    identities: tuple[JsonMapping, ...],
    exclusions: tuple[JsonMapping, ...],
) -> JsonObject:
    candidate = sorted(
        _string(identity["repo_rel_path"], "source_identity.repo_rel_path")
        for identity in identities
    )
    excluded = sorted(
        _string(exclusion["repo_rel_path"], "source_exclusion.repo_rel_path")
        for exclusion in exclusions
    )
    if len(set(candidate)) != len(candidate) or len(set(excluded)) != len(excluded):
        raise TransportInvalid("source universe contains duplicate paths")
    eligible = sorted(set(candidate) - set(excluded))
    candidate_set = set(candidate)
    if set(excluded) - candidate_set:
        raise TransportInvalid("source exclusion is outside candidate source set")
    return {
        "candidate_paths": candidate,
        "excluded_paths": excluded,
        "eligible_paths": eligible,
        "eligible_equals_candidate_minus_excluded": eligible == sorted(candidate_set - set(excluded)),
        "union_equals_candidate": sorted(set(eligible) | set(excluded)) == candidate,
        "intersection_empty": set(eligible).isdisjoint(excluded),
    }


def _normalized_fingerprint(values: list[JsonObject]) -> str:
    body = [
        {
            "record_type": value["record_type"],
            "record_id": value["record_id"],
            "payload": value["payload"],
        }
        for value in values
        if value["record_type"] not in {"normalized_record_set_header.v1", "normalization_summary.v1"}
    ]
    raw = b"".join(_canonical_bytes(value) + b"\0" for value in body)
    return _sha256_bytes(raw)


def _validate_source_fingerprint(
    header: JsonMapping,
    identities: tuple[JsonMapping, ...],
    surface_relations: tuple[JsonMapping, ...],
) -> None:
    parts = [
        "source_fingerprint.v1",
        _string(header["git_head"], "normalized_header.git_head"),
        str(_bool(header["git_worktree_dirty"], "normalized_header.git_worktree_dirty")).lower(),
        _string(header["git_status_hash"], "normalized_header.git_status_hash"),
        _string(header["agentcanon_pin"], "normalized_header.agentcanon_pin"),
        _string(header["schema_version"], "normalized_header.schema_version"),
        _string(header["tool_version"], "normalized_header.tool_version"),
        _string(header["profile"], "normalized_header.profile"),
    ]
    classification: dict[str, tuple[str, str]] = {}
    for relation in surface_relations:
        source_identity_id = _string(
            relation["source_identity_id"], "surface_relation.source_identity_id"
        )
        current = (
            _string(relation["owner_class"], "surface_relation.owner_class"),
            _string(relation["surface_mode"], "surface_relation.surface_mode"),
        )
        previous = classification.setdefault(source_identity_id, current)
        if previous != current:
            raise TransportInvalid("surface relation classification conflict")
    for identity in sorted(
        identities,
        key=lambda item: _string(item["repo_rel_path"], "source_identity.repo_rel_path"),
    ):
        identity_id = _string(identity["identity_id"], "source_identity.identity_id")
        owner_class, surface_mode = classification.get(
            identity_id, ("unresolved", "regular")
        )
        parts.extend(
            [
                _string(identity["repo_rel_path"], "source_identity.repo_rel_path"),
                _string(identity["file_mode"], "source_identity.file_mode"),
                str(_bool(identity["exists"], "source_identity.exists")).lower(),
                _string(identity["content_hash"], "source_identity.content_hash"),
                _string(
                    identity["git_blob_or_gitlink"], "source_identity.git_blob_or_gitlink"
                ),
                _string(identity["submodule_commit"], "source_identity.submodule_commit"),
                _string(identity["path_role"], "source_identity.path_role"),
                owner_class,
                surface_mode,
            ]
        )
    expected = _hash_parts(parts)
    if _string(header["source_fingerprint"], "normalized_header.source_fingerprint") != expected:
        raise TransportInvalid("source fingerprint mismatch")


def _registry_conversion(
    registry: ValidatedRelationRegistryV1,
    capability_id: str,
    raw_kind: str,
    discriminator: str,
) -> ValidatedRelationRegistryEntryV1 | None:
    matches = [
        entry
        for entry in registry.entries
        if entry.capability_id == capability_id
        and entry.raw_kind == raw_kind
        and entry.discriminator == discriminator
    ]
    if len(matches) > 1:
        raise TransportInvalid("relation registry semantic key is ambiguous")
    return matches[0] if matches else None


def _registry_capability_rows(
    registry: ValidatedRelationRegistryV1,
) -> dict[str, tuple[str, list[str]]]:
    raw_kinds: dict[str, set[str]] = {}
    for entry in registry.entries:
        raw_kinds.setdefault(entry.capability_id, set()).add(entry.raw_kind)
    return {
        capability_id: (
            capability_id.removesuffix(".v1"),
            sorted(kinds),
        )
        for capability_id, kinds in raw_kinds.items()
    }


def _identity_matches_locator(identity: JsonMapping, locator: str) -> bool:
    return locator in {
        _string(identity["repo_rel_path"], "source_identity.repo_rel_path"),
        _string(identity["canonical_locator"], "source_identity.canonical_locator"),
        *_strings(identity["alternate_locators"], "source_identity.alternate_locators"),
    }


def _content_identity_is_canonical(identity: JsonMapping, value: str) -> bool:
    mode = _string(identity["file_mode"], "source_identity.file_mode")
    if mode == "160000":
        return bool(HEX40.fullmatch(value)) and value == _string(
            identity["git_blob_or_gitlink"],
            "source_identity.git_blob_or_gitlink",
        )
    return mode in {"100644", "100755", "120000"} and bool(HEX64.fullmatch(value))


def _declaration_endpoints(
    declaration: JsonMapping,
    identities: Mapping[str, JsonMapping],
    excluded: set[str],
) -> tuple[str | None, str | None, str | None]:
    source_id = _string(
        declaration["source_identity_id"],
        "dependency_declaration.source_identity_id",
    )
    raw_target_id = declaration["resolved_target_identity_id"]
    target_id = None if raw_target_id is None else _string(
        raw_target_id,
        "dependency_declaration.resolved_target_identity_id",
    )
    source = identities.get(source_id)
    target = identities.get(target_id) if target_id is not None else None
    if source is None:
        reason = "unresolved_source"
    elif source_id in excluded:
        reason = "source_excluded_source"
    elif not _bool(source["exists"], "source_identity.exists"):
        reason = "stale_source"
    elif target_id is None:
        reason = "missing_target"
    elif target is None:
        reason = "unresolved_target"
    elif target_id in excluded:
        reason = "source_excluded_target"
    elif not _bool(target["exists"], "source_identity.exists"):
        reason = "stale_target"
    else:
        reason = None
    direction = _string(
        declaration["declared_direction"],
        "dependency_declaration.declared_direction",
    )
    if direction == "upstream":
        return source_id, target_id, reason
    if direction == "downstream":
        return target_id, source_id, reason
    return source_id, target_id, "invalid_direction"


def _observation_endpoints(
    observation: JsonMapping,
    identities: Mapping[str, JsonMapping],
    excluded: set[str],
) -> tuple[str, str, str | None]:
    from_id = _string(observation["from_identity_id"], "observed_evidence.from_identity_id")
    to_id = _string(observation["to_identity_id"], "observed_evidence.to_identity_id")
    from_identity = identities.get(from_id)
    to_identity = identities.get(to_id)
    if from_identity is None or to_identity is None:
        reason = "unresolved_observation"
    elif not (
        _identity_matches_locator(
            from_identity,
            _string(observation["from_locator"], "observed_evidence.from_locator"),
        )
        and _identity_matches_locator(
            to_identity,
            _string(observation["to_locator"], "observed_evidence.to_locator"),
        )
        and _identity_matches_locator(
            from_identity,
            _string(
                _span(observation["source_span"], "observed_evidence.source_span")["path"],
                "observed_evidence.source_span.path",
            ),
        )
    ):
        reason = "provenance_incomplete"
    elif from_id in excluded:
        reason = "source_excluded_source"
    elif to_id in excluded:
        reason = "source_excluded_target"
    elif not _bool(from_identity["exists"], "source_identity.exists") or not _bool(
        to_identity["exists"], "source_identity.exists"
    ):
        reason = "stale_target"
    else:
        reason = None
    return from_id, to_id, reason


def _validate_snapshot_derivations(
    header: JsonMapping,
    identities: tuple[JsonMapping, ...],
    declarations: tuple[JsonMapping, ...],
    surface_relations: tuple[JsonMapping, ...],
    exclusions: tuple[JsonMapping, ...],
) -> tuple[dict[str, JsonMapping], set[str], dict[str, str]]:
    expected_capture_hash = _hash_parts(
        [
            _string(header["git_head"], "source_snapshot.git_head"),
            _string(header["git_index_tree"], "source_snapshot.git_index_tree"),
            _string(header["git_status_hash"], "source_snapshot.git_status_hash"),
            _string(header["agentcanon_pin"], "source_snapshot.agentcanon_pin"),
            _string(header["schema_version"], "source_snapshot.schema_version"),
            _string(header["tool_version"], "source_snapshot.tool_version"),
            _string(header["profile"], "source_snapshot.profile"),
        ]
    )
    if (
        _string(header["captured_before_hash"], "source_snapshot.captured_before_hash")
        != expected_capture_hash
        or _string(header["captured_after_hash"], "source_snapshot.captured_after_hash")
        != expected_capture_hash
    ):
        raise TransportInvalid("source snapshot capture hash mismatch")
    parent_repo_id = _string(header["parent_repo_id"], "source_snapshot.parent_repo_id")
    snapshot_id = _string(header["snapshot_id"], "source_snapshot.snapshot_id")
    identity_ids: set[str] = set()
    repo_paths: set[str] = set()
    canonical_locators: set[str] = set()
    logical_ids: set[str] = set()
    for identity in identities:
        identity_id = _string(identity["identity_id"], "source_identity.identity_id")
        path = _string(identity["repo_rel_path"], "source_identity.repo_rel_path")
        locator = _string(identity["canonical_locator"], "source_identity.canonical_locator")
        logical_id = _string(identity["logical_id"], "source_identity.logical_id")
        if identity_id in identity_ids or path in repo_paths:
            raise TransportInvalid("source identities contain a duplicate ID or path")
        if locator in canonical_locators:
            raise TransportInvalid("duplicate source identity canonical locator")
        if logical_id in logical_ids:
            raise TransportInvalid("duplicate source identity logical ID")
        if identity_id != _hash_parts(["source_identity.v1", parent_repo_id, path]):
            raise TransportInvalid("source identity ID derivation mismatch")
        if logical_id != _hash_parts(["logical_source.v1", parent_repo_id, locator]):
            raise TransportInvalid("logical source ID derivation mismatch")
        if _string(identity["snapshot_id"], "source_identity.snapshot_id") != snapshot_id:
            raise TransportInvalid("source identity snapshot mismatch")
        content_hash = _string(identity["content_hash"], "source_identity.content_hash")
        if not _content_identity_is_canonical(identity, content_hash):
            raise TransportInvalid("source content identity is not canonical")
        alternates = _strings(identity["alternate_locators"], "source_identity.alternate_locators")
        if alternates != sorted(set(alternates)):
            raise TransportInvalid("source alternate locators are not sorted and unique")
        identity_ids.add(identity_id)
        repo_paths.add(path)
        canonical_locators.add(locator)
        logical_ids.add(logical_id)

    locator_owners: dict[str, str] = {}
    for identity in identities:
        identity_id = _string(identity["identity_id"], "source_identity.identity_id")
        locators = (
            _string(identity["repo_rel_path"], "source_identity.repo_rel_path"),
            _string(identity["canonical_locator"], "source_identity.canonical_locator"),
            *_strings(
                identity["alternate_locators"],
                "source_identity.alternate_locators",
            ),
        )
        for locator in locators:
            owner = locator_owners.get(locator)
            if owner is not None and owner != identity_id:
                raise TransportInvalid(
                    f"source identity locator namespace collision for {locator}"
                )
            locator_owners[locator] = identity_id

    identities_by_id: dict[str, JsonMapping] = {}
    identities_by_locator: dict[str, JsonMapping] = {}
    logical_by_id: dict[str, str] = {}
    for identity in identities:
        identity_id = _string(identity["identity_id"], "source_identity.identity_id")
        identities_by_id[identity_id] = identity
        logical_by_id[identity_id] = _string(
            identity["logical_id"], "source_identity.logical_id"
        )
        for locator in (
            _string(identity["repo_rel_path"], "source_identity.repo_rel_path"),
            _string(identity["canonical_locator"], "source_identity.canonical_locator"),
            *_strings(
                identity["alternate_locators"],
                "source_identity.alternate_locators",
            ),
        ):
            identities_by_locator[locator] = identity

    classifications: dict[str, tuple[str, str]] = {}
    for relation in surface_relations:
        relation_id = _string(relation["relation_id"], "surface_relation.relation_id")
        source_id = _string(
            relation["source_identity_id"], "surface_relation.source_identity_id"
        )
        source_path = _string(relation["source_path"], "surface_relation.source_path")
        target_path = _string(relation["target_path"], "surface_relation.target_path")
        relation_type = _string(relation["relation_type"], "surface_relation.relation_type")
        source_identity = identities_by_id.get(source_id)
        if source_identity is None or _string(
            source_identity["repo_rel_path"], "source_identity.repo_rel_path"
        ) != source_path:
            raise TransportInvalid("surface relation source identity/path mismatch")
        target_identity = identities_by_locator.get(target_path)
        expected_target_id = (
            _string(target_identity["identity_id"], "source_identity.identity_id")
            if target_identity is not None
            else _hash_parts(["source_identity.v1", parent_repo_id, target_path])
        )
        target_id = _string(
            relation["target_identity_id"], "surface_relation.target_identity_id"
        )
        expected_relation_id = _hash_parts(
            ["surface_relation.v1", source_id, target_id, relation_type]
        )
        if (
            target_id != expected_target_id
            or relation_id != expected_relation_id
            or _string(relation["evidence_id"], "surface_relation.evidence_id") != relation_id
            or _string(relation["snapshot_id"], "surface_relation.snapshot_id") != snapshot_id
        ):
            raise TransportInvalid("surface relation ID/provenance mismatch")
        classification = (
            _string(relation["owner_class"], "surface_relation.owner_class"),
            _string(relation["surface_mode"], "surface_relation.surface_mode"),
        )
        previous = classifications.setdefault(source_id, classification)
        if previous != classification or not all(classification):
            raise TransportInvalid("surface relation classification conflict")

    excluded_ids: set[str] = set()
    excluded_paths: set[str] = set()
    for exclusion in exclusions:
        exclusion_id = _string(
            exclusion["source_exclusion_id"], "source_exclusion.source_exclusion_id"
        )
        source_id = _string(
            exclusion["source_identity_id"], "source_exclusion.source_identity_id"
        )
        path = _string(exclusion["repo_rel_path"], "source_exclusion.repo_rel_path")
        reason = _string(exclusion["reason_code"], "source_exclusion.reason_code")
        scope = _string(exclusion["scope"], "source_exclusion.scope")
        identity = identities_by_id.get(source_id)
        if (
            identity is None
            or _string(identity["repo_rel_path"], "source_identity.repo_rel_path") != path
            or exclusion_id != _hash_parts(["source_exclusion.v1", source_id, reason, scope])
            or _string(exclusion["evidence_id"], "source_exclusion.evidence_id") != source_id
            or _string(exclusion["snapshot_id"], "source_exclusion.snapshot_id") != snapshot_id
            or _bool(exclusion["covered"], "source_exclusion.covered")
            or not _string(exclusion["rule_id"], "source_exclusion.rule_id")
        ):
            raise TransportInvalid("source exclusion identity/provenance mismatch")
        if source_id in excluded_ids or path in excluded_paths:
            raise TransportInvalid("source exclusion partition contains duplicates")
        excluded_ids.add(source_id)
        excluded_paths.add(path)

    for declaration in declarations:
        source_id = _string(
            declaration["source_identity_id"], "dependency_declaration.source_identity_id"
        )
        span = _span(declaration["source_span"], "dependency_declaration.source_span")
        span_path = _string(span["path"], "dependency_declaration.source_span.path")
        source_identity = identities_by_id.get(source_id)
        if source_identity is None:
            if source_id != _hash_parts(
                ["source_identity.v1", parent_repo_id, span_path]
            ):
                raise TransportInvalid(
                    "dependency declaration source identity/path mismatch"
                )
        elif _string(
            source_identity["repo_rel_path"], "source_identity.repo_rel_path"
        ) != span_path:
            raise TransportInvalid("dependency declaration source identity/path mismatch")
        target = declaration["resolved_target_identity_id"]
        if target is not None and _string(
            target, "dependency_declaration.resolved_target_identity_id"
        ) not in identities_by_id:
            raise TransportInvalid("dependency declaration target identity is unknown")
        direction = _string(
            declaration["declared_direction"], "dependency_declaration.declared_direction"
        )
        kind = _string(declaration["declared_kind"], "dependency_declaration.declared_kind")
        if direction not in {"upstream", "downstream"} or kind not in {
            "design", "implementation", "environment"
        }:
            raise TransportInvalid("dependency declaration direction/kind is invalid")
        start_line = str(_nonnegative_int(span["start_line"], "source_span.start_line"))
        end_line = str(_nonnegative_int(span["end_line"], "source_span.end_line"))
        target_text = _string(
            declaration["declared_target"], "dependency_declaration.declared_target"
        )
        raw_hash = _hex64(
            declaration["raw_line_hash"], "dependency_declaration.raw_line_hash"
        )
        expected_declaration_id = _hash_parts(
            [
                "dependency_declaration.v1", source_id, start_line, end_line,
                direction, kind, target_text, raw_hash,
            ]
        )
        expected_attestation_key = _hash_parts(
            [
                "dependency_attestation.v1", snapshot_id, source_id, start_line,
                end_line, direction, kind, target_text, raw_hash,
            ]
        )
        if (
            _string(declaration["declaration_id"], "dependency_declaration.declaration_id")
            != expected_declaration_id
            or _string(declaration["attestation_key"], "dependency_declaration.attestation_key")
            != expected_attestation_key
        ):
            raise TransportInvalid("dependency declaration ID derivation mismatch")

    _validate_source_fingerprint(header, identities, surface_relations)
    expected_snapshot_id = _hash_parts(
        [
            "source_snapshot.v1",
            parent_repo_id,
            _string(header["source_fingerprint"], "source_snapshot.source_fingerprint"),
            _string(header["schema_version"], "source_snapshot.schema_version"),
            _string(header["tool_version"], "source_snapshot.tool_version"),
            _string(header["profile"], "source_snapshot.profile"),
        ]
    )
    if snapshot_id != expected_snapshot_id:
        raise TransportInvalid("source snapshot ID derivation mismatch")
    return identities_by_id, excluded_ids, logical_by_id


def _capability_rejection_reason(
    registry: ValidatedRelationRegistryV1,
    capability: JsonMapping | None,
    observation: JsonMapping,
) -> str | None:
    if capability is None:
        return "capability_unknown"
    expected = _registry_capability_rows(registry).get(
        _string(capability["capability_id"], "extractor_capability.capability_id")
    )
    if expected is None:
        return "capability_unknown"
    expected_extractor, expected_raw_kinds = expected
    status = " ".join(
        [
            _string(capability["input_scope"], "extractor_capability.input_scope").lower(),
            _string(
                capability["completeness_claim"],
                "extractor_capability.completeness_claim",
            ).lower(),
        ]
    )
    if (
        not _string(capability["input_scope"], "extractor_capability.input_scope").startswith(
            "connected:"
        )
        or "connected" not in _string(
            capability["completeness_claim"],
            "extractor_capability.completeness_claim",
        )
        or any(
            marker in status
            for marker in ("unavailable", "provided-empty", "o=empty", "coverage=0")
        )
    ):
        return "capability_unavailable"
    if (
        _string(capability["extractor_id"], "extractor_capability.extractor_id")
        != expected_extractor
        or _string(capability["extractor_id"], "extractor_capability.extractor_id")
        != _string(observation["extractor_id"], "observed_evidence.extractor_id")
        or _string(capability["extractor_version"], "extractor_capability.extractor_version")
        != _string(observation["extractor_version"], "observed_evidence.extractor_version")
        or _string(capability["extractor_version"], "extractor_capability.extractor_version")
        in {"", "unavailable"}
        or _strings(capability["relation_kinds"], "extractor_capability.relation_kinds")
        != expected_raw_kinds
        or set(
            _strings(
                capability["provenance_fields"],
                "extractor_capability.provenance_fields",
            )
        )
        != {"payload_hash", "snapshot_id", "source_span"}
    ):
        return "provenance_incomplete"
    return None


def _rows_by(
    rows: tuple[JsonMapping, ...],
    field: str,
    label: str,
) -> dict[str, JsonMapping]:
    indexed: dict[str, JsonMapping] = {}
    for row in rows:
        key = _string(row[field], f"{label}.{field}")
        if key in indexed:
            raise TransportInvalid(f"duplicate {label} {field}")
        indexed[key] = row
    return indexed


def _validate_normalized_semantics(
    header: JsonMapping,
    identities: tuple[JsonMapping, ...],
    declarations: tuple[JsonMapping, ...],
    attestations: tuple[JsonMapping, ...],
    relations: tuple[JsonMapping, ...],
    observations: tuple[JsonMapping, ...],
    surface_relations: tuple[JsonMapping, ...],
    exclusions: tuple[JsonMapping, ...],
    ambiguities: tuple[JsonMapping, ...],
    capabilities: tuple[JsonMapping, ...],
    source_universe: JsonMapping,
    registry: ValidatedRelationRegistryV1,
) -> None:
    identities_by_id, excluded_ids, logical_by_id = _validate_snapshot_derivations(
        header,
        identities,
        declarations,
        surface_relations,
        exclusions,
    )
    snapshot_id = _string(header["snapshot_id"], "source_snapshot.snapshot_id")
    parent_repo_id = _string(header["parent_repo_id"], "source_snapshot.parent_repo_id")
    if (
        _strings(source_universe["candidate_paths"], "source_universe.candidate_paths")
        != sorted(
            _string(identity["repo_rel_path"], "source_identity.repo_rel_path")
            for identity in identities
        )
        or not all(
            _bool(source_universe[field], f"source_universe.{field}")
            for field in (
                "eligible_equals_candidate_minus_excluded",
                "union_equals_candidate",
                "intersection_empty",
            )
        )
    ):
        raise TransportInvalid("normalized source universe algebra mismatch")

    declarations_by_id = _rows_by(
        declarations, "declaration_id", "dependency declaration"
    )
    observations_by_id = _rows_by(observations, "observation_id", "observation")
    capabilities_by_id = _rows_by(capabilities, "capability_id", "capability")
    ambiguities_by_id = _rows_by(ambiguities, "ambiguity_id", "ambiguity")
    registry_capabilities = _registry_capability_rows(registry)
    registered_capability_ids = set(registry_capabilities)
    if not registered_capability_ids.issubset(capabilities_by_id):
        raise TransportInvalid("registered capability transport is incomplete")
    for capability_id, capability in capabilities_by_id.items():
        required_strings = (
            "extractor_id", "extractor_version", "input_scope", "unsupported_behavior",
            "dynamic_behavior", "completeness_claim",
        )
        if any(not _string(capability[field], f"extractor_capability.{field}") for field in required_strings):
            raise TransportInvalid("extractor capability provenance is incomplete")
        relation_kinds = _strings(
            capability["relation_kinds"], "extractor_capability.relation_kinds"
        )
        provenance_fields = _strings(
            capability["provenance_fields"], "extractor_capability.provenance_fields"
        )
        if (
            not relation_kinds
            or relation_kinds != sorted(set(relation_kinds))
            or not provenance_fields
            or provenance_fields != sorted(set(provenance_fields))
        ):
            raise TransportInvalid("extractor capability lists are not sorted and unique")
        known = registry_capabilities.get(capability_id)
        if known is not None:
            expected_extractor, expected_raw_kinds = known
            if (
                _string(capability["extractor_id"], "extractor_capability.extractor_id")
                != expected_extractor
                or relation_kinds != expected_raw_kinds
            ):
                raise TransportInvalid("extractor capability disagrees with relation registry")
        elif (
            "unavailable"
            not in _string(capability["input_scope"], "extractor_capability.input_scope")
            or "unavailable"
            not in _string(
                capability["completeness_claim"],
                "extractor_capability.completeness_claim",
            )
            or not any(
                _string(ambiguity["reason_code"], "ambiguity.reason_code")
                == "capability_unknown"
                and capability_id
                in _strings(ambiguity["evidence_ids"], "ambiguity.evidence_ids")
                for ambiguity in ambiguities
            )
        ):
            raise TransportInvalid("unknown capability is not retained as unavailable ambiguity")
    if not observations:
        for capability_id in registered_capability_ids:
            capability = capabilities_by_id[capability_id]
            completeness = _string(
                capability["completeness_claim"],
                "extractor_capability.completeness_claim",
            )
            input_scope = _string(
                capability["input_scope"], "extractor_capability.input_scope"
            )
            if (
                "O=empty" not in completeness
                or "coverage=0" not in completeness
                or ("unavailable" not in input_scope and "provided-empty" not in completeness)
            ):
                raise TransportInvalid("empty observations require explicit empty capability status")

    attestations_by_id: dict[str, JsonMapping] = {}
    attestations_by_evidence: dict[tuple[str, str], JsonMapping] = {}
    for attestation in attestations:
        attestation_id = _string(attestation["attestation_id"], "attestation.attestation_id")
        attestation_key = _hex64(attestation["attestation_key"], "attestation.attestation_key")
        evidence_type = _string(attestation["evidence_type"], "attestation.evidence_type")
        evidence_id = _string(attestation["evidence_id"], "attestation.evidence_id")
        rejection_reason = _string(
            attestation["rejection_reason"], "attestation.rejection_reason"
        )
        accepted = _bool(attestation["accepted"], "attestation.accepted")
        if (
            evidence_type not in {"declaration", "observation"}
            or not evidence_id
            or not _string(
                attestation["declaring_identity_id"], "attestation.declaring_identity_id"
            )
            or not _string(attestation["declared_direction"], "attestation.declared_direction")
            or not _string(attestation["relation_kind"], "attestation.relation_kind")
            or not _string(attestation["reason"], "attestation.reason")
            or not _string(
                _span(attestation["source_span"], "attestation.source_span")["path"],
                "attestation.source_span.path",
            )
            or _string(attestation["snapshot_id"], "attestation.snapshot_id") != snapshot_id
            or accepted == bool(rejection_reason)
            or attestation_id != _hash_parts(["attestation.v1", attestation_key])
        ):
            raise TransportInvalid("attestation provenance or ID derivation is invalid")
        _hex64(attestation["raw_line_hash"], "attestation.raw_line_hash")
        if attestation_id in attestations_by_id:
            raise TransportInvalid("duplicate attestation ID")
        evidence_key = (evidence_type, evidence_id)
        if evidence_key in attestations_by_evidence:
            raise TransportInvalid("duplicate attestation evidence provenance")
        attestations_by_id[attestation_id] = attestation
        attestations_by_evidence[evidence_key] = attestation

    def ambiguity_has(reason: str, evidence_id: str) -> bool:
        return any(
            _string(ambiguity["reason_code"], "ambiguity.reason_code") == reason
            and evidence_id in _strings(ambiguity["evidence_ids"], "ambiguity.evidence_ids")
            for ambiguity in ambiguities
        )

    for observation in observations:
        observation_id = _observation_id(
            observation["observation_id"], "observed_evidence.observation_id"
        )
        for field in (
            "extractor_id", "extractor_version", "capability_id", "relation_kind",
            "from_locator", "to_locator", "classification",
        ):
            if not _string(observation[field], f"observed_evidence.{field}"):
                raise TransportInvalid("observation provenance is incomplete")
        if _string(observation["snapshot_id"], "observed_evidence.snapshot_id") != snapshot_id:
            raise TransportInvalid("observation snapshot mismatch")
        payload_hash = _hex64(observation["payload_hash"], "observed_evidence.payload_hash")
        attestation = attestations_by_evidence.get(("observation", observation_id))
        if attestation is None:
            raise TransportInvalid("observation attestation missing")
        dependent, prerequisite, endpoint_reason = _observation_endpoints(
            observation, identities_by_id, excluded_ids
        )
        classification = _string(
            observation["classification"], "observed_evidence.classification"
        )
        discriminator = classification if "=" in classification else ""
        capability_id = _string(
            observation["capability_id"], "observed_evidence.capability_id"
        )
        raw_kind = _string(observation["relation_kind"], "observed_evidence.relation_kind")
        registry_entry = _registry_conversion(
            registry, capability_id, raw_kind, discriminator
        )
        expected_rejection = endpoint_reason
        if expected_rejection is None and ambiguity_has("kind_contradiction", observation_id):
            expected_rejection = "kind_contradiction"
        if expected_rejection is None:
            expected_rejection = _capability_rejection_reason(
                registry, capabilities_by_id.get(capability_id), observation
            )
        lowered = classification.lower()
        if expected_rejection is None and any(
            marker in lowered for marker in ("dynamic", "reflection", "runtime")
        ):
            expected_rejection = "dynamic_or_reflection"
        if expected_rejection is None and "unresolved" in lowered:
            expected_rejection = "unsupported_relation"
        if expected_rejection is None and not _bool(
            observation["accepted"], "observed_evidence.accepted"
        ):
            expected_rejection = "unsupported_relation"
        if expected_rejection is None and registry_entry is None:
            expected_rejection = "kind_unregistered"
        expected_kind = registry_entry.stored_kind if registry_entry is not None else raw_kind
        expected_accepted = expected_rejection is None
        if (
            _string(attestation["attestation_key"], "attestation.attestation_key")
            != _hash_parts(
                ["observed_attestation.v1", snapshot_id, observation_id, payload_hash]
            )
            or _string(
                attestation["declaring_identity_id"], "attestation.declaring_identity_id"
            )
            != dependent
            or _string(
                attestation["dependent_identity_id"], "attestation.dependent_identity_id"
            )
            != dependent
            or _string(
                attestation["prerequisite_identity_id"],
                "attestation.prerequisite_identity_id",
            )
            != prerequisite
            or _string(attestation["declared_direction"], "attestation.declared_direction")
            != "observed"
            or _string(attestation["relation_kind"], "attestation.relation_kind")
            != expected_kind
            or attestation["source_span"] != observation["source_span"]
            or _string(attestation["reason"], "attestation.reason") != classification
            or _string(attestation["raw_line_hash"], "attestation.raw_line_hash")
            != payload_hash
            or _bool(attestation["accepted"], "attestation.accepted") != expected_accepted
            or _string(attestation["rejection_reason"], "attestation.rejection_reason")
            != (expected_rejection or "")
            or _bool(observation["accepted"], "observed_evidence.accepted")
            != expected_accepted
        ):
            raise TransportInvalid("observation attestation consistency failed")

    for declaration in declarations:
        declaration_id = _string(
            declaration["declaration_id"], "dependency_declaration.declaration_id"
        )
        attestation = attestations_by_evidence.get(("declaration", declaration_id))
        if attestation is None:
            raise TransportInvalid("declaration attestation missing")
        dependent, prerequisite, expected_rejection = _declaration_endpoints(
            declaration, identities_by_id, excluded_ids
        )
        kind = _string(declaration["declared_kind"], "dependency_declaration.declared_kind")
        registry_entry = _registry_conversion(
            registry,
            "header-target-resolver.v1",
            "header_context",
            f"declared_kind={kind}",
        )
        if expected_rejection is None and registry_entry is None:
            expected_rejection = "kind_unregistered"
        if expected_rejection is None and ambiguity_has("kind_contradiction", declaration_id):
            expected_rejection = "kind_contradiction"
        expected_kind = registry_entry.stored_kind if registry_entry is not None else kind
        expected_accepted = expected_rejection is None
        if (
            _string(attestation["attestation_key"], "attestation.attestation_key")
            != _string(declaration["attestation_key"], "dependency_declaration.attestation_key")
            or _string(
                attestation["declaring_identity_id"], "attestation.declaring_identity_id"
            )
            != _string(
                declaration["source_identity_id"], "dependency_declaration.source_identity_id"
            )
            or _string(
                attestation["dependent_identity_id"], "attestation.dependent_identity_id"
            )
            != (dependent or "")
            or _string(
                attestation["prerequisite_identity_id"],
                "attestation.prerequisite_identity_id",
            )
            != (prerequisite or "")
            or _string(attestation["declared_direction"], "attestation.declared_direction")
            != _string(
                declaration["declared_direction"], "dependency_declaration.declared_direction"
            )
            or _string(attestation["relation_kind"], "attestation.relation_kind")
            != expected_kind
            or attestation["source_span"] != declaration["source_span"]
            or _string(attestation["reason"], "attestation.reason")
            != _string(declaration["reason"], "dependency_declaration.reason")
            or _string(attestation["raw_line_hash"], "attestation.raw_line_hash")
            != _string(declaration["raw_line_hash"], "dependency_declaration.raw_line_hash")
            or _bool(attestation["accepted"], "attestation.accepted") != expected_accepted
            or _string(attestation["rejection_reason"], "attestation.rejection_reason")
            != (expected_rejection or "")
        ):
            raise TransportInvalid("declaration attestation consistency failed")

    for ambiguity_id, ambiguity in ambiguities_by_id.items():
        source_id = _string(ambiguity["source_identity_id"], "ambiguity.source_identity_id")
        reason = _string(ambiguity["reason_code"], "ambiguity.reason_code")
        relation_kind = _string(ambiguity["relation_kind"], "ambiguity.relation_kind")
        candidate_fact_ids = _strings(
            ambiguity["candidate_fact_ids"], "ambiguity.candidate_fact_ids"
        )
        candidate_targets = _strings(
            ambiguity["candidate_targets"], "ambiguity.candidate_targets"
        )
        evidence_ids = _strings(ambiguity["evidence_ids"], "ambiguity.evidence_ids")
        expected_id = _hash_parts(
            [
                "ambiguity_a.v1", snapshot_id, source_id, reason, relation_kind,
                ",".join(candidate_fact_ids), ",".join(candidate_targets),
                ",".join(evidence_ids),
            ]
        )
        if (
            ambiguity_id != expected_id
            or _string(ambiguity["snapshot_id"], "ambiguity.snapshot_id") != snapshot_id
            or _bool(ambiguity["covered"], "ambiguity.covered")
            or not _bool(ambiguity["resolution_required"], "ambiguity.resolution_required")
            or not reason
            or not evidence_ids
            or candidate_fact_ids != sorted(set(candidate_fact_ids))
            or candidate_targets != sorted(set(candidate_targets))
            or evidence_ids != sorted(set(evidence_ids))
        ):
            raise TransportInvalid("ambiguity derivation or canonical ordering mismatch")
        contradiction = reason == "kind_contradiction"
        if not contradiction and len(evidence_ids) != 1:
            raise TransportInvalid("non-contradiction ambiguity must own one evidence row")
        expected_source_id = ""
        expected_kind = "kind_contradiction" if contradiction else ""
        expected_fact_ids: set[str] = set()
        expected_targets: set[str] = set()
        evidence_domain: str | None = None
        for evidence_id in evidence_ids:
            declaration = declarations_by_id.get(evidence_id)
            observation = observations_by_id.get(evidence_id)
            capability = capabilities_by_id.get(evidence_id)
            if sum(item is not None for item in (declaration, observation, capability)) != 1:
                raise TransportInvalid("ambiguity evidence does not resolve to one typed row")
            if declaration is not None:
                attestation = attestations_by_evidence.get(("declaration", evidence_id))
                if attestation is None or _bool(attestation["accepted"], "attestation.accepted") or _string(
                    attestation["rejection_reason"], "attestation.rejection_reason"
                ) != reason:
                    raise TransportInvalid("ambiguity declaration lacks matching rejected attestation")
                if evidence_domain is not None and (
                    evidence_domain == "capability"
                    or (not contradiction and evidence_domain != "declaration")
                ):
                    raise TransportInvalid("ambiguity mixes evidence domains")
                evidence_domain = "declaration"
                if contradiction:
                    dependent = _string(
                        attestation["dependent_identity_id"], "attestation.dependent_identity_id"
                    )
                    prerequisite = _string(
                        attestation["prerequisite_identity_id"],
                        "attestation.prerequisite_identity_id",
                    )
                    if expected_source_id and expected_source_id != dependent:
                        raise TransportInvalid("contradiction ambiguity source closure mismatch")
                    expected_source_id = dependent
                    expected_targets.update(
                        endpoint for endpoint in (dependent, prerequisite) if endpoint
                    )
                    if dependent in logical_by_id and prerequisite in logical_by_id:
                        pair_id = _hash_parts(
                            [
                                "relation_pair.v1", parent_repo_id,
                                logical_by_id[dependent], logical_by_id[prerequisite],
                            ]
                        )
                        expected_fact_ids.add(
                            _hash_parts(
                                [
                                    "normalized_relation.v1", pair_id,
                                    _string(attestation["relation_kind"], "attestation.relation_kind"),
                                ]
                            )
                        )
                else:
                    expected_source_id = _string(
                        declaration["source_identity_id"],
                        "dependency_declaration.source_identity_id",
                    )
                    expected_targets.add(
                        _string(
                            declaration["declared_target"],
                            "dependency_declaration.declared_target",
                        )
                    )
                    expected_kind = _string(
                        attestation["relation_kind"], "attestation.relation_kind"
                    )
            elif observation is not None:
                attestation = attestations_by_evidence.get(("observation", evidence_id))
                if attestation is None or _bool(attestation["accepted"], "attestation.accepted") or _string(
                    attestation["rejection_reason"], "attestation.rejection_reason"
                ) != reason:
                    raise TransportInvalid("ambiguity observation lacks matching rejected attestation")
                if evidence_domain is not None and (
                    evidence_domain == "capability"
                    or (not contradiction and evidence_domain != "observation")
                ):
                    raise TransportInvalid("ambiguity mixes evidence domains")
                evidence_domain = "observation"
                dependent = _string(
                    attestation["dependent_identity_id"], "attestation.dependent_identity_id"
                )
                prerequisite = _string(
                    attestation["prerequisite_identity_id"],
                    "attestation.prerequisite_identity_id",
                )
                if contradiction:
                    if expected_source_id and expected_source_id != dependent:
                        raise TransportInvalid("contradiction ambiguity source closure mismatch")
                    expected_source_id = dependent
                    expected_targets.update(
                        endpoint for endpoint in (dependent, prerequisite) if endpoint
                    )
                    if dependent in logical_by_id and prerequisite in logical_by_id:
                        pair_id = _hash_parts(
                            [
                                "relation_pair.v1", parent_repo_id,
                                logical_by_id[dependent], logical_by_id[prerequisite],
                            ]
                        )
                        expected_fact_ids.add(
                            _hash_parts(
                                [
                                    "normalized_relation.v1", pair_id,
                                    _string(attestation["relation_kind"], "attestation.relation_kind"),
                                ]
                            )
                        )
                else:
                    expected_source_id = _string(
                        observation["from_identity_id"], "observed_evidence.from_identity_id"
                    )
                    expected_targets.add(
                        _string(
                            observation["to_identity_id"], "observed_evidence.to_identity_id"
                        )
                    )
                    expected_kind = _string(
                        attestation["relation_kind"], "attestation.relation_kind"
                    )
            elif capability is not None:
                if evidence_domain not in (None, "capability"):
                    raise TransportInvalid("ambiguity mixes capability and relation evidence")
                evidence_domain = "capability"
                if (
                    reason != "capability_unknown"
                    or source_id
                    or candidate_fact_ids
                    or candidate_targets
                    or evidence_id in registered_capability_ids
                ):
                    raise TransportInvalid("capability ambiguity is not explicit unavailable evidence")
        if (
            source_id != expected_source_id
            or relation_kind != expected_kind
            or set(candidate_fact_ids) != expected_fact_ids
            or set(candidate_targets) != expected_targets
        ):
            raise TransportInvalid("ambiguity source/kind/candidate closure mismatch")

    for attestation in attestations:
        evidence_id = _string(attestation["evidence_id"], "attestation.evidence_id")
        matches = [
            ambiguity
            for ambiguity in ambiguities
            if evidence_id in _strings(ambiguity["evidence_ids"], "ambiguity.evidence_ids")
        ]
        if _bool(attestation["accepted"], "attestation.accepted"):
            if matches:
                raise TransportInvalid("accepted evidence has ambiguity provenance")
        elif len(matches) != 1 or _string(
            matches[0]["reason_code"], "ambiguity.reason_code"
        ) != _string(attestation["rejection_reason"], "attestation.rejection_reason"):
            raise TransportInvalid("rejected attestation ambiguity partition mismatch")

    relation_by_fact = _rows_by(relations, "fact_id", "normalized relation")
    registered_stored_kinds = {entry.stored_kind for entry in registry.entries}
    consumed_attestations: set[str] = set()
    for relation in relations:
        fact_id = _string(relation["fact_id"], "normalized_relation.fact_id")
        relation_kind = _string(
            relation["relation_kind"], "normalized_relation.relation_kind"
        )
        from_id = _string(
            relation["from_identity_id"], "normalized_relation.from_identity_id"
        )
        to_id = _string(relation["to_identity_id"], "normalized_relation.to_identity_id")
        if (
            not _bool(relation["accepted"], "normalized_relation.accepted")
            or _string(
                relation["semantic_direction"], "normalized_relation.semantic_direction"
            )
            != "depends_on"
            or _string(
                relation["source_snapshot_id"], "normalized_relation.source_snapshot_id"
            )
            != snapshot_id
            or relation_kind not in registered_stored_kinds
            or from_id not in identities_by_id
            or to_id not in identities_by_id
            or from_id in excluded_ids
            or to_id in excluded_ids
            or not _bool(identities_by_id[from_id]["exists"], "source_identity.exists")
            or not _bool(identities_by_id[to_id]["exists"], "source_identity.exists")
        ):
            raise TransportInvalid("normalized direct fact or source-universe contract failed")
        expected_pair = _hash_parts(
            [
                "relation_pair.v1", parent_repo_id,
                logical_by_id[from_id], logical_by_id[to_id],
            ]
        )
        expected_fact = _hash_parts(
            ["normalized_relation.v1", expected_pair, relation_kind]
        )
        if (
            _string(relation["pair_identity"], "normalized_relation.pair_identity")
            != expected_pair
            or fact_id != expected_fact
        ):
            raise TransportInvalid("normalized fact/pair identity derivation mismatch")
        attestation_ids = _strings(
            relation["attestation_ids"], "normalized_relation.attestation_ids"
        )
        observation_ids = _strings(
            relation["observation_ids"], "normalized_relation.observation_ids"
        )
        if (
            not attestation_ids
            or attestation_ids != sorted(set(attestation_ids))
            or observation_ids != sorted(set(observation_ids))
        ):
            raise TransportInvalid("fact provenance is empty, duplicated, or unsorted")
        expected_observation_ids: list[str] = []
        has_declaration = False
        has_observation = False
        for attestation_id in attestation_ids:
            attestation = attestations_by_id.get(attestation_id)
            if (
                attestation is None
                or not _bool(attestation["accepted"], "attestation.accepted")
                or _string(
                    attestation["dependent_identity_id"], "attestation.dependent_identity_id"
                )
                != from_id
                or _string(
                    attestation["prerequisite_identity_id"],
                    "attestation.prerequisite_identity_id",
                )
                != to_id
                or _string(attestation["relation_kind"], "attestation.relation_kind")
                != relation_kind
                or _string(attestation["snapshot_id"], "attestation.snapshot_id")
                != snapshot_id
                or attestation_id in consumed_attestations
            ):
                raise TransportInvalid("fact attestation endpoint/kind/snapshot/membership mismatch")
            consumed_attestations.add(attestation_id)
            evidence_type = _string(attestation["evidence_type"], "attestation.evidence_type")
            if evidence_type == "declaration":
                has_declaration = True
            else:
                has_observation = True
                expected_observation_ids.append(
                    _string(attestation["evidence_id"], "attestation.evidence_id")
                )
        expected_observation_ids.sort()
        if observation_ids != expected_observation_ids or any(
            observation_id not in observations_by_id
            for observation_id in expected_observation_ids
        ):
            raise TransportInvalid("fact observation provenance membership is incomplete")
        if has_declaration and has_observation:
            expected_status, expected_authority = "matched", "declaration+observation"
        elif has_declaration:
            expected_status, expected_authority = "declared_only", "declaration"
        elif has_observation:
            expected_status, expected_authority = "observed_only", "observation"
        else:
            raise TransportInvalid("fact has no typed attestation provenance")
        expected_hashes = [
            _string(identities_by_id[from_id]["content_hash"], "source_identity.content_hash"),
            _string(identities_by_id[to_id]["content_hash"], "source_identity.content_hash"),
        ]
        source_hashes = _strings(
            relation["source_content_hashes"], "normalized_relation.source_content_hashes"
        )
        if (
            _string(
                relation["reconciliation_status"],
                "normalized_relation.reconciliation_status",
            )
            != expected_status
            or _string(relation["authority"], "normalized_relation.authority")
            != expected_authority
            or source_hashes != expected_hashes
            or not _content_identity_is_canonical(
                identities_by_id[from_id], source_hashes[0]
            )
            or not _content_identity_is_canonical(
                identities_by_id[to_id], source_hashes[1]
            )
        ):
            raise TransportInvalid("relation reconciliation/content provenance mismatch")

    accepted_attestation_ids = {
        _string(attestation["attestation_id"], "attestation.attestation_id")
        for attestation in attestations
        if _bool(attestation["accepted"], "attestation.accepted")
    }
    if consumed_attestations != accepted_attestation_ids:
        raise TransportInvalid("accepted fact provenance membership is incomplete")
    if any(
        candidate in relation_by_fact
        for ambiguity in ambiguities
        for candidate in _strings(ambiguity["candidate_fact_ids"], "ambiguity.candidate_fact_ids")
    ):
        raise TransportInvalid("accepted facts overlap ambiguity candidates")

    for declaration in declarations:
        declaration_id = _string(
            declaration["declaration_id"], "dependency_declaration.declaration_id"
        )
        attestation = attestations_by_evidence[("declaration", declaration_id)]
        if _bool(attestation["accepted"], "attestation.accepted"):
            dependent = _string(
                attestation["dependent_identity_id"], "attestation.dependent_identity_id"
            )
            prerequisite = _string(
                attestation["prerequisite_identity_id"],
                "attestation.prerequisite_identity_id",
            )
            pair_id = _hash_parts(
                [
                    "relation_pair.v1", parent_repo_id,
                    logical_by_id[dependent], logical_by_id[prerequisite],
                ]
            )
            fact_id = _hash_parts(
                [
                    "normalized_relation.v1", pair_id,
                    _string(attestation["relation_kind"], "attestation.relation_kind"),
                ]
            )
            if fact_id not in relation_by_fact:
                raise TransportInvalid("accepted declaration has no direct fact")
    if len(attestations) != len(declarations) + len(observations):
        raise TransportInvalid("evidence/attestation partition is not exhaustive")
    statuses = [
        _string(relation["reconciliation_status"], "normalized_relation.reconciliation_status")
        for relation in relations
    ]
    if any(status not in {"matched", "declared_only", "observed_only"} for status in statuses):
        raise TransportInvalid("reconciliation partition is not exhaustive and disjoint")


def load_normalized_record_set(
    path: Path,
    *,
    expected_root: Path,
    expected_snapshot_id: str,
    relation_registry_path: Path,
) -> NormalizedRecordSetV1:
    """Decode one exact current Rust normalized-record JSONL artifact."""
    if not HEX64.fullmatch(expected_snapshot_id):
        raise TransportInvalid("expected snapshot ID must be lowercase 64-hex")
    registry = load_relation_registry_artifact(relation_registry_path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise TransportInvalid(f"normalized record set: {error}") from error
    if raw.startswith(b"\xef\xbb\xbf"):
        raise TransportInvalid("normalized JSONL must not contain a UTF-8 BOM")
    lines = raw.splitlines(keepends=True)
    if len(lines) < 3:
        raise TransportInvalid("normalized record set requires header, snapshot, and summary")
    values = [_parse_line(line, index) for index, line in enumerate(lines, 1)]
    first = values[0]
    if _string(first["record_type"], "line 1.record_type") != "normalized_record_set_header.v1":
        raise TransportInvalid("normalized record-set header must be first")
    if _string(first["schema_version"], "line 1.schema_version") != MANIFEST_SCHEMA_VERSION:
        raise TransportInvalid("normalized envelope schema mismatch")
    if (
        _string(first["record_id"], "line 1.record_id") != expected_snapshot_id
        or _string(first["snapshot_id"], "line 1.snapshot_id") != expected_snapshot_id
    ):
        raise TransportInvalid("normalized header snapshot mismatch")
    header_payload = _validate_header_payload(first["payload"], expected_snapshot_id)

    family_values: dict[str, list[JsonObject]] = {family: [] for family in PAYLOAD_KEYS}
    header: JsonObject | None = None
    summary: JsonObject | None = None
    previous_rank = 0
    previous_id: str | None = None
    for index, value in enumerate(values[1:], 2):
        if (
            _string(value["schema_version"], f"line {index}.schema_version")
            != MANIFEST_SCHEMA_VERSION
            or _string(value["snapshot_id"], f"line {index}.snapshot_id")
            != expected_snapshot_id
        ):
            raise TransportInvalid(f"line {index} envelope schema/snapshot mismatch")
        record_type = _string(value["record_type"], f"line {index}.record_type")
        if record_type not in FAMILY_RANK:
            raise TransportInvalid(f"unknown normalized record type {record_type}")
        rank = FAMILY_RANK[record_type]
        if rank < previous_rank or (rank == 11 and index != len(values)):
            raise TransportInvalid("normalized record families are not in canonical order")
        record_id = _string(value["record_id"], f"line {index}.record_id")
        if rank == previous_rank and previous_id is not None and record_id <= previous_id:
            raise TransportInvalid("normalized record IDs are not strictly increasing")
        previous_rank, previous_id = rank, record_id
        if record_type == "source_snapshot.v1":
            if header is not None:
                raise TransportInvalid("duplicate normalized source snapshot")
            header = _validate_snapshot_payload(value["payload"], expected_snapshot_id)
            _validate_record_id(record_type, record_id)
            if record_id != expected_snapshot_id:
                raise TransportInvalid("normalized source snapshot mismatch")
        elif record_type == "normalization_summary.v1":
            if summary is not None:
                raise TransportInvalid("duplicate normalization summary")
            summary = _validate_summary_payload(value["payload"], expected_snapshot_id)
            _validate_record_id(record_type, record_id)
            if record_id != expected_snapshot_id:
                raise TransportInvalid("normalization summary mismatch")
        else:
            payload = _validate_payload(record_type, value["payload"])
            id_field = FAMILY_ID_FIELDS[record_type]
            if _string(payload[id_field], f"{record_type}.{id_field}") != record_id:
                raise TransportInvalid(f"{record_type} record_id mismatch")
            _validate_record_id(record_type, record_id)
            _validate_payload_linkage(record_type, payload, expected_snapshot_id)
            family_values[record_type].append(payload)
    if header is None or summary is None:
        raise TransportInvalid("normalized record set is missing source snapshot or summary")
    if values[-1]["record_type"] != "normalization_summary.v1":
        raise TransportInvalid("normalization summary must be last")
    header = dict(header)
    header.update(
        source_fingerprint=_string(
            header_payload["source_fingerprint"], "normalized_header.source_fingerprint"
        ),
        profile=_string(header_payload["profile"], "normalized_header.profile"),
    )
    if Path(_string(header["root_realpath"], "source_snapshot.root_realpath")).resolve() != expected_root.resolve():
        raise TransportInvalid("normalized root mismatch")
    identities = tuple(family_values["source_identity.v1"])
    declarations = tuple(family_values["dependency_declaration.v1"])
    attestations = tuple(family_values["attestation.v1"])
    relations = tuple(family_values["normalized_relation.v1"])
    observations = tuple(family_values["observed_evidence.v1"])
    surface_relations = tuple(family_values["surface_relation.v1"])
    exclusions = tuple(family_values["source_exclusion.v1"])
    ambiguities = tuple(family_values["ambiguity_a.v1"])
    capabilities = tuple(family_values["extractor_capability.v1"])
    source_universe = _source_universe(identities, exclusions)
    computed_counts: dict[str, int] = {
        "source_snapshot.v1": 1,
        **{family: len(rows) for family, rows in family_values.items()},
        "matched_count": sum(
            _string(row["reconciliation_status"], "normalized_relation.reconciliation_status")
            == "matched"
            for row in family_values["normalized_relation.v1"]
        ),
        "declared_only_count": sum(
            _string(row["reconciliation_status"], "normalized_relation.reconciliation_status")
            == "declared_only"
            for row in family_values["normalized_relation.v1"]
        ),
        "observed_only_count": sum(
            _string(row["reconciliation_status"], "normalized_relation.reconciliation_status")
            == "observed_only"
            for row in family_values["normalized_relation.v1"]
        ),
        "accepted_direct_fact_count": len(family_values["normalized_relation.v1"]),
        "rejected_declaration_count": sum(
            _string(row["evidence_type"], "attestation.evidence_type") == "declaration"
            and not _bool(row["accepted"], "attestation.accepted")
            for row in family_values["attestation.v1"]
        ),
        "rejected_observation_count": sum(
            _string(row["evidence_type"], "attestation.evidence_type") == "observation"
            and not _bool(row["accepted"], "attestation.accepted")
            for row in family_values["attestation.v1"]
        ),
        "excluded_count": len(exclusions),
        "unresolved_count": len(family_values["ambiguity_a.v1"]),
        "duplicate_evidence_count": 0,
        "x_core_count": 0,
    }
    summary_counts = _json_object(
        summary["record_counts"], "normalization_summary.record_counts"
    )
    if {
        key: _nonnegative_int(value, f"normalization_summary.record_counts.{key}")
        for key, value in summary_counts.items()
    } != computed_counts:
        raise TransportInvalid("normalization summary record counts mismatch")
    expected_fingerprint = _normalized_fingerprint(values)
    if _string(
        summary["normalized_record_fingerprint"],
        "normalization_summary.normalized_record_fingerprint",
    ) != expected_fingerprint:
        raise TransportInvalid("normalized record fingerprint mismatch")
    if _nonnegative_int(
        summary["accepted_fact_count"], "normalization_summary.accepted_fact_count"
    ) != len(family_values["normalized_relation.v1"]):
        raise TransportInvalid("accepted fact count mismatch")
    if (
        _nonnegative_int(
            summary["rejected_declaration_count"],
            "normalization_summary.rejected_declaration_count",
        )
        != computed_counts["rejected_declaration_count"]
        or _nonnegative_int(
            summary["rejected_observation_count"],
            "normalization_summary.rejected_observation_count",
        )
        != computed_counts["rejected_observation_count"]
        or _nonnegative_int(
            summary["ambiguity_count"], "normalization_summary.ambiguity_count"
        )
        != len(family_values["ambiguity_a.v1"])
        or _nonnegative_int(
            summary["source_exclusion_count"],
            "normalization_summary.source_exclusion_count",
        )
        != len(exclusions)
    ):
        raise TransportInvalid("normalization summary metadata count mismatch")
    _validate_normalized_semantics(
        header,
        identities,
        declarations,
        attestations,
        relations,
        observations,
        surface_relations,
        exclusions,
        ambiguities,
        capabilities,
        source_universe,
        registry,
    )
    return NormalizedRecordSetV1(
        header=_freeze_mapping(header),
        source_identities=tuple(_freeze_mapping(value) for value in identities),
        declarations=tuple(_freeze_mapping(value) for value in declarations),
        attestations=tuple(_freeze_mapping(value) for value in attestations),
        relations=tuple(_freeze_mapping(value) for value in relations),
        observations=tuple(_freeze_mapping(value) for value in observations),
        surface_relations=tuple(_freeze_mapping(value) for value in surface_relations),
        source_exclusions=tuple(_freeze_mapping(value) for value in exclusions),
        ambiguities=tuple(_freeze_mapping(value) for value in ambiguities),
        capabilities=tuple(_freeze_mapping(value) for value in capabilities),
        source_universe=_freeze_mapping(source_universe),
        summary=_freeze_mapping(summary),
    )


def _registry_entry_from_fixture(row: JsonMapping) -> RelationRegistryEntryV1:
    expected = {"case", "producer", "raw_kind", "discriminator", "stored_kind", "layer", "query_family"}
    _exact_keys(row, expected, "relation registry source row")
    return {
        "capability_id": _string(row["producer"], "producer"),
        "discriminator": _string(row["discriminator"], "discriminator"),
        "family": _string(row["query_family"], "query_family"),
        "layer": _string(row["layer"], "layer"),
        "raw_kind": _string(row["raw_kind"], "raw_kind"),
        "stored_kind": _string(row["stored_kind"], "stored_kind"),
    }


def write_relation_registry_conformance_artifact(
    source_fixture: Path,
    output: Path,
) -> RelationRegistryArtifactV1:
    """Project the exact AgentCanon registry fixture into canonical R2 JSON."""
    try:
        lines = source_fixture.read_bytes().splitlines(keepends=True)
    except OSError as error:
        raise TransportInvalid(f"relation registry source fixture: {error}") from error
    rows: list[RelationRegistryEntryV1] = []
    for index, line in enumerate(lines, 1):
        if not line.endswith(b"\n") or line.endswith(b"\r\n"):
            raise TransportInvalid(f"registry source line {index} is not LF-terminated")
        try:
            row = cast(
                object,
                json.loads(
                    line[:-1].decode("utf-8"),
                    object_pairs_hook=_strict_object,
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, TransportInvalid) as error:
            raise TransportInvalid(f"registry source line {index}: {error}") from error
        rows.append(
            _registry_entry_from_fixture(
                _json_object(row, f"registry source line {index}")
            )
        )
    entries = sorted(
        rows,
        key=lambda row: (
            row["capability_id"], row["raw_kind"], row["discriminator"], row["stored_kind"],
            row["layer"], row["family"],
        ),
    )
    if len(entries) != 20 or len({tuple(sorted(entry.items())) for entry in entries}) != 20:
        raise TransportInvalid("relation registry source fixture must project exactly 20 unique rows")
    fingerprint = _sha256_bytes(_canonical_bytes({"entries": entries, "registry_version": REGISTRY_VERSION}))
    if fingerprint != EXPECTED_REGISTRY_FINGERPRINT:
        raise TransportInvalid("projected relation registry fingerprint does not match generic baseline")
    artifact: RelationRegistryArtifactV1 = {
        "entries": entries,
        "registry_fingerprint": fingerprint,
        "registry_version": REGISTRY_VERSION,
    }
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_canonical_bytes(artifact) + b"\n")
    except OSError as error:
        raise TransportInvalid(f"relation registry artifact output: {error}") from error
    return artifact


def main(argv: Sequence[str]) -> int:
    """Run the relation-registry conformance producer CLI."""
    parser = argparse.ArgumentParser(prog="dependency_manifest_records.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    producer = subparsers.add_parser("relation-registry-artifact")
    producer.add_argument("--source-fixture", type=Path, required=True)
    producer.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(list(argv))
    command = cast(str, args.command)
    source_fixture = cast(Path, args.source_fixture)
    output = cast(Path, args.output)
    try:
        if command == "relation-registry-artifact":
            artifact = write_relation_registry_conformance_artifact(source_fixture, output)
            print(
                "R2_REGISTRY_PRODUCER=pass "
                f"bytes={output.stat().st_size} "
                f"sha256={_sha256_bytes(output.read_bytes())} "
                f"entries={len(artifact['entries'])} fingerprint={artifact['registry_fingerprint']}"
            )
            return 0
    except (OSError, TransportInvalid) as error:
        print(f"R2_REGISTRY_PRODUCER=transport-invalid error={error}", file=sys.stderr)
        return 22
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
