"""Tests for the Rust structured document inventory CLI."""

# @dependency-start
# contract test
# responsibility Tests Rust document-canon inventory CLI behavior.
# upstream implementation ../../rust/agent-canon/src/structured_analysis.rs implements document inventory.
# upstream design ../../agents/skills/document-canon-cleanup.md defines cleanup workflow.
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


class StructuredDocumentInventoryCliTest(unittest.TestCase):
    """Verify the canonical Rust document inventory CLI."""

    def test_reports_missing_header_and_duplicate_titles(self) -> None:
        """The inventory should classify document cleanup candidates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "repo"
            self.write_fixture(root)
            json_out = root / "reports" / "document-inventory.json"
            markdown_out = root / "reports" / "document-inventory.md"

            result = self.run_agent_canon(
                [
                    "structured-analysis",
                    "document-inventory",
                    "--root",
                    str(root),
                    "--json-out",
                    str(json_out),
                    "--markdown-out",
                    str(markdown_out),
                ],
                cargo_target_dir=temp_path / "cargo-target",
            )

            payload = json.loads(json_out.read_text(encoding="utf-8"))
            findings = {
                (finding["path"], finding["kind"]): finding
                for finding in payload["findings"]
            }
            markdown_text = markdown_out.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STRUCTURED_ANALYSIS_DOCUMENT_INVENTORY=pass", result.stdout)
        self.assertIn(
            (
                "agents/evals/results/skill-workflow-prompt/skill-eval-test-fail-example.md",
                "accumulated_eval_result",
            ),
            findings,
        )
        self.assertIn(("documents/missing-header.md", "missing_dependency_manifest"), findings)
        self.assertIn(("documents/duplicate-b.md", "duplicate_heading_candidate"), findings)
        self.assertIn("Non-Canonical Document Inventory", markdown_text)

    def test_fail_on_findings_returns_nonzero(self) -> None:
        """Optional fail mode should make the report usable as a gate."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root = temp_path / "repo"
            self.write_file(root, "documents/missing-header.md", "# Missing\n")

            result = self.run_agent_canon(
                [
                    "structured-analysis",
                    "document-inventory",
                    "--root",
                    str(root),
                    "--fail-on-findings",
                ],
                cargo_target_dir=temp_path / "cargo-target",
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("STRUCTURED_ANALYSIS_DOCUMENT_FINDINGS=1", result.stdout)

    @staticmethod
    def run_agent_canon(
        args: list[str], *, cargo_target_dir: Path
    ) -> subprocess.CompletedProcess[str]:
        """Run the Rust CLI with build artifacts isolated from the repo target."""
        env = os.environ.copy()
        env["CARGO_TARGET_DIR"] = str(cargo_target_dir)
        return subprocess.run(
            [str(AGENT_CANON), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    @staticmethod
    def write_file(root: Path, relative: str, text: str) -> None:
        """Write a fixture file under root."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_fixture(self, root: Path) -> None:
        """Create a compact document inventory fixture."""
        manifest = self.manifest("Documents a duplicate heading fixture.")
        self.write_file(root, "documents/duplicate-a.md", manifest + "# Duplicate\n")
        self.write_file(root, "documents/duplicate-b.md", manifest + "# Duplicate\n")
        self.write_file(root, "documents/missing-header.md", "# Missing\n")
        self.write_file(
            root,
            "agents/evals/results/skill-workflow-prompt/skill-eval-test-fail-example.md",
            "# Eval Result\n",
        )

    @staticmethod
    def manifest(responsibility: str) -> str:
        """Return a minimal dependency manifest block."""
        return (
            "<!--\n"
            "@dependency-start\n"
            "contract test-fixture\n"
            f"responsibility {responsibility}\n"
            "@dependency-end\n"
            "-->\n\n"
        )


if __name__ == "__main__":
    unittest.main()
