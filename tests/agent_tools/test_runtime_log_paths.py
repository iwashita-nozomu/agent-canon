"""Tests for runtime log path resolution."""

# @dependency-start
# contract test
# responsibility Tests AgentCanon runtime log archive path resolution.
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves active and legacy log archive paths
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and branch policy
# @dependency-end

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.agent_tools.runtime_log_paths import (
    agent_report_archive_dir,
    codex_runtime_index_path,
    codex_runtime_summary_path,
    hook_log_file_name,
    hook_result_search_dirs,
    log_branch_key,
    mounted_log_archive_root,
    repo_log_key,
)


class RuntimeLogPathsTest(unittest.TestCase):
    """Exercise runtime log archive path ordering."""

    def make_git_commit(self, root: Path) -> str:
        """Create one commit in root and return its HEAD SHA."""
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
        (root / "README.md").write_text("# Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=root, check=True, capture_output=True)
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_hook_result_search_dirs_parent_prefers_archive_legacy_before_tree_legacy(self) -> None:
        """Parent repo invocation should search mounted legacy import before in-tree legacy logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            canon_root = parent / "vendor" / "agent-canon"
            archive_root = mounted_log_archive_root(canon_root)
            (archive_root / "hook-runs" / "legacy-import").mkdir(parents=True)
            (canon_root / "agents" / "evals" / "results" / "hook-runs").mkdir(parents=True)

            dirs = hook_result_search_dirs(parent, canon_root)

        self.assertEqual(dirs[0], archive_root / "hook-runs" / repo_log_key(parent))
        self.assertEqual(dirs[1], archive_root / "hook-runs" / "legacy-import")
        self.assertEqual(dirs[2], canon_root / "agents" / "evals" / "results" / "hook-runs")

    def test_hook_result_search_dirs_standalone_prefers_archive_legacy_before_tree_legacy(self) -> None:
        """Standalone AgentCanon invocation should search mounted legacy import before in-tree legacy logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            canon_root = Path(temp_dir)
            archive_root = mounted_log_archive_root(canon_root)
            (archive_root / "hook-runs" / "legacy-import").mkdir(parents=True)
            (canon_root / "agents" / "evals" / "results" / "hook-runs").mkdir(parents=True)

            dirs = hook_result_search_dirs(canon_root, canon_root)

        self.assertEqual(dirs[0], archive_root / "hook-runs" / repo_log_key(canon_root))
        self.assertEqual(dirs[1], archive_root / "hook-runs" / "legacy-import")
        self.assertEqual(dirs[2], canon_root / "agents" / "evals" / "results" / "hook-runs")

    def test_agent_report_archive_dir_uses_repo_key_namespace(self) -> None:
        """Agent report archives should be namespaced by source repository key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "project"
            canon_root = Path(temp_dir) / "agent-canon"
            parent.mkdir()
            canon_root.mkdir()
            mounted_log_archive_root(canon_root).mkdir(parents=True)

            report_dir = agent_report_archive_dir(parent, canon_root)

        self.assertEqual(
            report_dir,
            mounted_log_archive_root(canon_root) / "agent-reports" / repo_log_key(parent),
        )

    def test_codex_runtime_summary_path_uses_chat_partition_and_index(self) -> None:
        """Codex runtime summaries should write per-chat files plus a repo index."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "project"
            canon_root = Path(temp_dir) / "agent-canon"
            parent.mkdir()
            canon_root.mkdir()
            mounted_log_archive_root(canon_root).mkdir(parents=True)

            summary_path = codex_runtime_summary_path(parent, canon_root, "Thread 1")
            index_path = codex_runtime_index_path(parent, canon_root)

        runtime_root = mounted_log_archive_root(canon_root) / "codex-runtime" / repo_log_key(parent)
        self.assertEqual(summary_path, runtime_root / "chats" / "thread-1" / "summary-no-git-head.jsonl")
        self.assertEqual(index_path, runtime_root / "index.jsonl")

    def test_log_branch_key_uses_environment_and_chat(self) -> None:
        """Archive branch keys should be environment plus Codex chat UUID."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "project"
            canon_root = Path(temp_dir) / "agent-canon"
            parent.mkdir()
            canon_root.mkdir()
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_LOG_ENV": "Dev Env",
                    "CODEX_THREAD_ID": "Chat UUID 1",
                    "CODEX_SESSION_ID": "",
                    "CODEX_CONVERSATION_ID": "",
                },
            ):
                branch_key = log_branch_key(parent, canon_root)

        self.assertEqual(branch_key, "dev-env-chat-uuid-1")

    def test_log_branch_key_uses_explicit_no_chat_fallback(self) -> None:
        """Non-Codex tools should use an explicit no-chat branch segment."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "project"
            canon_root = Path(temp_dir) / "agent-canon"
            parent.mkdir()
            canon_root.mkdir()
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_LOG_ENV": "Dev Env",
                    "CODEX_THREAD_ID": "",
                    "CODEX_SESSION_ID": "",
                    "CODEX_CONVERSATION_ID": "",
                },
            ):
                branch_key = log_branch_key(parent, canon_root)

        self.assertEqual(branch_key, f"dev-env-no-chat-{repo_log_key(parent)}")

    def test_log_filenames_use_agent_canon_commit_key(self) -> None:
        """Hook and Codex summary files should carry the AgentCanon commit key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "project"
            canon_root = Path(temp_dir) / "agent-canon"
            parent.mkdir()
            canon_root.mkdir()
            head = self.make_git_commit(canon_root)
            mounted_log_archive_root(canon_root).mkdir(parents=True)

            summary_path = codex_runtime_summary_path(parent, canon_root, "Thread 1")
            hook_name = hook_log_file_name("skill_usage", canon_root)

        commit_key = head[:12]
        runtime_root = mounted_log_archive_root(canon_root) / "codex-runtime" / repo_log_key(parent)
        self.assertEqual(
            summary_path,
            runtime_root / "chats" / "thread-1" / f"summary-{commit_key}.jsonl",
        )
        self.assertEqual(hook_name, f"skill_usage-{commit_key}.jsonl")


if __name__ == "__main__":
    unittest.main()
