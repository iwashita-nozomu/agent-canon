"""Focused regression tests for semantic orphan lifecycle inventory."""

# @dependency-start
# contract test
# responsibility Verifies semantic branch, PR, and worktree classification plus fail-closed cleanup admission.
# upstream implementation ../../tools/repository/git/orphan_lifecycle.py inventories and classifies orphan candidates.
# upstream design ../../documents/operations/orphan-lifecycle.md defines lifecycle states and cleanup admission.
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = PROJECT_ROOT / "tools" / "repository" / "git" / "orphan_lifecycle.py"


def load_tool() -> ModuleType:
    """Load the standalone tool as a module."""
    spec = importlib.util.spec_from_file_location("orphan_lifecycle", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load orphan lifecycle tool")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOOL = load_tool()


class GitFixture:
    """Small repository with a bare origin and current remote-tracking main."""

    def __init__(self, root: Path) -> None:
        """Initialize a repository fixture below ``root``."""
        self.root = root
        self.repo = root / "repo"
        self.remote = root / "origin.git"
        self.git_at(root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git_at(root, "init", "--initial-branch=main", str(self.repo))
        self.git("config", "user.name", "Orphan Test")
        self.git("config", "user.email", "orphan@example.invalid")
        self.write("base.txt", "base\n")
        self.git("add", "base.txt")
        self.git("commit", "-m", "base")
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-u", "origin", "main")

    @staticmethod
    def git_at(cwd: Path, *args: str) -> str:
        """Run Git and return stdout."""
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout.strip()

    def git(self, *args: str) -> str:
        """Run Git in the fixture repository."""
        return self.git_at(self.repo, *args)

    def write(self, relative: str, text: str) -> None:
        """Write a fixture file."""
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def branch_with_commit(
        self,
        branch: str,
        *,
        path: str,
        text: str,
        push: bool = True,
    ) -> str:
        """Create one branch commit and return its SHA."""
        self.git("switch", "main")
        self.git("switch", "-c", branch)
        self.write(path, text)
        self.git("add", path)
        self.git("commit", "-m", f"change {branch}")
        commit = self.git("rev-parse", "HEAD")
        if push:
            self.git("push", "-u", "origin", branch)
        self.git("switch", "main")
        return commit

    def branch_at_main(self, branch: str, *, push: bool = True) -> str:
        """Create a branch with no unique delta."""
        self.git("switch", "main")
        self.git("branch", branch)
        if push:
            self.git("push", "-u", "origin", branch)
        return self.git("rev-parse", branch)

    def squash_branch_to_main(self, branch: str, path: str) -> None:
        """Land the branch's final file tree through one different main commit."""
        self.git("switch", "main")
        self.git("checkout", branch, "--", path)
        self.git("commit", "-m", f"land {branch} as squash")
        self.git("push", "origin", "main")

    def cherry_pick_to_main(self, commit: str) -> None:
        """Land a patch with a different commit identity."""
        self.git("switch", "main")
        self.git("cherry-pick", "--no-commit", commit)
        self.git("commit", "-m", "land equivalent patch with different identity")
        self.git("push", "origin", "main")


class OrphanLifecycleTest(unittest.TestCase):
    """Exercise the finite lifecycle and cleanup admission contract."""

    def setUp(self) -> None:
        """Create an isolated Git fixture for each classification case."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = GitFixture(Path(self.temp.name))

    @staticmethod
    def trace_record(
        branch: str,
        *,
        active_owners: list[str] | None = None,
        successors: list[dict[str, str]] | None = None,
        requirement_state: str = "resolved",
        resolution: str | None = None,
        worktree_owner: str = "runtime",
    ) -> dict[str, object]:
        """Return one explicit branch relation record."""
        return {
            "selector": {"branch": branch},
            "active_owners": active_owners or [],
            "successors": successors or [],
            "requirement_state": requirement_state,
            "resolution": resolution,
            "worktree_owner": worktree_owner,
        }

    @staticmethod
    def trace(
        *records: dict[str, object],
        pull_requests: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        """Return normalized trace input without file I/O."""
        raw = {
            "schema": TOOL.TRACE_SCHEMA,
            "records": list(records),
            "pull_requests": pull_requests or [],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(raw, handle)
            path = Path(handle.name)
        try:
            return TOOL.load_trace(path)
        finally:
            path.unlink()

    def inventory(self, trace: dict[str, object]) -> dict[str, object]:
        """Build an inventory against the fixture's remote-tracking main."""
        return TOOL.build_inventory(
            self.fixture.repo,
            "refs/remotes/origin/main",
            trace,
        )

    @staticmethod
    def candidate(inventory: dict[str, object], candidate_id: str) -> dict[str, object]:
        """Return one inventory candidate by stable identity."""
        candidates = inventory["candidates"]
        assert isinstance(candidates, list)
        return next(
            candidate
            for candidate in candidates
            if candidate["candidate_id"] == candidate_id
        )

    def test_squash_equivalent_branch_is_merged_equivalent(self) -> None:
        """Tree-surface equivalence detects a squash even when patch IDs differ."""
        branch = "equivalent-squash"
        self.fixture.git("switch", "-c", branch)
        self.fixture.write("feature.txt", "first\n")
        self.fixture.git("add", "feature.txt")
        self.fixture.git("commit", "-m", "first part")
        self.fixture.write("feature.txt", "final\n")
        self.fixture.git("commit", "-am", "second part")
        self.fixture.git("push", "-u", "origin", branch)
        self.fixture.squash_branch_to_main(branch, "feature.txt")

        inventory = self.inventory(self.trace(self.trace_record(branch)))
        candidate = self.candidate(inventory, f"branch:local:{branch}")

        self.assertEqual(candidate["classification"], "merged_equivalent")
        self.assertEqual(candidate["semantic_diff"]["status"], "none")
        self.assertEqual(candidate["semantic_diff"]["basis"], "surface_equivalent")
        self.assertIn("missing_resolution_trace", candidate["cleanup_blockers"])

    def test_cherry_pick_equivalence_uses_patch_id(self) -> None:
        """Patch equivalence does not depend on commit SHA identity."""
        branch = "equivalent-patch"
        commit = self.fixture.branch_with_commit(
            branch, path="patch.txt", text="same patch\n"
        )
        self.fixture.cherry_pick_to_main(commit)

        inventory = self.inventory(self.trace(self.trace_record(branch)))
        candidate = self.candidate(inventory, f"branch:local:{branch}")

        self.assertEqual(candidate["semantic_diff"]["status"], "none")
        self.assertIn(
            candidate["semantic_diff"]["basis"],
            {"patch_equivalent", "surface_equivalent"},
        )

    def test_complete_successor_is_superseded_but_not_cleanup_safe(self) -> None:
        """A successor trace does not erase a branch's unique delta against main."""
        branch = "superseded"
        self.fixture.branch_with_commit(branch, path="superseded.txt", text="unique\n")
        record = self.trace_record(
            branch,
            successors=[{"id": "issue:#900", "coverage": "complete"}],
        )

        candidate = self.candidate(
            self.inventory(self.trace(record)), f"branch:local:{branch}"
        )

        self.assertEqual(candidate["classification"], "superseded")
        self.assertIn("unique_semantic_delta", candidate["cleanup_blockers"])

    def test_unique_published_delta_needs_extraction(self) -> None:
        """A unique remote-backed delta is extracted rather than discarded."""
        branch = "unique-delta"
        self.fixture.branch_with_commit(branch, path="unique.txt", text="unique\n")

        candidate = self.candidate(
            self.inventory(self.trace(self.trace_record(branch))),
            f"branch:local:{branch}",
        )

        self.assertEqual(candidate["classification"], "needs_extraction")
        self.assertEqual(candidate["semantic_diff"]["status"], "present")

    def test_dirty_worktree_is_protected_user_state(self) -> None:
        """Dirty and untracked worktree state is outside automatic cleanup authority."""
        branch = "dirty-worktree"
        self.fixture.branch_at_main(branch)
        worktree = Path(self.temp.name) / "dirty-wt"
        self.fixture.git("worktree", "add", str(worktree), branch)
        (worktree / "untracked.txt").write_text("user state\n", encoding="utf-8")

        inventory = self.inventory(self.trace(self.trace_record(branch)))
        candidate = self.candidate(inventory, f"worktree:{worktree}")

        self.assertEqual(candidate["classification"], "protected_user_state")
        self.assertIn("dirty_worktree", candidate["cleanup_blockers"])
        self.assertIn("untracked_worktree_state", candidate["cleanup_blockers"])

    def test_unpushed_local_branch_is_protected_user_state(self) -> None:
        """Local-only commits cannot be reclassified as disposable age-based state."""
        branch = "local-only"
        self.fixture.branch_with_commit(
            branch,
            path="local-only.txt",
            text="not published\n",
            push=False,
        )

        candidate = self.candidate(
            self.inventory(self.trace(self.trace_record(branch))),
            f"branch:local:{branch}",
        )

        self.assertEqual(candidate["classification"], "protected_user_state")
        self.assertGreater(candidate["user_state"]["unpushed_commits"], 0)
        self.assertIn("unpushed_local_commits", candidate["cleanup_blockers"])

    def test_ambiguous_owner_trace_needs_verification(self) -> None:
        """Overlapping ownership records fail closed instead of guessing."""
        branch = "ambiguous"
        self.fixture.branch_at_main(branch)
        record = self.trace_record(branch)

        candidate = self.candidate(
            self.inventory(self.trace(record, record)),
            f"branch:local:{branch}",
        )

        self.assertEqual(candidate["classification"], "needs_verification")
        self.assertIn(
            "ownership_successor_trace_ambiguous", candidate["cleanup_blockers"]
        )

    def test_open_pr_head_is_active(self) -> None:
        """Open PR state remains active even when no second Issue state machine exists."""
        branch = "open-pr"
        sha = self.fixture.branch_at_main(branch)
        pull_request = {
            "number": 42,
            "head_ref": branch,
            "head_sha": sha,
            "state": "open",
            "url": "https://example.invalid/pr/42",
        }

        candidate = self.candidate(
            self.inventory(self.trace(pull_requests=[pull_request])), "pr:42"
        )

        self.assertEqual(candidate["classification"], "active")
        self.assertIn("pr:42", candidate["active_owners"])

    def test_cleanup_admission_requires_safe_class_and_exact_digest(self) -> None:
        """Cleanup admission is explicit, snapshot-bound, and non-mutating."""
        branch = "safe"
        self.fixture.branch_at_main(branch)
        record = self.trace_record(
            branch,
            resolution="issue:#808-comment:resolved-on-main",
        )
        inventory = self.inventory(self.trace(record))
        candidate_id = f"branch:local:{branch}"
        candidate = self.candidate(inventory, candidate_id)
        self.assertEqual(candidate["classification"], "orphan_safe_to_remove")

        admission = TOOL.authorize_cleanup(
            inventory,
            fresh_inventory=self.inventory(self.trace(record)),
            expected_digest=inventory["inventory_digest"],
            selections=[candidate_id],
        )
        stale = TOOL.authorize_cleanup(
            inventory,
            fresh_inventory=self.inventory(self.trace(record)),
            expected_digest="sha256:stale",
            selections=[candidate_id],
        )

        self.assertEqual(admission["status"], "authorized")
        self.assertFalse(admission["mutation_performed"])
        self.assertEqual(stale["status"], "refused")
        self.assertIn(
            "selection_inventory_digest_mismatch",
            stale["decisions"][0]["blockers"],
        )

    def test_cleanup_admission_refuses_live_inventory_drift(self) -> None:
        """A valid old report cannot authorize cleanup after any observed drift."""
        branch = "safe-before-drift"
        self.fixture.branch_at_main(branch)
        record = self.trace_record(
            branch,
            resolution="issue:#808-comment:resolved-on-main",
        )
        trace = self.trace(record)
        inventory = self.inventory(trace)
        candidate_id = f"branch:local:{branch}"

        self.fixture.branch_at_main("unrelated-new-candidate")
        fresh_inventory = self.inventory(trace)
        admission = TOOL.authorize_cleanup(
            inventory,
            fresh_inventory=fresh_inventory,
            expected_digest=inventory["inventory_digest"],
            selections=[candidate_id],
        )

        self.assertEqual(admission["status"], "refused")
        self.assertIn(
            "live_inventory_digest_mismatch",
            admission["decisions"][0]["blockers"],
        )

    def test_inventory_has_no_age_authorization_fields(self) -> None:
        """The canonical result contains no time threshold or age evidence."""
        branch = "no-age"
        self.fixture.branch_at_main(branch)
        inventory = self.inventory(self.trace(self.trace_record(branch)))
        encoded = json.dumps(inventory, sort_keys=True)

        self.assertNotIn('"age"', encoded)
        self.assertNotIn("created_at", encoded)
        self.assertNotIn("updated_at", encoded)
        self.assertFalse(inventory["cleanup_contract"]["age_is_authorization_evidence"])


if __name__ == "__main__":
    unittest.main()
