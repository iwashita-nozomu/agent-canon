"""Tests for source-derived dependency query and context projections."""

# @dependency-start
# contract test
# responsibility Verifies dependency consumers do not require persisted graph runtime state.
# upstream implementation ../../tools/agent_tools/source_dependency_graph.py derives source projections
# upstream implementation ../../tools/agent_tools/graph_client.py routes dependency reads to source
# downstream implementation ../../tools/ci/check_agent_canon_pr.sh uses source-owned dependency review
# @dependency-end

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.agent_tools.graph_client import GraphClient, GraphClientError


def write(path: Path, content: str) -> None:
    """Write one dedented fixture file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


class GraphClientSourceProjectionTest(unittest.TestCase):
    """Verify dependency reads are pure functions of tracked source bytes."""

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
            downstream implementation ../../tools/feature.py implements the feature
            @dependency-end
            -->
            # Feature
            """,
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

    def test_dependency_query_works_without_graph_executable_or_state(self) -> None:
        """Dependency query reads source even when no executable or graph DB exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.fixture(root)
            client = GraphClient(root, executable=root / "missing-agent-canon")

            response = client.query(
                all_nodes=True,
                relation="dependency",
                direction="both",
                depth=0,
            )

            self.assertEqual(response.status, "fresh")
            self.assertEqual(response.payload["projection"], "tracked-source")
            self.assertGreaterEqual(len(response.dependency_facts), 4)
            self.assertFalse((root / ".agent-canon").exists())

    def test_legacy_all_query_option_uses_the_same_source_projection(self) -> None:
        """The current vector-search call shape remains source-direct."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.fixture(root)
            client = GraphClient(root, executable=root / "missing-agent-canon")

            response = client.query(
                **{"all": True},
                relation="dependency",
                direction="both",
                depth=0,
            )

            self.assertEqual(response.status, "fresh")
            self.assertEqual(response.payload["projection"], "tracked-source")

    def test_context_is_source_bound_and_contains_declared_closure(self) -> None:
        """Context identity and closure are derived from current source bytes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.fixture(root)
            client = GraphClient(root, executable=root / "missing-agent-canon")

            response = client.context("documents/design/feature.md")

            identity = response.source_identity
            self.assertIsNotNone(identity)
            assert identity is not None
            self.assertEqual(identity.source_path, "documents/design/feature.md")
            self.assertEqual(len(identity.content_sha256), 64)
            self.assertEqual(
                response.payload["parent_paths"],
                ["documents/design/parent.md"],
            )
            self.assertEqual(
                response.payload["evidence_paths"],
                [
                    "documents/design/feature.md",
                    "documents/design/parent.md",
                    "tools/feature.py",
                ],
            )
            self.assertFalse((root / ".agent-canon").exists())

    def test_explicit_persisted_graph_commands_still_require_runtime(self) -> None:
        """Only explicit build/status and non-source relations invoke the runtime."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.fixture(root)
            client = GraphClient(root, executable=root / "missing-agent-canon")

            with self.assertRaisesRegex(GraphClientError, "process launch failed"):
                client.build()
            with self.assertRaisesRegex(GraphClientError, "process launch failed"):
                client.status()
            with self.assertRaisesRegex(GraphClientError, "process launch failed"):
                client.query(
                    all_nodes=True,
                    relation="owner",
                    direction="both",
                    depth=0,
                )

    def test_dependency_target_escape_is_rejected_without_runtime_fallback(self) -> None:
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
            client = GraphClient(root, executable=root / "missing-agent-canon")

            with self.assertRaisesRegex(
                GraphClientError,
                "source dependency projection failed.*escapes repository root",
            ):
                client.query(
                    all_nodes=True,
                    relation="dependency",
                    direction="both",
                    depth=0,
                )


if __name__ == "__main__":
    unittest.main()
