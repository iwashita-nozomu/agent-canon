# @dependency-start
# contract test
# responsibility Verifies root entrypoint grammar, the common-base directive, and actual required owner destinations.
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
        paths = {contract.path for contract in checker.CONTRACTS}
        paths.add(checker.MARKER_MANIFEST_PATH)
        paths.update(
            marker
            for contract in checker.CONTRACTS
            for markers in contract.owner_rows
            for marker in markers
            if marker.endswith(".md")
        )
        for path in paths:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPOSITORY_ROOT / path).read_bytes())
        return root

    def _rules(self, root: Path) -> set[str]:
        return {finding.rule for finding in checker.run_checks(root)}

    def test_repository_entrypoints_satisfy_contract(self) -> None:
        self.assertEqual(checker.run_checks(REPOSITORY_ROOT), [])

    def test_rejects_renamed_operational_section(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        target.write_text(
            target.read_text(encoding="utf-8")
            + "\n## Emergency Operations\n\nDo the thing.\n",
            encoding="utf-8",
        )
        self.assertIn("heading-sequence", self._rules(root))

    def test_rejects_nested_procedure_heading(self) -> None:
        root = self._fixture()
        target = root / "ROOT_AGENTS.md"
        text = target.read_text(encoding="utf-8").replace(
            "## Task Entry\n", "## Task Entry\n\n### Retry Procedure\n", 1
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
            "## Task Entry\n", "## Task Entry\n\n1. Run the bootstrap command.\n", 1
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
        target = root / "agents/canonical/SOURCE_ROUTING.md"
        text = "\n".join(
            line
            for line in target.read_text(encoding="utf-8").splitlines()
            if "public skill registry" not in line
        ) + "\n"
        target.write_text(text, encoding="utf-8")
        self.assertIn("owner-map", self._rules(root))

    def test_rejects_missing_optional_map(self) -> None:
        root = self._fixture()
        (root / "agents/canonical/SOURCE_ROUTING.md").unlink()
        self.assertIn("file", self._rules(root))

    def test_rejects_missing_route_to_optional_map(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        text = "\n".join(
            line
            for line in target.read_text(encoding="utf-8").splitlines()
            if "| unresolved source owner |" not in line
        ) + "\n"
        target.write_text(text, encoding="utf-8")
        self.assertIn("owner-map", self._rules(root))

    def test_full_source_owner_map_is_not_automatically_loaded(self) -> None:
        entry = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        optional = "agents/canonical/SOURCE_ROUTING.md"
        self.assertIn(f"]({optional})", entry)
        self.assertNotIn("public skill registry", entry)
        self.assertNotIn(optional, checker.ROOT_ENTRYPOINT_PATHS)
        self.assertTrue((REPOSITORY_ROOT / optional).is_file())

    def test_rejects_operational_marker_surface(self) -> None:
        root = self._fixture()
        target = root / checker.MARKER_MANIFEST_PATH
        target.write_text(
            target.read_text(encoding="utf-8")
            + '\n[[contracts]]\nid = "regression"\n'
            + '[[contracts.surfaces]]\npath = "AGENTS.md"\n'
            + 'markers = ["operational detail"]\n',
            encoding="utf-8",
        )
        self.assertIn("delegated-marker-surface", self._rules(root))

    def test_rejects_missing_common_base_directive(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        text = target.read_text(encoding="utf-8").replace("@ROOT_AGENTS.md\n", "", 1)
        target.write_text(text, encoding="utf-8")
        self.assertIn("common-base", self._rules(root))

    def test_rejects_nonleading_common_base_directive(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        target.write_text(
            "<!-- heading before common base -->\n"
            + target.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.assertIn("common-base", self._rules(root))

    def test_rejects_correct_label_with_wrong_destination(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        text = target.read_text(encoding="utf-8").replace(
            "[source map](agents/canonical/SOURCE_ROUTING.md)",
            "[agents/canonical/SOURCE_ROUTING.md](ROOT_AGENTS.md)",
        )
        target.write_text(text, encoding="utf-8")
        self.assertNotIn("owner-map", self._rules(root))
        self.assertIn("owner-link", self._rules(root))

    def test_rejects_unlinked_owner_path(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        text = target.read_text(encoding="utf-8").replace(
            "[source map](agents/canonical/SOURCE_ROUTING.md)",
            "`agents/canonical/SOURCE_ROUTING.md`",
        )
        target.write_text(text, encoding="utf-8")
        self.assertIn("owner-link", self._rules(root))

    def test_rejects_missing_required_document(self) -> None:
        root = self._fixture()
        (root / "agents/skills/agent-canon-update.md").unlink()
        self.assertIn("owner-target", self._rules(root))

    def test_accepts_equivalent_relative_destination(self) -> None:
        root = self._fixture()
        target = root / "agents/canonical/SOURCE_ROUTING.md"
        text = target.read_text(encoding="utf-8")
        original = "](../skills/agent-canon-update.md)"
        self.assertIn(original, text)
        target.write_text(
            text.replace(original, "](../../agents/skills/agent-canon-update.md)"),
            encoding="utf-8",
        )
        self.assertEqual(checker.run_checks(root), [])


if __name__ == "__main__":
    unittest.main()
