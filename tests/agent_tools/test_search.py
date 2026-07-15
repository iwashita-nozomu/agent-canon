"""Tests for coordinated AgentCanon search."""

# @dependency-start
# contract test
# responsibility Tests purpose-based search across tool, local LLM card, header dependency, and code dependency providers.
# upstream implementation ../../tools/agent_tools/search.py coordinates search providers
# upstream implementation ../../tools/agent_tools/search_index.py supplies local LLM semantic cards
# upstream implementation ../../tools/agent_tools/vector_search.py supplies dependency and code facts
# upstream design ../../documents/search-coordination.md coordinated search provider contract
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

from tools.agent_tools import search as search_tool
from tools.agent_tools.graph_client import GraphResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEARCH = PROJECT_ROOT / "tools" / "agent_tools" / "search.py"


def write_search_fixture(root: Path) -> None:
    """Write a bounded repository fixture for coordinated search."""
    (root / "tools").mkdir(parents=True)
    (root / "documents").mkdir(parents=True)
    (root / "python").mkdir(parents=True)
    (root / "tools" / "catalog.yaml").write_text(
        "\n".join(
            [
                "version: 1",
                "entries:",
                "  - id: dependency-graph",
                "    summary: Validates dependency graph edit scope.",
                "    path: tools/dependency_graph.py",
                "    family: agent_tools",
                "    role: checker",
                "    docs:",
                "      - documents/dependency-graph.md",
                "    tests:",
                "      - tests/test_dependency_graph.py",
            ]
        ),
        encoding="utf-8",
    )
    (root / "tools" / "dependency_graph.py").write_text(
        "\n".join(
            [
                "# @dependency-start",
                "# responsibility Validates dependency graph edit scope.",
                "# upstream design ../documents/dependency-graph.md dependency graph policy",
                "# @dependency-end",
                "def dependency_graph_scope():",
                "    return 'dependency graph edit scope'",
            ]
        ),
        encoding="utf-8",
    )
    (root / "documents" / "workflow.md").write_text(
        "\n".join(
            [
                "<!--",
                "@dependency-start",
                "responsibility Documents alpha dispatch workflow ownership.",
                "upstream implementation ../python/workflow.py alpha dispatch implementation",
                "@dependency-end",
                "-->",
                "# Alpha Dispatch",
            ]
        ),
        encoding="utf-8",
    )
    (root / "python" / "workflow.py").write_text(
        "\n".join(
            [
                "def alpha_dispatch():",
                "    return alpha_target()",
                "",
                "def alpha_target():",
                "    return 'target'",
            ]
        ),
        encoding="utf-8",
    )


def run_search(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run search.py against a temporary root."""
    return subprocess.run(
        [sys.executable, str(SEARCH), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def run_search_with_input(
    root: Path, input_text: str, *args: str
) -> subprocess.CompletedProcess[str]:
    """Run search.py with stdin against a temporary root."""
    return subprocess.run(
        [sys.executable, str(SEARCH), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
    )


class CoordinatedSearchTest(unittest.TestCase):
    """Verify purpose-based candidate generation."""

    @staticmethod
    def graph_response(*, status: str = "fresh", exit_code: int = 0) -> GraphResponse:
        """Return one provenance-complete dependency query response."""
        return GraphResponse(
            schema="agent-canon.graph.query.v1",
            command="query",
            status=status,
            exit_code=exit_code,
            payload={
                "reason": None if status == "fresh" else "fingerprint differs",
                "graph_fingerprint": "fixture",
                "nodes": [
                    {
                        "id": "source",
                        "path": "documents/workflow.md",
                    },
                    {
                        "id": "target",
                        "path": "python/workflow.py",
                    },
                ],
                "facts": [
                    {
                        "id": "fact:workflow",
                        "kind": "dependency",
                        "inferred": False,
                        "from": "source",
                        "to": "target",
                        "producer": "source-snapshot",
                        "source_path": "documents/workflow.md",
                        "source_span": {
                            "path": "documents/workflow.md",
                            "start_line": 4,
                            "start_column": 1,
                            "end_line": 4,
                            "end_column": 72,
                        },
                        "evidence_ref": "documents/workflow.md:4",
                        "authority": "ManifestParser",
                        "dependency_detail": {
                            "direction": "upstream",
                            "kind": "implementation",
                            "reason": "alpha dispatch implementation target",
                        },
                    }
                ],
            },
        )

    def test_purpose_returns_tool_and_llm_card_candidate(self) -> None:
        """Tool search and semantic cards should agree on a cataloged tool."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)

            result = run_search(
                root,
                "--purpose",
                "find tool for dependency graph edit scope validation",
                "--providers",
                "llm,tool",
                "--surface",
                ".",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            candidates = {item["path"]: item for item in payload["candidates"]}
            self.assertIn("tools/dependency_graph.py", candidates)
            self.assertIn("tool", candidates["tools/dependency_graph.py"]["providers"])
            self.assertIn("llm", candidates["tools/dependency_graph.py"]["providers"])

    def test_query_file_returns_tool_candidate(self) -> None:
        """File-backed long queries should use the same search pipeline."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)
            query_file = root / "query.txt"
            query_file.write_text(
                "find tool for dependency graph edit scope validation",
                encoding="utf-8",
            )

            result = run_search(
                root,
                "--query-file",
                str(query_file),
                "--providers",
                "tool",
                "--surface",
                ".",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            candidates = {item["path"]: item for item in payload["candidates"]}
            self.assertIn("tools/dependency_graph.py", candidates)

    def test_query_stdin_returns_tool_candidate(self) -> None:
        """Stdin-backed long queries should use the same search pipeline."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)

            result = run_search_with_input(
                root,
                "find tool for dependency graph edit scope validation",
                "--query-stdin",
                "--providers",
                "tool",
                "--surface",
                ".",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            candidates = {item["path"]: item for item in payload["candidates"]}
            self.assertIn("tools/dependency_graph.py", candidates)

    def test_missing_query_file_uses_cli_failure_contract(self) -> None:
        """Missing query files should use the normal CLI failure envelope."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)

            result = run_search(
                root,
                "--query-file",
                str(root / "missing-query.txt"),
                "--providers",
                "tool",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("AGENT_SEARCH=fail", result.stderr)
            self.assertIn("query-file-read-failed", result.stderr)

    def test_empty_query_file_uses_cli_failure_contract(self) -> None:
        """Empty query files should use the normal empty-query failure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)
            query_file = root / "query.txt"
            query_file.write_text("", encoding="utf-8")

            result = run_search(
                root,
                "--query-file",
                str(query_file),
                "--providers",
                "tool",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("AGENT_SEARCH=fail", result.stderr)
            self.assertIn("query-or-purpose-required", result.stderr)

    def test_inline_query_precedes_query_file(self) -> None:
        """Inline query values preserve existing precedence over file input."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)
            query_file = root / "query.txt"
            query_file.write_text("alpha dispatch workflow implementation target", encoding="utf-8")

            result = run_search(
                root,
                "--query",
                "find tool for dependency graph edit scope validation",
                "--query-file",
                str(query_file),
                "--providers",
                "tool",
                "--surface",
                ".",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            candidates = {item["path"]: item for item in payload["candidates"]}
            self.assertIn("tools/dependency_graph.py", candidates)
            self.assertNotIn("python/workflow.py", candidates)

    def test_query_file_and_stdin_are_mutually_exclusive(self) -> None:
        """Long-query input modes should have one active source."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)
            query_file = root / "query.txt"
            query_file.write_text(
                "find tool for dependency graph edit scope validation",
                encoding="utf-8",
            )

            result = run_search_with_input(
                root,
                "alpha dispatch workflow implementation target",
                "--query-file",
                str(query_file),
                "--query-stdin",
                "--providers",
                "tool",
                "--surface",
                ".",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("AGENT_SEARCH=fail", result.stderr)
            self.assertIn("mutually-exclusive", result.stderr)

    def test_purpose_returns_header_and_code_dependency_candidates(self) -> None:
        """Header dependency and Python call facts should both contribute candidates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)
            graph_client = mock.Mock()
            graph_client.query.return_value = self.graph_response()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    search_tool, "GraphClient", return_value=graph_client
                ) as constructor,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                return_code = search_tool.main(
                    [
                        "--root",
                        str(root),
                        "--purpose",
                        "alpha dispatch workflow implementation target",
                        "--providers",
                        "header-deps,code-deps",
                        "--surface",
                        ".",
                        "--format",
                        "json",
                    ]
                )

            self.assertEqual(return_code, 0, stderr.getvalue())
            constructor.assert_called_once_with(
                root.resolve(), search_tool.CANONICAL_GRAPH_EXECUTABLE
            )
            graph_client.query.assert_called_once_with(
                all=True,
                relation="dependency",
                direction="both",
                depth=0,
            )
            payload = json.loads(stdout.getvalue())
            providers = {
                evidence["provider"]
                for item in payload["candidates"]
                for evidence in item["evidence"]
            }
            paths = {item["path"] for item in payload["candidates"]}
            self.assertIn("header-deps", providers)
            self.assertIn("code-deps", providers)
            self.assertIn("python/workflow.py", paths)
            header_evidence = " ".join(
                evidence["evidence"]
                for item in payload["candidates"]
                for evidence in item["evidence"]
                if evidence["provider"] == "header-deps"
            )
            for value in (
                "producer=source-snapshot",
                "evidence_ref=documents/workflow.md:4",
                "authority=ManifestParser",
            ):
                self.assertIn(value, header_evidence)

    def test_without_header_provider_makes_zero_graph_calls(self) -> None:
        """Provider selection closes the graph call boundary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)
            request = search_tool.SearchRequest(
                root=root,
                query=search_tool.query_profile("alpha dispatch"),
                providers=("code-deps",),
                surfaces=(".",),
                excludes=(),
                index_dir=root / ".index",
                top=10,
                refresh_index=False,
                run_llm=False,
                llama_cli="",
                model="",
                max_llm_files=0,
                max_bytes=100_000,
            )
            with mock.patch.object(
                search_tool,
                "GraphClient",
                side_effect=AssertionError("unexpected graph call"),
            ):
                corpus = search_tool.load_corpus(request)

        self.assertEqual(corpus.dependency_edges, ())

    def test_nonfresh_header_graph_fails_without_fallback(self) -> None:
        """Nonfresh dependency evidence is not converted to an empty edge set."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)
            graph_client = mock.Mock()
            graph_client.query.return_value = self.graph_response(
                status="stale", exit_code=3
            )
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    search_tool, "GraphClient", return_value=graph_client
                ),
                redirect_stderr(stderr),
            ):
                return_code = search_tool.main(
                    [
                        "--root",
                        str(root),
                        "--purpose",
                        "alpha dispatch",
                        "--providers",
                        "header-deps",
                    ]
                )

        self.assertEqual(return_code, 1)
        self.assertIn("AGENT_SEARCH=fail", stderr.getvalue())
        self.assertIn("status=stale", stderr.getvalue())
        graph_client.query.assert_called_once()


if __name__ == "__main__":
    unittest.main()
