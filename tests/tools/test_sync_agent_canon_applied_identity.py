# @dependency-start
# contract test
# responsibility Verifies ensure-latest receipts use post-materialization Git identity.
# upstream implementation ../../tools/sync_agent_canon.sh derives applied identity readback
# upstream design ../../documents/agent-canon/agent-canon-update-route.md update acceptance
# @dependency-end

"""Regression tests for ensure-latest applied identity receipts."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_TEST_ROOT = Path(__file__).resolve().parent
if str(TOOLS_TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_TEST_ROOT))

import test_update_agent_canon as update_tests  # noqa: E402


class EnsureLatestAppliedIdentityTest(unittest.TestCase):
    """Keep successful receipts bound to the materialized branch and upstream."""

    @staticmethod
    def git_output(cwd: Path, *args: str) -> str:
        """Run one read-only Git command and return its stripped stdout."""
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def isolate_receipt_owner(self, repo: Path) -> None:
        """Stop the derived fixture before unrelated root-view projection."""
        script = repo / "tools" / "sync_agent_canon.sh"
        text = script.read_text(encoding="utf-8")
        needle = (
            "    cmd_link_root\n"
            '    commit_sync_paths_if_needed "$remote_sha" "submodule_update"\n'
            "    return\n"
        )
        replacement = (
            "    # Focused receipt fixture omits the unrelated root-view projection.\n"
            "    return\n"
        )
        self.assertEqual(text.count(needle), 1)
        script.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
        subprocess.run(
            ["git", "add", "--", "tools/sync_agent_canon.sh"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "isolate applied receipt fixture"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def make_old_alias_fixture(self, root: Path) -> tuple[Path, Path, str, str]:
        """Create main@new while unrelated origin/origin remains at the old pin."""
        fixture = object.__new__(update_tests.SubmoduleUpdateAgentCanonTest)
        bare_repo, work_dir = fixture.make_agent_canon_remote(root)
        repo = fixture.make_superproject(root, bare_repo)
        submodule = repo / "vendor" / "agent-canon"
        self.isolate_receipt_owner(repo)
        old_pin = self.git_output(submodule, "rev-parse", "HEAD")

        subprocess.run(
            ["git", "push", "origin", f"{old_pin}:refs/heads/origin"],
            cwd=work_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        (work_dir / "remote-marker.txt").write_text("new main\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "--", "remote-marker.txt"], cwd=work_dir, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "advance main"], cwd=work_dir, check=True
        )
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=work_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        new_main = self.git_output(work_dir, "rev-parse", "HEAD")
        subprocess.run(
            [
                "git",
                "fetch",
                "origin",
                "refs/heads/origin:refs/remotes/origin/origin",
            ],
            cwd=submodule,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            self.git_output(submodule, "rev-parse", "origin/origin^{commit}"),
            old_pin,
        )
        self.assertNotEqual(old_pin, new_main)
        return repo, submodule, old_pin, new_main

    @staticmethod
    def run_ensure_latest(repo: Path) -> subprocess.CompletedProcess[str]:
        """Run the authorized low-level update route under test."""
        return subprocess.run(
            ["bash", "tools/sync_agent_canon.sh", "ensure-latest", "main"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=update_tests.authorized_test_env(),
        )

    def test_receipt_ignores_old_unrelated_remote_alias(self) -> None:
        """An old origin/origin alias cannot name the applied main checkout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo, submodule, _old_pin, new_main = self.make_old_alias_fixture(
                Path(tmp_dir)
            )

            result = self.run_ensure_latest(repo)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for receipt in (
                "agent_canon_latest=updating_submodule",
                "agent_canon_latest_branch=main",
                "agent_canon_latest_submodule_branch=main",
                "agent_canon_latest_remote_branch=origin/main",
                "agent_canon_latest_submodule_applied_branch=main",
                "agent_canon_latest_submodule_applied_remote_branch=origin/main",
                f"agent_canon_latest_submodule_applied_head={new_main}",
                f"agent_canon_latest_submodule_staged_pin={new_main}",
                "agent_canon_latest_submodule_applied_upstream=origin/main",
                f"agent_canon_latest_submodule_applied_upstream_sha={new_main}",
            ):
                self.assertIn(receipt, result.stdout)
            self.assertNotIn("origin/origin", result.stdout)
            self.assertEqual(
                self.git_output(submodule, "branch", "--show-current"), "main"
            )
            self.assertEqual(
                self.git_output(
                    submodule,
                    "for-each-ref",
                    "--format=%(upstream:short)",
                    "refs/heads/main",
                ),
                "origin/main",
            )
            self.assertEqual(
                self.git_output(submodule, "rev-parse", "HEAD"), new_main
            )
            self.assertEqual(
                self.git_output(submodule, "rev-parse", "@{upstream}^{commit}"),
                new_main,
            )

    def test_receipt_fails_closed_on_branch_config_mismatch(self) -> None:
        """A configured upstream that contradicts requested main blocks success."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo, submodule, old_pin, new_main = self.make_old_alias_fixture(
                Path(tmp_dir)
            )
            subprocess.run(
                ["git", "config", "branch.main.merge", "refs/heads/origin"],
                cwd=submodule,
                check=True,
            )

            result = self.run_ensure_latest(repo)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "agent_canon_latest_submodule_applied_identity_error=readback_mismatch",
                result.stderr,
            )
            self.assertNotIn("agent_canon_latest=updating_submodule", result.stdout)
            self.assertNotIn(
                "agent_canon_latest_submodule_staged_pin=", result.stdout
            )
            self.assertEqual(
                self.git_output(submodule, "rev-parse", "HEAD"), new_main
            )
            self.assertEqual(
                self.git_output(repo, "rev-parse", ":vendor/agent-canon"), old_pin
            )


if __name__ == "__main__":
    unittest.main()
