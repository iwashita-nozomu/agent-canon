"""Tests for fail-closed parent PR dependency graph selection."""

# @dependency-start
# contract test
# responsibility Verifies canonical selection, trusted diff bases, changed-responsibility reachability, and typed graph failures.
# upstream implementation ../../tools/ci/agent_canon_pr_graph_selector.py selects parent strict graph gating
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh prepares and passes the trusted GitHub base
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.json owns canonical validation profile IDs and graph requirements
# upstream design ../../documents/design/dependency-manifest-design.md owns canonical dependency surfaces
# @dependency-end

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTOR_PATH = PROJECT_ROOT / "tools" / "ci" / "agent_canon_pr_graph_selector.py"
CHECKER_PATH = PROJECT_ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
SPEC = importlib.util.spec_from_file_location(
    "agent_canon_pr_graph_selector", SELECTOR_PATH
)
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


def shallow_pr_checkout(root: Path) -> tuple[Path, Path, str]:
    """Create a depth-one PR checkout, event payload, and missing base SHA."""
    source = root / "source"
    source.mkdir()
    base = commit_change(source, "vendor/agent-canon")
    remote = root / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )
    checkout = root / "checkout"
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            "main",
            remote.as_uri(),
            str(checkout),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    event = root / "event.json"
    event.write_text(
        json.dumps({"pull_request": {"base": {"sha": base}}}),
        encoding="utf-8",
    )
    return checkout, event, base


def graph_change_fixture(root: Path, extra_base_files: dict[str, str]) -> str:
    """Create one changed path plus unchanged base-owned graph sources."""
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "selector@example.invalid")
    git(root, "config", "user.name", "Selector Fixture")
    (root / "changed.py").write_text("before\n", encoding="utf-8")
    for relative, content in extra_base_files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    (root / "changed.py").write_text("after\n", encoding="utf-8")
    git(root, "add", "changed.py")
    git(root, "commit", "-m", "change")
    return base


def write_graph_result(
    root: Path,
    paths: tuple[str, ...],
    edges: tuple[tuple[str, str], ...],
    diagnostics: tuple[tuple[str, str, str], ...],
) -> Path:
    """Write one result bound to canonical persisted integration metadata."""
    graph_dir = root / ".agent-canon" / "knowledge-graph"
    graph_dir.mkdir(parents=True)
    database = graph_dir / "graph.sqlite"
    snapshot_head = git(root, "rev-parse", "HEAD")
    input_fingerprint = "1" * 64
    graph_fingerprint = "2" * 64
    integration_record = {
        "schema": "agent-canon.graph.integration.v1",
        "root": str(root.resolve()),
        "db_path": str(database.resolve()),
        "schema_version": "fixture",
        "profile": "default",
        "source_snapshot_profile": "parent",
        "snapshot_head": snapshot_head,
        "input_fingerprint": input_fingerprint,
        "graph_fingerprint": graph_fingerprint,
        "contract_fingerprint": "fixture",
        "producer_artifacts": [],
        "runtime_evidence": None,
        "verified": True,
        "verification_code": "source-facts-readback-v1",
    }
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)")
        connection.execute("CREATE TABLE nodes(id TEXT, layer TEXT, payload_json TEXT)")
        connection.execute(
            "CREATE TABLE edges(layer TEXT, from_node_id TEXT, to_node_id TEXT)"
        )
        connection.execute(
            "CREATE TABLE diagnostics(layer TEXT, rule TEXT, message TEXT, target_node_id TEXT)"
        )
        for path in paths:
            connection.execute(
                "INSERT INTO nodes VALUES(?, 'source', ?)",
                (f"node:source:{path}", json.dumps({"path": path})),
            )
        for source, target in edges:
            connection.execute(
                "INSERT INTO edges VALUES('source', ?, ?)",
                (f"node:source:{source}", f"node:source:{target}"),
            )
        for code, message, source in diagnostics:
            target_node = f"node:source:{source}" if source else ""
            connection.execute(
                "INSERT INTO diagnostics VALUES('source', ?, ?, ?)",
                (code, message, target_node),
            )
        for key, value in (
            ("integration_record", json.dumps(integration_record)),
            ("snapshot_head", snapshot_head),
            ("input_fingerprint", input_fingerprint),
            ("graph_fingerprint", graph_fingerprint),
        ):
            connection.execute("INSERT INTO metadata VALUES(?, ?)", (key, value))
    result = graph_dir / "graph-build.json"
    result.write_text(
        json.dumps(
            {
                "schema": "agent-canon.graph.build.v1",
                "command": "build",
                "status": "incomplete",
                "graph_status": "incomplete",
                "exit_code": 1,
                "root": str(root.resolve()),
                "profile": "default",
                "db_path": str(database.resolve()),
                "input_fingerprint": input_fingerprint,
                "graph_fingerprint": graph_fingerprint,
                "integration_record": integration_record,
                "publication": "published",
                "durability": "durable",
            }
        ),
        encoding="utf-8",
    )
    return result


class AgentCanonPrGraphSelectorTest(unittest.TestCase):
    """Exercise required, skipped, and typed failure states."""

    def setUp(self) -> None:
        """Keep unit fixtures focused on head classification semantics."""
        self.base_graph_patch = patch.object(
            selector,
            "build_trusted_base_graph",
            return_value=selector.TrustedBaseGraph(
                "0" * 40,
                "1" * 64,
                "2" * 64,
                "published",
                "durable",
                True,
                "fresh",
                (),
            ),
        )
        self.base_graph_patch.start()
        self.addCleanup(self.base_graph_patch.stop)

    def test_pr_entrypoint_prepares_and_passes_trusted_base(self) -> None:
        """The parent gate wires shallow preparation to the exact selector argument."""
        entrypoint = CHECKER_PATH.read_text(encoding="utf-8")

        self.assertIn("--prepare-ci-base", entrypoint)
        self.assertIn(
            'selector_args+=(--trusted-base-sha "${trusted_base_sha}")',
            entrypoint,
        )
        self.assertIn(
            'graph_acceptance_args+=(--trusted-base-sha "${PR_GATE_DEPENDENCY_GRAPH_BASE_SHA}")',
            entrypoint,
        )
        self.assertIn(
            'if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then\n      graph_acceptance_args+=',
            entrypoint,
        )

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
                "tools/ci/check_agent_canon_pr.sh",
                "tools/ci/run_all_checks.sh",
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

    def test_unrelated_base_unresolved_is_reported_without_blocking(self) -> None:
        """An unchanged non-reachable declaration remains evidence, not a PR blocker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"legacy.py": "legacy\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "legacy.py"),
                (),
                (("target-unresolved", "legacy.py:4:missing.md", "legacy.py"),),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {"AGENT_CANON_PR_BASE_REF": base},
            )
            head = git(root, "rev-parse", "HEAD")

        self.assertEqual(acceptance.status, "pass")
        self.assertEqual(
            acceptance.reason,
            "unrelated_baseline_incompleteness_reported",
        )
        self.assertEqual(acceptance.report["blocking_diagnostics"], [])
        graph_identity = acceptance.report["graph_identity"]
        self.assertEqual(graph_identity["snapshot_head"], head)
        self.assertEqual(graph_identity["publication"], "published")
        self.assertEqual(
            graph_identity["db_path"],
            str(root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"),
        )
        baseline = acceptance.report["baseline_diagnostics"]
        self.assertEqual(len(baseline), 1)
        self.assertEqual(baseline[0]["source_path"], "legacy.py")

    def test_concurrent_database_replacement_is_typed_failure(self) -> None:
        """Replacing the canonical DB after open cannot reach classification."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"legacy.py": "legacy\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "legacy.py"),
                (),
                (("target-unresolved", "legacy.py:4:missing.md", "legacy.py"),),
            )
            database = root / ".agent-canon" / "knowledge-graph" / "graph.sqlite"
            real_identity = selector.regular_file_identity
            database_reads = 0

            def replace_after_open(
                path: Path,
                unavailable_reason: str,
                invalid_reason: str,
            ) -> object:
                nonlocal database_reads
                if path == database:
                    database_reads += 1
                    if database_reads == 2:
                        replacement = database.with_name("replacement.sqlite")
                        replacement.write_bytes(database.read_bytes())
                        os.replace(replacement, database)
                return real_identity(path, unavailable_reason, invalid_reason)

            with patch.object(
                selector,
                "regular_file_identity",
                side_effect=replace_after_open,
            ):
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.evaluate_built_graph(
                        root,
                        graph_result,
                        {"AGENT_CANON_PR_BASE_REF": base},
                    )

        self.assertEqual(raised.exception.reason, "graph_identity_replaced")
        self.assertIn("artifact=graph_database", raised.exception.evidence)

    def test_reachable_unresolved_blocks_changed_responsibility(self) -> None:
        """A diagnostic reached through a dependency edge remains a blocker."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"related.py": "related\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "related.py"),
                (("changed.py", "related.py"),),
                (("target-unresolved", "related.py:4:missing.md", "related.py"),),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {"AGENT_CANON_PR_BASE_REF": base},
            )

        self.assertEqual(acceptance.status, "fail")
        blocking = acceptance.report["blocking_diagnostics"]
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0]["classification"], "changed_responsibility")

    def test_reachable_base_identity_is_evidence_not_a_new_blocker(self) -> None:
        """Reachability alone does not block a diagnostic already in trusted base."""
        base_diagnostic = {
            "code": "target-unresolved",
            "message": "related.py:4:missing.md",
            "source_path": "related.py",
            "target_path": "missing.md",
            "declaration": "missing.md",
            "severity": "blocker",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"related.py": "related\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "related.py"),
                (("changed.py", "related.py"),),
                (("target-unresolved", "related.py:19:missing.md", "related.py"),),
            )
            with patch.object(
                selector,
                "build_trusted_base_graph",
                return_value=selector.TrustedBaseGraph(
                    base,
                    "1" * 64,
                    "2" * 64,
                    "published",
                    "durable",
                    True,
                    "incomplete",
                    (base_diagnostic,),
                ),
            ):
                acceptance = selector.evaluate_built_graph(
                    root,
                    graph_result,
                    {"AGENT_CANON_PR_BASE_REF": base},
                )

        self.assertEqual(acceptance.status, "pass")
        self.assertEqual(acceptance.report["blocking_diagnostics"], [])
        self.assertEqual(len(acceptance.report["baseline_diagnostics"]), 1)
        self.assertEqual(
            acceptance.report["baseline_diagnostics"][0]["declaration"],
            "missing.md",
        )

    def test_same_count_replacement_is_a_new_blocker(self) -> None:
        """Replacing one diagnostic identity cannot be hidden by equal counts."""
        base_diagnostic = {
            "code": "target-unresolved",
            "message": "changed.py:4:old.md",
            "source_path": "changed.py",
            "target_path": "old.md",
            "declaration": "old.md",
            "severity": "blocker",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {})
            graph_result = write_graph_result(
                root,
                ("changed.py",),
                (),
                (("target-unresolved", "changed.py:40:new.md", "changed.py"),),
            )
            with patch.object(
                selector,
                "build_trusted_base_graph",
                return_value=selector.TrustedBaseGraph(
                    base,
                    "1" * 64,
                    "2" * 64,
                    "published",
                    "durable",
                    True,
                    "incomplete",
                    (base_diagnostic,),
                ),
            ):
                acceptance = selector.evaluate_built_graph(
                    root,
                    graph_result,
                    {"AGENT_CANON_PR_BASE_REF": base},
                )

        self.assertEqual(acceptance.status, "fail")
        self.assertEqual(len(acceptance.report["blocking_diagnostics"]), 1)
        self.assertFalse(acceptance.report["blocking_diagnostics"][0]["base_match"])

    def test_changed_manifest_grammar_blocks_without_target_node(self) -> None:
        """Invalid grammar in a changed declaration is always in the gate closure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {})
            graph_result = write_graph_result(
                root,
                ("changed.py",),
                (),
                (("manifest-grammar", "changed.py:3:upstream bad", ""),),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {"AGENT_CANON_PR_BASE_REF": base},
            )

        self.assertEqual(acceptance.status, "fail")
        blocking = acceptance.report["blocking_diagnostics"]
        self.assertEqual(blocking[0]["code"], "manifest-grammar")
        self.assertEqual(blocking[0]["source_path"], "changed.py")

    def test_changed_target_blocks_an_unchanged_unresolved_declaration(self) -> None:
        """Deleting a declared target keeps its unchanged source in changed scope."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            git(root, "init", "-b", "main")
            git(root, "config", "user.email", "selector@example.invalid")
            git(root, "config", "user.name", "Selector Fixture")
            (root / "legacy.py").write_text("legacy\n", encoding="utf-8")
            (root / "deleted.md").write_text("target\n", encoding="utf-8")
            git(root, "add", ".")
            git(root, "commit", "-m", "base")
            base = git(root, "rev-parse", "HEAD")
            (root / "deleted.md").unlink()
            git(root, "add", "deleted.md")
            git(root, "commit", "-m", "delete target")
            graph_result = write_graph_result(
                root,
                ("legacy.py",),
                (),
                (("target-unresolved", "legacy.py:4:deleted.md", "legacy.py"),),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {"AGENT_CANON_PR_BASE_REF": base},
            )

        self.assertEqual(acceptance.status, "fail")
        blocking = acceptance.report["blocking_diagnostics"]
        self.assertEqual(blocking[0]["target_path"], "deleted.md")
        self.assertEqual(blocking[0]["classification"], "changed_responsibility")

    def test_explicit_parent_migration_keeps_full_graph_completeness(self) -> None:
        """A declared migration owns baseline diagnostics across the whole graph."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = graph_change_fixture(root, {"legacy.py": "legacy\n"})
            graph_result = write_graph_result(
                root,
                ("changed.py", "legacy.py"),
                (),
                (("target-unresolved", "legacy.py:4:missing.md", "legacy.py"),),
            )

            acceptance = selector.evaluate_built_graph(
                root,
                graph_result,
                {
                    "AGENT_CANON_PR_BASE_REF": base,
                    "AGENT_CANON_PR_PARENT_GRAPH_MIGRATION": "yes",
                },
            )

        self.assertEqual(acceptance.status, "fail")
        self.assertTrue(acceptance.report["full_scope"])

    def test_pr_entrypoint_records_scoped_graph_receipt(self) -> None:
        """The parent entrypoint and receipt consumer preserve scoped acceptance."""
        entrypoint = CHECKER_PATH.read_text(encoding="utf-8")
        quick_ci = (PROJECT_ROOT / "tools" / "ci" / "run_all_checks.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("--evaluate-built-graph", entrypoint)
        self.assertIn("PR_GATE_DEPENDENCY_GRAPH_STATUS=scoped", entrypoint)
        self.assertIn('!= "scoped"', quick_ci)
        self.assertIn("validated_changed_responsibility_graph_receipt", quick_ci)

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
                extra_environment: dict[str, str] | None = None,
            ) -> subprocess.CompletedProcess[str]:
                if args and args[0] == "diff":
                    return subprocess.CompletedProcess(
                        ["git", *args],
                        128,
                        stdout="",
                        stderr="fixture diff failure",
                    )
                return real_run_git(command_root, args, extra_environment)

            with patch.object(selector, "run_git", side_effect=fail_diff):
                with self.assertRaises(selector.SelectorFailure) as raised:
                    selector.load_diff(root, {"AGENT_CANON_PR_BASE_REF": base})

        self.assertEqual(raised.exception.reason, "pr_changed_paths_diff_failed")

    def test_ci_auth_required_fetch_succeeds_without_persisting_credential(
        self,
    ) -> None:
        """CI authenticates a needed fetch and binds selection to the event base."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            checkout, event, base = shallow_pr_checkout(root)
            environment = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
                "AGENT_CANON_PR_READ_TOKEN": "fixture-read-token",
            }
            unresolved = subprocess.run(
                ["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
                cwd=checkout,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unresolved.returncode, 0)

            real_run_git = selector.run_git
            fetch_environments: list[dict[str, str]] = []

            def inspect_fetch(
                command_root: Path,
                args: list[str] | tuple[str, ...],
                extra_environment: dict[str, str] | None = None,
            ) -> subprocess.CompletedProcess[str]:
                if args and args[0] == "fetch":
                    self.assertEqual(tuple(args[-2:]), ("origin", base))
                    self.assertIsNotNone(extra_environment)
                    fetch_environment = dict(extra_environment or {})
                    self.assertEqual(fetch_environment["GIT_TERMINAL_PROMPT"], "0")
                    self.assertEqual(
                        fetch_environment["GIT_CONFIG_KEY_0"],
                        "http.https://github.com/.extraheader",
                    )
                    self.assertTrue(
                        fetch_environment["GIT_CONFIG_VALUE_0"].startswith(
                            "AUTHORIZATION: basic "
                        )
                    )
                    fetch_environments.append(fetch_environment)
                return real_run_git(command_root, args, extra_environment)

            with patch.object(selector, "run_git", side_effect=inspect_fetch):
                prepared = selector.prepare_ci_base(checkout, environment)

            diff = selector.load_diff(
                checkout,
                environment,
                prepared.base_sha,
            )
            persisted = subprocess.run(
                [
                    "git",
                    "config",
                    "--local",
                    "--get-all",
                    "http.https://github.com/.extraheader",
                ],
                cwd=checkout,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(diff.base_sha, base)
        self.assertTrue(prepared.fetched)
        self.assertEqual(len(fetch_environments), 1)
        self.assertEqual(prepared.base_source, "github_event_pull_request_base_sha")
        self.assertEqual(diff.base_source, "github_event_pull_request_base_sha")
        self.assertNotEqual(persisted.returncode, 0)
        self.assertEqual(persisted.stdout, "")

    def test_ci_skips_fetch_when_base_object_and_history_are_available(self) -> None:
        """A complete checkout needs neither a fetch nor a read credential."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")
            event = root / "event.json"
            event.write_text(
                json.dumps({"pull_request": {"base": {"sha": base}}}),
                encoding="utf-8",
            )
            environment = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
            }
            real_run_git = selector.run_git

            def reject_fetch(
                command_root: Path,
                args: list[str] | tuple[str, ...],
                extra_environment: dict[str, str] | None = None,
            ) -> subprocess.CompletedProcess[str]:
                if args and args[0] == "fetch":
                    self.fail("history-ready CI preparation must not fetch")
                return real_run_git(command_root, args, extra_environment)

            with patch.object(selector, "run_git", side_effect=reject_fetch):
                prepared = selector.prepare_ci_base(root, environment)

        self.assertEqual(prepared.base_sha, base)
        self.assertFalse(prepared.fetched)

    def test_ci_missing_fetch_credential_is_typed_failure(self) -> None:
        """A fetch-required GitHub checkout fails before unauthenticated fetch."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            checkout, event, _base = shallow_pr_checkout(root)
            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.prepare_ci_base(
                    checkout,
                    {
                        "GITHUB_ACTIONS": "true",
                        "GITHUB_EVENT_NAME": "pull_request",
                        "GITHUB_EVENT_PATH": str(event),
                    },
                )

        self.assertEqual(
            raised.exception.reason,
            "pr_base_read_credential_missing",
        )

    def test_ci_rejects_missing_or_mismatched_trusted_base_argument(self) -> None:
        """Normal CI selection cannot invent or replace the prepared event base."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base = commit_change(root, "vendor/agent-canon")
            event = root / "event.json"
            event.write_text(
                json.dumps({"pull_request": {"base": {"sha": base}}}),
                encoding="utf-8",
            )
            environment = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event),
            }

            with self.assertRaises(selector.SelectorFailure) as missing:
                selector.load_diff(root, environment)
            with self.assertRaises(selector.SelectorFailure) as mismatch:
                selector.load_diff(root, environment, "0" * 40)

        self.assertEqual(missing.exception.reason, "trusted_pr_base_argument_invalid")
        self.assertEqual(mismatch.exception.reason, "trusted_pr_base_argument_mismatch")

    def test_ci_rejects_base_override_before_fetch(self) -> None:
        """CI accepts only its event base and never an environment override."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _checkout, event, base = shallow_pr_checkout(root)
            with self.assertRaises(selector.SelectorFailure) as raised:
                selector.prepare_ci_base(
                    _checkout,
                    {
                        "GITHUB_ACTIONS": "true",
                        "GITHUB_EVENT_NAME": "pull_request",
                        "GITHUB_EVENT_PATH": str(event),
                        "AGENT_CANON_PR_BASE_REF": base,
                    },
                )

        self.assertEqual(raised.exception.reason, "ci_base_override_forbidden")


if __name__ == "__main__":
    unittest.main()
