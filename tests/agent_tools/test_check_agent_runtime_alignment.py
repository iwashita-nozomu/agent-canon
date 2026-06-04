# @dependency-start
# responsibility Tests test check agent runtime alignment behavior.
# upstream design ../../tools/README.md validated automation surface
# @dependency-end

"""Integration test for the agent runtime alignment checker."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "agent_tools" / "check_agent_runtime_alignment.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from agent_team import (  # noqa: E402
    load_team_config,
    resolve_cross_cutting_document_packet,
    resolve_role,
    resolve_role_document_packet,
)
from check_agent_runtime_alignment import validate_permanent_team_mapping  # noqa: E402


class AgentRuntimeAlignmentTest(unittest.TestCase):
    """Verify that the runtime alignment checker passes on the checked-in canon."""

    def test_alignment_script_passes(self) -> None:
        """The runtime alignment checker should succeed without findings."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("AGENT_RUNTIME_ALIGNMENT=pass", result.stdout)

    def test_permanent_team_mapping_requires_every_configured_role(self) -> None:
        """The CODEX_SUBAGENTS mapping should not omit configured team roles."""
        config = load_team_config()
        subagents_path = PROJECT_ROOT / "agents" / "canonical" / "CODEX_SUBAGENTS.md"
        text = subagents_path.read_text(encoding="utf-8")
        text_without_verifier = text.replace("| `verifier` | parent validation runner |\n", "")

        with self.assertRaisesRegex(
            RuntimeError,
            "permanent-team mapping missing roles: verifier",
        ):
            validate_permanent_team_mapping(config, text_without_verifier)

    def test_template_workspace_can_use_agent_canon_shared_docs(self) -> None:
        """Derived workspaces need not expose shared AgentCanon docs at root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace_root = Path(tmp_dir)
            entries = resolve_cross_cutting_document_packet(workspace_root)
            review_process = (PROJECT_ROOT / "documents" / "REVIEW_PROCESS.md").resolve()

            self.assertIn(review_process, {entry.path for entry in entries})
            self.assertTrue(all(entry.path.exists() for entry in entries))

            config = load_team_config()
            role = resolve_role(config, "design_reviewer")
            packet = resolve_role_document_packet(
                config=config,
                role=role,
                report_dir=workspace_root / "reports" / "agents" / "_packet_probe",
                workspace_root=workspace_root,
            )
            non_artifact_paths = {
                entry.path for entry in packet.read_before_work if not entry.rationale.startswith("run artifact:")
            }

            self.assertIn(review_process, non_artifact_paths)
            self.assertTrue(all(path.exists() for path in non_artifact_paths))


if __name__ == "__main__":
    unittest.main()
