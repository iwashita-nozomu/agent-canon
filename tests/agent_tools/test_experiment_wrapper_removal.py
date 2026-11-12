"Focused regressions for experiment wrapper-skill removal."

# @dependency-start
# contract test
# responsibility Verifies direct experiment, artifact, and HTML owners after wrapper deletion.
# upstream design ../../agents/skills/experiment-lifecycle.md sole run-state owner
# upstream design ../../agents/skills/result-artifact-writeout.md concrete artifact owner
# upstream design ../../agents/skills/html-output.md HTML artifact owner
# upstream design ../../agents/skills/catalog.yaml public skill identity owner
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/prompt_classifier.rs native prompt classifier
# @dependency-end

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

REMOVED = ("html-experiment-report", "save-experiment-results")


class ExperimentWrapperRemovalTest(unittest.TestCase):
    "Verify deleted wrappers cannot regain public or routing ownership."

    def test_removed_public_identities_and_files_are_absent(self) -> None:
        catalog = yaml.safe_load(
            (PROJECT_ROOT / "agents/skills/catalog.yaml").read_text(encoding="utf-8")
        )
        skill_ids = {row["id"] for row in catalog["skill_families"]}
        dependencies = yaml.safe_load(
            (PROJECT_ROOT / "agents/skills/skill-dependencies.yaml").read_text(
                encoding="utf-8"
            )
        )["skill_dependencies"]
        for skill in REMOVED:
            self.assertNotIn(skill, skill_ids)
            self.assertNotIn(skill, dependencies)
            self.assertFalse(
                (PROJECT_ROOT / "agents/skills" / f"{skill}.md").exists()
            )
            self.assertFalse(
                (PROJECT_ROOT / ".codex/personal/skills" / skill / "SKILL.md").exists()
            )

    def test_artifact_writeout_does_not_require_report_writing(self) -> None:
        dependencies = yaml.safe_load(
            (PROJECT_ROOT / "agents/skills/skill-dependencies.yaml").read_text(
                encoding="utf-8"
            )
        )["skill_dependencies"]
        self.assertEqual(
            dependencies["result-artifact-writeout"]["required_prerequisites"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
