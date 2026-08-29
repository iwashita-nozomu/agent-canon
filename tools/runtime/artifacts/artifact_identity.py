#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Materializes and verifies canonical artifact byte identities.
# upstream design ../../agents/COMMUNICATION_PROTOCOL.md owns artifact identity schemas and import rules.
# downstream implementation ./review_dispatch.py imports review target and decision identities.
# downstream implementation ./publication_integrator.py imports approval and publication identities.
# downstream implementation ./github_publish.py verifies publication packet identities before network mutation.
# downstream implementation ./report_artifact_checks.py recomputes artifact identity equality.
# downstream implementation ./task_close.py rejects stale or hand-transcribed artifact identities.
# downstream implementation ../../tests/agent_tools/test_artifact_identity.py validates exact byte and source readback.
# @dependency-end
"""Materialize exact artifact identities from Git objects or stable file bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

UTC = timezone.utc  # noqa: UP017

ARTIFACT_IDENTITY_SCHEMA = "agent-canon.artifact-identity.v1"
ARTIFACT_ROLES = frozenset(
    {
        "review_target",
        "review_decision",
        "review_receipt",
        "source_packet_artifact",
        "publication_authority",
        "publication_receipt",
    }
)
SOURCE_BINDING_KINDS = frozenset({"git_commit_path", "filesystem_immutable"})
TEXT_EXTENSIONS = frozenset(
    {
        ".json",
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".yaml",
        ".yml",
        ".txt",
    }
)


class ArtifactIdentityError(ValueError):
    """Typed artifact-identity contract failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Initialize one stable failure."""
        self.code = code
        self.detail = detail
        rendered = code if not detail else f"{code}:{detail}"
        super().__init__(rendered)


def _reject_noncanonical_json(value: object) -> None:
    """Reject values whose JSON representation is not stable in this contract."""
    if isinstance(value, float):
        raise ArtifactIdentityError("artifact_identity:float_forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ArtifactIdentityError("artifact_identity:non_string_key")
            _reject_noncanonical_json(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_noncanonical_json(item)


def canonical_json_bytes(value: object) -> bytes:
    """Return RFC-8785-compatible bytes for the contract's integer/string domain."""
    _reject_noncanonical_json(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_body_sha256(record: Mapping[str, object], hash_field: str) -> str:
    """Hash one canonical record while omitting only its body-hash field."""
    body = {key: value for key, value in record.items() if key != hash_field}
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def git_blob_oid(data: bytes) -> str:
    """Return the SHA-1 Git blob object ID for exact bytes."""
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _run_git(
    workspace: Path, args: Sequence[str], *, text: bool = False
) -> bytes | str:
    """Run one read-only Git command."""
    completed = subprocess.run(
        ["git", "-C", str(workspace), *args],
        check=False,
        capture_output=True,
        text=text,
    )
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip()
            if text
            else completed.stderr.decode(errors="replace").strip()
        )
        raise ArtifactIdentityError("artifact_identity:git_read_failed", detail)
    return completed.stdout


def _normalized_relative_path(workspace: Path, artifact_path: Path) -> str:
    """Return one normalized repository-relative path."""
    root = workspace.resolve()
    path = artifact_path if artifact_path.is_absolute() else root / artifact_path
    try:
        relative = path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ArtifactIdentityError(
            "artifact_identity:path_outside_repository"
        ) from exc
    normalized = PurePosixPath(relative.as_posix())
    if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
        raise ArtifactIdentityError("artifact_identity:path_invalid")
    return normalized.as_posix()


def _infer_artifact_role(path: str) -> str:
    """Infer the closed artifact role from the canonical path."""
    name = PurePosixPath(path).name.lower()
    if "review" in name and ("decision" in name or "receipt" in name):
        return "review_decision"
    if "review" in name:
        return "review_target"
    if "publication" in name and ("receipt" in name or "result" in name):
        return "publication_receipt"
    if "publication" in name or "authority" in name:
        return "publication_authority"
    return "source_packet_artifact"


def _text_characteristics(path: str, data: bytes) -> tuple[str, str, str]:
    """Return exact encoding, BOM, and line-ending fields."""
    if PurePosixPath(path).suffix.lower() not in TEXT_EXTENSIONS:
        return "binary", "not_applicable", "not_applicable"
    bom = "present" if data.startswith(b"\xef\xbb\xbf") else "absent"
    payload = data[3:] if bom == "present" else data
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        return "binary", "not_applicable", "not_applicable"
    if b"\r\n" in payload or b"\r" in payload.replace(b"\r\n", b""):
        line_endings = "mixed_or_crlf"
    else:
        line_endings = "LF"
    return "UTF-8", bom, line_endings


def _stable_filesystem_read(path: Path) -> tuple[bytes, dict[str, object]]:
    """Read one no-follow regular file and prove the node stayed stable."""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ArtifactIdentityError("artifact_identity:not_regular_file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_mode,
        opened.st_size,
        opened.st_mtime_ns,
    ) or (
        opened.st_dev,
        opened.st_ino,
        opened.st_mode,
        opened.st_size,
        opened.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ArtifactIdentityError("artifact_identity:readback_changed")
    data = b"".join(chunks)
    if len(data) != after.st_size:
        raise ArtifactIdentityError("artifact_identity:size_changed")
    mode = f"{stat.S_IMODE(after.st_mode):06o}"
    return data, {
        "nofollow": True,
        "regular_file": True,
        "device": after.st_dev,
        "inode": after.st_ino,
        "mode": mode,
        "size_before": before.st_size,
        "size_after": after.st_size,
        "mtime_ns_before": before.st_mtime_ns,
        "mtime_ns_after": after.st_mtime_ns,
    }


def _head_source_binding(
    workspace: Path,
    path: str,
) -> tuple[dict[str, object], bytes] | None:
    """Return exact committed bytes and source binding when HEAD tracks the path."""
    try:
        head = str(_run_git(workspace, ["rev-parse", "HEAD"], text=True)).strip()
        tree = str(_run_git(workspace, ["rev-parse", "HEAD^{tree}"], text=True)).strip()
        entry = str(
            _run_git(workspace, ["ls-tree", "HEAD", "--", path], text=True)
        ).strip()
    except ArtifactIdentityError:
        return None
    if not entry:
        return None
    metadata, entry_path = entry.split("\t", 1)
    if entry_path != path:
        raise ArtifactIdentityError("artifact_identity:tree_path_mismatch")
    mode, object_kind, blob = metadata.split()
    if object_kind != "blob":
        raise ArtifactIdentityError("artifact_identity:tree_entry_not_blob")
    data = _run_git(workspace, ["show", f"HEAD:{path}"])
    if not isinstance(data, bytes):
        raise ArtifactIdentityError("artifact_identity:git_bytes_invalid")
    return (
        {
            "kind": "git_commit_path",
            "commit": head,
            "tree": tree,
            "path_mode": mode,
            "tree_blob": blob,
        },
        data,
    )


def _owner_tool_identity(workspace: Path) -> dict[str, object]:
    """Return the frozen owner-tool source tuple."""
    owner_path = "tools/agent_tools/artifact_identity.py"
    committed = _head_source_binding(workspace, owner_path)
    if committed is not None:
        source, _ = committed
        return {
            "owner_tool": owner_path,
            "tool_source_commit": source["commit"],
            "tool_source_tree": source["tree"],
            "tool_source_blob": source["tree_blob"],
        }
    owner_bytes = (workspace / owner_path).read_bytes()
    head = str(_run_git(workspace, ["rev-parse", "HEAD"], text=True)).strip()
    tree = str(_run_git(workspace, ["rev-parse", "HEAD^{tree}"], text=True)).strip()
    return {
        "owner_tool": owner_path,
        "tool_source_commit": head,
        "tool_source_tree": tree,
        "tool_source_blob": git_blob_oid(owner_bytes),
    }


def materialize_artifact_identity(
    workspace: Path,
    artifact_path: Path,
) -> dict[str, object]:
    """Materialize one canonical artifact identity from exact bytes."""
    root = workspace.resolve()
    relative = _normalized_relative_path(root, artifact_path)
    committed = _head_source_binding(root, relative)
    if committed is not None:
        source_binding, data = committed
        filesystem_path = root / relative
        if filesystem_path.is_file():
            _, filesystem_readback = _stable_filesystem_read(filesystem_path)
        else:
            filesystem_readback = {
                "nofollow": True,
                "regular_file": True,
                "device": 0,
                "inode": 0,
                "mode": source_binding["path_mode"],
                "size_before": len(data),
                "size_after": len(data),
                "mtime_ns_before": 0,
                "mtime_ns_after": 0,
            }
    else:
        path = root / relative
        data, filesystem_readback = _stable_filesystem_read(path)
        source_binding = {
            "kind": "filesystem_immutable",
            "commit": None,
            "tree": None,
            "path_mode": None,
            "tree_blob": None,
        }
    encoding, bom, line_endings = _text_characteristics(relative, data)
    stable_seed = {
        "artifact_role": _infer_artifact_role(relative),
        "repository_id": root.name,
        "artifact_path": relative,
        "source_binding": source_binding,
        "byte_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "git_blob": git_blob_oid(data),
    }
    identity_record_id = (
        "artifact-identity:"
        + hashlib.sha256(canonical_json_bytes(stable_seed)).hexdigest()
    )
    record: dict[str, object] = {
        "schema": ARTIFACT_IDENTITY_SCHEMA,
        "schema_version": 1,
        "identity_record_id": identity_record_id,
        "artifact_role": stable_seed["artifact_role"],
        "repository_id": root.name,
        "repository_root": str(root),
        "artifact_path": relative,
        "source_binding": source_binding,
        "byte_size": len(data),
        "sha256": stable_seed["sha256"],
        "git_blob": stable_seed["git_blob"],
        "encoding": encoding,
        "bom": bom,
        "line_endings": line_endings,
        "filesystem_readback": filesystem_readback,
        "materializer": _owner_tool_identity(root),
        "materialized_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "materialization_order_index": 1,
        "identity_record_body_sha256": "",
    }
    record["identity_record_body_sha256"] = canonical_body_sha256(
        record,
        "identity_record_body_sha256",
    )
    return record


def verify_identity_record(
    workspace: Path,
    record: Mapping[str, object],
) -> dict[str, object]:
    """Verify one in-memory artifact identity record against canonical bytes."""
    if (
        record.get("schema") != ARTIFACT_IDENTITY_SCHEMA
        or record.get("schema_version") != 1
    ):
        raise ArtifactIdentityError("artifact_identity:schema_mismatch")
    if set(record) != {
        "schema",
        "schema_version",
        "identity_record_id",
        "artifact_role",
        "repository_id",
        "repository_root",
        "artifact_path",
        "source_binding",
        "byte_size",
        "sha256",
        "git_blob",
        "encoding",
        "bom",
        "line_endings",
        "filesystem_readback",
        "materializer",
        "materialized_at_utc",
        "materialization_order_index",
        "identity_record_body_sha256",
    }:
        raise ArtifactIdentityError("artifact_identity:key_set_mismatch")
    role = record.get("artifact_role")
    if role not in ARTIFACT_ROLES:
        raise ArtifactIdentityError("artifact_identity:artifact_role_invalid")
    source_binding = record.get("source_binding")
    if (
        not isinstance(source_binding, Mapping)
        or source_binding.get("kind") not in SOURCE_BINDING_KINDS
    ):
        raise ArtifactIdentityError("artifact_identity:source_binding_invalid")
    artifact_path = record.get("artifact_path")
    if not isinstance(artifact_path, str):
        raise ArtifactIdentityError("artifact_identity:path_invalid")
    current = materialize_artifact_identity(workspace, Path(artifact_path))
    for field in (
        "artifact_role",
        "repository_id",
        "repository_root",
        "artifact_path",
        "source_binding",
        "byte_size",
        "sha256",
        "git_blob",
        "encoding",
        "bom",
        "line_endings",
        "materializer",
    ):
        if record.get(field) != current.get(field):
            raise ArtifactIdentityError("artifact_identity:readback_mismatch", field)
    stable_seed = {
        "artifact_role": record["artifact_role"],
        "repository_id": record["repository_id"],
        "artifact_path": record["artifact_path"],
        "source_binding": record["source_binding"],
        "byte_size": record["byte_size"],
        "sha256": record["sha256"],
        "git_blob": record["git_blob"],
    }
    expected_id = (
        "artifact-identity:"
        + hashlib.sha256(canonical_json_bytes(stable_seed)).hexdigest()
    )
    if record.get("identity_record_id") != expected_id:
        raise ArtifactIdentityError("artifact_identity:id_mismatch")
    if record.get("identity_record_body_sha256") != canonical_body_sha256(
        record,
        "identity_record_body_sha256",
    ):
        raise ArtifactIdentityError("artifact_identity:body_hash_mismatch")
    return {
        "schema": "agent-canon.artifact-identity-verification.v1",
        "ok": True,
        "identity_record_id": expected_id,
        "identity_record_body_sha256": record["identity_record_body_sha256"],
        "artifact_path": artifact_path,
        "sha256": record["sha256"],
        "git_blob": record["git_blob"],
    }


def verify_artifact_identity(
    workspace: Path,
    identity_record_path: Path,
) -> dict[str, object]:
    """Load and verify one materializer-produced identity record."""
    root = workspace.resolve()
    relative = _normalized_relative_path(root, identity_record_path)
    loaded = json.loads((root / relative).read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping):
        raise ArtifactIdentityError("artifact_identity:record_not_object")
    return verify_identity_record(root, loaded)


def build_parser() -> argparse.ArgumentParser:
    """Build the low-level identity CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    subparsers = parser.add_subparsers(dest="action", required=True)
    materialize = subparsers.add_parser("materialize")
    materialize.add_argument("artifact_path")
    verify = subparsers.add_parser("verify")
    verify.add_argument("identity_record_path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the identity CLI without writing an authority artifact."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.action == "materialize":
            result = materialize_artifact_identity(root, Path(args.artifact_path))
        else:
            result = verify_artifact_identity(root, Path(args.identity_record_path))
    except (ArtifactIdentityError, OSError, json.JSONDecodeError) as exc:
        print("ARTIFACT_IDENTITY=fail")
        print(f"ARTIFACT_IDENTITY_FINDING={exc}")
        return 1
    print("ARTIFACT_IDENTITY=pass")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
