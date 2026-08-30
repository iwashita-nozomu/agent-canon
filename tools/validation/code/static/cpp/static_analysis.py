#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides generic CMake compile-database selection plus clangd and clang-tidy checks.
# upstream design ../../../../../documents/conventions/coding-conventions-cpp.md C++ build and validation conventions
# upstream implementation ../../../../repository/support/repo_paths.sh resolves standalone/vendored tool views
# downstream implementation ../../../../../tests/tools/test_cpp_static_analysis.py focused CLI and policy tests
# @dependency-end
"""Select a CMake compile database and run clangd/clang-tidy against sources."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


DATABASE_NAME = "compile_commands.json"
DEFAULT_ACTIVE_DATABASE = Path("build/cpp/dev/compile_commands.json")
DEFAULT_CLANG_TIDY_CONFIG = Path("clang/clang-tidy.yaml")


class StaticAnalysisFailure(ValueError):
    """Typed failure that is rendered consistently by the CLI."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _workspace(raw_root: str | None) -> Path:
    """Resolve the explicit workspace root or the current repository directory."""
    return Path(raw_root or Path.cwd()).expanduser().resolve()


def _path(raw_path: str | Path, root: Path, *, preserve_final_symlink: bool = False) -> Path:
    """Resolve a path relative to the selected workspace root."""
    value = Path(raw_path).expanduser()
    candidate = value if value.is_absolute() else root / value
    return candidate.absolute() if preserve_final_symlink else candidate.resolve()


def _validate_database(path: Path) -> None:
    """Require a readable CMake JSON array without inspecting compiler flags."""
    if not path.is_file():
        raise StaticAnalysisFailure("compile_database_missing", f"CMake compile database does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StaticAnalysisFailure("compile_database_invalid", f"Unable to parse compile database {path}: {exc}") from exc
    if not isinstance(value, list):
        raise StaticAnalysisFailure("compile_database_invalid", f"CMake compile database must contain a JSON array: {path}")


def _database(root: Path, build_dir: str | None, compile_database: str | None) -> Path:
    """Resolve one explicit database source or the selected profile-level view."""
    if build_dir and compile_database:
        raise StaticAnalysisFailure("compile_database_selection_conflict", "Provide either --build-dir or --compile-database, not both")
    if build_dir:
        directory = _path(build_dir, root)
        if not directory.is_dir():
            raise StaticAnalysisFailure("build_directory_missing", f"Build directory does not exist: {directory}")
        selected = directory / DATABASE_NAME
    elif compile_database:
        selected = _path(compile_database, root)
    else:
        selected = root / DEFAULT_ACTIVE_DATABASE
    selected = selected.resolve()
    _validate_database(selected)
    return selected


def _materialize(root: Path, source: Path, output: str | None) -> tuple[Path, bool]:
    """Atomically materialize one active symlink under the workspace build tree."""
    active = _path(output or DEFAULT_ACTIVE_DATABASE, root, preserve_final_symlink=True)
    build_root = (root / "build").resolve()
    try:
        active.relative_to(build_root)
        active.parent.resolve().relative_to(build_root)
    except ValueError as exc:
        raise StaticAnalysisFailure("active_database_outside_build", f"Active database must remain under {build_root}: {active}") from exc
    active.parent.mkdir(parents=True, exist_ok=True)
    if active.is_dir():
        raise StaticAnalysisFailure("active_database_is_directory", f"Active database path is a directory: {active}")
    if active.exists() and not active.is_symlink():
        raise StaticAnalysisFailure("active_database_exists", f"Refusing to replace unrelated regular file: {active}")
    if active.is_symlink() and active.resolve() == source.resolve():
        return active, True

    fd, name = tempfile.mkstemp(prefix=f".{active.name}.", suffix=".tmp", dir=active.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        temporary.unlink()
        temporary.symlink_to(os.path.relpath(source, active.parent))
        os.replace(temporary, active)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise StaticAnalysisFailure("active_database_materialization_failed", f"Unable to materialize active database {active}: {exc}") from exc
    return active, False


def _source_paths(args: argparse.Namespace, root: Path) -> list[Path]:
    """Resolve positional and repeated --source paths."""
    values = [*args.sources, *args.source_options]
    if not values:
        raise StaticAnalysisFailure("source_missing", "Provide at least one C or C++ source path")
    paths = [_path(value, root) for value in values]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise StaticAnalysisFailure("source_missing", "Source file does not exist: " + ", ".join(map(str, missing)))
    return paths


def _executable(raw_tool: str, name: str) -> str:
    """Resolve an executable before starting an analyzer process."""
    path = raw_tool if Path(raw_tool).is_absolute() else shutil.which(raw_tool)
    if path is None or not Path(path).is_file() or not os.access(path, os.X_OK):
        raise StaticAnalysisFailure("tool_missing", f"{name} executable is not available: {raw_tool}")
    return path


def _clang_tidy_config(root: Path, explicit: str | None) -> str | None:
    """Resolve explicit or project-conventional clang-tidy configuration."""
    if explicit is not None:
        config = _path(explicit, root)
        if not config.is_file():
            raise StaticAnalysisFailure("config_file_missing", f"clang-tidy config file does not exist: {config}")
        return explicit
    default = root / DEFAULT_CLANG_TIDY_CONFIG
    return str(default) if default.is_file() else None


def _run_checks(args: argparse.Namespace, name: str) -> int:
    """Run one native checker per source while preserving native output/status."""
    root = _workspace(args.workspace_root)
    sources = _source_paths(args, root)
    database = _database(root, args.build_dir, args.compile_database)
    executable = _executable(args.tool, name)
    first_failure = 0
    for source in sources:
        if name == "clangd":
            command = [executable, f"--check={source}", f"--compile-commands-dir={database.parent}"]
        else:
            command = [executable, str(source), "-p", str(database.parent)]
            config = _clang_tidy_config(root, args.config_file)
            if config is not None:
                command[1:1] = ["--config-file", config]
        result = subprocess.run(command, cwd=root, check=False, capture_output=True, text=True)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode and not first_failure:
            first_failure = result.returncode
    return first_failure


def _database_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-root", help="Project root; defaults to the current directory")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--build-dir", help="CMake build directory containing compile_commands.json")
    group.add_argument("--compile-database", "--compile-commands", help="Path to compile_commands.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the stable command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    select = subparsers.add_parser("select-db", help="Select one CMake-generated database for editor consumers")
    select.add_argument("--workspace-root", help="Project root; defaults to the current directory")
    select.add_argument("--build-dir", required=True, help="CMake build directory containing compile_commands.json")
    select.add_argument("--output", help="Active database path under the workspace build directory")
    for command, executable, description in (
        ("clangd-check", "clangd", "Run clangd --check"),
        ("clang-tidy", "clang-tidy", "Run clang-tidy"),
    ):
        checker = subparsers.add_parser(command, help=description)
        checker.add_argument("sources", nargs="*", help="C or C++ source paths")
        checker.add_argument("--source", dest="source_options", action="append", default=[], help="Additional source path")
        _database_options(checker)
        checker.add_argument(f"--{executable}", dest="tool", default=executable, help=f"{executable} executable")
        if executable == "clang-tidy":
            checker.add_argument("--config-file", help="Project clang-tidy configuration to forward unchanged")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected command and return its exact native status when invoked."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "select-db":
            root = _workspace(args.workspace_root)
            source = _database(root, args.build_dir, None)
            active, reused = _materialize(root, source, args.output)
            print(f"workspace_root={root}")
            print(f"compile_database={source}")
            print(f"active_database={active}")
            print(f"materialization={'already-active' if reused else 'symlink'}")
            return 0
        if args.command == "clangd-check":
            return _run_checks(args, "clangd")
        return _run_checks(args, "clang-tidy")
    except StaticAnalysisFailure as exc:
        print(f"cpp-static-analysis: {exc.code}: {exc.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
