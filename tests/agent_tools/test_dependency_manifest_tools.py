"""Tests for dependency manifest shell tools."""

# @dependency-start
# contract test
# responsibility Tests dependency manifest shell tool behavior.
# upstream design ../../documents/dependency-contract-kinds.toml registered dependency header contract kinds
# upstream design ../../documents/dependency-manifest-design.md manifest design
# upstream design ../../reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_brief.md approved generic protocol/tool slice
# upstream implementation ../../tools/agent_tools/scan_dependency_headers.sh scans
# upstream implementation ../../tools/agent_tools/check_dependency_header_format.sh format checks
# upstream implementation ../../tools/agent_tools/check_dependency_graph.sh graph checks
# upstream implementation ../../tools/agent_tools/run_repo_dependency_review.sh wraps
# upstream implementation ../../tools/agent_tools/scan_code_dependencies.sh scans code
# upstream implementation ../../tools/agent_tools/dependency_manifest_records.py decodes normalized records and produces registry artifact
# upstream implementation ../../tools/agent_tools/bind_r2_scope.py binds R2 review evidence
# downstream implementation ../../tests/fixtures/dependency_manifest/transport_conformance.jsonl supplies transport adversaries
# @dependency-end

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from tools.agent_tools import dependency_manifest_records as dependency_records
from tools.agent_tools.bind_r2_scope import closeout, manifest
from tools.agent_tools.dependency_manifest_records import (
    TransportInvalid,
    load_normalized_record_set,
    load_relation_registry_artifact,
    write_relation_registry_conformance_artifact,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCAN = PROJECT_ROOT / "tools" / "agent_tools" / "scan_dependency_headers.sh"
FORMAT = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_header_format.sh"
GRAPH = PROJECT_ROOT / "tools" / "agent_tools" / "check_dependency_graph.sh"
REPO_REVIEW = PROJECT_ROOT / "tools" / "agent_tools" / "run_repo_dependency_review.sh"
CODE_SCAN = PROJECT_ROOT / "tools" / "agent_tools" / "scan_code_dependencies.sh"
DESIGN_CLAIMS = PROJECT_ROOT / "tools" / "agent_tools" / "check_design_doc_claims.py"
WORKFLOW_MONITOR = PROJECT_ROOT / "tools" / "agent_tools" / "workflow_monitor.py"
AGENT_TEAM = PROJECT_ROOT / "tools" / "agent_tools" / "agent_team.py"
REQUIREMENT_SYNC = PROJECT_ROOT / "tools" / "requirement_sync_validator.py"
DOCKER_VALIDATOR = PROJECT_ROOT / "tools" / "docker_dependency_validator.sh"
TRANSPORT_CONFORMANCE = (
    PROJECT_ROOT / "tests" / "fixtures" / "dependency_manifest" / "transport_conformance.jsonl"
)
RELATION_RECONCILIATION = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "dependency_manifest"
    / "relation_reconciliation.jsonl"
)
RELATION_REGISTRY_SOURCE = (
    PROJECT_ROOT / "tests" / "fixtures" / "knowledge_graph" / "query_kind_registry.jsonl"
)
RETAINED_RELATION_REGISTRY = (
    PROJECT_ROOT
    / "reports"
    / "agents"
    / "20260712-090608-context-packettool-skill-routing"
    / "validation"
    / "r2-source-pr"
    / "agentcanon_relation_registry.v1.json"
)
RETAINED_NORMALIZED_RECORD_SET = (
    PROJECT_ROOT
    / "reports"
    / "agents"
    / "20260712-090608-context-packettool-skill-routing"
    / "validation"
    / "r2-normalized-record-set.v1.jsonl"
)

JsonObject = dict[str, object]
JsonMapping = Mapping[str, object]
ValidateSnapshotDerivations = Callable[
    [
        JsonMapping,
        tuple[JsonMapping, ...],
        tuple[JsonMapping, ...],
        tuple[JsonMapping, ...],
        tuple[JsonMapping, ...],
    ],
    tuple[dict[str, JsonMapping], set[str], dict[str, str]],
]
DeclarationEndpoints = Callable[
    [JsonMapping, Mapping[str, JsonMapping], set[str]],
    tuple[str | None, str | None, str | None],
]
VALIDATE_SNAPSHOT_DERIVATIONS = cast(
    ValidateSnapshotDerivations,
    getattr(dependency_records, "_validate_snapshot_derivations"),
)
DECLARATION_ENDPOINTS = cast(
    DeclarationEndpoints,
    getattr(dependency_records, "_declaration_endpoints"),
)


def _json_object(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise AssertionError(f"{label} must be an object with string keys")
    raw_object = cast(dict[object, object], value)
    for key in raw_object:
        if not isinstance(key, str):
            raise AssertionError(f"{label} must be an object with string keys")
    return cast(JsonObject, raw_object)


def _parse_json_object(value: str | bytes, label: str) -> JsonObject:
    return _json_object(cast(object, json.loads(value)), label)


def _object_field(value: JsonObject, field: str, label: str) -> JsonObject:
    return _json_object(value[field], f"{label}.{field}")


def _string_field(value: JsonObject, field: str, label: str) -> str:
    field_value = value[field]
    if not isinstance(field_value, str):
        raise AssertionError(f"{label}.{field} must be a string")
    return field_value


def _int_field(value: JsonObject, field: str, label: str) -> int:
    field_value = value[field]
    if not isinstance(field_value, int) or isinstance(field_value, bool):
        raise AssertionError(f"{label}.{field} must be an integer")
    return field_value


def _string_list_field(value: JsonObject, field: str, label: str) -> list[str]:
    field_value = value[field]
    if not isinstance(field_value, list):
        raise AssertionError(f"{label}.{field} must be a string list")
    raw_values = cast(list[object], field_value)
    if any(not isinstance(item, str) for item in raw_values):
        raise AssertionError(f"{label}.{field} must be a string list")
    return cast(list[str], raw_values)


def _canonical_record_bytes(records: list[JsonObject]) -> bytes:
    return b"".join(
        json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
        for record in records
    )


def _hash_parts(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _duplicate_json_field(
    raw: bytes,
    field: str,
    value: object,
    *,
    occurrence: int = 0,
) -> bytes:
    encoded_field = json.dumps(
        field,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8") + b":" + json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    positions: list[int] = []
    offset = 0
    while True:
        position = raw.find(encoded_field, offset)
        if position < 0:
            break
        positions.append(position)
        offset = position + len(encoded_field)
    if occurrence >= len(positions):
        raise AssertionError(
            f"JSON field {field} occurrence {occurrence} is absent from fixture bytes"
        )
    position = positions[occurrence]
    return raw[:position] + encoded_field + b"," + raw[position:]


def _noncanonical_first_envelope(raw: bytes) -> bytes:
    lines = raw.splitlines(keepends=True)
    first = _parse_json_object(lines[0], "normalized header")
    reordered = {
        field: first[field]
        for field in ("record_id", "payload", "record_type", "schema_version", "snapshot_id")
    }
    first_line = json.dumps(
        reordered,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    return first_line + b"".join(lines[1:])


def _refreshed_normalized_fingerprint(records: list[JsonObject]) -> str:
    body = [
        {
            "record_type": _string_field(record, "record_type", "normalized record"),
            "record_id": _string_field(record, "record_id", "normalized record"),
            "payload": record["payload"],
        }
        for record in records
        if _string_field(record, "record_type", "normalized record")
        not in {"normalized_record_set_header.v1", "normalization_summary.v1"}
    ]
    return hashlib.sha256(
        b"".join(
            json.dumps(
                record,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\0"
            for record in body
        )
    ).hexdigest()


def _write_registry(root: Path) -> Path:
    path = root / "agentcanon_relation_registry.v1.json"
    write_relation_registry_conformance_artifact(RELATION_REGISTRY_SOURCE, path)
    return path


def _write_scope_fixture(
    root: Path,
) -> tuple[Path, str, Path, Path, Path]:
    source = root / "source.txt"
    fixture = root / "fixture.txt"
    source.write_text("source\n", encoding="utf-8")
    fixture.write_text("fixture\n", encoding="utf-8")
    registry = _write_registry(root)
    manifest_path = root / "scope.json"
    status = manifest(
        [
            "--source", str(source), "--fixture", str(fixture),
            "--registry-artifact", str(registry), "--command-id", "CMD-R2-PY",
            "--output", str(manifest_path),
        ]
    )
    if status != 0:
        raise AssertionError(f"scope fixture manifest failed with status {status}")
    manifest_value = _parse_json_object(
        manifest_path.read_text(encoding="utf-8"), "scope manifest"
    )
    manifest_id = _string_field(manifest_value, "scope_manifest_id", "scope manifest")
    return manifest_path, manifest_id, source, fixture, registry


def run_tool(*args: str, root: Path) -> subprocess.CompletedProcess[str]:
    """Run a dependency manifest shell tool."""
    return subprocess.run(
        ["bash", *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class DependencyManifestToolTest(unittest.TestCase):
    """Exercise the dependency manifest shell tools."""

    def test_relation_registry_producer_matches_exact_generic_artifact(self) -> None:
        """The generic producer emits the frozen 20-row canonical artifact."""
        fixture = PROJECT_ROOT / "tests" / "fixtures" / "knowledge_graph" / "query_kind_registry.jsonl"
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "agentcanon_relation_registry.v1.json"
            artifact = write_relation_registry_conformance_artifact(fixture, output)
            self.assertEqual(output.stat().st_size, 3323)
            self.assertEqual(
                hashlib.sha256(output.read_bytes()).hexdigest(),
                "e2601dcd34a2d6896526f6efc519a7faee7c9a47ccd50bdd29d04ecc8cf6ac69",
            )
            self.assertEqual(len(artifact["entries"]), 20)
            self.assertEqual(
                artifact["registry_fingerprint"],
                "1308cf12d7d9c2aa8d67b3cff250484d905e70304a6fb3dafdd7da94a7925624",
            )

    def test_runtime_registry_artifact_is_the_decoder_authority(self) -> None:
        """A self-consistent caller artifact, not a built-in set, drives semantics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            baseline = _write_registry(root)
            value = _parse_json_object(baseline.read_text(encoding="utf-8"), "registry")
            entries_value = value["entries"]
            if not isinstance(entries_value, list):
                self.fail("registry entries must be a list")
            entries = cast(list[object], entries_value)
            entries.append(
                {
                    "capability_id": "zz-review-only.v1",
                    "discriminator": "",
                    "family": "review",
                    "layer": "artifact",
                    "raw_kind": "review_link",
                    "stored_kind": "review_link",
                }
            )
            entries.sort(
                key=lambda item: (
                    _string_field(_json_object(item, "registry entry"), "capability_id", "registry entry"),
                    _string_field(_json_object(item, "registry entry"), "raw_kind", "registry entry"),
                    _string_field(_json_object(item, "registry entry"), "discriminator", "registry entry"),
                    _string_field(_json_object(item, "registry entry"), "stored_kind", "registry entry"),
                    _string_field(_json_object(item, "registry entry"), "layer", "registry entry"),
                    _string_field(_json_object(item, "registry entry"), "family", "registry entry"),
                )
            )
            value["registry_fingerprint"] = hashlib.sha256(
                json.dumps(
                    {"entries": entries, "registry_version": "relation_registry.v1"},
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            extended = root / "extended-registry.json"
            extended.write_bytes(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            validated = load_relation_registry_artifact(extended)
            self.assertEqual(len(validated.entries), 21)
            retained = [
                _parse_json_object(line, f"normalized line {index}")
                for index, line in enumerate(
                    RETAINED_NORMALIZED_RECORD_SET.read_text(encoding="utf-8").splitlines(),
                    1,
                )
            ]
            with self.assertRaises(TransportInvalid):
                load_normalized_record_set(
                    RETAINED_NORMALIZED_RECORD_SET,
                    expected_root=PROJECT_ROOT.parent.parent,
                    expected_snapshot_id=_string_field(
                        retained[0], "record_id", "normalized header"
                    ),
                    relation_registry_path=extended,
                )

    def test_normalized_record_set_projection_is_deeply_immutable(self) -> None:
        """Post-load nested mutation cannot alter verified aggregate decisions."""
        values = [
            _parse_json_object(line, f"normalized line {index}")
            for index, line in enumerate(
                RETAINED_NORMALIZED_RECORD_SET.read_text(encoding="utf-8").splitlines(),
                1,
            )
        ]
        record_set = load_normalized_record_set(
            RETAINED_NORMALIZED_RECORD_SET,
            expected_root=PROJECT_ROOT.parent.parent,
            expected_snapshot_id=_string_field(values[0], "record_id", "normalized header"),
            relation_registry_path=RETAINED_RELATION_REGISTRY,
        )
        original_snapshot_id = record_set.summary["snapshot_id"]
        with self.assertRaises(TypeError):
            cast(dict[str, object], record_set.summary)["snapshot_id"] = "f" * 64
        counts = record_set.summary["record_counts"]
        with self.assertRaises(TypeError):
            cast(dict[str, object], counts)["accepted_direct_fact_count"] = 0
        alternates = record_set.source_identities[0]["alternate_locators"]
        with self.assertRaises(AttributeError):
            cast(list[object], alternates).append("forged")
        self.assertEqual(record_set.summary["snapshot_id"], original_snapshot_id)

    def test_r2_scope_closeout_rehashes_every_bound_input(self) -> None:
        """Stale or missing source, fixture, and registry bytes block closeout."""
        for target_name in ("source", "fixture", "registry"):
            for mutation in ("stale", "missing"):
                with self.subTest(target=target_name, mutation=mutation), tempfile.TemporaryDirectory() as tmp_dir:
                    root = Path(tmp_dir)
                    manifest_path, manifest_id, source, fixture, registry = _write_scope_fixture(root)
                    change_review = root / "change.md"
                    logic_review = root / "logic.md"
                    change_review.write_text(
                        f"# Change\n\ndecision: approve\nbound_scope_manifest_id: {manifest_id}\n",
                        encoding="utf-8",
                    )
                    logic_review.write_text(
                        f"# Logic\n\ndecision: approve\nbound_scope_manifest_id: {manifest_id}\n",
                        encoding="utf-8",
                    )
                    target = {"source": source, "fixture": fixture, "registry": registry}[target_name]
                    if mutation == "stale":
                        target.write_bytes(target.read_bytes() + b"stale\n")
                    else:
                        target.unlink()
                    output = root / "closeout.json"
                    self.assertEqual(
                        closeout(
                            [
                                "--manifest", str(manifest_path),
                                "--change-review", str(change_review),
                                "--logic-review", str(logic_review),
                                "--output", str(output),
                            ]
                        ),
                        21,
                    )
                    self.assertFalse(output.exists())

    def test_r2_scope_review_machine_fields_are_unique_and_canonical(self) -> None:
        """Only one exact decision and manifest binding line is accepted per review."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            manifest_path, manifest_id, _, _, _ = _write_scope_fixture(root)
            change_review = root / "change.md"
            logic_review = root / "logic.md"
            change_review.write_text(
                f"# Change\n\ndecision: approve\nbound_scope_manifest_id: {manifest_id}\n",
                encoding="utf-8",
            )
            logic_review.write_text(
                f"# Logic\n\ndecision: approve\nbound_scope_manifest_id: {manifest_id}\n",
                encoding="utf-8",
            )
            output = root / "closeout.json"
            self.assertEqual(
                closeout(
                    [
                        "--manifest", str(manifest_path),
                        "--change-review", str(change_review),
                        "--logic-review", str(logic_review),
                        "--output", str(output),
                    ]
                ),
                0,
            )
            self.assertTrue(output.is_file())
            canonical = (
                f"# Change\n\ndecision: approve\nbound_scope_manifest_id: {manifest_id}\n"
            ).encode()
            invalid_reviews = {
                "duplicate-decision": canonical + b"decision: revise\n",
                "duplicate-bound": canonical + f"bound_scope_manifest_id: {'0' * 64}\n".encode(),
                "malformed-decision": canonical.replace(b"decision: approve", b"decision : approve"),
                "indented-bound": canonical.replace(b"bound_scope", b" bound_scope"),
                "crlf": canonical.replace(b"\n", b"\r\n"),
                "bom": b"\xef\xbb\xbf" + canonical,
                "missing-final-lf": canonical[:-1],
                "invalid-utf8": canonical + b"\xff\n",
            }
            for name, raw in invalid_reviews.items():
                with self.subTest(name=name):
                    change_review.write_bytes(raw)
                    self.assertEqual(
                        closeout(
                            [
                                "--manifest", str(manifest_path),
                                "--change-review", str(change_review),
                                "--logic-review", str(logic_review),
                                "--output", str(output),
                            ]
                        ),
                        21,
                    )
                    self.assertFalse(output.exists())

    def test_r2_scope_binding_fails_closed_without_bound_reviews(self) -> None:
        """The post-review phase cannot claim approval from unbound reviews."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.txt"
            fixture = root / "fixture.txt"
            registry = root / "registry.json"
            invalid_registry = root / "invalid-registry.json"
            manifest_path = root / "scope.json"
            closeout_path = root / "closeout.json"
            source.write_text("source\n", encoding="utf-8")
            fixture.write_text("fixture\n", encoding="utf-8")
            invalid_registry.write_text(
                json.dumps({"registry_fingerprint": "1" * 64}) + "\n",
                encoding="utf-8",
            )
            invalid_status = manifest(
                [
                    "--source", str(source), "--fixture", str(fixture),
                    "--registry-artifact", str(invalid_registry), "--command-id", "CMD-R2-PY",
                    "--output", str(manifest_path),
                ]
            )
            self.assertEqual(invalid_status, 22)
            self.assertFalse(manifest_path.exists())
            write_relation_registry_conformance_artifact(
                PROJECT_ROOT / "tests" / "fixtures" / "knowledge_graph" / "query_kind_registry.jsonl",
                registry,
            )
            self.assertEqual(
                manifest(
                    [
                        "--source", str(source), "--fixture", str(fixture),
                        "--registry-artifact", str(registry), "--command-id", "CMD-R2-PY",
                        "--output", str(manifest_path),
                    ]
                ),
                0,
            )
            change_review = root / "change.md"
            logic_review = root / "logic.md"
            change_review.write_text("decision: approve\n", encoding="utf-8")
            logic_review.write_text("decision: approve\n", encoding="utf-8")
            self.assertEqual(
                closeout(
                    [
                        "--manifest", str(manifest_path), "--change-review", str(change_review),
                        "--logic-review", str(logic_review), "--output", str(closeout_path),
                    ]
                ),
                21,
            )
            self.assertFalse(closeout_path.exists())

    def test_r2_scope_closeout_rejects_review_aliases(self) -> None:
        """Two review roles must bind distinct paths, identities, and content."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.txt"
            fixture = root / "fixture.txt"
            registry = root / "registry.json"
            manifest_path = root / "scope.json"
            source.write_text("source\n", encoding="utf-8")
            fixture.write_text("fixture\n", encoding="utf-8")
            write_relation_registry_conformance_artifact(
                PROJECT_ROOT / "tests" / "fixtures" / "knowledge_graph" / "query_kind_registry.jsonl",
                registry,
            )
            self.assertEqual(
                manifest(
                    [
                        "--source", str(source), "--fixture", str(fixture),
                        "--registry-artifact", str(registry), "--command-id", "CMD-R2-PY",
                        "--output", str(manifest_path),
                    ]
                ),
                0,
            )
            manifest_id = _string_field(
                _parse_json_object(
                    manifest_path.read_text(encoding="utf-8"),
                    "scope manifest",
                ),
                "scope_manifest_id",
                "scope manifest",
            )
            change_review = root / "change.md"
            change_review.write_text(
                f"decision: approve\nbound_scope_manifest_id: {manifest_id}\n",
                encoding="utf-8",
            )
            resolved_alias = root / "resolved-alias.md"
            resolved_alias.symlink_to(change_review)
            identity_alias = root / "identity-alias.md"
            os.link(change_review, identity_alias)
            content_alias = root / "content-alias.md"
            content_alias.write_bytes(change_review.read_bytes())
            for name, logic_review in (
                ("same-path", change_review),
                ("same-resolved-path", resolved_alias),
                ("same-file-identity", identity_alias),
                ("same-content", content_alias),
            ):
                with self.subTest(name=name):
                    closeout_path = root / f"{name}-closeout.json"
                    self.assertEqual(
                        closeout(
                            [
                                "--manifest", str(manifest_path),
                                "--change-review", str(change_review),
                                "--logic-review", str(logic_review),
                                "--output", str(closeout_path),
                            ]
                        ),
                        21,
                    )
                    self.assertFalse(closeout_path.exists())

    def test_transport_conformance_fixture_executes_every_case(self) -> None:
        """The decoder executes every canonical and refreshed transport case."""
        self.assertTrue(
            RETAINED_NORMALIZED_RECORD_SET.is_file(),
            f"required retained decoder input missing: {RETAINED_NORMALIZED_RECORD_SET}",
        )
        fixture_cases = [
            _parse_json_object(line, f"transport fixture line {index}")
            for index, line in enumerate(
                TRANSPORT_CONFORMANCE.read_text(encoding="utf-8").splitlines(),
                1,
            )
        ]
        values = [
            _parse_json_object(line, f"retained normalized line {index}")
            for index, line in enumerate(
                RETAINED_NORMALIZED_RECORD_SET.read_text(encoding="utf-8").splitlines(),
                1,
            )
        ]
        expected_snapshot_id = _string_field(values[0], "record_id", "normalized header")

        def refresh_family_count(
            records: list[JsonObject],
            family: str,
        ) -> None:
            summary_payload = _object_field(
                records[-1], "payload", "normalization summary"
            )
            record_counts = _object_field(
                summary_payload,
                "record_counts",
                "normalization summary payload",
            )
            record_counts[family] = sum(
                _string_field(record, "record_type", "normalized record") == family
                for record in records
            )

        executed: set[str] = set()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            registry = _write_registry(root)
            for case in fixture_cases:
                name = _string_field(case, "case", "transport fixture")
                candidate = copy.deepcopy(values)
                if name == "r2-json-duplicate-key-preflight":
                    shared_mutations = _string_list_field(
                        case, "shared_mutations", name
                    )
                    self.assertEqual(
                        set(shared_mutations),
                        {
                            "registry_top_level",
                            "registry_nested",
                            "normalized_top_level",
                            "normalized_nested",
                            "normalized_escaped_equivalent",
                        },
                    )
                    self.assertEqual(
                        set(_string_list_field(case, "rust_only_mutations", name)),
                        {
                            "snapshot_top_level",
                            "snapshot_nested",
                            "evidence_top_level",
                            "evidence_nested",
                        },
                    )
                    canonical_normalized = _canonical_record_bytes(values)
                    for mutation in shared_mutations:
                        if mutation == "registry_top_level":
                            mutated = _duplicate_json_field(
                                registry.read_bytes(),
                                "registry_version",
                                "relation_registry.v1",
                            )
                            path = root / f"{name}-{mutation}.json"
                            path.write_bytes(mutated)
                            with self.assertRaisesRegex(
                                TransportInvalid, "duplicate JSON key"
                            ):
                                load_relation_registry_artifact(path)
                        elif mutation == "registry_nested":
                            mutated = _duplicate_json_field(
                                registry.read_bytes(),
                                "capability_id",
                                "catalog-route.v1",
                            )
                            path = root / f"{name}-{mutation}.json"
                            path.write_bytes(mutated)
                            with self.assertRaisesRegex(
                                TransportInvalid, "duplicate JSON key"
                            ):
                                load_relation_registry_artifact(path)
                        elif mutation == "normalized_top_level":
                            mutated = _duplicate_json_field(
                                canonical_normalized,
                                "record_type",
                                "normalized_record_set_header.v1",
                            )
                            path = root / f"{name}-{mutation}.jsonl"
                            path.write_bytes(mutated)
                            with self.assertRaisesRegex(
                                TransportInvalid, "duplicate JSON key"
                            ):
                                load_normalized_record_set(
                                    path,
                                    expected_root=PROJECT_ROOT.parent.parent,
                                    expected_snapshot_id=expected_snapshot_id,
                                    relation_registry_path=registry,
                                )
                        elif mutation == "normalized_nested":
                            mutated = _duplicate_json_field(
                                canonical_normalized,
                                "schema_version",
                                "normalized_record_set.v1",
                            )
                            path = root / f"{name}-{mutation}.jsonl"
                            path.write_bytes(mutated)
                            with self.assertRaisesRegex(
                                TransportInvalid, "duplicate JSON key"
                            ):
                                load_normalized_record_set(
                                    path,
                                    expected_root=PROJECT_ROOT.parent.parent,
                                    expected_snapshot_id=expected_snapshot_id,
                                    relation_registry_path=registry,
                                )
                        elif mutation == "normalized_escaped_equivalent":
                            mutated = _duplicate_json_field(
                                canonical_normalized,
                                "record_type",
                                "normalized_record_set_header.v1",
                            ).replace(
                                b'"record_type":',
                                b'"\\u0072ecord_type":',
                                1,
                            )
                            path = root / f"{name}-{mutation}.jsonl"
                            path.write_bytes(mutated)
                            with self.assertRaisesRegex(
                                TransportInvalid, "duplicate JSON key"
                            ):
                                load_normalized_record_set(
                                    path,
                                    expected_root=PROJECT_ROOT.parent.parent,
                                    expected_snapshot_id=expected_snapshot_id,
                                    relation_registry_path=registry,
                                )
                        else:
                            self.fail(f"unknown shared duplicate-key mutation: {mutation}")
                    executed.add(name)
                    continue
                if name == "r2-evidence-jsonl-raw-byte-gate":
                    canonical_normalized = _canonical_record_bytes(values)
                    for mutation in _string_list_field(case, "mutations", name):
                        if mutation == "bom":
                            mutated = b"\xef\xbb\xbf" + canonical_normalized
                        elif mutation == "crlf":
                            mutated = canonical_normalized.replace(b"\n", b"\r\n", 1)
                        elif mutation == "missing_final_lf":
                            mutated = canonical_normalized[:-1]
                        elif mutation == "noncanonical_key_order":
                            mutated = _noncanonical_first_envelope(canonical_normalized)
                        else:
                            self.fail(f"unknown JSONL byte-gate mutation: {mutation}")
                        path = root / f"{name}-{mutation}.jsonl"
                        path.write_bytes(mutated)
                        with self.assertRaises(TransportInvalid):
                            load_normalized_record_set(
                                path,
                                expected_root=PROJECT_ROOT.parent.parent,
                                expected_snapshot_id=expected_snapshot_id,
                                relation_registry_path=registry,
                            )
                    executed.add(name)
                    continue
                if name == "r2-reader-global-locator-namespace":
                    for mutation in _string_list_field(case, "mutations", name):
                        mutation_candidate = copy.deepcopy(values)
                        identity_records = [
                            record
                            for record in mutation_candidate
                            if _string_field(record, "record_type", "normalized record")
                            == "source_identity.v1"
                        ]
                        self.assertGreaterEqual(len(identity_records), 2)
                        if mutation == "path_vs_canonical":
                            path_record = next(
                                record
                                for record in identity_records
                                if _string_field(
                                    _object_field(record, "payload", name),
                                    "repo_rel_path",
                                    name,
                                )
                                != _string_field(
                                    _object_field(record, "payload", name),
                                    "canonical_locator",
                                    name,
                                )
                            )
                            path_payload = _object_field(path_record, "payload", name)
                            path_locator = _string_field(
                                path_payload, "repo_rel_path", name
                            )
                            collision_record = next(
                                record for record in identity_records if record is not path_record
                            )
                            collision_payload = _object_field(
                                collision_record, "payload", name
                            )
                            collision_payload["canonical_locator"] = path_locator
                            snapshot_record = next(
                                record
                                for record in mutation_candidate
                                if _string_field(
                                    record, "record_type", "normalized record"
                                )
                                == "source_snapshot.v1"
                            )
                            parent_repo_id = _string_field(
                                _object_field(snapshot_record, "payload", name),
                                "parent_repo_id",
                                name,
                            )
                            collision_payload["logical_id"] = _hash_parts(
                                "logical_source.v1", parent_repo_id, path_locator
                            )
                        elif mutation == "alternate_vs_alternate":
                            shared_locator = "alternate://shared-collision"
                            for record in identity_records[:2]:
                                _object_field(record, "payload", name)[
                                    "alternate_locators"
                                ] = [shared_locator]
                        else:
                            self.fail(f"unknown locator namespace mutation: {mutation}")
                        summary_payload = _object_field(
                            mutation_candidate[-1], "payload", "normalization summary"
                        )
                        summary_payload["normalized_record_fingerprint"] = (
                            _refreshed_normalized_fingerprint(mutation_candidate)
                        )
                        path = root / f"{name}-{mutation}.jsonl"
                        path.write_bytes(_canonical_record_bytes(mutation_candidate))
                        with self.assertRaisesRegex(
                            TransportInvalid,
                            "source identity locator namespace collision",
                        ):
                            load_normalized_record_set(
                                path,
                                expected_root=PROJECT_ROOT.parent.parent,
                                expected_snapshot_id=expected_snapshot_id,
                                relation_registry_path=registry,
                            )
                    self.assertEqual(
                        _string_field(case, "producer_mutation", name),
                        "tracked_symlink_and_target",
                    )
                    self.assertEqual(
                        set(_string_list_field(case, "rust_preflight_mutations", name)),
                        {
                            "duplicate_identity_id",
                            "duplicate_repo_path",
                            "duplicate_canonical_locator",
                            "duplicate_logical_id",
                        },
                    )
                    executed.add(name)
                    continue
                if name == "r2-reader-same-family-reorder":
                    family = _string_field(case, "family", name)
                    positions = [
                        index
                        for index, record in enumerate(candidate)
                        if _string_field(record, "record_type", "normalized record") == family
                    ][:2]
                    self.assertEqual(len(positions), 2)
                    candidate[positions[0]], candidate[positions[1]] = (
                        candidate[positions[1]], candidate[positions[0]]
                    )
                elif name == "r2-reader-refreshed-fingerprint":
                    summary_payload = _object_field(
                        candidate[-1], "payload", "normalization summary"
                    )
                    record_counts = _object_field(
                        summary_payload,
                        "record_counts",
                        "normalization summary payload",
                    )
                    record_counts["source_identity.v1"] = _int_field(
                        record_counts,
                        "source_identity.v1",
                        "normalization summary record counts",
                    ) + 1
                elif name == "r2-reader-cross-family-snapshot-refresh":
                    family = _string_field(case, "family", name)
                    snapshot_field = _string_field(case, "snapshot_field", name)
                    family_record = next(
                        record
                        for record in candidate
                        if _string_field(record, "record_type", "normalized record") == family
                    )
                    family_payload = _object_field(family_record, "payload", family)
                    family_payload[snapshot_field] = "f" * 64
                    refresh_family_count(candidate, family)
                elif name == "r2-reader-registry-kind-authority":
                    relation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "normalized_relation.v1"
                    )
                    _object_field(relation, "payload", name)["relation_kind"] = "unregistered_kind"
                elif name == "r2-reader-source-universe-endpoint":
                    relation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "normalized_relation.v1"
                    )
                    _object_field(relation, "payload", name)["from_identity_id"] = "0" * 64
                elif name == "r2-reader-identity-id-derivation":
                    identity = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "source_identity.v1"
                    )
                    identity["record_id"] = "0" * 64
                    _object_field(identity, "payload", name)["identity_id"] = "0" * 64
                elif name == "r2-reader-source-identity-uniqueness":
                    for mutation in _string_list_field(case, "mutations", name):
                        if mutation == "duplicate_canonical_locator":
                            field = "canonical_locator"
                            expected = "duplicate source identity canonical locator"
                        elif mutation == "duplicate_logical_id":
                            field = "logical_id"
                            expected = "duplicate source identity logical ID"
                        else:
                            self.fail(f"unknown source identity mutation: {mutation}")
                        mutation_candidate = copy.deepcopy(values)
                        identities = [
                            record
                            for record in mutation_candidate
                            if _string_field(record, "record_type", "normalized record")
                            == "source_identity.v1"
                        ][:2]
                        self.assertEqual(len(identities), 2)
                        first_payload = _object_field(identities[0], "payload", name)
                        second_payload = _object_field(identities[1], "payload", name)
                        second_payload[field] = _string_field(first_payload, field, name)
                        summary_payload = _object_field(
                            mutation_candidate[-1], "payload", "normalization summary"
                        )
                        summary_payload["normalized_record_fingerprint"] = (
                            _refreshed_normalized_fingerprint(mutation_candidate)
                        )
                        path = root / f"{name}-{mutation}.jsonl"
                        path.write_bytes(_canonical_record_bytes(mutation_candidate))
                        with self.assertRaisesRegex(TransportInvalid, expected):
                            load_normalized_record_set(
                                path,
                                expected_root=PROJECT_ROOT.parent.parent,
                                expected_snapshot_id=expected_snapshot_id,
                                relation_registry_path=registry,
                            )
                    executed.add(name)
                    continue
                elif name == "r2-reader-fact-id-derivation":
                    relation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "normalized_relation.v1"
                    )
                    relation["record_id"] = "0" * 64
                    _object_field(relation, "payload", name)["fact_id"] = "0" * 64
                elif name == "r2-reader-pair-id-derivation":
                    relation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "normalized_relation.v1"
                    )
                    _object_field(relation, "payload", name)["pair_identity"] = "0" * 64
                elif name == "r2-reader-attestation-membership":
                    relation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "normalized_relation.v1"
                    )
                    _object_field(relation, "payload", name)["attestation_ids"] = []
                elif name == "r2-reader-attestation-endpoint":
                    relation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "normalized_relation.v1"
                    )
                    relation_payload = _object_field(relation, "payload", name)
                    attestation_id = _string_list_field(
                        relation_payload, "attestation_ids", name
                    )[0]
                    attestation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "attestation.v1"
                        and _string_field(record, "record_id", "attestation") == attestation_id
                    )
                    _object_field(attestation, "payload", name)["dependent_identity_id"] = "0" * 64
                elif name == "r2-reader-observation-membership":
                    relation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "normalized_relation.v1"
                    )
                    _object_field(relation, "payload", name)["observation_ids"] = [
                        f"O-{'0' * 64}"
                    ]
                elif name == "r2-reader-reconciliation-partition":
                    relation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "normalized_relation.v1"
                    )
                    relation_payload = _object_field(relation, "payload", name)
                    relation_payload["reconciliation_status"] = "matched"
                    relation_payload["authority"] = "declaration+observation"
                    summary_payload = _object_field(
                        candidate[-1], "payload", "normalization summary"
                    )
                    counts = _object_field(
                        summary_payload, "record_counts", "normalization summary"
                    )
                    counts["matched_count"] = _int_field(
                        counts, "matched_count", "normalization counts"
                    ) + 1
                    counts["declared_only_count"] = _int_field(
                        counts, "declared_only_count", "normalization counts"
                    ) - 1
                elif name == "r2-reader-source-content-provenance":
                    relation = next(
                        record for record in candidate
                        if _string_field(record, "record_type", "normalized record")
                        == "normalized_relation.v1"
                    )
                    source_hashes = _string_list_field(
                        _object_field(relation, "payload", name),
                        "source_content_hashes",
                        name,
                    )
                    source_hashes[0] = "f" * 64
                elif name != "r2-transport-canonical-envelope-order":
                    self.fail(f"unknown transport fixture case: {name}")
                if case.get("refresh_normalized_record_fingerprint") is True:
                    summary_payload = _object_field(
                        candidate[-1], "payload", "normalization summary"
                    )
                    summary_payload["normalized_record_fingerprint"] = (
                        _refreshed_normalized_fingerprint(candidate)
                    )
                path = root / f"{name}.jsonl"
                path.write_bytes(_canonical_record_bytes(candidate))
                if _string_field(case, "expected", name) == "accept":
                    load_normalized_record_set(
                        path,
                        expected_root=PROJECT_ROOT.parent.parent,
                        expected_snapshot_id=expected_snapshot_id,
                        relation_registry_path=registry,
                    )
                else:
                    with self.assertRaises(TransportInvalid):
                        load_normalized_record_set(
                            path,
                            expected_root=PROJECT_ROOT.parent.parent,
                            expected_snapshot_id=expected_snapshot_id,
                            relation_registry_path=registry,
                        )
                executed.add(name)
        self.assertEqual(
            executed,
            {_string_field(case, "case", "transport fixture") for case in fixture_cases},
        )

    def test_synthetic_missing_source_identity_is_narrow_and_source_first(self) -> None:
        """Python accepts only Rust's derived missing source before endpoint diagnosis."""
        relation_case = next(
            _parse_json_object(line, "declaration endpoint fixture")
            for line in RELATION_RECONCILIATION.read_text(encoding="utf-8").splitlines()
            if _string_field(
                _parse_json_object(line, "relation fixture"),
                "case",
                "relation fixture",
            )
            == "r2-declaration-endpoint-u-adversaries"
        )
        self.assertEqual(
            _string_list_field(relation_case, "cases", "declaration endpoint fixture"),
            ["excluded-source", "stale-source", "nonexistent-source"],
        )
        self.assertEqual(
            _string_list_field(
                relation_case, "expected_rejection", "declaration endpoint fixture"
            ),
            ["source_excluded_source", "stale_source", "unresolved_source"],
        )

        values = [
            _parse_json_object(line, f"retained normalized line {index}")
            for index, line in enumerate(
                RETAINED_NORMALIZED_RECORD_SET.read_text(encoding="utf-8").splitlines(),
                1,
            )
        ]

        def family_payloads(family: str) -> list[JsonObject]:
            return [
                copy.deepcopy(_object_field(record, "payload", family))
                for record in values
                if _string_field(record, "record_type", "normalized record") == family
            ]

        normalized_header = _object_field(values[0], "payload", "normalized header")
        snapshot_header = family_payloads("source_snapshot.v1")[0]
        snapshot_header["source_fingerprint"] = _string_field(
            normalized_header, "source_fingerprint", "normalized header"
        )
        snapshot_header["profile"] = _string_field(
            normalized_header, "profile", "normalized header"
        )
        identities = family_payloads("source_identity.v1")
        declarations = family_payloads("dependency_declaration.v1")
        surface_relations = family_payloads("surface_relation.v1")
        exclusions = family_payloads("source_exclusion.v1")
        identity_ids = {
            _string_field(identity, "identity_id", "source identity")
            for identity in identities
        }
        declaration = next(
            item
            for item in declarations
            if item["resolved_target_identity_id"] in identity_ids
        )
        source_span = _object_field(
            declaration, "source_span", "dependency declaration"
        )
        missing_path = "synthetic-missing-source.txt"
        source_span["path"] = missing_path
        parent_repo_id = _string_field(
            snapshot_header, "parent_repo_id", "source snapshot"
        )
        synthetic_source_id = _hash_parts(
            "source_identity.v1", parent_repo_id, missing_path
        )
        declaration["source_identity_id"] = synthetic_source_id
        start_line = str(_int_field(source_span, "start_line", "source span"))
        end_line = str(_int_field(source_span, "end_line", "source span"))
        direction = _string_field(
            declaration, "declared_direction", "dependency declaration"
        )
        kind = _string_field(declaration, "declared_kind", "dependency declaration")
        target = _string_field(
            declaration, "declared_target", "dependency declaration"
        )
        raw_line_hash = _string_field(
            declaration, "raw_line_hash", "dependency declaration"
        )
        snapshot_id = _string_field(snapshot_header, "snapshot_id", "source snapshot")
        declaration["declaration_id"] = _hash_parts(
            "dependency_declaration.v1",
            synthetic_source_id,
            start_line,
            end_line,
            direction,
            kind,
            target,
            raw_line_hash,
        )
        declaration["attestation_key"] = _hash_parts(
            "dependency_attestation.v1",
            snapshot_id,
            synthetic_source_id,
            start_line,
            end_line,
            direction,
            kind,
            target,
            raw_line_hash,
        )

        identities_by_id, excluded_ids, _ = (
            VALIDATE_SNAPSHOT_DERIVATIONS(
                snapshot_header,
                tuple(identities),
                tuple(declarations),
                tuple(surface_relations),
                tuple(exclusions),
            )
        )
        _, _, reason = DECLARATION_ENDPOINTS(
            declaration, identities_by_id, excluded_ids
        )
        self.assertEqual(reason, "unresolved_source")

        unknown_target_declarations = copy.deepcopy(declarations)
        unknown_target_declarations[declarations.index(declaration)][
            "resolved_target_identity_id"
        ] = "f" * 64
        with self.assertRaisesRegex(
            TransportInvalid, "dependency declaration target identity is unknown"
        ):
            VALIDATE_SNAPSHOT_DERIVATIONS(
                snapshot_header,
                tuple(identities),
                tuple(unknown_target_declarations),
                tuple(surface_relations),
                tuple(exclusions),
            )

        wrong_source_declarations = copy.deepcopy(declarations)
        wrong_source_declarations[declarations.index(declaration)][
            "source_identity_id"
        ] = "0" * 64
        with self.assertRaisesRegex(
            TransportInvalid, "dependency declaration source identity/path mismatch"
        ):
            VALIDATE_SNAPSHOT_DERIVATIONS(
                snapshot_header,
                tuple(identities),
                tuple(wrong_source_declarations),
                tuple(surface_relations),
                tuple(exclusions),
            )

    def test_normalized_decoder_rejects_noncanonical_transport(self) -> None:
        """The decoder rejects a whitespace mutation before projection."""
        self.assertTrue(RETAINED_NORMALIZED_RECORD_SET.is_file())
        raw_lines = RETAINED_NORMALIZED_RECORD_SET.read_bytes().splitlines(keepends=True)
        mutated = raw_lines[0].replace(b"{", b"{ ", 1)
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "mutated.jsonl"
            path.write_bytes(mutated + b"".join(raw_lines[1:]))
            first = _parse_json_object(raw_lines[0], "normalized header")
            with self.assertRaises(TransportInvalid):
                load_normalized_record_set(
                    path,
                    expected_root=PROJECT_ROOT.parent.parent,
                    expected_snapshot_id=_string_field(
                        first, "record_id", "normalized header"
                    ),
                    relation_registry_path=RETAINED_RELATION_REGISTRY,
                )

    def test_scan_reports_missing_manifest(self) -> None:
        """The scan tool reports missing markers and can fail on request."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "doc.md"
            doc.write_text("# Doc\n\nBody.\n", encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(doc),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MISSING_DEPENDENCY_MANIFEST=doc.md", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN=fail", result.stdout)

    def test_scan_reports_display_path_and_real_source_path(self) -> None:
        """Missing-header findings should include review path and real source path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "doc.md"
            doc.write_text("# Doc\n\nBody.\n", encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                str(doc),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("MISSING_DEPENDENCY_MANIFEST=doc.md", result.stdout)
            self.assertIn("realpath=doc.md", result.stdout)
            self.assertIn("owner=product_file", result.stdout)

    def test_scan_accepts_large_file_with_manifest_markers_near_top(self) -> None:
        """Early marker matches in large files must not trip pipefail/SIGPIPE."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "large.md"
            doc.write_text(
                "\n".join(
                    [
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises large-file dependency header scanning.",
                        "upstream design README.md repo overview",
                        "@dependency-end",
                        "-->",
                        "",
                        *("x" * 4096 for _ in range(120)),
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(doc),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", result.stdout)

    def test_repo_review_output_is_stable_across_repeated_runs(self) -> None:
        """Strict repo dependency review should be stable across repeated runs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target fixture for stable review.",
                        "downstream design source.md source consumes target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source fixture for stable review.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            first = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                root=root,
            )
            second = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                root=root,
            )

            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", first.stdout)

    def test_repo_review_default_root_uses_current_worktree(self) -> None:
        """Default root should be cwd, not the symlinked tool source repository."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.parent.mkdir(parents=True)
            tool_dir.symlink_to(PROJECT_ROOT / "tools" / "agent_tools")
            target = root / "target.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines cwd-root dependency fixture.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "\n".join(
                    [
                        "# Readme",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines readme fixture.",
                        "downstream design target.md target fixture",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "README.md", "target.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                ["bash", str(REPO_REVIEW), "--fail-missing"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPO_DEPENDENCY_REVIEW_PATHS=2", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_can_run_design_claim_checker_for_explicit_path(self) -> None:
        """The dependency review wrapper can invoke design claim evidence checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "check_design_doc_claims.py").symlink_to(DESIGN_CLAIMS)
            design = root / "documents" / "design" / "feature.md"
            implementation = root / "tools" / "feature_runner.py"
            design.parent.mkdir(parents=True)
            implementation.parent.mkdir(parents=True, exist_ok=True)
            design.write_text(
                "\n".join(
                    [
                        "# Feature",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Documents feature fixture.",
                        "downstream implementation ../../tools/feature_runner.py runner",
                        "@dependency-end",
                        "-->",
                        "",
                        "## Evidence And Assumption Ledger",
                        "",
                        "- Evidence sources: `tools/feature_runner.py`.",
                        "- Assumptions: direct implementation evidence.",
                        "",
                        "## Claims",
                        "",
                        "- The design must use `run_feature`.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            implementation.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Implements feature fixture.",
                        "# upstream design ../documents/design/feature.md feature design",
                        "# @dependency-end",
                        "",
                        "def run_feature() -> None:",
                        "    pass",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "documents/design/feature.md", "tools/feature_runner.py"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--check-design-doc-claims",
                "--design-doc-claim-path",
                "documents/design/feature.md",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_design_claim_checker_defaults_to_changed_design_docs(self) -> None:
        """Wrapper claim checks stay migration-safe for legacy design backlog."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "check_design_doc_claims.py").symlink_to(DESIGN_CLAIMS)
            readme = root / "README.md"
            legacy = root / "documents" / "design" / "legacy.md"
            legacy.parent.mkdir(parents=True)
            readme.write_text(
                "\n".join(
                    [
                        "# Readme",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines fixture readme.",
                        "downstream design documents/design/legacy.md legacy design",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            legacy.write_text(
                "\n".join(
                    [
                        "# Legacy",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Documents legacy design fixture.",
                        "upstream design ../../README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                        "## Claims",
                        "",
                        "- The legacy design must preserve behavior.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "README.md", "documents/design/legacy.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.email=test@example.com",
                    "-c",
                    "user.name=Test User",
                    "commit",
                    "-m",
                    "baseline",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            design = root / "documents" / "design" / "feature.md"
            implementation = root / "tools" / "feature_runner.py"
            design.write_text(
                "\n".join(
                    [
                        "# Feature",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Documents feature fixture.",
                        "downstream implementation ../../tools/feature_runner.py runner",
                        "@dependency-end",
                        "-->",
                        "",
                        "## Evidence And Assumption Ledger",
                        "",
                        "- Evidence sources: `tools/feature_runner.py`.",
                        "- Assumptions: direct implementation evidence.",
                        "",
                        "## Claims",
                        "",
                        "- The design must use `run_feature`.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            implementation.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Implements feature fixture.",
                        "# upstream design ../documents/design/feature.md feature design",
                        "# @dependency-end",
                        "",
                        "def run_feature() -> None:",
                        "    pass",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "documents/design/feature.md", "tools/feature_runner.py"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--check-design-doc-claims",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DESIGN_DOC_CLAIMS=pass", result.stdout)
            self.assertIn("DESIGN_DOC_CLAIMS_CHECKED=1", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_code_scan_extracts_python_import_edges(self) -> None:
        """The code dependency scanner resolves local Python imports."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            package = root / "pkg"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            source = package / "consumer.py"
            source.write_text("from . import module\n", encoding="utf-8")

            result = run_tool(
                str(CODE_SCAN),
                "--root",
                str(root),
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "CODE_DEPENDENCY\tpython\tfrom-import-symbol\tpkg/consumer.py\tpkg/module.py\t.module",
                result.stdout,
            )
            self.assertIn("CODE_DEPENDENCY_SCAN=pass files=1", result.stdout)

    def test_code_scan_extracts_c_family_local_includes(self) -> None:
        """The code dependency scanner resolves local C/C++ includes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            include = root / "include"
            include.mkdir()
            header = include / "api.hpp"
            source = root / "main.cpp"
            header.write_text("#pragma once\n", encoding="utf-8")
            source.write_text('#include "include/api.hpp"\n', encoding="utf-8")

            result = run_tool(
                str(CODE_SCAN),
                "--root",
                str(root),
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "CODE_DEPENDENCY\tc-family\tinclude\tmain.cpp\tinclude/api.hpp\tinclude/api.hpp",
                result.stdout,
            )

    def test_requirement_sync_reports_pyproject_docker_summary(self) -> None:
        """The Python dependency validator reports pyproject/docker ownership summary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "python").mkdir()
            (root / "docker").mkdir()
            (root / "pyproject.toml").write_text(
                "\n".join(
                    [
                        "[project]",
                        "dependencies = [\"requests>=2\"]",
                        "[project.optional-dependencies]",
                        "dev = [\"pytest>=8\"]",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "docker" / "requirements.txt").write_text(
                "requests>=2\npytest>=8\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(REQUIREMENT_SYNC)],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PYPROJECT_DOCKER_DEPENDENCY_SUMMARY=pass", result.stdout)
            self.assertIn("PYPROJECT_RUNTIME_DEPENDENCIES=1", result.stdout)
            self.assertIn("PYPROJECT_DOCKER_RUNTIME_MISSING=0", result.stdout)

    def test_requirement_sync_fails_when_runtime_dependency_missing_from_docker(self) -> None:
        """Runtime package declarations in pyproject must be present in docker requirements."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "python").mkdir()
            (root / "docker").mkdir()
            (root / "pyproject.toml").write_text(
                "[project]\ndependencies = [\"requests>=2\"]\n",
                encoding="utf-8",
            )
            (root / "docker" / "requirements.txt").write_text("", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(REQUIREMENT_SYNC)],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PYPROJECT_DOCKER_DEPENDENCY_SUMMARY=fail", result.stdout)
            self.assertIn(
                "pyproject project dependency 'requests' missing from docker/requirements.txt",
                result.stdout,
            )

    def test_docker_validator_accepts_requirement_extras_for_required_packages(self) -> None:
        """The Docker validator should accept valid extras syntax in requirements."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "python").mkdir()
            (root / "docker").mkdir()
            (root / ".devcontainer").mkdir()
            (root / "tools" / "ci").mkdir(parents=True)
            (root / "pyproject.toml").write_text(
                "[project]\ndependencies = []\n",
                encoding="utf-8",
            )
            (root / "docker" / "requirements.txt").write_text(
                "\n".join(
                    [
                        "jupyterlab",
                        "notebook",
                        "ipykernel",
                        "pydeps",
                        "snakeviz",
                        "pyyaml[secure]>=6",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "docker" / "Dockerfile").write_text(
                "RUN apt-get update && apt-get install -y rsync openssh-client graphviz python3.11-venv\n",
                encoding="utf-8",
            )
            (root / "docker" / "install_python_dependencies.sh").write_text(
                "\n".join(
                    [
                        "python3 -m pip install --no-cache-dir -r docker/requirements.txt",
                        "sha256sum docker/requirements.txt",
                        "python3 -m pip check",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / ".devcontainer" / "post-create.sh").write_text(
                "\n".join(
                    [
                        "run_as_root",
                        "docker/register_safe_directories.sh",
                        "docker/install_python_dependencies.sh",
                        'git config --global --add safe.directory "$workspace"',
                        "repo-local Python dependency installer absent",
                        "cli.github.com/packages",
                        "apt_install gh",
                        "npm install -g @openai/codex",
                        "gh --version",
                        "codex --version",
                        "rustup toolchain install",
                        "rustfmt",
                        "clippy",
                        "rust-analyzer",
                        "cargo build --release",
                        "AGENT_CANON_TOOLS_HOME",
                        "${tools_home}/agent-canon/bin/agent-canon",
                        "/usr/local/bin/agent-canon",
                        "install_llama_cpp",
                        "tools/install_llama_cpp.sh",
                        "ggml-org/SmolLM3-3B-GGUF:Q4_K_M",
                        "${tools_home}/bin/llama-cli",
                        "/etc/profile.d/agent-canon-rust.sh",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / ".devcontainer" / "devcontainer.json").write_text(
                '{"postCreateCommand": "bash .devcontainer/post-create.sh /workspace"}\n',
                encoding="utf-8",
            )
            (root / ".dockerignore").write_text(
                "vendor/agent-canon\n.git\n.state\n*.gguf\n",
                encoding="utf-8",
            )
            (root / ".gitignore").write_text(".venv/\nvenv/\n", encoding="utf-8")
            (root / "README.md").write_text(
                "PYTHONPATH=/workspace/python\nUse docker run for execution.\n",
                encoding="utf-8",
            )
            (root / "tools" / "install_llama_cpp.sh").write_text(
                "ggml-org/llama.cpp\ncmake --build\n",
                encoding="utf-8",
            )
            (root / "tools" / "ci" / "python_env_policy.py").write_text(
                "# env policy fixture\n",
                encoding="utf-8",
            )
            (root / "tools" / "requirement_sync_validator.py").symlink_to(
                REQUIREMENT_SYNC
            )

            result = subprocess.run(
                ["bash", str(DOCKER_VALIDATOR)],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("result-log / visualization requirements present", result.stdout)
            self.assertIn("Summary: 0 issues found", result.stdout)

    def test_format_accepts_line_comment_manifest(self) -> None:
        """Line-comment manifests are valid for Python-like files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.py"
            source = root / "source.py"
            target.write_text("# target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises a valid line-comment manifest.",
                        "# upstream implementation target.py target contract",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_accepts_markdown_h1_before_manifest(self) -> None:
        """Markdown H1 titles may precede the dependency manifest near the top."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text("# Target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source Title",
                        "",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises H1 before manifest parsing.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_accepts_coverage_rule_manifest_lines(self) -> None:
        """Coverage-rule manifest lines are valid non-edge dependency metadata."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "source.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises coverage-rule metadata in dependency manifests.",
                        "upstream design README.md readme context",
                        "coverage graph_trace requires node record|edge record",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_accepts_registered_contract_kind(self) -> None:
        """Format validation accepts registry-backed manifest metadata."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "source.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract design",
                        "responsibility Exercises registered contract kind metadata.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_rejects_missing_contract_kind(self) -> None:
        """Format validation rejects manifests without contract metadata."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "source.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "responsibility Exercises missing contract kind metadata.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                str(source),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one contract line", result.stdout)
            self.assertIn("fix: add 'contract <registered-kind>'", result.stdout)
            self.assertIn("documents/dependency-contract-kinds.toml", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=fail", result.stdout)

    def test_format_rejects_unregistered_contract_kind(self) -> None:
        """Format validation keeps contract kinds in the registry."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "source.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract invented-kind",
                        "responsibility Exercises unregistered contract kind metadata.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                str(source),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unregistered contract kind", result.stdout)
            self.assertIn("fix: use an existing allowed_kinds entry", result.stdout)
            self.assertIn("documents/dependency-contract-kinds.toml", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=fail", result.stdout)

    def test_format_accepts_skill_frontmatter_before_html_manifest(self) -> None:
        """YAML frontmatter may precede an HTML-comment dependency manifest."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "SKILL.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "---",
                        "name: demo",
                        "description: Demo skill.",
                        "---",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises skill frontmatter manifest parsing.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_scan_and_format_accept_shell_and_toml_line_comments(self) -> None:
        """Shell and TOML files can use line-comment dependency manifests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.md"
            shell = root / "script.sh"
            toml = root / "config.toml"
            target.write_text("# Target\n", encoding="utf-8")
            shell.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises shell manifest parsing.",
                        "# upstream design target.md target context",
                        "# @dependency-end",
                        "set -euo pipefail",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            toml.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises TOML manifest parsing.",
                        "# upstream design target.md target context",
                        "# @dependency-end",
                        "[tool.demo]",
                        'enabled = true',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            scan = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(shell),
                str(toml),
                root=root,
            )
            fmt = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(shell),
                str(toml),
                root=root,
            )

            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", fmt.stdout)

    def test_allow_frontmatter_flag_is_accepted_by_manifest_tools(self) -> None:
        """Manifest tools accept an explicit frontmatter policy flag."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            readme = root / "README.md"
            source = root / "SKILL.md"
            readme.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "---",
                        "name: demo",
                        "description: Demo skill.",
                        "---",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Exercises explicit frontmatter allowance.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            scan = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--allow-frontmatter",
                str(source),
                root=root,
            )
            fmt = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                "--allow-frontmatter",
                str(source),
                root=root,
            )
            graph = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--allow-frontmatter",
                str(source),
                root=root,
            )

            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
            self.assertEqual(graph.returncode, 0, graph.stdout + graph.stderr)

    def test_scan_groups_missing_manifests_by_owner_and_explains(self) -> None:
        """Missing manifest output includes owner grouping and first-lines evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            product = root / "product.md"
            root_view = root / ".github" / "workflows" / "agent-coordination.yml"
            submodule = root / "vendor" / "agent-canon" / "shared.md"
            root_view.parent.mkdir(parents=True)
            submodule.parent.mkdir(parents=True)
            product.write_text("# Product\n\nBody.\n", encoding="utf-8")
            root_view.write_text("name: Agent Coordination\n", encoding="utf-8")
            submodule.write_text("# Shared\n\nBody.\n", encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                "--explain-missing",
                str(product),
                str(root_view),
                str(submodule),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "MISSING_DEPENDENCY_MANIFEST=product.md owner=product_file",
                result.stdout,
            )
            self.assertIn(
                "MISSING_DEPENDENCY_MANIFEST=.github/workflows/"
                "agent-coordination.yml owner=root_view",
                result.stdout,
            )
            self.assertIn(
                "MISSING_DEPENDENCY_MANIFEST=vendor/agent-canon/shared.md owner=submodule_source",
                result.stdout,
            )
            self.assertIn(
                "DEPENDENCY_HEADER_SCAN_MISSING_BY_OWNER product_file=1 root_view=1 "
                "symlink=0 submodule_source=1 other=0",
                result.stdout,
            )
            self.assertIn("MISSING_DEPENDENCY_EXPLANATION_BEGIN=product.md", result.stdout)
            self.assertIn(
                "missing_start_and_end_markers_in_first_80_lines",
                result.stdout,
            )

    def test_graph_distinguishes_root_symlink_from_vendor_source(self) -> None:
        """Graph extraction should report the real vendor source, not the root symlink."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vendor = root / "vendor" / "agent-canon"
            vendor.mkdir(parents=True)
            source = vendor / "ROOT_AGENTS.md"
            target = vendor / "README.md"
            target.write_text("# Readme\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# Root Agents",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines the vendor source for root agent instructions.",
                        "upstream design README.md readme context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            os.symlink("vendor/agent-canon/ROOT_AGENTS.md", root / "AGENTS.md")

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--print-edges",
                str(root / "AGENTS.md"),
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "upstream\tdesign\tvendor/agent-canon/ROOT_AGENTS.md\tvendor/agent-canon/README.md",
                result.stdout,
            )
            self.assertNotIn("upstream\tdesign\tAGENTS.md\t", result.stdout)

    def test_root_copy_headers_resolve_in_agentcanon_source_context(self) -> None:
        """Root-copy GitHub headers should keep valid AgentCanon-source paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            root_copy = root / ".github" / "PULL_REQUEST_TEMPLATE" / "agent_canon.md"
            source_copy = (
                root
                / "vendor"
                / "agent-canon"
                / ".github"
                / "PULL_REQUEST_TEMPLATE"
                / "agent_canon.md"
            )
            issue_readme = root / "vendor" / "agent-canon" / "issues" / "README.md"
            root_copy.parent.mkdir(parents=True)
            source_copy.parent.mkdir(parents=True)
            issue_readme.parent.mkdir(parents=True)
            issue_readme.write_text("# Issues\n", encoding="utf-8")
            content = "\n".join(
                [
                    "<!--",
                    "@dependency-start",
                    "contract test",
                    "responsibility Defines a template AgentCanon PR checklist copy.",
                    "upstream design ../../issues/README.md durable issue storage",
                    "@dependency-end",
                    "-->",
                    "",
                ]
            )
            root_copy.write_text(content, encoding="utf-8")
            source_copy.write_text(content, encoding="utf-8")

            format_result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                str(root_copy),
                root=root,
            )
            graph_result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--print-edges",
                str(root_copy),
                root=root,
            )

            self.assertEqual(
                format_result.returncode,
                0,
                format_result.stdout + format_result.stderr,
            )
            self.assertEqual(
                graph_result.returncode,
                0,
                graph_result.stdout + graph_result.stderr,
            )
            self.assertIn(
                "upstream\tdesign\t.github/PULL_REQUEST_TEMPLATE/agent_canon.md\t"
                "vendor/agent-canon/issues/README.md",
                graph_result.stdout,
            )
            self.assertNotIn("\tissues/README.md", graph_result.stdout)

    def test_graph_lists_related_dependency_surfaces_for_focus_path(self) -> None:
        """Focused graph output should list declared and incoming dependency edges."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.py"
            dependent = root / "tests" / "test_source.py"
            design = root / "design.md"
            dependent.parent.mkdir(parents=True)
            design.write_text("# Design\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises focused dependency graph listing.",
                        "# upstream design design.md source design",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            dependent.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Tests focused dependency graph listing.",
                        "# upstream implementation ../source.py source behavior",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--list-related",
                "--focus",
                "source.py",
                "source.py",
                "tests/test_source.py",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_RELATED_SURFACE=source.py", result.stdout)
            self.assertIn(
                "DEPENDENCY_RELATED_EDGE role=declared_upstream "
                "kind=design source=source.py target=design.md",
                result.stdout,
            )
            self.assertIn(
                "DEPENDENCY_RELATED_EDGE role=incoming_upstream "
                "kind=implementation source=tests/test_source.py target=source.py",
                result.stdout,
            )
            self.assertIn("DEPENDENCY_RELATED_SURFACES=1", result.stdout)

    def test_graph_writes_machine_readable_tsv_artifact(self) -> None:
        """Graph checks can emit a stable TSV artifact for issue and PR evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.py"
            dependent = root / "tests" / "test_source.py"
            design = root / "design.md"
            graph_tsv = root / "reports" / "dependency_graph.tsv"
            dependent.parent.mkdir(parents=True)
            design.write_text("# Design\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises TSV dependency graph output.",
                        "# upstream design design.md source design",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            dependent.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Tests TSV dependency graph output.",
                        "# upstream implementation ../source.py source behavior",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--graph-tsv",
                str(graph_tsv),
                "source.py",
                "tests/test_source.py",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(f"DEPENDENCY_GRAPH_TSV={graph_tsv}", result.stdout)
            self.assertEqual(
                graph_tsv.read_text(encoding="utf-8").splitlines(),
                [
                    "direction\tkind\tsource\ttarget",
                    "upstream\tdesign\tsource.py\tdesign.md",
                    "upstream\timplementation\ttests/test_source.py\tsource.py",
                ],
            )

    def test_graph_expands_search_hits_to_edit_scope(self) -> None:
        """Search hit files should expand to declared and incoming dependency scope."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.py"
            dependent = root / "tests" / "test_source.py"
            design = root / "design.md"
            hits = root / "search_hits.txt"
            dependent.parent.mkdir(parents=True)
            design.write_text("# Design\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises search edit-scope expansion.",
                        "# upstream design design.md source design",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            dependent.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Tests search edit-scope expansion.",
                        "# upstream implementation ../source.py source behavior",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            hits.write_text("source.py:1:needle\n", encoding="utf-8")

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--search-hits-file",
                str(hits),
                "source.py",
                "tests/test_source.py",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=search_hit path=source.py",
                result.stdout,
            )
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=declared_upstream "
                "kind=design path=design.md source=source.py target=design.md",
                result.stdout,
            )
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=incoming_upstream "
                "kind=implementation path=tests/test_source.py "
                "source=tests/test_source.py target=source.py",
                result.stdout,
            )
            self.assertIn("DEPENDENCY_EDIT_SCOPE_PATHS=3", result.stdout)

    def test_repo_review_report_dir_generates_graph_and_edit_scope(self) -> None:
        """Repo dependency review should persist graph and edit-scope artifacts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "workflow_monitor.py").symlink_to(WORKFLOW_MONITOR)
            target = root / "target.md"
            source = root / "source.md"
            hits = root / "search_hits.txt"
            report_dir = root / "reports" / "dependency-review"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target fixture for report artifacts.",
                        "downstream design source.md source consumes target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source fixture for report artifacts.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            hits.write_text("source.md:1:Source\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--report-dir",
                str(report_dir),
                "--search-hits-file",
                str(hits),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((report_dir / "dependency_graph.tsv").is_file())
            self.assertTrue((report_dir / "dependency_edit_scope.txt").is_file())
            self.assertIn("direction\tkind\tsource\ttarget", (report_dir / "dependency_graph.tsv").read_text(encoding="utf-8"))
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=search_hit path=source.md",
                (report_dir / "dependency_edit_scope.txt").read_text(encoding="utf-8"),
            )

    def test_repo_review_report_dir_without_search_hits_records_changed_scope(self) -> None:
        """Report-dir dependency review persists changed-file edit scope by default."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "workflow_monitor.py").symlink_to(WORKFLOW_MONITOR)
            target = root / "target.md"
            source = root / "source.md"
            report_dir = root / "reports" / "dependency-review"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target fixture for changed scope.",
                        "downstream design source.md source consumes target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source fixture for changed scope.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.email=test@example.invalid",
                    "-c",
                    "user.name=Test User",
                    "commit",
                    "-m",
                    "seed dependency fixture",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            source.write_text(
                source.read_text(encoding="utf-8") + "changed\n",
                encoding="utf-8",
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--report-dir",
                str(report_dir),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((report_dir / "dependency_edit_scope.txt").is_file())
            self.assertIn(
                "DEPENDENCY_EDIT_SCOPE_PATH role=search_hit path=source.md",
                (report_dir / "dependency_edit_scope.txt").read_text(encoding="utf-8"),
            )

    def test_symlink_root_views_are_skipped_without_breaking_scan(self) -> None:
        """Root symlink views are owned by link-root and do not fail header scans."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vendor = root / "vendor" / "agent-canon"
            vendor.mkdir(parents=True)
            (vendor / "README.md").write_text(
                "\n".join(
                    [
                        "# Vendor",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines a vendor source fixture.",
                        "upstream design README.md self fixture",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            os.symlink("vendor/agent-canon/README.md", root / "README.md")

            scan = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(root / "README.md"),
                root=root,
            )
            fmt = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(root / "README.md"),
                root=root,
            )

            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN_SKIPPED=1", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN_MISSING=0", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", fmt.stdout)

    def test_legal_license_files_are_skipped_without_dependency_headers(self) -> None:
        """Canonical legal license files keep standard legal text without repo headers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            license_file = root / "LICENSE"
            license_file.write_text("Apache License\nVersion 2.0\n", encoding="utf-8")

            scan = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(license_file),
                root=root,
            )
            fmt = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(license_file),
                root=root,
            )

            self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
            self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN_SKIPPED=1", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN_MISSING=0", scan.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", fmt.stdout)

    def test_agent_runtime_surfaces_pass_manifest_scan_and_format(self) -> None:
        """Agent runtime docs and skill surfaces stay compatible with manifest tools."""
        paths = [
            ".agents/skills/codex-task-workflow/SKILL.md",
            ".codex/README.md",
            "ROOT_AGENTS.md",
            "agents/TASK_WORKFLOWS.md",
            "agents/USER_GUIDE_JA.md",
            "agents/skills/catalog.yaml",
            "agents/skills/worktree-start.md",
            "agents/task_catalog.yaml",
            "agents/workflows/adaptive-improvement-workflow.md",
            "agents/workflows/agent-canon-pr-workflow.md",
            "agents/workflows/agent-learning-workflow.md",
            "agents/workflows/experiment-workflow.md",
            "agents/workflows/implementation-waterfall-workflow.md",
            "documents/BRANCH_SCOPE.md",
            "documents/algorithm-implementation-boundary.md",
            "documents/codex-configuration-reference.md",
            "documents/coding-conventions-project.md",
            "documents/coding-conventions-reviews.md",
            "documents/conventions/python/20_benchmark_policy.md",
            "documents/experiment-critical-review.md",
            "documents/tools/README.md",
            "documents/worktree-lifecycle.md",
            "memory/AGENT_PHILOSOPHY.md",
            "memory/USER_PREFERENCES.md",
            "notes/README.md",
            "notes/guardrails/engineering_avoidances.md",
        ]

        scan = run_tool(
            str(SCAN),
            "--root",
            str(PROJECT_ROOT),
            "--fail-missing",
            *paths,
            root=PROJECT_ROOT,
        )
        fmt = run_tool(
            str(FORMAT),
            "--root",
            str(PROJECT_ROOT),
            "--require-header",
            *paths,
            root=PROJECT_ROOT,
        )

        self.assertEqual(scan.returncode, 0, scan.stdout + scan.stderr)
        self.assertEqual(fmt.returncode, 0, fmt.stdout + fmt.stderr)
        self.assertIn("DEPENDENCY_HEADER_SCAN=pass", scan.stdout)
        self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", fmt.stdout)
        self.assertTrue((PROJECT_ROOT / "ROOT_AGENTS.md").is_file())
        template_root = PROJECT_ROOT.parent.parent
        embedded_vendor = template_root / "vendor" / "agent-canon"
        if embedded_vendor.exists() and embedded_vendor.resolve() == PROJECT_ROOT:
            self.assertFalse((template_root / "ROOT_AGENTS.md").exists())
            self.assertTrue((template_root / "AGENTS.md").is_symlink())
            self.assertEqual(
                (template_root / "AGENTS.md").readlink().as_posix(),
                "vendor/agent-canon/ROOT_AGENTS.md",
            )

    def test_format_accepts_json_string_manifest(self) -> None:
        """JSON files can keep valid syntax by storing manifest lines as strings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.py"
            source = root / "source.json"
            target.write_text("# target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "{",
                        '  "_dependency_manifest": [',
                        '    "@dependency-start",',
                        '    "contract test",',
                        '    "responsibility Exercises a JSON string manifest.",',
                        '    "upstream implementation target.py target contract",',
                        '    "@dependency-end"',
                        "  ],",
                        '  "ok": true',
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_scan_skips_strict_json_without_manifest(self) -> None:
        """Strict JSON is commentless and is not part of required header coverage."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")

            result = run_tool(
                str(SCAN),
                "--root",
                str(root),
                "--fail-missing",
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_SCAN_SKIPPED=1", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN_MISSING=0", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", result.stdout)

    def test_require_header_skips_strict_json_without_manifest(self) -> None:
        """Strict JSON without manifest markers remains valid under require-header."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(source),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_require_header_skips_agent_run_artifacts(self) -> None:
        """Run-bundle artifacts are workflow evidence, not product manifest surface."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report = root / "reports" / "agents" / "run-1" / "verification.txt"
            report.parent.mkdir(parents=True)
            report.write_text("status=pass\n", encoding="utf-8")

            result = run_tool(
                str(FORMAT),
                "--root",
                str(root),
                "--require-header",
                str(report),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=pass", result.stdout)

    def test_format_rejects_invalid_direction(self) -> None:
        """The format checker rejects unknown directions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "target.py"
            source = root / "source.py"
            target.write_text("# target\n", encoding="utf-8")
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises invalid direction validation.",
                        "# sideways implementation target.py invalid direction",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(FORMAT), "--root", str(root), str(source), root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid direction", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_FORMAT=fail", result.stdout)

    def test_graph_accepts_bidirectional_edges(self) -> None:
        """Matching upstream/downstream reverse edges pass graph validation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines source a for graph validation.",
                        "# downstream implementation b.py b consumes a",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines source b for graph validation.",
                        "# upstream implementation a.py a is consumed by b",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                str(a),
                str(b),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_GRAPH=pass", result.stdout)

    def test_graph_rejects_isolated_manifest(self) -> None:
        """The graph checker rejects manifests that do not connect to any edge."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source.py"
            source.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Exercises isolated manifest validation.",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(str(GRAPH), "--root", str(root), str(source), root=root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("isolated dependency manifest", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=fail", result.stdout)

    def test_graph_rejects_missing_reverse_edge(self) -> None:
        """Strict bidirectional mode requires the matching reverse edge."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines source a for reverse validation.",
                        "# downstream implementation b.py b consumes a",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text("# no manifest\n", encoding="utf-8")

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--check-bidirectional",
                str(a),
                str(b),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing reverse upstream implementation edge", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=fail", result.stdout)

    def test_graph_rejects_upstream_cycles(self) -> None:
        """The graph checker detects cycles in the upstream graph."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# upstream implementation b.py b is prerequisite",
                        "# downstream implementation b.py b also affected",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# upstream implementation a.py a is prerequisite",
                        "# downstream implementation a.py a also affected",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                str(a),
                str(b),
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cycle includes", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=fail", result.stdout)

    def test_graph_can_report_cycles_without_failing(self) -> None:
        """Cycle report-only mode keeps known graph debt visible without blocking."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            a = root / "a.py"
            b = root / "b.py"
            a.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines a fixture with a known cycle.",
                        "# upstream implementation b.py b is prerequisite",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# contract test",
                        "# responsibility Defines b fixture with a known cycle.",
                        "# upstream implementation a.py a is prerequisite",
                        "# @dependency-end",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = run_tool(
                str(GRAPH),
                "--root",
                str(root),
                "--cycle-report-only",
                str(a),
                str(b),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("cycle includes", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH_UPSTREAM_CYCLES=report_only", result.stdout)
            self.assertIn("DEPENDENCY_GRAPH=pass", result.stdout)

    def test_repo_review_runs_all_dependency_tools(self) -> None:
        """The wrapper applies dependency tools to tracked checkable files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target test fixture context.",
                        "downstream design source.md source reads target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source test fixture context.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(str(REPO_REVIEW), "--root", str(root), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPO_DEPENDENCY_REVIEW_PATHS=2", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_can_report_cycles_without_failing(self) -> None:
        """The wrapper supports report-only cycles when a durable graph artifact is used."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "workflow_monitor.py").symlink_to(WORKFLOW_MONITOR)
            (tool_dir / "agent_team.py").symlink_to(AGENT_TEAM)
            a = root / "a.md"
            b = root / "b.md"
            a.write_text(
                "\n".join(
                    [
                        "# A",
                        "",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines a cycle-report-only fixture.",
                        "upstream design b.md b is prerequisite",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# B",
                        "",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines b cycle-report-only fixture.",
                        "upstream design a.md a is prerequisite",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "a.md", "b.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                "--cycle-report-only",
                "--report-dir",
                str(root / "reports" / "dependency-review" / "run"),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_GRAPH_UPSTREAM_CYCLES=report_only", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_skips_dependency_review_artifacts(self) -> None:
        """Generated dependency-review outputs are not repo source inputs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target test fixture context.",
                        "downstream design source.md source reads target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source test fixture context.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            artifact = root / "reports" / "dependency-review" / "run" / "search_hits.txt"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("source.md\n", encoding="utf-8")
            subprocess.run(
                [
                    "git",
                    "add",
                    "target.md",
                    "source.md",
                    "reports/dependency-review/run/search_hits.txt",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("REPO_DEPENDENCY_REVIEW_PATHS=2", result.stdout)
            self.assertNotIn("reports/dependency-review/run/search_hits.txt", result.stdout)

    def test_repo_review_records_monitoring_when_report_dir_is_given(self) -> None:
        """The review wrapper records monitoring evidence when directed to a run."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            (tool_dir / "workflow_monitor.py").symlink_to(WORKFLOW_MONITOR)
            (tool_dir / "agent_team.py").symlink_to(AGENT_TEAM)
            target = root / "target.md"
            source = root / "source.md"
            target.write_text(
                "\n".join(
                    [
                        "# Target",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines target test fixture context.",
                        "downstream design source.md source reads target",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source.write_text(
                "\n".join(
                    [
                        "# Source",
                        "<!--",
                        "@dependency-start",
                        "contract test",
                        "responsibility Defines source test fixture context.",
                        "upstream design target.md target context",
                        "@dependency-end",
                        "-->",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(
                ["git", "add", "target.md", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            report_dir = root / "reports" / "agents" / "run-3"

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--report-dir",
                str(report_dir),
                root=root,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            text = (report_dir / "workflow_monitoring.md").read_text(encoding="utf-8")
            self.assertIn("repo_dependency_review=pass", text)
            self.assertIn(
                "run_repo_dependency_review.sh recorded dependency review pass",
                text,
            )

    def test_repo_review_reports_missing_manifests_by_default(self) -> None:
        """The repo-wide wrapper keeps missing headers report-only during migration."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            source = root / "source.md"
            source.write_text("# Source\n\nBody.\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(str(REPO_REVIEW), "--root", str(root), root=root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("MISSING_DEPENDENCY_MANIFEST=source.md", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN=pass", result.stdout)
            self.assertIn("REPO_DEPENDENCY_REVIEW=pass", result.stdout)

    def test_repo_review_can_require_missing_manifests(self) -> None:
        """Strict mode fails when tracked checkable files lack manifests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(
                ["git", "init"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            tool_dir = root / "tools" / "agent_tools"
            tool_dir.mkdir(parents=True)
            (tool_dir / "scan_dependency_headers.sh").symlink_to(SCAN)
            (tool_dir / "check_dependency_header_format.sh").symlink_to(FORMAT)
            (tool_dir / "check_dependency_graph.sh").symlink_to(GRAPH)
            source = root / "source.md"
            source.write_text("# Source\n\nBody.\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "source.md"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            result = run_tool(
                str(REPO_REVIEW),
                "--root",
                str(root),
                "--fail-missing",
                root=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MISSING_DEPENDENCY_MANIFEST=source.md", result.stdout)
            self.assertIn("DEPENDENCY_HEADER_SCAN=fail", result.stdout)


if __name__ == "__main__":
    unittest.main()
