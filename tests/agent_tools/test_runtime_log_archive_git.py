"""Tests for runtime log archive Git helper."""

# @dependency-start
# contract test
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

from tools.agent_tools.runtime_log_paths import (
    mounted_log_archive_root,
    repo_log_key,
    safe_slug,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "runtime_log_archive_git.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
import runtime_log_archive_git  # noqa: E402


class RuntimeLogArchiveGitTest(unittest.TestCase):
    """Validate the runtime log archive Git workflow."""

    def test_git_index_locked_detects_transient_lock_failure(self) -> None:
        """Index lock errors should be classified for bounded retry."""
        result = subprocess.CompletedProcess(
            ["git", "commit"],
            128,
            "",
            "fatal: Unable to create '.git/index.lock': File exists.",
        )

        self.assertTrue(runtime_log_archive_git.git_index_locked(result))

    def run_tool(
        self,
        *args: str,
        source_root: Path,
        canon_root: Path,
        remote: Path,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the archive helper with explicit temp paths."""
        env = os.environ.copy()
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["AGENT_CANON_LOG_ENV"] = "test-env"
        for env_name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CONVERSATION_ID"):
            env.pop(env_name, None)
        if extra_env:
            env.update(extra_env)
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

    def expected_branch(self, source: Path, chat_key: str | None = None) -> str:
        """Return the deterministic branch expected by run_tool."""
        chat_segment = safe_slug(chat_key) if chat_key else f"no-chat-{repo_log_key(source)}"
        return f"logs/test-env-{chat_segment}"

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
        """repo-key should show the environment-plus-chat derived log branch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            chat_key = "Chat UUID 1"

            result = self.run_tool(
                "repo-key",
                source_root=source,
                canon_root=canon,
                remote=remote,
                extra_env={"CODEX_THREAD_ID": chat_key},
            )

        key = repo_log_key(source)
        expected_branch = self.expected_branch(source, chat_key)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPO_KEY={key}", result.stdout)
        self.assertIn("RUNTIME_LOG_ARCHIVE_BRANCH_KEY=test-env-chat-uuid-1", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_BRANCH={expected_branch}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_RUN_LOCAL={source / 'reports' / 'agents'}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_BRANCH={expected_branch}", result.stdout)
        self.assertIn(
            f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_DIR={mounted_log_archive_root(canon) / 'agent-reports' / key}",
            result.stdout,
        )
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPORTS_ARCHIVE_REL=agent-reports/{key}", result.stdout)

    def test_repo_key_defaults_to_canon_root_when_run_inside_canon_checkout(self) -> None:
        """Running from AgentCanon itself should key logs to the AgentCanon checkout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canon = root / "agent-canon"
            canon.mkdir()
            remote = self.make_remote(root)
            subprocess.run(["git", "init"], cwd=canon, check=True, capture_output=True)
            env = os.environ.copy()
            env["GIT_CONFIG_GLOBAL"] = os.devnull
            env["AGENT_CANON_LOG_ENV"] = "test-env"
            for env_name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_CONVERSATION_ID"):
                env.pop(env_name, None)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--canon-root",
                    str(canon),
                    "--remote",
                    str(remote),
                    "repo-key",
                ],
                check=False,
                capture_output=True,
                cwd=canon,
                env=env,
                text=True,
            )

        key = repo_log_key(canon)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_SOURCE_ROOT={canon}", result.stdout)
        self.assertIn(f"RUNTIME_LOG_ARCHIVE_REPO_KEY={key}", result.stdout)

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
                self.expected_branch(source),
            )

            log_path = archive / "hook-runs" / key / "test" / "skill_usage-no-git-head.jsonl"
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
                ["git", "--git-dir", str(remote), "show-ref", "--verify", f"refs/heads/{self.expected_branch(source)}"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(remote_ref.returncode, 0, remote_ref.stderr)

    def test_ensure_preserves_keyed_dirty_logs_before_branch_switch(self) -> None:
        """Ensure should commit managed dirty logs before switching branches."""
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

            other_ensure = self.run_tool(
                "ensure",
                source_root=other_source,
                canon_root=canon,
                remote=remote,
            )
            self.assertEqual(other_ensure.returncode, 0, other_ensure.stdout + other_ensure.stderr)
            archive = mounted_log_archive_root(canon)
            self.assertEqual(self.archive_branch(archive), self.expected_branch(other_source))

            log_path = archive / "hook-runs" / key / "runtime" / "skill_usage.jsonl"
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

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_ENSURE=pass", ensure.stdout)
            self.assertEqual(self.archive_branch(archive), self.expected_branch(source))
            show = subprocess.run(
                [
                    "git",
                    "-C",
                    str(archive),
                    "show",
                    f"{self.expected_branch(other_source)}:{log_path.relative_to(archive).as_posix()}",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("hook-current-key", show.stdout)

    def test_ensure_preserves_foreign_dirty_logs_before_branch_switch(self) -> None:
        """Ensure should preserve managed logs even when target repo key differs."""
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
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_ENSURE=pass", ensure.stdout)
            self.assertEqual(self.archive_branch(archive), self.expected_branch(source))
            show = subprocess.run(
                [
                    "git",
                    "-C",
                    str(archive),
                    "show",
                    f"{self.expected_branch(other_source)}:{foreign_log.relative_to(archive).as_posix()}",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("foreign-dirty", show.stdout)

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
            self.assertIn("RUNTIME_LOG_ARCHIVE_ERROR=archive has non-runtime local changes", ensure.stdout)
            self.assertEqual(self.archive_branch(archive), self.expected_branch(other_source))
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
            foreign_log = archive / "hook-runs" / other_key / "runtime" / "module_boundary_guard-no-git-head.jsonl"
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
        """check-clean should reject committed trees for other repo keys on a chat branch."""
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
            foreign_log = archive / "hook-runs" / other_key / "runtime" / "skill_usage-no-git-head.jsonl"
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
            self.assertNotEqual(clean_check.returncode, 0, clean_check.stdout + clean_check.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_DIRTY=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", clean_check.stdout)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_FOREIGN_TREE_KEYS={other_key}", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_TREE=yes", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=fail", clean_check.stdout)

    def test_check_clean_allows_source_and_canon_repo_key_trees(self) -> None:
        """A chat branch may contain source and AgentCanon repo-key trees."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            canon_key = repo_log_key(canon)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon)
            canon_log = archive / "hook-runs" / canon_key / "runtime" / "skill_usage-no-git-head.jsonl"
            canon_log.parent.mkdir(parents=True)
            canon_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-associated-canon",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": canon_key,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(archive), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(archive), "config", "user.name", "Test User"], check=True)
            subprocess.run(["git", "-C", str(archive), "add", "hook-runs"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(archive), "commit", "-m", "Commit associated canon tree"],
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
            self.assertEqual(clean_check.returncode, 0, clean_check.stdout + clean_check.stderr)
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_TREE_KEYS={canon_key}", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_TREE_KEYS=", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_TREE=no", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CLEAN=yes", clean_check.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_CHECK_CLEAN=pass", clean_check.stdout)

    def test_status_allows_associated_repo_key_dirty_paths(self) -> None:
        """Dirty logs from source or AgentCanon repo keys are associated chat evidence."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "project"
            canon = root / "agent-canon"
            source.mkdir()
            canon.mkdir()
            remote = self.make_remote(root)
            canon_key = repo_log_key(canon)

            ensure = self.run_tool("ensure", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(ensure.returncode, 0, ensure.stdout + ensure.stderr)
            archive = mounted_log_archive_root(canon)
            canon_log = archive / "hook-runs" / canon_key / "runtime" / "skill_usage.jsonl"
            canon_log.parent.mkdir(parents=True)
            canon_log.write_text(
                json.dumps(
                    {
                        "hook_run_id": "hook-associated-dirty",
                        "timestamp": "2026-05-25T00:00:00Z",
                        "status": "pass",
                        "source_repo_key": canon_key,
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
            self.assertIn(f"RUNTIME_LOG_ARCHIVE_DIRTY_KEYS={canon_key}", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY_KEYS=", status.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no", status.stdout)

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
            runtime_summary = archive / "codex-runtime" / key / "chats" / "thread-1" / "summary-no-git-head.jsonl"
            runtime_summary.parent.mkdir(parents=True)
            runtime_summary.write_text('{"conversation_id": "thread-1", "thread_id": "thread-1"}\n', encoding="utf-8")
            runtime_index = archive / "codex-runtime" / key / "index.jsonl"
            runtime_index.write_text(
                '{"conversation_id": "thread-1", "summary_path": "chats/thread-1/summary-no-git-head.jsonl"}\n',
                encoding="utf-8",
            )
            run_dir = source / "reports" / "agents" / "run-2"
            run_dir.mkdir(parents=True)
            (run_dir / "closeout_gate.md").write_text("closeout=yes\n", encoding="utf-8")

            synced = self.run_tool("sync", source_root=source, canon_root=canon, remote=remote)
            self.assertEqual(synced.returncode, 0, synced.stdout + synced.stderr)
            self.assertIn("RUNTIME_LOG_ARCHIVE_SYNC=pass", synced.stdout)
            self.assertIn("RUNTIME_LOG_ARCHIVE_COMMITTED=yes", synced.stdout)

            clone = root / "verification"
            subprocess.run(["git", "clone", str(remote), str(clone)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(clone), "switch", self.expected_branch(source)], check=True, capture_output=True)
            self.assertTrue((clone / "codex-runtime" / key / "chats" / "thread-1" / "summary-no-git-head.jsonl").exists())
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
                    self.expected_branch(source),
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
