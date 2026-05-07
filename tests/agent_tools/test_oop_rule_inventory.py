"""Tests for OOP rule inventory tooling."""

# @dependency-start
# responsibility Tests OOP rule inventory and legacy placement reporting.
# upstream implementation ../../tools/agent_tools/oop_rule_inventory.py inventory CLI
# upstream design ../../documents/object-oriented-design.md OOP policy source
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "tools" / "agent_tools" / "oop_rule_inventory.py"


def run_inventory(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the inventory CLI."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class OopRuleInventoryTest(unittest.TestCase):
    """Exercise OOP rule inventory behavior."""

    def test_current_repository_passes(self) -> None:
        """The AgentCanon repo contains required OOP rule and analyzer surfaces."""
        result = run_inventory(PROJECT_ROOT, "--include-legacy")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OOP_RULE_INVENTORY=pass", result.stdout)
        self.assertIn("tools/agent_tools/analyze_oop_readability.py", result.stdout)
        self.assertIn("tools/legacy/jax_solver_util/oop_check_support", result.stdout)

    def test_missing_required_policy_fails(self) -> None:
        """Missing required rule sources fail closed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_inventory(Path(tmp_dir))

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("OOP_RULE_INVENTORY=fail", result.stdout)
            self.assertIn("OOP_RULE_INVENTORY_MISSING=", result.stdout)

    def test_json_output_is_machine_readable(self) -> None:
        """JSON output should expose status and entries."""
        result = run_inventory(PROJECT_ROOT, "--format", "json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "pass")
        paths = {entry["path"] for entry in payload["entries"]}
        self.assertIn("documents/object-oriented-design.md", paths)


if __name__ == "__main__":
    unittest.main()
