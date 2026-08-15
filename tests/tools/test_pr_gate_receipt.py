"""Unit tests for the source-owned PR dependency gate receipt."""

# @dependency-start
# contract test
# responsibility Verifies the source/skipped receipt schema and identity bindings.
# upstream implementation ../../tools/ci/pr_gate_receipt.py owns receipt parsing and serialization
# upstream design ../../documents/design/source-owned-dependency-validation.md owns receipt meaning
# downstream implementation ../../tools/ci/check_agent_canon_pr.sh writes receipts
# downstream implementation ../../tools/ci/run_all_checks.sh consumes receipts
# @dependency-end

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.ci.pr_gate_receipt import (
    ReceiptError,
    parse_receipt,
    serialize_receipt,
    validate_receipt,
)


class PrGateReceiptTest(unittest.TestCase):
    """Exercise the complete parser contract without shell re-parsing."""

    def receipt(self, root: str, status: str = "source", pid: int = 4312) -> str:
        """Build a valid fixture receipt."""
        return serialize_receipt(
            root=root,
            parent_pid=pid,
            status=status,
            selector_reason="tracked_source_validated",
            selector_evidence="base=" + "a" * 40,
        )

    def test_source_and_skipped_are_the_only_accepted_statuses(self) -> None:
        """Accept both source-owned statuses."""
        with tempfile.TemporaryDirectory() as temporary:
            for status in ("source", "skipped"):
                text = self.receipt(temporary, status=status)
                parsed = validate_receipt(text, expected_root=temporary, expected_parent_pid=4312)
                self.assertEqual(parsed.status.value, status)

    def test_prepared_scoped_and_unknown_statuses_are_rejected(self) -> None:
        """Reject retired and unknown status values."""
        with tempfile.TemporaryDirectory() as temporary:
            for status in ("prepared", "scoped", "unknown"):
                with self.subTest(status=status):
                    with self.assertRaises(ReceiptError):
                        self.receipt(temporary, status=status)

    def test_status_fields_must_match(self) -> None:
        """Reject mismatched compatibility status fields."""
        with tempfile.TemporaryDirectory() as temporary:
            lines = self.receipt(temporary).splitlines()
            lines[4] = "graph=skipped"
            with self.assertRaisesRegex(ReceiptError, "statuses differ"):
                parse_receipt("\n".join(lines) + "\n")

    def test_malformed_duplicate_and_multiline_fields_fail_closed(self) -> None:
        """Reject malformed, duplicate, and multiline records."""
        with tempfile.TemporaryDirectory() as temporary:
            text = self.receipt(temporary)
            with self.assertRaises(ReceiptError):
                parse_receipt(text.replace("selector_reason=tracked_source_validated\n", ""))
            with self.assertRaises(ReceiptError):
                parse_receipt(text + "graph=source\n")
            with self.assertRaises(ReceiptError):
                parse_receipt(text.replace("selector_evidence=", "selector_evidence=bad\nextra="))

    def test_root_and_parent_bindings_are_checked(self) -> None:
        """Reject records bound to another root or process."""
        with tempfile.TemporaryDirectory() as temporary:
            text = self.receipt(temporary)
            with self.assertRaises(ReceiptError):
                validate_receipt(text, expected_root=str(Path(temporary).parent), expected_parent_pid=4312)
            with self.assertRaises(ReceiptError):
                validate_receipt(text, expected_root=temporary, expected_parent_pid=4313)


if __name__ == "__main__":
    unittest.main()
