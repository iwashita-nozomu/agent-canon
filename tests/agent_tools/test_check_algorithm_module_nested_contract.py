# @dependency-start
# responsibility Tests algorithm module nested ownership checker behavior.
# upstream implementation ../../tools/agent_tools/check_algorithm_module_nested_contract.py checker
# upstream design ../../documents/algorithm-implementation-boundary.md algorithm boundary policy
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
        "    child_info: child.Info",
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
        """A parent module holding child config/info/algorithm surfaces passes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(root, COMPLIANT_PARENT_SOURCE)

            result = self.run_checker(root, str(parent))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ALGORITHM_NESTED_CONTRACT=pass", result.stdout)

    def test_missing_nested_info_fails(self) -> None:
        """A child call requires the parent ``Info`` to hold child ``Info``."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            parent = self.write_module_tree(
                root,
                COMPLIANT_PARENT_SOURCE.replace(
                    "    child_info: child.Info",
                    "    pass",
                ),
            )

            result = self.run_checker(root, str(parent))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing_nested_field:child:Info", result.stdout)

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
                    "class Info(amp.Info):\n    child_info: child.Info",
                    "_ChildInfo = child.Info\n\nclass Info(amp.Info):\n    child_info: _ChildInfo",
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
