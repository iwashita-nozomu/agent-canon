#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides format markdown documentation tooling.
# upstream design ../README.md shared automation index
# upstream implementation ./fix_mermaid.py fixes Mermaid fenced blocks.
# downstream implementation ../../tests/tools/test_fix_mermaid.py validates Mermaid formatter wiring.
# @dependency-end

"""Simple Markdown formatter.

- normalize line endings to LF
- remove trailing spaces
- collapse more than 2 consecutive blank lines to 2
- fix Mermaid fenced blocks
- ensure file ends with a single newline

Usage: format_markdown.py [paths...]
If no paths given, formats common doc directories: README.md, documents/, notes/, reviews/.
"""
import sys
import os
import subprocess
from pathlib import Path

from fix_mermaid import fix_mermaid_markdown


def forward_cli_to_rust(args: list[str]) -> int:
    """Forward legacy CLI use to the unified Rust docs formatter."""
    root = Path(__file__).resolve().parents[2]
    caller_chain = f"ppid={os.getppid()}"
    print("AGENT_CANON_FORWARDER=deprecated", file=sys.stderr)
    print("AGENT_CANON_FORWARDER_SEVERITY=fix-now", file=sys.stderr)
    print(f"AGENT_CANON_FORWARDER_CALLER_CHAIN={caller_chain}", file=sys.stderr)
    print(
        "AGENT_CANON_FORWARDER_CANONICAL=tools/bin/agent-canon docs format",
        file=sys.stderr,
    )
    completed = subprocess.run(
        [str(root / "tools/bin/agent-canon"), "docs", "format", *args],
        cwd=Path.cwd(),
        check=False,
    )
    return completed.returncode


def process_text(text: str) -> str:
    """Return formatted Markdown text."""
    # Normalize CRLF to LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text, _ = fix_mermaid_markdown(text)
    # Remove trailing spaces on each line
    lines: list[str] = [ln.rstrip() for ln in text.split("\n")]
    # Collapse more than 2 blank lines
    out_lines: list[str] = []
    blank_count = 0
    for ln in lines:
        if ln == "":
            blank_count += 1
        else:
            blank_count = 0
        if blank_count > 2:
            continue
        out_lines.append(ln)
    # Ensure single newline at EOF
    return "\n".join(out_lines).rstrip("\n") + "\n"


def format_file(p: Path) -> bool:
    """Format one file and return whether it changed."""
    try:
        original = p.read_text(encoding="utf-8")
    except Exception:
        return False
    new = process_text(original)
    if new != original:
        p.write_text(new, encoding="utf-8")
        return True
    return False


def gather_targets(args: list[str]) -> list[Path]:
    """Collect Markdown files to format."""
    if args:
        paths: list[Path] = [Path(a) for a in args]
    else:
        paths = [Path("README.md"), Path("documents"), Path("notes"), Path("reviews")]
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            for f in p.rglob("*.md"):
                files.append(f)
        elif p.is_file():
            files.append(p)
    # filter common unwanted dirs
    files = [f for f in files if ".git" not in f.parts and ".worktrees" not in f.parts]
    return sorted(set(files))


def main() -> None:
    """Run the CLI."""
    targets = gather_targets(sys.argv[1:])
    changed: list[str] = []
    for f in targets:
        ok = format_file(f)
        if ok:
            changed.append(str(f))
    print(f"Formatted {len(changed)} files")
    for c in changed:
        print(c)


if __name__ == "__main__":
    raise SystemExit(forward_cli_to_rust(sys.argv[1:]))
