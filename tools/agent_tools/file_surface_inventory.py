#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Builds machine-readable file surface inventories for repo review.
# upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared surface model
# downstream implementation ./review_backlog_scan.sh includes inventory reports
# downstream implementation ../../tests/agent_tools/test_file_surface_inventory.py tests inventory
# @dependency-end
"""Build JSON and Markdown file-surface inventories for repo review."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from surface_manifest import SurfaceManifest, load_manifest

CHECKABLE_SUFFIXES = frozenset(
    {
        ".bash",
        ".cfg",
        ".css",
        ".h",
        ".hpp",
        ".html",
        ".c",
        ".cc",
        ".cpp",
        ".json",
        ".md",
        ".py",
        ".rst",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
        ".zsh",
    }
)
EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "reports",
    }
)
SUBMODULE_PATH = Path("vendor/agent-canon")
ROOT_TOOLS_PATH = Path("tools")
AGENTCANON_TOOL_SOURCE_KIND = "agentcanon_tool_source"
AGENTCANON_TOOL_VIEW_KIND = "agentcanon_tool_view"


@dataclass(frozen=True)
class FileEntry:
    """One tracked or discovered file-like surface."""

    scope: str
    path: str
    kind: str
    owner: str
    surface_class: str
    suffix: str
    checkable: bool
    git_mode: str
    symlink_target: str
    real_source_path: str
    canonical_source_path: str


@dataclass(frozen=True)
class ScopeInventory:
    """Inventory result for one scan scope."""

    name: str
    root: str
    files: int
    checkable_files: int
    by_kind: dict[str, int]
    entries: list[FileEntry]


@dataclass(frozen=True)
class SurfaceLookup:
    """Root surface ownership lookup derived from the shared manifest."""

    by_path: Mapping[str, tuple[str, str, str, str]]
    prefix: str

    def get(self, relative: Path) -> tuple[str, str, str, str]:
        """Return ``(kind, owner, class, source)`` for a root path."""
        return self.by_path.get(relative.as_posix(), ("", "", "", ""))


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--root-only", action="store_true")
    scope.add_argument("--agentcanon-only", action="store_true")
    scope.add_argument("--submodule-aware", action="store_true")
    parser.add_argument("--json-out", help="Optional JSON report path.")
    parser.add_argument("--markdown-out", help="Optional Markdown report path.")
    parser.add_argument(
        "--max-markdown-entries",
        type=int,
        default=200,
        help="Maximum file rows to include in Markdown. JSON is always complete.",
    )
    return parser


def load_surface_lookup(root: Path) -> SurfaceLookup:
    """Load shared surface metadata when the manifest is available."""
    try:
        manifest = load_manifest(root, "vendor/agent-canon", "documents/shared-runtime-surfaces.toml")
    except (OSError, ValueError):
        return SurfaceLookup(by_path={}, prefix="vendor/agent-canon")
    return SurfaceLookup(by_path=surface_entries(manifest), prefix=manifest.prefix)


def surface_entries(manifest: SurfaceManifest) -> dict[str, tuple[str, str, str, str]]:
    """Return path-indexed surface metadata."""
    entries: dict[str, tuple[str, str, str, str]] = {}
    for entry in manifest.entries:
        kind = {
            "copy": entry.surface_class,
            "repo_state": "repo_state",
            "regular": "product_file",
            "standalone_only": "standalone_only",
            "removed_legacy": "removed_legacy",
            "symlink": "symlink_view",
        }.get(entry.mode, entry.surface_class)
        entries[entry.path] = (
            kind,
            entry.owner,
            entry.surface_class,
            entry.source_or_default(),
        )
    return entries


def mode_for_untracked_path(path: Path) -> str:
    """Return a git-like mode for an untracked worktree path."""
    if path.is_symlink():
        return "120000"
    if os.access(path, os.X_OK):
        return "100755"
    return "100644"


def run_git_untracked_files(root: Path) -> list[tuple[str, str]]:
    """Return untracked, non-ignored paths as ``(mode, path)`` rows."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--others", "--exclude-standard"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return []
    rows: list[tuple[str, str]] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8", errors="replace")
        full_path = root / path
        if surface_exists(full_path):
            rows.append((mode_for_untracked_path(full_path), path))
    return rows


def run_git_ls_files(root: Path) -> list[tuple[str, str]]:
    """Return tracked and untracked paths from a Git worktree."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "-s"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed for inventory scope: {root}")
    rows: list[tuple[str, str]] = []
    for raw_record in result.stdout.split(b"\0"):
        if not raw_record:
            continue
        record = raw_record.decode("utf-8", errors="replace")
        metadata, path = record.split("\t", 1)
        mode = metadata.split(" ", 1)[0]
        rows.append((mode, path))
    rows.extend(run_git_untracked_files(root))
    return sorted(rows, key=lambda row: row[1])


def relative_real_path(root: Path, path: Path) -> str:
    """Return a stable root-relative real path when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def surface_exists(path: Path) -> bool:
    """Return true for file-like surfaces that exist in the worktree."""
    return path.exists() or path.is_symlink()


def entry_kind(
    scope_name: str,
    relative: Path,
    full_path: Path,
    git_mode: str,
    surface_lookup: SurfaceLookup,
) -> str:
    """Classify one inventory entry for review routing."""
    if git_mode == "160000":
        return "submodule_pin"
    manifest_kind = surface_lookup.get(relative)[0] if scope_name == "root" else ""
    if manifest_kind:
        return manifest_kind
    if scope_name == "root" and relative == ROOT_TOOLS_PATH and full_path.is_symlink():
        return AGENTCANON_TOOL_VIEW_KIND
    if scope_name == "agentcanon" and relative.parts[:1] == ROOT_TOOLS_PATH.parts:
        return AGENTCANON_TOOL_SOURCE_KIND
    if full_path.is_symlink():
        return "symlink_view"
    if scope_name == "agentcanon":
        return "canon_source"
    if relative.parts[:2] == SUBMODULE_PATH.parts:
        return "submodule_source"
    return "product_file"


def make_entry(
    scope_name: str,
    root: Path,
    git_mode: str,
    raw_path: str,
    surface_lookup: SurfaceLookup,
) -> FileEntry:
    """Build one file entry."""
    relative = Path(raw_path)
    full_path = root / relative
    suffix = relative.suffix
    kind = entry_kind(scope_name, relative, full_path, git_mode, surface_lookup)
    _, owner, surface_class, source = (
        surface_lookup.get(relative) if scope_name == "root" else ("", "", "", "")
    )
    symlink_target = os.readlink(full_path) if full_path.is_symlink() else ""
    real_source_path = relative_real_path(root, full_path) if surface_exists(full_path) else ""
    canonical_source_path = (
        str(Path(surface_lookup.prefix) / source).replace("\\", "/") if source else ""
    )
    return FileEntry(
        scope=scope_name,
        path=relative.as_posix(),
        kind=kind,
        owner=owner,
        surface_class=surface_class,
        suffix=suffix,
        checkable=suffix in CHECKABLE_SUFFIXES and kind != "submodule_pin",
        git_mode=git_mode,
        symlink_target=symlink_target,
        real_source_path=real_source_path,
        canonical_source_path=canonical_source_path,
    )


def scope_roots(root: Path, mode: str) -> list[tuple[str, Path]]:
    """Return scan scopes for the requested mode."""
    canon = (root / SUBMODULE_PATH).resolve()
    if mode == "agentcanon-only":
        return [("agentcanon", canon if canon.exists() else root)]
    if mode == "root-only":
        return [("root", root)]
    scopes = [("root", root)]
    if canon.exists() and canon != root:
        scopes.append(("agentcanon", canon))
    return scopes


def selected_mode(args: argparse.Namespace) -> str:
    """Return the requested scope mode."""
    if args.root_only:
        return "root-only"
    if args.agentcanon_only:
        return "agentcanon-only"
    return "submodule-aware"


def inventory_scope(scope_name: str, root: Path, surface_lookup: SurfaceLookup) -> ScopeInventory:
    """Inventory one scan scope."""
    rows = run_git_ls_files(root)
    entries = [
        make_entry(scope_name, root, git_mode, path, surface_lookup)
        for git_mode, path in rows
        if not set(Path(path).parts) & EXCLUDED_PARTS
        if git_mode == "160000" or surface_exists(root / path)
    ]
    by_kind = Counter(entry.kind for entry in entries)
    return ScopeInventory(
        name=scope_name,
        root=root.as_posix(),
        files=len(entries),
        checkable_files=sum(1 for entry in entries if entry.checkable),
        by_kind=dict(sorted(by_kind.items())),
        entries=entries,
    )


def render_json(mode: str, root: Path, scopes: Sequence[ScopeInventory]) -> str:
    """Render the complete JSON report."""
    files = sum(scope.files for scope in scopes)
    checkable = sum(scope.checkable_files for scope in scopes)
    payload: dict[str, object] = {
        "status": "pass",
        "mode": mode,
        "root": root.as_posix(),
        "files": files,
        "checkable_files": checkable,
        "scopes": [
            {
                **asdict(scope),
                "entries": [asdict(entry) for entry in scope.entries],
            }
            for scope in scopes
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def markdown_entry_rows(scopes: Sequence[ScopeInventory], limit: int) -> list[str]:
    """Render bounded Markdown rows for file-level review."""
    rows: list[str] = []
    remaining = max(limit, 0)
    for scope in scopes:
        for entry in scope.entries:
            if remaining <= 0:
                return rows
            rows.append(
                "| "
                + " | ".join(
                    (
                        entry.scope,
                        entry.path,
                        entry.kind,
                        entry.owner,
                        entry.surface_class,
                        "yes" if entry.checkable else "no",
                        entry.real_source_path,
                        entry.canonical_source_path,
                    )
                )
                + " |"
            )
            remaining -= 1
    return rows


def render_markdown(mode: str, root: Path, scopes: Sequence[ScopeInventory], limit: int) -> str:
    """Render a human-readable inventory report."""
    lines = [
        "# File Surface Inventory",
        "",
        "<!--",
        "@dependency-start",
        "responsibility Records file surface inventory for review.",
        (
            "upstream implementation ../../../../vendor/agent-canon/tools/"
            "agent_tools/file_surface_inventory.py generates this report"
        ),
        "@dependency-end",
        "-->",
        "",
        f"- mode: {mode}",
        f"- root: {root.as_posix()}",
        f"- files: {sum(scope.files for scope in scopes)}",
        f"- checkable_files: {sum(scope.checkable_files for scope in scopes)}",
        "",
        "## Scope Summary",
        "",
        "| Scope | Root | Files | Checkable | By Kind |",
        "| ----- | ---- | ----- | --------- | ------- |",
    ]
    for scope in scopes:
        by_kind = ", ".join(f"{key}={value}" for key, value in scope.by_kind.items())
        lines.append(
            f"| {scope.name} | {scope.root} | {scope.files} | "
            f"{scope.checkable_files} | {by_kind} |"
        )
    lines.extend(
        [
            "",
            "## File Rows",
            "",
            "| Scope | Path | Kind | Owner | Surface Class | Checkable | Real Source Path | Canonical Source Path |",
            "| ----- | ---- | ---- | ----- | ------------- | --------- | ---------------- | --------------------- |",
            *markdown_entry_rows(scopes, limit),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_optional(path: str | None, text: str) -> None:
    """Write a report path when requested."""
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def main() -> int:
    """Run the inventory command."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    mode = selected_mode(args)
    surface_lookup = load_surface_lookup(root)
    try:
        scopes = [
            inventory_scope(name, scope_root, surface_lookup)
            for name, scope_root in scope_roots(root, mode)
        ]
    except RuntimeError as exc:
        print(f"FILE_SURFACE_INVENTORY_ERROR={exc}")
        print("FILE_SURFACE_INVENTORY=fail")
        return 1
    json_text = render_json(mode, root, scopes)
    markdown_text = render_markdown(mode, root, scopes, int(args.max_markdown_entries))
    write_optional(args.json_out, json_text)
    write_optional(args.markdown_out, markdown_text)
    print("FILE_SURFACE_INVENTORY=pass")
    print(f"FILE_SURFACE_INVENTORY_MODE={mode}")
    print(f"FILE_SURFACE_INVENTORY_FILES={sum(scope.files for scope in scopes)}")
    print(
        "FILE_SURFACE_INVENTORY_CHECKABLE="
        f"{sum(scope.checkable_files for scope in scopes)}"
    )
    if args.json_out:
        print(f"FILE_SURFACE_INVENTORY_JSON={Path(args.json_out)}")
    if args.markdown_out:
        print(f"FILE_SURFACE_INVENTORY_MARKDOWN={Path(args.markdown_out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
