"""Tests for runtime log archive Git helper."""

# @dependency-start
# responsibility Tests runtime log archive Git clone, branch, status, and push behavior.
# upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py manages the ignored log archive clone
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py defines repo keys and archive mount paths
# upstream design ../../documents/runtime-log-archive.md documents archive branch and push policy
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "runtime_log_archive_git.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from runtime_log_paths import repo_log_key  # noqa: E402


class RuntimeLogArchiveGitTest(unittest.TestCase):
    """Validate the runtime log archive Git workflow."""

    def run_tool(
        self,
        *args: str,
        source_root: Path,
        canon_root: Path,
        remote: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Run the archive helper with explicit temp paths."""
        env = os.environ.copy()
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--source-root",
                str(source_root),
                "--canon-root",
                str(canon_root),
                "--remote",
                str(remote),
                *args,
            ],
            check=False,
            capture_output=True,
            env=env,
            text=True,
        )

    def make_remote(self, root: Path) -> Path:
        """Create a local bare remote with a main branch."""
        seed = root / "seed"
        remote = root / "agent-canon-log.git"
        seed.mkdir()
        subprocess.run(["git", "init"], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=seed, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=seed, check=True)
        (seed / "README.md").write_text("# Runtime Log Archive\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "InitialCommit"], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=seed, check=True, capture_output=True)
        subprocess.run(["git", "clone", "--bare", str(seed), str(remote)], check=True, capture_output=True)
        return remote

    def test_repo_key_prints_branch_context(self) -> None:
        """repo-key should show the source-root derived log branch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)

            result = self.run_tool("repo-key", source_root=source, canon_root=canon, remote=remote)

        key = repo_log_key(source)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPO_KEY={key}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_BRANCH=logs/{key}", result.stdout)

    def test_ensure_status_and_push_logs_branch(self) -> None:
        """Ensure should create the clone, and push should commit source repo logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_ENSURE=pass", ensure.stdout)

            archive = canon / ".agent-canon" / "log-archive"
            self.assertTrue((archive / ".git").exists())
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(archive), "branch", "--show-current"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                f"logs/{key}",
            )

            log_path = archive / "hook-runs" / key / "test" / "skill_usage.jsonl"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-1",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "payload_fingerprint": "abc",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            status = self.run_tool(
                "status",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY=yes", status.stdout)

            push = self.run_tool("push", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(push.returncode, 0, push.stdout + push.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", push.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_PUSH=pass", push.stdout)
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(archive), "config", "--get", "user.email"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "agent-canon-log@example.invalid",
            )

            remote_ref = subprocess.run(
                ["git", "--git-dir", str(remote), "show-ref", "--verify", f"refs/heads/logs/{key}"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(remote_ref.returncode, 0, remote_ref.stderr)

    def test_import_legacy_copies_and_deletes_old_jsonl(self) -> None:
        """import-legacy should move old in-tree hook JSONL to the archive."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)

            legacy = canon / "agents" / "evals" / "results" / "hook-runs" / "old-runtime"
            legacy.mkdir(parents=True)
            source_log = legacy / "skill_usage.jsonl"
            source_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "legacy-hook",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            imported = self.run_tool(
                "import-legacy",
                "--delete-source",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_FILES=1", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_DELETED_SOURCE=yes", imported.stdout)
            self.assertFalse(source_log.exists())

            archive_log = (
                canon
                / ".agent-canon"
                / "log-archive"
                / "hook-runs"
                / "legacy-import"
                / "old-runtime"
                / "skill_usage.jsonl"
            )
            self.assertTrue(archive_log.exists())

            pushed = self.run_tool(
                "push",
                "--message",
                "Import legacy logs",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", pushed.stdout)

    def test_import_eval_results_moves_reports_but_keeps_source_notices(self) -> None:
        """import-eval-results should archive legacy reports and retain source notices."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)

            results = canon / "agents" / "evals" / "results"
            skill_dir = results / "skill-workflow-prompt"
            hook_dir = results / "hook-runs"
            skill_dir.mkdir(parents=True)
            hook_dir.mkdir(parents=True)
            root_notice = results / "README.md"
            hook_notice = hook_dir / "README.md"
            family_notice = skill_dir / "README.md"
            report = skill_dir / "skill-eval-20260517T010203040506Z-1234567890-pass-agent-orchestration.md"
            root_notice.write_text("source notice\n", encoding="utf-8")
            hook_notice.write_text("hook notice\n", encoding="utf-8")
            family_notice.write_text("family notice\n", encoding="utf-8")
            report.write_text("EVAL_RUN_ID=skill-eval-20260517T010203040506Z-1234567890\n", encoding="utf-8")

            imported = self.run_tool(
                "import-eval-results",
                "--delete-source",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(imported.returncode, 0, imported.stdout + imported.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_FILES=3", imported.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_DELETIONS=2", imported.stdout)
            self.assertTrue(root_notice.exists())
            self.assertTrue(hook_notice.exists())
            self.assertFalse(family_notice.exists())
            self.assertFalse(report.exists())

            archive = canon / ".agent-canon" / "log-archive" / "eval-results" / "legacy-import"
            self.assertTrue((archive / "README.md").exists())
            self.assertTrue((archive / "skill-workflow-prompt" / family_notice.name).exists())
            self.assertTrue((archive / "skill-workflow-prompt" / report.name).exists())

            pushed = self.run_tool(
                "push",
                "--message",
                "Import legacy eval results",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", pushed.stdout)


if __name__ == "__main__":
    unittest.main()
