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
from textwrap import dedent

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

    def test_changed_baseline_reports_only_new_findings(self) -> None:
        """Changed baseline mode should hide findings already present at HEAD."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "config", "user.email", "agent@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Agent"],
                cwd=root,
                check=True,
            )
            source = root / "sample.py"
            source.write_text(
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
            subprocess.run(["git", "add", "sample.py"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True, text=True)
            source.write_text(
                "\n".join(
                    [
                        "def _ready(value: object) -> bool:",
                        "    return value is not None",
                        "",
                        "def public_api(value: object) -> bool:",
                        "    return _ready(value)",
                        "",
                        "def _format(value: object) -> dict[str, object]:",
                        "    return {'value': value}",
                        "",
                        "def public_report(value: object) -> dict[str, object]:",
                        "    return _format(value)",
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
                    "--changed",
                    "--baseline-ref",
                    "HEAD",
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
            self.assertTrue(payload["changed_only"])
            self.assertEqual(payload["baseline_ref"], "HEAD")
            self.assertGreaterEqual(payload["baseline_filtered"], 1)
            records = {record["qualname"]: record for record in payload["records"]}
            self.assertNotIn("_ready", records)
            self.assertEqual(records["_format"]["role"], "formatter_reporter")
            self.assertEqual(records["_format"]["candidate_rule"], "main:private-local-formatter_reporter")

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

    def test_shared_private_numeric_contract_is_not_user_judgment_helper(self) -> None:
        """Multi-caller private numeric diagnostics can be an owned primitive."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "solver.py").write_text(
                dedent(
                    """
                    import jax.numpy as jnp

                    def _residual_score(x, ax, lam):
                        residual = ax - x * lam
                        residual_norm = jnp.max(jnp.abs(residual), axis=0)
                        reference = jnp.where(residual_norm == 0, 1.0, residual_norm)
                        return jnp.max(residual_norm / reference)

                    def init(x, ax, lam):
                        return _residual_score(x, ax, lam)

                    def cond(x, ax, lam):
                        return _residual_score(x, ax, lam)

                    def step(x, ax, lam):
                        return _residual_score(x, ax, lam)

                    def finish(x, ax, lam):
                        return _residual_score(x, ax, lam)
                    """
                ).strip()
                + "\n",
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
            records = {record["qualname"]: record for record in json.loads(result.stdout)["records"]}
            self.assertEqual(records["_residual_score"]["incoming_count"], 4)
            self.assertEqual(records["_residual_score"]["role"], "numeric_kernel")
            self.assertFalse(records["_residual_score"]["helper_candidate"])
            self.assertFalse(records["_residual_score"]["needs_user_judgment"])

    def test_main_class_helpers_are_reported_with_domain_specific_rules(self) -> None:
        """Main-code class candidates should use deterministic rule surfaces."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "model.py").write_text(
                dedent(
                    """
                    from dataclasses import dataclass

                    class ExternalConfig:
                        pass

                    @dataclass
                    class PublicInfo:
                        value: int

                    class _InternalInfo(ExternalConfig):
                        pass

                    @dataclass
                    class LocalMetrics:
                        value: int

                    def public_api() -> LocalMetrics:
                        _InternalInfo()
                        return LocalMetrics(1)
                    """
                ).strip()
                + "\n",
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
            self.assertEqual(records["_InternalInfo"]["role"], "data_container")
            self.assertIn("candidate-rule:main:private-local-data_container", records["_InternalInfo"]["evidence"])
            self.assertNotIn("PublicInfo", records)

    def test_protocol_interfaces_are_not_reported_as_helpers(self) -> None:
        """Protocol classes are type boundaries, not helper classes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "interfaces.py").write_text(
                dedent(
                    """
                    from abc import ABC
                    from typing import Protocol

                    class PublicPort(Protocol):
                        def run(self) -> None: ...

                    class _PrivatePort(Protocol):
                        pass

                    class _ThinBase(ABC):
                        pass

                    def use() -> object:
                        return _PrivatePort(), _ThinBase()
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            default_result = subprocess.run(
                [sys.executable, str(INVENTORY), "--root", str(root), "--format", "json"],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            all_result = subprocess.run(
                [sys.executable, str(INVENTORY), "--root", str(root), "--all-functions", "--format", "json"],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(default_result.returncode, 0, default_result.stderr)
            self.assertEqual(all_result.returncode, 0, all_result.stderr)
            default_records = {
                record["qualname"]: record for record in json.loads(default_result.stdout)["records"]
            }
            self.assertNotIn("PublicPort", default_records)
            self.assertNotIn("_PrivatePort", default_records)
            records = {record["qualname"]: record for record in json.loads(all_result.stdout)["records"]}
            self.assertEqual(records["PublicPort"]["role"], "protocol_interface")
            self.assertEqual(records["_PrivatePort"]["role"], "protocol_interface")
            self.assertNotEqual(records["_ThinBase"]["role"], "protocol_interface")
            self.assertFalse(records["PublicPort"]["helper_candidate"])
            self.assertFalse(records["_PrivatePort"]["needs_user_judgment"])

    def test_test_directory_rules_exclude_test_cases_and_keep_support(self) -> None:
        """Test files should treat support symbols differently from test bodies."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_sample.py").write_text(
                dedent(
                    """
                    import math
                    import pytest

                    class TestWorkflow:
                        def test_case(self) -> None:
                            assert True

                    class Session:
                        pass

                    @pytest.fixture
                    def session() -> Session:
                        return Session()

                    def _reference(value: float) -> float:
                        return math.sqrt(value)

                    def test_numeric() -> None:
                        assert _reference(4.0) == 2.0
                    """
                ).strip()
                + "\n",
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
            self.assertIn("candidate-rule:test:local-test-class", records["Session"]["evidence"])
            self.assertIn("candidate-rule:test:fixture-function", records["session"]["evidence"])
            self.assertNotIn("TestWorkflow", records)
            self.assertNotIn("TestWorkflow.test_case", records)
            self.assertNotIn("test_numeric", records)
            self.assertIn("candidate-rule:test:private-local-numeric_kernel", records["_reference"]["evidence"])

    def test_experiment_directory_local_parser_rules(self) -> None:
        """Experiment files can keep local parser helpers without flagging unused names."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            experiments_dir = root / "experiments"
            experiments_dir.mkdir()
            (experiments_dir / "run_exp.py").write_text(
                dedent(
                    """
                    import json
                    from pathlib import Path

                    def parse_config(path: Path) -> dict[str, str]:
                        return json.loads(path.read_text())

                    def normalize_unused(value: object) -> object:
                        return value

                    def run() -> dict[str, str]:
                        return parse_config(Path('config.json'))
                    """
                ).strip()
                + "\n",
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
            self.assertIn("candidate-rule:experiment:local-parser_loader", records["parse_config"]["evidence"])
            self.assertNotIn("normalize_unused", records)

    def test_functional_features_do_not_depend_on_informative_names(self) -> None:
        """Opaque names should still be classified from behavior."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "opaque.py").write_text(
                dedent(
                    """
                    import sys
                    from pathlib import Path

                    class LocalFailure(Exception):
                        pass

                    def _a(raw: str) -> Path:
                        return Path(raw).expanduser().resolve()

                    def _b(handle: object) -> None:
                        handle.close()

                    def _c(box: object, payload: bytes) -> object:
                        return box.encrypt(payload)

                    def _d(root: Path, key: str) -> Path:
                        return root / 'artifacts' / key

                    def _e(buffer: object) -> object | None:
                        return None if len(buffer) == 0 else buffer

                    def _f() -> str:
                        if sys.platform == 'win32':
                            return '.dll'
                        return '.so'

                    def public_api(raw: str, handle: object, box: object, payload: bytes) -> tuple[Path, object]:
                        path = _a(raw)
                        _b(handle)
                        _d(path, 'payload')
                        _e(payload)
                        _f()
                        return path, _c(box, payload)
                    """
                ).strip()
                + "\n",
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
            self.assertEqual(records["_a"]["role"], "converter_normalizer")
            self.assertIn("path_operation", records["_a"]["features"])
            self.assertEqual(records["_b"]["role"], "writer_mutator")
            self.assertIn("resource_lifecycle", records["_b"]["features"])
            self.assertEqual(records["_c"]["role"], "converter_normalizer")
            self.assertIn("security_transform", records["_c"]["features"])
            self.assertEqual(records["_d"]["role"], "converter_normalizer")
            self.assertIn("path_operation", records["_d"]["features"])
            self.assertEqual(records["_e"]["role"], "converter_normalizer")
            self.assertIn("conditional_return", records["_e"]["features"])
            self.assertEqual(records["_f"]["role"], "converter_normalizer")
            self.assertIn("environment", records["_f"]["features"])
            self.assertNotIn("LocalFailure", records)

    def test_opaque_text_factory_and_callback_features(self) -> None:
        """Text, encoding, factory, and callback roles should come from AST facts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "opaque.py").write_text(
                dedent(
                    """
                    import base64
                    import re

                    def _g(text: str) -> str:
                        return re.sub(r'[^a-z]+', '-', text.strip().lower())

                    def _h(payload: bytes) -> bytes:
                        return base64.b64encode(payload)

                    def _i(name: str) -> str:
                        return f'value={name}'.strip()

                    def _j(prefix: str):
                        def inner(value: str) -> str:
                            return f'{prefix}:{value}'
                        return inner

                    def _k(progress_callback) -> None:
                        progress_callback('done')

                    def public_api(raw: str, payload: bytes) -> None:
                        _g(raw)
                        _h(payload)
                        _i(raw)
                        _j(raw)
                        _k(lambda message: None)
                    """
                ).strip()
                + "\n",
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
            self.assertEqual(records["_g"]["role"], "converter_normalizer")
            self.assertIn("text_transform", records["_g"]["features"])
            self.assertEqual(records["_h"]["role"], "converter_normalizer")
            self.assertIn("encoding_transform", records["_h"]["features"])
            self.assertEqual(records["_i"]["role"], "converter_normalizer")
            self.assertIn("text_transform", records["_i"]["features"])
            self.assertEqual(records["_j"]["role"], "factory_builder")
            self.assertIn("nested_function_definition", records["_j"]["features"])
            self.assertEqual(records["_k"]["role"], "formatter_reporter")
            self.assertIn("callback_emission", records["_k"]["features"])

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

    def test_markdown_output_contains_machine_readable_result_tables(self) -> None:
        """Markdown output should expose summary and count tables."""
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
                [
                    sys.executable,
                    str(INVENTORY),
                    "--root",
                    str(root),
                    "--format",
                    "markdown",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("## Summary", result.stdout)
            self.assertIn("| Metric | Value |", result.stdout)
            self.assertIn("| files scanned | 1 |", result.stdout)
            self.assertIn("## Verdict Counts", result.stdout)
            self.assertIn("| auto_helper | 1 |", result.stdout)
            self.assertIn("## Role Counts", result.stdout)
            self.assertIn("| predicate | 1 |", result.stdout)
            self.assertIn("## Records", result.stdout)
            self.assertIn(
                "| helpers.py | 1 | function | main | auto_helper | _ready | predicate |",
                result.stdout,
            )

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

    def test_redundant_identity_and_passthrough_helpers_are_marked(self) -> None:
        """Redundant identity and forwarding helpers should be explicit findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "redundant.py").write_text(
                dedent(
                    """
                    def normalize(value: str) -> str:
                        return value.strip()

                    def _same(value: str) -> str:
                        return value

                    def _wrap(value: str) -> str:
                        return normalize(value)

                    def _proxy(*args: object, **kwargs: object) -> object:
                        return normalize(*args, **kwargs)

                    def public_api(value: str) -> tuple[str, str, object]:
                        return _same(value), _wrap(value), _proxy(value)
                    """
                ).strip()
                + "\n",
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
            records = {record["qualname"]: record for record in json.loads(result.stdout)["records"]}
            self.assertTrue(records["_same"]["redundant_helper"])
            self.assertEqual(records["_same"]["redundancy_rule"], "identity-return")
            self.assertTrue(records["_wrap"]["redundant_helper"])
            self.assertEqual(records["_wrap"]["redundancy_rule"], "pass-through-return-internal")
            self.assertTrue(records["_proxy"]["redundant_helper"])
            self.assertEqual(records["_proxy"]["redundancy_rule"], "pass-through-return-internal")

    def test_duplicate_helper_implementations_are_marked(self) -> None:
        """Duplicate helper bodies should be linked as redundant alternatives."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "duplicates.py").write_text(
                dedent(
                    """
                    def _format(value: object) -> dict[str, str]:
                        return {'value': str(value)}

                    def _render(item: object) -> dict[str, str]:
                        return {'value': str(item)}

                    def public_api(value: object) -> tuple[dict[str, str], dict[str, str]]:
                        return _format(value), _render(value)
                    """
                ).strip()
                + "\n",
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
            records = {record["qualname"]: record for record in json.loads(result.stdout)["records"]}
            self.assertEqual(records["_format"]["redundancy_rule"], "duplicate-implementation")
            self.assertEqual(records["_render"]["redundancy_rule"], "duplicate-implementation")
            self.assertEqual(records["_format"]["redundant_with"], ["_render"])
            self.assertEqual(records["_render"]["redundant_with"], ["_format"])

    def test_multistep_orchestrator_with_forwarding_call_is_not_redundant(self) -> None:
        """A forwarding call inside a multi-step function should not imply redundancy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "orchestrator.py").write_text(
                dedent(
                    """
                    def normalize(value: str) -> str:
                        return value.strip()

                    def sink(value: str) -> None:
                        print(value)

                    def _orchestrate(value: str) -> str:
                        normalized = normalize(value)
                        sink(value)
                        return normalized

                    def public_api(value: str) -> str:
                        return _orchestrate(value)
                    """
                ).strip()
                + "\n",
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
            records = {record["qualname"]: record for record in json.loads(result.stdout)["records"]}
            self.assertFalse(records["_orchestrate"]["redundant_helper"])
            self.assertEqual(records["_orchestrate"]["redundancy_rule"], "")


if __name__ == "__main__":
    unittest.main()
