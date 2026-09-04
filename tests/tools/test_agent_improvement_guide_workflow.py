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

    def test_pr_candidate_clones_main_and_installs_runtime(self) -> None:
        """PR candidates install from a local main clone before execution."""
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            'candidate_bare="${RUNNER_TEMP}/agent-canon-pr-candidate.git"',
            text,
        )
        self.assertIn(
            'candidate_source="${RUNNER_TEMP}/agent-canon-pr-candidate"',
            text,
        )
        self.assertIn(
            'git -C "${GITHUB_WORKSPACE}" push "${candidate_bare}" "HEAD:refs/heads/main"',
            text,
        )
        self.assertIn(
            'git --git-dir="${candidate_bare}" symbolic-ref HEAD refs/heads/main',
            text,
        )
        self.assertIn(
            'git clone --branch main --single-branch "${candidate_bare}" "${candidate_source}"',
            text,
        )
        self.assertIn(
            "printf 'AGENT_CANON_CANDIDATE_SOURCE=%s",
            text,
        )
        self.assertIn(
            '"${candidate_source}" >> "${GITHUB_ENV}"',
            text,
        )
        self.assertIn("printf 'AGENT_CANON_CANDIDATE_BARE=%s", text)
        self.assertNotIn("AGENT_CANON_GUIDE_RUNTIME_ROOT", text)
        self.assertNotIn("AGENT_CANON_RUNTIME_ROOT", text)
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
        self.assertTrue(
            all("--runtime-root" not in line for line in bootstrap_lines)
        )
        self.assertTrue(any(line.endswith(" install") for line in bootstrap_lines))
        self.assertFalse(any(line.endswith(" update") for line in bootstrap_lines))
        self.assertTrue(any(line.endswith(" start") for line in bootstrap_lines))
        self.assertTrue(any(" target add " in line for line in bootstrap_lines))
        self.assertIn(
            'tool run --root "${GITHUB_WORKSPACE}" generate-agent-improvement-guide --',
            text,
        )
        self.assertNotIn("exec --root", text)
        self.assertIn(
            "--root . --runtime-root /var/lib/agent-canon/runtime",
            text,
        )
        self.assertIn(
            'guide_dir="${AGENT_CANON_CONTROL_PARENT_ROOT}/agent-improvement-guide"',
            text,
        )
        self.assertIn(
            'tool export guide --destination "${guide_dir}"',
            text,
        )
        self.assertNotIn("Setup Python", text)
        self.assertIn(
            'cat "${guide_path}" >> "${GITHUB_STEP_SUMMARY}"',
            text,
        )
        self.assertIn(
            '"${AGENT_CANON_CONTROL_PARENT_ROOT}/agent-improvement-guide"',
            text,
        )
        self.assertNotIn(".runtime/container-state", text)
        self.assertNotIn("docker ", text)

    def test_main_only_runtime_workflows_keep_install_contract(self) -> None:
        """Main-only runtime workflows retain their strict initial install."""
        for name in ("agent-canon-static-gates.yml", "agent-runtime-dashboard.yml"):
            text = (WORKFLOW.parent / name).read_text(encoding="utf-8")
            bootstrap_lines = [
                line.strip()
                for line in text.splitlines()
                if line.strip().startswith("./bootstrap.sh")
            ]
            self.assertTrue(any(line.endswith(" install") for line in bootstrap_lines), name)


if __name__ == "__main__":
    unittest.main()
