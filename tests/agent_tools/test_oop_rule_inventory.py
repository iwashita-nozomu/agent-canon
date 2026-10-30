"""Tests for OOP rule inventory tooling."""

# @dependency-start
# contract test
# responsibility Tests language-specific OOP rule inventory tooling.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/oop_rule_inventory.rs Python and C++ inventory CLI
# upstream design ../../documents/conventions/object-oriented-design.md OOP policy source
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON_CLI = os.environ.get("AGENT_CANON_CLI")
PYTHON_SELECTOR = "oop-python-rule-inventory"
CPP_SELECTOR = "oop-cpp-rule-inventory"


def run_inventory(
    selector: str,
    root: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """Run the inventory through the explicitly selected native CLI."""
    if AGENT_CANON_CLI is None:
        raise RuntimeError("AGENT_CANON_CLI must select the current native executable")
    return subprocess.run(
        [AGENT_CANON_CLI, selector, "--root", str(root), *args],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class OopRuleInventoryTest(unittest.TestCase):
    """Exercise OOP rule inventory behavior."""

    def test_current_repository_passes(self) -> None:
        """The AgentCanon repo contains required OOP rule and analyzer surfaces."""
        python_result = run_inventory(PYTHON_SELECTOR, PROJECT_ROOT)
        cpp_result = run_inventory(CPP_SELECTOR, PROJECT_ROOT)

        self.assertEqual(
            python_result.returncode,
            0,
            python_result.stdout + python_result.stderr,
        )
        self.assertEqual(
            cpp_result.returncode, 0, cpp_result.stdout + cpp_result.stderr
        )
        self.assertIn("OOP_PYTHON_RULE_INVENTORY=pass", python_result.stdout)
        self.assertIn(
            "tools/validation/code/oop/python/readability.py", python_result.stdout
        )
        self.assertIn("documents/tools/oop/python/readability.md", python_result.stdout)
        self.assertIn(
            "tools/runtime/dispatch/agent-canon/src/oop_rule_inventory.rs",
            python_result.stdout,
        )
        self.assertIn("OOP_CPP_RULE_INVENTORY=pass", cpp_result.stdout)
        self.assertIn("tools/validation/code/oop/cpp/readability.py", cpp_result.stdout)
        self.assertIn("documents/tools/oop/cpp/readability.md", cpp_result.stdout)
        self.assertIn(
            "tools/runtime/dispatch/agent-canon/src/oop_rule_inventory.rs",
            cpp_result.stdout,
        )
        self.assertIn("resolved=", cpp_result.stdout)

    def test_missing_required_policy_fails(self) -> None:
        """Missing required rule sources fail closed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = run_inventory(PYTHON_SELECTOR, Path(tmp_dir))

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("OOP_PYTHON_RULE_INVENTORY=fail", result.stdout)
            self.assertIn("OOP_PYTHON_RULE_INVENTORY_MISSING=", result.stdout)

    def test_json_output_is_machine_readable(self) -> None:
        """JSON output should expose status and entries."""
        result = run_inventory(CPP_SELECTOR, PROJECT_ROOT, "--format", "json")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "pass")
        paths = {entry["path"] for entry in payload["entries"]}
        self.assertIn("documents/conventions/coding-conventions-cpp.md", paths)
        self.assertIn(
            "tools/runtime/dispatch/agent-canon/src/oop_rule_inventory.rs", paths
        )
        resolved_paths = {
            entry["path"]: entry["resolved_path"] for entry in payload["entries"]
        }
        self.assertIn(
            resolved_paths["documents/conventions/coding-conventions-cpp.md"],
            {
                "documents/conventions/coding-conventions-cpp.md",
                "vendor/agent-canon/documents/conventions/coding-conventions-cpp.md",
            },
        )

    def test_cpp_readability_doc_covers_boundary_exemptions(self) -> None:
        """C++ tool docs should describe the implemented allowed boundaries."""
        doc = (
            PROJECT_ROOT / "documents" / "tools" / "oop" / "cpp" / "readability.md"
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
