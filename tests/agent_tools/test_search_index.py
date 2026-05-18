"""Tests for coordinated search index generation."""

# @dependency-start
# responsibility Tests repo-local search-card index generation and local LLM preflight behavior.
# upstream implementation ../../tools/agent_tools/search_index.py builds local LLM semantic cards
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
SEARCH_INDEX = PROJECT_ROOT / "tools" / "agent_tools" / "search_index.py"


def write_tool_registry(root: Path) -> None:
    """Write a minimal tool catalog."""
    (root / "tools").mkdir(parents=True, exist_ok=True)
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


def write_tool(root: Path) -> None:
    """Write one indexed tool file."""
    (root / "tools" / "dependency_graph.py").write_text(
        "\n".join(
            [
                "# @dependency-start",
                "# responsibility Validates dependency graph edit scope.",
                "# upstream design ../documents/dependency-graph.md dependency graph policy",
                "# downstream implementation ../tests/test_dependency_graph.py regression tests",
                "# @dependency-end",
                "def check_dependency_graph():",
                "    return 'graph scope'",
            ]
        ),
        encoding="utf-8",
    )


def run_index(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run search_index.py against a temporary root."""
    return subprocess.run(
        [sys.executable, str(SEARCH_INDEX), *args, "--root", str(root)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class SearchIndexTest(unittest.TestCase):
    """Verify search-card generation."""

    def test_build_writes_tool_card_and_state(self) -> None:
        """Build should persist ignored repo-local card and state files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_tool_registry(root)
            write_tool(root)

            result = run_index(root, "build", "--surface", "tools", "--format", "json")

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "pass")
            card_file = root / ".agent-canon" / "search-index" / "llm-cards.jsonl"
            state_file = root / ".agent-canon" / "search-index" / "index-state.json"
            self.assertTrue(card_file.is_file())
            self.assertTrue(state_file.is_file())
            cards = [json.loads(line) for line in card_file.read_text(encoding="utf-8").splitlines()]
            tool_cards = [card for card in cards if card["path"] == "tools/dependency_graph.py"]
            self.assertEqual(tool_cards[0]["kind"], "tool")
            self.assertEqual(tool_cards[0]["related_tools"], ["dependency-graph"])

    def test_required_llm_missing_fails_before_index_write(self) -> None:
        """A required unavailable local LLM must fail explicitly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            write_tool_registry(root)
            write_tool(root)

            result = run_index(
                root,
                "build",
                "--surface",
                "tools",
                "--run-llm",
                "--require-llm",
                "--llama-cli",
                str(root / "missing-llama-cli"),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("SEARCH_INDEX_ERROR=llama-cli-not-found", result.stderr)
            self.assertFalse((root / ".agent-canon" / "search-index" / "llm-cards.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
