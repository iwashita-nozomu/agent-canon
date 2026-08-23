#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Updates flat result-root latest pointers while selecting by variant metadata.
# upstream design ../../documents/experiments/result-log-retention-and-visualization.md defines latest-result pointer policy.
# upstream implementation ./experiment_identity.py owns the identity grammar.
# downstream implementation ../../tests/tools/test_update_latest_result.py validates latest result pointer updates.
# @dependency-end
"""Update flat result-root variant-scoped LATEST pointers."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

if __package__:
    from tools.experiments.experiment_identity import (
        DuplicateJSONKeyError,
        ExperimentIdentity,
        contained_path,
        load_json_file,
        load_json_text,
        report_relative_path,
        validate_segment,
    )
else:
    from experiment_identity import (  # type: ignore[no-redef]
        DuplicateJSONKeyError,
        ExperimentIdentity,
        contained_path,
        load_json_file,
        load_json_text,
        report_relative_path,
        validate_segment,
    )

LATEST_JSON_PREFIX = "LATEST."
LATEST_JSON_SUFFIX = ".json"
LATEST_MD_SUFFIX = ".md"
PointerGeneration = tuple[
    tuple[int, int, str] | None,
    tuple[int, int, str] | None,
]


def _pointer_names(variant: str) -> tuple[str, str]:
    """Return validated root-level pointer names for one variant."""
    variant = validate_segment(variant, "variant")
    return (
        f"{LATEST_JSON_PREFIX}{variant}{LATEST_JSON_SUFFIX}",
        f"{LATEST_JSON_PREFIX}{variant}{LATEST_MD_SUFFIX}",
    )


def _root_topic(result_root: Path) -> str:
    parts = result_root.resolve().parts
    if len(parts) < 3 or parts[-3:] != ("experiments", parts[-2], "result"):
        raise ValueError(
            "result-root must be experiments/<topic>/result (or its absolute path)"
        )
    return validate_segment(parts[-2], "topic")


def _manifest_candidates(result_dir: Path) -> list[Path]:
    return [
        result_dir / name
        for name in ("run_manifest.json", "result_manifest.json")
        if os.path.lexists(result_dir / name)
    ]


def _parse_created_at_utc(value: object, manifest_path: Path) -> datetime:
    """Parse a timezone-aware UTC timestamp from one result manifest."""
    if not isinstance(value, str):
        raise ValueError(f"manifest must contain created_at_utc: {manifest_path}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("manifest created_at_utc is not parseable") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("manifest created_at_utc must be timezone-aware UTC")
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("manifest created_at_utc must use UTC (+00:00 or Z)")
    return parsed.astimezone(UTC)


def _load_result_identity(
    result_dir: Path, topic: str, variant: str
) -> tuple[ExperimentIdentity, dict[str, object], Path]:
    if result_dir.is_symlink() or not result_dir.is_dir():
        raise ValueError(f"result directory must be a real directory: {result_dir}")
    resolved_dir = result_dir.resolve()
    if resolved_dir != result_dir:
        raise ValueError(f"result directory realpath differs: {result_dir}")
    candidates = _manifest_candidates(result_dir)
    if len(candidates) != 1:
        raise ValueError(
            f"exactly one run_manifest.json or result_manifest.json is required: {result_dir}"
        )
    manifest_path = candidates[0]
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError(
            f"manifest must be a regular non-symlink file: {manifest_path}"
        )
    try:
        manifest_path.resolve().relative_to(result_dir.resolve())
    except ValueError as exc:
        raise ValueError(
            f"manifest is outside result directory: {manifest_path}"
        ) from exc
    try:
        payload = load_json_file(manifest_path)
    except (json.JSONDecodeError, DuplicateJSONKeyError) as exc:
        raise ValueError(f"manifest is not valid JSON: {manifest_path}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"manifest must be an object: {manifest_path}")
    identity = ExperimentIdentity.from_dict(payload)
    if identity.topic != topic or identity.variant != variant:
        raise ValueError("manifest identity does not match the selected result variant")
    expected_dir = result_dir.parent / identity.run_name
    if result_dir != expected_dir:
        raise ValueError("result directory name does not match manifest run identity")
    _parse_created_at_utc(payload.get("created_at_utc"), manifest_path)
    return identity, dict(payload), manifest_path


def _result_timestamp(
    result_dir: Path, topic: str, variant: str
) -> tuple[datetime, str]:
    identity, manifest, manifest_path = _load_result_identity(
        result_dir, topic, variant
    )
    return (
        _parse_created_at_utc(manifest["created_at_utc"], manifest_path),
        identity.run_name,
    )


def _prepare_result_root(result_root: Path) -> tuple[Path, str]:
    """Validate and return one real flat result root."""
    result_root = result_root.absolute()
    if len(result_root.parts) < 3 or result_root.parts[-1] != "result":
        raise ValueError(
            "result-root must be experiments/<topic>/result (or its absolute path)"
        )
    repo_root = result_root.parents[2]
    experiments_root = repo_root / "experiments"
    topic_dir = experiments_root / result_root.parts[-2]
    expected_result_root = topic_dir / "result"
    if result_root != expected_result_root:
        raise ValueError(
            "result-root must be experiments/<topic>/result without path traversal"
        )
    topic = validate_segment(result_root.parts[-2], "topic")
    for ancestor in (repo_root, experiments_root, topic_dir, result_root):
        try:
            resolved = contained_path(repo_root, ancestor)
        except ValueError as exc:
            raise ValueError(
                f"result tree path escapes repository: {ancestor}"
            ) from exc
        if ancestor.is_symlink() or resolved != ancestor:
            raise ValueError(
                f"result tree path must not use a symlinked ancestor: {ancestor}"
            )
    return result_root, topic


@contextmanager
def _result_root_lock(result_root: Path):
    """Hold the flat result-root latest-pointer lock without creating a file."""
    directory_fd = os.open(result_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        fcntl.flock(directory_fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(directory_fd, fcntl.LOCK_UN)
    finally:
        os.close(directory_fd)


def _latest_result_dir_unlocked(result_root: Path, topic: str, variant: str) -> Path:
    """Return the newest result matching variant metadata under the flat root."""
    candidates: list[tuple[tuple[datetime, str], Path]] = []
    for path in sorted(result_root.iterdir()):
        if path.name.startswith(LATEST_JSON_PREFIX) and path.name.endswith(
            (LATEST_JSON_SUFFIX, LATEST_MD_SUFFIX)
        ):
            continue
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"result root contains a non-directory entry: {path}")
        validate_segment(path.name, "run_name")
        try:
            timestamp = _result_timestamp(path, topic, variant)
        except ValueError as exc:
            if "manifest identity does not match" in str(exc):
                continue
            raise
        candidates.append((timestamp, path))
    if not candidates:
        raise ValueError(
            f"no result directories for variant {variant!r} under {result_root}"
        )
    return max(candidates, key=lambda item: item[0])[1]


def latest_result_dir(result_root: Path, variant: str) -> Path:
    """Return the newest valid result directory below the flat result root."""
    result_root, topic = _prepare_result_root(result_root)
    validate_segment(variant, "variant")
    with _result_root_lock(result_root):
        return _latest_result_dir_unlocked(result_root, topic, variant)


def _canonical_text(path: Path, result_root: Path) -> str:
    """Return the canonical repository-relative path for a pointer payload."""
    resolved = path.resolve()
    root = result_root.parents[2]
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"pointer path is outside repository root: {path}") from exc


def _latest_payload(
    result_root: Path, result_dir: Path, variant: str
) -> dict[str, object]:
    topic = _root_topic(result_root)
    identity, _, manifest_path = _load_result_identity(result_dir, topic, variant)
    report_path = result_root.parents[2] / report_relative_path(identity)
    summary_path = result_dir / "summary" / "summary.json"
    visual_candidates = (
        result_dir / "summary" / "visual_diagnostics" / "report.html",
        result_dir / "summary" / "report.html",
        result_dir / "visual_diagnostics" / "report.html",
        result_dir / "report.html",
    )
    visual_report = next((path for path in visual_candidates if path.is_file()), None)
    return {
        "schema": "agentcanon.experiment-latest/v2",
        **identity.to_dict(),
        "result_root": _canonical_text(result_root, result_root),
        "latest_result": _canonical_text(result_dir, result_root),
        "latest_result_name": identity.run_name,
        "result_manifest": _canonical_text(manifest_path, result_root),
        "summary_json": _canonical_text(summary_path, result_root)
        if summary_path.is_file()
        else None,
        "visual_report_html": _canonical_text(visual_report, result_root)
        if visual_report
        else None,
        "experiment_report": _canonical_text(report_path, result_root),
    }


def _write_atomic_bytes(path: Path, content: bytes) -> None:
    """Write one pointer file atomically in its owning result root."""
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _pointer_snapshot(path: Path) -> tuple[bytes | None, tuple[int, int, str] | None]:
    """Read one pointer and its inode/content generation token."""
    if not os.path.lexists(path):
        return None, None
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"latest pointer must be a regular file: {path}")
    content = path.read_bytes()
    stat_result = path.stat()
    digest = hashlib.sha256(content).hexdigest()
    return content, (stat_result.st_ino, stat_result.st_size, digest)


def _pointer_generation(result_root: Path, variant: str) -> PointerGeneration:
    """Return the inode/content generation for both latest pointers."""
    json_name, markdown_name = _pointer_names(variant)
    _, json_generation = _pointer_snapshot(result_root / json_name)
    _, markdown_generation = _pointer_snapshot(result_root / markdown_name)
    return json_generation, markdown_generation


def _read_current_pointer(
    result_root: Path,
    topic: str,
    variant: str,
) -> tuple[tuple[datetime, str], Path, PointerGeneration] | None:
    """Read and validate one existing JSON/Markdown pointer pair."""
    json_name, markdown_name = _pointer_names(variant)
    json_path = result_root / json_name
    markdown_path = result_root / markdown_name
    json_bytes, json_generation = _pointer_snapshot(json_path)
    markdown_bytes, markdown_generation = _pointer_snapshot(markdown_path)
    if (json_bytes is None) != (markdown_bytes is None):
        raise ValueError(f"{json_name} and {markdown_name} must be published together")
    if json_bytes is None or markdown_bytes is None:
        return None
    try:
        payload = load_json_text(json_bytes)
    except (json.JSONDecodeError, DuplicateJSONKeyError) as exc:
        raise ValueError(f"{json_name} is not valid strict JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{json_name} must contain an object")
    if payload.get("schema") != "agentcanon.experiment-latest/v2":
        raise ValueError(f"{json_name} has an unsupported schema")
    identity = ExperimentIdentity.from_dict(payload)
    if identity.topic != topic or identity.variant != variant:
        raise ValueError(f"{json_name} identity does not match the selected variant")
    expected_result = result_root / identity.run_name
    expected_latest = expected_result.relative_to(result_root.parents[2]).as_posix()
    if payload.get("latest_result") != expected_latest:
        raise ValueError(f"{json_name} latest_result does not match its identity")
    if payload.get("latest_result_name") != identity.run_name:
        raise ValueError(f"{json_name} latest_result_name does not match its identity")
    try:
        markdown = markdown_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{markdown_name} is not valid UTF-8") from exc
    if markdown != _latest_markdown(payload):
        raise ValueError(f"{json_name} and {markdown_name} identities are inconsistent")
    timestamp = _result_timestamp(expected_result, topic, variant)
    return (
        timestamp,
        expected_result,
        (json_generation, markdown_generation),
    )


def _restore_pointer(path: Path, content: bytes | None) -> None:
    """Restore one pointer path without following a replacement symlink."""
    if content is None:
        if os.path.lexists(path):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"cannot remove replaced latest pointer: {path}")
            path.unlink()
        return
    _write_atomic_bytes(path, content)


def _publish_pointer_pair(
    result_root: Path,
    variant: str,
    payload: Mapping[str, object],
    expected_generation: PointerGeneration,
) -> None:
    """CAS-check and publish JSON/Markdown as one locked pair."""
    json_name, markdown_name = _pointer_names(variant)
    json_path = result_root / json_name
    markdown_path = result_root / markdown_name
    json_before, _ = _pointer_snapshot(json_path)
    markdown_before, _ = _pointer_snapshot(markdown_path)
    if _pointer_generation(result_root, variant) != expected_generation:
        raise ValueError("LATEST pointer generation changed during selection")
    json_content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    markdown_content = _latest_markdown(payload).encode("utf-8")
    json_fd, json_temp = tempfile.mkstemp(prefix=f".{json_name}.", dir=result_root)
    markdown_fd, markdown_temp = tempfile.mkstemp(
        prefix=f".{markdown_name}.", dir=result_root
    )
    json_temp_path = Path(json_temp)
    markdown_temp_path = Path(markdown_temp)
    json_replaced = False
    try:
        with os.fdopen(json_fd, "wb") as handle:
            handle.write(json_content)
            handle.flush()
            os.fsync(handle.fileno())
        with os.fdopen(markdown_fd, "wb") as handle:
            handle.write(markdown_content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(json_temp_path, json_path)
        json_replaced = True
        os.replace(markdown_temp_path, markdown_path)
    except BaseException:
        if json_replaced:
            _restore_pointer(json_path, json_before)
        raise
    finally:
        for temporary_path in (json_temp_path, markdown_temp_path):
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _latest_markdown(payload: Mapping[str, object]) -> str:
    identity_payload = payload.get("identity")
    if isinstance(identity_payload, Mapping):
        identity_text = json.dumps(
            dict(identity_payload), sort_keys=True, separators=(",", ":")
        )
    else:
        identity_text = str(identity_payload)
    return "\n".join(
        [
            "# Latest Experiment Result",
            "",
            f"- identity: `{identity_text}`",
            f"- result: `{payload['latest_result']}`",
            f"- manifest: `{payload['result_manifest']}`",
            f"- report: `{payload['experiment_report']}`",
            f"- summary: `{payload['summary_json']}`",
            f"- visual report: `{payload['visual_report_html']}`",
            "",
        ]
    )


def update_latest_result(
    result_root: Path, result_dir: Path | None, variant: str
) -> Path:
    """Select and publish one deterministic latest pointer pair under the flat root lock."""
    if result_dir is not None:
        if result_root.is_symlink():
            raise ValueError(f"result root must not be a symlink: {result_root}")
        preliminary_root = result_root.resolve()
        validate_segment(variant, "variant")
        if result_dir.is_symlink():
            raise ValueError(f"result directory must not be a symlink: {result_dir}")
        preliminary_result_dir = result_dir.resolve()
        if preliminary_result_dir.parent != preliminary_root:
            raise ValueError(
                "explicit result directory must be directly below result root"
            )
    result_root, topic = _prepare_result_root(result_root)
    validate_segment(variant, "variant")
    with _result_root_lock(result_root):
        generation = _pointer_generation(result_root, variant)
        if result_dir is None:
            selected_result_dir = _latest_result_dir_unlocked(
                result_root, topic, variant
            )
        else:
            if result_dir.is_symlink():
                raise ValueError(
                    f"result directory must not be a symlink: {result_dir}"
                )
            original_result_dir = result_dir
            selected_result_dir = result_dir.resolve()
            if selected_result_dir != original_result_dir:
                raise ValueError(
                    f"result directory realpath differs: {original_result_dir}"
                )
            expected_parent = result_root
            if selected_result_dir.parent != expected_parent:
                raise ValueError(
                    "explicit result directory must be directly below result root"
                )
            if not selected_result_dir.is_dir():
                raise ValueError(
                    f"result directory does not exist: {selected_result_dir}"
                )
        selected_timestamp = _result_timestamp(selected_result_dir, topic, variant)
        current = _read_current_pointer(result_root, topic, variant)
        if current is not None:
            current_timestamp, current_result_dir, current_generation = current
            if current_generation != generation:
                raise ValueError("LATEST pointer generation changed during selection")
            if selected_timestamp <= current_timestamp:
                return current_result_dir
        payload = _latest_payload(result_root, selected_result_dir, variant)
        _publish_pointer_pair(result_root, variant, payload, generation)
        return selected_result_dir


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--result-dir", type=Path, dest="result_dir")
    return parser.parse_args()


def main() -> None:
    """Run the per-variant LATEST pointer CLI."""
    args = _parse_args()
    try:
        selected = update_latest_result(args.result_root, args.result_dir, args.variant)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    print(f"latest_result_dir={selected}")


if __name__ == "__main__":
    main()
