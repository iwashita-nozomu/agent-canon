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

from tools.agent_tools.parent_root_side_effects import (
    ParentRootReject,
    ParentRootSideEffectBoundary,
    ParentRootSideEffectError,
)
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
    RUNTIME_EVENT_PUBLICATION_OUTCOME_SPOOL_RELATIVE,
    runtime_event_publication_outcome_spool_root,
)


class RuntimeLogPathsTest(unittest.TestCase):
    """Exercise runtime log archive path ordering."""

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

    def test_parent_capability_preserves_caller_archive_root(self) -> None:
        """A shared parent must not collapse caller archive namespaces."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "parent"
            caller_a = parent / "caller-a"
            caller_b = parent / "caller-b"
            parent.mkdir()
            caller_a.mkdir()
            caller_b.mkdir()
            self.make_git_commit(parent)

            with patch.dict(os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent)}):
                archive_a = mounted_log_archive_root(caller_a)
                archive_b = mounted_log_archive_root(caller_b)

        self.assertEqual(archive_a, caller_a / ".agent-canon" / "log-archive")
        self.assertEqual(archive_b, caller_b / ".agent-canon" / "log-archive")
        self.assertNotEqual(archive_a, archive_b)

    def test_parent_capability_preserves_caller_hook_spool_root(self) -> None:
        """Hook events remain in the active caller's runtime spool."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "parent"
            caller_a = parent / "caller-a"
            caller_b = parent / "caller-b"
            parent.mkdir()
            caller_a.mkdir()
            caller_b.mkdir()
            self.make_git_commit(parent)

            with patch.dict(os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent)}):
                spool_a = hook_event_spool_root(caller_a)
                spool_b = hook_event_spool_root(caller_b)

        self.assertEqual(
            spool_a,
            caller_a / ".agent-canon" / "runtime-event-spool" / "hook-events" / repo_log_key(caller_a),
        )
        self.assertEqual(
            spool_b,
            caller_b / ".agent-canon" / "runtime-event-spool" / "hook-events" / repo_log_key(caller_b),
        )
        self.assertNotEqual(spool_a, spool_b)

    def test_parent_capability_preserves_caller_publication_outcome_root(self) -> None:
        """Publication outcomes remain in the active caller's runtime spool."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "parent"
            caller_a = parent / "caller-a"
            caller_b = parent / "caller-b"
            parent.mkdir()
            caller_a.mkdir()
            caller_b.mkdir()
            self.make_git_commit(parent)

            with patch.dict(os.environ, {"AGENT_CANON_PARENT_ROOT": str(parent)}):
                spool_a = runtime_event_publication_outcome_spool_root(caller_a)
                spool_b = runtime_event_publication_outcome_spool_root(caller_b)

        self.assertEqual(
            spool_a,
            caller_a / ".agent-canon" / "runtime-event-spool" / "publication-outcome",
        )
        self.assertEqual(
            spool_b,
            caller_b / ".agent-canon" / "runtime-event-spool" / "publication-outcome",
        )
        self.assertNotEqual(spool_a, spool_b)

    def test_publication_outcome_root_uses_one_source_relative_layout(self) -> None:
        """The public resolver and lifecycle lock share one fixed layout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source.mkdir()
            spool_root = runtime_event_publication_outcome_spool_root(source)

        self.assertEqual(
            spool_root.relative_to(source),
            RUNTIME_EVENT_PUBLICATION_OUTCOME_SPOOL_RELATIVE,
        )

    def test_parent_capability_rejects_external_runtime_candidate(self) -> None:
        """An external runtime spool override fails before any write."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parent = root / "parent"
            caller = parent / "caller"
            external = root / "external"
            parent.mkdir()
            caller.mkdir()
            external.mkdir()
            self.make_git_commit(parent)

            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_PARENT_ROOT": str(parent),
                    "AGENT_CANON_HOOK_EVENT_SPOOL_DIR": str(external),
                },
            ):
                with self.assertRaises(ParentRootSideEffectError) as raised:
                    hook_event_spool_root(caller)

        self.assertIs(raised.exception.reject, ParentRootReject.SYMLINK_ESCAPE)
        self.assertFalse((external / repo_log_key(caller)).exists())

    def test_parent_capability_checks_unresolved_logical_candidate(self) -> None:
        """Boundary validation observes the caller path before physical resolution."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir) / "parent"
            caller = parent / "caller"
            override = caller / "override"
            parent.mkdir()
            caller.mkdir()
            self.make_git_commit(parent)
            observed: list[tuple[Path, str]] = []

            def capture(self, attestation, candidate, purpose, *, create=False):
                observed.append((candidate, purpose))
                return object()

            with patch.dict(
                os.environ,
                {
                    "AGENT_CANON_PARENT_ROOT": str(parent),
                    "AGENT_CANON_HOOK_EVENT_SPOOL_DIR": str(override),
                },
            ), patch.object(
                ParentRootSideEffectBoundary,
                "resolve_parent_owned_path",
                capture,
            ):
                result = hook_event_spool_root(caller)

        expected = override / repo_log_key(caller)
        self.assertEqual(observed, [(expected, "runtime-event-spool")])
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
