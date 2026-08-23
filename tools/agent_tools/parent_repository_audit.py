#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Enumerates canonical parent-repository audit units by semantic change surface and records selected tracked evidence.
# upstream design ../../documents/design/parent-repository-audit.md owns unit boundaries, migration, and failure semantics
# upstream design ../../documents/parent-repository-audit/README.md owns the audit surface reader route
# upstream implementation ./agent_canon_source_root.py resolves the AgentCanon source root and typed source-root failures
# downstream implementation ../../agents/skills/parent-repository-audit.md consumes deterministic unit selection and closure protocol
# downstream implementation ../../tests/agent_tools/test_parent_repository_audit.py tests semantic selection and failure semantics
# @dependency-end
"""Enumerate and validate the canonical parent-repository audit units."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Final, Literal

from agent_canon_source_root import SourceRootFailure, resolve_agent_canon_source_root

UNIT_ROOT: Final = Path("documents/parent-repository-audit/audit-unit")
SCHEMA: Final = "agent_canon.parent_repository_audit.v1"
AuditStatus = Literal["pass", "failed", "blocked"]
UnitStatus = Literal["pass", "closed", "failed", "deferred", "blocked"]
REQUIRED_SECTIONS: Final = (
    "Owner Responsibility",
    "Invariant",
    "Evidence Sources",
    "Repair Route",
    "Validation",
    "Close Condition",
    "Related Change Surfaces",
    "Legacy Migration IDs",
)
SURFACE_RE: Final = re.compile(r"\bsurface:([a-z0-9_.-]+)\b")
LEGACY_ID_RE: Final = re.compile(r"\bPRA-M[0-9]{2}\b|\bPRA-[CX][0-9]{3}\b")


class AuditFailure(ValueError):
    """One typed audit enumeration or validation failure."""

    def __init__(self, code: str, detail: str, *, status: AuditStatus = "failed") -> None:
        """Initialize one stable machine-readable failure."""
        self.code = code
        self.detail = detail
        self.status: AuditStatus = status
        super().__init__(f"{code}:{detail}")


@dataclass(frozen=True)
class AuditUnit:
    """One self-contained Markdown audit unit."""

    unit_id: str
    path: str
    surfaces: tuple[str, ...]
    legacy_ids: tuple[str, ...]


@dataclass(frozen=True)
class AuditEvidence:
    """Tracked-path evidence without classifying ownership or audit-unit coverage."""

    tracked_path_count: int | None = None
    unit_statuses: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditPayload:
    """Own the audit result fields and their text/JSON projections."""

    status: AuditStatus
    failure_code: str | None = None
    failure_detail: str | None = None
    source_root: str | None = None
    parent_root: str | None = None
    unit_paths: tuple[str, ...] | None = None
    unit_records: tuple[AuditUnit, ...] | None = None
    selected_surfaces: tuple[str, ...] = ()
    scope_paths: tuple[str, ...] | None = None
    evidence: AuditEvidence = AuditEvidence()

    def to_json_dict(self) -> dict[str, object]:
        """Convert the owned result into the stable JSON packet shape."""
        payload: dict[str, object] = {
            "schema": SCHEMA,
            "status": self.status,
        }
        optional_values: tuple[tuple[str, object | None], ...] = (
            ("failure_code", self.failure_code),
            ("failure_detail", self.failure_detail),
            ("source_root", self.source_root),
            ("parent_root", self.parent_root),
            ("tracked_path_count", self.evidence.tracked_path_count),
        )
        for key, value in optional_values:
            if value is not None:
                payload[key] = value
        if self.unit_paths is not None:
            payload["unit_paths"] = list(self.unit_paths)
        if self.unit_records is not None:
            payload["unit_records"] = [asdict(unit) for unit in self.unit_records]
        if self.selected_surfaces:
            payload["selected_surfaces"] = list(self.selected_surfaces)
        if self.scope_paths is not None:
            payload["scope_paths"] = list(self.scope_paths)
        payload["unit_statuses"] = list(self.evidence.unit_statuses)
        return payload


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


def final_audit_status(unit_statuses: Sequence[str]) -> str:
    """Aggregate unit receipts without promoting failed work to ``closed``."""
    statuses = {status for status in unit_statuses if status}
    if statuses & {"failed", "deferred"}:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    if statuses and statuses <= {"pass", "closed"}:
        return "closed"
    return "failed"


def _load_units(source_root: Path) -> tuple[AuditUnit, ...]:
    """Load and validate every canonical unit in deterministic path order."""
    unit_root = _safe_child(
        source_root / UNIT_ROOT,
        source_root,
        code="parent_repository_audit_path_escape",
    )
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


def git_tracked_bytes(parent_root: Path) -> bytes:
    """Read raw parent Git path evidence without entering a submodule."""
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
    return result.stdout


def _decode_tracked_paths(raw_output: bytes, parent_root: Path) -> tuple[str, ...]:
    """Decode NUL-separated Git path evidence into stable parent-relative paths."""
    try:
        decoded = raw_output.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditFailure(
            "parent_repository_audit_parent_git_invalid",
            f"non-UTF8 tracked path output: {parent_root}",
        ) from exc
    return tuple(sorted(path for path in decoded.split("\0") if path))


def _scope_paths(
    parent_root: Path,
    tracked: Sequence[str],
    scopes: Sequence[str],
) -> tuple[str, ...]:
    """Resolve optional evidence scopes to tracked parent-relative paths."""
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


def _normalize_surfaces(raw_surfaces: Sequence[str]) -> tuple[str, ...]:
    """Normalize repeated CLI surface selectors without adding another registry."""
    return tuple(
        dict.fromkeys(
            surface.removeprefix("surface:")
            for surface in raw_surfaces
            if surface.removeprefix("surface:")
        )
    )


def _select_units(
    units: Sequence[AuditUnit],
    requested_surfaces: Sequence[str],
) -> tuple[AuditUnit, ...]:
    """Select units by their canonical semantic change-surface relation."""
    requested = _normalize_surfaces(requested_surfaces)
    if not requested:
        return tuple(units)
    available = {surface for unit in units for surface in unit.surfaces}
    unknown = tuple(surface for surface in requested if surface not in available)
    if unknown:
        raise AuditFailure(
            "parent_repository_audit_surface_unknown",
            "surfaces=" + ",".join(unknown),
        )
    requested_set = set(requested)
    return tuple(unit for unit in units if requested_set.intersection(unit.surfaces))


def _resolution_and_units() -> tuple[Path, tuple[AuditUnit, ...]]:
    """Resolve the source root before loading canonical units."""
    resolution = resolve_agent_canon_source_root(Path.cwd())
    return resolution.source_root, _load_units(resolution.source_root)


def _payload_text(payload: AuditPayload) -> str:
    """Render a stable text packet for shell and skill readback."""
    lines = [
        f"PARENT_REPOSITORY_AUDIT_SCHEMA={SCHEMA}",
        f"PARENT_REPOSITORY_AUDIT_STATUS={payload.status}",
    ]
    optional_values: tuple[tuple[str, object | None], ...] = (
        ("failure_code", payload.failure_code),
        ("source_root", payload.source_root),
        ("parent_root", payload.parent_root),
        ("tracked_path_count", payload.evidence.tracked_path_count),
    )
    for key, value in optional_values:
        if value is not None:
            lines.append(f"PARENT_REPOSITORY_AUDIT_{key.upper()}={value}")
    for surface in payload.selected_surfaces:
        lines.append(f"PARENT_REPOSITORY_AUDIT_SURFACE={surface}")
    for path in payload.unit_paths or ():
        lines.append(f"PARENT_REPOSITORY_AUDIT_UNIT={path}")
    if payload.evidence.unit_statuses:
        lines.append(
            "PARENT_REPOSITORY_AUDIT_UNIT_STATUSES="
            + ",".join(payload.evidence.unit_statuses)
        )
    return "\n".join(lines)


def _render(payload: AuditPayload, output_format: str) -> None:
    """Write one typed text or JSON packet."""
    if output_format == "json":
        print(json.dumps(payload.to_json_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_payload_text(payload))


def _base_payload(
    source_root: Path,
    parent_root: Path,
    units: Sequence[AuditUnit],
    selected_surfaces: Sequence[str],
) -> AuditPayload:
    """Build common packet fields."""
    return AuditPayload(
        status="pass",
        source_root=str(source_root),
        parent_root=str(parent_root),
        unit_paths=tuple(unit.path for unit in units),
        unit_records=tuple(units),
        selected_surfaces=_normalize_surfaces(selected_surfaces),
    )


def _run_list(args: argparse.Namespace) -> AuditPayload:
    """Enumerate selected units without auditing their parent tree."""
    source_root, units = _resolution_and_units()
    parent_root = Path(args.root).expanduser().resolve()
    tracked = _decode_tracked_paths(git_tracked_bytes(parent_root), parent_root)
    scope_paths = _scope_paths(parent_root, tracked, args.scope)
    selected = _select_units(units, args.surface)
    return replace(
        _base_payload(source_root, parent_root, selected, args.surface),
        scope_paths=tuple(scope_paths),
        evidence=AuditEvidence(tracked_path_count=len(scope_paths)),
    )


def _run_check(args: argparse.Namespace) -> AuditPayload:
    """Validate unit contracts and aggregate unit receipts."""
    source_root, units = _resolution_and_units()
    parent_root = Path(args.root).expanduser().resolve()
    tracked = _decode_tracked_paths(git_tracked_bytes(parent_root), parent_root)
    scope_paths = _scope_paths(parent_root, tracked, args.scope)
    selected = _select_units(units, args.surface)
    requested_statuses = tuple(args.unit_status)
    aggregate_status = (
        final_audit_status(requested_statuses) if requested_statuses else "closed"
    )
    audit_status: AuditStatus
    if aggregate_status == "failed":
        audit_status = "failed"
    elif aggregate_status == "blocked":
        audit_status = "blocked"
    else:
        audit_status = "pass"
    return replace(
        _base_payload(source_root, parent_root, selected, args.surface),
        status=audit_status,
        scope_paths=tuple(scope_paths),
        evidence=AuditEvidence(
            tracked_path_count=len(scope_paths),
            unit_statuses=requested_statuses,
        ),
        failure_code=(
            "parent_repository_audit_unit_status_failed"
            if aggregate_status == "failed"
            else None
        ),
    )


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
            help=(
                "Parent-relative tracked file or directory evidence scope; repeatable. "
                "This does not classify ownership or select audit units."
            ),
        )
        command_parser.add_argument(
            "--surface",
            action="append",
            default=[],
            help=(
                "Semantic surface ID from a unit's Related Change Surfaces section; "
                "repeatable. Defaults to all units."
            ),
        )
        command_parser.add_argument(
            "--unit-status",
            action="append",
            choices=("pass", "closed", "failed", "deferred", "blocked"),
            default=[],
            help="Record a unit receipt for final status aggregation; repeatable.",
        )
        command_parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one deterministic parent-repository audit packet."""
    args = build_parser().parse_args(argv)
    try:
        payload = _run_list(args) if args.command == "list" else _run_check(args)
    except SourceRootFailure as exc:
        payload = AuditPayload(
            status="blocked",
            failure_code=exc.code,
            failure_detail=exc.detail,
        )
        _render(payload, args.format)
        return 2
    except AuditFailure as exc:
        payload = AuditPayload(
            status=exc.status,
            failure_code=exc.code,
            failure_detail=exc.detail,
        )
        _render(payload, args.format)
        return 2 if exc.status == "blocked" else 1
    _render(payload, args.format)
    return 0 if payload.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
