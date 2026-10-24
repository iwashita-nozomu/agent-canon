# @dependency-start
# contract implementation
# responsibility Delivers successful main-push Eval artifacts to the existing archive publisher.
# upstream design ../../../documents/runtime/runtime-log-archive.md main Eval delivery boundary
# upstream implementation ./log_repository_identity.py configured source identity
# upstream implementation ../artifacts/runtime_artifacts.py bounded external staging paths
# upstream implementation ../container/bootstrap_runtime.py canonical runtime manifest reader
# upstream design ../../../bootstrap/host/manifest.toml transport resource quotas
# downstream implementation ./runtime_log_archive_git.py existing sync and archive-eval owner
# downstream implementation ../../../tests/agent_tools/test_github_eval_delivery.py validates source binding and delivery
# @dependency-end
"""GitHub artifact input for the existing host archive sync operation."""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import zipfile
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from tools.runtime.archive.log_repository_identity import (
    normalize_remote,
    source_remote,
)
from tools.runtime.artifacts.runtime_artifacts import (
    RuntimeArtifactBoundary,
    RuntimeArtifactError,
    runtime_spool_boundary,
)
from tools.runtime.container.bootstrap_runtime import BootstrapError, load_manifest

WORKFLOW_PATH = ".github/workflows/agent-canon-static-gates.yml"
ARTIFACT_NAME = re.compile(r"agent-canon-main-eval-([1-9][0-9]*)-([1-9][0-9]*)")
SHA = re.compile(r"[0-9a-f]{40}")
STAGE_NAME = re.compile(r"(main-[0-9a-f]{40}-[1-9][0-9]*-[1-9][0-9]*)-[1-9][0-9]*")
# Three uint16-sized metadata fields plus a fixed central-directory header.
ZIP_MEMBER_METADATA_BYTES = 3 * ((1 << 16) - 1) + 64
CHUNK_BYTES = 65536
JsonObject = dict[str, object]
ApiReader = Callable[[str, Path], JsonObject]
Downloader = Callable[[str, Path, Path, int], None]
Publisher = Callable[[Path, str], None]


class GitHubEvalDeliveryError(ValueError):
    """Selected main Eval evidence could not be safely delivered."""


@dataclass(frozen=True)
class EvalArtifactLimits:
    """Use existing runtime byte budgets and the archive's member quota."""

    artifact_bytes: int
    entry_bytes: int
    runtime_bytes: int
    members: int

    @classmethod
    def from_manifest(cls, path: Path) -> EvalArtifactLimits:
        try:
            manifest, _ = load_manifest(path)
            container = _object(manifest.get("container"))
            archive = _object(manifest.get("archive"))
            return cls(
                artifact_bytes=_positive_limit(container.get("task_state_quota_bytes")),
                entry_bytes=_positive_limit(container.get("task_log_quota_bytes")),
                runtime_bytes=_positive_limit(container.get("runtime_quota_bytes")),
                members=_positive_limit(archive.get("main_eval_max_members")),
            )
        except (BootstrapError, OSError, ValueError) as exc:
            raise GitHubEvalDeliveryError("github_eval_limits_invalid") from exc


def _positive_limit(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GitHubEvalDeliveryError("github_eval_limits_invalid")
    return value


class _MetadataReader(io.BufferedReader):
    """Bound ZipFile's metadata read before it constructs its entry list."""

    def __init__(self, raw: io.RawIOBase, limit: int) -> None:
        super().__init__(raw)
        self._length = os.fstat(raw.fileno()).st_size
        self._limit = limit
        self._metadata_remaining: int | None = limit

    def payload_reads(self, limit: int) -> None:
        self._metadata_remaining = None
        self._limit = limit

    def read(self, size: int | None = -1) -> bytes:
        requested = (
            size
            if size is not None and size >= 0
            else max(0, self._length - self.tell())
        )
        if requested > self._limit:
            raise GitHubEvalDeliveryError("github_eval_metadata_quota_exceeded")
        if (
            self._metadata_remaining is not None
            and requested > self._metadata_remaining
        ):
            raise GitHubEvalDeliveryError("github_eval_metadata_quota_exceeded")
        data = super().read(size)
        if self._metadata_remaining is not None:
            self._metadata_remaining -= len(data)
        return data


@contextmanager
def _delivery_lock(boundary: RuntimeArtifactBoundary) -> Generator[None, None, None]:
    path = boundary.resolve("locks/github-main-evals.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield


def _directory_bytes(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        observed = child.lstat()
        if stat.S_ISREG(observed.st_mode):
            total += observed.st_size
    return total


def _cleanup_stage(stage: Path, boundary: RuntimeArtifactBoundary) -> None:
    try:
        checked = boundary.resolve(stage)
        if checked.exists():
            shutil.rmtree(checked)
    except (OSError, RuntimeArtifactError):
        print(f"RUNTIME_LOG_ARCHIVE_MAIN_EVAL_CLEANUP_RETAINED={stage.name}")


def _object(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise GitHubEvalDeliveryError("github_eval_json_object_required")
    return cast(JsonObject, value)


def _github_json(endpoint: str, source_root: Path) -> JsonObject:
    try:
        result = subprocess.run(
            ["gh", "api", "--hostname", "github.com", endpoint],
            cwd=source_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as exc:
        raise GitHubEvalDeliveryError("github_eval_transport_unavailable") from exc
    if result.returncode:
        raise GitHubEvalDeliveryError(f"github_eval_metadata_unavailable:{endpoint}")
    try:
        return _object(json.loads(result.stdout))
    except (ValueError, TypeError) as exc:
        raise GitHubEvalDeliveryError("github_eval_metadata_invalid") from exc


def _download(
    endpoint: str, destination: Path, source_root: Path, max_bytes: int
) -> None:
    process = subprocess.Popen(
        ["gh", "api", "--hostname", "github.com", endpoint],
        cwd=source_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        if process.stdout is None:
            raise GitHubEvalDeliveryError("github_eval_download_unavailable")
        total = 0
        with destination.open("wb") as output:
            while block := process.stdout.read(CHUNK_BYTES):
                total += len(block)
                if total > max_bytes:
                    raise GitHubEvalDeliveryError("github_eval_download_quota_exceeded")
                output.write(block)
        if process.wait() != 0:
            raise GitHubEvalDeliveryError(f"github_eval_download_failed:{endpoint}")
    finally:
        if process.poll() is None:
            process.kill()
        if process.stdout is not None:
            process.stdout.close()
        process.wait()


def _digest(read: Callable[[int], bytes]) -> str:
    digest = hashlib.sha256()
    while block := read(CHUNK_BYTES):
        digest.update(block)
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return _digest(stream.read)


def _member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or not path.parts
        or not (
            name == "collection.json"
            or path.parts[0] in {"eval-results", "producer-logs"}
        )
    ):
        raise GitHubEvalDeliveryError("github_eval_artifact_path_invalid")
    return path


def _extract(
    archive: Path,
    destination: Path,
    limits: EvalArtifactLimits,
    boundary: RuntimeArtifactBoundary,
) -> None:
    metadata_limit = min(
        limits.entry_bytes, (limits.members + 1) * ZIP_MEMBER_METADATA_BYTES
    )
    with (
        io.FileIO(archive, "r") as raw,
        _MetadataReader(raw, metadata_limit) as reader,
        zipfile.ZipFile(reader) as bundle,
    ):
        members = bundle.infolist()
        if len(members) > limits.members:
            raise GitHubEvalDeliveryError("github_eval_member_quota_exceeded")
        reader.payload_reads(limits.entry_bytes)
        files: dict[str, zipfile.ZipInfo] = {}
        names: set[str] = set()
        total = 0
        for member in members:
            relative = _member_path(member.filename)
            name = relative.as_posix()
            if name in names:
                raise GitHubEvalDeliveryError("github_eval_duplicate_member")
            names.add(name)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode) or (
                stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))
            ):
                raise GitHubEvalDeliveryError("github_eval_artifact_type_invalid")
            if member.flag_bits & 1:
                raise GitHubEvalDeliveryError("github_eval_encrypted_member")
            if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                raise GitHubEvalDeliveryError("github_eval_unsupported_compression")
            if member.file_size < 0 or member.file_size > limits.entry_bytes:
                raise GitHubEvalDeliveryError("github_eval_entry_quota_exceeded")
            total += member.file_size
            if member.is_dir():
                continue
            if name != "collection.json" and len(relative.parts) < 2:
                raise GitHubEvalDeliveryError("github_eval_artifact_path_invalid")
            files[name] = member
        if total > limits.artifact_bytes:
            raise GitHubEvalDeliveryError("github_eval_expansion_quota_exceeded")
        temporary = boundary.resolve(destination.parent / "entry.part")
        temporary_bytes = temporary.stat().st_size if temporary.exists() else 0
        used = _directory_bytes(boundary.root)
        required = used - _directory_bytes(destination) - temporary_bytes + total
        if required > limits.runtime_bytes and required > used:
            raise GitHubEvalDeliveryError("github_eval_runtime_quota_exceeded")
        if destination.exists():
            for old in destination.rglob("*"):
                checked = boundary.resolve(old)
                if (
                    checked.is_file()
                    and checked.relative_to(destination).as_posix() not in files
                ):
                    raise GitHubEvalDeliveryError("github_eval_stage_changed")
        destination.mkdir(parents=True, exist_ok=True)
        for name, member in files.items():
            target = boundary.resolve(destination / name)
            if target.exists():
                if not target.is_file() or target.stat().st_size != member.file_size:
                    raise GitHubEvalDeliveryError("github_eval_stage_changed")
                with bundle.open(member) as original:
                    if _digest(original.read) != _sha256(target):
                        raise GitHubEvalDeliveryError("github_eval_stage_changed")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            count = 0
            with bundle.open(member) as source, temporary.open("wb") as output:
                while block := source.read(CHUNK_BYTES):
                    count += len(block)
                    if count > member.file_size or count > limits.entry_bytes:
                        raise GitHubEvalDeliveryError(
                            "github_eval_entry_quota_exceeded"
                        )
                    output.write(block)
            if count != member.file_size:
                raise GitHubEvalDeliveryError("github_eval_entry_size_mismatch")
            temporary.replace(target)


def _collection(spool: Path, run_id: str, head: str) -> None:
    try:
        collection = _object(
            json.loads((spool / "collection.json").read_text(encoding="utf-8"))
        )
    except (OSError, ValueError) as exc:
        raise GitHubEvalDeliveryError("github_eval_collection_invalid") from exc
    tree_digest = collection.get("source_tree_digest_before")
    if (
        collection.get("schema") != "agent_canon.eval_collection.v1"
        or collection.get("run_id") != run_id
        or collection.get("status") != "collected"
        or collection.get("source_tree_unchanged") is not True
        or any(
            collection.get(key) != head
            for key in (
                "source_head_before",
                "source_head_after",
                "agent_canon_commit",
            )
        )
        or any(
            collection.get(key) != ""
            for key in (
                "source_git_status_before",
                "source_git_status_after",
            )
        )
        or not isinstance(tree_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", tree_digest)
        or tree_digest != collection.get("source_tree_digest_after")
    ):
        raise GitHubEvalDeliveryError("github_eval_collection_source_mismatch")
    families = _object(collection.get("family_status"))
    matrix = collection.get("producer_matrix")
    if (
        not families
        or any(value != "pass" for value in families.values())
        or not isinstance(matrix, list)
    ):
        raise GitHubEvalDeliveryError("github_eval_collection_failed_family")
    rows = [_object(value) for value in cast(list[object], matrix)]
    if (
        len(rows) != len(families)
        or any(not isinstance(row.get("name"), str) for row in rows)
        or any(
            type(row.get("exit")) is not int
            or row.get("exit") != 0
            or row.get("status") != "pass"
            for row in rows
        )
        or {row.get("name"): row.get("status") for row in rows} != families
    ):
        raise GitHubEvalDeliveryError("github_eval_collection_matrix_mismatch")
    exported = _object(collection.get("exported_files"))
    for directory, key in (
        ("eval-results", "eval_results"),
        ("producer-logs", "producer_logs"),
    ):
        count = sum(path.is_file() for path in (spool / directory).rglob("*"))
        if count == 0 or exported.get(key) != count:
            raise GitHubEvalDeliveryError("github_eval_collection_incomplete")


def deliver_main_evals(
    *,
    source_root: Path,
    runtime_root: Path,
    published_run_ids: set[str],
    limits: EvalArtifactLimits,
    publish: Publisher,
    api: ApiReader = _github_json,
    download: Downloader = _download,
) -> int:
    """Drain trusted main artifacts under one bounded, replayable transport lease."""
    identity = normalize_remote(source_remote(source_root))
    match = re.fullmatch(r"github\.com/([a-z0-9_.-]+/[a-z0-9_.-]+)", identity)
    if not match:
        return 0
    repository = match[1]
    boundary = runtime_spool_boundary(source_root, runtime_root, create=True)
    stage_root = boundary.resolve("spool/github-main-evals")
    stage_root.mkdir(parents=True, exist_ok=True)
    with _delivery_lock(boundary):
        for previous in stage_root.iterdir():
            selected = STAGE_NAME.fullmatch(previous.name)
            if selected and selected[1] in published_run_ids:
                _cleanup_stage(previous, boundary)
        repo_id = api(f"repos/{repository}", source_root).get("id")
        if type(repo_id) is not int or repo_id <= 0:
            raise GitHubEvalDeliveryError("github_eval_repository_invalid")
        workflow = api(
            f"repos/{repository}/actions/workflows/agent-canon-static-gates.yml",
            source_root,
        )
        if workflow.get("path") != WORKFLOW_PATH or type(workflow.get("id")) is not int:
            raise GitHubEvalDeliveryError("github_eval_workflow_mismatch")
        delivered, failures, first_failure = 0, 0, ""
        page = 1
        while True:
            listing = api(
                f"repos/{repository}/actions/artifacts?per_page=100&page={page}",
                source_root,
            )
            artifacts = listing.get("artifacts")
            if not isinstance(artifacts, list):
                raise GitHubEvalDeliveryError("github_eval_artifact_listing_invalid")
            items = cast(list[object], artifacts)
            for value in items:
                artifact = _object(value)
                name = artifact.get("name")
                matched = (
                    ARTIFACT_NAME.fullmatch(name) if isinstance(name, str) else None
                )
                if not matched:
                    continue
                run_number, attempt = map(int, matched.groups())
                summary = _object(artifact.get("workflow_run"))
                head = summary.get("head_sha")
                if (
                    summary.get("repository_id") != repo_id
                    or summary.get("head_repository_id") != repo_id
                    or summary.get("head_branch") != "main"
                ):
                    continue
                if not isinstance(head, str) or not SHA.fullmatch(head):
                    raise GitHubEvalDeliveryError("github_eval_head_invalid")
                run_id = f"main-{head}-{run_number}-{attempt}"
                if run_id in published_run_ids:
                    continue
                try:
                    run = api(
                        f"repos/{repository}/actions/runs/{run_number}/attempts/{attempt}",
                        source_root,
                    )
                    if (
                        run.get("event") != "push"
                        or run.get("head_branch") != "main"
                        or run.get("path") != WORKFLOW_PATH
                        or run.get("workflow_id") != workflow.get("id")
                        or _object(run.get("repository")).get("id") != repo_id
                        or _object(run.get("head_repository")).get("id") != repo_id
                    ):
                        continue
                    if run.get("status") != "completed":
                        continue
                    if (
                        summary.get("id") != run_number
                        or run.get("id") != run_number
                        or run.get("run_attempt") != attempt
                        or run.get("head_sha") != head
                    ):
                        raise GitHubEvalDeliveryError("github_eval_run_mismatch")
                    artifact_id, size, digest = (
                        artifact.get("id"),
                        artifact.get("size_in_bytes"),
                        artifact.get("digest"),
                    )
                    if type(artifact_id) is not int or artifact_id <= 0:
                        raise GitHubEvalDeliveryError("github_eval_artifact_id_invalid")
                    if (
                        type(size) is not int
                        or size <= 0
                        or size > limits.artifact_bytes
                    ):
                        raise GitHubEvalDeliveryError(
                            "github_eval_archive_quota_exceeded"
                        )
                    if not isinstance(digest, str) or not re.fullmatch(
                        r"sha256:[0-9a-f]{64}", digest
                    ):
                        raise GitHubEvalDeliveryError(
                            "github_eval_artifact_digest_missing"
                        )
                    stage = boundary.resolve(stage_root / f"{run_id}-{artifact_id}")
                    stage.mkdir(exist_ok=True)
                    archive = boundary.resolve(stage / "artifact.zip")
                    partial = boundary.resolve(stage / "artifact.zip.part")
                    if (
                        partial.is_file()
                        and partial.stat().st_size > limits.artifact_bytes
                    ):
                        raise GitHubEvalDeliveryError(
                            "github_eval_archive_quota_exceeded"
                        )
                    if (
                        not archive.exists()
                        and partial.is_file()
                        and "sha256:" + _sha256(partial) == digest
                    ):
                        partial.replace(archive)
                    if not archive.exists():
                        if artifact.get("expired") is not False:
                            raise GitHubEvalDeliveryError(
                                "github_eval_artifact_expired"
                            )
                        previous_bytes = (
                            partial.stat().st_size if partial.exists() else 0
                        )
                        available = (
                            limits.runtime_bytes
                            - _directory_bytes(boundary.root)
                            + previous_bytes
                        )
                        if size > available:
                            raise GitHubEvalDeliveryError(
                                "github_eval_runtime_quota_exceeded"
                            )
                        download(
                            f"repos/{repository}/actions/artifacts/{artifact_id}/zip",
                            partial,
                            source_root,
                            min(limits.artifact_bytes, available),
                        )
                        if "sha256:" + _sha256(partial) != digest:
                            raise GitHubEvalDeliveryError(
                                "github_eval_artifact_digest_mismatch"
                            )
                        partial.replace(archive)
                    if (
                        archive.stat().st_size > limits.artifact_bytes
                        or "sha256:" + _sha256(archive) != digest
                    ):
                        raise GitHubEvalDeliveryError(
                            "github_eval_artifact_digest_mismatch"
                        )
                    spool = boundary.resolve(stage / "spool")
                    _extract(archive, spool, limits, boundary)
                    _collection(spool, run_id, head)
                    publish(spool, run_id)
                    published_run_ids.add(run_id)
                    delivered += 1
                    _cleanup_stage(stage, boundary)
                except (
                    OSError,
                    ValueError,
                    EOFError,
                    OverflowError,
                    NotImplementedError,
                    RuntimeArtifactError,
                    zipfile.BadZipFile,
                ) as exc:
                    reason = (
                        str(exc)
                        if isinstance(exc, GitHubEvalDeliveryError)
                        else type(exc).__name__
                    )
                    failures += 1
                    if not first_failure:
                        first_failure = f"{run_id}:{reason}"
                    print(f"RUNTIME_LOG_ARCHIVE_MAIN_EVAL_PENDING={run_id}:{reason}")
            if len(items) < 100:
                break
            page += 1
        if failures:
            raise GitHubEvalDeliveryError(
                f"github_eval_delivery_pending:{failures}:{first_failure}"
            )
        return delivered
