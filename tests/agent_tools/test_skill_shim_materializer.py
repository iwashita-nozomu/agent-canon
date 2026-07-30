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
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = PROJECT_ROOT / "tools" / "agent_tools"
sys.path.insert(0, str(TOOLS_ROOT))

from skill_shim_materializer import (  # noqa: E402
    MIGRATION_BASELINE_PATH,
    MaterializerError,
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

    def test_migration_baseline_blocks_host_config_mismatch(self) -> None:
        """Mismatching host config row must fail closed before migration."""
        baseline_path = PROJECT_ROOT / MIGRATION_BASELINE_PATH
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        rows = baseline["host_config_rows"]
        if not rows:
            raise AssertionError("migration baseline is empty")
        mutated = json.loads(json.dumps(baseline))
        rows_mutated = []
        for index, row in enumerate(mutated["host_config_rows"]):
            if index == 0:
                row = dict(row)
                row["host_config_entry_digest"] = "0" * 64
            rows_mutated.append(row)
        mutated["host_config_rows"] = rows_mutated
        with tempfile.TemporaryDirectory() as tmpdir:
            staged = Path(tmpdir) / "baseline.json"
            staged.write_text(json.dumps(mutated, ensure_ascii=False, indent=2), encoding="utf-8")
            with patch(
                "skill_shim_materializer.MIGRATION_BASELINE_PATH",
                Path(staged),
            ):
                with self.assertRaises(MaterializerError) as context:
                    build_context(PROJECT_ROOT)
        self.assertEqual(context.exception.code, "migration_baseline_mismatch")
        self.assertIn("migration_baseline_mismatch", str(context.exception))

    def test_host_config_path_requires_exact_skill_root_path(self) -> None:
        """Only ../.agents/skills/<id>/SKILL.md is accepted as canonical host path."""
        config_path = PROJECT_ROOT / ".codex/config.toml"
        original = config_path.read_text(encoding="utf-8")
        skill = "agent-orchestration"
        current = f'path = "../.agents/skills/{skill}/SKILL.md"'
        replacement = f'path = "../../.agents/skills/{skill}/SKILL.md"'
        self.assertIn(current, original)
        config_path.write_text(original.replace(current, replacement, 1), encoding="utf-8")
        try:
            with self.assertRaises(MaterializerError) as context:
                build_context(PROJECT_ROOT)
        finally:
            config_path.write_text(original, encoding="utf-8")
        self.assertEqual(context.exception.code, "host_config_path_mismatch")
        self.assertIn("host_config_path_mismatch", str(context.exception))

    def test_legacy_classification_blocks_tool_commands_only(self) -> None:
        """Generated section-only bodies must keep all unmatched blocks and remain blocked."""
        context = build_context(PROJECT_ROOT)
        skill = "agent-orchestration"
        runtime_path = PROJECT_ROOT / ".agents/skills" / skill / "SKILL.md"
        expected = render_shim(build_record(context, skill))
        original = runtime_path.read_text(encoding="utf-8")
        runtime_path.write_text(
            "<!-- generated: agent_canon.skill_runtime_shim.v1 -->\n"
            "## Tool Commands\n"
            "python3 tools/agent_tools/skill_tool_commands.py show --skill agent-orchestration --format text\n",
            encoding="utf-8",
        )
        try:
            receipt = classify_legacy(context, skill, expected)
        finally:
            runtime_path.write_text(original, encoding="utf-8")
        self.assertEqual(receipt["resolution"], "blocked")
        self.assertEqual(receipt["classification"], "legacy_exact_sections")
        self.assertEqual(len(receipt["unmatched_blocks"]), 2)
        locators = [entry["locator"] for entry in receipt["unmatched_blocks"]]
        self.assertIn(
            f"{runtime_path.relative_to(PROJECT_ROOT).as_posix()}#preamble",
            locators,
        )
        self.assertIn(
            f"{runtime_path.relative_to(PROJECT_ROOT).as_posix()}#L2-L3",
            locators,
        )

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
