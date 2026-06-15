"""Tests for non-canonical document inventory."""

# @dependency-start
# responsibility Tests non-canonical document inventory behavior.
# upstream implementation ../../tools/agent_tools/noncanonical_document_inventory.py forwards legacy calls to Rust document cleanup inventory
# upstream design ../../agents/skills/document-canon-cleanup.md defines cleanup workflow
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "noncanonical_document_inventory.py"


class NoncanonicalDocumentInventoryTest(unittest.TestCase):
    """Verify document-canon cleanup inventory output."""

    def test_reports_evidence_missing_header_and_duplicate_titles(self) -> None:
        """The inventory should classify non-canonical document candidates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_fixture(root)
            json_out = root / "reports" / "noncanonical-docs.json"
            markdown_out = root / "reports" / "noncanonical-docs.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--json-out",
                    str(json_out),
                    "--markdown-out",
                    str(markdown_out),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            payload = json.loads(json_out.read_text(encoding="utf-8"))
            findings = {
                (finding["path"], finding["kind"]): finding
                for finding in payload["findings"]
            }
            markdown_text = markdown_out.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NONCANONICAL_DOCUMENT_INVENTORY=pass", result.stdout)
        self.assertIn(
            (
                "agents/evals/results/skill-workflow-prompt/skill-eval-test-fail-example.md",
                "accumulated_eval_result",
            ),
            findings,
        )
        self.assertIn(("documents/missing-header.md", "missing_dependency_manifest"), findings)
        self.assertIn(
            ("documents/duplicate-b.md", "duplicate_heading_candidate"),
            findings,
        )
        self.assertIn("Non-Canonical Document Inventory", markdown_text)

    def test_fail_on_findings_returns_nonzero(self) -> None:
        """Optional fail mode should make the report usable as a gate."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_file(root, "documents/missing-header.md", "# Missing\n")

            result = subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root), "--fail-on-findings"],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("NONCANONICAL_DOCUMENT_FINDINGS=1", result.stdout)

    def test_heading_prefix_is_ignored_for_non_markdown_duplicate_detection(self) -> None:
        """Only Markdown H1 syntax should feed duplicate-heading findings."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest = self.manifest("Documents a shared heading fixture.")
            self.write_file(root, "documents/alpha.md", manifest + "# Shared Heading\n")
            self.write_file(root, "documents/beta.md", manifest + "# Shared Heading\n")
            self.write_file(root, "documents/noise.txt", manifest + "# Shared Heading\n")
            self.write_file(root, "documents/noise.rst", manifest + "# Shared Heading\n")
            json_out = root / "reports" / "noncanonical-docs.json"

            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--root",
                    str(root),
                    "--json-out",
                    str(json_out),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            payload = json.loads(json_out.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            {
                "action": "merge, retitle, or document why both headings are active",
                "canonical_path": "documents/alpha.md",
                "kind": "duplicate_heading_candidate",
                "path": "documents/beta.md",
                "reason": "shares H1 title with documents/alpha.md",
            },
            payload["findings"],
        )
        self.assertNotIn(
            {
                "action": "merge, retitle, or document why both headings are active",
                "canonical_path": "documents/alpha.md",
                "kind": "duplicate_heading_candidate",
                "path": "documents/noise.txt",
                "reason": "shares H1 title with documents/alpha.md",
            },
            payload["findings"],
        )
        self.assertNotIn(
            {
                "action": "merge, retitle, or document why both headings are active",
                "canonical_path": "documents/alpha.md",
                "kind": "duplicate_heading_candidate",
                "path": "documents/noise.rst",
                "reason": "shares H1 title with documents/alpha.md",
            },
            payload["findings"],
        )

    def test_git_untracked_documents_are_included(self) -> None:
        """New documents must be visible before their first commit."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
            self.write_file(root, "documents/missing-header.md", "# Missing\n")

            result = subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NONCANONICAL_DOCUMENTS=1", result.stdout)
        self.assertIn("documents/missing-header.md", result.stdout)

    def test_reports_are_excluded_by_default(self) -> None:
        """Generated report artifacts should not enter source document inventory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_file(root, "documents/missing-header.md", "# Missing Header\n")
            self.write_file(root, "reports/run-output.md", "# Generated Report\n")

            result = subprocess.run(
                [sys.executable, str(TOOL), "--root", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NONCANONICAL_DOCUMENTS=1", result.stdout)
        self.assertIn("documents/missing-header.md", result.stdout)
        self.assertNotIn("reports/run-output.md", result.stdout)

    def write_fixture(self, root: Path) -> None:
        """Write a fixture repository with known document candidates."""
        skill_text = self.manifest("Documents the example skill.") + "# Example Skill\n"
        self.write_file(root, ".agents/skills/example/SKILL.md", skill_text)
        self.write_file(
            root,
            "agents/evals/results/skill-workflow-prompt/skill-eval-test-fail-example.md",
            self.manifest("Records one accumulated eval result.") + "# Eval\n",
        )
        self.write_file(root, "documents/missing-header.md", "# Missing Header\n")
        self.write_file(
            root,
            "documents/duplicate-a.md",
            self.manifest("Documents active duplicate A.") + "# Duplicate Topic\n",
        )
        self.write_file(
            root,
            "documents/duplicate-b.md",
            self.manifest("Documents active duplicate B.") + "# Duplicate Topic\n",
        )

    def write_file(self, root: Path, relative: str, text: str) -> None:
        """Write one fixture file."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def manifest(self, responsibility: str) -> str:
        """Return a dependency manifest block."""
        return "\n".join(
            [
                "<!--",
                "@dependency-start",
                f"responsibility {responsibility}",
                "upstream design README.md fixture anchor",
                "@dependency-end",
                "-->",
                "",
            ]
        )


if __name__ == "__main__":
    unittest.main()
