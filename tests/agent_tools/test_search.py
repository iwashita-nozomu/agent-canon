"""Tests for coordinated AgentCanon search."""

# @dependency-start
# responsibility Tests purpose-based search across tool, local LLM card, header dependency, and code dependency providers.
# upstream implementation ../../tools/agent_tools/search.py coordinates search providers
# upstream implementation ../../tools/agent_tools/search_index.py supplies local LLM semantic cards
# upstream implementation ../../tools/agent_tools/vector_search.py supplies dependency and code facts
# upstream design ../../documents/search-coordination.md coordinated search provider contract
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEARCH = PROJECT_ROOT / "tools" / "agent_tools" / "search.py"


def write_search_fixture(root: Path) -> None:
    """Write a small repository fixture for coordinated search."""
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


class CoordinatedSearchTest(unittest.TestCase):
    """Verify purpose-based candidate generation."""

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

    def test_purpose_returns_header_and_code_dependency_candidates(self) -> None:
        """Header dependency and Python call facts should both contribute candidates."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_search_fixture(root)

            result = run_search(
                root,
                "--purpose",
                "alpha dispatch workflow implementation target",
                "--providers",
                "header-deps,code-deps",
                "--surface",
                ".",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            providers = {
                evidence["provider"]
                for item in payload["candidates"]
                for evidence in item["evidence"]
            }
            paths = {item["path"] for item in payload["candidates"]}
            self.assertIn("header-deps", providers)
            self.assertIn("code-deps", providers)
            self.assertIn("python/workflow.py", paths)


if __name__ == "__main__":
    unittest.main()
