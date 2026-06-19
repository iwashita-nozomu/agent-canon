# @dependency-start
# contract test
# responsibility Tests Mermaid fenced-block formatter behavior.
# upstream implementation ../../tools/docs/fix_mermaid.py Mermaid formatter under test
# upstream implementation ../../tools/docs/format_markdown.py invokes Mermaid formatter
# @dependency-end
"""Tests for Mermaid fenced-block formatting."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIX_MERMAID = PROJECT_ROOT / "tools" / "docs" / "fix_mermaid.py"
FORMAT_MARKDOWN = PROJECT_ROOT / "tools" / "docs" / "format_markdown.py"


def load_module(path: Path) -> ModuleType:
    """Load a Python script as a module."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mermaid_formatter_normalizes_typo_fence_and_reserved_graph_node() -> None:
    """The formatter should detect Mermaid fences and avoid reserved node ids."""
    module = load_module(FIX_MERMAID)
    fix_mermaid_markdown = cast(
        Callable[[str], tuple[str, list[str]]],
        getattr(module, "fix_mermaid_markdown"),
    )
    source = """# Diagram

```mermeid
flowchart LR
  source[Markdown] --> ingest[ingest]
  ingest --> graph[(SQLite graph DB)]
  graph --> analyze[analyze graph overlays]
```
"""

    fixed, changes = fix_mermaid_markdown(source)

    assert "```mermaid" in fixed
    assert "```mermeid" not in fixed
    assert "ingest --> graph_node[(SQLite graph DB)]" in fixed
    assert "graph_node --> analyze[analyze graph overlays]" in fixed
    assert "SQLite graph DB" in fixed
    assert any("normalize Mermaid fence" in change for change in changes)
    assert any("reserved node id `graph`" in change for change in changes)


def test_mermaid_formatter_preserves_directive_graph_keyword() -> None:
    """Diagram directives should not be rewritten as node ids."""
    module = load_module(FIX_MERMAID)
    fix_mermaid_markdown = cast(
        Callable[[str], tuple[str, list[str]]],
        getattr(module, "fix_mermaid_markdown"),
    )
    source = """```mermaid
graph TD
  start --> graph[(Graph label)]
```
"""

    fixed, _ = fix_mermaid_markdown(source)

    assert fixed.startswith("```mermaid\ngraph TD\n")
    assert "start --> graph_node[(Graph label)]" in fixed


def test_mermaid_formatter_rewrites_line_initial_graph_node() -> None:
    """A line-initial reserved word with an edge is a node id, not a directive."""
    module = load_module(FIX_MERMAID)
    fix_mermaid_markdown = cast(
        Callable[[str], tuple[str, list[str]]],
        getattr(module, "fix_mermaid_markdown"),
    )
    source = """```mermaid
flowchart LR
  ingest --> graph
  graph --> analyze
```
"""

    fixed, _ = fix_mermaid_markdown(source)

    assert "ingest --> graph_node" in fixed
    assert "graph_node --> analyze" in fixed


def test_markdown_formatter_invokes_mermaid_formatter() -> None:
    """The general Markdown formatter should run Mermaid fixes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / "diagram.md"
        target.write_text(
            """# Diagram

```mermeid
flowchart LR
  ingest --> graph[(SQLite graph DB)]
  graph --> analyze[analyze]
```
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(FORMAT_MARKDOWN), str(target)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        text = target.read_text(encoding="utf-8")
        assert "```mermaid" in text
        assert "graph_node[(SQLite graph DB)]" in text
        assert "graph_node --> analyze[analyze]" in text
