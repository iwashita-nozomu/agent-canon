"""Regression tests for layout-only public command projection."""

# @dependency-start
# contract test
# responsibility Proves that layout-only rendering is pure while concrete public-view validation remains fail-closed.
# upstream implementation ../../tools/agent_tools/skill_tool_commands.py public command projection owner
# upstream implementation ../../tools/agent_tools/agent_canon_source_root.py typed root resolution and failure owner
# @dependency-end

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from agent_canon_source_root import RootResolution, SourceRootFailure  # noqa: E402
from skill_tool_commands import (  # noqa: E402
    project_public_command,
    project_public_command_for_layout,
)


class SkillToolCommandsLayoutProjectionTest(unittest.TestCase):
    """Keep spelling projection separate from authenticated path validation."""

    def test_layout_only_projection_does_not_require_a_materialized_vendor_view(self) -> None:
        """A layout token alone must not consult the ambient working tree."""
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.chdir(tmp_dir)
            try:
                projection = project_public_command_for_layout(
                    "PYTHONPATH=tools python3 tools/agent_tools/search.py --query fixture",
                    layout="vendored",
                )
            finally:
                os.chdir(previous)

        self.assertEqual(
            projection.public_env,
            (("PYTHONPATH", "vendor/agent-canon/tools"),),
        )
        self.assertEqual(
            projection.public_argv,
            (
                "python3",
                "vendor/agent-canon/tools/agent_tools/search.py",
                "--query",
                "fixture",
            ),
        )

    def test_concrete_vendored_resolution_still_rejects_a_missing_executable(self) -> None:
        """Removing ambient validation must not weaken authenticated view checks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            source_root = workspace / "vendor" / "agent-canon"
            resolution = RootResolution(
                current_repository_root=workspace,
                source_root=source_root,
                layout="vendored",
                canon_root=source_root,
                public_tool_root=source_root / "tools",
            )

            with self.assertRaises(SourceRootFailure) as raised:
                project_public_command(
                    "python3 tools/agent_tools/search.py --query fixture",
                    resolution,
                )

        self.assertEqual(raised.exception.code, "agent_canon_public_command_missing")


if __name__ == "__main__":
    unittest.main()
