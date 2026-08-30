"""Tests for dependency-free vector search."""

# @dependency-start
# contract test
# responsibility Tests vector search indexing exclusions and context expansion.
# upstream implementation ../../tools/analysis/search/vector_search.py searches text surfaces
# upstream implementation ../../tools/analysis/dependencies/graph_client.py supplies canonical dependency context
# upstream design ../../tools/README.md documents vector search usage
# @dependency-end

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tools.analysis.search import vector_search as vector_tool
from tools.analysis.dependencies.graph_client import GraphResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VECTOR_SEARCH = PROJECT_ROOT / "tools" / "analysis" / "search" / "vector_search.py"


def run_search(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run vector search against a temporary root."""
    return subprocess.run(
        [sys.executable, str(VECTOR_SEARCH), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class VectorSearchTest(unittest.TestCase):
    """Verify vector search index hygiene."""

    @staticmethod
    def graph_response(*, include_dependencies: bool) -> GraphResponse:
        """Return one fresh canonical dependency projection."""
        facts: list[dict[str, object]] = []
        if include_dependencies:
            facts.extend(
                [
                    {
                        "id": "fact-upstream",
                        "kind": "dependency",
                        "inferred": False,
                        "from": "tool",
                        "to": "design",
                        "producer": "source-snapshot",
                        "source_path": "tools/search_tool.py",
                        "source_span": None,
                        "evidence_ref": "tools/search_tool.py:3",
                        "authority": "ManifestParser",
                        "dependency_detail": {
                            "direction": "upstream",
                            "kind": "design",
                            "reason": "alpha search design",
                        },
                    },
                    {
                        "id": "fact-downstream",
                        "kind": "dependency",
                        "inferred": False,
                        "from": "tool",
                        "to": "test",
                        "producer": "source-snapshot",
                        "source_path": "tools/search_tool.py",
                        "source_span": None,
                        "evidence_ref": "tools/search_tool.py:4",
                        "authority": "ManifestParser",
                        "dependency_detail": {
                            "direction": "downstream",
                            "kind": "implementation",
                            "reason": "validates search",
                        },
                    },
                ]
            )
        return GraphResponse(
            schema="agent-canon.graph.query.v1",
            command="query",
            status="fresh",
            payload={
                "nodes": [
                    {"id": "tool", "path": "tools/search_tool.py"},
                    {"id": "design", "path": "documents/search.md"},
                    {"id": "test", "path": "tests/test_search_tool.py"},
                ],
                "facts": facts,
                "graph_fingerprint": "fixture",
            },
            exit_code=0,
        )

    def run_context_search(
        self,
        root: Path,
        response: GraphResponse,
        *arguments: str,
    ) -> tuple[int, str, str]:
        """Run context mode with one canonical graph adapter fake."""
        client = mock.Mock()
        client.query.return_value = response
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(vector_tool, "GraphClient", return_value=client),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            return_code = vector_tool.main(["--root", str(root), *arguments])
        client.query.assert_called_once_with(
            all=True,
            relation="dependency",
            direction="both",
            depth=0,
        )
        return return_code, stdout.getvalue(), stderr.getvalue()

    def test_git_directory_is_not_indexed(self) -> None:
        """Root .git files must not be indexed even when the surface is broad."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "tools").mkdir()
            (root / "tools" / "guide.md").write_text(
                "ordinary searchable guide\n",
                encoding="utf-8",
            )
            leak = root / ".git" / "objects" / "aa" / "secret.md"
            leak.parent.mkdir(parents=True)
            leak.write_text("needleonlytoken\n", encoding="utf-8")

            result = run_search(
                root,
                "--surface",
                ".",
                "--query",
                "needleonlytoken",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["hits"], [])

    def test_submodule_object_database_is_not_indexed(self) -> None:
        """Nested .git object databases must be excluded from custom surfaces."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            module = root / "module"
            (module / "docs").mkdir(parents=True)
            (module / "docs" / "guide.md").write_text(
                "module visible guide\n",
                encoding="utf-8",
            )
            leak = module / ".git" / "objects" / "aa" / "secret.md"
            leak.parent.mkdir(parents=True)
            leak.write_text("submoduleonlytoken\n", encoding="utf-8")

            result = run_search(
                root,
                "--surface",
                "module",
                "--query",
                "submoduleonlytoken",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["hits"], [])
            self.assertEqual(payload["indexed_files"], 1)

    def test_legacy_token_tool_file_is_not_indexed(self) -> None:
        """Retired legacy-like implementation names must not enter search hits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tools = root / "tools"
            tools.mkdir()
            (tools / "current_search.py").write_text(
                "def current_search():\n    return 'current'\n",
                encoding="utf-8",
            )
            (tools / "search_legacy.py").write_text(
                "def retired_search():\n    return 'legacyonlyneedle'\n",
                encoding="utf-8",
            )

            result = run_search(
                root,
                "--surface",
                "tools",
                "--query",
                "legacyonlyneedle",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["hits"], [])
            self.assertEqual(payload["indexed_files"], 1)

    def test_legacy_token_document_file_remains_indexed(self) -> None:
        """Legacy terminology outside tools remains searchable documentation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            docs = root / "documents"
            docs.mkdir()
            (docs / "legacy-search-guide.md").write_text(
                "legacydocsneedle explains the retired path for readers\n",
                encoding="utf-8",
            )

            result = run_search(
                root,
                "--surface",
                "documents",
                "--query",
                "legacydocsneedle",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["indexed_files"], 1)
            self.assertEqual(payload["hits"][0]["path"], "documents/legacy-search-guide.md")

    def test_context_expands_dependency_headers(self) -> None:
        """Context mode should expand search hits through dependency manifests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "tools").mkdir()
            (root / "documents").mkdir()
            (root / "tests").mkdir()
            (root / "tools" / "search_tool.py").write_text(
                "\n".join(
                    [
                        "# @dependency-start",
                        "# responsibility Implements alpha search entrypoint.",
                        "# upstream design ../documents/search.md alpha search design",
                        "# downstream implementation ../tests/test_search_tool.py validates search",
                        "# @dependency-end",
                        "def alpha_entry():",
                        "    return alpha_helper()",
                        "",
                        "def alpha_helper():",
                        "    return 1",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "documents" / "search.md").write_text(
                "# Search Design\n",
                encoding="utf-8",
            )
            (root / "tests" / "test_search_tool.py").write_text(
                "from tools.search_tool import alpha_entry\n",
                encoding="utf-8",
            )

            return_code, stdout, stderr = self.run_context_search(
                root,
                self.graph_response(include_dependencies=True),
                "--surface",
                ".",
                "--query",
                "alpha_entry",
                "--context",
                "--format",
                "json",
            )

            self.assertEqual(return_code, 0, stderr)
            payload = json.loads(stdout)
            context_paths = {
                (item["role"], item["path"]) for item in payload["context"]["paths"]
            }
            self.assertIn(("search_hit", "tools/search_tool.py"), context_paths)
            self.assertIn(("declared_upstream", "documents/search.md"), context_paths)
            self.assertIn(("declared_downstream", "tests/test_search_tool.py"), context_paths)

    def test_context_expands_python_call_graph(self) -> None:
        """Context mode should include direct callees and callers for focus symbols."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_dir = root / "python"
            source_dir.mkdir()
            (source_dir / "workflow.py").write_text(
                "\n".join(
                    [
                        "def caller():",
                        "    return alpha_entry()",
                        "",
                        "def alpha_entry():",
                        "    return alpha_helper()",
                        "",
                        "def alpha_helper():",
                        "    return 1",
                    ]
                ),
                encoding="utf-8",
            )

            return_code, stdout, stderr = self.run_context_search(
                root,
                self.graph_response(include_dependencies=False),
                "--surface",
                "python",
                "--query",
                "alpha_entry",
                "--context",
                "--symbol",
                "alpha_entry",
                "--format",
                "json",
            )

            self.assertEqual(return_code, 0, stderr)
            payload = json.loads(stdout)
            edge_pairs = {
                (item["direction"], item["caller"], item["callee"])
                for item in payload["context"]["python_edges"]
            }
            self.assertIn(
                (
                    "calls",
                    "python/workflow.py:alpha_entry",
                    "python/workflow.py:alpha_helper",
                ),
                edge_pairs,
            )
            self.assertIn(
                (
                    "called_by",
                    "python/workflow.py:caller",
                    "python/workflow.py:alpha_entry",
                ),
                edge_pairs,
            )


if __name__ == "__main__":
    unittest.main()
