# @dependency-start
# @dependency-end

"""Tests for worktree scope linting."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "worktree_scope_lint.py"


def write_scope(
    workspace_root: Path,
    *,
    branch: str = "main",
    worktree_path: Path | None = None,
    editable: Path | None = None,
    readonly: Path | None = None,
) -> Path:
    """Write a concrete WORKTREE_SCOPE.md for one temporary workspace."""
    action_log = workspace_root / "notes" / "worktrees" / "worktree_test.md"
    action_log.parent.mkdir(parents=True, exist_ok=True)
    action_log.write_text("# Worktree Test\n\n## Action Log\n\n- kickoff\n", encoding="utf-8")
    resolved_worktree_path = worktree_path or workspace_root
    resolved_editable = editable or workspace_root
    resolved_readonly = readonly or (workspace_root / "readonly")
    scope_path = workspace_root / "WORKTREE_SCOPE.md"
    scope_path.write_text(
        "\n".join(
            [
                "# WORKTREE_SCOPE",
                "",
                "## Worktree Summary",
                f"- Branch: {branch}",
                f"- Worktree path: `{resolved_worktree_path}`",
                "- Purpose: test scope lint",
                "- Owner or agent: test",
                "",
                "## Kickoff Status",
                "- Scope refreshed at: 2026-04-10",
                f"- Action log path: `{action_log}`",
                "- Branch summary path: none",
                "- User request contract path: none",
                "- Kickoff checks completed: yes",
                "- Next step after kickoff: run lint",
                "",
                "## Editable Directories",
                f"- `{resolved_editable}`",
                "",
                "## Runtime Output Directories",
                f"- `{workspace_root / 'result'}`",
                "",
                "## Read-Only Or Avoid Directories",
                f"- `{resolved_readonly}`",
                "",
                "## Required References Before Editing",
                "- `documents/worktree-lifecycle.md`",
                "- `documents/BRANCH_SCOPE.md`",
                "- `notes/worktrees/README.md`",
                "",
                "## Main Carry-Over Targets",
                f"- `{action_log}`",
                "",
                "## Working Notes During Execution",
                f"- Action log path: `{action_log}`",
                "- Branch summary path: none",
                "",
                "## Required Checks Before Commit",
                "- `pytest`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return scope_path


class WorktreeScopeLintTest(unittest.TestCase):
    """Verify branch, path, and write-scope checks."""

    def test_rejects_stale_branch_and_path(self) -> None:
        """The linter should reject a scope copied from a different worktree."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "--initial-branch=main"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            write_scope(
                workspace_root,
                branch="other-branch",
                worktree_path=workspace_root.parent / "other-worktree",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--workspace-root", str(workspace_root)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Branch", result.stdout)
            self.assertIn("current branch", result.stdout)
            self.assertIn("Worktree path", result.stdout)
            self.assertIn("current worktree root", result.stdout)

    def test_rejects_changed_files_outside_editable_or_inside_readonly(self) -> None:
        """The linter should catch worktree scope write violations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init", "--initial-branch=main"],
                cwd=workspace_root,
                check=True,
                capture_output=True,
                text=True,
            )
            editable = workspace_root / "allowed"
            readonly = workspace_root / "readonly"
            editable.mkdir()
            readonly.mkdir()
            (editable / "ok.txt").write_text("ok\n", encoding="utf-8")
            outside = workspace_root / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            blocked = readonly / "blocked.txt"
            blocked.write_text("blocked\n", encoding="utf-8")
            write_scope(workspace_root, editable=editable, readonly=readonly)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--workspace-root", str(workspace_root)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Editable Directories", result.stdout)
            self.assertIn(str(outside), result.stdout)
            self.assertIn("Read-Only Or Avoid Directories", result.stdout)
            self.assertIn(str(blocked), result.stdout)


if __name__ == "__main__":
    unittest.main()
