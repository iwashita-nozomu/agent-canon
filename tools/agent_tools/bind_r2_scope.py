"""Bind an R2 source scope to later review decisions without circular hashes."""

# @dependency-start
# contract implementation
# responsibility Owns the two-phase R2 scope manifest and post-review binding evidence boundary.
# upstream design ../../reports/agents/20260712-090608-context-packettool-skill-routing/graph_design_brief.md Pre-review scope manifest and post-review binding
# upstream implementation ../../tools/agent_tools/dependency_manifest_records.py produces the registry artifact consumed here
# downstream implementation ../../reports/agents/20260712-090608-context-packettool-skill-routing/validation/r2-source-pr/ review evidence artifacts
# @dependency-end

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

if __package__ in (None, ""):
    from dependency_manifest_records import (
        EXPECTED_REGISTRY_FINGERPRINT,
        REGISTRY_VERSION,
    )
else:
    from .dependency_manifest_records import (
        EXPECTED_REGISTRY_FINGERPRINT,
        REGISTRY_VERSION,
    )

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_VERSION = "r2_scope_manifest.v1"
CLOSEOUT_VERSION = "r2_review_closeout.v1"
EXPECTED_REGISTRY_BYTES = 3323
EXPECTED_REGISTRY_SHA256 = "e2601dcd34a2d6896526f6efc519a7faee7c9a47ccd50bdd29d04ecc8cf6ac69"
REGISTRY_ENTRY_KEYS = {
    "capability_id", "discriminator", "family", "layer", "raw_kind", "stored_kind",
}

JsonObject = dict[str, object]


class ScopeRow(TypedDict):
    """One exact path/hash row in the pre-review manifest."""

    path: str
    sha256: str


class RegistryBinding(TypedDict):
    """Validated registry identity stored in the scope manifest."""

    path: str
    sha256: str
    registry_fingerprint: str


class ReviewArtifact(TypedDict):
    """Resolved immutable review identity used during closeout."""

    path: str
    resolved_path: str
    file_identity: tuple[int, int]
    sha256: str
    decision: str
    bound_scope_manifest_id: str


class ReviewBinding(TypedDict):
    """Review fields persisted in successful closeout evidence."""

    path: str
    sha256: str
    decision: str
    bound_scope_manifest_id: str


@dataclass(frozen=True)
class ManifestArgs:
    """Typed manifest-mode arguments after argparse validation."""

    sources: list[Path]
    fixtures: list[Path]
    registry_artifact: Path
    command_ids: list[str]
    output: Path


@dataclass(frozen=True)
class CloseoutArgs:
    """Typed closeout-mode arguments after argparse validation."""

    manifest: Path
    change_review: Path
    logic_review: Path
    output: Path


class ScopeBindingInvalid(ValueError):
    """Raised for missing, mismatched, or non-approving review evidence."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash_parts(parts: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ScopeBindingInvalid(f"cannot read {path}: {error}") from error


def _strict_object(pairs: list[tuple[str, object]]) -> JsonObject:
    value: JsonObject = {}
    for key, item in pairs:
        if key in value:
            raise ScopeBindingInvalid(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _json_object(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ScopeBindingInvalid(f"{label} must be an object with string keys")
    raw_object = cast(dict[object, object], value)
    for key in raw_object:
        if not isinstance(key, str):
            raise ScopeBindingInvalid(f"{label} must be an object with string keys")
    return cast(JsonObject, raw_object)


def _exact_keys(value: object, expected: set[str], label: str) -> JsonObject:
    object_value = _json_object(value, label)
    if set(object_value) != expected:
        raise ScopeBindingInvalid(f"{label} schema mismatch")
    return object_value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ScopeBindingInvalid(f"{label} must be a string")
    return value


def _path(value: object, label: str) -> Path:
    if not isinstance(value, Path):
        raise ScopeBindingInvalid(f"{label} must be a path")
    return value


def _path_list(value: object, label: str) -> list[Path]:
    if not isinstance(value, list):
        raise ScopeBindingInvalid(f"{label} must be a path list")
    raw_values = cast(list[object], value)
    if any(not isinstance(item, Path) for item in raw_values):
        raise ScopeBindingInvalid(f"{label} must be a path list")
    return cast(list[Path], raw_values)


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ScopeBindingInvalid(f"{label} must be a string list")
    raw_values = cast(list[object], value)
    if any(not isinstance(item, str) for item in raw_values):
        raise ScopeBindingInvalid(f"{label} must be a string list")
    return cast(list[str], raw_values)


def _object_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ScopeBindingInvalid(f"{label} must be an array")
    return cast(list[object], value)


def _registry_sort_key(entry: JsonObject) -> tuple[str, str, str, str, str, str]:
    return (
        _string(entry["capability_id"], "registry capability_id"),
        _string(entry["raw_kind"], "registry raw_kind"),
        _string(entry["discriminator"], "registry discriminator"),
        _string(entry["stored_kind"], "registry stored_kind"),
        _string(entry["layer"], "registry layer"),
        _string(entry["family"], "registry family"),
    )


def _validated_registry_artifact(path: Path) -> tuple[str, str]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ScopeBindingInvalid(f"registry artifact is unreadable: {path}: {error}") from error
    if (
        len(raw) != EXPECTED_REGISTRY_BYTES
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        raise ScopeBindingInvalid("registry artifact byte contract mismatch")
    try:
        value = cast(
            object,
            json.loads(
                raw[:-1].decode("utf-8"),
                object_pairs_hook=_strict_object,
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ScopeBindingInvalid) as error:
        raise ScopeBindingInvalid(f"registry artifact is invalid JSON: {error}") from error
    if _canonical_bytes(value) + b"\n" != raw:
        raise ScopeBindingInvalid("registry artifact is not canonical JSON")
    registry = _exact_keys(
        value,
        {"entries", "registry_fingerprint", "registry_version"},
        "registry artifact",
    )
    entries_value = registry["entries"]
    if (
        _string(registry["registry_version"], "registry_version") != REGISTRY_VERSION
        or _string(registry["registry_fingerprint"], "registry_fingerprint")
        != EXPECTED_REGISTRY_FINGERPRINT
    ):
        raise ScopeBindingInvalid("registry artifact version, count, or fingerprint mismatch")
    raw_entries = _object_list(entries_value, "registry artifact entries")
    if len(raw_entries) != 20:
        raise ScopeBindingInvalid("registry artifact version, count, or fingerprint mismatch")
    entries: list[JsonObject] = []
    for index, entry_value in enumerate(raw_entries):
        entry = _exact_keys(
            entry_value,
            REGISTRY_ENTRY_KEYS,
            f"registry artifact entry {index}",
        )
        for field in REGISTRY_ENTRY_KEYS:
            _string(entry[field], f"registry artifact entry {index}.{field}")
        entries.append(entry)
    if entries != sorted(entries, key=_registry_sort_key) or len(
        {_registry_sort_key(entry) for entry in entries}
    ) != 20:
        raise ScopeBindingInvalid("registry artifact entries are not the exact sorted unique set")
    computed_fingerprint = hashlib.sha256(
        _canonical_bytes({"entries": entries, "registry_version": REGISTRY_VERSION})
    ).hexdigest()
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    if computed_fingerprint != EXPECTED_REGISTRY_FINGERPRINT:
        raise ScopeBindingInvalid("registry artifact entry-set fingerprint mismatch")
    if artifact_sha256 != EXPECTED_REGISTRY_SHA256:
        raise ScopeBindingInvalid("registry artifact exact SHA-256 mismatch")
    return artifact_sha256, computed_fingerprint


def _parse_args(parser: argparse.ArgumentParser, argv: Sequence[str]) -> argparse.Namespace:
    return parser.parse_args(list(argv))


def _manifest_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bind_r2_scope.py manifest")
    parser.add_argument("--source", action="append", required=True, type=Path)
    parser.add_argument("--fixture", action="append", required=True, type=Path)
    parser.add_argument("--registry-artifact", required=True, type=Path)
    parser.add_argument("--command-id", action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _closeout_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bind_r2_scope.py closeout")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--change-review", required=True, type=Path)
    parser.add_argument("--logic-review", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def _manifest_args(argv: Sequence[str]) -> ManifestArgs:
    args = _parse_args(_manifest_parser(), argv)
    return ManifestArgs(
        sources=_path_list(cast(object, args.source), "--source"),
        fixtures=_path_list(cast(object, args.fixture), "--fixture"),
        registry_artifact=_path(
            cast(object, args.registry_artifact), "--registry-artifact"
        ),
        command_ids=_string_list(cast(object, args.command_id), "--command-id"),
        output=_path(cast(object, args.output), "--output"),
    )


def _closeout_args(argv: Sequence[str]) -> CloseoutArgs:
    args = _parse_args(_closeout_parser(), argv)
    return CloseoutArgs(
        manifest=_path(cast(object, args.manifest), "--manifest"),
        change_review=_path(cast(object, args.change_review), "--change-review"),
        logic_review=_path(cast(object, args.logic_review), "--logic-review"),
        output=_path(cast(object, args.output), "--output"),
    )


def _review_fields(path: Path) -> tuple[str, str, bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ScopeBindingInvalid(f"review is missing or unreadable: {path}: {error}") from error
    if (
        not raw.endswith(b"\n")
        or raw.startswith(b"\xef\xbb\xbf")
        or b"\r" in raw
        or b"\x00" in raw
    ):
        raise ScopeBindingInvalid(f"review is not canonical LF-terminated UTF-8: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ScopeBindingInvalid(f"review is not canonical UTF-8: {path}: {error}") from error
    decision_pattern = re.compile(r"decision: (approve|revise|escalate)")
    bound_pattern = re.compile(r"bound_scope_manifest_id: ([0-9a-f]{64})")
    decisions: list[str] = []
    bound_ids: list[str] = []
    for line in text[:-1].split("\n"):
        decision_match = decision_pattern.fullmatch(line)
        bound_match = bound_pattern.fullmatch(line)
        if decision_match is not None:
            decisions.append(decision_match.group(1))
        elif bound_match is not None:
            bound_ids.append(bound_match.group(1))
        elif line.lstrip().startswith(("decision", "bound_scope_manifest_id")):
            raise ScopeBindingInvalid(f"review contains a malformed machine field: {path}")
    if len(decisions) != 1 or len(bound_ids) != 1:
        raise ScopeBindingInvalid(f"review is not bound to the scope manifest: {path}")
    return decisions[0], bound_ids[0], raw


def _review_artifact(path: Path) -> ReviewArtifact:
    try:
        resolved = path.resolve(strict=True)
        metadata = path.stat()
    except OSError as error:
        raise ScopeBindingInvalid(f"review is missing or unreadable: {path}: {error}") from error
    decision, bound_id, raw = _review_fields(path)
    return {
        "path": str(path),
        "resolved_path": str(resolved),
        "file_identity": (metadata.st_dev, metadata.st_ino),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "decision": decision,
        "bound_scope_manifest_id": bound_id,
    }


def _scope_rows(value: object, label: str) -> list[ScopeRow]:
    raw_rows = _object_list(value, f"scope manifest {label}")
    rows: list[ScopeRow] = []
    for index, row_value in enumerate(raw_rows):
        row = _exact_keys(row_value, {"path", "sha256"}, f"{label} row {index}")
        path = _string(row["path"], f"{label} row {index}.path")
        sha256 = _string(row["sha256"], f"{label} row {index}.sha256")
        if not HEX64.fullmatch(sha256):
            raise ScopeBindingInvalid(f"{label} row {index}.sha256 is invalid")
        rows.append({"path": path, "sha256": sha256})
    if rows != sorted(rows, key=lambda row: row["path"]):
        raise ScopeBindingInvalid(f"scope manifest {label} is not sorted")
    if len({row["path"] for row in rows}) != len(rows):
        raise ScopeBindingInvalid(f"scope manifest {label} contains duplicate paths")
    return rows


def _registry_binding(value: object) -> RegistryBinding:
    registry = _exact_keys(
        value,
        {"path", "sha256", "registry_fingerprint"},
        "scope manifest registry artifact",
    )
    path = _string(registry["path"], "scope manifest registry path")
    sha256 = _string(registry["sha256"], "scope manifest registry sha256")
    fingerprint = _string(
        registry["registry_fingerprint"],
        "scope manifest registry fingerprint",
    )
    if not HEX64.fullmatch(sha256) or not HEX64.fullmatch(fingerprint):
        raise ScopeBindingInvalid("scope manifest registry artifact identity is invalid")
    return {
        "path": path,
        "sha256": sha256,
        "registry_fingerprint": fingerprint,
    }


def _read_manifest(path: Path) -> JsonObject:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ScopeBindingInvalid(f"scope manifest is unreadable: {path}: {error}") from error
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n") or raw.startswith(b"\xef\xbb\xbf"):
        raise ScopeBindingInvalid("scope manifest is not canonical JSON with one LF")
    try:
        value = cast(
            object,
            json.loads(
                raw[:-1].decode("utf-8"),
                object_pairs_hook=_strict_object,
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ScopeBindingInvalid) as error:
        raise ScopeBindingInvalid(f"scope manifest is invalid JSON: {error}") from error
    if _canonical_bytes(value) + b"\n" != raw:
        raise ScopeBindingInvalid("scope manifest is not canonical JSON")
    expected = {
        "manifest_version", "scope_manifest_id", "sources", "fixtures",
        "registry_artifact", "command_ids",
    }
    manifest_value = _exact_keys(value, expected, "scope manifest")
    manifest_version = _string(manifest_value["manifest_version"], "manifest_version")
    manifest_id = _string(manifest_value["scope_manifest_id"], "scope_manifest_id")
    if manifest_version != MANIFEST_VERSION or not HEX64.fullmatch(manifest_id):
        raise ScopeBindingInvalid("scope manifest version or ID is invalid")
    sources = _scope_rows(manifest_value["sources"], "sources")
    fixtures = _scope_rows(manifest_value["fixtures"], "fixtures")
    registry = _registry_binding(manifest_value["registry_artifact"])
    command_ids = _string_list(manifest_value["command_ids"], "command_ids")
    if any(not command_id for command_id in command_ids) or (
        command_ids != sorted(command_ids) or len(set(command_ids)) != len(command_ids)
    ):
        raise ScopeBindingInvalid("scope manifest command IDs are not sorted and unique")
    body = {
        "sources": sources,
        "fixtures": fixtures,
        "registry_artifact": registry,
        "command_ids": command_ids,
    }
    expected_id = _hash_parts([MANIFEST_VERSION, _canonical_bytes(body).decode("utf-8")])
    if manifest_id != expected_id:
        raise ScopeBindingInvalid("scope manifest ID mismatch")
    return manifest_value


def _verify_manifest_inputs(manifest_value: JsonObject) -> None:
    for label in ("sources", "fixtures"):
        for row in _scope_rows(manifest_value[label], label):
            path = Path(row["path"])
            if _sha256(path) != row["sha256"]:
                raise ScopeBindingInvalid(f"scope manifest {label} bytes are stale: {path}")
    registry = _registry_binding(manifest_value["registry_artifact"])
    registry_path = Path(registry["path"])
    sha256, fingerprint = _validated_registry_artifact(registry_path)
    if (
        sha256 != registry["sha256"]
        or fingerprint != registry["registry_fingerprint"]
    ):
        raise ScopeBindingInvalid("scope manifest registry bytes are stale")


def manifest(argv: Sequence[str]) -> int:
    """Create a pre-review, non-circular source/fixture scope manifest."""
    try:
        args = _manifest_args(argv)
        sources = sorted(
            [ScopeRow(path=str(path), sha256=_sha256(path)) for path in args.sources],
            key=lambda item: item["path"],
        )
        fixtures = sorted(
            [ScopeRow(path=str(path), sha256=_sha256(path)) for path in args.fixtures],
            key=lambda item: item["path"],
        )
        if len({item["path"] for item in sources}) != len(sources):
            raise ScopeBindingInvalid("source paths must be unique")
        if len({item["path"] for item in fixtures}) != len(fixtures):
            raise ScopeBindingInvalid("fixture paths must be unique")
        registry_sha256, registry_fingerprint = _validated_registry_artifact(
            args.registry_artifact
        )
        registry_artifact = RegistryBinding(
            path=str(args.registry_artifact),
            sha256=registry_sha256,
            registry_fingerprint=registry_fingerprint,
        )
        command_ids = sorted(set(args.command_ids))
        if len(command_ids) != len(args.command_ids):
            raise ScopeBindingInvalid("command IDs must be unique")
        body = {
            "sources": sources,
            "fixtures": fixtures,
            "registry_artifact": registry_artifact,
            "command_ids": command_ids,
        }
        value = {
            "manifest_version": MANIFEST_VERSION,
            "scope_manifest_id": _hash_parts([MANIFEST_VERSION, _canonical_bytes(body).decode("utf-8")]),
            **body,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(_canonical_bytes(value) + b"\n")
        print(f"R2_SCOPE_MANIFEST=pass scope_manifest_id={value['scope_manifest_id']}")
        return 0
    except (OSError, ScopeBindingInvalid) as error:
        print(f"R2_SCOPE_MANIFEST=transport-invalid error={error}", file=sys.stderr)
        return 22


def closeout(argv: Sequence[str]) -> int:
    """Bind two immutable review decisions to a previously-written manifest."""
    try:
        args = _closeout_args(argv)
        args.output.unlink(missing_ok=True)
        manifest_value = _read_manifest(args.manifest)
        _verify_manifest_inputs(manifest_value)
        manifest_id = _string(manifest_value["scope_manifest_id"], "scope_manifest_id")
        if args.change_review == args.logic_review:
            raise ScopeBindingInvalid("change and logic review paths must be distinct")
        change_artifact = _review_artifact(args.change_review)
        logic_artifact = _review_artifact(args.logic_review)
        if change_artifact["resolved_path"] == logic_artifact["resolved_path"]:
            raise ScopeBindingInvalid("change and logic reviews resolve to the same path")
        if change_artifact["file_identity"] == logic_artifact["file_identity"]:
            raise ScopeBindingInvalid("change and logic reviews have the same file identity")
        if change_artifact["sha256"] == logic_artifact["sha256"]:
            raise ScopeBindingInvalid("change and logic reviews have identical content")
        reviews: list[ReviewBinding] = []
        for review_artifact in (change_artifact, logic_artifact):
            review_path = review_artifact["path"]
            decision = review_artifact["decision"]
            bound_id = review_artifact["bound_scope_manifest_id"]
            if decision != "approve" or bound_id != manifest_id:
                raise ScopeBindingInvalid(
                    f"review binding mismatch or non-approve decision: {review_path}"
                )
            reviews.append(
                ReviewBinding(
                    path=review_path,
                    sha256=review_artifact["sha256"],
                    decision=decision,
                    bound_scope_manifest_id=bound_id,
                )
            )
        body = {
            "scope_manifest_id": manifest_id,
            "change_review": reviews[0],
            "logic_review": reviews[1],
        }
        value = {
            "closeout_version": CLOSEOUT_VERSION,
            "review_closeout_id": _hash_parts(
                [CLOSEOUT_VERSION, _canonical_bytes(body).decode("utf-8")]
            ),
            **body,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(_canonical_bytes(value) + b"\n")
        print(f"R2_REVIEW_CLOSEOUT=pass review_closeout_id={value['review_closeout_id']}")
        return 0
    except (OSError, ScopeBindingInvalid) as error:
        print(f"R2_REVIEW_CLOSEOUT=review-binding-blocked error={error}", file=sys.stderr)
        return 21


def main(argv: Sequence[str]) -> int:
    """Dispatch the manifest or closeout public mode."""
    if not argv or argv[0] not in {"manifest", "closeout"}:
        print("usage: bind_r2_scope.py manifest|closeout ...", file=sys.stderr)
        return 2
    if argv[0] == "manifest":
        return manifest(argv[1:])
    return closeout(argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
