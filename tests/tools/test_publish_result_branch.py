# @dependency-start
# contract test
# responsibility Tests variant-scoped experiment result branch publication.
# upstream implementation ../../tools/experiments/publish_result_branch.py helper under test
# @dependency-end

"""Tests for result publication identity and collision behavior."""

from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RESULT_BRANCH = "experiment-results/demo.topic/smoke.v1"


def run_git(repo_root: Path, *args: str) -> str:
    """Run one strict Git command in a fixture repository."""
    result = subprocess.run(["git", *args], cwd=repo_root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def init_repo(repo_root: Path) -> None:
    """Initialize a source checkout with a committed baseline."""
    repo_root.mkdir()
    run_git(repo_root, "init")
    run_git(repo_root, "checkout", "-b", "main")
    run_git(repo_root, "config", "user.name", "Experiment Test")
    run_git(repo_root, "config", "user.email", "experiment-test@example.invalid")
    (repo_root / "source.py").write_text("print('source')\n", encoding="utf-8")
    run_git(repo_root, "add", "source.py")
    run_git(repo_root, "commit", "-m", "initial source")


def write_result(repo_root: Path, run_name: str, manifest_branch: str) -> Path:
    """Write one complete variant-scoped result fixture."""
    result_dir = repo_root / "experiments" / "demo.topic" / "result" / "smoke.v1" / run_name
    result_dir.mkdir(parents=True)
    report_dir = repo_root / "experiments" / "report" / "demo.topic" / "smoke.v1"
    report_dir.mkdir(parents=True, exist_ok=True)
    source_commit = run_git(repo_root, "rev-parse", "HEAD")
    manifest = {
        "identity": {
            "schema": "agentcanon.experiment-run-identity/v2",
            "topic": "demo.topic",
            "variant": "smoke.v1",
            "run_name": run_name,
        },
        "created_at_utc": "2026-01-01T00:00:00Z",
        "git": {"branch": manifest_branch, "commit": source_commit},
    }
    (result_dir / "run_manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    (result_dir / "summary.json").write_text('{"status": "ok"}\n', encoding="utf-8")
    report = report_dir / f"{run_name}.md"
    report.write_text(f"# {run_name}\n", encoding="utf-8")
    return result_dir


def run_publish_result_command(repo_root: Path, result_dir: Path, *, extra_args: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    """Invoke the publication CLI against one result fixture."""
    command = [
        sys.executable,
        "-m",
        "tools.experiments.publish_result_branch",
        "--repo-root",
        str(repo_root),
        "--result-dir",
        str(result_dir),
        "--variant",
        "smoke.v1",
    ]
    command.extend(extra_args)
    return subprocess.run(command, check=False, capture_output=True, text=True)


def branch_files(repo_root: Path, branch: str) -> set[str]:
    """Return all files recorded on one result branch."""
    output = run_git(repo_root, "ls-tree", "-r", "--name-only", branch)
    return set(output.splitlines())


def test_publish_result_branch_keeps_source_checkout_on_main(tmp_path: Path) -> None:
    """Publish without switching the source checkout branch."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    result_dir = write_result(repo_root, "run.a", "main")

    result = run_publish_result_command(repo_root, result_dir)

    assert result.returncode == 0, result.stderr
    assert f"RESULT_BRANCH={RESULT_BRANCH}" in result.stdout
    assert run_git(repo_root, "branch", "--show-current") == "main"
    files = branch_files(repo_root, RESULT_BRANCH)
    assert "experiments/demo.topic/result/smoke.v1/run.a/summary.json" in files
    assert "experiments/report/demo.topic/smoke.v1/run.a.md" in files


def test_publish_result_branch_accumulates_distinct_runs(tmp_path: Path) -> None:
    """Accumulate distinct run identities on one variant branch."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    first_dir = write_result(repo_root, "run.a", "main")
    second_dir = write_result(repo_root, "run.b", "main")

    first_result = run_publish_result_command(repo_root, first_dir)
    second_result = run_publish_result_command(repo_root, second_dir)

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    files = branch_files(repo_root, RESULT_BRANCH)
    assert "experiments/demo.topic/result/smoke.v1/run.a/summary.json" in files
    assert "experiments/demo.topic/result/smoke.v1/run.b/summary.json" in files


def test_publish_result_branch_rejects_duplicate_identity_without_replacement(tmp_path: Path) -> None:
    """Reject a duplicate identity without replacing its existing commit."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    result_dir = write_result(repo_root, "run.a", "main")
    assert run_publish_result_command(repo_root, result_dir).returncode == 0
    original = run_git(repo_root, "rev-parse", RESULT_BRANCH)

    (result_dir / "summary.json").write_text('{"status": "changed"}\n', encoding="utf-8")
    result = run_publish_result_command(repo_root, result_dir)

    assert result.returncode == 2
    assert "never replaces" in result.stderr
    assert run_git(repo_root, "rev-parse", RESULT_BRANCH) == original


def test_publish_result_branch_rejects_variant_mismatch(tmp_path: Path) -> None:
    """Reject a CLI variant that disagrees with the result path."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    result_dir = write_result(repo_root, "run.a", "main")
    result = run_publish_result_command(repo_root, result_dir, extra_args=("--variant", "other"))
    assert result.returncode == 2
    assert "variant" in result.stderr


def test_publish_result_branch_rejects_manifest_branch_mismatch(tmp_path: Path) -> None:
    """Reject a result manifest recorded from another source branch."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    result_dir = write_result(repo_root, "run.a", "feature")
    result = run_publish_result_command(repo_root, result_dir)
    assert result.returncode == 2
    assert "run manifest branch" in result.stderr


def test_publish_result_branch_rejects_manifest_symlink(tmp_path: Path) -> None:
    """Reject a run manifest symlink before reading its identity."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    result_dir = write_result(repo_root, "run.a", "main")
    manifest = result_dir / "run_manifest.json"
    target = result_dir / "manifest-target.json"
    target.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(target.name)

    result = run_publish_result_command(repo_root, result_dir)

    assert result.returncode == 2
    assert "run manifest" in result.stderr


def test_publish_result_branch_cas_race_has_one_loser(tmp_path: Path) -> None:
    """Use the observed branch parent as a CAS token for first publication."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    first_dir = write_result(repo_root, "run.a", "main")
    second_dir = write_result(repo_root, "run.b", "main")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda directory: run_publish_result_command(repo_root, directory),
                (first_dir, second_dir),
            )
        )

    assert sorted(result.returncode for result in results) == [0, 2]
    winner = next(result for result in results if result.returncode == 0)
    loser = next(result for result in results if result.returncode == 2)
    assert "RESULT_BRANCH_COMMIT=" in winner.stdout
    assert "update-ref" in loser.stderr
    files = branch_files(repo_root, RESULT_BRANCH)
    run_files = {path for path in files if "/result/smoke.v1/" in path}
    assert any("run.a/" in path for path in run_files) != any(
        "run.b/" in path for path in run_files
    )
