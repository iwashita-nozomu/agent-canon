"""Tests for dependency-free vector search."""

# @dependency-start
# responsibility Tests vector search indexing exclusions.
# upstream implementation ../../tools/agent_tools/vector_search.py searches text surfaces
# upstream design ../../tools/README.md documents vector search usage
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VECTOR_SEARCH = PROJECT_ROOT / "tools" / "agent_tools" / "vector_search.py"


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


if __name__ == "__main__":
    unittest.main()
