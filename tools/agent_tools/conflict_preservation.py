#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Captures and validates content-preserving conflict and rework packets.
# upstream design ../../agents/skills/pr-processing.md owns merge and rework order.
# upstream design ../../agents/canonical/CODEX_SUBAGENTS.md assigns conflict mutation to integration_executor.
# downstream implementation ../../tests/agent_tools/test_conflict_preservation.py validates the focused preservation contract.
# @dependency-end
"""Capture and validate the content that a conflict or rework must preserve.

The checker is intentionally a small companion to the existing integration
owner.  It does not resolve a conflict or choose a side for the operator.  It
records the three index stages and requires an explicit disposition before a
resolution/rework can be accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast


SCHEMA = "agent-canon.conflict-preservation.v1"
REWORK_SCHEMA = "agent-canon.rework-preservation.v1"
DISPOSITIONS = frozenset({"keep", "replace", "manual"})
WHOLE_FILE_OPERATIONS = frozenset(
    {
        "checkout-ours",
        "checkout-theirs",
        "checkout-path",
        "reset",
        "reclone",
        "whole-file-overwrite",
        "regenerate-file",
    }
)


class ConflictPreservationError(ValueError):
    """Raised when a preservation packet is missing required semantic data."""


def _git(repo: Path, args: Sequence[str], *, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise ConflictPreservationError(
            f"git {' '.join(args)} failed: {result.stderr.strip() or 'command failed'}"
        )
    return result.stdout


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _blob(repo: Path, oid: str | None) -> dict[str, object] | None:
    if not oid:
        return None
    kind = _git(repo, ["cat-file", "-t", oid]).strip()
    if kind != "blob":
        raise ConflictPreservationError(f"index object is not a blob: {oid}")
    size = int(_git(repo, ["cat-file", "-s", oid]).strip())
    return {"oid": oid, "type": kind, "size": size}


def _blob_bytes(repo: Path, oid: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", oid],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ConflictPreservationError(f"cannot read expected blob: {oid}")
    return result.stdout


def _safe_relative_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ConflictPreservationError(f"path is outside repository: {path!r}")
    return candidate


def _tree_blob(repo: Path, revision: str, path: str) -> dict[str, object] | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", f"{revision}:{path}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return _blob(repo, result.stdout.strip())


def _parse_unmerged(repo: Path) -> dict[str, dict[str, object]]:
    raw = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--unmerged", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    records: dict[str, dict[str, object]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        header, separator, encoded_path = record.partition(b"\t")
        if not separator:
            raise ConflictPreservationError("malformed git ls-files --unmerged record")
        fields = header.decode("ascii").split()
        if len(fields) != 3:
            raise ConflictPreservationError("malformed unmerged index stage")
        mode, oid, stage = fields
        path = encoded_path.decode("utf-8", errors="surrogateescape")
        entry = records.setdefault(path, {"path": path, "stages": {}})
        stages = entry["stages"]
        assert isinstance(stages, dict)
        stages[{"1": "base", "2": "ours", "3": "theirs"}.get(stage, stage)] = {
            "mode": mode,
            **(_blob(repo, oid) or {}),
        }
    return records


def _revision(repo: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", ref],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def validate_snapshot(
    repo: Path | str,
    inventory: Mapping[str, object],
    target_paths: Sequence[str],
) -> None:
    """Ensure the active conflict still matches the captured stages and refs."""
    root = Path(repo).resolve()
    repository = inventory.get("repository")
    if isinstance(repository, str) and Path(repository).is_absolute():
        if Path(repository).resolve() != root:
            raise ConflictPreservationError("conflict inventory repository does not match active clone")
    base_record = inventory.get("base")
    ours_record = inventory.get("ours")
    theirs_record = inventory.get("theirs")
    if not all(isinstance(record, Mapping) for record in (base_record, ours_record, theirs_record)):
        raise ConflictPreservationError("conflict inventory snapshot refs are missing")
    ours_record = cast(Mapping[str, object], ours_record)
    theirs_record = cast(Mapping[str, object], theirs_record)
    head = _revision(root, "HEAD")
    merge_head = _revision(root, "MERGE_HEAD")
    if head != ours_record.get("commit") or merge_head != theirs_record.get("commit"):
        raise ConflictPreservationError("active clone HEAD or MERGE_HEAD drifted after inventory capture")
    entries = inventory.get("paths")
    if not isinstance(entries, list):
        raise ConflictPreservationError("conflict inventory paths are missing")
    by_path = {
        str(entry.get("path")): entry
        for entry in entries
        if isinstance(entry, Mapping) and isinstance(entry.get("path"), str)
    }
    current = _parse_unmerged(root)
    for path in target_paths:
        entry = by_path.get(path)
        current_entry = current.get(path)
        if entry is None or current_entry is None:
            raise ConflictPreservationError(f"target path is not covered by active conflict inventory: {path}")
        expected_stages = entry.get("stages")
        current_stages = current_entry.get("stages")
        if not isinstance(expected_stages, Mapping) or not isinstance(current_stages, Mapping):
            raise ConflictPreservationError(f"stage inventory is missing for target path: {path}")
        for stage in ("base", "ours", "theirs"):
            expected = expected_stages.get(stage)
            observed = current_stages.get(stage)
            if not isinstance(expected, Mapping) or not isinstance(observed, Mapping):
                raise ConflictPreservationError(f"stage {stage} is missing for target path: {path}")
            if expected.get("oid") != observed.get("oid") or expected.get("mode") != observed.get("mode"):
                raise ConflictPreservationError(f"stage {stage} drifted for target path: {path}")


def _parse_status(repo: Path) -> list[dict[str, str]]:
    raw = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    result: list[dict[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        text = record.decode("utf-8", errors="surrogateescape")
        result.append({"status": text[:2], "path": text[3:]})
    return result


def _name_only(repo: Path, left: str, right: str) -> list[str]:
    raw = _git(repo, ["diff", "--name-only", "-z", left, right]).encode()
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in raw.split(b"\0")
        if item
    ]


def _hunks(
    repo: Path, left: str, right: str, path: str, *, context: int = 3
) -> list[dict[str, str]]:
    output = _git(
        repo,
        ["diff", "--no-color", f"--unified={context}", left, right, "--", path],
    )
    return _parse_hunks(output)


def _resolved_hunks(repo: Path, base: str, path: str) -> list[dict[str, str]]:
    """Read resolved hunks from the index when staged, otherwise the worktree."""
    staged = _git(
        repo,
        ["diff", "--cached", "--no-color", "--unified=0", base, "--", path],
    )
    if staged:
        return _parse_hunks(staged)
    return _hunks(repo, base, "HEAD", path, context=0)


def _parse_hunks(output: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    current: list[str] = []
    header = ""
    for line in output.splitlines(keepends=True):
        if line.startswith("@@"):
            if current:
                text = "".join(current)
                result.append({"header": header, "text": text, "sha256": _sha256(text.encode())})
            header = line.rstrip("\n")
            current = [line]
        elif current:
            current.append(line)
    if current:
        text = "".join(current)
        result.append({"header": header, "text": text, "sha256": _sha256(text.encode())})
    return result


def _has_user_content(path: Mapping[str, object]) -> bool:
    content = path.get("unaffected_content")
    return isinstance(content, list) and any(
        isinstance(item, dict) and item.get("owner") == "user" for item in content
    )


def _inventory_hunk(
    inventory: Mapping[str, object], path: str, source_sha256: str
) -> dict[str, str] | None:
    entries = inventory.get("paths")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, Mapping) or entry.get("path") != path:
            continue
        hunk_groups = entry.get("hunks")
        if not isinstance(hunk_groups, Mapping):
            continue
        for hunks in hunk_groups.values():
            if not isinstance(hunks, list):
                continue
            for hunk in hunks:
                if isinstance(hunk, Mapping) and hunk.get("sha256") == source_sha256:
                    return {
                        key: str(value)
                        for key, value in hunk.items()
                        if isinstance(value, str)
                    }
    return None


def _derived_hunk_lines(source: Mapping[str, str]) -> tuple[str, ...]:
    """Derive preserved additions and context from the captured source hunk."""
    lines = source.get("text", "").splitlines(keepends=True)
    return tuple(
        line
        for line in lines
        if (line.startswith("+") and not line.startswith("+++"))
        or line.startswith(" ")
    )


def _validate_declared_hunk_lines(
    source: Mapping[str, str], identity: Mapping[str, object], path: str
) -> tuple[str, ...]:
    """Reject caller-supplied lines that do not exactly match captured content."""
    derived = _derived_hunk_lines(source)
    declared = identity.get("required_lines")
    if declared is not None:
        if not isinstance(declared, list) or tuple(declared) != derived:
            raise ConflictPreservationError(
                f"{path}: required_lines do not match captured hunk content"
            )
    return derived


def _validate_hunk_identity(
    repo: Path,
    inventory: Mapping[str, object],
    base: str,
    path: str,
    preserved: Mapping[str, object],
) -> None:
    identity = preserved.get("hunk_identity")
    if not isinstance(identity, Mapping):
        raise ConflictPreservationError(f"{path}: hunk identity is required")
    source_sha = identity.get("source_sha256")
    if not isinstance(source_sha, str) or not source_sha:
        raise ConflictPreservationError(f"{path}: hunk source identity is required")
    source = _inventory_hunk(inventory, path, source_sha)
    if source is None:
        raise ConflictPreservationError(f"{path}: hunk is not present in captured inventory")
    source_header = identity.get("source_header", source.get("header"))
    resolved_header = identity.get("resolved_header", source_header)
    if not isinstance(source_header, str) or not isinstance(resolved_header, str):
        raise ConflictPreservationError(f"{path}: hunk range/header identity is required")
    if source.get("header") != source_header:
        raise ConflictPreservationError(f"{path}: captured hunk header does not match source identity")
    source_range = source_header.split()[1] if len(source_header.split()) > 1 else ""
    resolved_range = resolved_header.split()[1] if len(resolved_header.split()) > 1 else ""
    if (
        not source_range
        or not resolved_range
        or not resolved_range.startswith(source_range.split("+")[0])
    ):
        raise ConflictPreservationError(f"{path}: resolved hunk range does not match base range")
    required_lines = _validate_declared_hunk_lines(source, identity, path)
    if not required_lines:
        raise ConflictPreservationError(f"{path}: captured hunk has no preservable content")
    candidates = [
        hunk
        for hunk in _resolved_hunks(repo, base, path)
        if hunk.get("header") == resolved_header
    ]
    if not candidates:
        raise ConflictPreservationError(f"{path}: resolved hunk range/header is missing")
    if not any(
        all(line in hunk.get("text", "") for line in required_lines)
        for hunk in candidates
    ):
        raise ConflictPreservationError(f"{path}: resolved hunk context is missing")


def capture_inventory(
    repo: Path | str,
    *,
    base: str,
    ours: str,
    theirs: str,
    repository: str | None = None,
    user_paths: Sequence[str] = (),
) -> dict[str, object]:
    """Capture immutable stage refs and hunk evidence for one conflicted tree."""
    root = Path(repo).resolve()
    unmerged = _parse_unmerged(root)
    if not unmerged:
        raise ConflictPreservationError("no unmerged paths; conflict inventory is not applicable")
    merge_base = _git(root, ["merge-base", ours, theirs]).strip()
    conflict_paths = sorted(unmerged)
    changed_ours = set(_name_only(root, base, ours))
    changed_theirs = set(_name_only(root, base, theirs))
    user_path_set = set(user_paths)
    for path in user_path_set:
        _safe_relative_path(path)
    all_paths = sorted(changed_ours | changed_theirs | user_path_set)
    paths: list[dict[str, object]] = []
    for path in all_paths:
        if path in unmerged:
            entry = dict(unmerged[path])
            entry["state"] = "unmerged"
            ours_hunks = _hunks(root, base, ours, path, context=0)
            entry["hunks"] = {
                "base_to_ours": ours_hunks,
                "base_to_theirs": _hunks(root, base, theirs, path, context=0),
            }
            entry["unaffected_content"] = [
                {
                    "path": path,
                    "owner": "unknown",
                    "status": "requires-disposition",
                    "side": "ours",
                    "hunk": hunk,
                }
                for hunk in ours_hunks
            ]
        else:
            entry = {
                "path": path,
                "state": (
                    "user-owned-unaffected"
                    if path in user_path_set and path not in changed_ours | changed_theirs
                    else "changed-without-conflict"
                    if path in changed_ours & changed_theirs
                    else "unaffected"
                ),
                "stages": {
                    "base": _tree_blob(root, base, path),
                    "ours": _tree_blob(root, ours, path),
                    "theirs": _tree_blob(root, theirs, path),
                },
                "hunks": {
                    "base_to_ours": _hunks(root, base, ours, path, context=0),
                    "base_to_theirs": _hunks(root, base, theirs, path, context=0),
                },
                "unaffected_content": (
                    [
                        {
                            "path": path,
                            "owner": "user" if path in user_path_set else "unknown",
                            "status": "unaffected",
                            "expected_blob": _tree_blob(root, ours, path),
                        }
                    ]
                    if path not in changed_ours & changed_theirs
                    else [
                        {
                            "path": path,
                            "owner": "user" if path in user_path_set else "unknown",
                            "status": "requires-disposition",
                            "hunks": _hunks(root, base, ours, path, context=0),
                        }
                    ]
                ),
            }
        paths.append(entry)
    return {
        "schema": SCHEMA,
        "repository": repository or str(root),
        "base": {"ref": base, "commit": _git(root, ["rev-parse", base]).strip()},
        "ours": {"ref": ours, "commit": _git(root, ["rev-parse", ours]).strip()},
        "theirs": {"ref": theirs, "commit": _git(root, ["rev-parse", theirs]).strip()},
        "merge_base": merge_base,
        "conflict_paths": conflict_paths,
        "staged_state": "unmerged",
        "status": _parse_status(root),
        "paths": paths,
        "combined_diff": _git(root, ["diff", "--no-color", "--cc", "--unified=3"]),
        "user_owned_unaffected": [
            path for path in paths if _has_user_content(path)
        ],
    }


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_fields(packet: Mapping[str, object], fields: Sequence[str], label: str) -> None:
    missing = [field for field in fields if not _non_empty(packet.get(field))]
    if missing:
        raise ConflictPreservationError(f"{label} missing required fields: {', '.join(missing)}")


def validate_rework_packet(
    packet: Mapping[str, object], *, inventory: Mapping[str, object] | None = None
) -> None:
    """Require cause, mechanism, exact delta, and unaffected content for rework."""
    if packet.get("schema") not in {REWORK_SCHEMA, SCHEMA}:
        raise ConflictPreservationError("unsupported rework preservation schema")
    _require_fields(
        packet,
        (
            "observed_finding",
            "stable_finding_id",
            "selected_cause",
            "expected_mechanism",
            "expected_behavior",
            "exact_edit_delta",
        ),
        "rework packet",
    )
    unaffected = packet.get("unaffected_content")
    if not isinstance(unaffected, list):
        raise ConflictPreservationError("rework packet requires unaffected_content list")
    for item in unaffected:
        if not isinstance(item, Mapping) or not _non_empty(item.get("path")):
            raise ConflictPreservationError("unaffected_content entries require a path")
        if not (
            isinstance(item.get("hunk_identity"), Mapping)
            or isinstance(item.get("expected_blob"), Mapping)
        ):
            raise ConflictPreservationError(
                "unaffected_content entries require hunk_identity or expected_blob"
            )
        identity = item.get("hunk_identity")
        if isinstance(identity, Mapping):
            if not _non_empty(identity.get("source_sha256")) or not _non_empty(
                identity.get("source_header")
            ):
                raise ConflictPreservationError(
                    "unaffected_content hunk_identity requires source_sha256 and source_header"
                )
            if inventory is not None:
                path = str(item["path"])
                source = _inventory_hunk(
                    inventory, path, str(identity["source_sha256"])
                )
                if source is None:
                    raise ConflictPreservationError(
                        f"{path}: hunk is not present in captured inventory"
                    )
                _validate_declared_hunk_lines(source, identity, path)
            elif "required_lines" in identity:
                raise ConflictPreservationError(
                    "unaffected_content hunk_identity requires captured inventory"
                )


def validate_plan(
    inventory: Mapping[str, object],
    plan: Mapping[str, object],
    *,
    repo: Path | str | None = None,
    readback: bool = True,
) -> None:
    """Validate a conflict disposition and optionally its post-resolution tree."""
    if inventory.get("schema") != SCHEMA:
        raise ConflictPreservationError("unsupported conflict inventory schema")
    conflict_paths = inventory.get("conflict_paths")
    entries = inventory.get("paths")
    if not isinstance(conflict_paths, list) or not isinstance(entries, list):
        raise ConflictPreservationError("inventory requires conflict_paths and paths")
    _require_fields(
        plan,
        ("repository", "base", "head", "merge_base", "selected_cause", "expected_mechanism", "exact_edit_delta"),
        "conflict plan",
    )
    if plan.get("repository") != inventory.get("repository"):
        raise ConflictPreservationError("conflict plan repository does not match inventory")
    base_record = inventory.get("base")
    ours_record = inventory.get("ours")
    if not isinstance(base_record, Mapping) or not isinstance(ours_record, Mapping):
        raise ConflictPreservationError("inventory base and ours records are required")
    if plan.get("base") not in {base_record.get("commit"), base_record.get("ref")}:
        raise ConflictPreservationError("conflict plan base does not match inventory")
    if plan.get("head") not in {ours_record.get("commit"), ours_record.get("ref")}:
        raise ConflictPreservationError("conflict plan head does not match inventory")
    if plan.get("merge_base") != inventory.get("merge_base"):
        raise ConflictPreservationError("conflict plan merge_base does not match inventory")
    if repo is not None:
        root = Path(repo).resolve()
        repository = inventory.get("repository")
        if isinstance(repository, str) and Path(repository).is_absolute():
            try:
                if Path(repository).resolve() != root:
                    raise ConflictPreservationError(
                        "conflict inventory repository does not match active clone"
                    )
            except OSError as exc:
                raise ConflictPreservationError(
                    "conflict inventory repository cannot be resolved"
                ) from exc
        if not readback:
            actual_unmerged = set(_parse_unmerged(root))
            if actual_unmerged != {str(path) for path in conflict_paths}:
                raise ConflictPreservationError(
                    "active clone unmerged paths do not match captured inventory"
                )
    planned = plan.get("paths")
    if not isinstance(planned, list):
        raise ConflictPreservationError("conflict plan requires paths list")
    expected_paths = {str(item.get("path")) for item in entries if isinstance(item, Mapping)}
    seen: set[str] = set()
    for item in planned:
        if not isinstance(item, Mapping):
            raise ConflictPreservationError("conflict plan path entries must be objects")
        path = item.get("path")
        if not _non_empty(path):
            raise ConflictPreservationError("conflict plan path entry requires path")
        path_text = str(path)
        seen.add(path_text)
        if item.get("disposition") not in DISPOSITIONS:
            raise ConflictPreservationError(f"{path_text}: disposition must be keep, replace, or manual")
        _require_fields(item, ("owner", "rationale", "expected_edit_delta", "operation"), path_text)
        unaffected = item.get("unaffected_content")
        if not isinstance(unaffected, list):
            raise ConflictPreservationError(f"{path_text}: unaffected_content is required")
        for preserved in unaffected:
            if not isinstance(preserved, Mapping):
                raise ConflictPreservationError(f"{path_text}: malformed unaffected content")
            if preserved.get("path") != path_text:
                raise ConflictPreservationError(
                    f"{path_text}: preserved hunk path does not match plan path"
                )
            identity = preserved.get("hunk_identity")
            if isinstance(identity, Mapping):
                source_sha = identity.get("source_sha256")
                if not isinstance(source_sha, str) or not source_sha:
                    raise ConflictPreservationError(
                        f"{path_text}: hunk source identity is required"
                    )
                source = _inventory_hunk(inventory, path_text, source_sha)
                if source is None:
                    raise ConflictPreservationError(
                        f"{path_text}: hunk is not present in captured inventory"
                    )
                _validate_declared_hunk_lines(source, identity, path_text)
            elif "expected_text" in preserved:
                raise ConflictPreservationError(
                    f"{path_text}: anywhere-text preservation is not accepted; use hunk_identity"
                )
        operation = item.get("operation")
        if operation in WHOLE_FILE_OPERATIONS:
            mapping = item.get("reconstruction_map")
            if not isinstance(mapping, list) or not mapping:
                raise ConflictPreservationError(
                    f"{path_text}: whole-file operation requires reconstruction_map"
                )
            if not _non_empty(item.get("rationale")):
                raise ConflictPreservationError(
                    f"{path_text}: whole-file operation requires explicit rationale"
                )
        if item.get("disposition") == "replace" and (
            not isinstance(item.get("reconstruction_map"), list)
            or not item.get("reconstruction_map")
        ):
            raise ConflictPreservationError(f"{path_text}: replace requires reconstruction_map")
    if seen != expected_paths:
        raise ConflictPreservationError(
            "conflict plan paths must exactly match inventory paths "
            f"(missing={sorted(expected_paths - seen)}, extra={sorted(seen - expected_paths)})"
        )
    rework = plan.get("rework")
    if rework is not None:
        if not isinstance(rework, Mapping):
            raise ConflictPreservationError("rework must be an object")
        validate_rework_packet(rework, inventory=inventory)
    if repo is not None and readback:
        validate_readback(Path(repo), inventory, plan)


def _read_path(repo: Path, path: str) -> bytes:
    _safe_relative_path(path)
    try:
        return (repo / path).read_bytes()
    except OSError as exc:
        raise ConflictPreservationError(f"preserved path is unavailable: {path}") from exc


def validate_readback(repo: Path, inventory: Mapping[str, object], plan: Mapping[str, object]) -> None:
    """Prove that planned unaffected text/blob content remains after resolution."""
    unmerged = _parse_unmerged(repo)
    if unmerged:
        raise ConflictPreservationError(
            f"resolution still has unmerged paths: {', '.join(sorted(unmerged))}"
        )
    planned = plan.get("paths")
    if not isinstance(planned, list):
        raise ConflictPreservationError("readback requires planned paths")
    for item in planned:
        if not isinstance(item, Mapping):
            continue
        path = item.get("path")
        if not isinstance(path, str):
            continue
        current = _read_path(repo, path)
        content = item.get("unaffected_content")
        assert isinstance(content, list)
        for preserved in content:
            if not isinstance(preserved, Mapping):
                raise ConflictPreservationError(f"{path}: malformed unaffected content")
            if preserved.get("path") != path:
                raise ConflictPreservationError(f"{path}: preserved hunk path does not match plan path")
            if isinstance(preserved.get("hunk_identity"), Mapping):
                base_record = inventory.get("base")
                if not isinstance(base_record, Mapping):
                    raise ConflictPreservationError("inventory base record is missing")
                base = base_record.get("commit")
                if not isinstance(base, str):
                    raise ConflictPreservationError("inventory base commit is missing")
                _validate_hunk_identity(repo, inventory, base, path, preserved)
            elif "expected_text" in preserved:
                raise ConflictPreservationError(
                    f"{path}: anywhere-text preservation is not accepted; use hunk_identity"
                )
            expected_blob = preserved.get("expected_blob")
            if isinstance(expected_blob, Mapping):
                oid = expected_blob.get("oid")
                if isinstance(oid, str) and _sha256(current) != _sha256(_blob_bytes(repo, oid)):
                    raise ConflictPreservationError(
                        f"{path}: preserved whole-file content does not match expected blob"
                    )


def _load_json(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConflictPreservationError(f"invalid JSON packet: {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConflictPreservationError(f"JSON packet must be an object: {path}")
    return loaded


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--repo-root", default=".")
    capture.add_argument("--base", required=True)
    capture.add_argument("--ours", required=True)
    capture.add_argument("--theirs", required=True)
    capture.add_argument("--repository")
    capture.add_argument("--user-path", action="append", default=[])
    capture.add_argument("--output")
    validate = commands.add_parser("validate")
    validate.add_argument("--inventory", required=True)
    validate.add_argument("--plan", required=True)
    validate.add_argument("--repo-root")
    rework = commands.add_parser("validate-rework")
    rework.add_argument("--packet", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "capture":
            packet = capture_inventory(
                args.repo_root,
                base=args.base,
                ours=args.ours,
                theirs=args.theirs,
                repository=args.repository,
                user_paths=args.user_path,
            )
            encoded = json.dumps(packet, ensure_ascii=False, indent=2) + "\n"
            if args.output:
                Path(args.output).write_text(encoded, encoding="utf-8")
            else:
                sys.stdout.write(encoded)
            print("CONFLICT_PRESERVATION_CAPTURE=pass", file=sys.stderr)
            return 0
        if args.command == "validate-rework":
            validate_rework_packet(_load_json(Path(args.packet)))
        else:
            inventory = _load_json(Path(args.inventory))
            plan = _load_json(Path(args.plan))
            validate_plan(inventory, plan, repo=args.repo_root)
        print("CONFLICT_PRESERVATION_VALIDATE=pass")
        return 0
    except ConflictPreservationError as exc:
        print(f"CONFLICT_PRESERVATION_ERROR={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
