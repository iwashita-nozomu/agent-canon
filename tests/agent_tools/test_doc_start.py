# @dependency-start
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Tests for machine-driven document start bootstrap."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOC_START_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "doc_start.py"


class DocStartTest(unittest.TestCase):
    """Verify machine-driven writing bootstrap behavior."""

    def test_doc_start_long_form(self) -> None:
        """Long-form doc start should emit the long-form skill and base review roles."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            workspace_root = Path(tmp_dir) / "workspace"
            report_root.mkdir(parents=True, exist_ok=True)
            workspace_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(DOC_START_SCRIPT),
                    "--task",
                    "workflow guide rewrite",
                    "--kind",
                    "long-form",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-doc-start-long-form",
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(workspace_root),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DOC_KIND=long-form", result.stdout)
            self.assertIn(
                "SUGGESTED_SKILLS=$agent-orchestration,$codex-task-workflow,$subagent-bootstrap,$long-form-writing",
                result.stdout,
            )
            self.assertIn(
                "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                result.stdout,
            )
            self.assertIn("START_DECLARATION=workflow=Scoped Change", result.stdout)
            self.assertIn("document_flow_reviewer", result.stdout)
            manifest_text = (
                report_root / "test-doc-start-long-form" / "team_manifest.yaml"
            ).read_text(
                encoding="utf-8",
            )
            self.assertIn("subagent_prompt_packet:", manifest_text)
            self.assertIn("prompt_contract:", manifest_text)

    def test_doc_start_paper(self) -> None:
        """Paper doc start should enable citation, notation, and logic reviewers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_root = Path(tmp_dir) / "reports"
            workspace_root = Path(tmp_dir) / "workspace"
            report_root.mkdir(parents=True, exist_ok=True)
            workspace_root.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(DOC_START_SCRIPT),
                    "--task",
                    "paper draft bootstrap",
                    "--kind",
                    "paper",
                    "--owner",
                    "codex",
                    "--run-id",
                    "test-doc-start-paper",
                    "--report-root",
                    str(report_root),
                    "--workspace-root",
                    str(workspace_root),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            report_dir = report_root / "test-doc-start-paper"

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DOC_KIND=paper", result.stdout)
            self.assertIn(
                "SUGGESTED_SKILLS=$agent-orchestration,$codex-task-workflow,$subagent-bootstrap,$paper-writing",
                result.stdout,
            )
            self.assertIn(
                "WORKFLOW_SUBAGENT_PROMPT_PACKET=team_manifest.yaml#run.subagent_prompt_packet",
                result.stdout,
            )
            self.assertIn("citation_evidence_reviewer", result.stdout)
            self.assertIn("notation_definition_reviewer", result.stdout)
            self.assertIn("logic_gap_reviewer", result.stdout)
            self.assertTrue((report_dir / "citation_evidence_review.md").is_file())
            self.assertTrue((report_dir / "notation_definition_review.md").is_file())
            self.assertTrue((report_dir / "logic_gap_review.md").is_file())
            manifest_text = (report_dir / "team_manifest.yaml").read_text(encoding="utf-8")
            self.assertIn("subagent_prompt_packet:", manifest_text)
            self.assertIn("prompt_contract:", manifest_text)


if __name__ == "__main__":
    unittest.main()
