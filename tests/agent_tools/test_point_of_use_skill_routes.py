# @dependency-start
# contract test
# responsibility Verifies that point-of-use Skill handoffs are candidates rather than mandatory prerequisites.
# upstream design ../../documents/design/entrypoint-owner-map.md point-of-use reading contract
# upstream implementation ../../agents/skills/skill-dependencies.yaml selected handoff candidates
# @dependency-end
"""Regression coverage for the three previously missing conditional Skill edges."""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.agent.skills.skill_route_catalog import (
    load_skill_route_rules,
    related_skill_candidates,
)

ROOT = Path(__file__).resolve().parents[2]
HANDOFFS = (
    ("cpp-review", "computational-optimization"),
    ("python-review", "change-review"),
    ("codex-task-workflow", "integration"),
)


class PointOfUseSkillRoutesTest(unittest.TestCase):
    """Use the production catalog loader and candidate projection."""

    def test_handoffs_are_candidates_without_required_activation(self) -> None:
        rules = {rule.skill: rule for rule in load_skill_route_rules(ROOT)}
        for source, target in HANDOFFS:
            with self.subTest(source=source, target=target):
                self.assertIn(target, rules)
                self.assertIn(target, rules[source].related_skills)
                self.assertNotIn(target, rules[source].required_prerequisites)
                self.assertNotIn(target, rules[source].successors)
                selected = (source,)
                related, candidates = related_skill_candidates(selected, rules, selected)
                self.assertIn(target, related[source])
                self.assertIn(target, candidates)

    def test_selected_handoff_is_not_reissued_as_a_pending_candidate(self) -> None:
        rules = {rule.skill: rule for rule in load_skill_route_rules(ROOT)}
        for source, target in HANDOFFS:
            with self.subTest(source=source, target=target):
                related, candidates = related_skill_candidates(
                    (source,), rules, (source, target)
                )
                self.assertNotIn(target, related.get(source, ()))
                self.assertNotIn(target, candidates)


if __name__ == "__main__":
    unittest.main()
