"""Tests for intermediate waterfall gate checks."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "bootstrap_agent_run.py"
GATE_CHECK_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "waterfall_gate_check.py"


class WaterfallGateCheckTest(unittest.TestCase):
    """Verify that intermediate waterfall gates fail closed."""

    def test_design_gate_rejects_fresh_template_bundle(self) -> None:
        """A fresh bundle should not pass design gate without filled reviews."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            report_dir = report_root / "fresh-bundle"
            subprocess.run(
                [
                    sys.executable,
                    str(BOOTSTRAP_SCRIPT),
                    "--task",
                    "waterfall gate smoke",
                    "--owner",
                    "codex",
                    "--run-id",
                    "fresh-bundle",
                    "--workspace-root",
                    str(PROJECT_ROOT),
                    "--report-root",
                    str(report_root),
                ],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "design",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WATERFALL_GATE_READY=no", result.stdout)
            self.assertIn("design_review.md:decision_not_approve", result.stdout)

    def test_design_gate_accepts_filled_approved_artifacts(self) -> None:
        """A filled design bundle should pass when both design reviews approve."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir) / "reports" / "filled"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "design_brief.md").write_text(
                "\n".join(
                    [
                        "# Detailed Design Brief",
                        "",
                        "## Goals",
                        "Implement the approved small change.",
                        "## Existing Code And Docs To Reuse",
                        "Mirror `tools/agent_tools/task_close.py`.",
                        "## Identifier And Naming Plan",
                        "Use `waterfall_gate_check.py` after the existing task tool names.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "design_review.md").write_text(
                "\n".join(
                    [
                        "# Detailed Design Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (report_dir / "document_flow_review.md").write_text(
                "\n".join(
                    [
                        "# Document Flow Review",
                        "",
                        "## Findings",
                        "No blockers.",
                        "## Decision",
                        "approve",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(GATE_CHECK_SCRIPT),
                    "--report-dir",
                    str(report_dir),
                    "--gate",
                    "design",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("WATERFALL_GATE_READY=yes", result.stdout)
            self.assertIn("NEXT_ACTION=proceed_to_next_waterfall_gate", result.stdout)


if __name__ == "__main__":
    unittest.main()
