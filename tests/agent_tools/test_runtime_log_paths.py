"""Tests for runtime log path resolution."""

# @dependency-start
# responsibility Tests AgentCanon runtime log archive path resolution.
# upstream implementation ../../tools/agent_tools/runtime_log_paths.py resolves active and legacy log archive paths
# upstream design ../../documents/runtime-log-archive.md runtime log archive ownership and branch policy
# @dependency-end

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))
from runtime_log_paths import (  # noqa: E402
    hook_result_search_dirs,
    mounted_log_archive_root,
    repo_log_key,
)


class RuntimeLogPathsTest(unittest.TestCase):
    """Exercise runtime log archive path ordering."""

    def test_hook_result_search_dirs_parent_prefers_archive_legacy_before_tree_legacy(self) -> None:
        """Parent repo invocation should search mounted legacy import before in-tree fallback."""
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
        """Standalone AgentCanon invocation should search mounted legacy import before in-tree fallback."""
        with tempfile.TemporaryDirectory() as temp_dir:
            canon_root = Path(temp_dir)
            archive_root = mounted_log_archive_root(canon_root)
            (archive_root / "hook-runs" / "legacy-import").mkdir(parents=True)
            (canon_root / "agents" / "evals" / "results" / "hook-runs").mkdir(parents=True)

            dirs = hook_result_search_dirs(canon_root, canon_root)

        self.assertEqual(dirs[0], archive_root / "hook-runs" / repo_log_key(canon_root))
        self.assertEqual(dirs[1], archive_root / "hook-runs" / "legacy-import")
        self.assertEqual(dirs[2], canon_root / "agents" / "evals" / "results" / "hook-runs")


if __name__ == "__main__":
    unittest.main()
