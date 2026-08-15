#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Saves one experiment result as one deterministic git-annex archive.
# upstream design ../../documents/experiments/result-log-retention-and-visualization.md defines result retention.
# upstream design ../../agents/workflows/experiment-workflow.md defines experiment result paths.
# downstream implementation ../../tests/tools/test_save_experiment_result_annex.py validates archive and annex behavior.
# @dependency-end

"""Save one experiment result tree as one deterministic git-annex archive."""

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
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

EXPERIMENTS = "experiments"
REPORT = "report"
RESULT = "result"
MANIFEST_NAME = "annex_retention_manifest.json"
ANNEX_REPO_ENV = "EXPERIMENT_RESULT_ANNEX_REPO"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"
CHUNK_SIZE = 1024 * 1024


class RetentionError(RuntimeError):
    """A user-actionable retention failure."""


@dataclass(frozen=True)
class SourceFile:
    """One regular source file and its archive identity."""

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
class ResultIdentity:
    """Validated result and optional report paths."""

    source_root: Path
    result_dir: Path
    result_relative: Path
    topic: str
    run_name: str
    report_path: Path | None
    source_branch: str
    source_commit: str
    source_dirty_paths: tuple[str, ...]
    run_manifest_sha256: str | None


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
    """Encode the retention manifest in the repository's canonical JSON form."""
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


def _ensure_regular(path: Path, *, label: str) -> None:
    """Require a regular non-LFS file."""
    info = _lstat(path)
    if stat.S_ISLNK(info.st_mode):
        raise RetentionError(f"{label} contains a symlink: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise RetentionError(f"{label} contains a special file: {path}")
    if _is_lfs_pointer(path):
        raise RetentionError(f"{label} contains a Git-LFS pointer: {path}")


def _validate_source_components(source_root: Path, relative: Path) -> None:
    """Reject symlinked path components in a source-relative path."""
    current = source_root
    for component in relative.parts:
        current = current / component
        info = _lstat(current)
        if stat.S_ISLNK(info.st_mode):
            raise RetentionError(f"source path contains a symlink: {current}")


def _parse_result_identity(source_root: Path, result_dir: Path) -> ResultIdentity:
    """Validate the exact result path and discover its optional report."""
    if not result_dir.exists() or not result_dir.is_dir():
        raise RetentionError(f"result-dir must be an existing directory: {result_dir}")
    result_relative = result_dir.relative_to(source_root)
    parts = result_relative.parts
    if len(parts) != 4 or parts[0] != EXPERIMENTS or parts[2] != RESULT:
        raise RetentionError(
            "result-dir must be experiments/<topic>/result/<run_name>: "
            f"{result_relative}"
        )
    if any(not part or part in {".", ".."} for part in (parts[1], parts[3])):
        raise RetentionError(f"result-dir has an invalid topic or run name: {result_relative}")
    _validate_source_components(source_root, result_relative)
    report_path = source_root / EXPERIMENTS / REPORT / f"{parts[3]}.md"
    if os.path.lexists(report_path):
        _validate_source_components(source_root, report_path.relative_to(source_root))
        _ensure_regular(report_path, label="report")
    else:
        report_path = None
    source_branch, source_commit, source_dirty_paths = _source_git_provenance(source_root)
    run_manifest = result_dir / "run_manifest.json"
    if os.path.lexists(run_manifest):
        _ensure_regular(run_manifest, label="run manifest")
        _, run_manifest_sha256 = _sha256_file(run_manifest)
    else:
        run_manifest_sha256 = None
    return ResultIdentity(
        source_root=source_root,
        result_dir=result_dir,
        result_relative=result_relative,
        topic=parts[1],
        run_name=parts[3],
        report_path=report_path,
        source_branch=source_branch,
        source_commit=source_commit,
        source_dirty_paths=source_dirty_paths,
        run_manifest_sha256=run_manifest_sha256,
    )


def _scan_source_tree(identity: ResultIdentity) -> tuple[tuple[ArchiveEntry, ...], tuple[SourceFile, ...]]:
    """Collect a complete result tree and optional report without following links."""
    entries: dict[str, ArchiveEntry] = {}
    source_files: list[SourceFile] = []

    def visit(directory: Path, archive_directory: str) -> None:
        info = _lstat(directory)
        if stat.S_ISLNK(info.st_mode):
            raise RetentionError(f"result tree contains a symlink: {directory}")
        if not stat.S_ISDIR(info.st_mode):
            raise RetentionError(f"result path is not a directory: {directory}")
        entries[archive_directory] = ArchiveEntry(archive_directory, directory, True)
        children = sorted(os.scandir(directory), key=lambda item: item.name)
        for child in children:
            child_path = directory / child.name
            child_archive = f"{archive_directory}/{child.name}"
            child_info = _lstat(child_path)
            if child.name == MANIFEST_NAME:
                raise RetentionError(
                    f"result tree reserves {MANIFEST_NAME}: {child_path}"
                )
            if stat.S_ISDIR(child_info.st_mode):
                visit(child_path, child_archive)
            else:
                _ensure_regular(child_path, label="result tree")
                size, digest = _sha256_file(child_path)
                entries[child_archive] = ArchiveEntry(child_archive, child_path, False)
                source_files.append(
                    SourceFile(
                        child_path,
                        child_archive,
                        size,
                        digest,
                        bool(child_info.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)),
                    )
                )

    result_archive = identity.result_relative.as_posix()
    visit(identity.result_dir, result_archive)
    entries[EXPERIMENTS] = ArchiveEntry(EXPERIMENTS, identity.source_root / EXPERIMENTS, True)
    entries[f"{EXPERIMENTS}/{identity.topic}"] = ArchiveEntry(
        f"{EXPERIMENTS}/{identity.topic}",
        identity.source_root / EXPERIMENTS / identity.topic,
        True,
    )
    entries[f"{EXPERIMENTS}/{identity.topic}/{RESULT}"] = ArchiveEntry(
        f"{EXPERIMENTS}/{identity.topic}/{RESULT}",
        identity.source_root / EXPERIMENTS / identity.topic / RESULT,
        True,
    )

    if identity.report_path is not None:
        report_archive = f"{EXPERIMENTS}/{REPORT}/{identity.run_name}.md"
        report_parent = f"{EXPERIMENTS}/{REPORT}"
        entries[report_parent] = ArchiveEntry(
            report_parent,
            identity.source_root / EXPERIMENTS / REPORT,
            True,
        )
        _ensure_regular(identity.report_path, label="report")
        size, digest = _sha256_file(identity.report_path)
        entries[report_archive] = ArchiveEntry(report_archive, identity.report_path, False)
        report_info = _lstat(identity.report_path)
        source_files.append(
            SourceFile(
                identity.report_path,
                report_archive,
                size,
                digest,
                bool(report_info.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)),
            )
        )

    result_file_count = sum(
        item.archive_path.startswith(f"{result_archive}/") for item in source_files
    )
    if result_file_count == 0:
        raise RetentionError("result directory is effectively empty; a report alone is not enough")

    return tuple(sorted(entries.values(), key=lambda item: item.archive_path)), tuple(
        sorted(source_files, key=lambda item: item.archive_path)
    )


def _manifest_bytes(
    identity: ResultIdentity,
    entries: Iterable[ArchiveEntry],
    source_files: Iterable[SourceFile],
    archive_relative: Path,
) -> bytes:
    """Build canonical manifest bytes for all archived regular files."""
    file_records = [
        {
            "mode": "executable" if item.executable else "regular",
            "path": item.archive_path,
            "sha256": item.sha256,
            "size": item.size,
        }
        for item in sorted(source_files, key=lambda item: item.archive_path)
    ]
    report_path = (
        f"{EXPERIMENTS}/{REPORT}/{identity.run_name}.md"
        if identity.report_path is not None
        else None
    )
    return _canonical_json(
        {
            "append_only": True,
            "archive": {
                "compression": "gzip",
                "gzip_filename": "",
                "gzip_level": 9,
                "gzip_mtime": 0,
                "path": archive_relative.as_posix(),
                "tar_format": "pax",
            },
            "directories": sorted(
                entry.archive_path for entry in entries if entry.is_dir
            ),
            "files": file_records,
            "report": report_path,
            "report_present": report_path is not None,
            "run": {
                "name": identity.run_name,
                "result_dir": identity.result_relative.as_posix(),
                "topic": identity.topic,
            },
            "schema": "git-annex-result-retention/v1",
            "source": {
                "branch": identity.source_branch,
                "commit": identity.source_commit,
                "dirty_paths": list(identity.source_dirty_paths),
                "run_manifest_sha256": identity.run_manifest_sha256,
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


def _write_archive(
    temporary_path: Path,
    entries: tuple[ArchiveEntry, ...],
    source_files: tuple[SourceFile, ...],
    manifest_bytes: bytes,
    manifest_path: str,
) -> None:
    """Stream one deterministic gzip/PAX archive to a same-filesystem temp file."""
    file_by_path = {item.archive_path: item for item in source_files}
    with temporary_path.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=0,
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                for entry in entries:
                    if entry.is_dir:
                        archive.addfile(_tar_info(entry.archive_path, is_dir=True))
                    elif entry.archive_path == manifest_path:
                        manifest_info = _tar_info(
                            manifest_path,
                            is_dir=False,
                            size=len(manifest_bytes),
                        )
                        archive.addfile(manifest_info, _BytesReader(manifest_bytes))
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
        raw.flush()
        os.fsync(raw.fileno())


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


def _read_archive(
    archive_path: Path,
    entries: tuple[ArchiveEntry, ...],
    source_files: tuple[SourceFile, ...],
    manifest_bytes: bytes,
    manifest_path: str,
) -> tuple[int, str]:
    """Read every archive member and verify layout, manifest, sizes, and hashes."""
    expected_entries = {entry.archive_path: entry.is_dir for entry in entries}
    expected_files = {item.archive_path: item for item in source_files}
    seen: set[str] = set()
    archive_digest = hashlib.sha256()
    archive_size = 0
    with archive_path.open("rb") as raw:
        while True:
            chunk = raw.read(CHUNK_SIZE)
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
                if not member.isfile():
                    raise RetentionError("archive manifest is not a regular file")
                actual = archive.extractfile(member)
                if actual is None or actual.read() != manifest_bytes:
                    raise RetentionError("archive manifest bytes are not canonical")
                continue
            expected_kind = expected_entries.get(path)
            if expected_kind is None:
                raise RetentionError(f"archive contains unexpected member: {path}")
            if expected_kind and not member.isdir():
                raise RetentionError(f"archive member should be a directory: {path}")
            if not expected_kind:
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
    status = _git(annex_root, ["status", "--porcelain=v1", "--untracked-files=all"])
    if status:
        raise RetentionError("annex repo must have a clean index and worktree")
    refs = _git(annex_root, ["for-each-ref", "--format=%(refname)", "refs/"])
    if any("/experiment-results/" in ref or ref.endswith("/experiment-results") for ref in refs.splitlines()):
        raise RetentionError("annex repo must not contain experiment-results/* refs")
    gitattributes = annex_root / ".gitattributes"
    gitattributes_info = _lstat(gitattributes) if os.path.lexists(gitattributes) else None
    if gitattributes_info is not None and (
        stat.S_ISLNK(gitattributes_info.st_mode) or not stat.S_ISREG(gitattributes_info.st_mode)
    ):
        raise RetentionError("annex repo .gitattributes must be a regular file")
    _validate_visible_paths(annex_root)
    return AnnexState(
        head=_git(annex_root, ["rev-parse", "HEAD"]),
        branch=branch,
        gitattributes_exists=gitattributes_info is not None,
        gitattributes_bytes=gitattributes.read_bytes() if gitattributes_info else None,
        gitattributes_mode=stat.S_IMODE(gitattributes_info.st_mode) if gitattributes_info else None,
        created_dirs=(),
    )


def _validate_visible_paths(annex_root: Path) -> None:
    """Reject pre-existing visible paths outside the annex archive layout."""
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
                and relative_root[2] == RESULT
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
                len(parts) == 4
                and parts[0] == EXPERIMENTS
                and parts[2] == RESULT
                and parts[3].endswith(".tar.gz")
                and parts[3] != ".tar.gz"
            ):
                continue
            raise RetentionError(f"annex repo contains an unexpected visible path: {relative}")
        for name in list(dirs):
            path = root_path / name
            if path.is_symlink():
                raise RetentionError(f"annex repo contains an unexpected symlink: {path}")


def _ensure_annex_parent(annex_root: Path, archive_relative: Path, state: AnnexState) -> AnnexState:
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
    return AnnexState(**{**state.__dict__, "created_dirs": tuple(created)})


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


def _verify_annex_content(annex_root: Path, archive_relative: Path, archive_size: int, archive_sha256: str) -> str:
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
        raise RetentionError(f"annex contentlocation is not a regular file: {location}")
    size, digest = _sha256_file(location)
    if size != archive_size or digest != archive_sha256:
        raise RetentionError("annex contentlocation bytes do not match the archive")
    _annex(annex_root, ["fsck", "--", archive_text])
    return key


def _commit_archive(
    annex_root: Path,
    archive_relative: Path,
    identity: ResultIdentity,
    *,
    include_gitattributes: bool,
) -> str:
    """Create exactly one normal-branch commit for this archive."""
    message = f"Retain experiment result archive: {identity.topic}/{identity.run_name}"
    paths = [archive_relative.as_posix()]
    if include_gitattributes:
        paths.append(".gitattributes")
    _command(
        ["git", "commit", "--only", "--message", message, "--", *paths],
        cwd=annex_root,
    )
    return _git(annex_root, ["rev-parse", "HEAD"])


def save_result(identity: ResultIdentity, annex_root: Path) -> ArchiveResult:
    """Create, verify, annex, and commit one result archive."""
    _validate_source_and_annex_roots(identity.source_root, annex_root)
    state = _validate_annex_repo(annex_root)
    archive_relative = Path(EXPERIMENTS) / identity.topic / RESULT / f"{identity.run_name}.tar.gz"
    archive_path = annex_root / archive_relative
    if os.path.lexists(archive_path):
        raise RetentionError(f"archive target already exists: {archive_path}")
    entries, source_files = _scan_source_tree(identity)
    manifest_relative = identity.result_relative / MANIFEST_NAME
    entries = tuple(
        sorted(
            (*entries, ArchiveEntry(manifest_relative.as_posix(), None, False)),
            key=lambda item: item.archive_path,
        )
    )
    manifest_bytes = _manifest_bytes(identity, entries, source_files, archive_relative)
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
        _annex(annex_root, ["add", "--backend=SHA256E", "--", archive_relative.as_posix()])
        status = _git(annex_root, ["status", "--porcelain=v1", "--untracked-files=all"])
        changed_paths = {line[3:] for line in status.splitlines() if len(line) >= 4}
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
        key = _verify_annex_content(annex_root, archive_relative, archive_size, archive_sha256)
        commit_before = state.head
        commit = _commit_archive(
            annex_root,
            archive_relative,
            identity,
            include_gitattributes=attrs_changed,
        )
        parent = _git(annex_root, ["rev-parse", f"{commit}^"])
        if parent != commit_before or commit == commit_before:
            raise RetentionError("annex commit count is not exactly one")
        _verify_annex_content(annex_root, archive_relative, archive_size, archive_sha256)
        _, reread_sha256 = _read_archive(
            archive_path,
            entries,
            source_files,
            manifest_bytes,
            manifest_relative.as_posix(),
        )
        if reread_sha256 != archive_sha256:
            raise RetentionError("postcommit archive reread differs from precommit archive")
        if _git(annex_root, ["branch", "--show-current"]) != state.branch:
            raise RetentionError("annex branch changed during retention")
        if _git(annex_root, ["status", "--porcelain=v1", "--untracked-files=all"]):
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
    """Parse the intentionally small public CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result-dir",
        action="append",
        required=True,
        type=Path,
        help="Exactly one experiments/<topic>/result/<run_name> directory.",
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
    if len(args.result_dir) != 1:
        parser.error("exactly one --result-dir is required")
    if args.annex_repo is None:
        configured = os.environ.get(ANNEX_REPO_ENV)
        if not configured:
            parser.error(f"--annex-repo or {ANNEX_REPO_ENV} is required")
        args.annex_repo = Path(configured)
    args.result_dir = args.result_dir[0]
    return args


def main(argv: list[str] | None = None) -> int:
    """Run the retention command."""
    try:
        args = parse_args(argv)
        source_root = args.source_repo_root.resolve()
        annex_root = args.annex_repo.resolve()
        # Keep the lexical result path intact until every component has been
        # checked with lstat.  Resolving here would hide a symlink that points
        # at a different run before _parse_result_identity can reject it.
        result_dir = Path(os.path.abspath(args.result_dir))
        if not source_root.is_dir():
            raise RetentionError(f"source repo root is not a directory: {source_root}")
        if not result_dir.is_relative_to(source_root):
            raise RetentionError("result-dir must be inside source repo root")
        identity = _parse_result_identity(source_root, result_dir)
        result = save_result(identity, annex_root)
    except (OSError, RetentionError, subprocess.SubprocessError, ValueError) as exc:
        message = str(exc)
        if "committed but verification failed" in message:
            message = f"{message}; commit is retained and must not be rewound"
        print(message, file=sys.stderr)
        return 2
    print("EXPERIMENT_RESULT_STATUS=complete")
    print(f"EXPERIMENT_RESULT_ARCHIVE_PATH={result.archive_path}")
    print(f"EXPERIMENT_RESULT_COMMIT={result.commit}")
    print(f"EXPERIMENT_RESULT_ANNEX_KEY={result.key}")
    print(f"EXPERIMENT_RESULT_ARCHIVE_SIZE={result.size}")
    print(f"EXPERIMENT_RESULT_ARCHIVE_SHA256={result.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
