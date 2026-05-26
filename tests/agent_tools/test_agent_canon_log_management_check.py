"""Tests for AgentCanon log management validation."""

# @dependency-start
# responsibility Tests AgentCanon hook/eval log management validation.
# upstream implementation ../../tools/agent_tools/agent_canon_log_management_check.py validates
# upstream design ../../documents/runtime-log-archive.md hook result accumulation contract
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "agent_canon_log_management_check.py"


class AgentCanonLogManagementCheckTest(unittest.TestCase):
    """Exercise AgentCanon log management validation."""

    def run_checker(self, root: Path) -> subprocess.CompletedProcess[str]:
        """Run the checker against a root."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_repository_passes(self) -> None:
        """The canonical repository has no active log management violations."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_CANON_LOG_MANAGEMENT=pass", result.stdout)

    def test_dirty_eval_log_on_product_branch_fails(self) -> None:
        """Dirty eval logs must not be left on product branches."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root, branch="main")

            result = self.run_checker(root)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("dirty_log_branch", result.stdout)
        self.assertIn("dirty-eval-log-on-main", result.stdout)

    def test_dirty_eval_log_on_agent_logs_branch_passes(self) -> None:
        """Dirty eval logs are allowed on agent-logs branches."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root, branch="agent-logs/example")

            result = self.run_checker(root)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("AGENT_CANON_LOG_MANAGEMENT_DIRTY_EVAL_LOG_PATHS=1", result.stdout)
        self.assertIn("AGENT_CANON_LOG_MANAGEMENT=pass", result.stdout)

    def test_tracked_source_eval_log_fails(self) -> None:
        """Tracked source-tree eval logs must move to the runtime log archive."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root, branch="main")
            subprocess.run(["git", "-C", str(root), "add", "agents/evals/results"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=AgentCanon Test",
                    "-c",
                    "user.email=agent-canon-test@example.invalid",
                    "commit",
                    "-q",
                    "-m",
                    "track logs",
                ],
                check=True,
            )

            result = self.run_checker(root)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("tracked_source_log", result.stdout)
        self.assertIn("AGENT_CANON_LOG_MANAGEMENT_TRACKED_EVAL_LOG_PATHS=1", result.stdout)

    def test_hook_namespace_mismatch_fails(self) -> None:
        """Entry namespace must match the JSONL path namespace."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.init_repo(root, branch="agent-logs/example")
            hook_path = (
                root
                / "agents"
                / "evals"
                / "results"
                / "hook-runs"
                / "path-namespace"
                / "hook.jsonl"
            )
            hook_path.parent.mkdir(parents=True)
            hook_path.write_text(
                json.dumps(self.hook_entry("entry-namespace")) + "\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("hook_log_namespace", result.stdout)
        self.assertIn("entry=entry-namespace;path=path-namespace", result.stdout)

    def test_parent_repo_invocation_checks_vendored_canon(self) -> None:
        """A parent root should check its vendored AgentCanon checkout."""
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            canon_root = parent / "vendor" / "agent-canon"
            self.write_fixture(canon_root, branch="agent-logs/example")

            result = self.run_checker(parent)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            f"AGENT_CANON_LOG_MANAGEMENT_CANON_ROOT={canon_root.resolve().as_posix()}",
            result.stdout,
        )

    def init_repo(self, root: Path, *, branch: str) -> None:
        """Create a small git checkout on the requested branch."""
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "checkout", "-q", "-b", branch], check=True)

    def write_fixture(self, root: Path, *, branch: str) -> None:
        """Write a minimal AgentCanon-like log fixture."""
        self.init_repo(root, branch=branch)
        evals_readme = root / "agents" / "evals" / "README.md"
        evals_readme.parent.mkdir(parents=True)
        evals_readme.write_text("eval definitions\n", encoding="utf-8")
        hook_path = root / "agents" / "evals" / "results" / "hook-runs" / "test" / "hook.jsonl"
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        hook_path.write_text(json.dumps(self.hook_entry("test")) + "\n", encoding="utf-8")

    def hook_entry(self, namespace: str) -> dict[str, str]:
        """Return one valid hook entry."""
        return {
            "hook_run_id": "hook-20260525T000000000000Z-1234567890-abcdef1234",
            "timestamp": "2026-05-25T00:00:00Z",
            "status": "pass",
            "payload_fingerprint": "abcdef123456",
            "hook_log_namespace": namespace,
        }


if __name__ == "__main__":
    unittest.main()
