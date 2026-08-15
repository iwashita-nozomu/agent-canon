"""Executable writer/parser/consumer checks for the PR gate receipt."""

# @dependency-start
# contract test
# responsibility Verifies the live source receipt writer and consumer handoff.
# upstream implementation ../../tools/ci/check_agent_canon_pr.sh owns receipt production
# upstream implementation ../../tools/ci/pr_gate_receipt.py owns receipt serialization and parsing
# downstream implementation ../../tools/ci/run_all_checks.sh consumes one validated status
# downstream design ../../documents/design/source-owned-dependency-validation.md owns source/runtime separation
# @dependency-end

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RECEIPT_TOOL = PROJECT_ROOT / "tools" / "ci" / "pr_gate_receipt.py"
PR_CHECK = PROJECT_ROOT / "tools" / "ci" / "check_agent_canon_pr.sh"
RUN_ALL_CHECKS = PROJECT_ROOT / "tools" / "ci" / "run_all_checks.sh"


class PrGateReceiptRoundTripTest(unittest.TestCase):
    """Keep the producer/parser/consumer boundary executable and one-way."""

    def run_writer(self, root: Path, status: str) -> subprocess.CompletedProcess[str]:
        """Execute the production receipt writer CLI."""
        return subprocess.run(
            [
                sys.executable,
                str(RECEIPT_TOOL),
                "write",
                "--root",
                str(root),
                "--parent-pid",
                str(os.getpid()),
                "--status",
                status,
                "--selector-reason",
                "tracked_source_validated",
                "--selector-evidence",
                "base=" + "a" * 40,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_source_and_skipped_live_receipts_reach_consumer(self) -> None:
        """Pass each live writer output through the consumer validator."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for status in ("source", "skipped"):
                with self.subTest(status=status):
                    written = self.run_writer(root, status)
                    self.assertEqual(written.returncode, 0, written.stderr)
                    receipt = root / f"{status}.receipt"
                    receipt.write_text(written.stdout, encoding="utf-8")
                    consumed = subprocess.run(
                        [
                            sys.executable,
                            str(RECEIPT_TOOL),
                            "validate",
                            "--receipt",
                            str(receipt),
                            "--root",
                            str(root),
                            "--parent-pid",
                            str(os.getpid()),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(consumed.returncode, 0, consumed.stderr)
                    self.assertEqual(consumed.stdout, f"status={status}\n")

    def test_retired_states_fail_at_writer_and_consumer_boundaries(self) -> None:
        """Fail closed for retired states at both executable boundaries."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for status in ("prepared", "scoped"):
                with self.subTest(status=status):
                    written = self.run_writer(root, status)
                    self.assertNotEqual(written.returncode, 0)
                    valid = self.run_writer(root, "source")
                    receipt = root / "receipt"
                    receipt.write_text(valid.stdout.replace("strict_dependency=source", f"strict_dependency={status}").replace("graph=source", f"graph={status}"), encoding="utf-8")
                    consumed = subprocess.run(
                        [
                            sys.executable,
                            str(RECEIPT_TOOL),
                            "validate",
                            "--receipt",
                            str(receipt),
                            "--root",
                            str(root),
                            "--parent-pid",
                            str(os.getpid()),
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(consumed.returncode, 0)

    def test_shell_writer_and_consumer_delegate_to_one_parser(self) -> None:
        """Keep shell producer and consumer delegated to one parser."""
        producer = PR_CHECK.read_text(encoding="utf-8")
        consumer = RUN_ALL_CHECKS.read_text(encoding="utf-8")
        self.assertIn('pr_gate_receipt.py" write', producer)
        self.assertIn('pr_gate_receipt.py" validate', consumer)
        self.assertNotIn('strict_dependency_status="$(awk', consumer)
        self.assertNotIn('graph_status="$(awk', consumer)
        self.assertIn("validated_source_receipt_consumed", consumer)
        self.assertNotIn('PR_GATE_DEPENDENCY_GRAPH_STATUS="', consumer)


if __name__ == "__main__":
    unittest.main()
