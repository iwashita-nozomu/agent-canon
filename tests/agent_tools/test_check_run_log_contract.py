# @dependency-start
# contract test
# responsibility Tests run-log contract checker behavior.
# upstream implementation ../../tools/agent_tools/check_run_log_contract.py checker under test
# @dependency-end
"""Tests for ``check_run_log_contract.py``."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "check_run_log_contract.py"


class CheckRunLogContractTest(unittest.TestCase):
    """Verify run-log contract findings."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a temporary root."""
        return subprocess.run(
            [sys.executable, str(TOOL), "--root", str(root), "--format", "json", *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_auto_info_submit_passes(self) -> None:
        """submit_info without field_names relies on Info auto-resolution."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import RunLog",
                        "def write(context, info):",
                        "    RunLog(solver='solver').submit_info(",
                        "        context,",
                        "        info,",
                        "        source_file='solver.py',",
                        "        func='solve',",
                        "    )",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 0)

    def test_manual_submit_info_field_names_are_flagged(self) -> None:
        """Product submit_info calls should not duplicate Info fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import RunLog",
                        "def write(context, info):",
                        "    RunLog(solver='solver').submit_info(",
                        "        context,",
                        "        info,",
                        "        source_file='solver.py',",
                        "        func='solve',",
                        "        field_names=('res_norm',),",
                        "    )",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 1)
            self.assertEqual(payload["findings"][0]["code"], "manual-info-field-list")

    def test_iteration_submit_without_info_is_flagged(self) -> None:
        """Iteration diagnostics should be emitted from the module Info type."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import RunLog",
                        "def write(context):",
                        "    RunLog(solver='solver').submit_device(",
                        "        context,",
                        "        source_file='solver.py',",
                        "        func='solve',",
                        "        event='iter',",
                        "        residual_norm=1.0,",
                        "    )",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 1)
            self.assertEqual(payload["findings"][0]["code"], "iteration-log-without-info")

    def test_iteration_submit_info_passes(self) -> None:
        """submit_info can emit iteration records from the same Info type."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import RunLog",
                        "def write(context, info):",
                        "    RunLog(solver='solver').submit_info(",
                        "        context,",
                        "        info,",
                        "        source_file='solver.py',",
                        "        func='solve',",
                        "        event='iter',",
                        "    )",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 0)

    def test_direct_writer_import_is_flagged(self) -> None:
        """Low-level run-log writers should not be imported by product code."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import write_info_run_log_event",
                        "def write(context, info):",
                        "    write_info_run_log_event(",
                        "        context, info, field_names=('x',),",
                        "        source_file='solver.py', func='solve',",
                        "    )",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            codes = {finding["code"] for finding in json.loads(result.stdout)["findings"]}
            self.assertIn("direct-run-log-writer-import", codes)
            self.assertIn("direct-run-log-writer-call", codes)

    def test_summary_field_list_constant_is_flagged(self) -> None:
        """Summary field-name constants duplicate amp.Info annotations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text("_KKT_INFO_FIELD_NAMES = {'res_norm': 'res_norm'}\n", encoding="utf-8")

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 1)
            self.assertEqual(payload["findings"][0]["code"], "summary-field-list-constant")

    def test_run_log_internal_module_is_allowed(self) -> None:
        """The base run-log implementation can define low-level helpers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "python" / "jax_util" / "base" / "_run_log.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "def _write_info_run_log_event():\n"
                "    pass\n"
                "def _begin_run_log():\n"
                "    pass\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, "python")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 0)


if __name__ == "__main__":
    unittest.main()
