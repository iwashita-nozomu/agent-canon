"""Focused tests for the canonical skill runtime shim materializer."""

# @dependency-start
# contract test
# responsibility Verifies 60-row materializer fixed-point and readback evidence.
# upstream design ../../documents/design/skill-runtime-shim-materialization.md approved materializer contract
# upstream implementation ../../tools/agent_tools/skill_shim_materializer.py single shim writer
# downstream implementation ../../tests/fixtures/skill-runtime-shim/fixed-point/expected.json fixed-point oracle
# @dependency-end

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS_ROOT))

from skill_shim_materializer import (  # noqa: E402
    build_context,
    build_record,
    check,
    classify_legacy,
    fixed_point_acceptance,
    render_shim,
)


class SkillShimMaterializerTest(unittest.TestCase):
    """Verify materialization converges without a second writer."""

    def test_materialize_fixed_point(self) -> None:
        """Two runs preserve all records/projections and the second run is empty."""
        actual = fixed_point_acceptance(PROJECT_ROOT)
        expected = json.loads(
            (
                PROJECT_ROOT
                / "tests/fixtures/skill-runtime-shim/fixed-point/expected.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(actual, expected)
        self.assertEqual(actual["second_run"]["content_delta_count"], 0)
        self.assertEqual(len(actual["first_run"]["record_digests"]), 60)
        self.assertEqual(len(actual["first_run"]["projection_digests"]), 60)
        self.assertEqual(actual["status"], "pass")

    def test_host_config_metadata_is_read_back_from_generated_bytes(self) -> None:
        """A changed host config path leaves the generated shim in fail-closed drift."""
        context = build_context(PROJECT_ROOT)
        skill = "agent-orchestration"
        host = context.host_entries[skill]
        runtime_path = PROJECT_ROOT / ".agents/skills" / skill / "SKILL.md"
        original = runtime_path.read_text(encoding="utf-8")
        self.assertIn(f"path={host.path}", original)
        runtime_path.write_text(
            original.replace(f"path={host.path}", f"path={host.path}.mutated", 1),
            encoding="utf-8",
        )
        try:
            result = check(PROJECT_ROOT, all_skills=True)
        finally:
            runtime_path.write_text(original, encoding="utf-8")
        self.assertEqual(result["status"], "fail")
        self.assertIn(runtime_path.relative_to(PROJECT_ROOT).as_posix(), result["content_delta_paths"])

    def test_legacy_receipt_lists_every_unmatched_block(self) -> None:
        """Legacy prose is rejected without a canonical-heading fallback."""
        context = build_context(PROJECT_ROOT)
        skill = "agent-orchestration"
        expected = render_shim(build_record(context, skill))
        runtime_path = PROJECT_ROOT / ".agents/skills" / skill / "SKILL.md"
        original = runtime_path.read_text(encoding="utf-8")
        runtime_path.write_text(
            "---\nname: agent-orchestration\ndescription: "
            '"Mandatory routing skill for repository tasks. Use before selecting workflow family, skills, review roles, subagents, model/team policy, runtime entrypoints, or run bundles for Codex routing."\n---\n'
            "# Legacy\n\n## Reader Map\n\nUnmatched prose.\n",
            encoding="utf-8",
        )
        try:
            receipt = classify_legacy(context, skill, expected)
        finally:
            runtime_path.write_text(original, encoding="utf-8")
        self.assertEqual(receipt["resolution"], "blocked")
        blocks = receipt["unmatched_blocks"]
        self.assertEqual(len(blocks), 2)
        self.assertTrue(all("locator" in block and "digest" in block for block in blocks))


if __name__ == "__main__":
    unittest.main()
