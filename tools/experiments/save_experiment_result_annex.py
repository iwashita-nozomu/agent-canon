#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Saves one experiment raw artifact tree as one deterministic git-annex archive.
# upstream design ../../documents/experiments/result-log-retention-and-visualization.md defines raw retention and tracked review evidence.
# upstream design ../../agents/workflows/experiment-workflow.md defines canonical experiment identity paths.
# upstream implementation ./experiment_identity.py owns the canonical result/raw path grammar.
# downstream implementation ../../tests/tools/test_save_experiment_result_annex.py validates archive and annex behavior.
# @dependency-end

"""Save one canonical raw artifact tree as one deterministic git-annex archive."""

from __future__ import annotations

import argparse
import errno
import gzip
import hashlib
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

# A direct filesystem invocation places ``tools/experiments`` on ``sys.path``;
# add the repository root so the same public module imports as ``python -m``.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.experiments.experiment_identity import (
    ExperimentIdentity,
    ExperimentIdentityError,
    identity_from_raw_relative_path,
    load_json_file,
    raw_relative_path,
    result_relative_path,
)

EXPERIMENTS = "experiments"
RAW = "raw"
MANIFEST_NAME = "annex_retention_manifest.json"
ANNEX_REPO_ENV = "EXPERIMENT_RAW_ANNEX_REPO"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"
CHUNK_SIZE = 1024 * 1024


class RetentionError(RuntimeError):
    """A user-actionable retention failure."""


@dataclass(frozen=True)
class SourceFile:
    """One regular raw source file and its archive identity."""

    source: Path
    archive_path: str
    size: int
    sha256: str
    executable: bool


@dataclass(frozen=True)
class ArchiveEntry:
    """One normalized archive directory or regular-file entry."""

    archive_path: str
    source: Path | None
    is_dir: bool
    executable: bool = False


@dataclass(frozen=True)
class EvidenceFile:
    """One tracked compact result file binding review evidence to raw retention."""

    source: Path
    repository_path: str
    size: int
    sha256: str
    executable: bool

    def manifest_record(self) -> dict[str, object]:
        """Return the canonical path-and-digest retention binding."""
        return {
            "mode": "executable" if self.executable else "regular",
            "path": self.repository_path,
            "sha256": self.sha256,
            "size": self.size,
        }


@dataclass(frozen=True)
class RawIdentity:
    """Validated raw input and its canonical tracked result evidence."""

    source_root: Path
    identity: ExperimentIdentity
    raw_dir: Path
    raw_relative: Path
    result_relative: Path
    summary: EvidenceFile
    run_manifest: EvidenceFile
    source_branch: str
    source_commit: str
    source_dirty_paths: tuple[str, ...]


@dataclass(frozen=True)
class AnnexState:
    """Pre-mutation state needed for bounded rollback."""

    head: str
    branch: str
    gitattributes_exists: bool
    gitattributes_bytes: bytes | None
    gitattributes_mode: int | None
    created_dirs: tuple[Path, ...]


@dataclass(frozen=True)
class ArchiveResult:
    """Published archive metadata."""

    archive_path: Path
    commit: str
    key: str
    size: int
    sha256: str


def _command(
    argv: list[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command without invoking a shell."""
    result = subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        rendered = " ".join(argv)
        raise RetentionError(f"{rendered} failed: {detail}")
    return result


def _git(repo: Path, args: list[str], *, check: bool = True) -> str:
    """Run git and return stripped stdout."""
    return _command(["git", *args], cwd=repo, check=check).stdout.strip()


def _annex(repo: Path, args: list[str]) -> str:
    """Run git-annex and return stripped stdout."""
    return _command(["git", "annex", *args], cwd=repo).stdout.strip()


def _canonical_json(value: object) -> bytes:
    """Encode the retention manifest in canonical JSON form."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_file(path: Path) -> tuple[int, str]:
    """Read one regular file once and return its byte count and digest."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _source_git_provenance(source_root: Path) -> tuple[str, str, tuple[str, ...]]:
    """Capture source branch, commit, and dirty paths without modifying source."""
    branch_result = _command(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=source_root,
        check=False,
    )
    branch = branch_result.stdout.strip() or "HEAD"
    commit = _git(source_root, ["rev-parse", "HEAD"])
    status = _git(source_root, ["status", "--porcelain=v1", "--untracked-files=all"])
    dirty_paths: list[str] = []
    for line in status.splitlines():
        if len(line) >= 4:
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            dirty_paths.append(path)
    return branch, commit, tuple(sorted(dirty_paths))


def _is_lfs_pointer(path: Path) -> bool:
    """Return whether a regular file has the canonical Git-LFS pointer shape."""
    with path.open("rb") as handle:
        prefix = handle.read(4096)
    if not prefix.startswith(LFS_POINTER_PREFIX):
        return False
    lines = prefix.splitlines()
    if len(lines) < 3:
        return False
    return (
        lines[1].startswith(b"oid sha256:")
        and lines[2].startswith(b"size ")
        and lines[1][len(b"oid sha256:") :].strip().isalnum()
        and lines[2][len(b"size ") :].strip().isdigit()
    )


def _lstat(path: Path) -> os.stat_result:
    """Return lstat data, preserving symlink and special-file detection."""
    try:
        return path.lstat()
    except FileNotFoundError as exc:
        raise RetentionError(f"source path disappeared: {path}") from exc


def _ensure_regular(path: Path, *, label: str) -> os.stat_result:
    """Require a regular non-LFS file and return its lstat record."""
    info = _lstat(path)
    if stat.S_ISLNK(info.st_mode):
        raise RetentionError(f"{label} contains a symlink: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise RetentionError(f"{label} contains a special file: {path}")
    if _is_lfs_pointer(path):
        raise RetentionError(f"{label} contains a Git-LFS pointer: {path}")
    return info


def _validate_source_components(source_root: Path, relative: Path) -> None:
    """Reject absolute/escaping paths and symlinked source components."""
    if relative.is_absolute() or ".." in relative.parts:
        raise RetentionError(f"source-relative path is invalid: {relative}")
    current = source_root
    for component in relative.parts:
        current = current / component
        if not os.path.lexists(current):
            break
        info = _lstat(current)
        if stat.S_ISLNK(info.st_mode):
            raise RetentionError(f"source path contains a symlink: {current}")


def _tracked_evidence(source_root: Path, path: Path, *, label: str) -> EvidenceFile:
    """Require one compact evidence file to be tracked and equal to source HEAD."""
    relative = path.relative_to(source_root)
    _validate_source_components(source_root, relative)
    info = _ensure_regular(path, label=label)
    relative_text = relative.as_posix()
    tracked = _command(
        ["git", "ls-files", "--error-unmatch", "--", relative_text],
        cwd=source_root,
        check=False,
    )
    if tracked.returncode != 0:
        raise RetentionError(f"{label} must be tracked: {relative_text}")
    clean = _command(
        ["git", "diff", "--quiet", "HEAD", "--", relative_text],
        cwd=source_root,
        check=False,
    )
    if clean.returncode != 0:
        raise RetentionError(
            f"{label} must match source commit before retention: {relative_text}"
        )
    size, digest = _sha256_file(path)
    return EvidenceFile(
        source=path,
        repository_path=relative_text,
        size=size,
        sha256=digest,
        executable=bool(info.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)),
    )


def _parse_raw_identity(source_root: Path, raw_dir: Path) -> RawIdentity:
    """Validate one canonical raw path and its compact tracked evidence binding."""
    if not os.path.lexists(raw_dir):
        raise RetentionError(f"raw-dir must be an existing directory: {raw_dir}")
    raw_info = _lstat(raw_dir)
    if stat.S_ISLNK(raw_info.st_mode):
        raise RetentionError(f"raw-dir contains a symlink: {raw_dir}")
    if not stat.S_ISDIR(raw_info.st_mode):
        raise RetentionError(f"raw-dir must be an existing directory: {raw_dir}")
    try:
        raw_relative = raw_dir.relative_to(source_root)
    except ValueError as exc:
        raise RetentionError("raw-dir must be inside source repo root") from exc
    _validate_source_components(source_root, raw_relative)
    try:
        identity = identity_from_raw_relative_path(raw_relative)
    except ExperimentIdentityError as exc:
        raise RetentionError(str(exc)) from exc
    if raw_relative != raw_relative_path(identity):
        raise RetentionError(f"raw-dir has an invalid identity: {raw_relative}")

    result_relative = result_relative_path(identity)
    result_dir = source_root / result_relative
    summary_path = result_dir / "summary.json"
    run_manifest_path = result_dir / "run_manifest.json"
    summary = _tracked_evidence(source_root, summary_path, label="summary evidence")
    run_manifest = _tracked_evidence(
        source_root,
        run_manifest_path,
        label="run manifest evidence",
    )

    try:
        summary_payload = load_json_file(summary_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RetentionError("summary evidence must be strict JSON") from exc
    if not isinstance(summary_payload, Mapping):
        raise RetentionError("summary evidence must be a JSON object")
    if summary_payload.get("run_id") != identity.run_name:
        raise RetentionError("summary run_id does not match raw-dir identity")

    try:
        manifest_payload = load_json_file(run_manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RetentionError("run manifest evidence must be strict JSON") from exc
    if not isinstance(manifest_payload, Mapping):
        raise RetentionError("run manifest evidence must be a JSON object")
    try:
        manifest_identity = ExperimentIdentity.from_dict(manifest_payload)
    except (ExperimentIdentityError, TypeError) as exc:
        raise RetentionError("run manifest identity is invalid") from exc
    if manifest_identity != identity:
        raise RetentionError("run manifest identity does not match raw-dir identity")
    raw_binding = manifest_payload.get("raw_artifacts")
    if not isinstance(raw_binding, Mapping) or set(raw_binding) != {"path", "retention"}:
        raise RetentionError("run manifest must contain the canonical raw_artifacts binding")
    if raw_binding.get("path") != raw_relative.as_posix():
        raise RetentionError("run manifest raw path does not match raw-dir identity")
    retention = raw_binding.get("retention")
    if not isinstance(retention, Mapping) or set(retention) != {"state"}:
        raise RetentionError("run manifest raw retention state is invalid")
    if retention.get("state") != "unarchived":
        raise RetentionError("run manifest raw retention state must be unarchived")

    source_branch, source_commit, source_dirty_paths = _source_git_provenance(source_root)
    return RawIdentity(
        source_root=source_root,
        identity=identity,
        raw_dir=raw_dir,
        raw_relative=raw_relative,
        result_relative=result_relative,
        summary=summary,
        run_manifest=run_manifest,
        source_branch=source_branch,
        source_commit=source_commit,
        source_dirty_paths=source_dirty_paths,
    )


def _scan_source_tree(
    raw: RawIdentity,
) -> tuple[tuple[ArchiveEntry, ...], tuple[SourceFile, ...]]:
    """Collect exactly one raw tree without following links."""
    entries: dict[str, ArchiveEntry] = {}
    source_files: list[SourceFile] = []

    def visit(directory: Path, archive_directory: str) -> None:
        info = _lstat(directory)
        if stat.S_ISLNK(info.st_mode):
            raise RetentionError(f"raw tree contains a symlink: {directory}")
        if not stat.S_ISDIR(info.st_mode):
            raise RetentionError(f"raw path is not a directory: {directory}")
        entries[archive_directory] = ArchiveEntry(archive_directory, directory, True)
        children = sorted(os.scandir(directory), key=lambda item: item.name)
        for child in children:
            child_path = directory / child.name
            child_archive = f"{archive_directory}/{child.name}"
            child_info = _lstat(child_path)
            if child.name == MANIFEST_NAME:
                raise RetentionError(f"raw tree reserves {MANIFEST_NAME}: {child_path}")
            if stat.S_ISDIR(child_info.st_mode):
                visit(child_path, child_archive)
                continue
            _ensure_regular(child_path, label="raw tree")
            size, digest = _sha256_file(child_path)
            executable = bool(
                child_info.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            )
            entries[child_archive] = ArchiveEntry(
                child_archive,
                child_path,
                False,
                executable,
            )
            source_files.append(
                SourceFile(
                    source=child_path,
                    archive_path=child_archive,
                    size=size,
                    sha256=digest,
                    executable=executable,
                )
            )

    raw_archive = raw.raw_relative.as_posix()
    visit(raw.raw_dir, raw_archive)
    for parent in (
        Path(EXPERIMENTS),
        Path(EXPERIMENTS) / raw.identity.topic,
        Path(EXPERIMENTS) / raw.identity.topic / RAW,
        Path(EXPERIMENTS) / raw.identity.topic / RAW / raw.identity.variant,
    ):
        entries[parent.as_posix()] = ArchiveEntry(
            parent.as_posix(),
            raw.source_root / parent,
            True,
        )
    if not source_files:
        raise RetentionError("raw directory is empty")
    return tuple(sorted(entries.values(), key=lambda item: item.archive_path)), tuple(
        sorted(source_files, key=lambda item: item.archive_path)
    )


def _manifest_bytes(
    raw: RawIdentity,
    entries: Iterable[ArchiveEntry],
    source_files: Iterable[SourceFile],
    archive_relative: Path,
) -> bytes:
    """Build canonical raw retention and compact-evidence binding bytes."""
    raw_files = [
        {
            "mode": "executable" if item.executable else "regular",
            "path": item.archive_path,
            "sha256": item.sha256,
            "size": item.size,
        }
        for item in sorted(source_files, key=lambda item: item.archive_path)
    ]
    raw_directories = sorted(
        entry.archive_path
        for entry in entries
        if entry.is_dir
        and (
            entry.archive_path == raw.raw_relative.as_posix()
            or entry.archive_path.startswith(raw.raw_relative.as_posix() + "/")
        )
    )
    return _canonical_json(
        {
            "append_only": True,
            **raw.identity.to_dict(),
            "archive": {
                "compression": "gzip",
                "gzip_filename": "",
                "gzip_level": 9,
                "gzip_mtime": 0,
                "path": archive_relative.as_posix(),
                "tar_format": "pax",
            },
            "raw": {
                "directory": raw.raw_relative.as_posix(),
                "directories": raw_directories,
                "files": raw_files,
            },
            "schema": "git-annex-raw-retention/v1",
            "source": {
                "branch": raw.source_branch,
                "commit": raw.source_commit,
                "dirty_paths": list(raw.source_dirty_paths),
            },
            "tracked_result_evidence": {
                "directory": raw.result_relative.as_posix(),
                "run_manifest": raw.run_manifest.manifest_record(),
                "summary": raw.summary.manifest_record(),
            },
        }
    ) + b"\n"


def _tar_info(path: str, *, is_dir: bool, size: int = 0) -> tarfile.TarInfo:
    """Create normalized PAX metadata for one archive member."""
    info = tarfile.TarInfo(path)
    info.type = tarfile.DIRTYPE if is_dir else tarfile.REGTYPE
    info.mode = 0o755 if is_dir else 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.size = 0 if is_dir else size
    info.pax_headers = {}
    return info


class _BytesReader:
    """Minimal file-like reader for tarfile's streaming addfile API."""

    def __init__(self, value: bytes) -> None:
        self._value = value
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._value) - self._offset
        start = self._offset
        self._offset = min(len(self._value), self._offset + size)
        return self._value[start : self._offset]


def _write_archive(
    temporary_path: Path,
    entries: tuple[ArchiveEntry, ...],
    source_files: tuple[SourceFile, ...],
    manifest_bytes: bytes,
    manifest_path: str,
) -> None:
    """Stream one deterministic gzip/PAX archive to a same-filesystem temp file."""
    file_by_path = {item.archive_path: item for item in source_files}
    with temporary_path.open("wb") as raw_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_handle,
            compresslevel=9,
            mtime=0,
        ) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode="w|",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for entry in entries:
                    if entry.is_dir:
                        archive.addfile(_tar_info(entry.archive_path, is_dir=True))
                    elif entry.archive_path == manifest_path:
                        info = _tar_info(
                            manifest_path,
                            is_dir=False,
                            size=len(manifest_bytes),
                        )
                        archive.addfile(info, _BytesReader(manifest_bytes))
                    else:
                        source_file = file_by_path[entry.archive_path]
                        info = _tar_info(
                            entry.archive_path,
                            is_dir=False,
                            size=source_file.size,
                        )
                        if source_file.executable:
                            info.mode = 0o755
                        with source_file.source.open("rb") as source_handle:
                            archive.addfile(info, source_handle)
        raw_handle.flush()
        os.fsync(raw_handle.fileno())


def _read_archive(
    archive_path: Path,
    entries: tuple[ArchiveEntry, ...],
    source_files: tuple[SourceFile, ...],
    manifest_bytes: bytes,
    manifest_path: str,
) -> tuple[int, str]:
    """Read every archive member and verify layout, metadata, sizes, and hashes."""
    expected_entries = {entry.archive_path: entry.is_dir for entry in entries}
    expected_files = {item.archive_path: item for item in source_files}
    seen: set[str] = set()
    archive_digest = hashlib.sha256()
    archive_size = 0
    with archive_path.open("rb") as raw_handle:
        while True:
            chunk = raw_handle.read(CHUNK_SIZE)
            if not chunk:
                break
            archive_digest.update(chunk)
            archive_size += len(chunk)
    with tarfile.open(archive_path, mode="r|gz") as archive:
        for member in archive:
            path = member.name
            if path in seen:
                raise RetentionError(f"archive contains duplicate member: {path}")
            seen.add(path)
            if path == manifest_path:
                if not member.isfile() or stat.S_IMODE(member.mode) != 0o644:
                    raise RetentionError("archive manifest metadata is invalid")
                actual = archive.extractfile(member)
                if actual is None or actual.read() != manifest_bytes:
                    raise RetentionError("archive manifest bytes are not canonical")
                continue
            expected_kind = expected_entries.get(path)
            if expected_kind is None:
                raise RetentionError(f"archive contains unexpected member: {path}")
            if expected_kind:
                if not member.isdir() or stat.S_IMODE(member.mode) != 0o755:
                    raise RetentionError(f"archive directory metadata mismatch: {path}")
                continue
            if not member.isfile():
                raise RetentionError(f"archive member should be a regular file: {path}")
            source_file = expected_files[path]
            expected_mode = 0o755 if source_file.executable else 0o644
            if stat.S_IMODE(member.mode) != expected_mode:
                raise RetentionError(f"archive member mode mismatch: {path}")
            stream = archive.extractfile(member)
            if stream is None:
                raise RetentionError(f"cannot read archive member: {path}")
            digest = hashlib.sha256()
            size = 0
            while True:
                chunk = stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
            if size != source_file.size or digest.hexdigest() != source_file.sha256:
                raise RetentionError(f"archive member hash mismatch: {path}")
    if seen != set(expected_entries):
        missing = sorted(set(expected_entries) - seen)
        raise RetentionError(f"archive is missing members: {', '.join(missing)}")
    return archive_size, archive_digest.hexdigest()


def _validate_source_and_annex_roots(source_root: Path, annex_root: Path) -> None:
    """Require two distinct, non-containing roots."""
    if source_root == annex_root:
        raise RetentionError("source repo root and annex repo root must differ")
    if source_root in annex_root.parents or annex_root in source_root.parents:
        raise RetentionError("source repo root and annex repo root must not contain one another")


def _validate_visible_paths(annex_root: Path) -> None:
    """Reject pre-existing visible paths outside the raw archive layout."""
    for root, dirs, files in os.walk(annex_root, topdown=True, followlinks=False):
        root_path = Path(root)
        dirs[:] = sorted(dirs)
        if ".git" in dirs:
            dirs.remove(".git")
        relative_root = root_path.relative_to(annex_root).parts
        if relative_root:
            valid_directory = (
                len(relative_root) == 1 and relative_root[0] == EXPERIMENTS
            ) or (
                len(relative_root) == 2 and relative_root[0] == EXPERIMENTS
            ) or (
                len(relative_root) == 3
                and relative_root[0] == EXPERIMENTS
                and relative_root[2] == RAW
            ) or (
                len(relative_root) == 4
                and relative_root[0] == EXPERIMENTS
                and relative_root[2] == RAW
            )
            if not valid_directory:
                raise RetentionError(
                    "annex repo contains an unexpected visible directory: "
                    + "/".join(relative_root)
                )
        for name in sorted(files):
            path = root_path / name
            relative = path.relative_to(annex_root).as_posix()
            if relative == ".gitattributes":
                continue
            parts = relative.split("/")
            if (
                len(parts) == 5
                and parts[0] == EXPERIMENTS
                and parts[2] == RAW
                and parts[4].endswith(".tar.gz")
                and parts[4] != ".tar.gz"
            ):
                continue
            raise RetentionError(
                f"annex repo contains an unexpected visible path: {relative}"
            )
        for name in list(dirs):
            path = root_path / name
            if path.is_symlink():
                raise RetentionError(
                    f"annex repo contains an unexpected symlink: {path}"
                )


def _validate_annex_repo(annex_root: Path) -> AnnexState:
    """Validate a clean non-bare normal-branch annex worktree."""
    if not annex_root.exists() or not annex_root.is_dir():
        raise RetentionError(f"annex repo is not a directory: {annex_root}")
    if _git(annex_root, ["rev-parse", "--is-inside-work-tree"]) != "true":
        raise RetentionError("annex repo must be a worktree")
    if _git(annex_root, ["rev-parse", "--is-bare-repository"]) != "false":
        raise RetentionError("annex repo must not be bare")
    branch = _git(annex_root, ["branch", "--show-current"])
    if not branch or branch.startswith("experiment-results/"):
        raise RetentionError("annex repo must be on a normal branch")
    status_text = _git(
        annex_root,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    )
    if status_text:
        raise RetentionError("annex repo must have a clean index and worktree")
    refs = _git(annex_root, ["for-each-ref", "--format=%(refname)", "refs/"])
    if any(
        "/experiment-results/" in ref or ref.endswith("/experiment-results")
        for ref in refs.splitlines()
    ):
        raise RetentionError("annex repo must not contain experiment-results/* refs")
    gitattributes = annex_root / ".gitattributes"
    gitattributes_info = _lstat(gitattributes) if os.path.lexists(gitattributes) else None
    if gitattributes_info is not None and (
        stat.S_ISLNK(gitattributes_info.st_mode)
        or not stat.S_ISREG(gitattributes_info.st_mode)
    ):
        raise RetentionError("annex repo .gitattributes must be a regular file")
    _validate_visible_paths(annex_root)
    return AnnexState(
        head=_git(annex_root, ["rev-parse", "HEAD"]),
        branch=branch,
        gitattributes_exists=gitattributes_info is not None,
        gitattributes_bytes=gitattributes.read_bytes() if gitattributes_info else None,
        gitattributes_mode=(
            stat.S_IMODE(gitattributes_info.st_mode) if gitattributes_info else None
        ),
        created_dirs=(),
    )


def _ensure_annex_parent(
    annex_root: Path,
    archive_relative: Path,
    state: AnnexState,
) -> AnnexState:
    """Create only the archive's structural parent directories."""
    created: list[Path] = []
    current = annex_root
    for component in archive_relative.parent.parts:
        current = current / component
        if current.exists():
            if not current.is_dir() or current.is_symlink():
                raise RetentionError(f"archive parent is not a directory: {current}")
            continue
        current.mkdir()
        created.append(current)
    return AnnexState(
        head=state.head,
        branch=state.branch,
        gitattributes_exists=state.gitattributes_exists,
        gitattributes_bytes=state.gitattributes_bytes,
        gitattributes_mode=state.gitattributes_mode,
        created_dirs=tuple(created),
    )


def _restore_gitattributes(annex_root: Path, state: AnnexState) -> None:
    """Restore only the pre-existing .gitattributes bytes and mode."""
    path = annex_root / ".gitattributes"
    if state.gitattributes_exists:
        assert state.gitattributes_bytes is not None
        path.write_bytes(state.gitattributes_bytes)
        assert state.gitattributes_mode is not None
        path.chmod(state.gitattributes_mode)
    elif os.path.lexists(path):
        path.unlink()


def _rollback_precommit(
    annex_root: Path,
    archive_path: Path,
    state: AnnexState,
    *,
    remove_archive: bool,
) -> None:
    """Rollback only this task's archive, index entries, generated attributes, and dirs."""
    archive_relative = archive_path.relative_to(annex_root).as_posix()
    try:
        _command(
            ["git", "update-index", "--force-remove", "--", archive_relative],
            cwd=annex_root,
        )
    except RetentionError:
        pass
    if remove_archive and os.path.lexists(archive_path):
        archive_path.unlink()
    attrs = annex_root / ".gitattributes"
    attrs_changed = (
        state.gitattributes_exists != os.path.lexists(attrs)
        or (
            state.gitattributes_exists
            and os.path.lexists(attrs)
            and attrs.read_bytes() != state.gitattributes_bytes
        )
    )
    if attrs_changed:
        try:
            _command(
                ["git", "update-index", "--force-remove", "--", ".gitattributes"],
                cwd=annex_root,
            )
        except RetentionError:
            pass
    _restore_gitattributes(annex_root, state)
    if state.gitattributes_exists:
        _command(["git", "add", "--", ".gitattributes"], cwd=annex_root)
    for directory in reversed(state.created_dirs):
        try:
            directory.rmdir()
        except OSError:
            pass


def _link_no_replace(temporary_path: Path, archive_path: Path) -> None:
    """Publish a temp archive atomically without replacing a collision."""
    try:
        os.link(temporary_path, archive_path)
    except FileExistsError as exc:
        raise RetentionError(f"archive target already exists: {archive_path}") from exc
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            raise RetentionError(f"archive target already exists: {archive_path}") from exc
        raise
    try:
        directory_fd = os.open(archive_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError:
        archive_path.unlink(missing_ok=True)
        raise


def _key_hash_and_size(key: str) -> tuple[int, str]:
    """Parse the size and SHA256 digest from a SHA256E key."""
    if not key.startswith("SHA256E-s"):
        raise RetentionError(f"annex key is not SHA256E: {key}")
    body = key[len("SHA256E-s") :]
    size_text, separator, digest_with_ext = body.partition("--")
    if not separator or not size_text.isdigit():
        raise RetentionError(f"invalid SHA256E key: {key}")
    digest = digest_with_ext.split(".", 1)[0]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise RetentionError(f"invalid SHA256E digest: {key}")
    return int(size_text), digest


def _verify_annex_content(
    annex_root: Path,
    archive_relative: Path,
    archive_size: int,
    archive_sha256: str,
) -> str:
    """Verify lookupkey, real contentlocation bytes, and full annex fsck."""
    archive_text = archive_relative.as_posix()
    key = _annex(annex_root, ["lookupkey", "--", archive_text])
    key_size, key_hash = _key_hash_and_size(key)
    if key_size != archive_size or key_hash != archive_sha256:
        raise RetentionError("annex SHA256E key does not match the archive")
    location_text = _annex(annex_root, ["contentlocation", key])
    if not location_text:
        raise RetentionError("annex contentlocation is empty")
    location = Path(location_text)
    if not location.is_absolute():
        location = annex_root / location
    location = location.resolve()
    if not location.is_file():
        raise RetentionError(
            f"annex contentlocation is not a regular file: {location}"
        )
    size, digest = _sha256_file(location)
    if size != archive_size or digest != archive_sha256:
        raise RetentionError("annex contentlocation bytes do not match the archive")
    _annex(annex_root, ["fsck", "--", archive_text])
    return key


def _commit_archive(
    annex_root: Path,
    archive_relative: Path,
    raw: RawIdentity,
    *,
    include_gitattributes: bool,
) -> str:
    """Create exactly one normal-branch commit for this raw archive."""
    message = (
        "Retain experiment raw archive: "
        f"{raw.identity.topic}/{raw.identity.variant}/{raw.identity.run_name}"
    )
    paths = [archive_relative.as_posix()]
    if include_gitattributes:
        paths.append(".gitattributes")
    _command(
        ["git", "commit", "--only", "--message", message, "--", *paths],
        cwd=annex_root,
    )
    return _git(annex_root, ["rev-parse", "HEAD"])


def save_raw(raw: RawIdentity, annex_root: Path) -> ArchiveResult:
    """Create, verify, annex, and commit exactly one raw archive."""
    _validate_source_and_annex_roots(raw.source_root, annex_root)
    state = _validate_annex_repo(annex_root)
    archive_relative = (
        Path(EXPERIMENTS)
        / raw.identity.topic
        / RAW
        / raw.identity.variant
        / f"{raw.identity.run_name}.tar.gz"
    )
    archive_path = annex_root / archive_relative
    if os.path.lexists(archive_path):
        raise RetentionError(f"archive target already exists: {archive_path}")
    entries, source_files = _scan_source_tree(raw)
    manifest_relative = raw.raw_relative / MANIFEST_NAME
    entries = tuple(
        sorted(
            (*entries, ArchiveEntry(manifest_relative.as_posix(), None, False)),
            key=lambda item: item.archive_path,
        )
    )
    manifest_bytes = _manifest_bytes(raw, entries, source_files, archive_relative)
    state = _ensure_annex_parent(annex_root, archive_relative, state)
    temporary_path: Path | None = None
    linked_archive = False
    try:
        fd, name = tempfile.mkstemp(
            prefix=f".{archive_path.name}.",
            suffix=".tmp",
            dir=archive_path.parent,
        )
        os.close(fd)
        temporary_path = Path(name)
        _write_archive(
            temporary_path,
            entries,
            source_files,
            manifest_bytes,
            manifest_relative.as_posix(),
        )
        archive_size, archive_sha256 = _read_archive(
            temporary_path,
            entries,
            source_files,
            manifest_bytes,
            manifest_relative.as_posix(),
        )
        _link_no_replace(temporary_path, archive_path)
        linked_archive = True
        temporary_path.unlink(missing_ok=True)
        _annex(
            annex_root,
            ["add", "--backend=SHA256E", "--", archive_relative.as_posix()],
        )
        status_text = _git(
            annex_root,
            ["status", "--porcelain=v1", "--untracked-files=all"],
        )
        changed_paths = {line[3:] for line in status_text.splitlines() if len(line) >= 4}
        allowed_paths = {archive_relative.as_posix()}
        attrs_changed = ".gitattributes" in changed_paths
        if attrs_changed:
            allowed_paths.add(".gitattributes")
        unexpected_paths = changed_paths - allowed_paths
        if unexpected_paths:
            raise RetentionError(
                "annex add changed unexpected paths: "
                + ", ".join(sorted(unexpected_paths))
            )
        key = _verify_annex_content(
            annex_root,
            archive_relative,
            archive_size,
            archive_sha256,
        )
        commit_before = state.head
        commit = _commit_archive(
            annex_root,
            archive_relative,
            raw,
            include_gitattributes=attrs_changed,
        )
        parent = _git(annex_root, ["rev-parse", f"{commit}^"])
        if parent != commit_before or commit == commit_before:
            raise RetentionError("annex commit count is not exactly one")
        _verify_annex_content(
            annex_root,
            archive_relative,
            archive_size,
            archive_sha256,
        )
        _, reread_sha256 = _read_archive(
            archive_path,
            entries,
            source_files,
            manifest_bytes,
            manifest_relative.as_posix(),
        )
        if reread_sha256 != archive_sha256:
            raise RetentionError(
                "postcommit archive reread differs from precommit archive"
            )
        if _git(annex_root, ["branch", "--show-current"]) != state.branch:
            raise RetentionError("annex branch changed during retention")
        if _git(
            annex_root,
            ["status", "--porcelain=v1", "--untracked-files=all"],
        ):
            raise RetentionError("annex worktree is not clean after commit")
        return ArchiveResult(archive_path, commit, key, archive_size, archive_sha256)
    except Exception as exc:
        current_head = _git(annex_root, ["rev-parse", "HEAD"], check=False)
        if current_head == state.head:
            _rollback_precommit(
                annex_root,
                archive_path,
                state,
                remove_archive=linked_archive,
            )
        else:
            raise RetentionError(
                f"archive committed but verification failed; retained commit {current_head}: {exc}"
            ) from exc
        if isinstance(exc, RetentionError):
            raise
        raise RetentionError(str(exc)) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the intentionally small raw-only public CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        action="append",
        required=True,
        type=Path,
        help="Exactly one experiments/<topic>/raw/<variant>/<run_name> directory.",
    )
    parser.add_argument(
        "--annex-repo",
        type=Path,
        help=f"Existing annex worktree (or {ANNEX_REPO_ENV}).",
    )
    parser.add_argument(
        "--source-repo-root",
        type=Path,
        default=Path.cwd(),
        help="Source repository root; defaults to the current directory.",
    )
    args = parser.parse_args(argv)
    if len(args.raw_dir) != 1:
        parser.error("exactly one --raw-dir is required")
    if args.annex_repo is None:
        configured = os.environ.get(ANNEX_REPO_ENV)
        if not configured:
            parser.error(f"--annex-repo or {ANNEX_REPO_ENV} is required")
        args.annex_repo = Path(configured)
    args.raw_dir = args.raw_dir[0]
    return args


def main(argv: list[str] | None = None) -> int:
    """Run the raw retention command."""
    try:
        args = parse_args(argv)
        source_root = args.source_repo_root.resolve()
        annex_root = args.annex_repo.resolve()
        # Preserve the lexical raw path until every component has been checked
        # with lstat; resolving here would hide a symlinked run directory.
        raw_dir = Path(os.path.abspath(args.raw_dir))
        if not source_root.is_dir():
            raise RetentionError(f"source repo root is not a directory: {source_root}")
        if not raw_dir.is_relative_to(source_root):
            raise RetentionError("raw-dir must be inside source repo root")
        raw = _parse_raw_identity(source_root, raw_dir)
        result = save_raw(raw, annex_root)
    except (OSError, RetentionError, subprocess.SubprocessError, ValueError) as exc:
        message = str(exc)
        if "committed but verification failed" in message:
            message = f"{message}; commit is retained and must not be rewound"
        print(message, file=sys.stderr)
        return 2
    print("EXPERIMENT_RAW_STATUS=complete")
    print(f"EXPERIMENT_RAW_ARCHIVE_PATH={result.archive_path}")
    print(f"EXPERIMENT_RAW_COMMIT={result.commit}")
    print(f"EXPERIMENT_RAW_ANNEX_KEY={result.key}")
    print(f"EXPERIMENT_RAW_ARCHIVE_SIZE={result.size}")
    print(f"EXPERIMENT_RAW_ARCHIVE_SHA256={result.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
