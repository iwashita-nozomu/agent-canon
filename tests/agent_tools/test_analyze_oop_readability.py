"""Tests for the OOP readability analyzer."""

# @dependency-start
# responsibility Tests OOP readability analyzer behavior.
# upstream implementation ../../tools/agent_tools/analyze_oop_readability.py analyzer
# upstream design ../../documents/object-oriented-design.md OOP boundary policy
# upstream design ../../agents/workflows/comprehensive-refactoring-workflow.md static analyzer gate
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANALYZER = PROJECT_ROOT / "tools" / "agent_tools" / "analyze_oop_readability.py"


class AnalyzeOopReadabilityTest(unittest.TestCase):
    """Verify analyzer scoring and finding output."""

    def run_analyzer(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the analyzer against a temporary root."""
        return subprocess.run(
            [sys.executable, str(ANALYZER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

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
            self.assertIn("none_runtime_branch:choose:1>typed-variant-boundary", result.stdout)

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
                        "  void run(int a, int b, int c, int d, int e, int f, int g) {}",
                        "};",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_analyzer(root, "--min-score", "100", str(source))

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

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cpp:info:null_runtime_branch:route:1>typed-reference-or-variant-boundary", result.stdout)

    def test_python_mathematical_redundancy_is_flagged(self) -> None:
        """Identity, pass-through, stateless callables, and formatting wrappers are reported."""
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

            result = self.run_analyzer(root, "--min-score", "100", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cpp:warn:trivial_format_function:format_value", result.stdout)

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

    def test_markdown_report_and_review_prompt_are_generated(self) -> None:
        """Markdown reports and reviewer prompts are generated without agent judgment."""
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
            self.assertIn("This report is generated by static heuristics", result.stdout)
            self.assertTrue(prompt.exists())
            self.assertIn("Do not invent new findings", prompt.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
