# @dependency-start
# contract test
# responsibility Tests deterministic one-run git-annex result retention.
# upstream design ../../documents/experiments/result-log-retention-and-visualization.md result retention policy
# upstream implementation ../../tools/experiments/save_experiment_result_annex.py helper under test
# @dependency-end

"""Tests for one-run git-annex experiment result retention."""

# pyright: reportPrivateUsage=false, reportUntypedFunctionDecorator=false

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from tools.experiments import save_experiment_result_annex as retention
from tools.experiments.experiment_identity import ExperimentIdentity

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "experiments" / "save_experiment_result_annex.py"
GIT_ANNEX = shutil.which("git-annex")
pytestmark = pytest.mark.skipif(GIT_ANNEX is None, reason="git-annex is required")


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run Git in a fixture repository."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def init_source(root: Path, *, report: bool = True) -> Path:
    """Create a committed source repository with a non-empty result."""
    result = root / "experiments" / "demo" / "result" / "run-a"
    (result / "logs").mkdir(parents=True)
    (result / "summary").mkdir()
    (result / "run_manifest.json").write_text(
        json.dumps(
            {
                **ExperimentIdentity("demo", "formal", "run-a").to_dict(),
                "status": "ok",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (result / "summary" / "summary.json").write_text('{"value":1}\n', encoding="utf-8")
    (result / "summary" / "cases.jsonl").write_text('{"case_id":"run-a"}\n', encoding="utf-8")
    script = result / "run.sh"
    script.write_text("#!/bin/sh\nprintf ok\n", encoding="utf-8")
    script.chmod(0o755)
    (result / "logs" / "events.jsonl").write_text('{"event":1}\n', encoding="utf-8")
    if report:
        report_path = root / "experiments" / "demo" / "report" / "run-a.md"
        report_path.parent.mkdir(parents=True)
        report_path.write_text("# run-a\n", encoding="utf-8")
    run_git(root, "init", "-q")
    run_git(root, "checkout", "-q", "-b", "main")
    run_git(root, "config", "user.name", "Annex Test")
    run_git(root, "config", "user.email", "annex-test@example.invalid")
    run_git(root, "add", "experiments")
    run_git(root, "commit", "-qm", "source")
    (root / "source-dirty.txt").write_text("dirty\n", encoding="utf-8")
    return result


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


def run_save(source: Path, annex: Path, result_dir: Path) -> subprocess.CompletedProcess[str]:
    """Invoke the public retention CLI."""
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-repo-root",
            str(source),
            "--result-dir",
            str(result_dir),
            "--annex-repo",
            str(annex),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def archive_path(annex: Path) -> Path:
    """Return the expected external archive path."""
    return annex / "experiments" / "demo" / "result" / "run-a.tar.gz"


def archive_members(path: Path) -> list[tarfile.TarInfo]:
    """Read all members from a retained archive."""
    with tarfile.open(path, "r:gz") as archive:
        return archive.getmembers()


def archive_manifest(path: Path) -> dict[str, object]:
    """Read the internal canonical manifest."""
    manifest_path = "experiments/demo/result/run-a/annex_retention_manifest.json"
    with tarfile.open(path, "r:gz") as archive:
        payload = archive.extractfile(manifest_path)
        assert payload is not None
        raw = payload.read()
    assert raw.endswith(b"\n")
    return json.loads(raw)


def test_retains_layout_manifest_hashes_modes_and_clean_single_commit(tmp_path: Path) -> None:
    """One run is archived completely and committed once on a clean normal branch."""
    source = tmp_path / "source"
    annex = init_annex(tmp_path / "annex")
    result = init_source(source)
    before = run_git(annex, "rev-parse", "HEAD").stdout.strip()

    completed = run_save(source, annex, result)

    assert completed.returncode == 0, completed.stderr
    assert "EXPERIMENT_RESULT_STATUS=complete" in completed.stdout
    target = archive_path(annex)
    assert target.is_symlink()
    names = [member.name for member in archive_members(target)]
    assert "experiments/demo/result/run-a/run_manifest.json" in names
    assert "experiments/demo/result/run-a/logs/events.jsonl" in names
    assert "experiments/demo/report/run-a.md" in names
    assert "experiments/demo/result/run-a/annex_retention_manifest.json" in names
    manifest = archive_manifest(target)
    assert manifest["append_only"] is True
    assert manifest["report"] == "experiments/demo/report/run-a.md"
    assert manifest["report_present"] is True
    assert manifest["source"]["branch"] == "main"  # type: ignore[index]
    assert manifest["source"]["dirty_paths"] == ["source-dirty.txt"]  # type: ignore[index]
    assert manifest["source"]["run_manifest_sha256"]  # type: ignore[index]
    assert ExperimentIdentity.from_dict(manifest) == ExperimentIdentity(
        "demo", "formal", "run-a"
    )
    records = {item["path"]: item for item in manifest["files"]}  # type: ignore[index]
    assert records["experiments/demo/result/run-a/run.sh"]["mode"] == "executable"
    assert records["experiments/demo/result/run-a/summary/summary.json"]["sha256"] == hashlib.sha256(
        (result / "summary" / "summary.json").read_bytes()
    ).hexdigest()
    assert records["experiments/demo/result/run-a/summary/cases.jsonl"]["sha256"] == hashlib.sha256(
        (result / "summary" / "cases.jsonl").read_bytes()
    ).hexdigest()
    assert run_git(annex, "status", "--porcelain=v1", "--untracked-files=all").stdout == ""
    head = run_git(annex, "rev-parse", "HEAD").stdout.strip()
    assert head != before
    assert run_git(annex, "rev-list", "--count", f"{before}..{head}").stdout.strip() == "1"
    assert run_git(annex, "rev-parse", f"{head}^").stdout.strip() == before
    assert run_git(annex, "branch", "--show-current").stdout.strip() == "main"
    assert not any(
        "experiment-results/" in line
        for line in run_git(annex, "for-each-ref", "--format=%(refname)", "refs/").stdout.splitlines()
    )
    fsck = run_git(
        annex,
        "annex",
        "fsck",
        "--",
        "experiments/demo/result/run-a.tar.gz",
    )
    assert fsck.returncode == 0, fsck.stderr


def test_rejects_mismatched_run_manifest_identity_before_annex_mutation(
    tmp_path: Path,
) -> None:
    """The result path and canonical run-manifest identity must agree."""
    source = tmp_path / "source"
    result = init_source(source)
    (result / "run_manifest.json").write_text(
        json.dumps(ExperimentIdentity("demo", "formal", "run-b").to_dict()) + "\n",
        encoding="utf-8",
    )
    annex = init_annex(tmp_path / "annex")
    before = run_git(annex, "rev-parse", "HEAD").stdout.strip()

    completed = run_save(source, annex, result)

    assert completed.returncode == 2
    assert "identity does not match" in completed.stderr
    assert run_git(annex, "rev-parse", "HEAD").stdout.strip() == before
    assert run_git(annex, "status", "--porcelain=v1", "--untracked-files=all").stdout == ""
    assert not (annex / "experiments").exists()


def test_report_absent_and_determinism(tmp_path: Path) -> None:
    """Report omission is explicit and identical source runs produce identical bytes."""
    source = tmp_path / "source"
    result = init_source(source, report=False)
    annex_one = init_annex(tmp_path / "annex-one")
    annex_two = init_annex(tmp_path / "annex-two")
    first = run_save(source, annex_one, result)
    second = run_save(source, annex_two, result)
    assert first.returncode == second.returncode == 0
    first_bytes = archive_path(annex_one).read_bytes()
    second_bytes = archive_path(annex_two).read_bytes()
    assert first_bytes == second_bytes
    manifest = archive_manifest(archive_path(annex_one))
    assert manifest["report"] is None
    assert manifest["report_present"] is False
    assert "experiments/demo/report/run-a.md" not in [
        member.name for member in archive_members(archive_path(annex_one))
    ]


@pytest.mark.parametrize("kind", ["reserved", "lfs", "symlink"])
def test_rejects_reserved_lfs_and_symlink_sources(tmp_path: Path, kind: str) -> None:
    """Unsafe source entries fail before any annex mutation."""
    source = tmp_path / "source"
    result = init_source(source)
    if kind == "reserved":
        (result / retention.MANIFEST_NAME).write_text("collision\n", encoding="utf-8")
    elif kind == "lfs":
        (result / "pointer").write_text(
            "version https://git-lfs.github.com/spec/v1\noid sha256:" + "a" * 64 + "\nsize 4\n",
            encoding="utf-8",
        )
    else:
        (result / "link").symlink_to(result / "summary" / "summary.json")
    annex = init_annex(tmp_path / "annex")
    before = run_git(annex, "rev-parse", "HEAD").stdout.strip()
    completed = run_save(source, annex, result)
    assert completed.returncode == 2
    assert run_git(annex, "rev-parse", "HEAD").stdout.strip() == before
    assert run_git(annex, "status", "--porcelain=v1", "--untracked-files=all").stdout == ""
    assert not (annex / "experiments").exists()


@pytest.mark.parametrize("kind", ["result-dir", "report-parent"])
def test_rejects_symlinked_input_components(tmp_path: Path, kind: str) -> None:
    """Lexical result and report paths cannot escape validation through symlinks."""
    source = tmp_path / "source"
    result = init_source(source, report=kind != "report-parent")
    if kind == "result-dir":
        target = result.with_name("run-b")
        result.rename(target)
        result.symlink_to(target, target_is_directory=True)
    else:
        outside_report = tmp_path / "outside-report"
        outside_report.mkdir()
        (outside_report / "run-a.md").write_text("# outside\n", encoding="utf-8")
        (source / "experiments" / "report").symlink_to(
            outside_report, target_is_directory=True
        )
    annex = init_annex(tmp_path / "annex")
    before = run_git(annex, "rev-parse", "HEAD").stdout.strip()
    completed = run_save(source, annex, result)
    assert completed.returncode == 2
    assert "symlink" in completed.stderr
    assert run_git(annex, "rev-parse", "HEAD").stdout.strip() == before
    assert run_git(annex, "status", "--porcelain=v1", "--untracked-files=all").stdout == ""
    assert not (annex / "experiments").exists()


def test_rejects_effectively_empty_result(tmp_path: Path) -> None:
    """A report cannot substitute for a result file."""
    source = tmp_path / "source"
    result = source / "experiments" / "demo" / "result" / "formal" / "run-a"
    result.mkdir(parents=True)
    report = source / "experiments" / "report"
    report.mkdir(parents=True)
    (report / "run-a.md").write_text("# report\n", encoding="utf-8")
    run_git(source, "init", "-q")
    run_git(source, "checkout", "-q", "-b", "main")
    run_git(source, "config", "user.name", "Annex Test")
    run_git(source, "config", "user.email", "annex-test@example.invalid")
    run_git(source, "add", "experiments")
    run_git(source, "commit", "-qm", "source")
    annex = init_annex(tmp_path / "annex")
    completed = run_save(source, annex, result)
    assert completed.returncode == 2
    assert "effectively empty" in completed.stderr


def test_rejects_root_containment_and_collision(tmp_path: Path) -> None:
    """Source/annex containment and append-only target collisions fail safely."""
    source = tmp_path / "source"
    result = init_source(source)
    annex = init_annex(tmp_path / "annex")
    first = run_save(source, annex, result)
    assert first.returncode == 0, first.stderr
    second = run_save(source, annex, result)
    assert second.returncode == 2
    assert "already exists" in second.stderr
    nested_annex = source / "nested-annex"
    nested_annex.mkdir()
    assert run_save(source, nested_annex, result).returncode == 2


def test_no_replace_race_keeps_existing_target_and_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A link race cannot replace an existing target or leave task state."""
    source = tmp_path / "source"
    result = init_source(source)
    annex = init_annex(tmp_path / "annex")
    identity = retention._parse_result_identity(source, result)
    target = annex / "experiments" / "demo" / "result" / "formal" / "run-a.tar.gz"

    def race(_temporary: Path, final: Path) -> None:
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"racing owner")
        raise FileExistsError(final)

    monkeypatch.setattr(retention, "_link_no_replace", race)
    with pytest.raises(retention.RetentionError, match="run-a.tar.gz"):
        retention.save_result(identity, annex)
    assert target.read_bytes() == b"racing owner"
    assert "run-a.tar.gz" in run_git(
        annex, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout


def test_bounded_precommit_rollback_and_postcommit_no_rewind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Precommit failure rolls back owned paths; postcommit failure retains its commit."""
    source = tmp_path / "source"
    result = init_source(source)
    annex = init_annex(tmp_path / "annex")
    identity = retention._parse_result_identity(source, result)
    baseline = run_git(annex, "rev-parse", "HEAD").stdout.strip()

    def fail_pre(*_args: object) -> str:
        raise retention.RetentionError("precommit fsck failure")

    monkeypatch.setattr(
        retention,
        "_verify_annex_content",
        fail_pre,
    )
    with pytest.raises(retention.RetentionError, match="precommit fsck failure"):
        retention.save_result(identity, annex)
    assert run_git(annex, "rev-parse", "HEAD").stdout.strip() == baseline
    assert run_git(annex, "status", "--porcelain=v1", "--untracked-files=all").stdout == ""
    assert not (annex / "experiments").exists()

    monkeypatch.undo()
    original_verify = retention._verify_annex_content
    calls = 0

    def fail_post(*args: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original_verify(*args)  # type: ignore[arg-type]
        raise retention.RetentionError("postcommit fsck failure")

    monkeypatch.setattr(retention, "_verify_annex_content", fail_post)
    with pytest.raises(retention.RetentionError, match="retained commit"):
        retention.save_result(identity, annex)
    retained = run_git(annex, "rev-parse", "HEAD").stdout.strip()
    assert retained != baseline
    assert run_git(annex, "rev-parse", f"{retained}^").stdout.strip() == baseline
    assert run_git(annex, "status", "--porcelain=v1", "--untracked-files=all").stdout == ""


def test_removed_branch_cli_is_not_available() -> None:
    """The replacement CLI does not accept retired branch/push options."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--result-dir", "x", "--branch", "main"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


def test_annex_repo_environment_and_single_result_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The environment fallback works and repeated result arguments remain invalid."""
    source = tmp_path / "source"
    result_dir = init_source(source)
    annex = init_annex(tmp_path / "annex")
    monkeypatch.setenv(retention.ANNEX_REPO_ENV, str(annex))
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-repo-root",
            str(source),
            "--result-dir",
            str(result_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    repeated = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-repo-root",
            str(source),
            "--result-dir",
            str(result_dir),
            "--result-dir",
            str(result_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert repeated.returncode != 0
    assert "exactly one --result-dir" in repeated.stderr


def test_rejects_non_regular_report_and_unexpected_store_directory(
    tmp_path: Path,
) -> None:
    """The conventional report and existing store topology remain bounded."""
    source = tmp_path / "source"
    result_dir = init_source(source, report=False)
    report = source / "experiments" / "demo" / "report" / "run-a.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.symlink_to(result_dir / "summary" / "summary.json")
    annex = init_annex(tmp_path / "annex")
    completed = run_save(source, annex, result_dir)
    assert completed.returncode == 2
    assert "symlink" in completed.stderr

    report.unlink()
    unexpected = annex / "unrelated"
    unexpected.mkdir()
    completed = run_save(source, annex, result_dir)
    assert completed.returncode == 2
    assert "unexpected visible directory" in completed.stderr
