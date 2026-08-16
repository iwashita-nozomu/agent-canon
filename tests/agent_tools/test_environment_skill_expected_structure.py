"""Protect the canonical Dockerfile-to-public-runner test structure."""

# @dependency-start
# contract test
# responsibility Protects canonical image build and public runner full-test acceptance.
# upstream design ../../agents/skills/environment-maintenance.md standard route owner
# upstream design ../../agents/skills/dependency-design.md image-owned dependency consumer
# upstream design ../../agents/skills/environment-cleanup.md alternate construction consumer
# upstream design ../../agents/skills/devcontainer-exec.md targeted execution boundary
# @dependency-end

from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE = (
    "dockerfile -> canonical image -> "
    "docker run <canonical-full-test-command> -> pass"
)
STANDARD_COMMANDS = (
    "docker build -f docker/Dockerfile -t <rootrepo> .",
    "docker run --rm <rootrepo> testrunner.sh",
)


class EnvironmentSkillExpectedStructureTests(unittest.TestCase):
    """Keep the standard route and its observable runner contract stable."""

    def read(self, relative_path: str) -> str:
        """Read and normalize one canonical skill owner."""
        return " ".join(
            (PROJECT_ROOT / relative_path)
            .read_text(encoding="utf-8")
            .lower()
            .split()
        )

    def read_raw(self, relative_path: str) -> str:
        """Read one owner without coupling assertions to prose line wrapping."""
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    def section(self, heading: str, next_heading: str) -> str:
        """Return one bounded owner section for semantic assertions."""
        text = self.read_raw("agents/skills/environment-maintenance.md")
        start = text.index(heading) + len(heading)
        end = text.index(next_heading, start)
        return text[start:end]

    def code_fence(self, text: str, language: str) -> str:
        """Extract one code example from a bounded contract section."""
        match = re.search(rf"```{re.escape(language)}\n(.*?)\n```", text, flags=re.DOTALL)
        self.assertIsNotNone(match, f"missing {language} contract example")
        return match.group(1)

    def test_pr709_pipeline_and_adjacent_owner_boundaries_remain(self) -> None:
        """Preserve the earlier image-to-full-test owner boundary."""
        for relative_path in (
            "agents/skills/environment-maintenance.md",
            "agents/skills/dependency-design.md",
            "agents/skills/environment-cleanup.md",
        ):
            self.assertIn(PIPELINE, self.read(relative_path), relative_path)

        devcontainer = self.read("agents/skills/devcontainer-exec.md")
        for marker in ("environment acceptance", "docker run", "targeted command"):
            self.assertIn(marker, devcontainer, marker)

    def test_expected_structure_precedes_operating_rules(self) -> None:
        """The owner starts from the image/full-test structure."""
        raw = self.read_raw("agents/skills/environment-maintenance.md").lower()
        self.assertLess(raw.index("## expected structure"), raw.index("## operating rules"))
        for marker in ("dockerfile", "canonical image", "docker run", "standard suite"):
            self.assertIn(marker, raw, marker)

    def test_standard_route_uses_target_root_and_exact_command_pair(self) -> None:
        """Build and run use the target Git root and one shared image name."""
        route = self.section("### Non-template standard route", "## Purpose")
        commands = self.code_fence(route, "text").splitlines()
        self.assertEqual(commands, list(STANDARD_COMMANDS))

        normalized = " ".join(route.lower().split())
        for marker in (
            "target repository git root",
            "image name/tag",
            "build context",
            "`testrunner.sh`",
            "internal test path",
        ):
            self.assertIn(marker, normalized, marker)

    def test_testlist_toml_has_required_entry_fields_and_ordered_command(self) -> None:
        """The TOML example has required fields without inventory overchecks."""
        invariants = self.section("### Standard invariants", "## Purpose")
        testlist = tomllib.loads(self.code_fence(invariants, "toml"))
        self.assertIn("tests", testlist)
        self.assertTrue(testlist["tests"])
        entry = testlist["tests"][0]

        required = {
            "id",
            "environment",
            "code_owner",
            "responsibility_scope",
            "require",
            "command",
        }
        self.assertTrue(required.issubset(entry), sorted(required - set(entry)))
        self.assertIsInstance(entry["id"], str)
        self.assertTrue(entry["id"])
        self.assertIn(entry["environment"], {"tooling", "product"})
        self.assertIsInstance(entry["code_owner"], str)
        self.assertTrue(entry["code_owner"])
        code_owner = PurePosixPath(entry["code_owner"])
        self.assertFalse(code_owner.is_absolute())
        self.assertNotIn("..", code_owner.parts)
        self.assertIsInstance(entry["responsibility_scope"], str)
        self.assertTrue(entry["responsibility_scope"])
        self.assertIn(entry["require"], {"docker", "devcontainer"})
        self.assertIsInstance(entry["command"], list)
        self.assertTrue(entry["command"])
        self.assertTrue(all(isinstance(token, str) and token for token in entry["command"]))

        normalized = " ".join(invariants.lower().split())
        for marker in (
            "`#` comment",
            "unique stable",
            "ordered nonempty",
            "token-array",
            "require=docker",
            "require=devcontainer",
        ):
            self.assertIn(marker, normalized, marker)

    def test_runner_selects_require_and_emits_classified_receipts(self) -> None:
        """Route selection and result metadata form an observable runner contract."""
        invariants = self.section("### Standard invariants", "## Purpose")
        text = " ".join(invariants.lower().split())
        for marker in (
            "active_route=docker",
            "active_route=devcontainer",
            "active_route != require",
            "`not_selected` iff",
            "require=docker",
            "require=devcontainer",
            "start",
            "pass",
            "fail",
            "not_selected",
            "exact argv",
            "code_owner",
            "responsibility_scope",
            "status",
            "exit code",
            "selected entry",
            "malformed",
            "duplicate",
            "unsupported",
        ):
            self.assertIn(marker, text, marker)

    def test_adjacent_cleanup_completion_regression_remains_observable(self) -> None:
        """The existing cleanup owner still exposes image/full-test completion evidence."""
        for relative_path in (
            "agents/skills/environment-maintenance.md",
            "agents/skills/environment-cleanup.md",
        ):
            text = self.read(relative_path)
            for marker in (
                "canonical docker image",
                "docker run",
                "repositoryの標準テスト一式",
            ):
                self.assertIn(marker, text, f"{relative_path}: {marker}")

if __name__ == "__main__":
    unittest.main()
