"""Tests for OOP rule inventory tooling."""

# @dependency-start
# responsibility Tests language-specific OOP rule inventory tooling.
# upstream implementation ../../tools/oop/python/rule_inventory.py Python inventory CLI
# upstream implementation ../../tools/oop/cpp/rule_inventory.py C++ inventory CLI
# upstream implementation ../../tools/oop/shared/rule_inventory_core.py shared inventory behavior
# upstream design ../../documents/object-oriented-design.md OOP policy source
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.oop.shared.rule_inventory_core import (
    InventoryEntry,
    inventory_payload,
    missing_entries,
    resolve_surface_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_SCRIPT = PROJECT_ROOT / "tools" / "oop" / "python" / "rule_inventory.py"
CPP_SCRIPT = PROJECT_ROOT / "tools" / "oop" / "cpp" / "rule_inventory.py"


def run_inventory(
    script: Path,
    root: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """Run the inventory CLI."""
    return subprocess.run(
        [sys.executable, str(script), "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class OopRuleInventoryTest(unittest.TestCase):
    """Exercise OOP rule inventory behavior."""

    def test_current_repository_passes(self) -> None:
        """The AgentCanon repo contains required OOP rule and analyzer surfaces."""
        python_result = run_inventory(PYTHON_SCRIPT, PROJECT_ROOT)
        cpp_result = run_inventory(CPP_SCRIPT, PROJECT_ROOT)

        self.assertEqual(
            python_result.returncode,
            0,
            python_result.stdout + python_result.stderr,
        )
        self.assertEqual(cpp_result.returncode, 0, cpp_result.stdout + cpp_result.stderr)
        self.assertIn("OOP_PYTHON_RULE_INVENTORY=pass", python_result.stdout)
        self.assertIn("tools/oop/python/readability.py", python_result.stdout)
        self.assertIn("documents/tools/oop/python/readability.md", python_result.stdout)
        self.assertIn("OOP_CPP_RULE_INVENTORY=pass", cpp_result.stdout)
        self.assertIn("tools/oop/cpp/readability.py", cpp_result.stdout)
        self.assertIn("documents/tools/oop/cpp/readability.md", cpp_result.stdout)
        self.assertIn("resolved=", cpp_result.stdout)

    def test_missing_required_policy_fails(self) -> None:
        """Missing required rule sources fail closed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_inventory(PYTHON_SCRIPT, Path(tmp_dir))

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("OOP_PYTHON_RULE_INVENTORY=fail", result.stdout)
            self.assertIn("OOP_PYTHON_RULE_INVENTORY_MISSING=", result.stdout)

    def test_json_output_is_machine_readable(self) -> None:
        """JSON output should expose status and entries."""
        result = run_inventory(CPP_SCRIPT, PROJECT_ROOT, "--format", "json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "pass")
        paths = {entry["path"] for entry in payload["entries"]}
        self.assertIn("documents/coding-conventions-cpp.md", paths)
        self.assertIn("tools/oop/cpp/rule_inventory.py", paths)
        resolved_paths = {
            entry["path"]: entry["resolved_path"] for entry in payload["entries"]
        }
        self.assertIn(
            resolved_paths["documents/coding-conventions-cpp.md"],
            {
                "documents/coding-conventions-cpp.md",
                "vendor/agent-canon/documents/coding-conventions-cpp.md",
            },
        )

    def test_shared_inventory_resolves_vendor_surfaces(self) -> None:
        """Shared inventory entries should accept AgentCanon-owned vendor docs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vendor_doc = (
                root
                / "vendor"
                / "agent-canon"
                / "documents"
                / "object-oriented-design.md"
            )
            vendor_doc.parent.mkdir(parents=True)
            vendor_doc.write_text("# OOP\n", encoding="utf-8")
            entry = InventoryEntry(
                "policy",
                "documents/object-oriented-design.md",
                "OOP policy",
            )

            resolved = resolve_surface_path(root, entry.path)
            payload = inventory_payload(root, [entry])
            missing = missing_entries(root, [entry])

            self.assertEqual(resolved, vendor_doc)
            self.assertEqual(missing, [])
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["missing"], [])

    def test_cpp_readability_doc_covers_boundary_exemptions(self) -> None:
        """C++ tool docs should describe the implemented allowed boundaries."""
        doc = (
            PROJECT_ROOT
            / "documents"
            / "tools"
            / "oop"
            / "cpp"
            / "readability.md"
        ).read_text(encoding="utf-8")

        required_terms = (
            "named aggregate value object",
            "NATIVE_AD_VJP",
            "__nad_",
            "apply_compile_bindings",
            "numeric scalar value object",
        )
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, doc)


if __name__ == "__main__":
    unittest.main()
