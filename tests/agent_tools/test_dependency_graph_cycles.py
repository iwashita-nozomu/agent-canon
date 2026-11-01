"""Regression coverage for normalized, source-wide dependency cycle review."""

# @dependency-start
# contract test
# responsibility Verifies normalized SCC scope and projection snapshot boundaries.
# upstream implementation ../../tools/analysis/dependencies/check_dependency_graph.sh reviews source topology
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/source_dependency_graph.rs resolves canonical source
# upstream design ../../documents/design/dependency-manifest-design.md defines prerequisite ordering
# @dependency-end

from __future__ import annotations

import itertools
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.agent_tools.test_dependency_manifest_tools import GRAPH, run_tool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = Path(
    os.environ.get("AGENT_CANON_CLI", str(PROJECT_ROOT / "tools/bin/agent-canon"))
)


def run_source_graph(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_CANON_CLI), "source-dependency-graph", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def run_graph_client(
    root: Path, command: str, *args: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(AGENT_CANON_CLI),
            "graph-client",
            command,
            "--root",
            str(root),
            "--format",
            "json",
            *args,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


CYCLE = (
    ("a.py", "downstream", "b.py"),
    ("c.py", "upstream", "b.py"),
    ("c.py", "downstream", "a.py"),
)


def write_graph(
    root: Path,
    rows: tuple[tuple[str, str, str], ...],
    *,
    kind: str = "implementation",
) -> None:
    """Write relation declarations; incoming-only nodes carry an empty manifest."""
    nodes = {node for source, _, target in rows for node in (source, target)}
    for node in nodes:
        declarations = [
            f"# {direction} {kind} {target} declared relation"
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
            "-c",
            "user.name=Dependency Fixture",
            "-c",
            "user.email=dependency@example.invalid",
            "commit",
            "-qm",
            "fixture",
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

    def test_reference_cycle_remains_evidence_without_prerequisite_cycle(self) -> None:
        """Reference edges stay visible but do not create ordering cycles."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_graph(
                root,
                (("a.py", "upstream", "b.py"), ("b.py", "upstream", "a.py")),
                kind="reference",
            )

            result = self.check(root, "--print-edges")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("upstream\treference\ta.py\tb.py", result.stdout)
            self.assertNotIn("dependency cycle includes", result.stdout)

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
                CYCLE
                + (("x.py", "downstream", "y.py"), ("y.py", "downstream", "x.py")),
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
                CYCLE
                + (("x.py", "downstream", "y.py"), ("y.py", "downstream", "x.py")),
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
                edges = [
                    edge for index, edge in enumerate(pairs) if bits & (1 << index)
                ]
                reachable = set(edges) | {(node, node) for node in nodes}
                for middle in nodes:
                    for first in nodes:
                        for last in nodes:
                            if (first, middle) in reachable and (
                                middle,
                                last,
                            ) in reachable:
                                reachable.add((first, last))
                components = {
                    frozenset(
                        other
                        for other in nodes
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
                            if upstream
                            else (prerequisite, "downstream", consumer)
                        )
                        if encoding == 2:
                            declarations.append((consumer, "upstream", prerequisite))
                    if encoding == 5:
                        declarations.reverse()
                    for node in nodes:
                        (root / node).write_text(
                            "# no dependencies\n", encoding="utf-8"
                        )
                    write_graph(root, tuple(declarations))
                    with self.subTest(topology=bits, encoding=encoding):
                        result = self.check(root)
                        self.assertEqual(
                            result.returncode,
                            int(bool(expected)),
                            result.stdout + result.stderr,
                        )
                        self.assertEqual(reported_components(result.stdout), expected)


class SourceProjectionSnapshotTest(unittest.TestCase):
    """Exercise source paths and generated-view resolution through the native owner."""

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

    def resolve_target(
        self, root: Path, source: Path, target: str
    ) -> subprocess.CompletedProcess[str]:
        return run_source_graph(
            root,
            "resolve-targets",
            "--root",
            str(root),
            "--source",
            str(source),
            "--target",
            target,
        )

    def test_ordinary_source_and_targets_ignore_invalid_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self.fixture(root)
            catalog.write_text("not: a skill catalog\n", encoding="utf-8")
            result = self.resolve_target(root, root / "a.py", "b.py")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "b.py\n")

    def test_whole_scan_projects_materialized_generated_view_to_canonical_owner(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            consumer = root / "tools" / "consumer.py"
            consumer.parent.mkdir()
            consumer.write_text(
                "# @dependency-start\n"
                "# contract tool\n"
                "# responsibility References the generated skill view.\n"
                "# downstream implementation ../.codex/personal/skills/example/SKILL.md canonical owner\n"
                "# @dependency-end\n",
                encoding="utf-8",
            )
            shim = root / ".codex/personal/skills/example/SKILL.md"
            shim.parent.mkdir(parents=True)
            shim.write_text("# Distributed adapter\n", encoding="utf-8")
            result = run_graph_client(
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
            self.assertEqual(result.returncode, 0, result.stderr)
            response = json.loads(result.stdout)
            facts = response["dependency_facts"]
            self.assertEqual(
                sum(fact["target"] == "agents/skills/example.md" for fact in facts),
                1,
            )
            self.assertFalse(
                any(fact["target"].startswith(".codex/") for fact in facts)
            )

    def test_generated_view_target_resolves_to_canonical_source_without_materializing_view(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            result = self.resolve_target(
                root,
                root / "a.py",
                ".codex/personal/skills/example/SKILL.md",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "agents/skills/example.md\n")
            self.assertFalse(
                (root / ".codex/personal/skills/example/SKILL.md").exists()
            )

    def test_generated_view_still_requires_valid_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self.fixture(root)
            catalog.write_text("invalid catalog\n", encoding="utf-8")
            result = self.resolve_target(
                root,
                root / "a.py",
                ".codex/personal/skills/example/SKILL.md",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("skill catalog", result.stderr)

    def test_unmatched_generated_pattern_is_rejected_by_manifest_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            result = self.resolve_target(
                root,
                root / "a.py",
                ".codex/personal/skills/missing-*/SKILL.md",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout, ".codex/personal/skills/missing-*/SKILL.md\n"
            )

    def test_missing_generated_owner_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self.fixture(root)
            (catalog.parent / "example.md").unlink()
            result = self.resolve_target(
                root,
                root / "a.py",
                ".codex/personal/skills/example/SKILL.md",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "generated skill canonical source is unavailable", result.stderr
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
                with self.subTest(path=path):
                    result = run_graph_client(
                        root,
                        "context",
                        "--path",
                        path,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(reason, result.stderr)


if __name__ == "__main__":
    unittest.main()
