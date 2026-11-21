# @dependency-start
# contract test
# responsibility Tests standard Mermaid syntax validation and format immutability.
# upstream implementation ../../tools/runtime/dispatch/agent-canon/src/docs.rs invokes mmdc.
# @dependency-end
"""Tests Mermaid parsing through the native docs checker."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from tests.agent_tools.rust_cli_fixture import standalone_agent_canon

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_CANON = standalone_agent_canon()
LYCHEE_CONFIG = Path("tools/validation/documentation/config/lychee.toml")


def run_docs(root: Path, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the docs CLI with the existing project configuration."""
    config = root / LYCHEE_CONFIG
    config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        PROJECT_ROOT / ".markdownlint-cli2.jsonc", root / ".markdownlint-cli2.jsonc"
    )
    shutil.copyfile(PROJECT_ROOT / LYCHEE_CONFIG, config)
    return subprocess.run(
        [str(AGENT_CANON), "docs", command, "--root", str(root), *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def write_markdown(path: Path, text: str) -> None:
    """Create a Markdown fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_docs_check_accepts_valid_mermaid_source() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        write_markdown(
            root / "diagram.md",
            "# Diagram\n\n```mermaid\nflowchart LR\n  a[Start] --> b[End]\n```\n",
        )

        result = run_docs(root, "check", "diagram.md")

        assert result.returncode == 0, result.stdout + result.stderr


def test_docs_check_rejects_invalid_mermaid_source() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        write_markdown(
            root / "diagram.md", "# Diagram\n\n```mermaid\nnot a valid diagram\n```\n"
        )

        result = run_docs(root, "check", "diagram.md")

        assert result.returncode != 0


def test_docs_check_rejects_invalid_mermaid_in_tilde_fence(tmp_path: Path) -> None:
    write_markdown(
        tmp_path / "diagram.md", "# Diagram\n\n~~~mermaid\nnot a valid diagram\n~~~\n"
    )

    result = run_docs(tmp_path, "check", "diagram.md")

    assert result.returncode == 1
    assert "diagram.md: Mermaid block 1 failed to render" in result.stderr


def test_docs_check_rejects_pandoc_mermaid_attributes(tmp_path: Path) -> None:
    write_markdown(
        tmp_path / "diagram.md",
        "# Diagram\n\n```{.mermaid}\nflowchart LR\n  a --> b\n```\n",
    )

    result = run_docs(tmp_path, "check", "diagram.md")

    assert result.returncode == 1
    assert (
        "GitHub Mermaid fences use the `mermaid` language identifier" in result.stderr
    )


def test_docs_format_applies_native_fixes_to_selected_file(tmp_path: Path) -> None:
    selected = tmp_path / "selected.md"
    untouched = tmp_path / "untouched.md"
    write_markdown(selected, "# Title\n\nFirst line  \nNext line \n\n-   Item\n")
    write_markdown(untouched, "# Other\n\n-   Item\n")

    result = run_docs(tmp_path, "format", selected.name)

    assert result.returncode == 0, result.stdout + result.stderr
    assert selected.read_bytes() == b"# Title\n\nFirst line  \nNext line\n\n- Item\n"
    assert untouched.read_bytes() == b"# Other\n\n-   Item\n"


def test_docs_format_does_not_rewrite_diagram_content() -> None:
    source = "# Diagram\n\n```mermaid\nflowchart LR\n  a[Start] --> b[End]\n```\n"
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        target = root / "diagram.md"
        write_markdown(target, source)

        result = run_docs(root, "format", "diagram.md")
        formatted = target.read_text(encoding="utf-8")

    assert result.returncode == 0, result.stdout + result.stderr
    assert formatted == source
