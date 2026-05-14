"""Tests for the OOP readability analyzer."""

# @dependency-start
# responsibility Tests OOP readability analyzer behavior.
# upstream implementation ../../tools/oop/python/readability.py Python analyzer
# upstream implementation ../../tools/oop/cpp/readability.py C++ analyzer
# upstream design ../../documents/object-oriented-design.md OOP boundary policy
# upstream design ../../agents/workflows/comprehensive-refactoring-workflow.md OOP gate
# @dependency-end

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ANALYZER = PROJECT_ROOT / "tools" / "oop" / "python" / "readability.py"
CPP_ANALYZER = PROJECT_ROOT / "tools" / "oop" / "cpp" / "readability.py"
EMPTY_ENV: Mapping[str, str] = MappingProxyType({})


class AnalyzeOopReadabilityTest(unittest.TestCase):
    """Verify analyzer scoring and finding output."""

    def run_analyzer(
        self,
        root: Path,
        *args: str,
        env: Mapping[str, str] = EMPTY_ENV,
    ) -> subprocess.CompletedProcess[str]:
        """Run the analyzer against a temporary root."""
        return subprocess.run(
            [sys.executable, str(PYTHON_ANALYZER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, **env},
        )

    def run_cpp_analyzer(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the C++ analyzer against a temporary root."""
        return subprocess.run(
            [sys.executable, str(CPP_ANALYZER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def git(self, root: Path, *args: str) -> None:
        """Run a git command in a temporary analyzer fixture."""
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    def commit_all(self, root: Path) -> None:
        """Commit the current temporary fixture contents."""
        self.git(root, "add", ".")
        self.git(root, "commit", "-m", "baseline")

    def test_small_python_value_object_passes(self) -> None:
        """A small dataclass-style value object should pass the default score gate."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "model.py"
            source.write_text(
                "\n".join(
                    [
                        "from dataclasses import dataclass",
                        "",
                        "@dataclass(frozen=True)",
                        "class Result:",
                        "    value: int",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OOP_READABILITY_FILES=1", result.stdout)
            self.assertIn("OOP_READABILITY_FINDINGS=0", result.stdout)
            self.assertIn("OOP_READABILITY=pass", result.stdout)

    def test_algorithm_protocol_value_classes_are_not_thin_classes(self) -> None:
        """Standard algorithm-module protocol classes are intentional contracts."""
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
                        "    def __call__(self, problem, state, config):",
                        "        return Answer(), State(), Info()",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("thin_class", result.stdout)

    def test_typing_protocol_is_not_a_thin_class_smell(self) -> None:
        """A typing Protocol is a contract boundary even before implementations exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "ports.py"
            source.write_text(
                "\n".join(
                    [
                        "from abc import ABC",
                        "from typing import Protocol",
                        "",
                        "class SolverPort(Protocol):",
                        "    def solve(self) -> object: ...",
                        "",
                        "class EmptyBase(ABC):",
                        "    pass",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("thin_class:SolverPort", result.stdout)
            self.assertNotIn("method_without_self_use:SolverPort.solve", result.stdout)
            self.assertIn("thin_class:EmptyBase", result.stdout)

    def test_ast_visitor_hooks_are_not_public_surface_width(self) -> None:
        """AST visitor methods are framework hooks rather than an owned public API."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "visitor.py"
            source.write_text(
                "\n".join(
                    [
                        "import ast",
                        "",
                        "class Collector(ast.NodeVisitor):",
                        "    def __init__(self) -> None:",
                        "        self.count = 0",
                        "",
                        *[
                            f"    def visit_Node{index}(self, node: ast.AST) -> None: self.count += 1"
                            for index in range(14)
                        ],
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("public_methods:Collector", result.stdout)

    def test_algorithm_config_factories_are_not_namespace_smells(self) -> None:
        """Named algorithm config constructors are the module contract DSL."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "solver.py"
            source.write_text(
                "\n".join(
                    [
                        "from jax_util.base import algorithm_module_protocol as amp",
                        "",
                        "class InitializeConfig(amp.InitializeConfig):",
                        "    kind: str",
                        "",
                        "    @staticmethod",
                        "    def identity() -> 'InitializeConfig':",
                        "        return InitializeConfig(kind='identity')",
                        "",
                        "class SolveConfig(amp.SolveConfig):",
                        "    kind: str",
                        "",
                        "    @staticmethod",
                        "    def identity() -> 'SolveConfig':",
                        "        return SolveConfig(kind='identity')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("static_method_namespace", result.stdout)
            self.assertNotIn("pass_through_function", result.stdout)

    def test_symlink_and_source_paths_do_not_duplicate_findings(self) -> None:
        """Root symlink views and real source paths should deduplicate by real file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_dir = root / "vendor" / "agent-canon" / "tools"
            source_dir.mkdir(parents=True)
            (root / "tools").symlink_to(source_dir, target_is_directory=True)
            source = source_dir / "bad.py"
            source.write_text(
                "def helper_value(value: int) -> int:\n    return value\n",
                encoding="utf-8",
            )

            result = self.run_analyzer(
                root,
                "tools",
                "vendor/agent-canon/tools",
                "--min-score",
                "0",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OOP_READABILITY_FILES=1", result.stdout)
            self.assertEqual(result.stdout.count("module_helper_name"), 1)

    def test_baseline_ref_suppresses_existing_findings_after_line_shift(self) -> None:
        """Hook-style checks should not re-block debt that only moved lines."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.git(root, "init")
            self.git(root, "config", "user.email", "test@example.invalid")
            self.git(root, "config", "user.name", "Test User")
            source = root / "helpers.py"
            source.write_text(
                "def calculate_helper(value: int) -> int:\n    return value\n",
                encoding="utf-8",
            )
            self.commit_all(root)
            source.write_text(
                "\n".join(
                    [
                        "# shifted by an unrelated edit",
                        "def calculate_helper(value: int) -> int:",
                        "    return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(
                root,
                "--baseline-ref",
                "HEAD",
                "--min-score",
                "100",
                str(source),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OOP_READABILITY_FINDINGS=0", result.stdout)
            self.assertIn("OOP_READABILITY=pass", result.stdout)

    def test_baseline_ref_keeps_new_findings(self) -> None:
        """A baseline filter should still report newly introduced OOP risks."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.git(root, "init")
            self.git(root, "config", "user.email", "test@example.invalid")
            self.git(root, "config", "user.name", "Test User")
            source = root / "domain.py"
            source.write_text(
                "def domain_value(value: int) -> int:\n    return value + 1\n",
                encoding="utf-8",
            )
            self.commit_all(root)
            source.write_text(
                "\n".join(
                    [
                        "def domain_value(value: int) -> int:",
                        "    return value + 1",
                        "",
                        "def calculate_helper(value: int) -> int:",
                        "    return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(
                root,
                "--baseline-ref",
                "HEAD",
                "--min-score",
                "100",
                str(source),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("module_helper_name:calculate_helper", result.stdout)
            self.assertIn("OOP_READABILITY=fail", result.stdout)

    def test_private_and_nested_functions_are_not_public_boundary_findings(self) -> None:
        """Private helpers and closures do not create public API boundary findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "implementation.py"
            source.write_text(
                "\n".join(
                    [
                        "from typing import Any",
                        "",
                        "def _private(value: Any | None):",
                        "    if value is None:",
                        "        return 0",
                        "    return value",
                        "",
                        "def public(value: int) -> int:",
                        "    def branch(inner):",
                        "        return inner",
                        "    return branch(value)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("optional_boundary:_private", result.stdout)
            self.assertNotIn("none_runtime_branch:_private", result.stdout)
            self.assertNotIn("missing_public_annotations:branch", result.stdout)

    def test_python_vague_static_namespace_is_flagged(self) -> None:
        """A vague utility class with static methods is reported."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "helpers.py"
            source.write_text(
                "\n".join(
                    [
                        "class DataHelper:",
                        "    @staticmethod",
                        "    def calculate(value):",
                        "        if value:",
                        "            return value",
                        "        return 0",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("vague_class_name:DataHelper", result.stdout)
            self.assertIn("static_method_namespace:DataHelper", result.stdout)
            self.assertIn("missing_public_annotations:calculate", result.stdout)

    def test_python_vague_static_namespace_fails_default_gate(self) -> None:
        """The default OOP score gate should not pass namespace-class findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "helpers.py"
            source.write_text(
                "\n".join(
                    [
                        "class DataHelper:",
                        "    @staticmethod",
                        "    def calculate(value):",
                        "        return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("OOP_READABILITY_SCORE=", result.stdout)
            self.assertIn("OOP_READABILITY=fail", result.stdout)

    def test_python_optional_none_boundary_is_flagged(self) -> None:
        """Optional public boundaries and None routing are reported."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "routing.py"
            source.write_text(
                "\n".join(
                    [
                        "def choose(value: int | None) -> int:",
                        "    if value is None:",
                        "        return 0",
                        "    return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("optional_boundary:choose:1>0", result.stdout)
            self.assertIn(
                "none_runtime_branch:choose:1>typed-variant-boundary",
                result.stdout,
            )

    def test_python_module_helper_name_is_flagged(self) -> None:
        """Module-level helper buckets are discouraged in favor of local helpers."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "helpers.py"
            source.write_text(
                "\n".join(
                    [
                        "def calculate_helper(value: int) -> int:",
                        "    return value + 1",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("module_helper_name:calculate_helper", result.stdout)

    def test_python_local_aggregation_is_not_mixed_effect(self) -> None:
        """Mutating a function-owned accumulator is not an external effect boundary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "rendering.py"
            source.write_text(
                "\n".join(
                    [
                        "def render_lines(values: tuple[int, ...]) -> str:",
                        "    lines: list[str] = []",
                        "    for value in values:",
                        "        lines.append(str(value))",
                        "    return '\\n'.join(lines)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("mixed_morphism_effect:render_lines", result.stdout)

    def test_python_boundary_mutation_is_mixed_effect(self) -> None:
        """Mutating caller-owned inputs remains an effect boundary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "mutation.py"
            source.write_text(
                "\n".join(
                    [
                        "def collect(values: list[int], value: int) -> list[int]:",
                        "    values.append(value)",
                        "    return values",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("mixed_morphism_effect:collect", result.stdout)

    def test_cpp_public_surface_is_flagged(self) -> None:
        """A C++ class with wide public state and vague name is reported."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "model.hpp"
            source.write_text(
                "\n".join(
                    [
                        "class SolverManager {",
                        "public:",
                        "  int a;",
                        "  int b;",
                        "  int c;",
                        "  int d;",
                        "  int e;",
                        "  int f;",
                        "  int g;",
                        "  int h;",
                        "  int i;",
                        (
                            "  void run(int a, int b, int c, int d, int e, "
                            "int f, int g) {}"
                        ),
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cpp_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cpp:warn:vague_class_name:SolverManager", result.stdout)
            self.assertIn("cpp:warn:public_fields:SolverManager:9>8", result.stdout)
            self.assertIn("cpp:warn:parameters:run:7>6", result.stdout)

    def test_cpp_null_runtime_branch_is_flagged(self) -> None:
        """Null-driven C++ routing is reported as a readability risk."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "route.cpp"
            source.write_text(
                "\n".join(
                    [
                        "int route(int* value) {",
                        "  if (value == nullptr) {",
                        "    return 0;",
                        "  }",
                        "  return *value;",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cpp_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "cpp:warn:null_runtime_branch:route:1>typed-reference-or-variant-boundary",
                result.stdout,
            )

    def test_cpp_raw_string_fixture_is_not_analyzed_as_product_code(self) -> None:
        """Embedded C++ fixture text should not create product-code findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "fixture.cpp"
            source.write_text(
                "\n".join(
                    [
                        'const char* fixture = R"cpp(',
                        "struct FixtureInput {",
                        "  int a;",
                        "  int b;",
                        "  int c;",
                        "};",
                        ")cpp\";",
                        "struct RealInput {",
                        "  int a;",
                        "  int b;",
                        "  int c;",
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cpp_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("FixtureInput", result.stdout)
            self.assertIn("state_heavy_public_surface:RealInput", result.stdout)
            self.assertIn("fixture.cpp:8:cpp", result.stdout)

    def test_cpp_comment_quotes_do_not_mask_real_code(self) -> None:
        """Comment-contained quotes must not suppress later C++ findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "comments.cpp"
            source.write_text(
                "\n".join(
                    [
                        "// don't let apostrophes mask the rest of the file",
                        '/* "quoted block comment" stays non-code */',
                        "struct RealInput {",
                        "  int a;",
                        "  int b;",
                        "  int c;",
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cpp_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("state_heavy_public_surface:RealInput", result.stdout)

    def test_cpp_unterminated_literals_do_not_mask_later_real_code(self) -> None:
        """Malformed literals are left visible rather than masking the rest of a file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "unterminated.cpp"
            source.write_text(
                "\n".join(
                    [
                        'const char* raw = R"cpp(',
                        "struct RealInput {",
                        "  int a;",
                        "  int b;",
                        "  int c;",
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cpp_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("state_heavy_public_surface:RealInput", result.stdout)

    def test_cpp_literal_lines_do_not_trigger_function_length(self) -> None:
        """Long fixture literals should not count as visible function body lines."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "long_fixture.cpp"
            source.write_text(
                "\n".join(
                    [
                        "int scenario() {",
                        '  const char* fixture = R"ir(',
                        *["  fixture payload" for _ in range(120)],
                        ')ir";',
                        "  return 0;",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cpp_analyzer(root, "--min-score", "100", str(source))

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("function_lines:scenario", result.stdout)

    def test_cpp_literal_lines_do_not_trigger_class_length(self) -> None:
        """Long fixture literals should not count as visible class body lines."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "long_fixture_class.cpp"
            source.write_text(
                "\n".join(
                    [
                        "class FixtureOwner {",
                        " private:",
                        '  const char* fixture = R"ir(',
                        *["  fixture payload" for _ in range(120)],
                        ')ir";',
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cpp_analyzer(
                root,
                "--min-score",
                "100",
                "--max-class-lines",
                "10",
                str(source),
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("class_lines:FixtureOwner", result.stdout)

    def test_cpp_comment_tokens_inside_literals_do_not_mask_real_code(self) -> None:
        """Literal-contained comment tokens must not suppress later C++ findings."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "literal_tokens.cpp"
            source.write_text(
                "\n".join(
                    [
                        'const char* block_marker = "/*";',
                        'const char* line_marker = "http://example.test";',
                        "struct RealInput {",
                        "  int a;",
                        "  int b;",
                        "  int c;",
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cpp_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("state_heavy_public_surface:RealInput", result.stdout)

    def test_python_mathematical_redundancy_is_flagged(self) -> None:
        """Identity, pass-through, stateless callables, and format wrappers are reported."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "redundant.py"
            source.write_text(
                "\n".join(
                    [
                        "class Projection:",
                        "    def __call__(self, value: int) -> int:",
                        "        return value",
                        "",
                        "def identity_value(value: int) -> int:",
                        "    return value",
                        "",
                        "def forward_value(value: int) -> int:",
                        "    return identity_value(value)",
                        "",
                        "def format_value(value: int) -> str:",
                        "    return f'{value}'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("stateless_callable_class:Projection", result.stdout)
            self.assertIn("identity_function:identity_value", result.stdout)
            self.assertIn("pass_through_function:forward_value", result.stdout)
            self.assertIn("trivial_format_function:format_value", result.stdout)

    def test_python_redundant_class_uses_dependency_sources(self) -> None:
        """Class redundancy should use incoming construction and type-boundary facts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            package = root / "package"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "model.py").write_text(
                "\n".join(
                    [
                        "class Projection:",
                        "    def run(self, value: int) -> int:",
                        "        return value",
                        "",
                        "class Port:",
                        "    def run(self, value: int) -> int:",
                        "        return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (package / "service.py").write_text(
                "\n".join(
                    [
                        "from .model import Port, Projection",
                        "",
                        "def compute(value: int) -> int:",
                        "    projection = Projection()",
                        "    return projection.run(value)",
                        "",
                        "def accepts_port(port: Port, value: int) -> int:",
                        "    return port.run(value)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            model = package / "model.py"

            result = self.run_analyzer(root, "--min-score", "100", str(model))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("redundant_class_boundary:Projection", result.stdout)
            self.assertNotIn("redundant_class_boundary:Port", result.stdout)

    def test_python_usage_root_extends_redundant_class_construction_sources(self) -> None:
        """Explicit usage roots should inform selected-file redundant class analysis."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            library = root / "library"
            consumer = root / "consumer"
            library.mkdir()
            consumer.mkdir()
            model = library / "model.py"
            model.write_text(
                "\n".join(
                    [
                        "class Projection:",
                        "    def run(self, value: int) -> int:",
                        "        return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (consumer / "consumer.py").write_text(
                "\n".join(
                    [
                        "from model import Projection",
                        "",
                        "def compute(value: int) -> int:",
                        "    projection = Projection()",
                        "    return projection.run(value)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(
                library,
                "--min-score",
                "100",
                "--usage-root",
                str(consumer),
                str(model),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("redundant_class_boundary:Projection", result.stdout)

    def test_python_dependency_module_extends_type_boundary_sources(self) -> None:
        """Importable dependency modules should contribute type-boundary evidence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            library = root / "library"
            downstream = root / "downstream"
            library.mkdir()
            downstream.mkdir()
            (downstream / "__init__.py").write_text("", encoding="utf-8")
            model = library / "model.py"
            model.write_text(
                "\n".join(
                    [
                        "class Port:",
                        "    def run(self, value: int) -> int:",
                        "        return value",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (downstream / "consumer.py").write_text(
                "\n".join(
                    [
                        "from model import Port",
                        "",
                        "def accepts_port(port: Port, value: int) -> int:",
                        "    return port.run(value)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(
                library,
                "--min-score",
                "100",
                "--dependency-module",
                "downstream",
                str(model),
                env={"PYTHONPATH": os.pathsep.join([str(library), str(root)])},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("redundant_class_boundary:Port", result.stdout)

    def test_cpp_trivial_format_function_is_flagged(self) -> None:
        """C++ format-only wrappers are reported as mathematical redundancy."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "format.cpp"
            source.write_text(
                "\n".join(
                    [
                        "#include <string>",
                        "std::string format_value(int value) {",
                        "  return std::to_string(value);",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cpp_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "cpp:warn:trivial_format_function:format_value",
                result.stdout,
            )

    def test_json_report_adds_mechanical_interpretation(self) -> None:
        """JSON output includes deterministic summary and explanation fields."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "formatting.py"
            source.write_text(
                "\n".join(
                    [
                        "def render_label(value: int) -> str:",
                        "    return str(value)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(
                root,
                "--format",
                "json",
                "--include-snippets",
                "--min-score",
                "100",
                str(source),
            )

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["status"], "fail")
            finding = payload["findings"][0]
            self.assertEqual(finding["dimension"], "mathematical redundancy")
            self.assertIn("snippet", finding)
            self.assertIn("mechanical_grade", payload["summary"])

    def test_exclude_skips_vendored_or_report_surfaces(self) -> None:
        """External scans can exclude vendored snapshots and generated reports."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            product = root / "python"
            vendor = root / "vendor" / "agent-canon"
            reports = root / "reports" / "agents"
            product.mkdir()
            vendor.mkdir(parents=True)
            reports.mkdir(parents=True)
            (product / "model.py").write_text(
                "\n".join(
                    [
                        "from dataclasses import dataclass",
                        "",
                        "@dataclass(frozen=True)",
                        "class Result:",
                        "    value: int",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            for path in (vendor / "helpers.py", reports / "helpers.py"):
                path.write_text(
                    "\n".join(
                        [
                            "class DataHelper:",
                            "    @staticmethod",
                            "    def calculate(value):",
                            "        return value",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

            result = self.run_analyzer(
                root,
                "--exclude",
                "vendor",
                "--exclude",
                "reports",
                "--min-score",
                "100",
                ".",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OOP_READABILITY_FILES=1", result.stdout)
            self.assertNotIn("DataHelper", result.stdout)

            markdown = self.run_analyzer(
                root,
                "--exclude",
                "vendor",
                "--exclude",
                "reports",
                "--min-score",
                "100",
                "--format",
                "markdown",
                ".",
            )
            self.assertEqual(markdown.returncode, 0, markdown.stdout + markdown.stderr)
            self.assertIn("excluded_patterns: `vendor, reports`", markdown.stdout)

    def test_markdown_report_and_review_prompt_are_generated(self) -> None:
        """Markdown reports and reviewer prompts are generated."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "formatting.py"
            prompt = root / "review_prompt.md"
            source.write_text(
                "\n".join(
                    [
                        "def render_label(value: int) -> str:",
                        "    return f'{value}'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(
                root,
                "--format",
                "markdown",
                "--include-snippets",
                "--review-prompt-out",
                str(prompt),
                "--min-score",
                "100",
                str(source),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("# OOP Readability Mechanical Report", result.stdout)
            self.assertIn("trivial_format_function", result.stdout)
            self.assertIn(
                "This report is generated by static heuristics",
                result.stdout,
            )
            self.assertTrue(prompt.exists())
            self.assertIn(
                "Do not invent new findings",
                prompt.read_text(encoding="utf-8"),
            )

    def test_run_bundle_timing_event_is_recorded_when_monitor_is_available(self) -> None:
        """Analyzer should append timing tokens when run-bundle monitoring is active."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            report_dir = root / "reports" / "agents" / "run-1"
            monitor = root / "tools" / "agent_tools" / "workflow_monitor.py"
            monitor.parent.mkdir(parents=True)
            monitor.write_text(
                "\n".join(
                    [
                        "import argparse",
                        "from pathlib import Path",
                        "parser = argparse.ArgumentParser()",
                        "parser.add_argument('--report-dir', required=True)",
                        "parser.add_argument('--behavior-event', required=True)",
                        "args = parser.parse_args()",
                        "path = Path(args.report_dir) / 'workflow_monitoring.md'",
                        "path.parent.mkdir(parents=True, exist_ok=True)",
                        "with path.open('a', encoding='utf-8') as stream:",
                        "    stream.write(args.behavior_event + '\\n')",
                    ]
                ),
                encoding="utf-8",
            )
            source = root / "model.py"
            source.write_text(
                "\n".join(
                    [
                        "from dataclasses import dataclass",
                        "",
                        "@dataclass(frozen=True)",
                        "class Result:",
                        "    value: int",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PYTHON_ANALYZER),
                    "--root",
                    str(root),
                    "model.py",
                ],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "AGENT_CANON_WORKFLOW_MONITOR_REPORT_DIR": str(report_dir),
                },
            )
            monitoring = (report_dir / "workflow_monitoring.md").read_text(
                encoding="utf-8"
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("tool_call=oop-readability-check", monitoring)
        self.assertIn("duration_ms=", monitoring)
        self.assertIn("status=pass", monitoring)
        self.assertIn("scope=model.py", monitoring)
        self.assertIn("output_path=stdout", monitoring)


if __name__ == "__main__":
    unittest.main()
