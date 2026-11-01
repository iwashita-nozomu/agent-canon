"""Tests the native read-only historical skill-usage boundary."""

# @dependency-start
# contract test
# responsibility Tests native historical skill-usage parsing without writing archived input.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/historical_skill_usage.rs owns historical parsing
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/main.rs exposes the read-only command
# upstream reference ../fixtures/historical_skill_usage/python_golden.json freezes the old reader contract
# @dependency-end

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLDEN = json.loads(
    (
        PROJECT_ROOT
        / "tests"
        / "fixtures"
        / "historical_skill_usage"
        / "python_golden.json"
    ).read_text(encoding="utf-8")
)


def native_cli() -> str:
    for name in ("AGENT_CANON_CLI", "AGENT_CANON_CLI_CMD", "AGENT_CANON_NATIVE_BIN"):
        selected = os.environ.get(name, "").strip()
        if selected:
            return selected
    executable = shutil.which("agent-canon")
    if executable:
        return executable
    return str(PROJECT_ROOT / "tools" / "bin" / "agent-canon")


class HistoricalSkillUsageReaderTest(unittest.TestCase):
    def test_old_python_readback_cases_match_native_cli(self) -> None:
        """The native boundary preserves the frozen bytes, counts, reasons, and records."""
        self.assertEqual(
            GOLDEN["source"], "cdf54b674130cd9b058e6848b8fd815b6ea8bfa6"
        )
        self.assertEqual(
            GOLDEN["script_sha256"],
            "daa9a1d1cf9cab68ebc59f742bb3104cc1253e606b785abd0dced93fb0f3f831",
        )
        for case in GOLDEN["cases"]:
            with self.subTest(case=case["name"]), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "skill_usage.jsonl"
                input_base64 = case["input_base64"]
                before: bytes | None = None
                if input_base64 == "directory":
                    path.mkdir()
                elif input_base64 is not None:
                    before = base64.b64decode(input_base64)
                    path.write_bytes(before)

                result = subprocess.run(
                    [
                        native_cli(),
                        "historical-skill-usage-read",
                        "--path",
                        str(path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stderr, "")
                readback = json.loads(result.stdout)
                expected = case["expected"]
                self.assertEqual(set(readback), set(expected))
                self.assertEqual(readback["accepted_count"], expected["accepted_count"])
                self.assertEqual(readback["malformed_count"], expected["malformed_count"])
                self.assertEqual(readback["ignored_count"], expected["ignored_count"])
                self.assertEqual(readback["malformed_by_reason"], expected["malformed_by_reason"])
                self.assertEqual(readback["status"], expected["status"])
                actual_records = readback["records"]
                self.assertEqual(len(actual_records), len(expected["records"]))
                for actual, wanted in zip(actual_records, expected["records"]):
                    self.assertEqual(list(actual), list(wanted))
                    self.assertEqual(
                        json.dumps(actual, sort_keys=True, allow_nan=True),
                        json.dumps(wanted, sort_keys=True, allow_nan=True),
                    )
                if before is not None:
                    self.assertEqual(path.read_bytes(), before)
                elif path.is_dir():
                    self.assertEqual(list(path.iterdir()), [])
                else:
                    self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
