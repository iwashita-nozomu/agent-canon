"""Tests for the hardcoded numeric literal checker."""

# @dependency-start
# responsibility Tests hardcoded numeric literal checker behavior.
# upstream implementation ../../tools/agent_tools/check_hardcoded_numbers.py checker
# upstream design ../../documents/conventions/common/01_principles.md magic-number policy
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "check_hardcoded_numbers.py"


class CheckHardcodedNumbersTest(unittest.TestCase):
    """Verify hardcoded number checker output and allowances."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a temporary root."""
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_python_named_constants_pass(self) -> None:
        """Module-level uppercase constants document otherwise nontrivial values."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "config.py"
            source.write_text(
                "\n".join(
                    [
                        "MAX_RETRIES = 7",
                        "TIMEOUT_SECONDS: float = 3.5",
                        "",
                        "def retry_limit() -> int:",
                        "    return MAX_RETRIES",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("HARDCODED_NUMBERS_FILES=1", result.stdout)
            self.assertIn("HARDCODED_NUMBERS_FINDINGS=0", result.stdout)
            self.assertIn("HARDCODED_NUMBERS=pass", result.stdout)

    def test_python_body_literal_fails(self) -> None:
        """Opaque body literals must become named constants or typed configuration."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "def damping(value: float) -> float:",
                        "    return value * 0.125",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "HARDCODED_NUMBER_FINDING=solver.py:2:python:literal:0.125:damping",
                result.stdout,
            )
            self.assertIn("HARDCODED_NUMBERS=fail", result.stdout)

    def test_python_allow_marker_passes(self) -> None:
        """A line-local allowance can document deliberate literals."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "math_rule.py"
            source.write_text(
                "\n".join(
                    [
                        "def normalize(value: float) -> float:",
                        "    return value / 3.0  # hardcoded-number-ok: domain formula",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cpp_body_literal_fails_but_named_constant_passes(self) -> None:
        """C++ constexpr constants are allowed, while opaque body literals fail."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.hpp"
            source.write_text(
                "\n".join(
                    [
                        "constexpr double MAX_STEP = 4.0;",
                        "double step(double value) {",
                        "  return value * 2.0 + 9.0;",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "HARDCODED_NUMBER_FINDING=solver.hpp:3:cpp:literal:9.0",
                result.stdout,
            )
            self.assertNotIn("literal:4.0", result.stdout)
            self.assertNotIn("literal:2.0", result.stdout)

    def test_json_output_is_machine_readable(self) -> None:
        """JSON output preserves file counts and finding details."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text("def solve() -> float:\n    return 42.0\n", encoding="utf-8")

            result = self.run_checker(root, "--format", "json", str(source))

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["files"], 1)
            self.assertEqual(payload["status"], "fail")
            self.assertEqual(payload["findings"][0]["literal"], "42.0")


if __name__ == "__main__":
    unittest.main()
