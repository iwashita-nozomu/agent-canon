"""Tests for the SOLID evidence coverage checker."""

# @dependency-start
# contract test
# responsibility Tests SOLID-sensitive Python evidence coverage checks.
# upstream implementation ../../tools/agent_tools/check_solid_evidence.py evidence coverage checker
# upstream implementation ../../tools/oop/shared/readability_core.py emits scanned_paths in OOP reports
# upstream design ../../documents/coding-conventions-python.md SOLID evidence route policy
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "agent_tools" / "check_solid_evidence.py"
OOP_ANALYZER = PROJECT_ROOT / "tools" / "oop" / "python" / "readability.py"


class CheckSolidEvidenceTest(unittest.TestCase):
    """Validate SOLID-sensitive evidence coverage behavior."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker in a temporary root."""
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_json_evidence(self, root: Path, scanned_paths: list[str]) -> Path:
        """Write a minimal OOP JSON report."""
        report = root / "reports" / "agents" / "run" / "oop.json"
        report.parent.mkdir(parents=True)
        report.write_text(
            json.dumps(
                {
                    "summary": {
                        "dimension_counts": {},
                        "findings": 0,
                        "kind_counts": {},
                        "scanned_paths": scanned_paths,
                        "solid_counts": {},
                        "status": "pass",
                    },
                    "findings": [],
                }
            ),
            encoding="utf-8",
        )
        return report

    def test_non_boundary_python_file_passes_without_evidence(self) -> None:
        """A Python file without public boundaries does not need OOP evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "tools" / "constants.py"
            source.parent.mkdir(parents=True)
            source.write_text("VALUE = 1\n", encoding="utf-8")

            result = self.run_checker(root, "tools/constants.py")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SOLID_EVIDENCE=pass", result.stdout)
            self.assertIn("SOLID_EVIDENCE_SENSITIVE_CHANGES=0", result.stdout)

    def test_class_boundary_requires_oop_evidence(self) -> None:
        """A changed class boundary needs an OOP readability report."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "python" / "model.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "class CustomerRecord:\n    name: str\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, "python/model.py")

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("SOLID_EVIDENCE=fail", result.stdout)
            self.assertIn("SOLID_EVIDENCE_SENSITIVE_CHANGE=python/model.py:1:class_boundary:CustomerRecord", result.stdout)
            self.assertIn("missing-oop-readability-evidence", result.stdout)

    def test_evidence_must_cover_sensitive_path(self) -> None:
        """OOP evidence for another path should not close the gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "python" / "model.py"
            source.parent.mkdir(parents=True)
            source.write_text("class CustomerRecord:\n    pass\n", encoding="utf-8")
            report = self.write_json_evidence(root, ["python/other.py"])

            result = self.run_checker(root, "python/model.py", "--evidence", str(report))

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing-path-coverage", result.stdout)

    def test_json_evidence_covering_path_passes(self) -> None:
        """Path-covered OOP JSON evidence closes a SOLID-sensitive path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "python" / "model.py"
            source.parent.mkdir(parents=True)
            source.write_text("class CustomerRecord:\n    pass\n", encoding="utf-8")
            report = self.write_json_evidence(root, ["python/model.py"])

            result = self.run_checker(root, "python/model.py", "--evidence", str(report))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SOLID_EVIDENCE=pass", result.stdout)
            self.assertIn("SOLID_EVIDENCE_COVERED_PATHS=1", result.stdout)

    def test_oop_json_report_exposes_scanned_paths(self) -> None:
        """OOP JSON reports expose scanned paths for evidence coverage."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "example.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(OOP_ANALYZER),
                    "--root",
                    str(root),
                    "--format",
                    "json",
                    "--min-score",
                    "0",
                    str(source),
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["scanned_paths"], ["example.py"])

    def test_changed_mode_uses_changed_lines(self) -> None:
        """Changed mode should ignore an unchanged class when another line changes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "python" / "model.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "class CustomerRecord:\n    pass\n\nVALUE = 1\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
            subprocess.run(["git", "add", "python/model.py"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True)
            source.write_text(
                "class CustomerRecord:\n    pass\n\nVALUE = 2\n",
                encoding="utf-8",
            )

            result = self.run_checker(root, "--changed")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SOLID_EVIDENCE_SENSITIVE_CHANGES=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
