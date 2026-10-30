# @dependency-start
# contract test
# responsibility Verifies root entrypoint grammar, the common-base directive, and actual required owner destinations.
# upstream design ../../documents/design/entrypoint-owner-map.md structural contract
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/entrypoint_owner_map.rs verifier under test
# @dependency-end
"""Tests for the root entrypoint owner-map checker."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")
MARKER_MANIFEST_PATH = (
    "tools/validation/semantic/convention/convention_compliance_contracts.toml"
)
ENTRYPOINT_INPUTS = (
    "AGENTS.md",
    "ROOT_AGENTS.md",
    "agents/canonical/SOURCE_ROUTING.md",
    MARKER_MANIFEST_PATH,
    "agents/skills/agent-canon-update.md",
    "documents/design/entrypoint-owner-map.md",
)


class EntrypointOwnerMapTest(unittest.TestCase):
    """Exercise valid entrypoints and each structural rejection class."""

    def _fixture(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for path in ENTRYPOINT_INPUTS:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPOSITORY_ROOT / path).read_bytes())
        return root

    def _run(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if AGENT_CANON_CLI is None:
            raise RuntimeError(
                "AGENT_CANON_CLI must select the current native executable"
            )
        return subprocess.run(
            [
                AGENT_CANON_CLI,
                "docs",
                "check-entrypoints",
                "--root",
                str(root),
                *args,
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def _report(
        self, root: Path
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        result = self._run(root, "--format", "json")
        payload = json.loads(result.stdout)
        expected_status = "fail" if payload["findings"] else "pass"
        self.assertEqual(payload["status"], expected_status)
        expected_exit = 1 if expected_status == "fail" else 0
        self.assertEqual(
            result.returncode, expected_exit, result.stdout + result.stderr
        )
        return result, payload

    def _rules(self, root: Path) -> set[str]:
        _result, payload = self._report(root)
        return {finding["rule"] for finding in payload["findings"]}

    def test_repository_entrypoints_satisfy_contract(self) -> None:
        result, payload = self._report(REPOSITORY_ROOT)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(
            payload["checked"],
            ["AGENTS.md", "agents/canonical/SOURCE_ROUTING.md", "ROOT_AGENTS.md"],
        )

    def test_text_format_preserves_status_markers(self) -> None:
        result = self._run(REPOSITORY_ROOT, "--format", "text")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ENTRYPOINT_OWNER_MAP_FINDINGS=0", result.stdout)
        self.assertIn("ENTRYPOINT_OWNER_MAP=pass", result.stdout)

    def test_accepts_source_overlay_without_common_or_phase_sections(self) -> None:
        root = self._fixture()
        (root / "AGENTS.md").write_text(
            "@ROOT_AGENTS.md\n"
            "# AgentCanon Repository Instructions\n\n"
            "## Repository Role\n\n"
            "Instructions for editing AgentCanon itself.\n\n"
            "## Runtime Owner Map\n\n"
            "| Responsibility | Canonical owner | Reader route |\n"
            "| --- | --- | --- |\n"
            "| unresolved source owner | "
            "[source map](agents/canonical/SOURCE_ROUTING.md) | selected row only |\n",
            encoding="utf-8",
        )
        self.assertEqual(self._rules(root), set())

    def test_rejects_shared_or_phase_sections_in_source_overlay(self) -> None:
        for heading in (
            "Reader Map",
            "Always-On Boundary",
            "Task Entry",
            "Validation Routing",
            "Completion Readiness",
        ):
            with self.subTest(heading=heading):
                root = self._fixture()
                target = root / "AGENTS.md"
                target.write_text(
                    target.read_text(encoding="utf-8")
                    + f"\n## {heading}\n\nDuplicated shared or phase policy.\n",
                    encoding="utf-8",
                )
                self.assertIn("heading-sequence", self._rules(root))

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
            "## Repository Role\n",
            "## Repository Role\n\n```bash\npython3 tool.py\n```\n",
            1,
        )
        target.write_text(text, encoding="utf-8")
        self.assertIn("fenced-recipe", self._rules(root))

    def test_rejects_numbered_procedure(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        text = target.read_text(encoding="utf-8").replace(
            "## Repository Role\n",
            "## Repository Role\n\n1. Run the bootstrap command.\n",
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
        target = root / "agents/canonical/SOURCE_ROUTING.md"
        text = (
            "\n".join(
                line
                for line in target.read_text(encoding="utf-8").splitlines()
                if "public skill registry" not in line
            )
            + "\n"
        )
        target.write_text(text, encoding="utf-8")
        self.assertIn("owner-map", self._rules(root))

    def test_rejects_missing_optional_map(self) -> None:
        root = self._fixture()
        (root / "agents/canonical/SOURCE_ROUTING.md").unlink()
        self.assertIn("file", self._rules(root))

    def test_rejects_missing_route_to_optional_map(self) -> None:
        root = self._fixture()
        target = root / "AGENTS.md"
        text = (
            "\n".join(
                line
                for line in target.read_text(encoding="utf-8").splitlines()
                if "| unresolved source owner |" not in line
            )
            + "\n"
        )
        target.write_text(text, encoding="utf-8")
        self.assertIn("owner-map", self._rules(root))

    def test_full_source_owner_map_is_not_automatically_loaded(self) -> None:
        entry = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        optional = "agents/canonical/SOURCE_ROUTING.md"
        self.assertIn(f"]({optional})", entry)
        self.assertNotIn("public skill registry", entry)
        _result, payload = self._report(REPOSITORY_ROOT)
        self.assertNotIn(optional, payload["checked"])
        self.assertTrue((REPOSITORY_ROOT / optional).is_file())

    def test_rejects_operational_marker_surface(self) -> None:
        root = self._fixture()
        target = root / MARKER_MANIFEST_PATH
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
        self.assertEqual(self._rules(root), set())


if __name__ == "__main__":
    unittest.main()
