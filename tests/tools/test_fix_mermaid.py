# @dependency-start
# contract test
# responsibility Tests Rust Mermaid fenced-block formatter behavior.
# upstream implementation ../../rust/agent-canon/src/docs.rs implements docs format and fix-mermaid.
# @dependency-end
"""Tests for Mermaid fenced-block formatting."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON = PROJECT_ROOT / "tools" / "bin" / "agent-canon"


def test_mermaid_formatter_normalizes_typo_fence_and_reserved_graph_node() -> None:
    """The formatter should detect Mermaid fences and avoid reserved node ids."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / "diagram.md"
        target.write_text(
            """# Diagram

```mermeid
flowchart LR
  source[Markdown] --> ingest[ingest]
  ingest --> graph[(SQLite graph DB)]
  graph --> analyze[analyze graph overlays]
```
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [str(AGENT_CANON), "docs", "fix-mermaid", str(target)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        fixed = target.read_text(encoding="utf-8")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "DOCS_FIX_MERMAID=wrote" in result.stdout
    assert "DOCS_CHECK=pass" in result.stdout
    assert "```mermaid" in fixed
    assert "```mermeid" not in fixed
    assert "ingest --> graph_node[(SQLite graph DB)]" in fixed
    assert "graph_node --> analyze[analyze graph overlays]" in fixed
    assert "SQLite graph DB" in fixed


def test_mermaid_formatter_preserves_directive_graph_keyword() -> None:
    """Diagram directives should not be rewritten as node ids."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / "diagram.md"
        target.write_text(
            """# Diagram

```mermaid
graph TD
  start --> graph[(Graph label)]
```
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [str(AGENT_CANON), "docs", "fix-mermaid", str(target)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        fixed = target.read_text(encoding="utf-8")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "```mermaid\ngraph TD\n" in fixed
    assert "start --> graph_node[(Graph label)]" in fixed


def test_mermaid_formatter_rewrites_line_initial_graph_node() -> None:
    """A line-initial reserved word with an edge is a node id, not a directive."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / "diagram.md"
        target.write_text(
            """# Diagram

```mermaid
flowchart LR
  ingest --> graph
  graph --> analyze
```
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [str(AGENT_CANON), "docs", "fix-mermaid", str(target)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        fixed = target.read_text(encoding="utf-8")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ingest --> graph_node" in fixed
    assert "graph_node --> analyze" in fixed


def test_markdown_formatter_invokes_mermaid_formatter() -> None:
    """The canonical Markdown formatter should run Mermaid fixes."""
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
            [str(AGENT_CANON), "docs", "format", str(target)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "DOCS_FORMAT=wrote" in result.stdout
        assert "DOCS_CHECK=pass" in result.stdout
        text = target.read_text(encoding="utf-8")
        assert "```mermaid" in text
        assert "graph_node[(SQLite graph DB)]" in text
        assert "graph_node --> analyze[analyze]" in text
