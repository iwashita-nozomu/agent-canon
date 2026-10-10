"""Tests for the provider-selecting AgentCanon search route."""

# @dependency-start
# contract test
# responsibility Tests native search-provider routing, result separation, and failure semantics.
# upstream implementation ../../tools/analysis/search/search.py routes selected providers
# upstream design ../../documents/tools/search-coordination.md staged search owner contract
# upstream implementation ../../tools/analysis/dependencies/graph_client.py supplies source dependency context
# upstream implementation ../../tools/analysis/code/lsp_code_analysis.py supplies code facts
# @dependency-end

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tools.analysis.code import lsp_code_analysis
from tools.analysis.dependencies.graph_client import GraphResponse
from tools.analysis.search import search as search_tool


class SearchRouteTest(unittest.TestCase):
    """Verify provider selection stays native and never fuses scores."""

    def run_main(self, *args: str) -> tuple[int, str, str]:
        """Capture one direct CLI invocation."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = search_tool.main(args)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_default_is_stateless_git_search_with_native_regex(self) -> None:
        """The default route selects Git only and preserves its stdout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = subprocess.CompletedProcess(
                args=["git", "grep"],
                returncode=0,
                stdout="tools/guide.md:4:alpha\n",
                stderr="",
            )
            with mock.patch.object(search_tool.subprocess, "run", return_value=completed) as run:
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--purpose",
                    "alpha|beta",
                    "--regex",
                    "--word-regexp",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["providers"], ["text"])
        self.assertEqual(payload["results"][0]["result"], "tools/guide.md:4:alpha\n")
        self.assertEqual(payload["results"][0]["status"], "pass")
        argv = run.call_args.args[0]
        self.assertEqual(argv[0:2], ("git", "grep"))
        self.assertIn("--untracked", argv)
        self.assertIn("--exclude-standard", argv)
        self.assertIn("--extended-regexp", argv)
        self.assertIn("--word-regexp", argv)
        self.assertIn("alpha|beta", argv)
        self.assertNotIn("agent-canon", argv)

    def test_query_file_uses_git_native_pattern_file(self) -> None:
        """Git receives line-delimited patterns without a custom tokenizer."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            query_file = root / "patterns.txt"
            query_file.write_text("alpha\nbeta\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=["git", "grep"], returncode=0, stdout="tools/a.py:1:beta\n", stderr=""
            )
            with mock.patch.object(search_tool.subprocess, "run", return_value=completed) as run:
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--query-file",
                    str(query_file),
                    "--providers",
                    "text",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 0, stderr)
        self.assertIn("tools/a.py:1:beta", json.loads(stdout)["results"][0]["result"])
        argv = run.call_args.args[0]
        self.assertIn("-f", argv)
        self.assertIn(str(query_file.resolve()), argv)
        self.assertNotIn("-e", argv)

    def test_query_stdin_uses_git_native_pattern_file(self) -> None:
        """Stdin patterns are passed to Git without custom term splitting."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = subprocess.CompletedProcess(
                args=["git", "grep"], returncode=0, stdout="docs/a.md:1:beta\n", stderr=""
            )
            with (
                mock.patch.object(search_tool.sys, "stdin", io.StringIO("alpha\nbeta\n")),
                mock.patch.object(search_tool.subprocess, "run", return_value=completed) as run,
            ):
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--query-stdin",
                    "--providers",
                    "text",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 0, stderr)
        self.assertIn("docs/a.md:1:beta", json.loads(stdout)["results"][0]["result"])
        argv = run.call_args.args[0]
        self.assertIn("-f", argv)
        self.assertIn("-", argv)
        self.assertEqual(run.call_args.kwargs["input"], "alpha\nbeta\n")

    def test_missing_or_empty_query_file_uses_cli_failure_contract(self) -> None:
        """Missing and empty query files fail before any provider is started."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            missing = root / "missing-patterns.txt"
            code, stdout, stderr = self.run_main(
                "--root", str(root), "--query-file", str(missing), "--providers", "text"
            )
            self.assertEqual(code, 2)
            self.assertIn("AGENT_SEARCH=fail", stderr)
            self.assertIn("query-file-read-failed", stderr)
            self.assertEqual(stdout, "")

            empty = root / "empty-patterns.txt"
            empty.write_text("\n", encoding="utf-8")
            code, stdout, stderr = self.run_main(
                "--root", str(root), "--query-file", str(empty), "--providers", "text"
            )

        self.assertEqual(code, 2)
        self.assertIn("query-or-purpose-required", stderr)
        self.assertEqual(stdout, "")

    def test_inline_query_precedes_query_file(self) -> None:
        """Inline pattern input keeps its existing precedence over a file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            query_file = root / "patterns.txt"
            query_file.write_text("file-pattern\n", encoding="utf-8")
            completed = subprocess.CompletedProcess(
                args=["git", "grep"], returncode=0, stdout="docs/a.md:1:inline\n", stderr=""
            )
            with mock.patch.object(search_tool.subprocess, "run", return_value=completed) as run:
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--query",
                    "inline-pattern",
                    "--query-file",
                    str(query_file),
                    "--providers",
                    "text",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 0, stderr)
        argv = run.call_args.args[0]
        self.assertIn("inline-pattern", argv)
        self.assertNotIn(str(query_file.resolve()), argv)

    def test_tool_provider_is_scoped_to_canonical_catalog(self) -> None:
        """Tool lookup delegates literal/regex matching to Git on tools/catalog.yaml."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = subprocess.CompletedProcess(
                args=["git", "grep"], returncode=1, stdout="", stderr=""
            )
            with mock.patch.object(search_tool.subprocess, "run", return_value=completed) as run:
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--query",
                    "dependency-graph",
                    "--providers",
                    "tool",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["results"][0]["status"], "no_match")
        argv = run.call_args.args[0]
        separator = argv.index("--")
        self.assertEqual(argv[separator + 1 :], ("tools/catalog.yaml",))

    def test_semantic_provider_delegates_without_fallback(self) -> None:
        """Unavailable semantic-index state stays a failure; Git is not a fallback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = subprocess.CompletedProcess(
                args=["agent-canon"], returncode=1, stdout="", stderr="index-stale"
            )
            with mock.patch.object(search_tool.subprocess, "run", return_value=completed) as run:
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--purpose",
                    "find dependency graph ownership",
                    "--providers",
                    "semantic",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 1)
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["providers"], ["semantic"])
        self.assertEqual(payload["results"][0]["stderr"], "index-stale")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(
            tuple(run.call_args.args[0][:3]),
            ("agent-canon", "semantic-index", "search"),
        )

    def test_selected_providers_remain_separate(self) -> None:
        """Explicit multi-provider requests preserve native results without ranking."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = [
                subprocess.CompletedProcess(
                    args=["git", "grep"], returncode=0, stdout="docs/a.md:1:x\n", stderr=""
                ),
                subprocess.CompletedProcess(
                    args=["git", "grep"], returncode=0, stdout="id: tool-x\n", stderr=""
                ),
            ]
            with mock.patch.object(search_tool.subprocess, "run", side_effect=completed):
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--query",
                    "x",
                    "--providers",
                    "text,tool",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["providers"], ["text", "tool"])
        self.assertEqual([item["provider"] for item in payload["results"]], ["text", "tool"])
        self.assertEqual([item["result"] for item in payload["results"]], ["docs/a.md:1:x\n", "id: tool-x\n"])
        self.assertNotIn("candidates", payload)
        self.assertNotIn("score", stdout)

    def test_header_dependency_provider_uses_source_graph_context(self) -> None:
        """Dependency context comes from GraphClient, not a copied header parser."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            graph = mock.Mock()
            graph.context.return_value = GraphResponse(
                schema="agent-canon.graph.context.v1",
                command="context",
                status="fresh",
                payload={"resolved_path": "tools/sample.py", "facts": ["source-fact"]},
                exit_code=0,
            )
            with mock.patch.object(search_tool, "GraphClient", return_value=graph):
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--query",
                    "tools/sample.py",
                    "--providers",
                    "header-deps",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 0, stderr)
        graph.context.assert_called_once_with("tools/sample.py")
        payload = json.loads(stdout)
        self.assertEqual(payload["results"][0]["result"][0]["facts"], ["source-fact"])

    def test_code_provider_returns_native_lsp_report(self) -> None:
        """Code facts come from the explicit LSP owner with no AST fallback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "src" / "module.py"
            source.parent.mkdir()
            source.write_text("def target():\n    return 1\n", encoding="utf-8")
            report = mock.Mock()
            report.status = "complete"
            report.as_json.return_value = {"status": "complete", "symbols": [{"name": "target"}]}
            with (
                mock.patch.object(
                    lsp_code_analysis,
                    "discover_lsp_files",
                    return_value=(source,),
                ) as discover,
                mock.patch.object(lsp_code_analysis, "analyze", return_value=report) as analyze,
            ):
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--query",
                    "target",
                    "--providers",
                    "code-deps",
                    "--surface",
                    "src",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 0, stderr)
        discover.assert_called_once_with(root.resolve(), ("src",), ())
        analyze.assert_called_once_with(root.resolve(), (source,))
        report.as_json.assert_called_once_with(root.resolve())
        payload = json.loads(stdout)
        self.assertEqual(payload["results"][0]["result"]["symbols"], [{"name": "target"}])

    def test_code_provider_preserves_lsp_failure(self) -> None:
        """An unavailable selected LSP route stays failed instead of downgrading."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report = mock.Mock()
            report.status = "failed"
            report.as_json.return_value = {
                "status": "failed",
                "error": {"code": "server-unavailable"},
            }
            with (
                mock.patch.object(lsp_code_analysis, "discover_lsp_files", return_value=()),
                mock.patch.object(lsp_code_analysis, "analyze", return_value=report) as analyze,
                mock.patch.object(search_tool.subprocess, "run") as subprocess_run,
            ):
                code, stdout, stderr = self.run_main(
                    "--root",
                    str(root),
                    "--query",
                    "target",
                    "--providers",
                    "code-deps",
                    "--format",
                    "json",
                )

        self.assertEqual(code, 1)
        self.assertEqual(stderr, "")
        analyze.assert_called_once_with(root.resolve(), ())
        subprocess_run.assert_not_called()
        payload = json.loads(stdout)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["results"][0]["result"]["error"]["code"], "server-unavailable")

    def test_query_file_and_stdin_are_mutually_exclusive(self) -> None:
        """Query input modes retain their existing strict conflict behavior."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            query_file = Path(tmp_dir) / "query.txt"
            query_file.write_text("alpha\n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(search_tool.sys, "stdin", io.StringIO("beta\n")),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                code = search_tool.main(
                    [
                        "--query-file",
                        str(query_file),
                        "--query-stdin",
                        "--providers",
                        "text",
                    ]
                )

        self.assertEqual(code, 2)
        self.assertIn("query-file-and-query-stdin-are-mutually-exclusive", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
