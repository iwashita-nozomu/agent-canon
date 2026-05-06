"""Tests for the explicit Any static-analysis checker."""

# @dependency-start
# responsibility Tests explicit Any static-analysis checker behavior.
# upstream implementation ../../tools/agent_tools/check_static_any.py checker
# upstream design ../../documents/conventions/python/04_type_annotations.md type annotation policy
# @dependency-end

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "check_static_any.py"


class CheckStaticAnyTest(unittest.TestCase):
    """Verify explicit Any checker behavior."""

    def run_checker(self, root: Path, *paths: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a temporary root."""
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), *paths],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_current_repository_passes(self) -> None:
        """The canonical Python source tree does not use explicit Any."""
        result = self.run_checker(PROJECT_ROOT)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STATIC_ANY=pass", result.stdout)
        self.assertIn("STATIC_ANY_FINDINGS=0", result.stdout)

    def test_typing_any_import_fails(self) -> None:
        """Importing typing.Any is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "tools" / "bad.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "from typing import Any\nvalue: Any = 1\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("typing_any_import", result.stdout)
            self.assertIn("any_annotation", result.stdout)
            self.assertIn("STATIC_ANY=fail", result.stdout)

    def test_typing_attribute_any_fails(self) -> None:
        """typing.Any attribute references are rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "python" / "bad.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "import typing\nvalue: typing.Any = 1\n",
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("explicit-typing-Any-attribute", result.stdout)

    def test_string_mentions_do_not_fail(self) -> None:
        """Documentation strings may discuss Any without binding it as a type."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "tests" / "ok.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                'MESSAGE = "Do not use Any in annotations."\n',
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("STATIC_ANY=pass", result.stdout)

    def test_submodule_aware_scope_avoids_symlink_duplicate_findings(self) -> None:
        """Root symlink views and AgentCanon source should not duplicate findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_dir = root / "vendor" / "agent-canon" / "tools"
            source_dir.mkdir(parents=True)
            (root / "tools").symlink_to(source_dir, target_is_directory=True)
            (source_dir / "bad.py").write_text(
                "from typing import Any\nvalue: Any = 1\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECKER),
                    "--root",
                    str(root),
                    "--submodule-aware",
                    "tools",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("STATIC_ANY_FILES=1", result.stdout)
            self.assertEqual(result.stdout.count("typing_any_import"), 1)
            self.assertEqual(result.stdout.count("any_annotation"), 1)


if __name__ == "__main__":
    unittest.main()
