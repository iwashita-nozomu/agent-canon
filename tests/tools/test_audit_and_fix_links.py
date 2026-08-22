# @dependency-start
# contract test
# responsibility Tests the canonical Rust link-check route and explicit source mutation boundary.
# upstream implementation ../../tools/docs/audit_and_fix_links.py link audit compatibility wrapper
# upstream implementation ../../tools/docs/_runtime_output.py mutation capability parser
# downstream implementation ../../rust/agent-canon/src/docs.rs canonical link diagnostics
# @dependency-end
"""Tests for the Markdown link compatibility wrapper."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "docs" / "audit_and_fix_links.py"


def load_module():
    """Load the wrapper as a module without executing its CLI."""
    spec = importlib.util.spec_from_file_location("audit_and_fix_links", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("wrapper module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AuditAndFixLinksTest(unittest.TestCase):
    """Exercise one canonical read-only route and one explicit apply route."""

    def write_file(self, path: Path, contents: str) -> None:
        """Create a fixture file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_check_forwards_to_rust_once_without_report_write(self) -> None:
        """Read-only checks use the Rust CLI and never create source reports."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "README.md", "# Root\n")
            completed = subprocess.CompletedProcess([], 1)
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.object(module.subprocess, "run", return_value=completed) as run:
                    self.assertEqual(module.main(["--check", "README.md"]), 1)
            finally:
                os.chdir(old_cwd)
            command = run.call_args.args[0]
            self.assertEqual(command[1:4], ["docs", "check", "--root"])
            self.assertEqual(command[4], str(root))
            self.assertFalse((root / "reports" / "broken_links.txt").exists())

    def test_container_route_uses_immutable_rust_binary_without_source_output(self) -> None:
        """The bootstrap image route invokes its binary directly and stays read-only."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "README.md", "# Root\n")
            completed = subprocess.CompletedProcess([], 0)
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(module.os.environ, {"AGENT_CANON_EXECUTION_PLANE": "tool-container"}), patch.object(
                    module.subprocess, "run", return_value=completed
                ) as run:
                    self.assertEqual(module.main(["README.md"]), 0)
            finally:
                os.chdir(old_cwd)
            command = run.call_args.args[0]
            self.assertEqual(command[0], "/usr/local/bin/agent-canon")
            self.assertEqual(command[1:4], ["docs", "check", "--root"])
            self.assertFalse((root / "reports").exists())

    def test_apply_requires_mutation_capability_and_preserves_source_on_failure(self) -> None:
        """An apply request without a typed capability fails before writing."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "README.md", "# Root\n")
            self.write_file(root / "docs" / "guide.md", "[root](README.md)\n")
            before = (root / "docs" / "guide.md").read_bytes()
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.object(module, "forward_cli_to_rust") as forward:
                    with self.assertRaises(SystemExit) as error:
                        module.main(["--apply", "docs"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(error.exception.code, 2)
            forward.assert_not_called()
            self.assertEqual((root / "docs" / "guide.md").read_bytes(), before)

    def test_apply_rewrites_only_capability_bound_source_file(self) -> None:
        """The explicit capability permits one source rewrite without a report."""
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(root / "README.md", "# Root\n")
            guide = root / "docs" / "guide.md"
            self.write_file(guide, "[root](README.md)\n")
            capability = '{"allowed_paths":["docs/guide.md"],"purpose":"test","authority":"issue-841"}'
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.object(module, "forward_cli_to_rust") as forward:
                    self.assertEqual(
                        module.main(
                            [
                                "--apply",
                                "--mutation-capability-json",
                                capability,
                                "docs",
                            ]
                        ),
                        0,
                    )
            finally:
                os.chdir(old_cwd)
            forward.assert_not_called()
            self.assertEqual(guide.read_text(encoding="utf-8"), "[root](../README.md)\n")
            self.assertFalse((root / "reports").exists())


if __name__ == "__main__":
    unittest.main()
