# @dependency-start
# contract test
# responsibility Tests Rust markdown math check behavior.
# upstream implementation ../../rust/agent-canon/src/docs.rs implements docs check.
# upstream design ../../tools/README.md validates automation surface.
# @dependency-end

"""Tests for the markdown math notation checker."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


class CheckMarkdownMathTest(unittest.TestCase):
    """Exercise markdown math notation checks through the CLI."""

    def run_cli(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker and capture output."""
        return subprocess.run(
            [str(AGENT_CANON), "docs", "check", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_file(self, path: Path, contents: str) -> None:
        """Create one markdown file with parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")

    def test_passes_for_dollar_inline_and_double_dollar_display(self) -> None:
        """Inline math should use $...$ and display math should use $$...$$."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "Inline math uses $x + y$ in a sentence.",
                        "",
                        "$$",
                        "x + y = z",
                        "$$",
                        "",
                        "$$a^2 + b^2 = c^2$$",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("DOCS_CHECK=pass", result.stdout)

    def test_fails_on_legacy_latex_delimiters(self) -> None:
        """Legacy LaTeX delimiters should be rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        r"Inline \(x + y\) is not allowed.",
                        r"\[x + y = z\]",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn(r"inline math must use `$...$`, not `\(...\)`", result.stderr)
            self.assertIn(r"display math must use `$$...$$`, not `\[...\]`", result.stderr)

    def test_fails_on_inline_double_dollar_math(self) -> None:
        """Inline math should not use display delimiters."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "# Doc\n\nInline $$x + y$$ should fail.\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn("inline math must use `$...$`, not `$$...$$`", result.stderr)

    def test_fails_on_standalone_single_dollar_display(self) -> None:
        """Display math should not use single-dollar delimiters on its own line."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "# Doc\n\n$x + y = z$\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "display math must use `$$...$$`, not `$...$` on its own line", result.stderr
            )

    def test_fails_on_single_dollar_block_delimiters(self) -> None:
        """Display blocks should not use single-dollar delimiter lines."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "# Doc\n\n$\nx + y = z\n$\n",
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "display math must use `$$...$$`, not `$` block delimiters", result.stderr
            )

    def test_fails_on_optimization_block_in_text_fence(self) -> None:
        """Optimization notation in a text fence is forbidden."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        "minimize c^T x",
                        "    x <= y",
                        "subject to:",
                        "    x >= y",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "mathematical notation must use standalone `$$` display math, "
                "not a `text` fenced block",
                result.stderr,
            )
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 4)
            for line_number in (4, 5, 6, 7):
                self.assertIn(
                    f"DOCS_CHECK_FINDING=markdown-math:doc.md:{line_number}:",
                    result.stderr,
                )

    def test_fails_on_set_builder_constraints_in_plaintext_fence(self) -> None:
        """Set-builder style constraints in plaintext should use display math fences."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```plaintext",
                        "{ x for x in X if x <= y and x >= 0 }",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "mathematical notation must use standalone `$$` display math, "
                "not a `plaintext` fenced block",
                result.stderr,
            )

    def test_fails_on_explicit_math_delimiters_in_text_fences(self) -> None:
        """Whole-line math delimiters in text-like fences are forbidden."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        "$x+y$",
                        "$$",
                        "```",
                        "",
                        "```plaintext",
                        r"\(x+y\)",
                        r"\[x+y\]",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "mathematical notation must use standalone `$$` display math, "
                "not a `text` fenced block",
                result.stderr,
            )
            self.assertIn(
                "mathematical notation must use standalone `$$` display math, "
                "not a `plaintext` fenced block",
                result.stderr,
            )
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 4)

    def test_fails_on_compact_inequalities_in_text_fence(self) -> None:
        """Compact less-than-or-equal and greater-than-or-equal remain math."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        "x<=y",
                        "x>=0",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 2)

    def test_fails_on_spaced_mathematical_equalities(self) -> None:
        """Math atoms on both sides make spaced equality math."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        "G = (V, E)",
                        "A_eq x = b_eq",
                        "Q = mu I",
                        "benchmark latency = 12 ms",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 3)

    def test_passes_literal_spaced_equality(self) -> None:
        """A natural-language metric assignment is not mathematical notation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        "benchmark latency = 12 ms",
                        "status = pass",
                        "output = /tmp/result.txt",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("DOCS_CHECK=pass", result.stdout)

    def test_fails_on_numeric_and_function_equalities(self) -> None:
        """Numeric literals and deterministic function atoms form equations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        "x = 0",
                        "x = 1.0",
                        "f(x) = 0",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 3)

    def test_fails_on_math_with_literal_spans_on_the_same_line(self) -> None:
        """Literal spans do not hide mathematical syntax elsewhere on a line."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        "x = 0 -> status",
                        "x <= y https://example.com",
                        "x = 0 <pass|fail>",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 3)

    def test_fails_on_ascii_and_unicode_binary_relations(self) -> None:
        """Compact, spaced, and Unicode relations require math operands."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        "x<y",
                        "x>y",
                        "x ≤ y",
                        "x≠y",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 4)

    def test_fails_on_inline_math_inside_text_fence(self) -> None:
        """Explicit math delimiters are rejected even when prose shares the line."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```TEXT prose",
                        "The value is $x + y$ here.",
                        r"The constraint is \(x \le y\).",
                        "Use $HOME for the literal shell variable.",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 2)

    def test_supports_case_insensitive_text_and_math_aliases(self) -> None:
        """Documented fence aliases are normalized from the first info token."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```TXT",
                        "x<=y",
                        "```",
                        "",
                        "```plain title",
                        "x = y",
                        "```",
                        "",
                        "```TEX",
                        "plain payload",
                        "```",
                        "",
                        "```LaTeX",
                        "another payload",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 4)
            self.assertIn("not a `txt` fenced block", result.stderr)
            self.assertIn("not a `plain` fenced block", result.stderr)
            self.assertIn("not a `tex` fenced block", result.stderr)
            self.assertIn("not a `latex` fenced block", result.stderr)

    def test_fails_on_math_alias_fence(self) -> None:
        """Every nonblank math/latex fence payload is declared math."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```math",
                        "plain payload",
                        "```",
                        "",
                        "```latex",
                        "another payload",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "mathematical notation must use standalone `$$` display math, "
                "not a `math` fenced block",
                result.stderr,
            )
            self.assertIn(
                "mathematical notation must use standalone `$$` display math, "
                "not a `latex` fenced block",
                result.stderr,
            )
            self.assertEqual(result.stderr.count("DOCS_CHECK_FINDING=markdown-math"), 2)

    def test_fails_on_tilde_math_like_fence(self) -> None:
        """Tilde fences must also be checked for math-like payload."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "~~~math",
                        "x = y",
                        "~~~",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "mathematical notation must use standalone `$$` display math, "
                "not a `math` fenced block",
                result.stderr,
            )

    def test_passes_with_proper_double_dollar(self) -> None:
        """Proper standalone double-dollar display math should pass."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "Inline notation can be $x + y$ in a sentence.",
                        "",
                        "$$",
                        "x + y = z",
                        "$$",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("DOCS_CHECK=pass", result.stdout)

    def test_passes_literal_output_and_protocol_lines_in_text_fence(self) -> None:
        """Literal output and protocol syntax in a text fence should pass."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        "STATUS=pass",
                        "CUDA_VISIBLE_DEVICES=1",
                        "x=[1. 2.]",
                        "status = pass",
                        "output = /tmp/result.txt",
                        'assignment = "read-only"',
                        "R<integer>=<pass|fail|malformed>: <short evidence>",
                        "command=<exact proposed command or none>",
                        "`protocol = literal`",
                        "endpoint = https://example.com",
                        "source -> target = routed",
                        "<div>literal output</div>",
                        '<span class="value">literal output</span>',
                        "version < 2",
                        "C:\\Users\\name",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("DOCS_CHECK=pass", result.stdout)

    def test_passes_currency_and_shell_variables_in_text_fence(self) -> None:
        """Currency and shell-variable dollars are not math delimiters."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```text",
                        'echo "$5 + $10"',
                        'echo "$HOME/$PATH"',
                        "price is $5",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("DOCS_CHECK=pass", result.stdout)

    def test_passes_literal_output_and_protocol_lines_in_python_fence(self) -> None:
        """Typed source fences are exempt from math-like content heuristics."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_file(
                root / "doc.md",
                "\n".join(
                    [
                        "# Doc",
                        "",
                        "```python",
                        "STATUS=pass, CUDA_VISIBLE_DEVICES=1",
                        "x=[1. 2.]",
                        "protocol=foo://bar",
                        "x -> y",
                        "```",
                        "",
                    ]
                ),
            )

            result = self.run_cli(root, "doc.md")

            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("DOCS_CHECK=pass", result.stdout)


if __name__ == "__main__":
    unittest.main()
