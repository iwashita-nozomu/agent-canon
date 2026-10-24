"""Tests for path/risk check matrix classification."""

# @dependency-start
# contract test
# responsibility Tests path-risk classifier smoke routing.
# upstream implementation ../../tools/validation/semantic/path/classify_path_risk.py classifies changed paths.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md defines risk/check routing.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.validation.semantic.path.classify_path_risk import select_static_gate_units

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = (
    PROJECT_ROOT
    / "tools"
    / "validation"
    / "semantic"
    / "path"
    / "classify_path_risk.py"
)


class ClassifyPathRiskTest(unittest.TestCase):
    """Validate representative path-risk profiles."""

    def test_behavior_sources_add_eval_without_retiring_existing_units(self) -> None:
        cases = {
            "agents/skills/example.md": ("docs", "eval"),
            "agents/internal-routines/example.md": ("docs", "eval"),
            "ROOT_AGENTS.md": ("docs", "eval"),
            ".codex/agents/worker.toml": ("contracts", "eval"),
            "agents/agents_config.json": ("contracts", "eval"),
            "tools/agent/orchestration/route.py": ("contracts", "eval"),
            "documents/conventions/example.md": ("docs", "eval"),
            "bootstrap/host/manifest.toml": ("eval", "workflow-container"),
            "tools/runtime/archive/github_eval_delivery.py": ("contracts", "eval"),
            ".github/workflows/other.yml": ("eval", "workflow-container"),
            "documents/design/example.md": ("docs",),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(select_static_gate_units((path,)), expected)

    def test_docs_python_and_github_profiles_are_reported(self) -> None:
        """Classifier should expose active profile and checks."""
        result = subprocess.run(
            [
                sys.executable,
                str(CLASSIFIER),
                "--format",
                "json",
                "--path",
                "documents/example.md",
                "--path",
                "tools/agent_tools/example.py",
                "--path",
                ".github/workflows/demo.yml",
                "--path",
                "bootstrap/runtime.py",
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        profiles = {row["profile"] for row in payload["risks"]}

        self.assertIn("docs-only-or-docs-impact", profiles)
        self.assertIn("python-tooling", profiles)
        self.assertIn("github-automation", profiles)
        self.assertIn("container-runtime", profiles)
        self.assertNotIn("docker-devcontainer", profiles)


if __name__ == "__main__":
    unittest.main()
