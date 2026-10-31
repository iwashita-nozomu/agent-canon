"""CLI integration tests for the provider-selecting AgentCanon search route."""

# @dependency-start
# contract test
# responsibility Tests native search CLI input precedence, provider routing, and failure semantics.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/agent_search.rs routes providers
# upstream design ../../documents/tools/search-coordination.md staged search owner contract
# downstream test ../../tools/runtime/dispatch/agent-canon/src/agent_search_tests.rs checks owner composition
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")


class SearchRouteTest(unittest.TestCase):
    """Verify native search uses separate providers and Git's own match rules."""

    def new_repository(self, root: Path) -> None:
        """Create the independent Git input required by the text provider."""
        completed = subprocess.run(
            ["git", "-C", str(root), "init", "-q"], capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def run_search(
        self, root: Path, *args: str, input_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Invoke the selected native executable against a fixture repository."""
        if not AGENT_CANON_CLI:
            self.fail("AGENT_CANON_CLI must select the current native executable")
        return subprocess.run(
            [AGENT_CANON_CLI, "agent-search", "--root", str(root), *args],
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_default_is_stateless_git_search_with_native_regex(self) -> None:
        """The default selects Git only and preserves native regex/word behavior."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.new_repository(root)
            (root / "guide.md").write_text(
                "alpha beta\nalphabet\n", encoding="utf-8"
            )
            result = self.run_search(
                root,
                "--purpose",
                "alpha|beta",
                "--regex",
                "--word-regexp",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["providers"], ["text"])
        self.assertEqual(payload["results"][0]["status"], "pass")
        self.assertEqual(payload["results"][0]["result"], "guide.md:1:alpha beta\n")

    def test_query_file_uses_git_native_pattern_file(self) -> None:
        """Git receives separate line-delimited patterns without tokenization."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            root = workspace / "repo"
            root.mkdir()
            self.new_repository(root)
            (root / "guide.md").write_text("alpha\nbeta\n", encoding="utf-8")
            query_file = workspace / "patterns.txt"
            query_file.write_text("alpha\nbeta\n", encoding="utf-8")
            result = self.run_search(
                root,
                "--query-file",
                str(query_file),
                "--providers",
                "text",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["results"][0]["result"],
            "guide.md:1:alpha\nguide.md:2:beta\n",
        )

    def test_query_stdin_uses_git_native_pattern_file(self) -> None:
        """Stdin lines stay native Git patterns rather than custom search terms."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.new_repository(root)
            (root / "guide.md").write_text("alpha\nbeta\n", encoding="utf-8")
            result = self.run_search(
                root,
                "--query-stdin",
                "--providers",
                "text",
                "--format",
                "json",
                input_text="alpha\nbeta\n",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["results"][0]["result"],
            "guide.md:1:alpha\nguide.md:2:beta\n",
        )

    def test_missing_or_empty_query_file_uses_cli_failure_contract(self) -> None:
        """Missing and whitespace-only query files fail before provider dispatch."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.new_repository(root)
            missing = self.run_search(
                root,
                "--query-file",
                str(root / "missing-patterns.txt"),
                "--providers",
                "text",
            )
            empty_file = root / "empty-patterns.txt"
            empty_file.write_text(" \n", encoding="utf-8")
            empty = self.run_search(
                root,
                "--query-file",
                str(empty_file),
                "--providers",
                "text",
            )

        self.assertEqual(missing.returncode, 2)
        self.assertIn("query-file-read-failed", missing.stderr)
        self.assertEqual(missing.stdout, "")
        self.assertEqual(empty.returncode, 2)
        self.assertIn("query-or-purpose-required", empty.stderr)
        self.assertEqual(empty.stdout, "")

    def test_inline_query_precedes_query_file(self) -> None:
        """An inline pattern keeps precedence when a query file is also present."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            root = workspace / "repo"
            root.mkdir()
            self.new_repository(root)
            (root / "inline.md").write_text("inline-pattern\n", encoding="utf-8")
            (root / "file.md").write_text("file-pattern\n", encoding="utf-8")
            query_file = workspace / "patterns.txt"
            query_file.write_text("file-pattern\n", encoding="utf-8")
            result = self.run_search(
                root,
                "--query",
                "inline-pattern",
                "--query-file",
                str(query_file),
                "--providers",
                "text",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)["results"][0]["result"]
        self.assertIn("inline.md:1:inline-pattern", output)
        self.assertNotIn("file.md", output)

    def test_tool_provider_is_scoped_to_canonical_catalog(self) -> None:
        """Tool lookup uses Git on the catalog path and excludes other surfaces."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.new_repository(root)
            (root / "tools").mkdir()
            (root / "tools" / "catalog.yaml").write_text(
                "id: dependency-graph\n", encoding="utf-8"
            )
            (root / "docs.md").write_text("dependency-graph\n", encoding="utf-8")
            result = self.run_search(
                root,
                "--query",
                "dependency-graph",
                "--providers",
                "tool",
                "--format",
                "json",
            )
            no_match = self.run_search(
                root,
                "--query",
                "missing-tool-token",
                "--providers",
                "tool",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["results"][0]["status"], "pass")
        self.assertEqual(
            payload["results"][0]["result"],
            "tools/catalog.yaml:1:id: dependency-graph\n",
        )
        self.assertEqual(no_match.returncode, 0, no_match.stderr)
        no_match_payload = json.loads(no_match.stdout)
        self.assertEqual(no_match_payload["status"], "pass")
        self.assertEqual(no_match_payload["results"][0]["status"], "no_match")

    def test_semantic_provider_fails_without_text_fallback(self) -> None:
        """A missing index remains a semantic failure with no Git result."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.new_repository(root)
            (root / "docs.md").write_text("responsibility scope\n", encoding="utf-8")
            result = self.run_search(
                root,
                "--purpose",
                "responsibility scope",
                "--providers",
                "semantic",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["providers"], ["semantic"])
        self.assertEqual(payload["results"][0]["status"], "fail")
        self.assertNotIn("text", [item["provider"] for item in payload["results"]])

    def test_selected_providers_remain_separate_and_ordered(self) -> None:
        """Explicit results preserve provider order without ranking or fusion."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.new_repository(root)
            (root / "tools").mkdir()
            (root / "tools" / "catalog.yaml").write_text("id: token\n", encoding="utf-8")
            (root / "docs.md").write_text("token\n", encoding="utf-8")
            result = self.run_search(
                root,
                "--query",
                "token",
                "--surface",
                "docs.md",
                "--providers",
                "text,tool,text",
                "--format",
                "json",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["providers"], ["text", "tool"])
        self.assertEqual([item["provider"] for item in payload["results"]], ["text", "tool"])
        self.assertEqual(
            [item["result"] for item in payload["results"]],
            ["docs.md:1:token\n", "tools/catalog.yaml:1:id: token\n"],
        )
        self.assertNotIn("score", result.stdout)

    def test_query_file_and_stdin_remain_mutually_exclusive(self) -> None:
        """Conflicting query input modes retain the strict CLI error contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.new_repository(root)
            query_file = root / "query.txt"
            query_file.write_text("alpha\n", encoding="utf-8")
            result = self.run_search(
                root,
                "--query-file",
                str(query_file),
                "--query-stdin",
                "--providers",
                "text",
                input_text="beta\n",
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("query-file-and-query-stdin-are-mutually-exclusive", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
