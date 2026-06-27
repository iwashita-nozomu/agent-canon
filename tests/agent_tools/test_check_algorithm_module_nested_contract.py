# @dependency-start
# contract test
# responsibility Tests algorithm module nested ownership checker behavior.
# upstream implementation ../../tools/agent_tools/check_algorithm_module_nested_contract.py checker
# upstream design ../../documents/design/jax_util/algorithm_module_contract.md algorithm boundary policy
# @dependency-end
"""Tests for the algorithm module nested ownership checker."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    PROJECT_ROOT
    / "tools"
    / "agent_tools"
    / "check_algorithm_module_nested_contract.py"
)

STANDARD_CHILD_SOURCE = "\n".join(
    [
        "from jax_util.base import algorithm_module_protocol as amp",
        "",
        "class InitializeConfig(amp.InitializeConfig):",
        "    pass",
        "",
        "class SolveConfig(amp.SolveConfig):",
        "    pass",
        "",
        "class Problem(amp.Problem):",
        "    pass",
        "",
        "class State(amp.State):",
        "    pass",
        "",
        "class Answer(amp.Answer):",
        "    pass",
        "",
        "class Info(amp.Info):",
        "    pass",
        "",
        "class Algorithm(amp.Algorithm):",
        "    pass",
        "",
        "def initialize(config: InitializeConfig) -> tuple[Algorithm, State]:",
        "    return Algorithm(), State()",
        "",
        "__all__ = [",
        '    "InitializeConfig",',
        '    "SolveConfig",',
        '    "Problem",',
        '    "State",',
        '    "Answer",',
        '    "Info",',
        '    "Algorithm",',
        '    "initialize",',
        "]",
        "",
    ]
)

COMPLIANT_PARENT_SOURCE = "\n".join(
    [
        "from jax_util.base import algorithm_module_protocol as amp",
        "from . import child",
        "",
        "class InitializeConfig(amp.InitializeConfig):",
        "    child_initialize: child.InitializeConfig",
        "",
        "class SolveConfig(amp.SolveConfig):",
        "    child_solve: child.SolveConfig",
        "",
        "class Problem(amp.Problem):",
        "    pass",
        "",
        "class State(amp.State):",
        "    pass",
        "",
        "class Answer(amp.Answer):",
        "    pass",
        "",
        "class Info(amp.Info):",
        "    pass",
        "",
        "class Algorithm(amp.Algorithm):",
        "    child_algorithm: child.Algorithm",
        "",
        "def initialize(config: InitializeConfig) -> tuple[Algorithm, State]:",
        "    child.initialize(config.child_initialize)",
        "    return Algorithm(), State()",
        "",
        "__all__ = [",
        '    "InitializeConfig",',
        '    "SolveConfig",',
        '    "Problem",',
        '    "State",',
        '    "Answer",',
        '    "Info",',
        '    "Algorithm",',
        '    "initialize",',
        "]",
        "",
    ]
)


class AlgorithmModuleNestedContractTest(unittest.TestCase):
    """Verify nested algorithm ownership checking."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the nested contract checker."""
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_module_tree(self, root: Path, parent_source: str) -> Path:
        """Write a parent/child algorithm module fixture."""
        package = root / "pkg"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "child.py").write_text(STANDARD_CHILD_SOURCE, encoding="utf-8")
        parent = package / "parent.py"
        parent.write_text(parent_source, encoding="utf-8")
        return parent

    def test_compliant_nested_dependency_passes(self) -> None:
        """A parent module holding child config/algorithm surfaces passes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(root, COMPLIANT_PARENT_SOURCE)

            result = self.run_checker(root, str(parent))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ALGORITHM_NESTED_CONTRACT=pass", result.stdout)

    def test_summary_info_can_omit_nested_child_info(self) -> None:
        """A parent ``Info`` can summarize nested calls without owning child ``Info``."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(root, COMPLIANT_PARENT_SOURCE)

            result = self.run_checker(root, str(parent))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ALGORITHM_NESTED_CONTRACT=pass", result.stdout)

    def test_initialize_call_requires_owned_child_algorithm(self) -> None:
        """A child ``initialize`` call requires the parent ``Algorithm`` to own it."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(
                root,
                COMPLIANT_PARENT_SOURCE.replace(
                    "    child_algorithm: child.Algorithm",
                    "    pass",
                ),
            )

            result = self.run_checker(root, str(parent))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_nested_field:child:Algorithm", result.stdout)

    def test_config_field_initialize_requires_owned_initialize_config(self) -> None:
        """Passing ``config.<field>`` to child init requires a parent config field."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(
                root,
                COMPLIANT_PARENT_SOURCE.replace(
                    "    child_initialize: child.InitializeConfig",
                    "    pass",
                ),
            )

            result = self.run_checker(root, str(parent))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_nested_field:child:InitializeConfig", result.stdout)

    def test_derived_initialize_config_does_not_require_parent_field(self) -> None:
        """A locally constructed child config need not be duplicated in parent config."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(
                root,
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "from . import child",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    pass",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    pass",
                        "",
                        "class Problem(amp.Problem):",
                        "    pass",
                        "",
                        "class State(amp.State):",
                        "    pass",
                        "",
                        "class Answer(amp.Answer):",
                        "    pass",
                        "",
                        "class Info(amp.Info):",
                        "    pass",
                        "",
                        "class Algorithm(amp.Algorithm):",
                        "    child_algorithm: child.Algorithm",
                        "",
                        "def initialize(config: InitializeConfig) -> tuple[Algorithm, State]:",
                        "    child.initialize(child.InitializeConfig())",
                        "    return Algorithm(), State()",
                        "",
                        "__all__ = [",
                        '    "InitializeConfig",',
                        '    "SolveConfig",',
                        '    "Problem",',
                        '    "State",',
                        '    "Answer",',
                        '    "Info",',
                        '    "Algorithm",',
                        '    "initialize",',
                        "]",
                        "",
                    ]
                ),
            )

            result = self.run_checker(root, str(parent))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_problem_only_usage_is_exempt(self) -> None:
        """Using only a child ``Problem`` does not require nested ownership fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(
                root,
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "from . import child",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    pass",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    pass",
                        "",
                        "class Problem(amp.Problem):",
                        "    child_problem: child.Problem",
                        "",
                        "class State(amp.State):",
                        "    pass",
                        "",
                        "class Answer(amp.Answer):",
                        "    pass",
                        "",
                        "class Info(amp.Info):",
                        "    pass",
                        "",
                        "class Algorithm(amp.Algorithm):",
                        "    pass",
                        "",
                        "def initialize(config: InitializeConfig) -> tuple[Algorithm, State]:",
                        "    return Algorithm(), State()",
                        "",
                        "__all__ = [",
                        '    "InitializeConfig",',
                        '    "SolveConfig",',
                        '    "Problem",',
                        '    "State",',
                        '    "Answer",',
                        '    "Info",',
                        '    "Algorithm",',
                        '    "initialize",',
                        "]",
                        "",
                    ]
                ),
            )

            result = self.run_checker(root, str(parent))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ALGORITHM_NESTED_CONTRACT_DEPENDENCIES=0", result.stdout)

    def test_type_alias_expansion_passes(self) -> None:
        """A private type alias can carry the concrete nested surfaces."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(
                root,
                COMPLIANT_PARENT_SOURCE.replace(
                    "class SolveConfig(amp.SolveConfig):\n    child_solve: child.SolveConfig",
                    "_ChildSolveConfig = child.SolveConfig\n\nclass SolveConfig(amp.SolveConfig):\n    child_solve: _ChildSolveConfig",
                ),
            )

            result = self.run_checker(root, str(parent))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_json_output_reports_findings(self) -> None:
        """JSON output is deterministic for automation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(root, COMPLIANT_PARENT_SOURCE)

            result = self.run_checker(root, "--format", "json", str(parent))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["status"], "pass")
            self.assertEqual(payload["findings"], [])


if __name__ == "__main__":
    unittest.main()
