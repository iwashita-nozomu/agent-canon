#!/usr/bin/env python3
"""Run pydocstyle only for trusted changed production Python files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib  # type: ignore[no-redef]


PACKET_SCHEMA = "agent-canon.pr-changed-paths.v1"
SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DIAGNOSTIC_HEADER = re.compile(r"^(?P<path>.+):(?P<line>[0-9]+) (?P<context>.+):$")
DIAGNOSTIC_LINE = re.compile(r"^\s+(?P<code>D[0-9]{3}): (?P<message>.*)$")
CONFIG_NAMES = (
    "setup.cfg",
    "tox.ini",
    ".pydocstyle",
    ".pydocstyle.ini",
    ".pydocstylerc",
    ".pydocstylerc.ini",
    "pyproject.toml",
    ".pep257",
)
EXCLUDED_PARTS = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "fixtures",
        "generated",
        "test",
        "tests",
        "vendor",
    }
)


class ScopeFailure(RuntimeError):
    """One fail-closed changed-scope validation failure."""

    def __init__(self, reason: str, evidence: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence


@dataclass(frozen=True)
class Packet:
    """Validated trusted PR path packet."""

    base_sha: str
    head_sha: str
    changed_paths: tuple[str, ...]


@dataclass(frozen=True)
class Diagnostic:
    """One normalized pydocstyle diagnostic."""

    code: str
    qualified_name: str
    path: str
    line: int
    message: str

    @property
    def identity(self) -> str:
        """Return the line-independent comparison identity."""
        return f"{self.code}|{self.qualified_name}"

    def report(self) -> dict[str, object]:
        """Return the durable diagnostic record."""
        return {
            "code": self.code,
            "qualified_name": self.qualified_name,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "identity": self.identity,
        }


def run_git(root: Path, args: Sequence[str]) -> str:
    """Return Git output or fail closed with a typed reason."""
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr_hash = hashlib.sha256(result.stderr.encode()).hexdigest()
        command = args[0] if args else "unknown"
        raise ScopeFailure(
            f"git_{command}_failed",
            f"exit={result.returncode};stderr_sha256={stderr_hash}",
        )
    return result.stdout.strip()


def require_string(mapping: Mapping[str, object], key: str) -> str:
    """Return a non-empty string packet field."""
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ScopeFailure("changed_path_packet_invalid", f"field={key}")
    return value


def validate_packet(root: Path, packet_path: Path, trusted_base_sha: str) -> Packet:
    """Validate packet type, trusted base, exact trees, diff, and digest."""
    if not SHA40.fullmatch(trusted_base_sha):
        raise ScopeFailure("trusted_base_argument_missing_or_invalid", "field=base_sha")
    if not packet_path.is_file() or packet_path.is_symlink():
        raise ScopeFailure(
            "changed_path_packet_missing_or_wrong_type", str(packet_path)
        )
    try:
        payload = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ScopeFailure(
            "changed_path_packet_invalid",
            f"error={type(error).__name__}",
        ) from error
    if not isinstance(payload, dict):
        raise ScopeFailure("changed_path_packet_invalid", "field=object")
    payload = cast(dict[str, object], payload)
    if require_string(payload, "schema") != PACKET_SCHEMA:
        raise ScopeFailure("changed_path_packet_schema_mismatch", "field=schema")
    packet_root = require_string(payload, "root")
    if packet_root != str(root):
        raise ScopeFailure("changed_path_packet_root_mismatch", f"expected={root}")
    base_sha = require_string(payload, "base_sha")
    head_sha = require_string(payload, "head_sha")
    base_tree = require_string(payload, "base_tree")
    head_tree = require_string(payload, "head_tree")
    merge_base = require_string(payload, "merge_base")
    packet_digest = require_string(payload, "changed_paths_sha256")
    if not SHA40.fullmatch(base_sha) or not SHA40.fullmatch(head_sha):
        raise ScopeFailure("changed_path_packet_invalid", "field=commit_sha")
    if not SHA40.fullmatch(base_tree) or not SHA40.fullmatch(merge_base):
        raise ScopeFailure("changed_path_packet_invalid", "field=tree_or_merge_base")
    if not SHA256.fullmatch(packet_digest):
        raise ScopeFailure("changed_path_packet_invalid", "field=changed_paths_sha256")
    if base_sha != trusted_base_sha:
        raise ScopeFailure(
            "changed_path_packet_trusted_base_mismatch", "field=base_sha"
        )
    raw_paths = payload.get("changed_paths")
    if not isinstance(raw_paths, list):
        raise ScopeFailure("changed_path_packet_invalid", "field=changed_paths")
    raw_paths = cast(list[object], raw_paths)
    changed_path_values: list[str] = []
    for raw_path in raw_paths:
        if (
            not isinstance(raw_path, str)
            or not raw_path
            or PurePosixPath(raw_path).is_absolute()
            or PurePosixPath(raw_path).as_posix() != raw_path
            or ".." in PurePosixPath(raw_path).parts
        ):
            raise ScopeFailure("changed_path_packet_invalid", "field=changed_paths")
        changed_path_values.append(raw_path)
    changed_paths = tuple(changed_path_values)
    if len(set(changed_paths)) != len(changed_paths):
        raise ScopeFailure("changed_path_packet_duplicate_path", "field=changed_paths")

    resolved_base = run_git(
        root, ["rev-parse", "--verify", "--end-of-options", f"{base_sha}^{{commit}}"]
    )  # noqa: E501
    if resolved_base != base_sha:
        raise ScopeFailure("changed_path_packet_base_identity_mismatch", resolved_base)
    if (
        run_git(
            root, ["rev-parse", "--verify", "--end-of-options", f"{base_sha}^{{tree}}"]
        )
        != base_tree
    ):
        raise ScopeFailure("changed_path_packet_base_tree_mismatch", "field=base_tree")
    if (
        run_git(
            root,
            ["rev-parse", "--verify", "--end-of-options", f"{head_sha}^{{commit}}"],
        )
        != head_sha
    ):
        raise ScopeFailure(
            "changed_path_packet_head_identity_mismatch", "field=head_sha"
        )
    if (
        run_git(
            root, ["rev-parse", "--verify", "--end-of-options", f"{head_sha}^{{tree}}"]
        )
        != head_tree
    ):
        raise ScopeFailure("changed_path_packet_head_tree_mismatch", "field=head_tree")
    if run_git(root, ["rev-parse", "HEAD"]) != head_sha:
        raise ScopeFailure("changed_path_packet_head_identity_mismatch", "field=HEAD")
    if run_git(root, ["merge-base", base_sha, head_sha]) != merge_base:
        raise ScopeFailure(
            "changed_path_packet_merge_base_mismatch", "field=merge_base"
        )
    actual_paths = tuple(
        run_git(root, ["diff", "--name-only", f"{base_sha}...{head_sha}"]).splitlines()
    )
    if actual_paths != changed_paths:
        raise ScopeFailure("changed_path_packet_paths_mismatch", "field=changed_paths")
    computed_digest = hashlib.sha256("\0".join(changed_paths).encode()).hexdigest()
    if computed_digest != packet_digest:
        raise ScopeFailure(
            "changed_path_packet_digest_mismatch", "field=changed_paths_sha256"
        )
    return Packet(base_sha, head_sha, changed_paths)


def is_derived_root(root: Path) -> bool:
    """Return whether the root consumes AgentCanon as a submodule."""
    return (root / "vendor" / "agent-canon").is_dir() and not (
        root / "rust" / "agent-canon" / "Cargo.toml"
    ).is_file()


def root_view_paths(root: Path) -> tuple[str, ...]:
    """Read AgentCanon-owned root-view paths for derived repositories."""
    source_root = root / "vendor" / "agent-canon" if is_derived_root(root) else root
    manifest = source_root / "documents" / "runtime" / "shared-runtime-surfaces.toml"
    if not manifest.is_file():
        return ()
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ScopeFailure(
            "root_view_manifest_invalid",
            f"path={manifest};error={type(error).__name__}",
        ) from error
    paths: list[str] = []
    data = cast(dict[str, object], data)
    surfaces = data.get("surface", [])
    groups = data.get("group", [])
    surface_entries = cast(list[object], surfaces) if isinstance(surfaces, list) else []
    group_entries = cast(list[object], groups) if isinstance(groups, list) else []
    for raw_entry in surface_entries:
        if not isinstance(raw_entry, dict):
            continue
        entry = cast(dict[str, object], raw_entry)
        if entry.get("owner") == "agent-canon":
            path = entry.get("path")
            if isinstance(path, str) and path:
                paths.append(path)
    for raw_group in group_entries:
        if not isinstance(raw_group, dict):
            continue
        group = cast(dict[str, object], raw_group)
        if group.get("owner") != "agent-canon":
            continue
        raw_paths = group.get("paths", [])
        if isinstance(raw_paths, list):
            paths.extend(
                path
                for path in cast(list[object], raw_paths)
                if isinstance(path, str) and path
            )
    return tuple(sorted(set(paths)))


def is_root_view(path: str, views: Iterable[str]) -> bool:
    """Return whether a path belongs to a declared root view."""
    return any(
        path == view or path.startswith(f"{view.rstrip('/')}/") for view in views
    )


def production_path(root: Path, path: str, views: Sequence[str]) -> tuple[bool, str]:
    """Classify a changed path for the pydocstyle production surface."""
    pure = PurePosixPath(path)
    if pure.suffix != ".py":
        return False, "non_python"
    if any(part in EXCLUDED_PARTS for part in pure.parts):
        return False, "test_fixture_generated_or_submodule"
    if pure.name.startswith("test_") or pure.name.endswith("_test.py"):
        return False, "test_surface"
    candidate = root / Path(*pure.parts)
    if candidate.is_symlink():
        return False, "root_view_symlink"
    if is_derived_root(root) and is_root_view(path, views):
        return False, "root_view"
    if not candidate.is_file():
        return False, "deleted_or_missing"
    return True, "production"


def file_identity(path: Path) -> tuple[int, int, int, int]:
    """Return replacement-sensitive file identity."""
    stat_result = path.stat()
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
    )


def config_section_exists(path: Path) -> bool:
    """Return whether a candidate file contains a pydocstyle section."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if path.name == "pyproject.toml":
        return "[tool.pydocstyle]" in text or "[tool.pep257]" in text
    return bool(re.search(r"^\s*\[(?:pydocstyle|pep257)\]\s*$", text, re.MULTILINE))


def nearest_config(root: Path, path: str) -> Path | None:
    """Return the nearest active pydocstyle config for one head path."""
    current = (root / Path(*PurePosixPath(path).parts)).parent
    while True:
        for name in CONFIG_NAMES:
            candidate = current / name
            if candidate.is_file() and config_section_exists(candidate):
                return candidate
        if current == root:
            return None
        if root not in current.parents:
            return None
        current = current.parent


def config_files_for_paths(root: Path, paths: Sequence[str]) -> tuple[Path, ...]:
    """Return all head config files needed for base discovery parity."""
    files: set[Path] = set()
    for path in paths:
        current = (root / Path(*PurePosixPath(path).parts)).parent
        while True:
            for name in CONFIG_NAMES:
                candidate = current / name
                if candidate.is_file() and config_section_exists(candidate):
                    files.add(candidate)
            if current == root or root not in current.parents:
                break
            current = current.parent
    return tuple(sorted(files))


def unchanged_production_paths(
    root: Path,
    changed_paths: Sequence[str],
    views: Sequence[str],
) -> list[str]:
    """Return unchanged production files for non-blocking baseline evidence."""
    changed = set(changed_paths)
    candidates = run_git(root, ["ls-files", "--", "*.py"]).splitlines()
    return [
        path
        for path in candidates
        if path not in changed and production_path(root, path, views)[0]
    ]


def module_name(root: Path, filename: Path) -> str:
    """Return a stable module name independent of the checked-out root."""
    relative = filename.resolve().relative_to(root.resolve())
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = Path(parts[-1]).stem
    return ".".join(parts) or "__main__"


def parse_diagnostics(root: Path, output: str) -> tuple[Diagnostic, ...]:
    """Parse pydocstyle output into line-independent identities."""
    lines = output.splitlines()
    diagnostics: list[Diagnostic] = []
    index = 0
    while index < len(lines):
        header = DIAGNOSTIC_HEADER.match(lines[index])
        if header is None:
            index += 1
            continue
        if index + 1 >= len(lines):
            raise ScopeFailure("pydocstyle_diagnostic_parse_failed", lines[index])
        detail = DIAGNOSTIC_LINE.match(lines[index + 1])
        if detail is None:
            raise ScopeFailure("pydocstyle_diagnostic_parse_failed", lines[index])
        raw_path = Path(header.group("path")).resolve()
        try:
            relative_path = raw_path.relative_to(root.resolve()).as_posix()
        except ValueError as error:
            raise ScopeFailure(
                "pydocstyle_diagnostic_path_outside_root",
                str(raw_path),
            ) from error
        module = module_name(root, raw_path)
        context = header.group("context")
        symbol_match = re.search(r"`([^`]+)`", context)
        qualified_name = module
        if symbol_match and "module level" not in context and "package" not in context:
            qualified_name = f"{module}.{symbol_match.group(1)}"
        diagnostics.append(
            Diagnostic(
                code=detail.group("code"),
                qualified_name=qualified_name,
                path=relative_path,
                line=int(header.group("line")),
                message=detail.group("message"),
            )
        )
        index += 2
    return tuple(diagnostics)


def run_pydocstyle(
    root: Path,
    paths: Sequence[Path],
    python_bin: str,
    canonical_config: Path | None,
) -> tuple[Diagnostic, ...]:
    """Run the current pydocstyle producer against an explicit path set."""
    if not paths:
        return ()
    command = [python_bin, "-m", "pydocstyle"]
    if canonical_config is not None:
        command.append(f"--config={canonical_config}")
    command.extend(str(path) for path in paths)
    result = subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    output = f"{result.stdout}{result.stderr}"
    diagnostics = parse_diagnostics(root, output)
    if result.returncode not in (0, 1):
        raise ScopeFailure(
            "pydocstyle_execution_failed",
            f"exit={result.returncode};output_sha256={hashlib.sha256(output.encode()).hexdigest()}",
        )
    return diagnostics


def materialize_base_files(
    root: Path, packet: Packet, paths: Sequence[str], target: Path
) -> list[Path]:
    """Materialize only exact base blobs and current config files."""
    base_paths: list[Path] = []
    for relative in paths:
        object_type = subprocess.run(
            ["git", "cat-file", "-t", f"{packet.base_sha}:{relative}"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if object_type.returncode != 0 or object_type.stdout.strip() != "blob":
            continue
        destination = target / Path(*PurePosixPath(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = subprocess.run(
            ["git", "show", f"{packet.base_sha}:{relative}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if content.returncode != 0:
            raise ScopeFailure("trusted_base_file_read_failed", f"path={relative}")
        destination.write_bytes(content.stdout)
        base_paths.append(destination)
    return base_paths


def copy_head_configs(root: Path, configs: Sequence[Path], target: Path) -> None:
    """Copy current config files so base discovery uses head policy semantics."""
    for config in configs:
        relative = config.resolve().relative_to(root.resolve())
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(config, destination)


def emit_failure(error: ScopeFailure) -> int:
    """Emit a typed fail-closed result."""
    print("PYDOCSTYLE_CHANGED_SCOPE=fail")
    print(f"PYDOCSTYLE_CHANGED_SCOPE_REASON={error.reason}")
    print(f"PYDOCSTYLE_CHANGED_SCOPE_EVIDENCE={error.evidence}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    """Build the changed-scope scanner CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--changed-path-packet", required=True)
    parser.add_argument("--trusted-base-sha", required=True)
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--report-out")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the packet, run head/base style checks, and partition findings."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    packet_path = Path(args.changed_path_packet).resolve()
    try:
        packet = validate_packet(root, packet_path, args.trusted_base_sha)
        views = root_view_paths(root)
        selected: list[str] = []
        skipped: dict[str, list[str]] = {}
        for path in packet.changed_paths:
            include, reason = production_path(root, path, views)
            if include:
                selected.append(path)
            else:
                skipped.setdefault(reason, []).append(path)

        baseline_paths = unchanged_production_paths(root, packet.changed_paths, views)
        all_production_paths = [*selected, *baseline_paths]
        config_files = config_files_for_paths(root, all_production_paths)
        use_canonical_config = not config_files
        canonical_config = None
        if use_canonical_config:
            source_root = (
                root / "vendor" / "agent-canon" if is_derived_root(root) else root
            )
            canonical_config = source_root / "tools" / "ci" / "pydocstyle.toml"
            if not canonical_config.is_file() or canonical_config.is_symlink():
                raise ScopeFailure(
                    "canonical_pydocstyle_config_missing", str(canonical_config)
                )

        head_paths = [
            root / Path(*PurePosixPath(path).parts) for path in all_production_paths
        ]
        before = {path: file_identity(path) for path in head_paths}
        all_head_diagnostics = run_pydocstyle(
            root, head_paths, args.python_bin, canonical_config
        )
        if any(file_identity(path) != identity for path, identity in before.items()):
            raise ScopeFailure(
                "pydocstyle_concurrent_replacement", "head_file_identity_changed"
            )
        with tempfile.TemporaryDirectory(
            prefix="agent-canon-pydocstyle-base-"
        ) as base_dir:
            base_root = Path(base_dir)
            base_paths = materialize_base_files(
                root, packet, all_production_paths, base_root
            )
            copy_head_configs(root, config_files, base_root)
            all_base_diagnostics = run_pydocstyle(
                base_root,
                base_paths,
                args.python_bin,
                canonical_config,
            )

        selected_set = set(selected)
        baseline_set = set(baseline_paths)
        head_diagnostics = tuple(
            diagnostic
            for diagnostic in all_head_diagnostics
            if diagnostic.path in selected_set
        )
        unchanged_diagnostics = tuple(
            diagnostic
            for diagnostic in all_head_diagnostics
            if diagnostic.path in baseline_set
        )
        base_diagnostics = tuple(
            diagnostic
            for diagnostic in all_base_diagnostics
            if diagnostic.path in selected_set
        )
        base_by_identity = {
            diagnostic.identity: diagnostic for diagnostic in base_diagnostics
        }
        blocking: list[dict[str, object]] = []
        baseline: list[dict[str, object]] = []
        all_base_identities = {
            diagnostic.identity for diagnostic in all_base_diagnostics
        }
        for diagnostic in unchanged_diagnostics:
            record = diagnostic.report()
            record["base_match"] = diagnostic.identity in all_base_identities
            record["worsened"] = False
            record["classification"] = "unchanged_baseline"
            baseline.append(record)
        for diagnostic in {item.identity: item for item in head_diagnostics}.values():
            record = diagnostic.report()
            record["base_match"] = diagnostic.identity in base_by_identity
            record["worsened"] = diagnostic.identity not in base_by_identity
            if record["worsened"]:
                record["classification"] = "changed_production"
                blocking.append(record)
            else:
                record["classification"] = "baseline"
                baseline.append(record)
        report = {
            "schema": "agent-canon.pydocstyle.changed-scope.v1",
            "root": str(root),
            "base_sha": packet.base_sha,
            "head_sha": packet.head_sha,
            "changed_paths": list(packet.changed_paths),
            "selected_production_paths": selected,
            "baseline_production_paths": baseline_paths,
            "skipped_paths": skipped,
            "unchanged_paths_baseline": {
                "evidence": "production_only_report_baseline",
                "path_count": len(baseline_paths),
                "diagnostic_count": len(unchanged_diagnostics),
            },
            "head_diagnostics": [item.report() for item in all_head_diagnostics],
            "base_diagnostics": [item.report() for item in base_diagnostics],
            "blocking_diagnostics": blocking,
            "baseline_diagnostics": baseline,
            "diagnostic_identity": "code+qualified_module_class_function",
            "config": str(canonical_config)
            if canonical_config
            else "parent_discovered",
        }
        if args.report_out:
            report_path = Path(args.report_out)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        print(f"PYDOCSTYLE_CHANGED_SCOPE_SELECTED={len(selected)}")
        print(
            f"PYDOCSTYLE_CHANGED_SCOPE_SKIPPED={sum(len(items) for items in skipped.values())}"
        )
        print(f"PYDOCSTYLE_CHANGED_SCOPE_BASELINE={len(baseline)}")
        print(f"PYDOCSTYLE_CHANGED_SCOPE_BLOCKING={len(blocking)}")
        for item in blocking:
            print(
                "PYDOCSTYLE_CHANGED_SCOPE_FINDING="
                f"{item['code']}:{item['qualified_name']}:{item['path']}:{item['line']}"
            )
        if blocking:
            print("PYDOCSTYLE_CHANGED_SCOPE=fail")
            print("PYDOCSTYLE_CHANGED_SCOPE_REASON=changed_production_diagnostic")
            return 1
        print("PYDOCSTYLE_CHANGED_SCOPE=pass")
        print("PYDOCSTYLE_CHANGED_SCOPE_REASON=changed_production_delta_clean")
        return 0
    except ScopeFailure as error:
        return emit_failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
