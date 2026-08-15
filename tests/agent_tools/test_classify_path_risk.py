"""Tests for path/risk check matrix classification."""

# @dependency-start
# contract test
# responsibility Tests path-risk classifier smoke routing.
# upstream implementation ../../tools/agent_tools/classify_path_risk.py classifies changed paths.
# upstream design ../../documents/runtime/runtime-profiles-and-check-matrix.md defines risk/check routing.
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = PROJECT_ROOT / "tools" / "agent_tools" / "classify_path_risk.py"


class ClassifyPathRiskTest(unittest.TestCase):
    """Validate representative path-risk profiles."""

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
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        profiles = {row["profile"] for row in payload["risks"]}

        self.assertEqual(
            profiles,
            {"docs-only-or-docs-impact", "python-tooling", "github-automation"},
        )
        self.assertNotIn("agentcanon-shared-surface", profiles)
        self.assertEqual(tuple(payload["units"]), ("contracts", "workflow-container"))


if __name__ == "__main__":
    unittest.main()
