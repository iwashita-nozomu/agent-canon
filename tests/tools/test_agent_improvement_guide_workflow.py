# @dependency-start
# contract test
# responsibility Tests Agent Improvement Guide workflow trigger boundaries.
# upstream implementation ../../.github/workflows/agent-improvement-guide.yml selected diagnostic workflow
# @dependency-end

"""Tests for the Agent Improvement Guide workflow trigger surface."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "agent-improvement-guide.yml"


class AgentImprovementGuideWorkflowTest(unittest.TestCase):
    """Keep guide generation off broad ordinary pull requests."""

    def test_pr_trigger_is_limited_and_manual_dispatch_remains(self) -> None:
        """Only the guide generator surface may trigger PR diagnostics."""
        workflow = yaml.load(
            WORKFLOW.read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        triggers = workflow["on"]

        self.assertEqual(
            triggers["pull_request"]["paths"],
            [
                ".github/workflows/agent-improvement-guide.yml",
                "eval/producers/generate_agent_improvement_guide.py",
                "tests/agent_tools/test_generate_agent_improvement_guide.py",
            ],
        )
        self.assertIn("workflow_dispatch", triggers)
        self.assertNotIn("push", triggers)

    def test_pr_checkout_selects_local_runtime_image_build(self) -> None:
        """PR guide runs must not select an unpublished GHCR merge tag."""
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "fetch-depth: ${{ github.event_name == 'pull_request' && '0' || '1' }}",
            text,
        )
        self.assertNotIn('mkdir -p "${report_dir}"', text)
        self.assertIn("--output-mode 644", text)


if __name__ == "__main__":
    unittest.main()
