#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Enumerates and validates the canonical parent-repository audit unit Markdown set against a parent tracked tree.
# upstream design ../../documents/design/parent-repository-audit.md owns unit boundaries, migration, and failure semantics
# upstream design ../../documents/parent-repository-audit/README.md owns the audit surface reader route
# upstream implementation ./agent_canon_source_root.py resolves the AgentCanon source root and typed source-root failures
# downstream implementation ../../agents/skills/parent-repository-audit.md consumes deterministic unit selection and closure protocol
# downstream implementation ../../tests/agent_tools/test_parent_repository_audit.py tests coverage and failure semantics
# @dependency-end
"""Enumerate and validate the canonical parent-repository audit units."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from agent_canon_source_root import SourceRootFailure, resolve_agent_canon_source_root

UNIT_ROOT: Final = Path("documents/parent-repository-audit/audit-unit")
SCHEMA: Final = "agent_canon.parent_repository_audit.v1"
REQUIRED_SECTIONS: Final = (
    "Owner Responsibility",
    "Invariant",
    "Evidence Sources",
    "Repair Route",
    "Validation",
    "Close Condition",
    "Related Change Surfaces",
    "Scope Patterns",
    "Legacy Migration IDs",
)
SURFACE_RE: Final = re.compile(r"\bsurface:([a-z0-9_.-]+)\b")
PATTERN_RE: Final = re.compile(r"\bpattern:([^\s`]+)")
LEGACY_ID_RE: Final = re.compile(r"\bPRA-M[0-9]{2}\b|\bPRA-[CX][0-9]{3}\b")


class AuditFailure(ValueError):
    """One typed audit enumeration or validation failure."""

    def __init__(self, code: str, detail: str, *, status: str = "failed") -> None:
        """Initialize one stable machine-readable failure."""
        self.code = code
        self.detail = detail
        self.status = status
        super().__init__(f"{code}:{detail}")


@dataclass(frozen=True)
class AuditUnit:
    """One self-contained Markdown audit unit."""

    unit_id: str
    path: str
    scope_patterns: tuple[str, ...]
    surfaces: tuple[str, ...]
    legacy_ids: tuple[str, ...]


def _section_text(text: str, heading: str) -> str:
    """Return one Markdown section body without interpreting prose as policy."""
    marker = f"## {heading}"
    lines = text.splitlines()
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return ""
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body).strip()


def _safe_child(path: Path, root: Path, *, code: str) -> Path:
    """Resolve a path and keep it below the selected owner root."""
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise AuditFailure(code, f"path={path} root={root}")
    return resolved


def _parse_patterns(section: str, *, path: Path) -> tuple[str, ...]:
    """Extract stable parent-relative scope patterns from one unit section."""
    patterns = tuple(dict.fromkeys(PATTERN_RE.findall(section)))
    if not patterns:
        raise AuditFailure(
            "parent_repository_audit_unit_invalid",
            f"missing scope pattern: {path}",
        )
    for pattern in patterns:
        pattern_path = Path(pattern)
        if pattern.startswith("/") or pattern.startswith("~") or ".." in pattern_path.parts:
            raise AuditFailure(
                "parent_repository_audit_path_escape",
                f"pattern={pattern} unit={path}",
            )
    return patterns


def _load_units(source_root: Path) -> tuple[AuditUnit, ...]:
    """Load and validate every canonical unit in deterministic path order."""
    unit_root = _safe_child(source_root / UNIT_ROOT, source_root, code="parent_repository_audit_path_escape")
    if not unit_root.is_dir():
        raise AuditFailure(
            "parent_repository_audit_unit_invalid",
            f"unit directory missing: {unit_root}",
        )
    paths = tuple(sorted(unit_root.glob("*.md")))
    if not paths:
        raise AuditFailure(
            "parent_repository_audit_unit_invalid",
            f"no audit units: {unit_root}",
        )
    units: list[AuditUnit] = []
    for path in paths:
        safe_path = _safe_child(path, source_root, code="parent_repository_audit_path_escape")
        text = safe_path.read_text(encoding="utf-8")
        missing = tuple(
            heading for heading in REQUIRED_SECTIONS if not _section_text(text, heading)
        )
        if missing:
            raise AuditFailure(
                "parent_repository_audit_unit_invalid",
                f"unit={safe_path} missing_sections={','.join(missing)}",
            )
        related = _section_text(text, "Related Change Surfaces")
        legacy = _section_text(text, "Legacy Migration IDs")
        surfaces = tuple(dict.fromkeys(SURFACE_RE.findall(related)))
        legacy_ids = tuple(dict.fromkeys(LEGACY_ID_RE.findall(legacy)))
        if not surfaces:
            raise AuditFailure(
                "parent_repository_audit_unit_invalid",
                f"missing change surface: {safe_path}",
            )
        units.append(
            AuditUnit(
                unit_id=safe_path.stem,
                path=safe_path.relative_to(source_root).as_posix(),
                scope_patterns=_parse_patterns(
                    _section_text(text, "Scope Patterns"), path=safe_path
                ),
                surfaces=surfaces,
                legacy_ids=legacy_ids,
            )
        )
    legacy_owner: dict[str, str] = {}
    for unit in units:
        for legacy_id in unit.legacy_ids:
            previous = legacy_owner.get(legacy_id)
            if previous is not None:
                raise AuditFailure(
                    "parent_repository_audit_unit_invalid",
                    f"duplicate legacy migration ID={legacy_id}: {previous}, {unit.path}",
                )
            legacy_owner[legacy_id] = unit.path
    return tuple(units)


def _tracked_paths(parent_root: Path) -> tuple[str, ...]:
    """Read the parent Git tracked tree without entering a submodule."""
    result = subprocess.run(
        ["git", "-C", str(parent_root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise AuditFailure(
            "parent_repository_audit_parent_git_missing",
            detail or f"git ls-files failed: {parent_root}",
        )
    try:
        decoded = result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditFailure(
            "parent_repository_audit_parent_git_invalid",
            f"non-UTF8 tracked path output: {parent_root}",
        ) from exc
    return tuple(sorted(path for path in decoded.split("\0") if path))


def _scope_paths(parent_root: Path, tracked: Sequence[str], scopes: Sequence[str]) -> tuple[str, ...]:
    """Resolve optional scope paths to tracked parent-relative paths."""
    if not scopes:
        return tuple(tracked)
    selected: set[str] = set()
    tracked_set = set(tracked)
    for raw_scope in scopes:
        raw_path = Path(raw_scope)
        candidate = raw_path if raw_path.is_absolute() else parent_root / raw_path
        safe = _safe_child(
            candidate,
            parent_root,
            code="parent_repository_audit_path_escape",
        )
        relative = safe.relative_to(parent_root).as_posix() if safe != parent_root else "."
        if safe == parent_root:
            selected.update(tracked)
        elif safe.is_dir():
            prefix = f"{relative}/"
            selected.update(path for path in tracked if path.startswith(prefix))
        elif relative in tracked_set:
            selected.add(relative)
        else:
            raise AuditFailure(
                "parent_repository_audit_scope_missing",
                f"scope={raw_scope} parent={parent_root}",
            )
    return tuple(sorted(selected))


def _matches(pattern: str, tracked_path: str) -> bool:
    """Match one unit pattern against one parent-relative tracked path."""
    if pattern == "all-tracked":
        return True
    return fnmatch.fnmatchcase(tracked_path, pattern)


def _unit_matches(units: Iterable[AuditUnit], paths: Sequence[str]) -> dict[str, tuple[str, ...]]:
    """Return stable unit IDs matched by each tracked path."""
    matches: dict[str, tuple[str, ...]] = {}
    for path in paths:
        matching = tuple(
            unit.unit_id
            for unit in units
            if any(_matches(pattern, path) for pattern in unit.scope_patterns)
        )
        matches[path] = matching
    return matches


def _resolution_and_units() -> tuple[Path, tuple[AuditUnit, ...]]:
    """Resolve the source root before loading canonical units."""
    resolution = resolve_agent_canon_source_root(Path.cwd())
    return resolution.source_root, _load_units(resolution.source_root)


def _select_units(units: Sequence[AuditUnit], scope_paths: Sequence[str], scopes_given: bool) -> tuple[AuditUnit, ...]:
    """Select units in canonical order for a full or scoped audit."""
    if not scopes_given:
        return tuple(units)
    matches = _unit_matches(units, scope_paths)
    selected_ids = {unit_id for values in matches.values() for unit_id in values}
    return tuple(unit for unit in units if unit.unit_id in selected_ids)


def _payload_text(payload: dict[str, object]) -> str:
    """Render a stable text packet for shell and skill readback."""
    lines = [
        f"PARENT_REPOSITORY_AUDIT_SCHEMA={payload['schema']}",
        f"PARENT_REPOSITORY_AUDIT_STATUS={payload['status']}",
    ]
    for key in ("failure_code", "source_root", "parent_root", "tracked_path_count", "uncovered_path_count", "overlap_path_count"):
        if key in payload:
            lines.append(f"PARENT_REPOSITORY_AUDIT_{key.upper()}={payload[key]}")
    for path in payload.get("unit_paths", []):
        lines.append(f"PARENT_REPOSITORY_AUDIT_UNIT={path}")
    for path in payload.get("uncovered_paths", []):
        lines.append(f"PARENT_REPOSITORY_AUDIT_UNCOVERED={path}")
    return "\n".join(lines)


def _render(payload: dict[str, object], output_format: str) -> None:
    """Write one typed text or JSON packet."""
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_payload_text(payload))


def _base_payload(source_root: Path, parent_root: Path, units: Sequence[AuditUnit]) -> dict[str, object]:
    """Build common packet fields."""
    return {
        "schema": SCHEMA,
        "source_root": str(source_root),
        "parent_root": str(parent_root),
        "unit_paths": [unit.path for unit in units],
        "unit_records": [asdict(unit) for unit in units],
    }


def _run_list(args: argparse.Namespace) -> dict[str, object]:
    """Enumerate selected units without auditing their parent tree."""
    source_root, units = _resolution_and_units()
    parent_root = Path(args.root).expanduser().resolve()
    tracked = _tracked_paths(parent_root)
    scope_paths = _scope_paths(parent_root, tracked, args.scope)
    selected = _select_units(units, scope_paths, bool(args.scope))
    payload = _base_payload(source_root, parent_root, selected)
    payload.update(
        {
            "status": "pass",
            "scope_paths": list(scope_paths),
            "tracked_path_count": len(tracked),
        }
    )
    return payload


def _run_check(args: argparse.Namespace) -> dict[str, object]:
    """Validate unit contracts and tracked-tree coverage."""
    source_root, units = _resolution_and_units()
    parent_root = Path(args.root).expanduser().resolve()
    tracked = _tracked_paths(parent_root)
    scope_paths = _scope_paths(parent_root, tracked, args.scope)
    selected = _select_units(units, scope_paths, bool(args.scope))
    matches = _unit_matches(selected, scope_paths)
    uncovered = tuple(path for path, values in matches.items() if not values)
    overlaps = {
        path: list(values) for path, values in matches.items() if len(values) > 1
    }
    payload = _base_payload(source_root, parent_root, selected)
    payload.update(
        {
            "status": "failed" if uncovered else "pass",
            "scope_paths": list(scope_paths),
            "tracked_path_count": len(scope_paths),
            "uncovered_paths": list(uncovered),
            "overlap_paths": overlaps,
            "uncovered_path_count": len(uncovered),
            "overlap_path_count": len(overlaps),
        }
    )
    if uncovered:
        payload["failure_code"] = "parent_repository_audit_uncovered_tracked_path"
    return payload


def build_parser() -> argparse.ArgumentParser:
    """Build the list/check CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("list", "check"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--root", required=True, help="Parent repository root.")
        command_parser.add_argument(
            "--scope",
            action="append",
            default=[],
            help="Parent-relative file or directory scope; repeatable.",
        )
        command_parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one deterministic parent-repository audit packet."""
    args = build_parser().parse_args(argv)
    try:
        payload = _run_list(args) if args.command == "list" else _run_check(args)
    except SourceRootFailure as exc:
        payload = {
            "schema": SCHEMA,
            "status": "blocked",
            "failure_code": exc.code,
            "failure_detail": exc.detail,
        }
        _render(payload, args.format)
        return 2
    except AuditFailure as exc:
        payload = {
            "schema": SCHEMA,
            "status": exc.status,
            "failure_code": exc.code,
            "failure_detail": exc.detail,
        }
        _render(payload, args.format)
        return 2 if exc.status == "blocked" else 1
    _render(payload, args.format)
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
