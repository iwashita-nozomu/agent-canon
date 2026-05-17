#!/usr/bin/env python3
# @dependency-start
# responsibility Inventories machine-readable log and hook output fields from hooks, skills, and tools.
# upstream design ../../agents/evals/results/hook-runs/README.md hook result accumulation contract
# downstream implementation ../../.codex/hooks/log_surface_inventory_guard.py blocks stale inventory drift
# downstream implementation ../../tests/agent_tools/test_log_surface_inventory.py validates field extraction and baseline checks
# @dependency-end
"""Inventory machine-readable fields emitted by AgentCanon hooks, skills, and tools."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

SurfaceKind = Literal["hook", "skill", "tool"]
Certainty = Literal["static", "dynamic"]

DEFAULT_BASELINE = Path("documents") / "log-surface-inventory.json"
KEY_VALUE_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*)=")
SHELL_ECHO_PATTERN = re.compile(r"^\s*(?:echo|printf)\s+(?:--\s+)?(?P<value>.+)$")
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "reports",
}
SKILL_PATTERNS = (
    ".agents/skills/*/SKILL.md",
    ".claude/skills/*/SKILL.md",
    "agents/skills/*.md",
)
HOOK_PATTERNS = (".codex/hooks/*.py", ".codex/hooks/*.sh")
TOOL_PATTERNS = ("tools/*.py", "tools/*.sh", "tools/**/*.py", "tools/**/*.sh", "tools/**/*.bash")


@dataclass(frozen=True, order=True)
class FieldRecord:
    """One emitted machine-readable field discovered from source."""

    path: str
    surface: SurfaceKind
    emitter: str
    field: str
    line: int
    certainty: Certainty

    def machine_line(self, prefix: str) -> str:
        """Render one stable machine-readable inventory line."""
        return (
            f"{prefix}={self.path}:{self.line}:"
            f"{self.surface}:{self.emitter}:{self.certainty}:{self.field}"
        )


@dataclass(frozen=True)
class Inventory:
    """Stable inventory payload."""

    schema_version: int
    scanned_files: tuple[str, ...]
    records: tuple[FieldRecord, ...]

    def to_json_payload(self) -> dict[str, object]:
        """Return a deterministic JSON-compatible payload."""
        return {
            "schema_version": self.schema_version,
            "scanned_files": list(self.scanned_files),
            "records": [asdict(record) for record in self.records],
        }


@dataclass(frozen=True)
class BaselineDiff:
    """Structured difference between current and baseline inventories."""

    added: tuple[FieldRecord, ...]
    removed: tuple[FieldRecord, ...]

    @property
    def has_drift(self) -> bool:
        """Return whether the baseline differs from the current inventory."""
        return bool(self.added or self.removed)


class PythonLogSurfaceVisitor(ast.NodeVisitor):
    """Extract emitted field names from one Python AST."""

    def __init__(self, relative_path: str, surface: SurfaceKind) -> None:
        """Initialize the visitor for one root-relative Python path."""
        self.relative_path = relative_path
        self.surface: SurfaceKind = surface
        self.records: list[FieldRecord] = []
        self.dict_assignments: dict[str, tuple[tuple[str, Certainty], ...]] = {}

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """Record simple dict assignments that later logging calls may emit."""
        fields = self._dict_fields(node.value)
        if not fields:
            self.generic_visit(node)
            return
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.dict_assignments[target.id] = fields
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        """Record annotated dict assignments."""
        if isinstance(node.target, ast.Name) and node.value is not None:
            fields = self._dict_fields(node.value)
            if fields:
                self.dict_assignments[node.target.id] = fields
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Record print/json/log-helper calls."""
        call_name = self._call_name(node.func)
        if call_name == "print":
            self._record_print_call(node)
        if call_name.endswith("json.dump") or call_name.endswith("json.dumps"):
            self._record_json_arg(node, "json_object")
        if "log" in call_name and call_name not in {"logging.getLogger"}:
            self._record_log_helper_args(node)
        self.generic_visit(node)

    def _record_print_call(self, node: ast.Call) -> None:
        for arg in node.args:
            if isinstance(arg, ast.Call):
                call_name = self._call_name(arg.func)
                if call_name.endswith("json.dumps"):
                    self._record_json_arg(arg, "json_stdout")
                    continue
            for field, certainty in self._key_value_fields(arg):
                self._add_record("key_value_stdout", field, node.lineno, certainty)

    def _record_json_arg(self, node: ast.Call, emitter: str) -> None:
        if not node.args:
            return
        for field, certainty in self._fields_from_node(node.args[0]):
            self._add_record(emitter, field, node.lineno, certainty)

    def _record_log_helper_args(self, node: ast.Call) -> None:
        for arg in node.args:
            if isinstance(arg, ast.Dict) or (
                isinstance(arg, ast.Name) and arg.id in self.dict_assignments
            ):
                for field, certainty in self._fields_from_node(arg):
                    self._add_record("json_log_helper", field, node.lineno, certainty)

    def _fields_from_node(self, node: ast.AST) -> tuple[tuple[str, Certainty], ...]:
        if isinstance(node, ast.Dict):
            return self._dict_fields(node)
        if isinstance(node, ast.Name):
            return self.dict_assignments.get(node.id, (("<dynamic>", cast(Certainty, "dynamic")),))
        return (("<dynamic>", cast(Certainty, "dynamic")),)

    def _dict_fields(self, node: ast.AST) -> tuple[tuple[str, Certainty], ...]:
        if not isinstance(node, ast.Dict):
            return ()
        fields: list[tuple[str, Certainty]] = []
        for key in node.keys:
            if key is None:
                fields.append(("<dynamic>", cast(Certainty, "dynamic")))
            elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                fields.append((key.value, cast(Certainty, "static")))
            else:
                fields.append(("<dynamic>", cast(Certainty, "dynamic")))
        return tuple(fields)

    def _key_value_fields(self, node: ast.AST) -> tuple[tuple[str, Certainty], ...]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            match = KEY_VALUE_PATTERN.match(node.value)
            return ((match.group(1), cast(Certainty, "static")),) if match else ()
        if isinstance(node, ast.JoinedStr):
            return self._joined_string_key(node)
        return ()

    def _joined_string_key(self, node: ast.JoinedStr) -> tuple[tuple[str, Certainty], ...]:
        if not node.values:
            return ()
        first = node.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            match = KEY_VALUE_PATTERN.match(first.value)
            return ((match.group(1), cast(Certainty, "static")),) if match else ()
        return (("<dynamic>", cast(Certainty, "dynamic")),)

    def _add_record(
        self,
        emitter: str,
        field: str,
        line: int,
        certainty: Certainty,
    ) -> None:
        self.records.append(
            FieldRecord(
                path=self.relative_path,
                surface=self.surface,
                emitter=emitter,
                field=field,
                line=line,
                certainty=certainty,
            )
        )

    def _call_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = self._call_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""


class ShellLogSurfaceScanner:
    """Extract emitted key-value field names from one shell script."""

    def __init__(self, relative_path: str, surface: SurfaceKind) -> None:
        """Initialize the scanner for one root-relative shell path."""
        self.relative_path = relative_path
        self.surface: SurfaceKind = surface

    def scan(self, text: str) -> tuple[FieldRecord, ...]:
        """Return machine-readable shell output fields."""
        records: list[FieldRecord] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            match = SHELL_ECHO_PATTERN.match(raw_line)
            if not match:
                continue
            value = self._first_shell_value(match.group("value"))
            field, certainty = self._shell_key(value)
            if field:
                records.append(
                    FieldRecord(
                        path=self.relative_path,
                        surface=self.surface,
                        emitter="shell_key_value_stdout",
                        field=field,
                        line=line_number,
                        certainty=certainty,
                    )
                )
        return tuple(records)

    def _first_shell_value(self, value: str) -> str:
        stripped = value.strip()
        if stripped.startswith(('"', "'")):
            quote = stripped[0]
            end = stripped.find(quote, 1)
            if end != -1:
                return stripped[1:end]
        return stripped.split()[0] if stripped.split() else ""

    def _shell_key(self, value: str) -> tuple[str, Certainty]:
        if value.startswith(("$", "${")):
            return "<dynamic>", cast(Certainty, "dynamic")
        match = KEY_VALUE_PATTERN.match(value)
        if match:
            return match.group(1), cast(Certainty, "static")
        return "", cast(Certainty, "static")


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Statically inventory machine-readable field names emitted by "
            "AgentCanon hooks, skills, and tools."
        )
    )
    parser.add_argument("paths", nargs="*", help="Optional files/directories to scan.")
    parser.add_argument("--root", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--output", help="Write the JSON inventory to this path.")
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE),
        help="Baseline JSON path for --check. Defaults to documents/log-surface-inventory.json.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare the current inventory with the baseline and fail on drift.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for non-check runs.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress pass output for hook use.",
    )
    return parser


def git_tracked_files(root: Path) -> tuple[str, ...]:
    """Return tracked files, or an empty tuple outside git."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ()
    return tuple(line for line in result.stdout.splitlines() if line)


def iter_surface_files(root: Path, raw_paths: list[str]) -> tuple[Path, ...]:
    """Return selected hook, skill, and tool files."""
    if raw_paths:
        candidates = selected_files(root, raw_paths)
    else:
        candidates = tracked_surface_files(root)
    files: list[Path] = []
    for candidate in candidates:
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if should_skip(relative):
            continue
        if surface_kind(relative) is not None:
            files.append(candidate)
    return tuple(sorted(set(files)))


def selected_files(root: Path, raw_paths: list[str]) -> tuple[Path, ...]:
    """Return files under explicit paths."""
    files: list[Path] = []
    for raw_path in raw_paths:
        candidate = (root / raw_path).resolve()
        if candidate.is_file():
            files.append(candidate)
        elif candidate.is_dir():
            files.extend(path for path in candidate.rglob("*") if path.is_file())
    return tuple(files)


def tracked_surface_files(root: Path) -> tuple[Path, ...]:
    """Return tracked files matching known hook/skill/tool surfaces."""
    tracked = tuple(root / path for path in git_tracked_files(root))
    return tuple(path for path in tracked if surface_kind(path.relative_to(root)) is not None)


def should_skip(relative: Path) -> bool:
    """Return whether one root-relative path is excluded."""
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def surface_kind(relative: Path) -> SurfaceKind | None:
    """Classify one root-relative path."""
    text = relative.as_posix()
    if matches_any(text, HOOK_PATTERNS):
        return "hook"
    if matches_any(text, SKILL_PATTERNS):
        return "skill"
    if matches_any(text, TOOL_PATTERNS):
        return "tool"
    return None


def matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    """Return whether one POSIX path matches any glob pattern."""
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def build_inventory(root: Path, raw_paths: list[str]) -> Inventory:
    """Build a stable log-surface inventory."""
    records: list[FieldRecord] = []
    scanned: list[str] = []
    for path in iter_surface_files(root, raw_paths):
        relative = path.relative_to(root).as_posix()
        kind = surface_kind(Path(relative))
        if kind is None:
            continue
        scanned.append(relative)
        records.extend(scan_one_file(root, path, relative, kind))
    return Inventory(
        schema_version=1,
        scanned_files=tuple(sorted(scanned)),
        records=tuple(sorted(records)),
    )


def scan_one_file(
    root: Path,
    path: Path,
    relative: str,
    kind: SurfaceKind,
) -> tuple[FieldRecord, ...]:
    """Return field records for one source file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return scan_python_file(relative, kind, text)
    if path.suffix in {".sh", ".bash"}:
        return ShellLogSurfaceScanner(relative, kind).scan(text)
    if path.name == "SKILL.md" or path.suffix == ".md":
        return scan_markdown_key_values(relative, kind, text)
    _ = root
    return ()


def scan_python_file(relative: str, kind: SurfaceKind, text: str) -> tuple[FieldRecord, ...]:
    """Return emitted fields from one Python file."""
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError as exc:
        return (
            FieldRecord(
                path=relative,
                surface=kind,
                emitter="python_syntax_error",
                field="<syntax-error>",
                line=exc.lineno or 1,
                certainty="dynamic",
            ),
        )
    visitor = PythonLogSurfaceVisitor(relative, kind)
    visitor.visit(tree)
    return tuple(visitor.records)


def scan_markdown_key_values(
    relative: str,
    kind: SurfaceKind,
    text: str,
) -> tuple[FieldRecord, ...]:
    """Return key-value examples from skill Markdown code fences."""
    records: list[FieldRecord] = []
    in_fence = False
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if raw_line.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        stripped = raw_line.strip()
        match = KEY_VALUE_PATTERN.match(stripped)
        if match:
            records.append(
                FieldRecord(
                    path=relative,
                    surface=kind,
                    emitter="markdown_key_value_example",
                    field=match.group(1),
                    line=line_number,
                    certainty="static",
                )
            )
    return tuple(records)


def write_inventory(path: Path, inventory: Inventory) -> None:
    """Write one inventory JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(inventory.to_json_payload(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_inventory(path: Path) -> Inventory:
    """Load one inventory JSON file."""
    payload = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    raw_records = payload.get("records", [])
    raw_record_items = cast(list[object], raw_records) if isinstance(raw_records, list) else []
    records = tuple(
        sorted(
            record
            for record in (record_from_payload(item) for item in raw_record_items)
            if record
        )
    )
    raw_scanned_files = payload.get("scanned_files", [])
    raw_scanned_items = (
        cast(list[object], raw_scanned_files)
        if isinstance(raw_scanned_files, list)
        else []
    )
    scanned_files = tuple(str(scanned_path) for scanned_path in raw_scanned_items)
    schema_version = payload.get("schema_version", 1)
    return Inventory(
        schema_version=int(schema_version) if isinstance(schema_version, int | str) else 1,
        scanned_files=tuple(sorted(scanned_files)),
        records=tuple(sorted(records)),
    )


def record_from_payload(value: object) -> FieldRecord | None:
    """Return one field record from loaded JSON."""
    if not isinstance(value, dict):
        return None
    record = cast(dict[str, object], value)
    line = record.get("line", 0)
    return FieldRecord(
        path=str(record.get("path", "")),
        surface=parse_surface_kind(record.get("surface")),
        emitter=str(record.get("emitter", "")),
        field=str(record.get("field", "")),
        line=int(line) if isinstance(line, int | str) else 0,
        certainty=parse_certainty(record.get("certainty")),
    )


def parse_surface_kind(value: object) -> SurfaceKind:
    """Return a safe surface kind for loaded JSON."""
    if value in {"hook", "skill", "tool"}:
        return cast(SurfaceKind, value)
    return "tool"


def parse_certainty(value: object) -> Certainty:
    """Return a safe certainty value for loaded JSON."""
    if value in {"static", "dynamic"}:
        return cast(Certainty, value)
    return "dynamic"


def diff_inventory(current: Inventory, baseline: Inventory) -> BaselineDiff:
    """Return records added and removed relative to a baseline."""
    current_records = set(current.records)
    baseline_records = set(baseline.records)
    return BaselineDiff(
        added=tuple(sorted(current_records - baseline_records)),
        removed=tuple(sorted(baseline_records - current_records)),
    )


def render_record(prefix: str, record: FieldRecord) -> str:
    """Render one stable machine-readable diff line."""
    return record.machine_line(prefix)


def render_check_failure(diff: BaselineDiff, baseline_path: Path) -> str:
    """Render a concise failure report."""
    lines = [
        "LOG_SURFACE_INVENTORY=fail",
        f"LOG_SURFACE_BASELINE={baseline_path}",
        f"LOG_SURFACE_ADDED={len(diff.added)}",
        f"LOG_SURFACE_REMOVED={len(diff.removed)}",
    ]
    for record in diff.added[:20]:
        lines.append(render_record("LOG_SURFACE_FIELD_ADDED", record))
    for record in diff.removed[:20]:
        lines.append(render_record("LOG_SURFACE_FIELD_REMOVED", record))
    return "\n".join(lines)


def render_text(inventory: Inventory) -> str:
    """Render text summary output."""
    dynamic_count = sum(1 for record in inventory.records if record.certainty == "dynamic")
    lines = [
        "LOG_SURFACE_INVENTORY=pass",
        f"LOG_SURFACE_FILES={len(inventory.scanned_files)}",
        f"LOG_SURFACE_FIELDS={len(inventory.records)}",
        f"LOG_SURFACE_DYNAMIC_FIELDS={dynamic_count}",
    ]
    for record in inventory.records:
        lines.append(render_record("LOG_SURFACE_FIELD", record))
    return "\n".join(lines)


def main() -> int:
    """Run the inventory CLI."""
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    inventory = build_inventory(root, list(args.paths))

    if args.output:
        write_inventory((root / args.output).resolve(), inventory)
        if not args.quiet:
            print(f"LOG_SURFACE_INVENTORY_OUTPUT={args.output}")

    if args.check:
        baseline_path = (root / args.baseline).resolve()
        if not baseline_path.is_file():
            print("LOG_SURFACE_INVENTORY=fail")
            print(f"LOG_SURFACE_BASELINE_MISSING={baseline_path}")
            return 1
        diff = diff_inventory(inventory, load_inventory(baseline_path))
        if diff.has_drift:
            print(render_check_failure(diff, baseline_path))
            return 1
        if not args.quiet:
            print("LOG_SURFACE_INVENTORY=pass")
        return 0

    if args.format == "json":
        print(json.dumps(inventory.to_json_payload(), indent=2, sort_keys=True))
    elif not args.quiet:
        print(render_text(inventory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
