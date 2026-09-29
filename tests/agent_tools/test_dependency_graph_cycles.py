"""Regression coverage for normalized, source-wide dependency cycle review."""

# @dependency-start
# contract test
# responsibility Verifies normalized SCC scope and projection snapshot boundaries.
# upstream implementation ../../tools/analysis/dependencies/check_dependency_graph.sh reviews source topology
# upstream implementation ../../tools/analysis/dependencies/source_dependency_graph.py resolves canonical source
# upstream design ../../documents/design/dependency-manifest-design.md defines prerequisite ordering
# @dependency-end

from __future__ import annotations

import itertools
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.agent_tools.test_dependency_manifest_tools import GRAPH, run_tool
from tools.agent.skills import skill_projection_registry as registry
from tools.analysis.dependencies import source_dependency_graph as source_graph

CYCLE = (
    ("a.py", "downstream", "b.py"),
    ("c.py", "upstream", "b.py"),
    ("c.py", "downstream", "a.py"),
)


def write_graph(root: Path, rows: tuple[tuple[str, str, str], ...]) -> None:
    """Write declarations; incoming-only nodes also carry an empty manifest."""
    nodes = {node for source, _, target in rows for node in (source, target)}
    for node in nodes:
        declarations = [
            f"# {direction} implementation {target} declared prerequisite relation"
            for source, direction, target in rows
            if source == node
        ]
        (root / node).write_text(
            "\n".join(
                [
                    "# @dependency-start",
                    "# contract test",
                    "# responsibility Defines a graph fixture node.",
                    *declarations,
                    "# @dependency-end",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def commit_fixture(root: Path) -> None:
    """Establish a real clean Git baseline for changed-scope tests."""
    for args in (
        ("init", "-q"),
        ("add", "."),
        (
            "-c", "user.name=Dependency Fixture",
            "-c", "user.email=dependency@example.invalid",
            "commit", "-qm", "fixture",
        ),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def reported_components(output: str) -> set[frozenset[str]]:
    """Read unordered SCC members, not a fabricated path through the component."""
    prefix = "dependency cycle includes "
    return {
        frozenset(line.removeprefix(prefix).split(", "))
        for line in output.splitlines()
        if line.startswith(prefix)
    }


class DependencyCycleScopeTest(unittest.TestCase):
    """Exercise the real shell review route, including unchanged source nodes."""

    def check(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return run_tool(str(GRAPH), "--root", str(root), *args, root=root)

    def test_mixed_direction_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(root, CYCLE)
            result = self.check(root)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                reported_components(result.stdout),
                {frozenset(("a.py", "b.py", "c.py"))},
            )

    def test_selected_cycle_through_unchanged_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(root, CYCLE)
            result = self.check(root, "a.py")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                reported_components(result.stdout),
                {frozenset(("a.py", "b.py", "c.py"))},
            )

    def test_changed_cycle_through_unchanged_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(root, CYCLE)
            commit_fixture(root)
            with (root / "a.py").open("a", encoding="utf-8") as stream:
                stream.write("# changed body\n")
            result = self.check(root, "--changed")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("cycle includes", result.stdout)

    def test_empty_changed_scope_is_not_full_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(
                root,
                (("a.py", "downstream", "b.py"), ("b.py", "downstream", "a.py")),
            )
            commit_fixture(root)
            result = self.check(root, "--changed", "--print-edges")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("cycle includes", result.stdout)
            self.assertNotIn("\t", result.stdout)

    def test_selected_incoming_only_manifest_is_not_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(root, (("a.py", "downstream", "b.py"),))
            result = self.check(root, "b.py")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reciprocal_declarations_are_one_ordering_edge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(
                root,
                (("a.py", "downstream", "b.py"), ("b.py", "upstream", "a.py")),
            )
            result = self.check(root, "--check-bidirectional")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("cycle includes", result.stdout)

    def test_full_review_reports_every_component_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(
                root,
                CYCLE + (("x.py", "downstream", "y.py"), ("y.py", "downstream", "x.py")),
            )
            result = self.check(root)
            self.assertEqual(
                reported_components(result.stdout),
                {frozenset(("a.py", "b.py", "c.py")), frozenset(("x.py", "y.py"))},
            )
            self.assertEqual(result.stdout.count("cycle includes"), 2)

    def test_selected_component_excludes_unrelated_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(
                root,
                CYCLE + (("x.py", "downstream", "y.py"), ("y.py", "downstream", "x.py")),
            )
            result = self.check(root, "a.py")
            self.assertEqual(
                reported_components(result.stdout),
                {frozenset(("a.py", "b.py", "c.py"))},
            )

    def test_reachable_but_unselected_cycle_is_not_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(root, CYCLE + (("x.py", "downstream", "a.py"),))
            result = self.check(root, "x.py")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("cycle includes", result.stdout)

    def test_report_only_retains_selected_component(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(root, CYCLE)
            result = self.check(root, "--cycle-report-only", "b.py")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("DEPENDENCY_GRAPH_CYCLES=report_only", result.stdout)
            self.assertEqual(len(reported_components(result.stdout)), 1)

    def test_self_reference_still_fails_in_report_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(root, (("a.py", "upstream", "a.py"),))
            result = self.check(root, "--cycle-report-only")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("self reference", result.stdout)

    def test_reverse_lookup_uses_full_topology(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(
                root,
                (("a.py", "downstream", "b.py"), ("b.py", "upstream", "a.py")),
            )
            result = self.check(root, "--check-bidirectional", "a.py")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_selected_edge_output_remains_declared_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(root, CYCLE)
            result = self.check(root, "--cycle-report-only", "--print-edges", "a.py")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rows = [line for line in result.stdout.splitlines() if "\t" in line]
            self.assertEqual(rows, ["downstream\timplementation\ta.py\tb.py"])

    def test_explicit_selection_precedes_changed_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(root, CYCLE)
            commit_fixture(root)
            result = self.check(root, "--changed", "a.py")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(reported_components(result.stdout)), 1)

    def test_deep_cycle_does_not_depend_on_recursion_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nodes = [f"node-{index:04d}.py" for index in range(1100)]
            rows = tuple(
                (node, "downstream", nodes[(index + 1) % len(nodes)])
                for index, node in enumerate(nodes)
            )
            write_graph(root, rows)
            result = self.check(root, nodes[0])
            self.assertEqual(reported_components(result.stdout), {frozenset(nodes)})
            self.assertNotIn("RecursionError", result.stderr)

    def test_all_three_node_topologies_under_six_declaration_encodings(self) -> None:
        """Compare 384 real CLI scenarios to an independent reachability oracle."""
        nodes = ("a.py", "b.py", "c.py")
        pairs = tuple(itertools.permutations(nodes, 2))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for bits in range(1 << len(pairs)):
                edges = [edge for index, edge in enumerate(pairs) if bits & (1 << index)]
                reachable = set(edges) | {(node, node) for node in nodes}
                for middle in nodes:
                    for first in nodes:
                        for last in nodes:
                            if (first, middle) in reachable and (middle, last) in reachable:
                                reachable.add((first, last))
                components = {
                    frozenset(
                        other for other in nodes
                        if (node, other) in reachable and (other, node) in reachable
                    )
                    for node in nodes
                }
                expected = {component for component in components if len(component) > 1}
                for encoding in range(6):
                    declarations = []
                    for index, (prerequisite, consumer) in enumerate(edges):
                        upstream = encoding == 1 or (
                            encoding in (3, 4) and index % 2 == encoding % 2
                        )
                        declarations.append(
                            (consumer, "upstream", prerequisite)
                            if upstream else (prerequisite, "downstream", consumer)
                        )
                        if encoding == 2:
                            declarations.append((consumer, "upstream", prerequisite))
                    if encoding == 5:
                        declarations.reverse()
                    for node in nodes:
                        (root / node).write_text("# no dependencies\n", encoding="utf-8")
                    write_graph(root, tuple(declarations))
                    with self.subTest(topology=bits, encoding=encoding):
                        result = self.check(root)
                        self.assertEqual(
                            result.returncode, int(bool(expected)),
                            result.stdout + result.stderr,
                        )
                        self.assertEqual(reported_components(result.stdout), expected)


class SourceProjectionSnapshotTest(unittest.TestCase):
    """Exercise ordinary-path independence and the existing projection snapshot API."""

    def fixture(self, root: Path) -> Path:
        catalog = root / "agents/skills/catalog.yaml"
        catalog.parent.mkdir(parents=True)
        catalog.write_text(
            "skill_families:\n  - id: example\n"
            "    canonical_doc: agents/skills/example.md\n"
            "    shim: .codex/personal/skills/example/SKILL.md\n",
            encoding="utf-8",
        )
        (catalog.parent / "example.md").write_text("# Example\n", encoding="utf-8")
        write_graph(root, (("a.py", "downstream", "b.py"),))
        return catalog

    def test_ordinary_source_and_targets_ignore_invalid_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self.fixture(root)
            catalog.write_text("not: a skill catalog\n", encoding="utf-8")
            self.assertEqual(source_graph.resolve_source_path(root, "a.py")[0], "a.py")
            self.assertEqual(
                source_graph.parse_manifest_document(root, "a.py").edges[0].target, "b.py"
            )
            self.assertEqual(
                source_graph.resolve_dependency_targets(root, root / "a.py", "b.py"),
                ("b.py",),
            )

    def test_whole_scan_acquires_one_projection_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            shim = root / ".codex/personal/skills/example/SKILL.md"
            shim.parent.mkdir(parents=True)
            shim.write_text("# Distributed adapter\n", encoding="utf-8")
            acquire = mock.Mock(wraps=registry.generated_skill_projections)
            with (
                mock.patch.object(registry, "generated_skill_projections", acquire),
                mock.patch.object(source_graph, "generated_skill_projections", acquire),
            ):
                documents = source_graph.dependency_documents(root)
            self.assertEqual(acquire.call_count, 1)
            self.assertEqual(
                sum(doc.path == "agents/skills/example.md" for doc in documents), 1
            )
            self.assertFalse(any(doc.path.startswith(".codex/") for doc in documents))

    def test_explicit_snapshot_is_reused_for_generated_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self.fixture(root)
            snapshot = registry.generated_skill_projections(root)
            catalog.write_text("invalid catalog\n", encoding="utf-8")
            document = source_graph.parse_manifest_document(
                root, ".codex/personal/skills/example/SKILL.md", snapshot
            )
            self.assertEqual(document.path, "agents/skills/example.md")

    def test_generated_view_still_requires_valid_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self.fixture(root)
            catalog.write_text("invalid catalog\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "skill catalog"):
                source_graph.resolve_source_path(
                    root, ".codex/personal/skills/example/SKILL.md"
                )
            with self.assertRaisesRegex(ValueError, "skill catalog"):
                source_graph.dependency_documents(root)

    def test_empty_snapshot_does_not_fall_back_to_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            with self.assertRaisesRegex(
                source_graph.SourceDependencyError, "unknown generated skill"
            ):
                source_graph.parse_manifest_document(
                    root, ".codex/personal/skills/example/SKILL.md", ()
                )

    def test_missing_generated_owner_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self.fixture(root)
            (catalog.parent / "example.md").unlink()
            with self.assertRaisesRegex(
                source_graph.SourceDependencyError, "unavailable"
            ):
                source_graph.resolve_source_path(
                    root, ".codex/personal/skills/example/SKILL.md"
                )

    def test_ordinary_missing_escape_and_symlink_fail_without_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self.fixture(root)
            catalog.write_text("invalid catalog\n", encoding="utf-8")
            (root / "link.py").symlink_to(root / "a.py")
            for path, reason in (
                ("missing.py", "unavailable"),
                ("../outside.py", "escapes repository root"),
                ("link.py", "symbolic link"),
            ):
                with (
                    self.subTest(path=path),
                    self.assertRaisesRegex(source_graph.SourceDependencyError, reason),
                ):
                    source_graph.resolve_source_path(root, path)


if __name__ == "__main__":
    unittest.main()
