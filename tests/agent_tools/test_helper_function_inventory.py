"""Tests for helper function inventory role inference."""

# @dependency-start
# responsibility Tests helper function inventory and role inference.
# upstream implementation ../../tools/agent_tools/helper_function_inventory.py inventories helper roles
# upstream design ../../documents/tools/README.md documents tool entrypoints
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INVENTORY = PROJECT_ROOT / "tools" / "agent_tools" / "helper_function_inventory.py"


class HelperFunctionInventoryTest(unittest.TestCase):
    """Verify helper candidate and role reports."""

    def test_role_inference_uses_static_body_facts(self) -> None:
        """Roles should reflect AST/call facts, not only function names."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "sample.py"
            source.write_text(
                "\n".join(
                    [
                        "import argparse",
                        "import ast",
                        "import subprocess",
                        "from pathlib import Path",
                        "",
                        "def public_api(value: int) -> int:",
                        "    return value",
                        "",
                        "def _parse_config(path: Path) -> dict[str, object]:",
                        "    tree = ast.parse(path.read_text())",
                        "    return {'nodes': len(tree.body)}",
                        "",
                        "def load_config(path: Path) -> dict[str, object]:",
                        "    return _parse_config(path)",
                        "",
                        "def execute(command: list[str]) -> int:",
                        "    return subprocess.run(command, check=False).returncode",
                        "",
                        "def build_parser() -> argparse.ArgumentParser:",
                        "    parser = argparse.ArgumentParser()",
                        "    parser.add_argument('--x')",
                        "    return parser",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(INVENTORY),
                    "--root",
                    str(root),
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            records = {record["qualname"]: record for record in payload["records"]}
            self.assertNotIn("public_api", records)
            self.assertEqual(records["_parse_config"]["role"], "static_analyzer")
            self.assertIn("ast-call", ",".join(records["_parse_config"]["evidence"]))
            self.assertEqual(records["_parse_config"]["incoming_count"], 1)
            self.assertEqual(
                records["_parse_config"]["incoming_call_sites"],
                ["sample.py:14:load_config"],
            )
            self.assertTrue(records["_parse_config"]["specialized_helper"])
            self.assertEqual(
                records["_parse_config"]["specialization"],
                "single_caller_helper",
            )
            self.assertEqual(records["execute"]["role"], "command_runner")
            self.assertEqual(records["build_parser"]["role"], "cli_parser")

    def test_all_functions_reports_public_api(self) -> None:
        """The all-functions mode should include non-helper public functions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "public.py").write_text(
                "def public_api(value: int) -> int:\n    return value\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(INVENTORY),
                    "--root",
                    str(root),
                    "--all-functions",
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["records"][0]["qualname"], "public_api")
            self.assertFalse(payload["records"][0]["helper_candidate"])

    def test_text_output_includes_pass_token(self) -> None:
        """Text output should provide machine-readable summary tokens."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "helpers.py").write_text(
                "def _is_ready(value: object) -> bool:\n    return value is not None\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(INVENTORY), "--root", str(root)],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("HELPER=helpers.py:1:_is_ready", result.stdout)
            self.assertIn("role=predicate", result.stdout)
            self.assertIn("HELPER_INVENTORY=pass", result.stdout)

    def test_attribute_leaf_call_is_not_local_function_caller(self) -> None:
        """Attribute calls like set.add should not call a local add helper."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "attributes.py").write_text(
                "\n".join(
                    [
                        "def add(value: str) -> str:",
                        "    return value",
                        "",
                        "def public_api() -> set[str]:",
                        "    values: set[str] = set()",
                        "    values.add('x')",
                        "    return values",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(INVENTORY),
                    "--root",
                    str(root),
                    "--format",
                    "json",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            records = {record["qualname"]: record for record in payload["records"]}
            self.assertEqual(records["add"]["incoming_count"], 0)
            self.assertEqual(records["add"]["specialization"], "no_internal_call_sites")


if __name__ == "__main__":
    unittest.main()
