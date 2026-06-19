"""Tests for notebook quality validation."""

# @dependency-start
# contract test
# responsibility Tests notebook quality validation for readable runnable demo notebooks.
# upstream implementation ../../tools/validation/notebook_quality.py validates notebook structure and content
# @dependency-end

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKER = PROJECT_ROOT / "tools" / "validation" / "notebook_quality.py"


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
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), *args],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def write_notebook(self, root: Path, relative: str, cells: list[dict[str, object]]) -> Path:
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
                    code_cell("import matplotlib.pyplot as plt\nplt.plot([0, 1], [0, 1])\nplt.show()"),
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
                    code_cell("import pytest\nassert 1 + 1 == 2\nplt.plot([0, 1], [0, 1])"),
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
                    error_code_cell("import matplotlib.pyplot as plt\nplt.plot([0], [0])\nplt.show()"),
                ],
            )

            result = self.run_checker(root, str(path.relative_to(root)))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("NOTEBOOK_QUALITY_WARNING=", result.stdout)
        self.assertIn("error-output", result.stdout)
        self.assertIn("NOTEBOOK_QUALITY=pass", result.stdout)

    def test_changed_mode_discovers_modified_notebook(self) -> None:
        """Changed mode should inspect tracked notebook edits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
            path = self.write_notebook(
                root,
                "jupyter/demo.ipynb",
                [
                    markdown_cell("# Demo\n\nReadable notebook narrative with visualization."),
                    code_cell("import matplotlib.pyplot as plt\nplt.plot([0], [0])"),
                ],
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True)
            path.write_text(
                notebook(
                    [
                        markdown_cell("# Demo\n\nReadable notebook narrative with visualization."),
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
