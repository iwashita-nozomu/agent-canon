"""Tests for deterministic parent-repository audit semantic selection."""

# @dependency-start
# contract test
# responsibility Verifies parent audit unit schema, semantic surface selection, path safety, and receipt aggregation.
# upstream design ../../documents/design/parent-repository-audit.md owns failure semantics and unit contract
# upstream implementation ../../tools/analysis/code/parent_repository_audit.py owns enumeration and evidence selection
# downstream implementation ../../documents/parent-repository-audit/README.md owns self-contained audit units
# @dependency-end

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "analysis" / "code" / "parent_repository_audit.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from tools.analysis.code.parent_repository_audit import _load_units


class ParentRepositoryAuditTests(unittest.TestCase):
    """Exercise the selected parent audit mechanism without runtime builds."""

    def run_tool(self, parent_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the canonical audit tool from the AgentCanon source root."""
        return subprocess.run(
            [sys.executable, str(TOOL), *args, "--root", str(parent_root), "--format", "json"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def make_parent(self, root: Path, *paths: str) -> Path:
        """Create a minimal tracked parent repository fixture."""
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(
            ["git", "-C", str(root), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "config", "user.name", "Audit Test"],
            check=True,
        )
        for relative in paths:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("tracked\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        return root

    def test_canonical_units_have_unique_migration_ids(self) -> None:
        """The nine surviving units expose semantic surfaces and unique migration IDs."""
        units = _load_units(PROJECT_ROOT)
        self.assertEqual(len(units), 9)
        self.assertTrue(all(unit.surfaces for unit in units))
        migration_ids = [legacy_id for unit in units for legacy_id in unit.legacy_ids]
        self.assertEqual(len(migration_ids), len(set(migration_ids)))
        expected_ids = {
            *(f"PRA-M{index:02d}" for index in range(1, 9)),
            *(f"PRA-C{index:03d}" for index in range(1, 111)),
            *(f"PRA-X{index:03d}" for index in range(1, 54)),
        }
        self.assertEqual(set(migration_ids), expected_ids)
        self.assertEqual(len(migration_ids), 171)

    def test_design_ledger_maps_each_legacy_id_to_one_unit(self) -> None:
        """The one-time design ledger and unit metadata remain a bijective mapping."""
        row_pattern = re.compile(
            r"\b(PRA-(?:M[0-9]{2}|[CX][0-9]{3}))\b.*"
            r"(documents/parent-repository-audit/audit-unit/[a-z-]+\.md)"
        )
        design_path = PROJECT_ROOT / "documents" / "design" / "parent-repository-audit.md"
        ledger: dict[str, str] = {}
        for line in design_path.read_text(encoding="utf-8").splitlines():
            match = row_pattern.search(line)
            if match:
                self.assertNotIn(match.group(1), ledger)
                ledger[match.group(1)] = match.group(2)
        unit_ids = {
            legacy_id: unit.path
            for unit in _load_units(PROJECT_ROOT)
            for legacy_id in unit.legacy_ids
        }
        self.assertEqual(ledger, unit_ids)

    def test_canonical_skill_uses_surface_and_evidence_boundaries(self) -> None:
        """The public workflow must not reintroduce path-pattern ownership."""
        skill = (
            PROJECT_ROOT / "agents" / "skills" / "parent-repository-audit.md"
        ).read_text(encoding="utf-8")
        self.assertIn("`--surface`", skill)
        self.assertIn("`--scope`", skill)
        self.assertIn("evidence", skill)
        self.assertNotIn("pattern:<parent-relative-glob>", skill)
        self.assertNotIn("uncovered selected path", skill)
        self.assertNotIn("selected-scope uncovered count", skill)

    def test_list_and_check_read_parent_tree_without_path_classification(self) -> None:
        """Full checks read tracked evidence without a second path owner or coverage map."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(
                Path(tmp_dir), "README.md", "docker/Dockerfile", "python/main.py"
            )
            listed = self.run_tool(parent, "list")
            self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
            listed_payload = json.loads(listed.stdout)
            self.assertEqual(listed_payload["tracked_path_count"], 3)
            self.assertEqual(len(listed_payload["unit_paths"]), 9)

            checked = self.run_tool(parent, "check")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            payload = json.loads(checked.stdout)
            self.assertEqual(payload["status"], "pass")
            self.assertNotIn("uncovered_path_count", payload)
            self.assertNotIn("uncovered_paths", payload)
            self.assertNotIn("overlap_path_count", payload)
            self.assertNotIn("overlap_paths", payload)
            self.assertNotIn("scope_patterns", payload["unit_records"][0])

    def test_scope_escape_returns_typed_failure(self) -> None:
        """An evidence scope outside the parent root is rejected without fallback."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(Path(tmp_dir), "README.md")
            result = self.run_tool(parent, "list", "--scope", "../outside")
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["failure_code"], "parent_repository_audit_path_escape")

    def test_failed_or_deferred_unit_receipt_cannot_close_audit(self) -> None:
        """Failed and deferred unit receipts remain failed in the CLI packet."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(Path(tmp_dir), "README.md")
            for status in ("failed", "deferred"):
                result = self.run_tool(parent, "check", "--unit-status", status)
                self.assertNotEqual(result.returncode, 0)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], "failed")
                self.assertEqual(
                    payload["failure_code"],
                    "parent_repository_audit_unit_status_failed",
                )

    def test_all_complete_unit_receipts_pass(self) -> None:
        """All positive unit receipts produce a passing audit packet."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(Path(tmp_dir), "README.md")
            result = self.run_tool(
                parent,
                "check",
                "--unit-status",
                "pass",
                "--unit-status",
                "closed",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["unit_statuses"], ["pass", "closed"])

    def test_scope_limits_evidence_without_selecting_units(self) -> None:
        """A path scope is evidence-only and cannot become another unit ownership map."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(
                Path(tmp_dir), "README.md", "docker/Dockerfile", "python/main.py"
            )
            result = self.run_tool(parent, "list", "--scope", "docker")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["scope_paths"], ["docker/Dockerfile"])
            self.assertEqual(len(payload["unit_paths"]), 9)

    def test_surface_selection_is_semantic_and_deterministic(self) -> None:
        """Explicit semantic surfaces select units without path-pattern inference."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(
                Path(tmp_dir), "README.md", "docker/Dockerfile", "python/main.py"
            )
            result = self.run_tool(
                parent,
                "list",
                "--surface",
                "environment.containers",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["selected_surfaces"], ["environment.containers"])
            self.assertEqual(
                payload["unit_paths"],
                [
                    "documents/parent-repository-audit/audit-unit/environment-containers.md"
                ],
            )

    def test_unknown_surface_returns_typed_failure(self) -> None:
        """Unknown semantic selectors fail instead of guessing from paths."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(Path(tmp_dir), "README.md")
            result = self.run_tool(parent, "list", "--surface", "unknown.surface")
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["failure_code"],
                "parent_repository_audit_surface_unknown",
            )


if __name__ == "__main__":
    unittest.main()
