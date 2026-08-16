"""Focused tests for root-absence fixed-point filtering."""

# @dependency-start
# contract test
# responsibility Verifies root-absence checks target only existing or index-represented retired paths.
# upstream implementation ../../tools/agent_tools/surface_manifest.py filters root-absence pathspecs by worktree and index state
# upstream design ../../documents/runtime/SHARED_RUNTIME_SURFACES.md owns removed legacy surface semantics
# @dependency-end

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_TEMP_ROOT = PROJECT_ROOT / ".agent-canon" / "test-root-absence-filter"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from surface_manifest import (  # noqa: E402
    SurfaceEntry,
    render_actionable_root_absent_paths,
)


class RootAbsenceFilterTest(unittest.TestCase):
    """Verify the actionable set R intersect (E union I)."""

    def temporary_directory(self) -> tempfile.TemporaryDirectory[str]:
        """Keep test-only repositories below the clone's temp boundary."""
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)

    def git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run one Git command in a fixture repository."""
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )

    def entry(self, path: str = "retired") -> SurfaceEntry:
        """Return one removed-legacy manifest entry."""
        return SurfaceEntry(
            path=path,
            mode="removed_legacy",
            projection_producer="legacy",
            projection_kind="removed_legacy",
            source="",
            local_override_allowed=False,
            optional=False,
        )

    def initialize_repository(self, root: Path) -> None:
        """Initialize isolated Git identity for one fixture."""
        self.git(root, "init")
        self.git(root, "config", "user.email", "agent-canon-test@example.invalid")
        self.git(root, "config", "user.name", "AgentCanon test")

    def test_existing_broken_symlink_remains_actionable(self) -> None:
        """Worktree existence uses lexists so broken retired links are removable."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.initialize_repository(root)
            os.symlink("missing-target", root / "retired")

            self.assertEqual(
                render_actionable_root_absent_paths((self.entry(),), root),
                "retired",
            )

    def test_index_entry_remains_actionable_until_deletion_is_staged(self) -> None:
        """An unstaged removal is actionable, while a staged removal is a fixed point."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.initialize_repository(root)
            retired = root / "retired"
            retired.write_text("legacy\n", encoding="utf-8")
            self.git(root, "add", "retired")
            self.git(root, "commit", "-m", "track retired path")

            retired.unlink()
            self.assertEqual(
                render_actionable_root_absent_paths((self.entry(),), root),
                "retired",
            )

            self.git(root, "add", "-A", "--", "retired")
            self.assertEqual(
                render_actionable_root_absent_paths((self.entry(),), root),
                "",
            )

    def test_committed_absence_is_not_rechecked(self) -> None:
        """A path absent from both worktree and index is already at the fixed point."""
        with self.temporary_directory() as tmp_dir:
            root = Path(tmp_dir)
            self.initialize_repository(root)

            self.assertEqual(
                render_actionable_root_absent_paths((self.entry(),), root),
                "",
            )

    def test_missing_git_state_uses_declarative_fallback(self) -> None:
        """Inspection failure preserves the full manifest set and fails conservatively."""
        with (
            self.temporary_directory() as tmp_dir,
            mock.patch("surface_manifest.subprocess.run", side_effect=OSError),
        ):
            root = Path(tmp_dir)

            self.assertEqual(
                render_actionable_root_absent_paths((self.entry(),), root),
                "retired",
            )


if __name__ == "__main__":
    unittest.main()
