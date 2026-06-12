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

from tools.agent_tools.runtime_log_paths import mounted_log_archive_root, repo_log_key

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "runtime_log_archive_git.py"


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
        """Create a temporary Git remote with a main branch."""
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

    def archive_branch(self, archive: Path) -> str:
        """Return the currently checked out archive branch."""
        return subprocess.run(
            ["git", "-C", str(archive), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

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
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL={source / 'reports' / 'agents'}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH=logs/{key}", result.stdout)
        self.assertIn(
            f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR={mounted_log_archive_root(canon) / 'agent-reports' / key}",
            result.stdout,
        )
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_REL=agent-reports/{key}", result.stdout)

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

            archive = mounted_log_archive_root(canon)
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
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={key}", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY=yes", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", status.stdout)

            dirty_clean_check = self.run_tool(
                "check-clean",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertNotEqual(dirty_clean_check.returncode, 0, dirty_clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=no", dirty_clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=fail", dirty_clean_check.stdout)

            push = self.run_tool("push", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(push.returncode, 0, push.stdout + push.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", push.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_PUSH=pass", push.stdout)

            clean_check = self.run_tool(
                "check-clean",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(clean_check.returncode, 0, clean_check.stdout + clean_check.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=yes", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=pass", clean_check.stdout)
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

    def test_ensure_moves_current_key_dirty_logs_to_expected_branch(self) -> None:
        """Ensure should preserve current repo-key dirt when switching from another log branch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            other_key = repo_log_key(other_source)

            source_ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(source_ensure.returncode, 0, source_ensure.stdout + source_ensure.stderr)
            archive = mounted_log_archive_root(canon)
            log_path = archive / "hook-runs" / key / "runtime" / "skill_usage.jsonl"
            context_path = archive / "hook-runs" / key / "runtime" / "skill_usage_context.json"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-existing",
                        "timestamp": "2026-05-24T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": key,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            context_path.write_text(
                json.dumps(
                    {
                        "workflows": ["Scoped Change Lite"],
                        "report_dir": str(source / "reports" / "agents" / "run-old"),
                        "timestamp": "2026-05-24T00:00:00Z",
                        "source_event": "PromptSubmit",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            initial_push = self.run_tool("push", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(initial_push.returncode, 0, initial_push.stdout + initial_push.stderr)

            other_ensure = self.run_tool(
                "ensure",
                source_root=other_source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(other_ensure.returncode, 0, other_ensure.stdout + other_ensure.stderr)
            self.assertEqual(self.archive_branch(archive), f"logs/{other_key}")

            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-current-key",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": key,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            context_path.write_text(
                json.dumps(
                    {
                        "workflows": ["Scoped Change", "python-review"],
                        "report_dir": str(source / "reports" / "agents" / "run-new"),
                        "timestamp": "2026-05-25T00:00:00Z",
                        "source_event": "PostToolUse",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertEqual(self.archive_branch(archive), f"logs/{key}")
            self.assertTrue(log_path.exists())
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("hook-existing", log_text)
            self.assertIn("hook-current-key", log_text)
            merged_context = json.loads(context_path.read_text(encoding="utf-8"))
            self.assertEqual(
                merged_context,
                {
                    "workflows": ["Scoped Change Lite", "Scoped Change", "python-review"],
                    "report_dir": str(source / "reports" / "agents" / "run-new"),
                    "timestamp": "2026-05-25T00:00:00Z",
                    "source_event": "PostToolUse",
                },
            )

            status = self.run_tool(
                "status",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_BRANCH_MATCH=yes", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY=yes", status.stdout)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={key}", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY=yes", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_GLOBAL_DIRTY=no", status.stdout)

            pushed = self.run_tool("push", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            remote_tree = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(remote),
                    "ls-tree",
                    "-r",
                    "--name-only",
                    f"logs/{key}",
                    "--",
                    "hook-runs",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn(f"hook-runs/{key}/runtime/skill_usage.jsonl", remote_tree.stdout)
            self.assertIn(f"hook-runs/{key}/runtime/skill_usage_context.json", remote_tree.stdout)

    def test_ensure_rejects_same_key_unmergeable_json_conflict(self) -> None:
        """Ensure should keep unsafe same-key JSON conflicts as blockers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            other_key = repo_log_key(other_source)

            source_ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(source_ensure.returncode, 0, source_ensure.stdout + source_ensure.stderr)
            archive = mounted_log_archive_root(canon)
            unsafe_path = archive / "hook-runs" / key / "runtime" / "tool_context.json"
            unsafe_path.parent.mkdir(parents=True)
            unsafe_path.write_text('{"value": "target"}\n', encoding="utf-8")
            initial_push = self.run_tool("push", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(initial_push.returncode, 0, initial_push.stdout + initial_push.stderr)

            other_ensure = self.run_tool(
                "ensure",
                source_root=other_source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(other_ensure.returncode, 0, other_ensure.stdout + other_ensure.stderr)
            self.assertEqual(self.archive_branch(archive), f"logs/{other_key}")
            unsafe_path.parent.mkdir(parents=True)
            unsafe_path.write_text('{"value": "dirty"}\n', encoding="utf-8")

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertNotEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertIn(
                "RUNTIME_LOG_ARCHIVE_ERROR=archive current repo-key changes were preserved in stash@{0}",
                ensure.stdout,
            )
            self.assertIn("but restoring them on", ensure.stdout)
            self.assertIn("archive destination already exists with different content", ensure.stdout)
            self.assertEqual(self.archive_branch(archive), f"logs/{key}")
            self.assertEqual(unsafe_path.read_text(encoding="utf-8"), '{"value": "target"}\n')

    def test_ensure_rejects_foreign_dirty_logs_before_branch_switch(self) -> None:
        """Ensure should not switch branches when dirty paths belong to another repo key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            other_key = repo_log_key(other_source)

            other_ensure = self.run_tool(
                "ensure",
                source_root=other_source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(other_ensure.returncode, 0, other_ensure.stdout + other_ensure.stderr)
            archive = mounted_log_archive_root(canon)
            foreign_log = archive / "hook-runs" / other_key / "runtime" / "skill_usage.jsonl"
            foreign_log.parent.mkdir(parents=True)
            foreign_log.write_text('{"hook_run_id": "foreign-dirty"}\n', encoding="utf-8")

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertNotEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_ERROR=archive has local changes", ensure.stdout)
            self.assertEqual(self.archive_branch(archive), f"logs/{other_key}")
            self.assertTrue(foreign_log.exists())

    def test_ensure_rejects_archive_level_dirty_paths_before_branch_switch(self) -> None:
        """Ensure should not auto-preserve archive-level policy/tool dirt."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            other_key = repo_log_key(other_source)

            other_ensure = self.run_tool(
                "ensure",
                source_root=other_source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(other_ensure.returncode, 0, other_ensure.stdout + other_ensure.stderr)
            archive = mounted_log_archive_root(canon)
            tool_path = archive / "tools" / "runtime_log_dashboard.py"
            tool_path.parent.mkdir(parents=True)
            tool_path.write_text("# dashboard change\n", encoding="utf-8")

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertNotEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_ERROR=archive has local changes", ensure.stdout)
            self.assertEqual(self.archive_branch(archive), f"logs/{other_key}")
            self.assertTrue(tool_path.exists())

    def test_status_reports_foreign_repo_key_dirty_paths(self) -> None:
        """status/check-clean should expose dirty paths for another repo key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            other_key = repo_log_key(other_source)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon)
            foreign_log = archive / "hook-runs" / other_key / "runtime" / "module_boundary_guard.jsonl"
            foreign_log.parent.mkdir(parents=True)
            foreign_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-foreign",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": other_key,
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
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={other_key}", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY=no", status.stdout)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY_KEYS={other_key}", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=yes", status.stdout)
            self.assertNotIn(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={key}", status.stdout)

            clean_check = self.run_tool(
                "check-clean",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertNotEqual(clean_check.returncode, 0, clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=fail", clean_check.stdout)

    def test_check_clean_rejects_committed_foreign_repo_key_tree(self) -> None:
        """check-clean should fail when a clean branch already contains another repo key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            other_source = root / "agent-canon-standalone"
            source.mkdir()
            canon.mkdir()
            other_source.mkdir()
            remote = self.make_remote(root)
            other_key = repo_log_key(other_source)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon)
            foreign_log = archive / "hook-runs" / other_key / "runtime" / "skill_usage.jsonl"
            foreign_log.parent.mkdir(parents=True)
            foreign_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-committed-foreign",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": other_key,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(archive), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(archive), "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", str(archive), "add", "hook-runs"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(archive), "commit", "-m", "Commit foreign tree"],
                check=True,
                capture_output=True,
            )

            clean_check = self.run_tool(
                "check-clean",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertNotEqual(clean_check.returncode, 0, clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", clean_check.stdout)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_FOREIGN_TREE_KEYS={other_key}", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_TREE=yes", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=fail", clean_check.stdout)

    def test_status_reports_archive_level_dirty_paths(self) -> None:
        """Status should separate archive-level tool or policy dirt from repo-key logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon)
            tool_path = archive / "tools" / "runtime_log_dashboard.py"
            tool_path.parent.mkdir(parents=True)
            tool_path.write_text("# dashboard tool update\n", encoding="utf-8")

            status = self.run_tool(
                "status",
                "--porcelain",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY=yes", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY_KEYS=", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CURRENT_KEY_DIRTY=no", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_GLOBAL_DIRTY=yes", status.stdout)
            self.assertIn("commit or revert archive-level dirty paths", status.stdout)

    def test_archive_agent_reports_copies_run_bundles(self) -> None:
        """archive-agent-reports should copy reports/agents into the log branch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)
            run_dir = source / "reports" / "agents" / "run-1"
            run_dir.mkdir(parents=True)
            (source / "reports" / "agents" / ".active_run").write_text("run-1\n", encoding="utf-8")
            (run_dir / "summary.md").write_text("# Summary\n", encoding="utf-8")
            (run_dir / "state.json").write_text('{"ok": true}\n', encoding="utf-8")

            archived = self.run_tool(
                "archive-agent-reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(archived.returncode, 0, archived.stdout + archived.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_FILES=2", archived.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_COPIED=2", archived.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SKIPPED=1", archived.stdout)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_REL=agent-reports/{key}", archived.stdout)

            archive = mounted_log_archive_root(canon)
            self.assertTrue((archive / "agent-reports" / key / "run-1" / "summary.md").exists())
            self.assertTrue((archive / "agent-reports" / key / "run-1" / "state.json").exists())
            self.assertFalse((archive / "agent-reports" / key / ".active_run").exists())

            pushed = self.run_tool(
                "push",
                "--message",
                "Archive agent reports",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", pushed.stdout)

    def test_sync_pushes_codex_runtime_and_agent_reports(self) -> None:
        """Sync should be the unattended path for runtime summaries and agent reports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)

            ensured = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensured.returncode, 0, ensured.stdout + ensured.stderr)
            archive = mounted_log_archive_root(canon)
            runtime_summary = archive / "codex-runtime" / key / "chats" / "thread-1" / "summary.jsonl"
            runtime_summary.parent.mkdir(parents=True)
            runtime_summary.write_text('{"conversation_id": "thread-1", "thread_id": "thread-1"}\n', encoding="utf-8")
            runtime_index = archive / "codex-runtime" / key / "index.jsonl"
            runtime_index.write_text('{"conversation_id": "thread-1", "summary_path": "chats/thread-1/summary.jsonl"}\n', encoding="utf-8")
            run_dir = source / "reports" / "agents" / "run-2"
            run_dir.mkdir(parents=True)
            (run_dir / "closeout_gate.md").write_text("closeout=yes\n", encoding="utf-8")

            synced = self.run_tool("sync", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_SYNC=pass", synced.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", synced.stdout)

            clone = root / "verification"
            subprocess.run(["git", "clone", str(remote), str(clone)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(clone), "switch", f"logs/{key}"], check=True, capture_output=True)
            self.assertTrue((clone / "codex-runtime" / key / "chats" / "thread-1" / "summary.jsonl").exists())
            self.assertTrue((clone / "codex-runtime" / key / "index.jsonl").exists())
            self.assertTrue((clone / "agent-reports" / key / "run-2" / "closeout_gate.md").exists())

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
                mounted_log_archive_root(canon)
                / "legacy-import"
                / "hook-runs"
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

    def test_import_eval_results_moves_reports_and_removes_source_tree(self) -> None:
        """import-eval-results should archive legacy reports and delete source notices."""
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
            self.assertIn("RUNTIME_LOG_ARCHIVE_IMPORT_EVAL_RESULTS_SOURCE_DELETIONS=4", imported.stdout)
            self.assertFalse(root_notice.exists())
            self.assertFalse(hook_notice.exists())
            self.assertFalse(family_notice.exists())
            self.assertFalse(report.exists())

            archive = mounted_log_archive_root(canon) / "legacy-import" / "eval-results"
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

    def test_archive_agent_report_snapshots_run_bundle_and_pushes(self) -> None:
        """archive-agent-report should copy a run bundle into agent-reports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            key = repo_log_key(source)

            report_dir = source / "reports" / "agents" / "run-1"
            report_dir.mkdir(parents=True)
            (report_dir / "verification.txt").write_text("status=pass\n", encoding="utf-8")
            (report_dir / "work_log.md").write_text("# Work Log\n\n- done\n", encoding="utf-8")

            archived = self.run_tool(
                "archive-agent-report",
                "--report-dir",
                str(report_dir),
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(archived.returncode, 0, archived.stdout + archived.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT=pass", archived.stdout)
            snapshot_line = next(
                line
                for line in archived.stdout.splitlines()
                if line.startswith("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_SNAPSHOT=")
            )
            snapshot = snapshot_line.split("=", 1)[1]
            archive = mounted_log_archive_root(canon) / "agent-reports" / key / "run-1" / snapshot
            self.assertTrue((archive / "verification.txt").exists())
            self.assertTrue((archive / "archive_manifest.json").exists())
            manifest = json.loads((archive / "archive_manifest.json").read_text(encoding="utf-8"))
            self.assertIn("codex_trace_key", manifest)
            self.assertIn("source_git_head", manifest)
            index_path = mounted_log_archive_root(canon) / "agent-reports" / key / "index.jsonl"
            first_index = index_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(first_index), 1)

            archived_again = self.run_tool(
                "archive-agent-report",
                "--report-dir",
                str(report_dir),
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(archived_again.returncode, 0, archived_again.stdout + archived_again.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_AGENT_REPORT_INDEX_APPENDED=no", archived_again.stdout)
            self.assertEqual(index_path.read_text(encoding="utf-8").splitlines(), first_index)

            pushed = self.run_tool(
                "push",
                "--message",
                "Archive agent report",
                source_root=source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", pushed.stdout)
            remote_tree = subprocess.run(
                [
                    "git",
                    "--git-dir",
                    str(remote),
                    "ls-tree",
                    "-r",
                    "--name-only",
                    f"logs/{key}",
                    "--",
                    "agent-reports",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("agent-reports", remote_tree.stdout)


if __name__ == "__main__":
    unittest.main()
