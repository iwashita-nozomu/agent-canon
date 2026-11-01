"""Tests for source-derived dependency query and context projections."""

# @dependency-start
# contract test
# responsibility Verifies dependency consumers do not require persisted graph runtime state.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/source_dependency_graph.rs derives source projections
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/graph_client.rs routes native dependency reads to source
# downstream implementation ../../tools/validation/ci/checks/check_agent_canon_pr.sh uses source-owned dependency review
# @dependency-end

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = Path(
    os.environ.get("AGENT_CANON_CLI", str(PROJECT_ROOT / "tools/bin/agent-canon"))
)
SOURCE_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "fixtures/source_dependency_projection/python_golden.json"
)
SOURCE_GOLDEN_SHA256 = (
    "fabfc4a93967e32c4c00c7c732340dc2e437683b45a0985993706ee2da21f119"
)


def write(path: Path, content: str) -> None:
    """Write one dedented fixture file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def run_graph_client(
    root: Path, command: str, *options: str
) -> subprocess.CompletedProcess[str]:
    """Invoke the native typed GraphClient route selected by the test runner."""
    return subprocess.run(
        [
            str(AGENT_CANON_CLI),
            "graph-client",
            command,
            "--root",
            str(root),
            "--format",
            "json",
            *options,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )


class GraphClientSourceProjectionTest(unittest.TestCase):
    """Verify dependency reads are pure functions of tracked source bytes."""

    def run_client(
        self, root: Path, command: str, *options: str
    ) -> subprocess.CompletedProcess[str]:
        return run_graph_client(root, command, *options)

    def error_text(self, result: subprocess.CompletedProcess[str]) -> str:
        text = result.stderr.strip()
        prefix = "GRAPH_CLIENT=fail reason="
        return text.removeprefix(prefix) if text.startswith(prefix) else text

    def fixture(self, root: Path) -> None:
        """Create one reciprocal design/implementation dependency fixture."""
        write(
            root / "documents" / "design" / "parent.md",
            """
            <!--
            @dependency-start
            contract design
            responsibility Defines the parent contract.
            downstream design feature.md specializes the parent
            @dependency-end
            -->
            # Parent
            """,
        )
        write(
            root / "documents" / "design" / "feature.md",
            """
            <!--
            @dependency-start
            contract design
            responsibility Defines the feature contract.
            upstream design parent.md inherits the parent contract
            upstream reference ../notes/source-evidence.md records non-authoritative context
            downstream implementation ../../tools/feature.py implements the feature
            @dependency-end
            -->
            # Feature
            """,
        )
        write(
            root / "documents" / "notes" / "source-evidence.md",
            "# Source evidence\n\nThis note is supporting context, not a design owner.\n",
        )
        write(
            root / "tools" / "feature.py",
            """
            # @dependency-start
            # contract tool
            # responsibility Implements the feature contract.
            # upstream design ../documents/design/feature.md feature design
            # @dependency-end
            def feature() -> None:
                pass
            """,
        )

    def test_frozen_old_source_query_context_and_export_corpus(self) -> None:
        """The ordinary native route matches frozen old source API projections."""
        raw = SOURCE_GOLDEN.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_GOLDEN_SHA256)
        corpus = json.loads(raw)
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for relative, encoded in corpus["input_files_base64"].items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(base64.b64decode(encoded))

            for case in corpus["cases"]:
                command = case["operation"]
                options = ["--path", case["path"]] if case.get("path") else []
                if command == "query":
                    options.extend(
                        [
                            "--relation",
                            "dependency",
                            "--direction",
                            "both",
                            "--depth",
                            "0",
                            "--all",
                        ]
                    )
                result = run_graph_client(root, command, *options)
                if case["accepted"]:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), case["output"])
                else:
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    detail = result.stderr.strip()
                    prefix = "GRAPH_CLIENT=fail reason="
                    if detail.startswith(prefix):
                        detail = detail.removeprefix(prefix)
                    self.assertEqual(detail, case["error"])

            edges = root / "projection" / "edges.tsv"
            manifests = root / "projection" / "manifests.txt"
            exported = subprocess.run(
                [
                    str(AGENT_CANON_CLI),
                    "source-dependency-graph",
                    "--root",
                    str(root),
                    "--edges-out",
                    str(edges),
                    "--manifests-out",
                    str(manifests),
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )
            self.assertEqual(exported.returncode, 0, exported.stderr)
            expected_export = corpus["export"]
            self.assertTrue(expected_export["accepted"])
            self.assertEqual(
                edges.read_bytes(), base64.b64decode(expected_export["edges_base64"])
            )
            self.assertEqual(
                manifests.read_bytes(),
                base64.b64decode(expected_export["manifests_base64"]),
            )

    def test_dependency_query_works_without_graph_executable_or_state(self) -> None:
        """Dependency query reads source even when no executable or graph DB exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.fixture(root)
            result = self.run_client(
                root,
                "query",
                "--all",
                "--relation",
                "dependency",
                "--direction",
                "both",
                "--depth",
                "0",
                "--executable",
                str(root / "missing-agent-canon"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            response = json.loads(result.stdout)
            self.assertEqual(response["status"], "fresh")
            self.assertEqual(response["payload"]["projection"], "tracked-source")
            self.assertGreaterEqual(len(response["dependency_facts"]), 4)
            self.assertFalse((root / ".agent-canon").exists())

    def test_context_is_source_bound_and_contains_declared_closure(self) -> None:
        """Context identity and closure are derived from current source bytes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.fixture(root)
            result = self.run_client(
                root,
                "context",
                "--path",
                "documents/design/feature.md",
                "--executable",
                str(root / "missing-agent-canon"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            response = json.loads(result.stdout)
            identity = response["source_identity"]
            self.assertIsNotNone(identity)
            self.assertEqual(identity["source_path"], "documents/design/feature.md")
            self.assertEqual(len(identity["content_sha256"]), 64)
            self.assertEqual(
                response["payload"]["parent_paths"],
                ["documents/design/parent.md"],
            )
            self.assertEqual(
                response["payload"]["evidence_paths"],
                [
                    "documents/design/feature.md",
                    "documents/design/parent.md",
                    "documents/notes/source-evidence.md",
                    "tools/feature.py",
                ],
            )
            self.assertFalse((root / ".agent-canon").exists())

    def test_explicit_persisted_graph_operations_still_use_the_selected_provider(
        self,
    ) -> None:
        """Status and non-source queries keep their explicit persisted provider route."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.fixture(root)
            missing = str(root / "missing-agent-canon")
            for command, options in (
                ("status", ()),
                (
                    "query",
                    (
                        "--all",
                        "--relation",
                        "owner",
                        "--direction",
                        "both",
                        "--depth",
                        "0",
                    ),
                ),
                (
                    "query",
                    (
                        "--path",
                        "documents/design/feature.md",
                        "--relation",
                        "dependency",
                        "--direction",
                        "outgoing",
                        "--depth",
                        "1",
                    ),
                ),
            ):
                result = self.run_client(
                    root, command, *options, "--executable", missing
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("process launch failed", self.error_text(result))

    def test_dependency_target_escape_is_rejected_without_runtime_fallback(
        self,
    ) -> None:
        """Invalid source paths fail closed instead of falling back to graph state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "tools" / "escape.py",
                """
                # @dependency-start
                # contract tool
                # responsibility Exercises root containment.
                # upstream design ../../outside.md escapes the repository
                # @dependency-end
                """,
            )
            result = self.run_client(
                root,
                "query",
                "--all",
                "--relation",
                "dependency",
                "--direction",
                "both",
                "--depth",
                "0",
                "--executable",
                str(root / "missing-agent-canon"),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "source dependency projection failed: path escapes repository root",
                self.error_text(result),
            )

    def test_unknown_dependency_relation_kind_stays_closed(self) -> None:
        """The evidence relation adds only `reference`, not arbitrary aliases."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "tools" / "invalid.py",
                """
                # @dependency-start
                # contract tool
                # responsibility Exercises the closed relation kind set.
                # upstream citation ../documents/evidence.md unsupported alias
                # @dependency-end
                """,
            )
            write(root / "documents" / "evidence.md", "# Evidence\n")

            result = self.run_client(
                root,
                "query",
                "--all",
                "--relation",
                "dependency",
                "--direction",
                "both",
                "--depth",
                "0",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid dependency kind: citation", self.error_text(result))

    def test_generated_skill_view_resolves_to_catalog_owner_without_view(self) -> None:
        """Ignored generated skill paths use the catalog owner in a clean checkout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "agents" / "skills" / "catalog.yaml",
                """
                skill_families:
                  - id: example
                    canonical_doc: agents/skills/example.md
                    shim: .codex/personal/skills/example/SKILL.md
                """,
            )
            write(
                root / "agents" / "skills" / "example.md",
                """
                # @dependency-start
                # contract skill
                # responsibility Owns the example skill.
                # @dependency-end
                # Example skill.
                """,
            )
            write(
                root / "tools" / "consumer.py",
                """
                # @dependency-start
                # contract tool
                # responsibility References the generated skill view.
                # downstream implementation ../.codex/personal/skills/example/SKILL.md generated view
                # @dependency-end
                """,
            )
            projection_result = self.run_client(root, "query", "--all")
            self.assertEqual(projection_result.returncode, 0, projection_result.stderr)
            projection = json.loads(projection_result.stdout)
            self.assertEqual(
                {
                    (fact["source"], fact["target"])
                    for fact in projection["dependency_facts"]
                },
                {("tools/consumer.py", "agents/skills/example.md")},
            )
            self.assertFalse(
                (
                    root / ".codex" / "personal" / "skills" / "example" / "SKILL.md"
                ).exists()
            )
            context_result = self.run_client(
                root, "context", "--path", ".codex/personal/skills/example/SKILL.md"
            )
            self.assertEqual(context_result.returncode, 0, context_result.stderr)
            context = json.loads(context_result.stdout)
            identity = context["source_identity"]
            self.assertIsNotNone(identity)
            self.assertEqual(identity["source_path"], "agents/skills/example.md")

    def test_unknown_generated_skill_view_is_rejected(self) -> None:
        """A stale generated skill path cannot become an implicit graph node."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "tools" / "consumer.py",
                """
                # @dependency-start
                # contract tool
                # responsibility References a stale generated skill view.
                # downstream implementation ../.codex/personal/skills/removed/SKILL.md stale view
                # @dependency-end
                """,
            )
            result = self.run_client(root, "query", "--all")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "source dependency projection failed: unknown generated skill view",
                self.error_text(result),
            )

    def test_generated_skill_glob_resolves_all_catalog_owners_without_views(
        self,
    ) -> None:
        """Registry-backed generated skill globs expand without reading ignored shims."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "agents" / "skills" / "catalog.yaml",
                """
                skill_families:
                  - id: alpha
                    canonical_doc: agents/skills/alpha.md
                    shim: .codex/personal/skills/alpha/SKILL.md
                  - id: beta
                    canonical_doc: agents/skills/beta.md
                    shim: .codex/personal/skills/beta/SKILL.md
                """,
            )
            for skill in ("alpha", "beta"):
                write(
                    root / "agents" / "skills" / f"{skill}.md",
                    f"""
                    # @dependency-start
                    # contract skill
                    # responsibility Owns the {skill} skill.
                    # @dependency-end
                    """,
                )
            write(
                root / "tools" / "consumer.py",
                """
                # @dependency-start
                # contract tool
                # responsibility References every generated skill view.
                # downstream implementation ../.codex/personal/skills/*/SKILL.md generated views
                # @dependency-end
                """,
            )

            projection_result = self.run_client(root, "query", "--all")
            self.assertEqual(projection_result.returncode, 0, projection_result.stderr)
            projection = json.loads(projection_result.stdout)

            self.assertEqual(
                {
                    (fact["source"], fact["target"])
                    for fact in projection["dependency_facts"]
                },
                {
                    ("tools/consumer.py", "agents/skills/alpha.md"),
                    ("tools/consumer.py", "agents/skills/beta.md"),
                },
            )
            self.assertFalse((root / ".codex").exists())

    def test_unmatched_generated_skill_glob_is_rejected(self) -> None:
        """An unmatched generated skill glob remains a rejected stale target."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write(
                root / "agents" / "skills" / "catalog.yaml",
                """
                skill_families:
                  - id: example
                    canonical_doc: agents/skills/example.md
                    shim: .codex/personal/skills/example/SKILL.md
                """,
            )
            write(
                root / "agents" / "skills" / "example.md",
                """
                # @dependency-start
                # contract skill
                # responsibility Owns the example skill.
                # @dependency-end
                """,
            )
            write(
                root / "tools" / "consumer.py",
                """
                # @dependency-start
                # contract tool
                # responsibility References an unmatched generated skill glob.
                # downstream implementation ../.codex/personal/skills/missing-*/SKILL.md stale view
                # @dependency-end
                """,
            )
            result = self.run_client(root, "query", "--all")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "source dependency projection failed: unknown generated skill view",
                self.error_text(result),
            )


if __name__ == "__main__":
    unittest.main()
