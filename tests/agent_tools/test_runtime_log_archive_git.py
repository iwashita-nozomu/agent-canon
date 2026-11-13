"""Black-box tests for the native runtime log archive command."""

# @dependency-start
# contract test
# responsibility Exercises the native archive CLI, local Git publication, and spool retention contract.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/runtime_log_archive.rs owns archive commands
# upstream test ../../tools/runtime/dispatch/agent-canon/tests/runtime_log_archive_native.rs exercises event byte contracts
# upstream design ../../documents/runtime/runtime-log-archive.md archive branch and publication policy
# @dependency-end

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NATIVE = (
    os.environ.get("AGENT_CANON_NATIVE_BIN")
    or os.environ.get("AGENT_CANON_CLI")
    or str(PROJECT_ROOT / "tools/bin/agent-canon")
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout.strip()


def init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Runtime Archive Test")
    git(root, "config", "user.email", "runtime-archive-test@example.invalid")
    (root / "README.md").write_text("runtime archive fixture\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "fixture source")


class RuntimeLogArchiveCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        root = Path(self._temporary.name)
        self.source = root / "source"
        self.canon = root / "agent-canon"
        self.runtime = root / "runtime"
        self.archive = root / "archive-clone"
        self.remote = root / "archive-remote.git"
        init_repo(self.source)
        init_repo(self.canon)
        self.runtime.mkdir()
        git(self.source, "remote", "add", "origin", "https://github.com/example/source.git")
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        seed = root / "archive-seed"
        init_repo(seed)
        git(seed, "remote", "add", "origin", str(self.remote))
        git(seed, "push", "-u", "origin", "main")

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def run_archive(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                NATIVE,
                "runtime-log-archive-git",
                "--source-root",
                str(self.source),
                "--canon-root",
                str(self.canon),
                "--archive-root",
                str(self.archive),
                "--runtime-root",
                str(self.runtime),
                "--remote",
                str(self.remote),
                *args,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_repo_key_and_help_are_native_cli_outputs(self) -> None:
        result = self.run_archive("repo-key")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUNTIME_LOG_ARCHIVE_REPO_KEY=github.com-example-source-", result.stdout)
        help_result = self.run_archive("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for command in ("append-context-discovery", "materialize-runtime-event", "sync", "push"):
            self.assertIn(command, help_result.stdout)

    def test_ensure_sync_push_and_check_clean_read_back_the_branch(self) -> None:
        ensure = self.run_archive("ensure")
        self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
        self.assertIn("RUNTIME_LOG_ARCHIVE_ENSURE=pass", ensure.stdout)
        sync = self.run_archive("sync", "--no-agent-reports")
        self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)
        self.assertIn("RUNTIME_LOG_ARCHIVE_SYNC=pass", sync.stdout)
        self.assertIn("RUNTIME_LOG_ARCHIVE_PUSH_STATUS=committed", sync.stdout)
        clean = self.run_archive("check-clean", "--porcelain")
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=pass", clean.stdout)
        branch = next(line.split("=", 1)[1] for line in sync.stdout.splitlines() if line.startswith("RUNTIME_LOG_ARCHIVE_BRANCH="))
        remote_branch = subprocess.run(
            ["git", "--git-dir", str(self.remote), "rev-parse", "--verify", f"refs/heads/{branch}"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(remote_branch.returncode, 0, remote_branch.stderr)

    def test_no_push_reports_retained_state_and_does_not_change_source(self) -> None:
        before = git(self.source, "status", "--porcelain=v1", "--untracked-files=all")
        result = self.run_archive("sync", "--no-agent-reports", "--no-push")
        after = git(self.source, "status", "--porcelain=v1", "--untracked-files=all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUNTIME_LOG_ARCHIVE_SYNC=partial_retained", result.stdout)
        self.assertEqual(after, before)

    def test_agent_reports_are_copied_under_the_source_key(self) -> None:
        reports = self.source / "reports/agents/run-1"
        reports.mkdir(parents=True)
        (reports / "review.md").write_text("durable report\n", encoding="utf-8")
        result = self.run_archive("archive-agent-reports", "--report-root", str(reports.parent))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORTS=pass", result.stdout)
        source_key = next(line.split("=", 1)[1] for line in result.stdout.splitlines() if line.startswith("RUNTIME_LOG_ARCHIVE_REPO_KEY="))
        self.assertEqual(
            (self.archive / "agent-reports" / source_key / "run-1" / "review.md").read_text(encoding="utf-8"),
            "durable report\n",
        )

    def test_archive_eval_reads_one_collection_and_stages_its_files(self) -> None:
        spool = self.runtime / "spool/eval-run-1"
        (spool / "eval-results").mkdir(parents=True)
        (spool / "producer-logs").mkdir(parents=True)
        (spool / "collection.json").write_text(
            '{"schema":"agent_canon.eval_collection.v1","run_id":"eval-run-1"}\n',
            encoding="utf-8",
        )
        (spool / "eval-results" / "result.json").write_text(
            '{"schema":"fixture.result.v1","status":"pass"}\n', encoding="utf-8"
        )
        result = self.run_archive(
            "archive-eval", "--spool-root", str(spool), "--run-id", "eval-run-1"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUNTIME_LOG_ARCHIVE_EVAL_STATUS=committed", result.stdout)
        self.assertTrue((self.archive / "eval-results" / "result.json").is_file())


if __name__ == "__main__":
    unittest.main()
