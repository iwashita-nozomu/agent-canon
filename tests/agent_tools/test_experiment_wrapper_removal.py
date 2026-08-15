"Focused regressions for experiment wrapper-skill removal."

# @dependency-start
# contract test
# responsibility Verifies direct experiment, artifact, and HTML owners after wrapper deletion.
# upstream design ../../agents/skills/experiment-lifecycle.md sole run-state owner
# upstream design ../../agents/skills/result-artifact-writeout.md concrete artifact owner
# upstream design ../../agents/skills/html-output.md HTML artifact owner
# upstream design ../../agents/skills/catalog.yaml public skill identity owner
# upstream implementation ../../tools/agent_tools/prompt_classifier.py prompt signal owner
# @dependency-end

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from prompt_classifier import SKILL_KEYWORDS  # noqa: E402

REMOVED = ("html-experiment-report", "save-experiment-results")


def selected_by_keywords(prompt: str) -> set[str]:
    "Return keyword-selected owners using the classifier's immutable table."
    normalized = prompt.casefold()
    return {
        skill
        for skill, groups in SKILL_KEYWORDS.items()
        if any(all(token.casefold() in normalized for token in group) for group in groups)
    }


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
                (PROJECT_ROOT / ".agents/skills" / skill / "SKILL.md").exists()
            )

    def test_existing_html_experiment_routes_to_direct_owners(self) -> None:
        selected = selected_by_keywords(
            "Render the existing experiment results as a browser-readable HTML page"
        )
        self.assertIn("html-output", selected)
        self.assertNotIn("experiment-lifecycle", selected)
        self.assertTrue(set(REMOVED).isdisjoint(selected))

    def test_new_html_experiment_adds_lifecycle_explicitly(self) -> None:
        selected = selected_by_keywords(
            "Rerun the experiment and render its result as a browser-readable HTML page"
        )
        self.assertIn("experiment-lifecycle", selected)
        self.assertIn("html-output", selected)
        self.assertTrue(set(REMOVED).isdisjoint(selected))

    def test_experiment_artifact_persistence_routes_to_direct_owners(self) -> None:
        selected = selected_by_keywords(
            "Persist experiment artifact evidence without writing a report"
        )
        self.assertIn("experiment-lifecycle", selected)
        self.assertIn("result-artifact-writeout", selected)
        self.assertTrue(set(REMOVED).isdisjoint(selected))

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
