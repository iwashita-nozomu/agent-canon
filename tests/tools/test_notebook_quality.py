"""Tests for notebook quality validation."""

# @dependency-start
# contract test
# responsibility Tests notebook quality validation for readable runnable demo notebooks.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/notebook_quality.rs validates notebook structure and content
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


def notebook(cells: list[dict[str, object]]) -> str:
    """Return a minimal notebook JSON document."""
    return json.dumps(
        {
            "cells": cells,
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                }
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    )


def markdown_cell(source: str) -> dict[str, object]:
    """Return one Markdown cell."""
    return {"cell_type": "markdown", "metadata": {}, "source": source}


def code_cell(source: str) -> dict[str, object]:
    """Return one code cell."""
    return {
        "cell_type": "code",
        "execution_count": 1,
        "metadata": {},
        "outputs": [],
        "source": source,
    }


def error_code_cell(source: str) -> dict[str, object]:
    """Return one code cell with stored error output."""
    return {
        "cell_type": "code",
        "execution_count": 1,
        "metadata": {},
        "outputs": [
            {
                "output_type": "error",
                "ename": "RuntimeError",
                "evalue": "boom",
                "traceback": [],
            }
        ],
        "source": source,
    }


class NotebookQualityTest(unittest.TestCase):
    """Exercise the notebook quality checker."""

    def run_checker(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """Run the checker against a fixture root."""
        if AGENT_CANON_CLI is None:
            raise RuntimeError(
                "AGENT_CANON_CLI must select the current native executable"
            )
        return subprocess.run(
            [
                AGENT_CANON_CLI,
                "notebook-quality",
                "--root",
                str(root),
                *args,
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_notebook(
        self, root: Path, relative: str, cells: list[dict[str, object]]
    ) -> Path:
        """Write one fixture notebook."""
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(notebook(cells), encoding="utf-8")
        return path

    def test_demo_notebook_passes(self) -> None:
        """A readable notebook with runnable visualization should pass."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self.write_notebook(
                root,
                "jupyter/demo.ipynb",
                [
                    markdown_cell(
                        "# Demo\n\n"
                        "This notebook explains the workflow, keeps tests in tests/, "
                        "and shows a compact visualization-oriented example for users."
                    ),
                    code_cell(
                        "import matplotlib.pyplot as plt\nplt.plot([0, 1], [0, 1])\nplt.show()"
                    ),
                ],
            )

            result = self.run_checker(root, str(path.relative_to(root)))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NOTEBOOK_QUALITY=pass", result.stdout)

    def test_fine_grained_test_notebook_fails(self) -> None:
        """Assertions and pytest usage belong in tests, not notebooks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self.write_notebook(
                root,
                "jupyter/testy.ipynb",
                [
                    markdown_cell(
                        "# Testy notebook\n\n"
                        "This has narrative text, but it still embeds detailed tests "
                        "that should live under tests/ instead."
                    ),
                    code_cell(
                        "import pytest\nassert 1 + 1 == 2\nplt.plot([0, 1], [0, 1])"
                    ),
                ],
            )

            result = self.run_checker(root, str(path.relative_to(root)))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fine-grained-assertion", result.stdout)
        self.assertIn("pytest-in-notebook", result.stdout)

    def test_missing_visualization_fails(self) -> None:
        """Notebooks should show runnable visualization code."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self.write_notebook(
                root,
                "jupyter/no_plot.ipynb",
                [
                    markdown_cell(
                        "# Demo without plot\n\n"
                        "This notebook has readable explanation, but no code that "
                        "demonstrates a visual output for the user."
                    ),
                    code_cell("values = [0, 1, 2]\nvalues"),
                ],
            )

            result = self.run_checker(root, str(path.relative_to(root)))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("missing-visualization", result.stdout)

    def test_error_output_warns(self) -> None:
        """Stored error outputs should warn without blocking demo notebooks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = self.write_notebook(
                root,
                "jupyter/error.ipynb",
                [
                    markdown_cell(
                        "# Demo with error\n\n"
                        "This notebook has enough explanation and a plot call, "
                        "but the stored output records a failed execution."
                    ),
                    error_code_cell(
                        "import matplotlib.pyplot as plt\nplt.plot([0], [0])\nplt.show()"
                    ),
                ],
            )

            result = self.run_checker(root, str(path.relative_to(root)))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NOTEBOOK_QUALITY_WARNING=", result.stdout)
        self.assertIn("error-output", result.stdout)
        self.assertIn("NOTEBOOK_QUALITY=pass", result.stdout)

    def test_json_output_preserves_metrics_and_codepoint_counts(self) -> None:
        """JSON reports retain their fields and count Markdown code points."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            markdown = "# Demo\n\n" + "あ😀" * 60
            path = self.write_notebook(
                root,
                "jupyter/demo.ipynb",
                [
                    markdown_cell(markdown),
                    code_cell("import matplotlib.pyplot as plt\nplt.plot([0], [1])"),
                ],
            )

            result = self.run_checker(
                root,
                "--format",
                "json",
                str(path.relative_to(root)),
            )

        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            set(payload),
            {"status", "findings", "warnings", "metrics"},
        )
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(
            payload["metrics"],
            [
                {
                    "path": "jupyter/demo.ipynb",
                    "markdown_cells": 1,
                    "code_cells": 1,
                    "visualization_cells": 1,
                    "error_outputs": 0,
                    "markdown_chars": len(markdown.strip()),
                }
            ],
        )

    def test_arbitrary_thresholds_match_python_integer_oracle(self) -> None:
        """Very large signed thresholds compare and render without narrowing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            markdown = "# Demo\n\nshort narrative"
            code = "\n".join("value = 1" for _ in range(81))
            positive = "9" * 100
            path = self.write_notebook(
                root,
                "jupyter/large.ipynb",
                [markdown_cell(markdown), code_cell(code)],
            )

            positive_result = self.run_checker(
                root,
                "--format",
                "json",
                "--max-code-cell-lines",
                positive,
                "--min-markdown-chars",
                positive,
                str(path.relative_to(root)),
            )

            negative = "-" + "٩" * 100
            negative_result = self.run_checker(
                root,
                "--format",
                "json",
                "--max-code-cell-lines",
                negative,
                "--min-markdown-chars",
                negative,
                str(path.relative_to(root)),
            )

        positive_payload = json.loads(positive_result.stdout)
        positive_findings = positive_payload["findings"]
        self.assertEqual(positive_result.returncode, 1, positive_result.stderr)
        self.assertNotIn(
            "oversized-code-cell", {item["check"] for item in positive_findings}
        )
        thin = next(
            item for item in positive_findings if item["check"] == "thin-narrative"
        )
        self.assertEqual(
            thin["detail"],
            f"{len(markdown.strip())} Markdown chars is below {int(positive)}",
        )

        negative_payload = json.loads(negative_result.stdout)
        negative_findings = negative_payload["findings"]
        oversized = next(
            item for item in negative_findings if item["check"] == "oversized-code-cell"
        )
        self.assertEqual(negative_result.returncode, 1, negative_result.stderr)
        self.assertEqual(oversized["line"], int(negative) + 1)
        self.assertEqual(oversized["detail"], f"81 lines exceeds {int(negative)}")
        self.assertNotIn(
            "thin-narrative", {item["check"] for item in negative_findings}
        )

    def test_unicode_integer_threshold_uses_python_int_semantics(self) -> None:
        """Unicode decimal digits parse like Python's int for CLI thresholds."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            markdown = "#" + "a" * 119
            path = self.write_notebook(
                root,
                "jupyter/unicode.ipynb",
                [
                    markdown_cell(markdown),
                    code_cell("import matplotlib.pyplot as plt\nplt.plot([0], [1])"),
                ],
            )

            threshold = "١٢١"
            result = self.run_checker(
                root,
                "--format",
                "json",
                "--min-markdown-chars",
                threshold,
                str(path.relative_to(root)),
            )

        payload = json.loads(result.stdout)
        thin = next(
            item for item in payload["findings"] if item["check"] == "thin-narrative"
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            thin["detail"],
            f"{len(markdown.strip())} Markdown chars is below {int(threshold)}",
        )

    def test_changed_mode_discovers_modified_notebook(self) -> None:
        """Changed mode should inspect tracked notebook edits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=root, check=True
            )
            path = self.write_notebook(
                root,
                "jupyter/demo.ipynb",
                [
                    markdown_cell(
                        "# Demo\n\nReadable notebook narrative with visualization."
                    ),
                    code_cell("import matplotlib.pyplot as plt\nplt.plot([0], [0])"),
                ],
            )
            subprocess.run(
                ["git", "add", "."], cwd=root, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "initial"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            path.write_text(
                notebook(
                    [
                        markdown_cell(
                            "# Demo\n\nReadable notebook narrative with visualization."
                        ),
                        code_cell("assert True\nplt.plot([0], [0])"),
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_checker(root, "--changed")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fine-grained-assertion", result.stdout)


if __name__ == "__main__":
    unittest.main()
