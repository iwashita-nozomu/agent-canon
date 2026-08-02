"""Tests for fail-closed parent PR dependency graph selection."""

# @dependency-start
# contract test
# responsibility Verifies canonical profile/surface selection, trusted diff bases, and typed selector failures.
# upstream implementation ../../tools/ci/agent_canon_pr_graph_selector.py selects parent strict graph gating
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.json owns canonical validation profile IDs and graph requirements
# upstream design ../../documents/design/dependency-manifest-design.md owns canonical dependency surfaces
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTOR_PATH = PROJECT_ROOT / "tools" / "ci" / "agent_canon_pr_graph_selector.py"
SPEC = importlib.util.spec_from_file_location("agent_canon_pr_graph_selector", SELECTOR_PATH)
assert SPEC is not None and SPEC.loader is not None
selector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = selector
SPEC.loader.exec_module(selector)


def git(root: Path, *args: str, input_text: str | None = None) -> str:
    """Run one Git fixture command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        input=input_text,
    )
    return result.stdout.strip()


def commit_change(root: Path, relative: str) -> str:
    """Create a two-commit fixture and return the base commit."""
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "selector@example.invalid")
    git(root, "config", "user.name", "Selector Fixture")
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("before\n", encoding="utf-8")
    git(root, "add", relative)
    git(root, "commit", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    path.write_text("after\n", encoding="utf-8")
    git(root, "add", relative)
    git(root, "commit", "-m", "change")
    return base


class AgentCanonPrGraphSelectorTest(unittest.TestCase):
    """Exercise required, skipped, and typed failure states."""

    def test_pin_only_diff_is_skipped_with_reason_and_evidence(self) -> None:
        """A pin-only parent diff does not select strict parent graph completeness."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {"AGENT_CANON_PR_BASE_REF": base},
            )

        self.assertEqual(selection.status, "skipped")
        self.assertEqual(selection.reason, "parent_graph_completeness_not_selected")
        self.assertIn(f"base={base}", selection.evidence)
        self.assertIn("dependency_surface_owner=", selection.evidence)
        self.assertIn("changed_paths_sha256=", selection.evidence)

    def test_canonical_maintenance_profile_requires_graph(self) -> None:
        """Strict graph selection comes from the canonical profile inventory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {
                    "AGENT_CANON_PR_BASE_REF": base,
                    "AGENT_CANON_PR_VALIDATION_PROFILE": "maintenance",
                },
            )

        self.assertEqual(selection.status, "required")
        self.assertIn("canonical_profile_requires_graph", selection.reason)
        self.assertIn("graph_profiles=maintenance", selection.evidence)

    def test_canonical_non_graph_profile_keeps_pin_only_diff_skipped(self) -> None:
        """A known profile with a false canonical requirement does not escalate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {
                    "AGENT_CANON_PR_BASE_REF": base,
                    "AGENT_CANON_PR_VALIDATION_PROFILE": "agent-runtime",
                },
            )

        self.assertEqual(selection.status, "skipped")
        self.assertIn("selected_profiles=agent-runtime", selection.evidence)

    def test_unknown_profile_is_typed_failure(self) -> None:
        """Unknown local profile strings never degrade to a skipped graph gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")

            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.select(
                    root,
                    PROJECT_ROOT,
                    {
                        "AGENT_CANON_PR_BASE_REF": base,
                        "AGENT_CANON_PR_VALIDATION_PROFILE": "strict-dependency",
                    },
                )

        self.assertEqual(raised.exception.reason, "unknown_validation_profile")

    def test_dependency_surfaces_come_from_canonical_owner_manifest(self) -> None:
        """All graph adapters named by review are manifest-derived surfaces."""
        surfaces = selector.dependency_surface_paths(PROJECT_ROOT)

        self.assertTrue(
            {
                "tools/agent_tools/scan_dependency_headers.sh",
                "tools/agent_tools/check_dependency_headers.py",
                "tools/agent_tools/render_dependency_manifest_graph.py",
                "tools/agent_tools/graph_client.py",
            }.issubset(surfaces)
        )

    def test_canonical_dependency_surface_change_requires_graph(self) -> None:
        """A manifest-owned dependency surface selects strict graph completeness."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "tools/agent_tools/graph_client.py")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {"AGENT_CANON_PR_BASE_REF": base},
            )

        self.assertEqual(selection.status, "required")
        self.assertIn("canonical_dependency_surface_touched", selection.reason)
        self.assertIn("tools/agent_tools/graph_client.py", selection.evidence)

    def test_graph_storage_dispatch_and_bootstrap_surfaces_require_graph(self) -> None:
        """Every reviewed graph storage/dispatch/bootstrap surface selects strict graph."""
        reviewed_surfaces = (
            "rust/agent-canon/src/structured_analysis.rs",
            "rust/agent-canon/src/main.rs",
            "tools/bin/agent-canon",
        )
        for relative in reviewed_surfaces:
            with self.subTest(path=relative):
                with tempfile.TemporaryDirectory() as tmp_dir:
                    root = Path(tmp_dir)
                    base = commit_change(root, relative)

                    selection = selector.select(
                        root,
                        PROJECT_ROOT,
                        {"AGENT_CANON_PR_BASE_REF": base},
                    )

                self.assertEqual(selection.status, "required")
                self.assertIn(
                    "canonical_dependency_surface_touched",
                    selection.reason,
                )
                self.assertIn(relative, selection.evidence)

    def test_dependency_manifest_change_requires_graph(self) -> None:
        """A changed dependency header selects strict graph completeness."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "README.md")
            readme = root / "README.md"
            readme.write_text(
                "# @dependency-start\n# responsibility Fixture manifest.\n# @dependency-end\n",
                encoding="utf-8",
            )
            git(root, "add", "README.md")
            git(root, "commit", "-m", "manifest")

            selection = selector.select(
                root,
                PROJECT_ROOT,
                {"AGENT_CANON_PR_BASE_REF": base},
            )

        self.assertEqual(selection.status, "required")
        self.assertIn("dependency_manifest_touched", selection.reason)

    def test_base_equal_to_head_is_typed_failure(self) -> None:
        """An equal base cannot masquerade as an empty PR diff."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            commit_change(root, "vendor/agent-canon")
            head = git(root, "rev-parse", "HEAD")

            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.load_diff(root, {"AGENT_CANON_PR_BASE_REF": head})

        self.assertEqual(raised.exception.reason, "pr_base_equals_head")

    def test_local_base_override_is_required(self) -> None:
        """Local callers cannot fall back to origin/main or HEAD parents."""
        with self.assertRaises(selector.SelectorFailure) as raised:
            selector.trusted_base_ref({})

        self.assertEqual(raised.exception.reason, "local_base_override_required")

    def test_history_unreachable_base_is_typed_failure(self) -> None:
        """A resolvable commit without common history cannot define the PR diff."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            commit_change(root, "vendor/agent-canon")
            empty_tree = git(root, "mktree", input_text="")
            unrelated = git(root, "commit-tree", empty_tree, input_text="unrelated\n")

            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.load_diff(root, {"AGENT_CANON_PR_BASE_REF": unrelated})

        self.assertEqual(raised.exception.reason, "pr_base_unreachable_from_head")

    def test_diff_command_failure_is_typed_failure(self) -> None:
        """A failed Git diff cannot become an empty changed-path set."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")
            real_run_git = selector.run_git

            def fail_diff(
                command_root: Path,
                args: list[str] | tuple[str, ...],
            ) -> subprocess.CompletedProcess[str]:
                if args and args[0] == "diff":
                    return subprocess.CompletedProcess(
                        ["git", *args],
                        128,
                        stdout="",
                        stderr="fixture diff failure",
                    )
                return real_run_git(command_root, args)

            with patch.object(selector, "run_git", side_effect=fail_diff):
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.load_diff(root, {"AGENT_CANON_PR_BASE_REF": base})

        self.assertEqual(raised.exception.reason, "pr_changed_paths_diff_failed")

    def test_ci_uses_pull_request_base_sha_from_event(self) -> None:
        """CI ignores branch-name heuristics and consumes the trusted PR event base."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")
            event = root / "event.json"
            event.write_text(
                json.dumps({"pull_request": {"base": {"sha": base}}}),
                encoding="utf-8",
            )

            diff = selector.load_diff(
                root,
                {
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_NAME": "pull_request",
                    "GITHUB_EVENT_PATH": str(event),
                },
            )

        self.assertEqual(diff.base_sha, base)
        self.assertEqual(diff.base_source, "github_event_pull_request_base_sha")


if __name__ == "__main__":
    unittest.main()
