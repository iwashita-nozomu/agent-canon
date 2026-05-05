"""Tests for the AgentCanon vector search helper."""

# @dependency-start
# responsibility Tests dependency-free vector search behavior.
# upstream implementation ../../tools/agent_tools/vector_search.py vector search CLI
# upstream design ../../documents/tools/README.md tool search policy
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "vector_search.py"


def run_search(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run vector_search.py inside a temporary repository root."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class VectorSearchTest(unittest.TestCase):
    """Exercise the vector-search CLI through realistic temporary surfaces."""

    def test_finds_tool_surface_by_query_terms(self) -> None:
        """A query should rank the matching tool file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "tools" / "agent_tools" / "check_mcp_inventory.py"
            target.parent.mkdir(parents=True)
            target.write_text(
                "MCP inventory checker validates configured repo_mcp_server command.\n",
                encoding="utf-8",
            )
            other = root / "documents" / "notes.md"
            other.parent.mkdir(parents=True)
            other.write_text("Notebook environment setup and unrelated prose.\n", encoding="utf-8")

            result = run_search(root, "--query", "configured mcp inventory command")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("VECTOR_SEARCH=pass", result.stdout)
            self.assertIn("tools/agent_tools/check_mcp_inventory.py", result.stdout)

    def test_surface_option_limits_index(self) -> None:
        """The surface option should keep searches scoped to requested roots."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tool = root / "tools" / "docker_dependency_validator.sh"
            tool.parent.mkdir(parents=True)
            tool.write_text("GitHub CLI gh validation for container tooling.\n", encoding="utf-8")
            doc = root / "documents" / "github.md"
            doc.parent.mkdir(parents=True)
            doc.write_text("GitHub remote policy for prose documentation.\n", encoding="utf-8")

            result = run_search(root, "--surface", "tools", "--query", "github remote policy")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("tools/docker_dependency_validator.sh", result.stdout)
            self.assertNotIn("documents/github.md", result.stdout)

    def test_symlinked_surface_is_indexed(self) -> None:
        """Template root symlink views should be indexed through the root path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "vendor" / "agent-canon" / "tools" / "agent_tools"
            target.mkdir(parents=True)
            (target / "vector_search.py").write_text(
                "AgentCanon directory link vector search helper.\n",
                encoding="utf-8",
            )
            (root / "tools").symlink_to(root / "vendor" / "agent-canon" / "tools")

            result = run_search(root, "--surface", "tools", "--query", "directory link vector")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("tools/agent_tools/vector_search.py", result.stdout)

    def test_json_output_is_machine_readable(self) -> None:
        """JSON output should expose indexed file count and hits."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            doc = root / "documents" / "dependency.md"
            doc.parent.mkdir(parents=True)
            doc.write_text(
                "Dependency graph header validation and scan workflow.\n",
                encoding="utf-8",
            )

            result = run_search(
                root,
                "--query",
                "dependency graph validation",
                "--format",
                "json",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["indexed_files"], 1)
            self.assertEqual(payload["hits"][0]["path"], "documents/dependency.md")


if __name__ == "__main__":
    unittest.main()
