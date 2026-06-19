# @dependency-start
# contract test
# responsibility Tests experiment result branch publication behavior.
# upstream design ../../agents/workflows/experiment-workflow.md experiment publication flow
# upstream implementation ../../tools/experiments/publish_result_branch.py helper under test
# @dependency-end

"""Tests for experiment result branch publication."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "experiments"
    / "publish_result_branch.py"
)
RESULT_BRANCH = "experiment-results/demo_topic"


def run_git(repo_root: Path, *args: str) -> str:
    """Run git in the fake repository."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def init_repo(repo_root: Path) -> None:
    """Create a minimal repository on main."""
    repo_root.mkdir()
    run_git(repo_root, "init")
    run_git(repo_root, "checkout", "-b", "main")
    run_git(repo_root, "config", "user.name", "Experiment Test")
    run_git(repo_root, "config", "user.email", "experiment-test@example.invalid")
    (repo_root / "source.py").write_text("print('source')\n", encoding="utf-8")
    run_git(repo_root, "add", "source.py")
    run_git(repo_root, "commit", "-m", "initial source")


def write_result(repo_root: Path, run_name: str, manifest_branch: str) -> Path:
    """Write one managed-result-shaped artifact directory and report."""
    result_dir = repo_root / "experiments" / "demo_topic" / "result" / run_name
    result_dir.mkdir(parents=True)
    report_dir = repo_root / "experiments" / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    source_commit = run_git(repo_root, "rev-parse", "HEAD")
    manifest = {
        "topic": "demo_topic",
        "run_name": run_name,
        "git": {
            "branch": manifest_branch,
            "commit": source_commit,
        },
    }
    (result_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    (result_dir / "summary.json").write_text('{"status": "ok"}\n', encoding="utf-8")
    (result_dir / "cases.jsonl").write_text('{"case": "a"}\n', encoding="utf-8")
    (report_dir / f"{run_name}.md").write_text(
        f"# {run_name}\n",
        encoding="utf-8",
    )
    return result_dir


def run_publish_result_command(
    repo_root_arg: Path,
    result_dir: Path,
    *,
    extra_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Run the publication helper."""
    command = [
        sys.executable,
        str(SCRIPT),
        "--repo-root",
        str(repo_root_arg),
        "--result-dir",
        str(result_dir),
        "--branch",
        RESULT_BRANCH,
    ]
    command.extend(extra_args)
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def branch_files(repo_root: Path, branch: str) -> set[str]:
    """Return files present in a branch tree."""
    output = run_git(repo_root, "ls-tree", "-r", "--name-only", branch)
    return set(output.splitlines())


def test_publish_result_branch_keeps_source_checkout_on_main(tmp_path: Path) -> None:
    """Publishing should update the result branch while leaving checkout on main."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    result_dir = write_result(repo_root, "run_a", "main")

    result = run_publish_result_command(repo_root, result_dir)

    assert result.returncode == 0, result.stderr
    assert "RESULT_BRANCH=experiment-results/demo_topic" in result.stdout
    assert "RESULT_BRANCH_PUSHED=no" in result.stdout
    assert run_git(repo_root, "branch", "--show-current") == "main"
    files = branch_files(repo_root, RESULT_BRANCH)
    assert "experiments/demo_topic/result/run_a/run_manifest.json" in files
    assert "experiments/demo_topic/result/run_a/summary.json" in files
    assert "experiments/report/run_a.md" in files
    assert "source.py" not in files


def test_publish_result_branch_accumulates_runs_on_existing_branch(
    tmp_path: Path,
) -> None:
    """Repeated publications should keep previous result branch artifacts."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    first_dir = write_result(repo_root, "run_a", "main")
    second_dir = write_result(repo_root, "run_b", "main")

    first_result = run_publish_result_command(repo_root, first_dir)
    second_result = run_publish_result_command(repo_root, second_dir)

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    files = branch_files(repo_root, RESULT_BRANCH)
    assert "experiments/demo_topic/result/run_a/summary.json" in files
    assert "experiments/demo_topic/result/run_b/summary.json" in files


def test_publish_result_branch_accepts_repo_subdirectory_argument(
    tmp_path: Path,
) -> None:
    """The helper should resolve --repo-root to the actual Git top-level path."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    tools_dir = repo_root / "tools"
    tools_dir.mkdir()
    result_dir = write_result(repo_root, "run_a", "main")

    result = run_publish_result_command(
        tools_dir,
        result_dir,
    )

    assert result.returncode == 0, result.stderr
    files = branch_files(repo_root, RESULT_BRANCH)
    assert "experiments/demo_topic/result/run_a/summary.json" in files
    assert run_git(repo_root, "branch", "--show-current") == "main"


def test_publish_result_branch_rejects_report_run_name_mismatch(
    tmp_path: Path,
) -> None:
    """A report from a different run should not be published with this result."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    result_dir = write_result(repo_root, "run_a", "main")
    mismatched_report_path = repo_root / "experiments" / "report" / "run_b.md"
    mismatched_report_path.write_text("# run_b\n", encoding="utf-8")

    result = run_publish_result_command(
        repo_root,
        result_dir,
        extra_args=("--report-path", str(mismatched_report_path)),
    )

    assert result.returncode == 2
    assert "report-path must match result run name" in result.stderr


def test_publish_result_branch_rejects_manifest_branch_mismatch(
    tmp_path: Path,
) -> None:
    """The helper should require the run manifest to match the source branch."""
    repo_root = tmp_path / "repo"
    init_repo(repo_root)
    result_dir = write_result(repo_root, "run_a", "feature")

    result = run_publish_result_command(repo_root, result_dir)

    assert result.returncode == 2
    assert "run manifest branch is 'feature'; expected 'main'" in result.stderr
