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
                        "def main() -> int:",
                        "    build_parser()",
                        "    return execute(['true'])",
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
            self.assertNotIn("load_config", records)
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
            self.assertFalse(records["execute"]["helper_candidate"])
            self.assertTrue(records["execute"]["needs_user_judgment"])
            self.assertEqual(records["execute"]["judgment_rule"], "main:public-local-command_runner")
            self.assertFalse(records["build_parser"]["helper_candidate"])
            self.assertTrue(records["build_parser"]["needs_user_judgment"])
            self.assertEqual(records["build_parser"]["judgment_rule"], "main:public-local-cli_parser")

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

    def test_public_names_without_functional_evidence_are_not_default_helpers(self) -> None:
        """Names alone should not make public main-code helpers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "main_code.py").write_text(
                "\n".join(
                    [
                        "def normalize_callable(value: object) -> object:",
                        "    return value",
                        "",
                        "def load_callable(path: str) -> str:",
                        "    return path",
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
            self.assertEqual(payload["records"], [])

    def test_class_helpers_are_reported_with_domain_specific_rules(self) -> None:
        """Class candidates should use the same deterministic rule surface."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "model.py").write_text(
                "\n".join(
                    [
                        "from dataclasses import dataclass",
                        "",
                        "@dataclass",
                        "class PublicInfo:",
                        "    value: int",
                        "",
                        "@dataclass",
                        "class LocalMetrics:",
                        "    value: int",
                        "",
                        "def public_api() -> LocalMetrics:",
                        "    return LocalMetrics(1)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_sample.py").write_text(
                "\n".join(
                    [
                        "import pytest",
                        "",
                        "class TestWorkflow:",
                        "    def test_case(self) -> None:",
                        "        assert True",
                        "",
                        "class Session:",
                        "    pass",
                        "",
                        "@pytest.fixture",
                        "def session() -> Session:",
                        "    return Session()",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            experiments_dir = root / "experiments"
            experiments_dir.mkdir()
            (experiments_dir / "run_exp.py").write_text(
                "\n".join(
                    [
                        "import json",
                        "",
                        "def parse_config() -> dict[str, str]:",
                        "    return json.loads('{}')",
                        "",
                        "def normalize_unused(value: object) -> object:",
                        "    return value",
                        "",
                        "def run() -> dict[str, str]:",
                        "    return parse_config()",
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
            self.assertEqual(records["LocalMetrics"]["kind"], "class")
            self.assertEqual(records["LocalMetrics"]["domain"], "main")
            self.assertFalse(records["LocalMetrics"]["helper_candidate"])
            self.assertTrue(records["LocalMetrics"]["needs_user_judgment"])
            self.assertEqual(records["LocalMetrics"]["judgment_rule"], "main:public-local-data_container")
            self.assertNotIn("PublicInfo", records)
            self.assertIn("candidate-rule:test:local-test-class", records["Session"]["evidence"])
            self.assertIn("candidate-rule:test:fixture-function", records["session"]["evidence"])
            self.assertNotIn("TestWorkflow", records)
            self.assertIn("candidate-rule:experiment:local-parser_loader", records["parse_config"]["evidence"])
            self.assertNotIn("normalize_unused", records)

    def test_text_output_includes_pass_token(self) -> None:
        """Text output should provide machine-readable summary tokens."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "helpers.py").write_text(
                "\n".join(
                    [
                        "def _ready(value: object) -> bool:",
                        "    return value is not None",
                        "",
                        "def public_api(value: object) -> bool:",
                        "    return _ready(value)",
                        "",
                    ]
                ),
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
            self.assertIn("SYMBOL=helpers.py:1:_ready", result.stdout)
            self.assertIn("verdict=auto_helper", result.stdout)
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
            records = {record["qualname"]: record for record in payload["records"]}
            self.assertEqual(records["add"]["incoming_count"], 0)
            self.assertFalse(records["add"]["helper_candidate"])
            self.assertEqual(records["add"]["specialization"], "not_helper_candidate")


if __name__ == "__main__":
    unittest.main()
