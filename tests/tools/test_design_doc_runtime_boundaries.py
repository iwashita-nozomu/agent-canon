# @dependency-start
# contract test
# responsibility Verifies design-document analyzers keep reports external and source mutation explicit.
# upstream implementation ../../tools/docs/_runtime_output.py shared runtime/mutation boundary
# upstream implementation ../../tools/docs/find_redundant_designs.py exact duplicate analyzer
# upstream implementation ../../tools/docs/find_similar_designs.py similarity analyzer
# upstream implementation ../../tools/docs/organize_designs.py organization planner
# downstream implementation ../../tests/agent_tools/test_source_runtime_side_effects.py source side-effect regression suite
# @dependency-end
"""Regression tests for external design-document reports."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = {
    "redundant": PROJECT_ROOT / "tools/docs/find_redundant_designs.py",
    "similar": PROJECT_ROOT / "tools/docs/find_similar_designs.py",
    "organize": PROJECT_ROOT / "tools/docs/organize_designs.py",
}


class DesignDocumentRuntimeBoundaryTest(unittest.TestCase):
    """Ensure read-only tools cannot create source-local reports."""

    def write(self, path: Path, text: str) -> None:
        """Write one fixture file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_tool(
        self,
        script: Path,
        source: Path,
        runtime: Path | None,
        *extra: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run one analyzer with a clean environment."""
        command = ["python3", str(script), *extra]
        if runtime is not None:
            command.extend(["--runtime-root", str(runtime)])
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        environment.pop("AGENT_CANON_RUNTIME_ROOT", None)
        return subprocess.run(
            command,
            cwd=source,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_all_analyzers_require_external_runtime_root(self) -> None:
        """Missing runtime capability fails before opening a source report."""
        with tempfile.TemporaryDirectory() as source_dir:
            source = Path(source_dir)
            self.write(source / "documents/design/a.md", "# A\n")
            for script in SCRIPTS.values():
                result = self.run_tool(script, source, None)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("explicit runtime root required", result.stderr)
            self.assertFalse((source / "reports").exists())

    def test_read_only_reports_are_external_and_source_is_unchanged(self) -> None:
        """External runtime output is used by all three read-only analyzers."""
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as runtime_dir:
            source = Path(source_dir)
            runtime = Path(runtime_dir)
            self.write(source / "documents/design/a.md", "# Shared\n`foo/bar.py`\n")
            self.write(source / "documents/design/b.md", "# Shared\n`foo/bar.py`\n")
            self.write(source / "documents/design/c.md", "# Other\n")
            before = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
            for script in SCRIPTS.values():
                result = self.run_tool(script, source, runtime)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(str(runtime), result.stdout)
            after = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertFalse((source / "reports").exists())
            self.assertTrue(tuple(runtime.rglob("*.txt")))

    def test_organize_apply_requires_capability(self) -> None:
        """The organization planner cannot mutate source implicitly."""
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as runtime_dir:
            source = Path(source_dir)
            self.write(source / "documents/design/a.md", "# A\n`foo/bar.py`\n")
            result = self.run_tool(
                SCRIPTS["organize"],
                source,
                Path(runtime_dir),
                "--apply",
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("mutation capability", result.stderr)
            self.assertFalse((source / "documents/design/foo/a.md").exists())

    def test_redundant_delete_requires_runtime_before_source_mutation(self) -> None:
        """A missing output capability cannot cause a source deletion."""
        with tempfile.TemporaryDirectory() as source_dir:
            source = Path(source_dir)
            self.write(source / "documents/design/a.md", "# Same\n")
            duplicate = source / "documents/design/b.md"
            self.write(duplicate, "# Same\n")
            capability = (
                '{"allowed_paths":["documents/design/b.md"],'
                '"purpose":"test","authority":"issue-841"}'
            )
            result = self.run_tool(
                SCRIPTS["redundant"],
                source,
                None,
                "--delete",
                "--mutation-capability-json",
                capability,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertTrue(duplicate.exists())

    def test_organize_apply_requires_runtime_before_source_mutation(self) -> None:
        """A valid mutation grant is not enough without external report output."""
        with tempfile.TemporaryDirectory() as source_dir:
            source = Path(source_dir)
            self.write(source / "documents/design/a.md", "# A\n`foo/bar.py`\n")
            capability = (
                '{"allowed_paths":["documents/design/foo/a.md"],'
                '"purpose":"test","authority":"issue-841"}'
            )
            result = self.run_tool(
                SCRIPTS["organize"],
                source,
                None,
                "--apply",
                "--mutation-capability-json",
                capability,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse((source / "documents/design/foo/a.md").exists())


if __name__ == "__main__":
    unittest.main()
