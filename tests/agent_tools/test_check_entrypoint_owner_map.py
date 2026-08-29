# @dependency-start
# contract test
# responsibility Verifies the root entrypoint owner-map grammar and regression failures.
# upstream design ../../documents/design/entrypoint-owner-map.md structural contract
# upstream implementation ../../tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py verifier under test
# @dependency-end
"""Tests for the root entrypoint owner-map checker."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.validation.semantic.entrypoint import check_entrypoint_owner_map as checker


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class EntrypointOwnerMapTest(unittest.TestCase):
    """Exercise valid entrypoints and each structural rejection class."""

    def _fixture(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for contract in checker.CONTRACTS:
            source = REPOSITORY_ROOT / contract.path
            (root / contract.path).write_text(
                source.read_text(encoding="utf-8"), encoding="utf-8"
            )
        manifest_source = REPOSITORY_ROOT / checker.MARKER_MANIFEST_PATH
        manifest_target = root / checker.MARKER_MANIFEST_PATH
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        manifest_target.write_text(
            manifest_source.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return root

    def _rules(self, root: Path) -> set[str]:
        return {finding.rule for finding in checker.run_checks(root)}

    def test_repository_entrypoints_satisfy_contract(self) -> None:
        self.assertEqual(checker.run_checks(REPOSITORY_ROOT), [])

    def test_rejects_renamed_operational_section(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        target.write_text(
            target.read_text(encoding="utf-8") + "\n## Emergency Operations\n\nDo the thing.\n",
            encoding="utf-8",
        )
        self.assertIn("heading-sequence", self._rules(root))

    def test_rejects_nested_procedure_heading(self) -> None:
        root = self._fixture()
        target = root / "ROOT_AGENTS.md"
        text = target.read_text(encoding="utf-8").replace(
            "## Task Entry\n",
            "## Task Entry\n\n### Retry Procedure\n",
            1,
        )
        target.write_text(text, encoding="utf-8")
        self.assertIn("nested-heading", self._rules(root))

    def test_rejects_fenced_command_recipe(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        text = target.read_text(encoding="utf-8").replace(
            "## Validation Routing\n",
            "## Validation Routing\n\n```bash\npython3 tool.py\n```\n",
            1,
        )
        target.write_text(text, encoding="utf-8")
        self.assertIn("fenced-recipe", self._rules(root))

    def test_rejects_numbered_procedure(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        text = target.read_text(encoding="utf-8").replace(
            "## Task Entry\n",
            "## Task Entry\n\n1. Run the bootstrap command.\n",
            1,
        )
        target.write_text(text, encoding="utf-8")
        self.assertIn("ordered-procedure", self._rules(root))

    def test_rejects_bullet_command_recipe(self) -> None:
        root = self._fixture()
        target = root / "ROOT_AGENTS.md"
        text = target.read_text(encoding="utf-8").replace(
            "## Validation Routing\n",
            "## Validation Routing\n\n- python3 tools/check.py\n",
            1,
        )
        target.write_text(text, encoding="utf-8")
        self.assertIn("command-recipe", self._rules(root))

    def test_rejects_missing_owner_row(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        text = target.read_text(encoding="utf-8")
        text = "\n".join(
            line for line in text.splitlines() if "public skill registry" not in line
        ) + "\n"
        target.write_text(text, encoding="utf-8")
        self.assertIn("owner-map", self._rules(root))

    def test_rejects_operational_marker_surface(self) -> None:
        root = self._fixture()
        target = root / checker.MARKER_MANIFEST_PATH
        target.write_text(
            target.read_text(encoding="utf-8")
            + "\n[[contracts]]\nid = \"regression\"\n"
            + "[[contracts.surfaces]]\npath = \"AGENTS.md\"\n"
            + "markers = [\"operational detail\"]\n",
            encoding="utf-8",
        )
        self.assertIn("delegated-marker-surface", self._rules(root))


if __name__ == "__main__":
    unittest.main()
