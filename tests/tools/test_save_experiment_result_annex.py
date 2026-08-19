# @dependency-start
# contract test
# responsibility Tests deterministic one-run git-annex raw retention and compact evidence binding.
# upstream design ../../documents/experiments/result-log-retention-and-visualization.md raw retention policy
# upstream implementation ../../tools/experiments/save_experiment_result_annex.py helper under test
# @dependency-end

"""Tests for one-run git-annex experiment raw retention."""

# pyright: reportPrivateUsage=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tools.experiments import save_experiment_result_annex as retention
from tools.experiments.experiment_identity import ExperimentIdentity

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "save_experiment_result_annex.py"
)
GIT_ANNEX = shutil.which("git-annex")
requires_git_annex = pytest.mark.skipif(
    GIT_ANNEX is None, reason="git-annex is required"
)


def run_git(
    repo: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run Git in a fixture repository."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def init_source(root: Path) -> Path:
    """Create a committed source repository with compact result evidence and ignored raw."""
    identity = ExperimentIdentity("demo", "formal", "run-a")
    result_dir = root / "experiments" / "demo" / "result" / "run-a"
    raw_dir = result_dir / "raw"
    summary_dir = result_dir / "summary"
    report_path = root / "experiments" / "demo" / "report" / "run-a.md"
    raw_dir.mkdir(parents=True)
    report_path.parent.mkdir(parents=True)
    (raw_dir / ".gitignore").write_text(
        "*\n!.gitignore\n",
        encoding="utf-8",
    )
    (raw_dir / "nested").mkdir()
    (raw_dir / "samples.bin").write_bytes(b"\x00\x01raw-samples\n")
    executable = raw_dir / "nested" / "collect.sh"
    executable.write_text("#!/bin/sh\nprintf raw\n", encoding="utf-8")
    executable.chmod(0o755)
    summary_dir.mkdir()
    (summary_dir / "summary.json").write_text(
        json.dumps(
            {
                "run_id": identity.run_name,
                "status": "success",
                "case_count": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (result_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                **identity.to_dict(),
                "status": "completed",
                "raw_artifacts": {
                    "path": "experiments/demo/result/run-a/raw",
                    "retention": {"state": "unarchived"},
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text("# compact reader report\n", encoding="utf-8")
    run_git(root, "init", "-q")
    run_git(root, "checkout", "-q", "-b", "main")
    run_git(root, "config", "user.name", "Annex Test")
    run_git(root, "config", "user.email", "annex-test@example.invalid")
    run_git(root, "add", "experiments")
    run_git(root, "commit", "-qm", "source evidence")
    (root / "source-dirty.txt").write_text("dirty\n", encoding="utf-8")
    return raw_dir


def init_annex(root: Path) -> Path:
    """Create a clean normal-branch git-annex worktree."""
    root.mkdir()
    run_git(root, "init", "-q")
    run_git(root, "checkout", "-q", "-b", "main")
    run_git(root, "config", "user.name", "Annex Test")
    run_git(root, "config", "user.email", "annex-test@example.invalid")
    run_git(root, "annex", "init", "-q")
    run_git(root, "commit", "--allow-empty", "-qm", "initial")
    return root


def run_save(
    source: Path,
    annex: Path,
    raw_dir: Path,
) -> subprocess.CompletedProcess[str]:
    """Invoke the public raw-only retention CLI."""
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-repo-root",
            str(source),
            "--raw-dir",
            str(raw_dir),
            "--annex-repo",
            str(annex),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def archive_path(annex: Path) -> Path:
    """Return the expected external raw archive path."""
    return annex / "experiments" / "demo" / "raw" / "formal" / "run-a.tar.gz"


def archive_members(path: Path) -> list[tarfile.TarInfo]:
    """Read all members from a retained archive."""
    with tarfile.open(path, "r:gz") as archive:
        return archive.getmembers()


def archive_manifest(path: Path) -> dict[str, object]:
    """Read the internal canonical retention manifest."""
    member_path = "experiments/demo/result/run-a/raw/annex_retention_manifest.json"
    with tarfile.open(path, "r:gz") as archive:
        member = archive.getmember(member_path)
        stream = archive.extractfile(member)
        assert stream is not None
        payload = json.loads(stream.read())
    assert isinstance(payload, dict)
    return payload


def parse_source(root: Path, raw_dir: Path) -> retention.RawIdentity:
    """Parse one fixture through the public identity boundary under test."""
    return retention._parse_raw_identity(root.resolve(), raw_dir.absolute())


def test_parse_and_archive_are_raw_only_without_git_annex(tmp_path: Path) -> None:
    """Pure archive construction excludes compact result and reader report bytes."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    raw = parse_source(source, raw_dir)
    entries, source_files = retention._scan_source_tree(raw)
    manifest_path = raw.raw_relative / retention.MANIFEST_NAME
    entries = tuple(
        sorted(
            (*entries, retention.ArchiveEntry(manifest_path.as_posix(), None, False)),
            key=lambda item: item.archive_path,
        )
    )
    archive_relative = Path("experiments/demo/raw/formal/run-a.tar.gz")
    manifest_bytes = retention._manifest_bytes(
        raw,
        entries,
        source_files,
        archive_relative,
    )
    archive = tmp_path / "raw.tar.gz"
    retention._write_archive(
        archive,
        entries,
        source_files,
        manifest_bytes,
        manifest_path.as_posix(),
    )
    retention._read_archive(
        archive,
        entries,
        source_files,
        manifest_bytes,
        manifest_path.as_posix(),
    )
    names = [member.name for member in archive_members(archive)]
    assert "experiments/demo/result/run-a/raw/samples.bin" in names
    assert "experiments/demo/result/run-a/raw/nested/collect.sh" in names
    assert not any("/summary/" in name for name in names)
    assert not any("/report/" in name for name in names)
    assert not any(name.endswith("summary.json") for name in names)
    payload = archive_manifest(archive)
    assert payload["schema"] == "git-annex-raw-retention/v1"
    assert payload["raw"]["directory"] == "experiments/demo/result/run-a/raw"
    evidence = payload["tracked_result_evidence"]
    assert evidence["summary"]["path"] == (
        "experiments/demo/result/run-a/summary/summary.json"
    )
    assert evidence["run_manifest"]["path"] == (
        "experiments/demo/result/run-a/run_manifest.json"
    )
    for key in ("summary", "run_manifest"):
        assert len(evidence[key]["sha256"]) == 64


def test_raw_archive_bytes_are_deterministic_without_git_annex(tmp_path: Path) -> None:
    """Stable PAX metadata and gzip headers make identical source bytes reproducible."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    raw = parse_source(source, raw_dir)
    entries, source_files = retention._scan_source_tree(raw)
    manifest_path = raw.raw_relative / retention.MANIFEST_NAME
    entries = tuple(
        sorted(
            (*entries, retention.ArchiveEntry(manifest_path.as_posix(), None, False)),
            key=lambda item: item.archive_path,
        )
    )
    archive_relative = Path("experiments/demo/raw/formal/run-a.tar.gz")
    manifest_bytes = retention._manifest_bytes(
        raw,
        entries,
        source_files,
        archive_relative,
    )
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    for path in (first, second):
        retention._write_archive(
            path,
            entries,
            source_files,
            manifest_bytes,
            manifest_path.as_posix(),
        )
    assert first.read_bytes() == second.read_bytes()
    assert (
        hashlib.sha256(first.read_bytes()).hexdigest()
        == hashlib.sha256(second.read_bytes()).hexdigest()
    )
    for member in archive_members(first):
        assert member.uid == 0
        assert member.gid == 0
        assert member.uname == ""
        assert member.gname == ""
        assert member.mtime == 0
        assert member.pax_headers == {}


def test_whole_result_cli_route_is_not_accepted(tmp_path: Path) -> None:
    """The old result-tree input is removed rather than retained as an alias."""
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--result-dir",
            str(tmp_path / "result"),
            "--annex-repo",
            str(tmp_path / "annex"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--raw-dir" in result.stderr
    assert "unrecognized arguments: --result-dir" in result.stderr


def test_raw_identity_rejects_manifest_path_or_state_mismatch(tmp_path: Path) -> None:
    """The tracked run manifest is the exact identity-to-raw binding oracle."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    manifest_path = source / "experiments/demo/result/run-a/run_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["raw_artifacts"]["path"] = "experiments/demo/result/other/raw"
    manifest_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(retention.RetentionError, match="must match source commit"):
        parse_source(source, raw_dir)
    run_git(source, "add", str(manifest_path.relative_to(source)))
    run_git(source, "commit", "-qm", "mismatched binding")
    with pytest.raises(retention.RetentionError, match="raw path does not match"):
        parse_source(source, raw_dir)


def test_raw_identity_rejects_untracked_summary(tmp_path: Path) -> None:
    """Review evidence must be tracked and equal to the recorded source commit."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    summary = source / "experiments/demo/result/run-a/summary/summary.json"
    run_git(source, "rm", "--cached", str(summary.relative_to(source)))
    summary.write_text('{"run_id":"run-a"}\n', encoding="utf-8")
    with pytest.raises(retention.RetentionError, match="must be tracked"):
        parse_source(source, raw_dir)


def test_empty_symlink_special_lfs_and_reserved_raw_are_rejected(
    tmp_path: Path,
) -> None:
    """Every unsupported raw shape fails before annex mutation."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    raw = parse_source(source, raw_dir)
    for child in sorted(
        raw_dir.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        if child.is_dir():
            child.rmdir()
        else:
            child.unlink()
    with pytest.raises(retention.RetentionError, match="raw directory is empty"):
        retention._scan_source_tree(raw)

    (raw_dir / "target").write_text("target\n", encoding="utf-8")
    (raw_dir / "link").symlink_to("target")
    with pytest.raises(retention.RetentionError, match="symlink"):
        retention._scan_source_tree(raw)
    (raw_dir / "link").unlink()

    fifo = raw_dir / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(retention.RetentionError, match="special file"):
        retention._scan_source_tree(raw)
    fifo.unlink()

    (raw_dir / "target").write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:" + "a" * 64 + "\n"
        "size 42\n",
        encoding="utf-8",
    )
    with pytest.raises(retention.RetentionError, match="Git-LFS pointer"):
        retention._scan_source_tree(raw)
    (raw_dir / "target").unlink()

    (raw_dir / retention.MANIFEST_NAME).write_text("reserved\n", encoding="utf-8")
    with pytest.raises(retention.RetentionError, match="reserves"):
        retention._scan_source_tree(raw)


@requires_git_annex
def test_public_save_archives_raw_only_and_binds_tracked_evidence(
    tmp_path: Path,
) -> None:
    """The committed annex object contains raw bytes plus one binding manifest only."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    annex = init_annex(tmp_path / "annex")
    result = run_save(source, annex, raw_dir)
    assert result.returncode == 0, result.stderr
    assert "EXPERIMENT_RAW_STATUS=complete" in result.stdout
    retained = archive_path(annex)
    members = archive_members(retained)
    names = [member.name for member in members]
    assert all(
        name.startswith("experiments/demo/result/run-a/raw")
        or name
        in {
            "experiments",
            "experiments/demo",
            "experiments/demo/result",
            "experiments/demo/result/run-a",
        }
        for name in names
    )
    assert not any("/report/" in name for name in names)
    assert not any(name.endswith("summary.json") for name in names)
    manifest = archive_manifest(retained)
    assert manifest["identity"] == {
        "schema": "agentcanon.experiment-run-identity/v2",
        "topic": "demo",
        "variant": "formal",
        "run_name": "run-a",
    }
    assert (
        manifest["source"]["commit"]
        == run_git(source, "rev-parse", "HEAD").stdout.strip()
    )
    assert "source-dirty.txt" in manifest["source"]["dirty_paths"]
    key = run_git(
        annex,
        "annex",
        "lookupkey",
        "--",
        "experiments/demo/raw/formal/run-a.tar.gz",
    ).stdout.strip()
    assert key.startswith("SHA256E-")
    assert not run_git(
        annex,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout


@requires_git_annex
def test_second_save_is_append_only_and_does_not_move_head(tmp_path: Path) -> None:
    """An identity collision fails closed without replacing or recommitting bytes."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    annex = init_annex(tmp_path / "annex")
    first = run_save(source, annex, raw_dir)
    assert first.returncode == 0, first.stderr
    first_head = run_git(annex, "rev-parse", "HEAD").stdout.strip()
    first_bytes = archive_path(annex).read_bytes()
    second = run_save(source, annex, raw_dir)
    assert second.returncode == 2
    assert "archive target already exists" in second.stderr
    assert run_git(annex, "rev-parse", "HEAD").stdout.strip() == first_head
    assert archive_path(annex).read_bytes() == first_bytes


@requires_git_annex
def test_precommit_failure_rolls_back_owned_annex_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before commit, the saver removes only its archive/index/attribute mutation."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    annex = init_annex(tmp_path / "annex")
    raw = parse_source(source, raw_dir)
    head = run_git(annex, "rev-parse", "HEAD").stdout.strip()

    def fail_verification(*_args: object, **_kwargs: object) -> str:
        raise retention.RetentionError("injected fsck failure")

    monkeypatch.setattr(retention, "_verify_annex_content", fail_verification)
    with pytest.raises(retention.RetentionError, match="injected fsck failure"):
        retention.save_raw(raw, annex.resolve())
    assert run_git(annex, "rev-parse", "HEAD").stdout.strip() == head
    assert not archive_path(annex).exists()
    assert not run_git(
        annex,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout


@requires_git_annex
def test_postcommit_failure_retains_commit_without_rewind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After commit, verification failure reports the retained commit and never resets HEAD."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    annex = init_annex(tmp_path / "annex")
    raw = parse_source(source, raw_dir)
    initial_head = run_git(annex, "rev-parse", "HEAD").stdout.strip()
    original = retention._read_archive
    calls = 0

    def fail_after_commit(*args: object, **kwargs: object) -> tuple[int, str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise retention.RetentionError("injected postcommit reread failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(retention, "_read_archive", fail_after_commit)
    with pytest.raises(retention.RetentionError, match="retained commit"):
        retention.save_raw(raw, annex.resolve())
    retained_head = run_git(annex, "rev-parse", "HEAD").stdout.strip()
    assert retained_head != initial_head
    assert (
        run_git(annex, "rev-parse", f"{retained_head}^").stdout.strip() == initial_head
    )


@requires_git_annex
def test_full_fsck_runs_before_and_after_exactly_one_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The existing fsck contract remains on both sides of the append-only commit."""
    source = tmp_path / "source"
    source.mkdir()
    raw_dir = init_source(source)
    annex = init_annex(tmp_path / "annex")
    raw = parse_source(source, raw_dir)
    original = retention._annex
    fsck_calls: list[tuple[str, ...]] = []

    def record_annex(repo: Path, args: list[str]) -> str:
        if args and args[0] == "fsck":
            fsck_calls.append(tuple(args))
        return original(repo, args)

    monkeypatch.setattr(retention, "_annex", record_annex)
    result = retention.save_raw(raw, annex.resolve())
    assert result.commit == run_git(annex, "rev-parse", "HEAD").stdout.strip()
    assert len(fsck_calls) == 2
    assert all("--" in call for call in fsck_calls)
