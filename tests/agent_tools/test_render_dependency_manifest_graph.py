"""Focused native-input/output tests for dependency graph rendering."""

# @dependency-start
# contract test
# responsibility Tests native dependency graph source, labels, relations, and output checks.
# upstream implementation ../../tools/analysis/dependencies/render_dependency_manifest_graph.py renders graph artifacts.
# upstream implementation ../../tools/analysis/dependencies/check_dependency_graph.sh produces graph TSV inputs.
# upstream design ../../documents/tools/render_dependency_manifest_graph.md defines renderer bundle and Graph IR contracts.
# @dependency-end

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RENDER_GRAPH = (
    PROJECT_ROOT
    / "tools"
    / "analysis"
    / "dependencies"
    / "render_dependency_manifest_graph.py"
)


def run_renderer(
    *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the renderer CLI and capture text output."""
    return subprocess.run(
        [sys.executable, str(RENDER_GRAPH), *args],
        cwd=cwd or PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_graph(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    """Write a native dependency graph TSV fixture."""
    path.write_text(
        "direction\tkind\tsource\ttarget\n"
        + "".join("\t".join(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def run_git(root: Path, *args: str) -> str:
    """Run one Git command for an isolated renderer fixture."""
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def commit_fixture(root: Path, message: str) -> str:
    """Commit the fixture index without relying on global Git identity."""
    run_git(
        root,
        "-c",
        "user.name=Graph Renderer Test",
        "-c",
        "user.email=graph-renderer@example.invalid",
        "commit",
        "-qm",
        message,
    )
    return run_git(root, "rev-parse", "HEAD")


def initialize_git_fixture(root: Path) -> str:
    """Create the committed source snapshot required by the renderer."""
    run_git(root, "init", "-q")
    run_git(root, "add", "-A")
    return commit_fixture(root, "renderer fixture")


def sha256_file(path: Path) -> str:
    """Return a file's lowercase SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RenderDependencyManifestGraphTest(unittest.TestCase):
    """Validate native graph inputs, labels, relations, and artifact readback."""

    def test_bundle_preserves_native_graph_and_artifact_descriptors(self) -> None:
        """Bundle mode emits all native artifacts and source summaries."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checker = (
                root
                / "tools"
                / "analysis"
                / "dependencies"
                / "check_dependency_graph.sh"
            )
            checker.parent.mkdir(parents=True)
            checker.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "out=''\n"
                'while [ "$#" -gt 0 ]; do\n'
                '  case "$1" in\n'
                '    --graph-tsv) out="$2"; shift 2 ;;\n'
                "    *) shift ;;\n"
                "  esac\n"
                "done\n"
                "printf 'direction\\tkind\\tsource\\ttarget\\nupstream\\tdesign\\ta.md\\tb.md\\n' > \"$out\"\n",
                encoding="utf-8",
            )
            checker.chmod(0o755)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            (root / "b.md").write_text("b\n", encoding="utf-8")
            initialize_git_fixture(root)
            bundle = root / "bundle"
            result = run_renderer(
                "--root",
                str(root),
                "--scope",
                "changed",
                "--bundle-dir",
                str(bundle),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                sorted(path.name for path in bundle.iterdir()),
                [
                    "dependency_graph.dot",
                    "dependency_graph.html",
                    "dependency_graph.ir.json",
                    "dependency_graph.md",
                    "dependency_graph.tsv",
                    "manifest.json",
                ],
            )
            manifest = json.loads(
                (bundle / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["schema"], "agent_canon.dependency_graph_bundle.v1"
            )
            self.assertEqual(manifest["status"], "pass")
            self.assertEqual(manifest["summary"]["node_count"], 2)
            self.assertEqual(manifest["summary"]["edge_count"], 1)
            self.assertNotIn("visualization_source_universe", manifest)
            self.assertNotIn("visualization_tool_calls", manifest)
            self.assertNotIn("visualization_coverage", manifest)
            for artifact in manifest["artifacts"]:
                self.assertEqual(
                    artifact["sha256"], sha256_file(bundle / artifact["path"])
                )

            graph_ir = json.loads(
                (bundle / "dependency_graph.ir.json").read_text(encoding="utf-8")
            )
            self.assertEqual(graph_ir["schema"], "agent_canon.graph_ir.v2")
            relations = {
                (edge["relation"], edge["label"]) for edge in graph_ir["edges"]
            }
            self.assertIn(("upstream", "design"), relations)
            self.assertIn(("contains", "contains"), relations)

    def test_supplied_tsv_is_copied_into_bundle_without_rewrite(self) -> None:
        """Supplied native TSV is preserved as data, without claiming a checker run."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            (root / "b.md").write_text("b\n", encoding="utf-8")
            graph = root / "source.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            initialize_git_fixture(root)
            bundle = root / "copied"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--bundle-dir",
                str(bundle),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (bundle / "dependency_graph.tsv").read_bytes(), graph.read_bytes()
            )
            manifest = json.loads(
                (bundle / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["source"]["origin_kind"], "supplied")
            self.assertEqual(
                manifest["source"]["origin_locator"], graph.resolve().as_posix()
            )
            self.assertEqual(manifest["checker"]["status"], "not_run")

    def test_generated_checker_failure_aborts_before_bundle(self) -> None:
        """Default checker failure remains visible even after writing a TSV."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            checker = (
                root
                / "tools"
                / "analysis"
                / "dependencies"
                / "check_dependency_graph.sh"
            )
            checker.parent.mkdir(parents=True)
            checker.write_text(
                "#!/usr/bin/env bash\n"
                "out=''\n"
                'while [ "$#" -gt 0 ]; do\n'
                '  case "$1" in\n'
                '    --graph-tsv) out="$2"; shift 2 ;;\n'
                "    *) shift ;;\n"
                "  esac\n"
                "done\n"
                "printf 'direction\\tkind\\tsource\\ttarget\\nupstream\\tdesign\\ta.md\\tb.md\\n' > \"$out\"\n"
                "printf 'checker stdout evidence\\n'\n"
                "printf 'checker stderr evidence\\n' >&2\n"
                "exit 7\n",
                encoding="utf-8",
            )
            checker.chmod(0o755)
            initialize_git_fixture(root)
            bundle = root / "bundle"

            result = run_renderer(
                "--root", str(root), "--bundle-dir", str(bundle), "--format", "json"
            )

            self.assertEqual(result.returncode, 7)
            self.assertEqual(result.stdout, "")
            self.assertIn("checker stdout evidence", result.stderr)
            self.assertIn("checker stderr evidence", result.stderr)
            self.assertFalse(bundle.exists())

    def test_bundle_fail_on_broken_exits_after_selected_output(self) -> None:
        """fail-on-broken reports the committed bundle and then returns nonzero."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "missing.md")])
            initialize_git_fixture(root)
            bundle = root / "bundle"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--bundle-dir",
                str(bundle),
                "--fail-on-broken",
            )

            self.assertEqual(result.returncode, 1)
            self.assertTrue((bundle / "manifest.json").exists())
            manifest = json.loads(
                (bundle / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "fail")
            self.assertEqual(manifest["summary"]["broken_target_count"], 1)
            self.assertIn("summary.broken_target_count=1", result.stdout)

    def test_bundle_text_and_json_formats(self) -> None:
        """Bundle output preserves its existing text and JSON CLI modes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.md").write_text("a\n", encoding="utf-8")
            (root / "b.md").write_text("b\n", encoding="utf-8")
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            initialize_git_fixture(root)
            text_bundle = root / "text-bundle"
            json_bundle = root / "json-bundle"

            text_result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--bundle-dir",
                str(text_bundle),
            )
            json_result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--bundle-dir",
                str(json_bundle),
                "--format",
                "json",
            )

            self.assertEqual(text_result.returncode, 0, text_result.stderr)
            self.assertIn(
                "schema=agent_canon.dependency_graph_bundle.v1", text_result.stdout
            )
            with self.assertRaises(json.JSONDecodeError):
                json.loads(text_result.stdout)
            self.assertEqual(json_result.returncode, 0, json_result.stderr)
            payload = json.loads(json_result.stdout)
            self.assertEqual(
                payload["schema"], "agent_canon.dependency_graph_bundle.v1"
            )
            self.assertIn("manifest_path", payload)
            self.assertIn("manifest_sha256", payload)

    def test_html_contains_complete_graph_ir_and_static_evidence(self) -> None:
        """HTML keeps all native nodes and edges alongside its accessible static view."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            rows = [
                ("upstream", "design", f"node-{index}.md", f"node-{index + 1}.md")
                for index in range(505)
            ]
            write_graph(graph, rows)
            initialize_git_fixture(root)
            html_out = root / "graph.html"

            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--html-out",
                str(html_out),
                "--title",
                "Accessible Dependency Graph",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            envelope = json.loads(result.stdout)
            self.assertEqual(envelope["summary"]["node_count"], 506)
            self.assertEqual(envelope["summary"]["edge_count"], 505)
            rendered_html = html_out.read_text(encoding="utf-8")
            self.assertIn(
                '<script id="graph-data" type="application/json">', rendered_html
            )
            embedded = rendered_html.split(
                '<script id="graph-data" type="application/json">', 1
            )[1].split("</script>", 1)[0]
            graph_ir = json.loads(embedded)
            self.assertEqual(graph_ir["schema"], "agent_canon.graph_ir.v2")
            self.assertEqual(graph_ir["summary"]["nodes"], 506)
            self.assertEqual(graph_ir["summary"]["edges"], 505)
            self.assertIn('id="direction-filters"', rendered_html)
            self.assertIn('id="focus"', rendered_html)
            self.assertIn('id="inspector-content"', rendered_html)
            self.assertIn('id="static-graph"', rendered_html)
            self.assertIn('aria-live="polite"', rendered_html)
            self.assertIn('role: "button"', rendered_html)
            self.assertIn('"aria-label": `Inspect ${node.id}`', rendered_html)
            self.assertIn('event.key === "Enter" || event.key === " "', rendered_html)
            self.assertIn("<noscript>", rendered_html)
            self.assertIn("Complete path node list (507)", rendered_html)
            self.assertIn("Complete dependency edge list (505)", rendered_html)
            self.assertIn("node-505.md", rendered_html)

    def test_committed_tree_layer_includes_isolated_paths_and_preserves_relations(
        self,
    ) -> None:
        """Tracked paths add structural evidence without changing dependency rows."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "docs").mkdir()
            (root / "deep").mkdir()
            (root / "aliases").mkdir()
            (root / "src" / "connected.md").write_text("source\n", encoding="utf-8")
            (root / "docs" / "target.md").write_text("target\n", encoding="utf-8")
            (root / "deep" / "nested.md").write_text("nested\n", encoding="utf-8")
            (root / "isolated.txt").write_text("no dependency rows\n", encoding="utf-8")
            (root / "worktree-missing.md").write_text(
                "committed, then removed\n", encoding="utf-8"
            )
            (root / "aliases" / "linked.md").symlink_to("../src/connected.md")
            graph = root / "source.tsv"
            write_graph(
                graph,
                [
                    ("upstream", "design", "src/connected.md", "docs/target.md"),
                    (
                        "downstream",
                        "implementation",
                        "src/connected.md",
                        "worktree-missing.md",
                    ),
                ],
            )
            base_revision = initialize_git_fixture(root)

            (root / "later-only.md").write_text("later commit\n", encoding="utf-8")
            run_git(root, "add", "later-only.md")
            run_git(
                root,
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{base_revision},vendor/module",
            )
            head_revision = commit_fixture(root, "add later path and gitlink")
            (root / "worktree-missing.md").unlink()
            (root / "untracked-only.md").write_text(
                "not in selected tree\n", encoding="utf-8"
            )

            ir_out = root / "graph.ir.json"
            markdown_out = root / "graph.md"
            dot_out = root / "graph.dot"
            html_out = root / "graph.html"
            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--ir-out",
                str(ir_out),
                "--markdown-out",
                str(markdown_out),
                "--dot-out",
                str(dot_out),
                "--html-out",
                str(html_out),
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            envelope = json.loads(result.stdout)
            self.assertEqual(envelope["summary"]["node_count"], 3)
            self.assertEqual(envelope["summary"]["edge_count"], 2)
            self.assertEqual(envelope["summary"]["tracked_path_count"], 9)
            self.assertEqual(envelope["summary"]["broken_target_count"], 1)

            graph_ir = json.loads(ir_out.read_text(encoding="utf-8"))
            self.assertEqual(graph_ir["source"]["git_tree_revision"], head_revision)
            self.assertEqual(graph_ir["summary"]["nodes"], 3)
            self.assertEqual(graph_ir["summary"]["edges"], 2)
            self.assertEqual(graph_ir["summary"]["trackedPaths"], 9)
            self.assertEqual(graph_ir["summary"]["totalNodes"], 15)
            nodes = {node["id"]: node for node in graph_ir["nodes"]}
            self.assertEqual(nodes["isolated.txt"]["layer"], "artifact")
            self.assertEqual(nodes["isolated.txt"]["kind"], "repo_path")
            isolated_entry = nodes["isolated.txt"]["payload_json"]["git_tree_entry"]
            self.assertEqual(isolated_entry["revision"], head_revision)
            self.assertEqual(isolated_entry["mode"], "100644")
            self.assertEqual(isolated_entry["object_type"], "blob")
            self.assertRegex(isolated_entry["object_id"], r"^[0-9a-f]{40,64}$")
            symlink_entry = nodes["aliases/linked.md"]["payload_json"]["git_tree_entry"]
            self.assertEqual(
                (symlink_entry["mode"], symlink_entry["object_type"]),
                ("120000", "blob"),
            )
            gitlink_entry = nodes["vendor/module"]["payload_json"]["git_tree_entry"]
            self.assertEqual(
                (gitlink_entry["mode"], gitlink_entry["object_type"]),
                ("160000", "commit"),
            )
            self.assertEqual(gitlink_entry["object_id"], base_revision)
            self.assertIn("later-only.md", nodes)
            self.assertNotIn("untracked-only.md", nodes)
            self.assertFalse(any(path.startswith("vendor/module/") for path in nodes))
            self.assertTrue(nodes["worktree-missing.md"]["broken"])
            self.assertFalse(nodes["worktree-missing.md"]["payload_json"]["exists"])
            self.assertIn(
                "git_tree_entry", nodes["worktree-missing.md"]["payload_json"]
            )

            dependency_edges = [
                edge for edge in graph_ir["edges"] if edge["relation"] != "contains"
            ]
            containment_edges = [
                edge for edge in graph_ir["edges"] if edge["relation"] == "contains"
            ]
            self.assertEqual(len(dependency_edges), 2)
            self.assertEqual(
                [edge["payload_json"]["row"] for edge in dependency_edges], [0, 1]
            )
            child_kinds = {
                edge["payload_json"]["childPath"]: edge["payload_json"]["childKind"]
                for edge in containment_edges
            }
            self.assertEqual(child_kinds["aliases/linked.md"], "symlink")
            self.assertEqual(child_kinds["vendor/module"], "gitlink")
            self.assertEqual(child_kinds["deep/nested.md"], "repo_path")
            markdown = markdown_out.read_text(encoding="utf-8")
            self.assertNotIn("untracked-only.md", markdown)
            self.assertIn("## Committed Git Tree Containment", markdown)
            self.assertIn("isolated.txt", markdown)
            self.assertIn("contains:gitlink", markdown)
            dot = dot_out.read_text(encoding="utf-8")
            self.assertIn('"isolated.txt"', dot)
            self.assertIn('"contains:symlink"', dot)
            self.assertIn('"contains:gitlink"', dot)
            rendered_html = html_out.read_text(encoding="utf-8")
            self.assertIn("Complete path node list (9)", rendered_html)
            self.assertIn("isolated.txt", rendered_html)
            self.assertIn("gitlink", rendered_html)

            old_ir_out = root / "old-tree.ir.json"
            old_result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--source-revision",
                base_revision,
                "--ir-out",
                str(old_ir_out),
                "--format",
                "json",
            )
            self.assertEqual(old_result.returncode, 0, old_result.stderr)
            old_ir = json.loads(old_ir_out.read_text(encoding="utf-8"))
            self.assertEqual(old_ir["source"]["git_tree_revision"], base_revision)
            self.assertEqual(old_ir["summary"]["trackedPaths"], 7)
            old_nodes = {node["id"] for node in old_ir["nodes"]}
            self.assertNotIn("later-only.md", old_nodes)
            self.assertNotIn("vendor/module", old_nodes)
            self.assertNotIn("untracked-only.md", old_nodes)

    def test_empty_tsv_is_valid_but_malformed_tsv_fails_before_output(self) -> None:
        """A header-only empty graph is valid; malformed native rows are not dropped."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            html_out = root / "empty.html"
            write_graph(graph, [])
            initialize_git_fixture(root)

            empty_result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--html-out",
                str(html_out),
                "--format",
                "json",
            )

            self.assertEqual(empty_result.returncode, 0, empty_result.stderr)
            empty_payload = json.loads(empty_result.stdout)
            self.assertEqual(empty_payload["summary"]["node_count"], 0)
            self.assertEqual(empty_payload["summary"]["edge_count"], 0)
            self.assertTrue(html_out.is_file())

            graph.write_text(
                "direction\tkind\tsource\ttarget\nupstream\tdesign\ta.md\n",
                encoding="utf-8",
            )
            malformed_out = root / "malformed.html"
            malformed_result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--html-out",
                str(malformed_out),
                "--format",
                "json",
            )

            self.assertEqual(malformed_result.returncode, 2)
            self.assertIn(
                "dependency graph TSV line 2 has 3 fields", malformed_result.stderr
            )
            self.assertFalse(malformed_out.exists())

    def test_projection_uses_native_tsv_and_rejects_invalid_mode(self) -> None:
        """Named projection mode keeps native source and output checks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            initialize_git_fixture(root)
            html_out = root / "graph.html"
            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--html-out",
                str(html_out),
                "--format",
                "json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            envelope = json.loads(result.stdout)
            self.assertEqual(envelope["source"]["origin_kind"], "supplied")
            self.assertEqual(envelope["summary"]["edge_count"], 1)
            self.assertTrue(html_out.exists())
            html_text = html_out.read_text(encoding="utf-8")
            self.assertIn("a.md", html_text)
            self.assertIn("b.md", html_text)

            missing_output = run_renderer(
                "--root", str(root), "--graph-tsv", str(graph)
            )
            self.assertEqual(missing_output.returncode, 2)
            self.assertIn("requires at least one named output", missing_output.stderr)

    def test_projection_rejects_duplicate_resolved_outputs(self) -> None:
        """Projection mode refuses aliases that resolve to one destination."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            graph = root / "graph.tsv"
            write_graph(graph, [("upstream", "design", "a.md", "b.md")])
            (root / "nested").mkdir()
            sentinel = root / "same.out"
            sentinel.write_text("sentinel\n", encoding="utf-8")
            initialize_git_fixture(root)
            result = run_renderer(
                "--root",
                str(root),
                "--graph-tsv",
                str(graph),
                "--html-out",
                str(root / "nested" / ".." / "same.out"),
                "--ir-out",
                str(sentinel),
                "--format",
                "json",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("conflicting projection output path", result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "sentinel\n")


if __name__ == "__main__":
    unittest.main()
