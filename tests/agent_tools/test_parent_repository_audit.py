"""Tests for deterministic parent-repository audit unit selection and coverage."""

# @dependency-start
# contract test
# responsibility Verifies parent audit unit schema, scope selection, path safety, and tracked-tree coverage.
# upstream design ../../documents/design/parent-repository-audit.md owns failure semantics and unit contract
# upstream implementation ../../tools/agent_tools/parent_repository_audit.py owns enumeration and coverage
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
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "parent_repository_audit.py"
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "agent_tools"))

from parent_repository_audit import _load_units  # noqa: E402


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
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Audit Test"], check=True)
        for relative in paths:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("tracked\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
        return root

    def test_canonical_units_have_unique_migration_ids(self) -> None:
        """All twelve units expose the required self-contained contract and unique IDs."""
        units = _load_units(PROJECT_ROOT)
        self.assertEqual(len(units), 12)
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

    def test_list_and_check_cover_the_parent_tracked_tree(self) -> None:
        """The all-tracked structure unit makes full-tree coverage explicit."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(
                Path(tmp_dir), "README.md", "docker/Dockerfile", "python/main.py"
            )
            listed = self.run_tool(parent, "list")
            self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
            listed_payload = json.loads(listed.stdout)
            self.assertEqual(listed_payload["tracked_path_count"], 3)
            self.assertEqual(len(listed_payload["unit_paths"]), 12)

            checked = self.run_tool(parent, "check")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            payload = json.loads(checked.stdout)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["uncovered_path_count"], 0)
            self.assertGreater(payload["overlap_path_count"], 0)

    def test_scope_escape_returns_typed_failure(self) -> None:
        """A scope outside the parent root is rejected without fallback selection."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(Path(tmp_dir), "README.md")
            result = self.run_tool(parent, "list", "--scope", "../outside")
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["failure_code"], "parent_repository_audit_path_escape")

    def test_scoped_listing_selects_matching_units_deterministically(self) -> None:
        """A scoped path selects matching units while preserving canonical order."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            parent = self.make_parent(
                Path(tmp_dir), "README.md", "docker/Dockerfile", "python/main.py"
            )
            result = self.run_tool(parent, "list", "--scope", "docker")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["scope_paths"], ["docker/Dockerfile"])
            self.assertEqual(
                payload["unit_paths"],
                sorted(payload["unit_paths"]),
            )
            self.assertIn(
                "documents/parent-repository-audit/audit-unit/environment-containers.md",
                payload["unit_paths"],
            )


if __name__ == "__main__":
    unittest.main()
