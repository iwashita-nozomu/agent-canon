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

    def test_pr_checkout_preserves_full_history_and_guide_mode(self) -> None:
        """PR candidate staging retains history and the guide export mode."""
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "fetch-depth: ${{ github.event_name == 'pull_request' && '0' || '1' }}",
            text,
        )
        self.assertNotIn('mkdir -p "${report_dir}"', text)
        self.assertIn("--output-mode 644", text)

    def test_candidate_runtime_and_cleanup_remain_source_isolated(self) -> None:
        """Runtime setup and cleanup must operate on the staged PR candidate."""
        text = WORKFLOW.read_text(encoding="utf-8")
        bootstrap_lines = [
            line.strip() for line in text.splitlines() if "bootstrap.sh" in line
        ]
        self.assertTrue(bootstrap_lines)
        self.assertTrue(
            all(
                line.startswith('"${AGENT_CANON_CANDIDATE_SOURCE}/bootstrap.sh"')
                for line in bootstrap_lines
            )
        )
        self.assertFalse(
            any(line.startswith("./bootstrap.sh") for line in bootstrap_lines)
        )
        self.assertTrue(any(line.endswith(" install") for line in bootstrap_lines))
        self.assertFalse(any(line.endswith(" update") for line in bootstrap_lines))
        self.assertTrue(any(line.endswith(" start") for line in bootstrap_lines))
        self.assertTrue(any(" target add " in line for line in bootstrap_lines))
        self.assertFalse(any("--runtime-root" in line for line in bootstrap_lines))
        self.assertIn(
            'rm -rf -- "${AGENT_CANON_CANDIDATE_BARE:-}" '
            '"${AGENT_CANON_CANDIDATE_SOURCE:-}"',
            text,
        )


if __name__ == "__main__":
    unittest.main()
