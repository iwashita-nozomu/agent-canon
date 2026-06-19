"""Tests for issue-derived eval manifest coverage."""

# @dependency-start
# contract test
# responsibility Tests issue-derived eval manifest coverage for AgentCanon closeout issues.
# upstream implementation ../../evidence/agent-evals/issue_eval_manifest.toml registers issue-derived eval rows.
# upstream design ../../documents/prompt-skill-evaluation-checklist.md defines eval closeout expectations.
# downstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates eval accumulation surfaces.
# @dependency-end

from __future__ import annotations

import unittest
from pathlib import Path
from typing import cast

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = PROJECT_ROOT / "evidence" / "agent-evals" / "issue_eval_manifest.toml"
REQUIRED_CLOSEOUT_ISSUES = {
    83,
    97,
    98,
    99,
    100,
    101,
    102,
    103,
    104,
    106,
    114,
    115,
    117,
    118,
    119,
    120,
}


class IssueEvalManifestTest(unittest.TestCase):
    """Validate the issue eval manifest used for closeout evidence."""

    def load_manifest(self) -> dict[str, object]:
        """Load the manifest TOML."""
        return tomllib.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_closeout_issue_set_has_eval_coverage(self) -> None:
        """Every issue in the bulk closeout set has at least one eval row."""
        manifest = self.load_manifest()
        rows = manifest.get("eval")
        self.assertIsInstance(rows, list)
        eval_rows = cast(list[object], rows)
        covered = {
            row.get("source_issue")
            for row in eval_rows
            if isinstance(row, dict) and isinstance(row.get("source_issue"), int)
        }

        self.assertFalse(REQUIRED_CLOSEOUT_ISSUES - covered)

    def test_eval_ids_are_unique(self) -> None:
        """Eval IDs should remain stable unique lookup keys."""
        manifest = self.load_manifest()
        rows = manifest.get("eval")
        self.assertIsInstance(rows, list)
        eval_rows = cast(list[object], rows)
        ids = [row.get("id") for row in eval_rows if isinstance(row, dict)]

        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
