# @dependency-start
# contract reference
# responsibility Owns atomic publication, provenance snapshots, serialization, and digest readback.
# upstream design ../../documents/experiment/experiment-provenance.template.toml defines reproducibility fields.
# upstream design ../../../documents/conventions/DOCSTRING_GUIDE.md owns semantic Docstring clauses.
# upstream implementation artifact_schema.py defines published artifact schemas.
# @dependency-end

"""
Publish experiment artifacts through one atomic and readback-oriented boundary.

責務は JSON/JSONL serialization、config/environment provenance、atomic replacement、manifest
digest 作成です。case execution と run acceptance の判断は別 module が所有します。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from artifact_schema import (
    CONFIG_SNAPSHOT_NAME,
    ENVIRONMENT_SNAPSHOT_NAME,
    FAILURE_EVIDENCE_NAME,
    RESULT_CASES_NAME,
    RESULT_MANIFEST_NAME,
    RESULT_SUMMARY_NAME,
    ArtifactEntry,
    ArtifactManifest,
    RunSummary,
)
from case_model import CaseResult


def utc_now() -> str:
    """
    Return an RFC3339 UTC timestamp for artifact provenance.

    Returns:
        A timezone-aware timestamp string with a trailing `Z`.

    Side effects:
        Reads the system clock only.
    """
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def atomic_write_text(path: Path, content: str) -> None:
    """
    Replace one artifact atomically after flushing its temporary sibling.

    Args:
        path: Destination artifact owned by this run.
        content: Complete UTF-8 payload to publish.

    Raises:
        OSError: If the destination directory or atomic replacement fails.

    Side effects:
        Creates a temporary file, flushes it, and replaces `path` atomically.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """
    Serialize one JSON object and publish it through atomic_write_text.

    Args:
        path: Destination JSON artifact.
        payload: JSON-compatible object owned by the producer.

    Raises:
        TypeError: If payload contains a non-JSON-serializable value.

    Side effects:
        Atomically creates or replaces the destination file.
    """
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def sha256_file(path: Path) -> str:
    """
    Calculate the content digest used by artifact-manifest.json.

    Args:
        path: Existing file whose bytes are read.

    Returns:
        Lowercase SHA-256 digest.

    Raises:
        OSError: If the file cannot be read.

    Side effects:
        Reads the complete file without mutating it.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_provenance_snapshots(run_dir: Path, template_dir: Path) -> tuple[str, str]:
    """
    Snapshot config and runtime identity before case execution.

    Args:
        run_dir: Result directory receiving the snapshots.
        template_dir: Materialized experiment directory containing config.yaml.

    Returns:
        Snapshot filenames in stable config-then-environment order.

    Raises:
        OSError: If a required snapshot cannot be written.

    Side effects:
        Atomically writes config_snapshot.json and environment.json.
    """
    config_path = template_dir / "config.yaml"
    config_content = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    atomic_write_json(
        run_dir / CONFIG_SNAPSHOT_NAME,
        {
            "path": "config.yaml",
            "state": "present" if config_content else "missing",
            "sha256": hashlib.sha256(config_content.encode("utf-8")).hexdigest(),
            "content": config_content,
        },
    )
    atomic_write_json(
        run_dir / ENVIRONMENT_SNAPSHOT_NAME,
        {
            "python": sys.version,
            "python_executable": sys.executable,
            "cwd": str(Path.cwd()),
            "run_dir": str(run_dir.resolve()),
            "managed_runner_manifest": os.environ.get("EXPERIMENT_RUN_MANIFEST", ""),
            "resource_visibility": os.environ.get("CUDA_VISIBLE_DEVICES", "caller-managed"),
        },
    )
    return CONFIG_SNAPSHOT_NAME, ENVIRONMENT_SNAPSHOT_NAME


def write_case_records(run_dir: Path, records: tuple[CaseResult, ...]) -> None:
    """
    Serialize every typed case record as one atomic JSONL artifact.

    Args:
        run_dir: Result directory receiving cases.jsonl.
        records: Complete ordered case records, including failures.

    Side effects:
        Replaces cases.jsonl atomically, including an empty file for empty CASES.
    """
    content = "".join(
        json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    atomic_write_text(run_dir / RESULT_CASES_NAME, content)


def write_failure_evidence(
    run_dir: Path,
    *,
    status: str,
    failure_class: str,
    records: tuple[CaseResult, ...],
    close_condition: str,
    visualization_error: str = "not_applicable",
) -> None:
    """
    Preserve failure-cause classification and rerun closure evidence.

    Args:
        run_dir: Result directory receiving failure-evidence.json.
        status: Current run state.
        failure_class: Stable cause category selected by the owner boundary.
        records: Failed or blocked typed case records.
        close_condition: Necessary action before the failure is considered closed.
        visualization_error: Explicit visualization error or not_applicable.

    Side effects:
        Atomically replaces failure-evidence.json.
    """
    atomic_write_json(
        run_dir / FAILURE_EVIDENCE_NAME,
        {
            "state": status,
            "failure_class": failure_class,
            "records": [record.to_dict() for record in records],
            "visualization_error": visualization_error,
            "close_condition": close_condition,
        },
    )


def write_summary(run_dir: Path, summary: RunSummary) -> None:
    """
    Publish the typed RunSummary as summary.json atomically.

    Args:
        run_dir: Result directory receiving summary.json.
        summary: Complete run-level schema selected by orchestration.

    Side effects:
        Atomically replaces summary.json.
    """
    atomic_write_json(run_dir / RESULT_SUMMARY_NAME, summary.to_dict())


def write_artifact_manifest(run_dir: Path, summary: RunSummary) -> None:
    """
    Publish digests for every completed run artifact except the manifest itself.

    Args:
        run_dir: Result directory containing the complete run snapshot.
        summary: Final run state whose identity is recorded in the manifest.

    Raises:
        OSError: If a materialized artifact cannot be read or the manifest fails
            to replace atomically.

    Side effects:
        Reads all regular files in run_dir and atomically writes the manifest.
    """
    entries = tuple(
        ArtifactEntry(
            path=path.name,
            sha256=sha256_file(path),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(run_dir.iterdir())
        if path.name != RESULT_MANIFEST_NAME and path.is_file()
    )
    manifest = ArtifactManifest(
        run_id=summary.run_id,
        state=summary.status,
        artifacts=entries,
    )
    atomic_write_json(run_dir / RESULT_MANIFEST_NAME, manifest.to_dict())
