# @dependency-start
# responsibility Tests algorithm module public surface checker behavior.
# upstream implementation ../../tools/agent_tools/check_algorithm_module_public_surface.py checker
# upstream design ../../documents/tools/README.md algorithm module surface checker
# @dependency-end
"""Tests for the algorithm module public surface checker."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    PROJECT_ROOT / "tools" / "agent_tools" / "check_algorithm_module_public_surface.py"
)

STANDARD_MODULE_SOURCE = "\n".join(
    [
        "from jax_util.base import algorithm_module_protocol as amp",
        "",
        "class InitializeConfig(amp.InitializeConfig):",
        "    pass",
        "",
        "class SolveConfig(amp.SolveConfig):",
        "    pass",
        "",
        "class Problem(amp.Problem):",
        "    pass",
        "",
        "class State(amp.State):",
        "    pass",
        "",
        "class Answer(amp.Answer):",
        "    pass",
        "",
        "class Info(amp.Info):",
        "    pass",
        "",
        "class Algorithm(amp.Algorithm):",
        "    pass",
        "",
        "def initialize(config: InitializeConfig) -> tuple[Algorithm, State]:",
        "    return Algorithm(), State()",
        "",
        "__all__ = [",
        '    "InitializeConfig",',
        '    "SolveConfig",',
        '    "Problem",',
        '    "State",',
        '    "Answer",',
        '    "Info",',
        '    "Algorithm",',
        '    "initialize",',
        "]",
        "",
    ]
)


class AlgorithmModulePublicSurfaceTest(unittest.TestCase):
    """Verify algorithm module public surface checking."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the public surface checker."""
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_standard_algorithm_module_passes(self) -> None:
        """A module with exactly the standard public names passes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "pcg.py"
            source.write_text(STANDARD_MODULE_SOURCE, encoding="utf-8")

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ALGORITHM_PUBLIC_SURFACE_MODULES=1", result.stdout)
            self.assertIn("ALGORITHM_PUBLIC_SURFACE=pass", result.stdout)

    def test_extra_all_name_fails(self) -> None:
        """An extra ``__all__`` name is rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "pcg.py"
            source.write_text(
                STANDARD_MODULE_SOURCE.replace(
                    '    "initialize",\n]',
                    '    "initialize",\n    "solve",\n]',
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("extra_all:solve", result.stdout)

    def test_extra_public_definition_fails(self) -> None:
        """A top-level public helper definition is rejected even outside ``__all__``."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "pcg.py"
            source.write_text(
                STANDARD_MODULE_SOURCE + "\ndef solve() -> None:\n    return None\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("extra_public_definition:solve", result.stdout)

    def test_missing_all_fails(self) -> None:
        """Algorithm modules must pin public names through literal ``__all__``."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "pcg.py"
            source.write_text(
                STANDARD_MODULE_SOURCE.split("__all__ = [", maxsplit=1)[0],
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_all:__all__", result.stdout)

    def test_non_algorithm_protocol_import_fails(self) -> None:
        """Production protocol imports must expose the standard algorithm surface."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "helper.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class _State(amp.State):",
                        "    pass",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non_algorithm_protocol_import", result.stdout)

    def test_allowlisted_test_protocol_import_is_ignored(self) -> None:
        """Test files can import the base protocol without becoming algorithm modules."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            test_dir = root / "python" / "tests" / "base"
            test_dir.mkdir(parents=True)
            source = test_dir / "test_protocol.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class _State(amp.State):",
                        "    pass",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ALGORITHM_PUBLIC_SURFACE_MODULES=0", result.stdout)

    def test_json_output_reports_modules_and_findings(self) -> None:
        """JSON output is deterministic for automation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "pcg.py"
            source.write_text(STANDARD_MODULE_SOURCE, encoding="utf-8")

            result = self.run_checker(root, "--format", "json", str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["algorithm_modules"], 1)
            self.assertEqual(payload["summary"]["status"], "pass")
            self.assertEqual(payload["findings"], [])


if __name__ == "__main__":
    unittest.main()
