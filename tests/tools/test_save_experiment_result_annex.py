"""Public native retention CLI tested with the existing real git-annex provider."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

requires_git_annex = pytest.mark.skipif(
    shutil.which("git-annex") is None, reason="git-annex is required"
)


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )


def init_source(root: Path) -> Path:
    result = root / "experiments/demo/result/run-a"
    raw = result / "raw"
    summary = result / "summary"
    report = root / "experiments/demo/report/run-a.md"
    raw.mkdir(parents=True)
    summary.mkdir()
    report.parent.mkdir(parents=True)
    (raw / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (raw / "nested").mkdir()
    (raw / "samples.bin").write_bytes(b"\x00\x01raw-samples\n")
    executable = raw / "nested/collect.sh"
    executable.write_text("#!/bin/sh\nprintf raw\n", encoding="utf-8")
    executable.chmod(0o755)
    (summary / "summary.json").write_text(
        json.dumps(
            {"run_id": "run-a", "status": "success", "case_count": 1}, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    (result / "run_manifest.json").write_text(
        json.dumps(
            {
                "identity": {
                    "schema": "agentcanon.experiment-run-identity/v2",
                    "topic": "demo",
                    "variant": "formal",
                    "run_name": "run-a",
                },
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
    report.write_text("# compact reader report\n", encoding="utf-8")
    run_git(root, "init", "-q")
    run_git(root, "checkout", "-q", "-b", "main")
    run_git(root, "config", "user.name", "Annex Test")
    run_git(root, "config", "user.email", "annex-test@example.invalid")
    run_git(root, "add", "experiments")
    run_git(root, "commit", "-qm", "source evidence")
    (root / "source-dirty.txt").write_text("dirty\n", encoding="utf-8")
    return raw


def init_annex(root: Path) -> Path:
    root.mkdir()
    run_git(root, "init", "-q")
    run_git(root, "checkout", "-q", "-b", "main")
    run_git(root, "config", "user.name", "Annex Test")
    run_git(root, "config", "user.email", "annex-test@example.invalid")
    run_git(root, "annex", "init", "-q")
    run_git(root, "commit", "--allow-empty", "-qm", "initial")
    return root


def run_save(source: Path, annex: Path, raw: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            os.environ["AGENT_CANON_CLI"],
            "save-experiment-result-annex",
            "--source-repo-root",
            str(source),
            "--raw-dir",
            str(raw),
            "--annex-repo",
            str(annex),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_whole_result_cli_route_is_not_accepted(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            os.environ["AGENT_CANON_CLI"],
            "save-experiment-result-annex",
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


@requires_git_annex
def test_public_save_archives_raw_only_and_binds_tracked_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    raw = init_source(source)
    annex = init_annex(tmp_path / "annex")
    result = run_save(source, annex, raw)
    assert result.returncode == 0, result.stderr
    assert "EXPERIMENT_RAW_STATUS=complete" in result.stdout
    retained = annex / "experiments/demo/raw/formal/run-a.tar.gz"
    with tarfile.open(retained, "r:gz") as archive:
        names = archive.getnames()
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
        assert not any(
            "/report/" in name or name.endswith("summary.json") for name in names
        )
        stream = archive.extractfile(
            "experiments/demo/result/run-a/raw/annex_retention_manifest.json"
        )
        assert stream is not None
        manifest = json.loads(stream.read())
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
    assert (
        run_git(
            annex,
            "annex",
            "lookupkey",
            "--",
            "experiments/demo/raw/formal/run-a.tar.gz",
        )
        .stdout.strip()
        .startswith("SHA256E-")
    )
    assert not run_git(
        annex, "status", "--porcelain=v1", "--untracked-files=all"
    ).stdout


@requires_git_annex
def test_second_save_is_append_only_and_does_not_move_head(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    raw = init_source(source)
    annex = init_annex(tmp_path / "annex")
    first = run_save(source, annex, raw)
    assert first.returncode == 0, first.stderr
    head = run_git(annex, "rev-parse", "HEAD").stdout.strip()
    retained = annex / "experiments/demo/raw/formal/run-a.tar.gz"
    before = retained.read_bytes()
    second = run_save(source, annex, raw)
    assert second.returncode == 2
    assert "archive target already exists" in second.stderr
    assert run_git(annex, "rev-parse", "HEAD").stdout.strip() == head
    assert retained.read_bytes() == before
