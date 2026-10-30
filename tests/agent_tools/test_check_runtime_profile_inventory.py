"""Tests for runtime profile inventory drift checks."""

# @dependency-start
# contract test
# responsibility Tests runtime profile inventory drift detection.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/docs.rs owns native runtime profile rendering and drift checks
# @dependency-end

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")
INVENTORY_RELATIVE_PATH = Path(
    "documents/runtime/runtime-profiles-and-check-matrix.json"
)
DOC_RELATIVE_PATH = Path("documents/runtime/runtime-profiles-and-check-matrix.md")
DEFAULT_TITLE = "Runtime Profiles And Check Matrix"


def write_minimal_inventory(path: Path, *, title: str = DEFAULT_TITLE) -> None:
    """Write one small valid runtime profile inventory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "title": title,
        "summary": ["summary line 1", "summary line 2"],
        "profile_classes": [
            {
                "id": "base-project",
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
    """Exercise the native docs owner's runtime profile behavior."""

    def prepare_root(
        self, root: Path, *, title: str = DEFAULT_TITLE
    ) -> tuple[Path, Path]:
        """Install the canonical profile fixture and docs tool configs in a root."""
        inventory = root / INVENTORY_RELATIVE_PATH
        doc = root / DOC_RELATIVE_PATH
        write_minimal_inventory(inventory, title=title)
        for relative in (
            Path(".markdownlint-cli2.jsonc"),
            Path("tools/validation/documentation/config/lychee.toml"),
        ):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT_ROOT / relative, destination)
        return inventory, doc

    def run_native_docs(
        self, root: Path, command: str, *args: str
    ) -> subprocess.CompletedProcess[str]:
        """Invoke the selected native docs command against an explicit root."""
        self.assertIsNotNone(
            AGENT_CANON_CLI, "AGENT_CANON_CLI must select the current native executable"
        )
        executable = Path(str(AGENT_CANON_CLI))
        self.assertTrue(
            executable.is_absolute(),
            "AGENT_CANON_CLI must be an absolute executable path",
        )
        return subprocess.run(
            [str(executable), "docs", command, "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_passes_when_doc_matches_native_renderer(self) -> None:
        """Pass when the checked document matches the native renderer output."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _, doc = self.prepare_root(root)
            rendered = self.run_native_docs(root, "render-runtime-profile")
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            doc.write_text(rendered.stdout, encoding="utf-8")

            result = self.run_native_docs(root, "check", DOC_RELATIVE_PATH.as_posix())

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("## Validation Failure Response", rendered.stdout)
        self.assertIn("`intent_preservation`", rendered.stdout)
        self.assertIn("`stale_generated_artifact`", rendered.stdout)
        self.assertIn(
            "repair_same_intent: repair implementation while preserving approved intent",
            rendered.stdout,
        )

    def test_native_docs_paths_resolve_from_selected_root(self) -> None:
        """The native renderer reads the canonical paths under its selected root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            title = "Selected Temporary Runtime Profile Inventory"
            self.prepare_root(root, title=title)
            result = self.run_native_docs(root, "render-runtime-profile")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"# {title}", result.stdout)

    def test_fails_when_doc_drifts(self) -> None:
        """Fail with the native drift finding when the checked document differs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _, doc = self.prepare_root(root)
            doc.write_text("# different\n", encoding="utf-8")

            result = self.run_native_docs(root, "check", DOC_RELATIVE_PATH.as_posix())

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "runtime profile inventory markdown drifts from documents/runtime/runtime-profiles-and-check-matrix.json",
            result.stderr,
        )
        self.assertIn(DOC_RELATIVE_PATH.as_posix(), result.stderr)


if __name__ == "__main__":
    unittest.main()
