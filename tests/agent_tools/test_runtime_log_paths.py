"""Tests for runtime log path resolution."""

# @dependency-start
# contract test
# responsibility Tests AgentCanon runtime log archive path resolution.
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves active and legacy log archive paths
# upstream design ../../documents/runtime/runtime-log-archive.md runtime log archive ownership and branch policy
# @dependency-end

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Put the current AgentCanon clone ahead of any parent template namespace
# package before importing the implementation under test.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent_tools.runtime_artifacts import RuntimePathEscape, SourceLocalArtifact
from tools.agent_tools.runtime_log_paths import (
    agent_report_archive_dir,
    codex_runtime_index_path,
    codex_runtime_summary_path,
    hook_event_spool_root,
    hook_log_file_name,
    hook_result_search_dirs,
    log_branch_key,
    mounted_log_archive_root,
    repo_log_key,
    runtime_event_publication_outcome_spool_root,
)


class RuntimeLogPathsTest(unittest.TestCase):
    """Exercise runtime log archive path ordering."""

    def runtime_root(self, source: Path) -> Path:
        """Return a sibling runtime root for one temporary source fixture."""
        runtime = source.parent / f".{source.name}.agent-canon-runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        return runtime

    def setUp(self) -> None:
        """Set the stable source remote used by path fixtures."""
        self._old_source_remote = os.environ.get("AGENT_CANON_SOURCE_REPOSITORY_REMOTE")
        self._old_parent_root = os.environ.get("AGENT_CANON_PARENT_ROOT")
        self._old_hook_archive_dir = os.environ.get("AGENT_CANON_HOOK_ARCHIVE_DIR")
        self._old_hook_event_spool_dir = os.environ.get(
            "AGENT_CANON_HOOK_EVENT_SPOOL_DIR"
        )
        self._old_git_ceiling = os.environ.get("GIT_CEILING_DIRECTORIES")
        os.environ["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"] = "https://github.com/test/source.git"
        # Temporary fixture paths live below the repository checkout.  Stop
        # Git discovery at the fixture temp root so a non-Git fixture cannot
        # accidentally inherit the checkout's HEAD or archive overrides.
        os.environ["GIT_CEILING_DIRECTORIES"] = tempfile.gettempdir()
        for env_name in (
            "AGENT_CANON_PARENT_ROOT",
            "AGENT_CANON_HOOK_ARCHIVE_DIR",
            "AGENT_CANON_HOOK_EVENT_SPOOL_DIR",
        ):
            os.environ.pop(env_name, None)

    def tearDown(self) -> None:
        """Restore the caller's source remote environment."""
        if self._old_source_remote is None:
            os.environ.pop("AGENT_CANON_SOURCE_REPOSITORY_REMOTE", None)
        else:
            os.environ["AGENT_CANON_SOURCE_REPOSITORY_REMOTE"] = self._old_source_remote
        for env_name, old_value in (
            ("AGENT_CANON_PARENT_ROOT", self._old_parent_root),
            ("AGENT_CANON_HOOK_ARCHIVE_DIR", self._old_hook_archive_dir),
            ("AGENT_CANON_HOOK_EVENT_SPOOL_DIR", self._old_hook_event_spool_dir),
            ("GIT_CEILING_DIRECTORIES", self._old_git_ceiling),
        ):
            if old_value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = old_value

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
            runtime = self.runtime_root(parent)
            archive_root = mounted_log_archive_root(canon_root, runtime)
            (archive_root / "hook-runs" / "legacy-import").mkdir(parents=True)
            (canon_root / "agents" / "evals" / "results" / "hook-runs").mkdir(parents=True)

            dirs = hook_result_search_dirs(parent, canon_root, runtime)

        self.assertEqual(dirs[0], archive_root / "hook-runs" / repo_log_key(parent))
        self.assertEqual(dirs[1], archive_root / "hook-runs" / "legacy-import")
        self.assertEqual(dirs[2], archive_root / "hook-runs")

    def test_hook_result_search_dirs_standalone_prefers_archive_legacy_before_tree_legacy(self) -> None:
        """Standalone AgentCanon invocation should search mounted legacy import before in-tree legacy logs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            canon_root = Path(temp_dir)
            runtime = self.runtime_root(canon_root)
            archive_root = mounted_log_archive_root(canon_root, runtime)
            (archive_root / "hook-runs" / "legacy-import").mkdir(parents=True)
            (canon_root / "agents" / "evals" / "results" / "hook-runs").mkdir(parents=True)

            dirs = hook_result_search_dirs(canon_root, canon_root, runtime)

        self.assertEqual(dirs[0], archive_root / "hook-runs" / repo_log_key(canon_root))
        self.assertEqual(dirs[1], archive_root / "hook-runs" / "legacy-import")
        self.assertEqual(dirs[2], archive_root / "hook-runs")

    def test_agent_report_archive_dir_uses_repo_key_namespace(self) -> None:
        """Agent report archives should be namespaced by source repository key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "project"
            canon_root = Path(temp_dir) / "agent-canon"
            parent.mkdir()
            canon_root.mkdir()
            runtime = self.runtime_root(canon_root)
            mounted_log_archive_root(canon_root, runtime).mkdir(parents=True)

            report_dir = agent_report_archive_dir(parent, canon_root, runtime)

        self.assertEqual(
            report_dir,
            mounted_log_archive_root(canon_root, runtime) / "agent-reports" / repo_log_key(parent),
        )

    def test_codex_runtime_summary_path_uses_chat_partition_and_index(self) -> None:
        """Codex runtime summaries should write per-chat files plus a repo index."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "project"
            canon_root = Path(temp_dir) / "agent-canon"
            parent.mkdir()
            canon_root.mkdir()
            runtime = self.runtime_root(canon_root)
            mounted_log_archive_root(canon_root, runtime).mkdir(parents=True)

            summary_path = codex_runtime_summary_path(parent, canon_root, "Thread 1", runtime)
            index_path = codex_runtime_index_path(parent, canon_root, runtime)

        archive_namespace = mounted_log_archive_root(canon_root, runtime) / "codex-runtime" / repo_log_key(parent)
        self.assertEqual(summary_path, archive_namespace / "chats" / "thread-1" / "summary-no-git-head.jsonl")
        self.assertEqual(index_path, archive_namespace / "index.jsonl")

    def test_log_branch_key_uses_stable_source_identity(self) -> None:
        """Archive branch keys should ignore environment and Codex chat UUID."""
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

        self.assertEqual(branch_key, repo_log_key(parent))

    def test_log_branch_key_uses_same_identity_without_chat(self) -> None:
        """Non-Codex tools should use the same stable source branch."""
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

        self.assertEqual(branch_key, repo_log_key(parent))

    def test_log_filenames_use_agent_canon_commit_key(self) -> None:
        """Hook and Codex summary files should carry the AgentCanon commit key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "project"
            canon_root = Path(temp_dir) / "agent-canon"
            parent.mkdir()
            canon_root.mkdir()
            head = self.make_git_commit(canon_root)
            runtime = self.runtime_root(canon_root)
            mounted_log_archive_root(canon_root, runtime).mkdir(parents=True)

            summary_path = codex_runtime_summary_path(parent, canon_root, "Thread 1", runtime)
            hook_name = hook_log_file_name("skill_usage", canon_root)

        commit_key = head[:12]
        runtime_root = mounted_log_archive_root(canon_root, runtime) / "codex-runtime" / repo_log_key(parent)
        self.assertEqual(
            summary_path,
            runtime_root / "chats" / "thread-1" / f"summary-{commit_key}.jsonl",
        )
        self.assertEqual(hook_name, f"skill_usage-{commit_key}.jsonl")

    def test_explicit_runtime_root_preserves_caller_namespaces(self) -> None:
        """A shared external root keeps each source repository namespace distinct."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parent = root / "parent"
            caller_a = parent / "caller-a"
            caller_b = parent / "caller-b"
            runtime = root / "runtime"
            parent.mkdir()
            caller_a.mkdir()
            caller_b.mkdir()
            runtime.mkdir()
            archive_a = mounted_log_archive_root(caller_a, runtime)
            archive_b = mounted_log_archive_root(caller_b, runtime)
            spool_a = hook_event_spool_root(caller_a, runtime)
            spool_b = hook_event_spool_root(caller_b, runtime)
            outcome_a = runtime_event_publication_outcome_spool_root(caller_a, runtime)
            outcome_b = runtime_event_publication_outcome_spool_root(caller_b, runtime)

        self.assertEqual(archive_a, runtime / "archive" / "agent-canon-log")
        self.assertEqual(archive_b, archive_a)
        self.assertEqual(spool_a, runtime / "spool" / "hook-events" / repo_log_key(caller_a))
        self.assertEqual(spool_b, runtime / "spool" / "hook-events" / repo_log_key(caller_b))
        self.assertEqual(outcome_a, outcome_b)

    def test_bootstrap_source_runtime_is_spool_only(self) -> None:
        """The canonical source runtime serves spool paths, never archive output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            runtime = source / ".runtime"
            runtime.mkdir()

            self.assertEqual(
                hook_event_spool_root(source, runtime),
                runtime / "spool" / "hook-events" / repo_log_key(source),
            )
            self.assertEqual(
                runtime_event_publication_outcome_spool_root(source, runtime),
                runtime / "spool" / "publication-outcome",
            )
            with self.assertRaises(SourceLocalArtifact):
                mounted_log_archive_root(source, runtime)
            self.assertFalse((runtime / "archive").exists())

    def test_explicit_runtime_root_rejects_external_spool_override(self) -> None:
        """A spool override outside the declared runtime root fails closed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            runtime = root / "runtime"
            external = root / "external"
            source.mkdir()
            runtime.mkdir()
            external.mkdir()
            with patch.dict(os.environ, {"AGENT_CANON_HOOK_EVENT_SPOOL_DIR": str(external)}):
                with self.assertRaises(RuntimePathEscape):
                    hook_event_spool_root(source, runtime)

    def test_explicit_archive_override_reads_external_private_log_mount(self) -> None:
        """Dashboard readers may use the already-mounted private archive checkout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            runtime = root / "runtime"
            private_log = root / "private-log"
            source.mkdir()
            runtime.mkdir()
            private_log.mkdir()
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": str(private_log),
                    "AGENT_CANON_LOG_ROOT": str(private_log),
                },
            ):
                dirs = hook_result_search_dirs(source, source, runtime)

        self.assertEqual(dirs[0], private_log / "hook-runs" / repo_log_key(source))

    def test_absolute_archive_override_rejects_unowned_path(self) -> None:
        """An absolute archive override cannot select an arbitrary external tree."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            runtime = root / "runtime"
            private_log = root / "private-log"
            external = root / "external"
            source.mkdir()
            runtime.mkdir()
            private_log.mkdir()
            external.mkdir()
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": str(external),
                    "AGENT_CANON_LOG_ROOT": str(private_log),
                },
            ):
                with self.assertRaises(RuntimePathEscape):
                    hook_result_search_dirs(source, source, runtime)

    def test_absolute_archive_override_rejects_symlinked_private_mount(self) -> None:
        """A private-log alias cannot redirect the archive reader."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            runtime = root / "runtime"
            private_log = root / "private-log"
            private_alias = root / "private-log-alias"
            source.mkdir()
            runtime.mkdir()
            private_log.mkdir()
            private_alias.symlink_to(private_log, target_is_directory=True)
            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_HOOK_ARCHIVE_DIR": str(private_alias),
                    "AGENT_CANON_LOG_ROOT": str(private_alias),
                },
            ):
                with self.assertRaises(RuntimePathEscape):
                    hook_result_search_dirs(source, source, runtime)


if __name__ == "__main__":
    unittest.main()
