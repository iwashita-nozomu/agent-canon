"""Tests for runtime profile inventory drift checks."""

# @dependency-start
# contract test
# responsibility Tests runtime profile inventory drift detection.
# upstream implementation ../../tools/agent_tools/check_runtime_profile_inventory.py checks runtime profile inventory drift
# upstream implementation ../../tools/docs/render_runtime_profile_inventory.py renders runtime profile doc from inventory
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "check_runtime_profile_inventory.py"
RENDER_SCRIPT = PROJECT_ROOT / "tools" / "docs" / "render_runtime_profile_inventory.py"


def write_minimal_inventory(path: Path) -> None:
    """Write one small valid runtime profile inventory."""
    payload = {
        "version": 1,
        "title": "Runtime Profiles And Check Matrix",
        "summary": ["summary line 1", "summary line 2"],
        "profile_classes": [
            {
                "profile": "Base project",
                "activates": ["`README.md`"],
                "required_when": "Every repo",
            }
        ],
        "compatibility_note": ["compat note"],
        "risk_classes": [
            {
                "risk": "Routine docs",
                "examples": "examples",
                "required_validation": "validation",
            }
        ],
        "risk_note": ["risk note"],
        "validation_failure_response": {
            "rule": [
                "After any validation test/check failure, preserve intended behavior.",
                "Record `failing_contract`, `observation_level`, `cause_classification`, `intent_preservation`, and `evidence`.",
            ],
            "required_fields": [
                "failing_contract",
                "observation_level",
                "cause_classification",
                "intent_preservation",
                "evidence",
            ],
            "cause_classes": [
                "implementation_bug",
                "stale_generated_artifact",
            ],
            "intent_preservation": [
                "repair_same_intent",
                "redesign_same_intent",
                "escalate_design_conflict",
            ],
            "repair_routes": [
                "repair_same_intent: repair implementation while preserving approved intent",
                "redesign_same_intent: return to design while preserving approved intent",
                "escalate_design_conflict: escalate before any intent change",
            ],
        },
        "check_matrix": [
            {
                "changed_surface": "Markdown docs only",
                "required_check": ["`tools/bin/agent-canon docs check`"],
            }
        ],
        "closeout_rule": ["closeout"],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class RuntimeProfileInventoryCheckTest(unittest.TestCase):
    """Exercise runtime profile inventory drift detection end-to-end."""

    def render_doc(self, inventory_path: Path, doc_path: Path) -> str:
        """Render a fixture document from a fixture inventory."""
        result = subprocess.run(
            [
                sys.executable,
                str(RENDER_SCRIPT),
                "--inventory",
                str(inventory_path),
                "--doc",
                str(doc_path),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_passes_when_doc_matches_rendered(self) -> None:
        """Pass when the checked document matches renderer output."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            inventory = root / "inventory.json"
            doc = root / "doc.md"
            write_minimal_inventory(inventory)
            rendered = self.render_doc(inventory, doc)
            doc.write_text(rendered, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_SCRIPT),
                    "--inventory",
                    str(inventory),
                    "--doc",
                    str(doc),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("RUNTIME_PROFILE_INVENTORY_DRIFT=pass", result.stdout)
        self.assertIn("## Validation Failure Response", rendered)
        self.assertIn("`intent_preservation`", rendered)
        self.assertIn("`stale_generated_artifact`", rendered)
        self.assertIn(
            "repair_same_intent: repair implementation while preserving approved intent",
            rendered,
        )

    def test_default_paths_resolve_from_script_source_root(self) -> None:
        """Resolve default inventory/doc paths from AgentCanon source root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = subprocess.run(
                [sys.executable, str(CHECK_SCRIPT)],
                cwd=tmp_dir,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUNTIME_PROFILE_INVENTORY_DRIFT=pass", result.stdout)

    def test_fails_when_doc_drifts(self) -> None:
        """Fail with a diff when the checked document drifts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            inventory = root / "inventory.json"
            doc = root / "doc.md"
            write_minimal_inventory(inventory)
            doc.write_text("# different\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECK_SCRIPT),
                    "--inventory",
                    str(inventory),
                    "--doc",
                    str(doc),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("RUNTIME_PROFILE_INVENTORY_DRIFT=fail", result.stdout)
        self.assertIn("---", result.stdout)
        self.assertIn("+++", result.stdout)
