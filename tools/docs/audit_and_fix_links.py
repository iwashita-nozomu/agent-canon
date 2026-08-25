#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Routes link checks to the canonical Rust docs checker and keeps link apply behind explicit source mutation capability.
# upstream design ../README.md shared automation index
# upstream implementation ../../rust/agent-canon/src/docs.rs canonical Markdown link diagnostics
# upstream implementation ./_runtime_output.py explicit source mutation capability
# downstream implementation ../../tests/tools/test_audit_and_fix_links.py validates the compatibility route
# @dependency-end
"""Audit Markdown links through the canonical Rust docs checker.

This file is intentionally a thin compatibility wrapper.  Read-only checks
have one implementation: ``agent-canon docs check``.  The legacy Python link
rewriter remains only as an explicit ``--apply`` operation and requires a
typed ``--mutation-capability-json``; it never creates a source ``reports``
file.  ``--apply`` is therefore a source mutation capability, not a report
output mode.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

ROOT = Path.cwd().resolve()
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
SKIP_PARTS = {".git", ".worktrees", "__pycache__", "Archive"}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.docs._runtime_output import MutationCapability, MutationCapabilityError  # noqa: E402


@dataclass(frozen=True)
class LinkIssue:
    """A Markdown link that could not be resolved safely."""

    file_path: Path
    target: str
    candidates: tuple[Path, ...]


def find_markdown_links(text: str) -> list[tuple[str, str]]:
    """Return Markdown links found in ``text``."""
    return LINK_PATTERN.findall(text)


def replace_link_targets(text: str, replacements: dict[str, str]) -> str:
    """Replace exact link targets with corrected targets."""

    def repl(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        replacement = replacements.get(target)
        if replacement is None:
            return match.group(0)
        return f"[{label}]({replacement})"

    return LINK_PATTERN.sub(repl, text)


def iter_markdown_files(paths: list[str]) -> list[Path]:
    """Expand paths into Markdown files below the current source root."""
    markdown_files: list[Path] = []
    for raw_path in paths:
        path = (
            (ROOT / raw_path).resolve()
            if not Path(raw_path).is_absolute()
            else Path(raw_path).resolve()
        )
        if not path.exists():
            continue
        if path.is_dir():
            markdown_files.extend(path.rglob("*.md"))
        elif path.suffix == ".md":
            markdown_files.append(path)
    seen: set[Path] = set()
    filtered: list[Path] = []
    for path in markdown_files:
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path not in seen:
            seen.add(path)
            filtered.append(path)
    return sorted(filtered)


def build_name_index() -> dict[str, list[Path]]:
    """Build a filename index for explicit unique-name resolution."""
    name_index: dict[str, list[Path]] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        name_index.setdefault(path.name, []).append(path)
    return name_index


def is_external_target(target: str) -> bool:
    """Return whether a target is not a local filesystem link."""
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target)) or target.startswith(
        ("mailto:", "#")
    )


def split_anchor(target: str) -> tuple[str, str]:
    """Split a link target into path and anchor components."""
    if "#" not in target:
        return target, ""
    return target.split("#", 1)


def normalize_repo_absolute_path(target_path: Path) -> Path | None:
    """Map a workspace-specific absolute path back to this checkout."""
    if not target_path.is_absolute():
        return None
    if target_path.exists():
        return target_path
    parts = list(target_path.parts)
    indexes = [index for index, part in enumerate(parts) if part == ROOT.name]
    for index in reversed(indexes):
        candidate = ROOT.joinpath(*parts[index + 1 :])
        if candidate.exists():
            return candidate
    return None


def resolve_local_target(source_path: Path, target_path: str) -> Path | None:
    """Resolve one local link target relative to its Markdown source."""
    if not target_path:
        return None
    raw_path = Path(target_path)
    if raw_path.is_absolute():
        return normalize_repo_absolute_path(raw_path)
    candidate = (source_path.parent / raw_path).resolve()
    return candidate if candidate.exists() else None


def relative_target(source_path: Path, target_path: Path) -> str:
    """Return a portable relative target."""
    return os.path.relpath(target_path, start=source_path.parent).replace(os.sep, "/")


def planned_rewrites(paths: list[str]) -> dict[Path, str]:
    """Compute all rewrites before mutating any source file."""
    name_index = build_name_index()
    changes: dict[Path, str] = {}
    for markdown_file in iter_markdown_files(paths):
        text = markdown_file.read_text(encoding="utf-8")
        replacements: dict[str, str] = {}
        for _label, target in find_markdown_links(text):
            if is_external_target(target):
                continue
            target_path, anchor = split_anchor(target)
            resolved = resolve_local_target(markdown_file, target_path)
            if resolved is not None:
                if Path(target_path).is_absolute() and resolved.is_relative_to(ROOT):
                    new_target = relative_target(markdown_file, resolved)
                    replacements[target] = f"{new_target}#{anchor}" if anchor else new_target
                continue
            basename = Path(target_path).name
            candidates = tuple(
                candidate
                for candidate in name_index.get(basename, [])
                if not str(candidate).endswith(".bak")
            )
            if len(candidates) == 1:
                new_target = relative_target(markdown_file, candidates[0])
                replacements[target] = f"{new_target}#{anchor}" if anchor else new_target
        rewritten = replace_link_targets(text, replacements)
        if rewritten != text:
            changes[markdown_file] = rewritten
    return changes


def apply_rewrites(paths: list[str], capability: MutationCapability) -> int:
    """Apply a prevalidated source rewrite set under one explicit capability."""
    changes = planned_rewrites(paths)
    targets = [(path, capability.assert_allowed(path)) for path in changes]
    for path, _resolved in targets:
        path.write_text(changes[path], encoding="utf-8")
    return len(targets)


def forward_cli_to_rust(paths: list[str]) -> int:
    """Forward all read-only checks to exactly one canonical Rust implementation."""
    rust_args = ["docs", "check", "--root", str(ROOT), *paths]
    if os.environ.get("AGENT_CANON_EXECUTION_PLANE") == "tool-container":
        command = ["/usr/local/bin/agent-canon", *rust_args]
    else:
        command = [str(PROJECT_ROOT / "tools" / "bin" / "agent-canon"), *rust_args]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    """Run the canonical link check or an explicitly authorized link apply."""
    global ROOT
    ROOT = Path.cwd().resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--mutation-capability-json")
    args = parser.parse_args(argv)
    paths = args.paths or [
        "README.md",
        "QUICK_START.md",
        "AGENTS.md",
        "agents",
        "documents",
        "scripts",
        ".github",
        ".codex/personal/skills",
        ".codex/README.md",
    ]

    if args.apply:
        if not args.mutation_capability_json:
            parser.error(
                "--apply requires --mutation-capability-json; link audit is read-only by default"
            )
        try:
            capability = MutationCapability.from_json(ROOT, args.mutation_capability_json)
            changed = apply_rewrites(paths, capability)
        except MutationCapabilityError as exc:
            parser.error(f"mutation_capability_error: {exc}")
        print(f"Applied link rewrites: {changed}")
        if not args.check:
            return 0
    elif args.mutation_capability_json:
        parser.error("--mutation-capability-json is valid only with --apply")

    # ``--check`` is retained as a compatibility spelling.  The Rust route is
    # always the sole implementation for the read-only audit and owns its
    # diagnostics; this wrapper never creates a source report.
    return forward_cli_to_rust(paths)


if __name__ == "__main__":
    raise SystemExit(main())
