# @dependency-start
# contract test
# responsibility Tests algorithm config partition checker behavior.
# upstream implementation ../../tools/agent_tools/check_algorithm_config_partition.py checker
# upstream design ../../documents/design/jax_util/algorithm_module_contract.md config contract
# @dependency-end
"""Tests for the algorithm config partition checker."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOL = PROJECT_ROOT / "tools" / "agent_tools" / "check_algorithm_config_partition.py"


class CheckAlgorithmConfigPartitionTest(unittest.TestCase):
    """Verify InitializeConfig/SolveConfig ownership checks."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a temporary root."""
        return subprocess.run(
            [sys.executable, str(TOOL), "--root", str(root), "--format", "json", *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_initialize_only_config_is_allowed_in_initialize_config(self) -> None:
        """Run-log and nested InitializeConfig belong to InitializeConfig."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import RunLogConfig",
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class Child:",
                        "    class InitializeConfig(amp.InitializeConfig):",
                        "        pass",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    child_initialize: Child.InitializeConfig",
                        "    run_log: RunLogConfig",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    maxiter: int",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 0)

    def test_run_log_in_solve_config_is_flagged(self) -> None:
        """A RunLogConfig in SolveConfig is an initialization-owned sink contract."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import RunLogConfig",
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    pass",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    run_log: RunLogConfig",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 1)
            self.assertEqual(payload["findings"][0]["expected_owner"], "InitializeConfig")

    def test_child_initialize_config_in_solve_config_is_flagged(self) -> None:
        """Child InitializeConfig cannot be changed by a solve-time config."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class child:",
                        "    class InitializeConfig(amp.InitializeConfig):",
                        "        pass",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    pass",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    child_initialize: child.InitializeConfig",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 1)
            self.assertEqual(
                payload["findings"][0]["reason"],
                "initialization-only config type in SolveConfig",
            )

    def test_child_solve_config_in_initialize_config_is_flagged(self) -> None:
        """Child SolveConfig is a runtime policy and belongs to SolveConfig."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class child:",
                        "    class SolveConfig(amp.SolveConfig):",
                        "        pass",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    child_solve: child.SolveConfig",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    pass",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 1)
            self.assertEqual(payload["findings"][0]["expected_owner"], "SolveConfig")

    def test_config_like_name_without_amp_base_is_ignored(self) -> None:
        """Do not infer config ownership from class names alone."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class Legacy:",
                        "    class InitializeConfig:",
                        "        pass",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    pass",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    legacy: Legacy.InitializeConfig",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 0)

    def test_imported_config_class_is_resolved_from_ast_imports(self) -> None:
        """Resolve imported config annotations through module AST, not suffixes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            package = root / "pkg"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "child.py").write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    pass",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            source = package / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "from . import child",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    pass",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    child_initialize: child.InitializeConfig",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(package))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 1)
            self.assertEqual(
                payload["findings"][0]["reason"],
                "initialization-only config type in SolveConfig",
            )

    def test_runtime_tolerance_is_allowed_in_solve_config(self) -> None:
        """Tolerance and stopping policy can vary between solve calls."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    default_rtol: str",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    maxiter: int",
                        "    rtol: str",
                        "    atol: str",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["findings"], 0)

    def test_runtime_default_parameter_is_flagged(self) -> None:
        """Callable defaults outside config ownership hide runtime policy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "def build_solver(*, maxiter: int = 100) -> object:",
                        "    return object()",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["runtime_default_errors"], 1)
            self.assertEqual(payload["default_findings"][0]["kind"], "keyword-parameter-default")

    def test_config_default_is_warning_not_runtime_error(self) -> None:
        """Config-owned defaults are visible migration targets, not hidden runtime defaults."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    seed: int = 0",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["runtime_default_errors"], 0)
            self.assertEqual(payload["summary"]["config_default_warnings"], 1)

    def test_mapping_get_implicit_default_is_flagged(self) -> None:
        """Mapping defaults should fail instead of inventing policy at read time."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "def read_config(payload: dict[str, object]) -> object:",
                        "    return payload.get('rtol', '1e-6')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["runtime_default_errors"], 1)
            self.assertEqual(payload["default_findings"][0]["kind"], "mapping-get-default")

    def test_non_amp_config_named_constructor_is_not_flagged_by_suffix(self) -> None:
        """Only amp-derived config constructors should be detected as config defaults."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "class Legacy:",
                        "    class InitializeConfig:",
                        "        pass",
                        "",
                        "def choose(value: object | None) -> object:",
                        "    return value or Legacy.InitializeConfig()",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["runtime_default_errors"], 0)

    def test_amp_config_constructor_implicit_default_is_resolved_from_ast(self) -> None:
        """Amp-derived config constructors remain visible through AST resolution."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    pass",
                        "",
                        "def choose(value: object | None) -> object:",
                        "    return value or InitializeConfig()",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            kinds = {finding["kind"] for finding in payload["default_findings"]}
            self.assertIn("or-implicit-default", kinds)
            self.assertIn("empty-config-constructor", kinds)

    def test_direct_protocol_config_import_is_resolved_from_ast(self) -> None:
        """Direct protocol config imports should not require the local name amp."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base.algorithm_module_protocol import InitializeConfig as BaseInitializeConfig",
                        "",
                        "class LocalInitializeConfig(BaseInitializeConfig):",
                        "    pass",
                        "",
                        "def choose(value: object | None) -> object:",
                        "    return value or LocalInitializeConfig()",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            kinds = {finding["kind"] for finding in payload["default_findings"]}
            self.assertIn("or-implicit-default", kinds)
            self.assertIn("empty-config-constructor", kinds)

    def test_unimported_amp_name_is_not_treated_as_protocol(self) -> None:
        """The local name amp must come from an AST import to mark config ownership."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    pass",
                        "",
                        "def choose(value: object | None) -> object:",
                        "    return value or InitializeConfig()",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["runtime_default_errors"], 0)


if __name__ == "__main__":
    unittest.main()
