#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Resolves catalog-owned typed command items into argv plans and checks generated runtime projections.
# upstream design ../../../agents/skills/catalog.yaml structured command item contract
# upstream design ../../../tools/catalog.yaml existing tool and dispatch catalog
# upstream implementation ../../runtime/source/agent_canon_source_root.py source-root resolution
# downstream implementation ../../../.codex/personal/skills/*/SKILL.md generated command projection
# downstream implementation ../../../tests/agent_tools/test_skill_tool_commands.py typed command tests
# @dependency-end
"""Resolve structured Skill command items and execute native argv plans."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - clean host fallback
    from tools.runtime.container import stdlib_yaml as yaml

from tools.runtime.source.agent_canon_source_root import (
    RootResolution,
    SourceRootFailure,
    resolve_agent_canon_source_root,
)
from tools.agent.orchestration.route import load_skill_related_map

DEFAULT_ROOT = Path.cwd()
RUNTIME_SKILL_ROOT = Path(".codex/personal/skills")
HUMAN_SKILL_ROOT = Path("agents/skills")
CATALOG_PATH = Path("agents/skills/catalog.yaml")
TOOLS_CATALOG_PATH = Path("tools/catalog.yaml")
SECTION_HEADING = "## Tool Commands"
SECTION_START = "<!-- skill-tool-commands:start -->"
SECTION_END = "<!-- skill-tool-commands:end -->"
COMMAND_TEMPLATE = "python3 tools/agent/skills/skill_tool_commands.py show --skill {skill} --format text"
PHASES = ("required", "conditional", "maintenance")


class StructuredCommandError(ValueError):
    """Typed pre-spawn command failure."""

    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class CommandPlan:
    """Resolved command with argv and execution policy."""

    logical_command: str
    source_root: str
    execution_cwd: str
    execution_env: tuple[tuple[str, str], ...]
    execution_argv: tuple[str, ...]
    skill_id: str = ""
    command_id: str = ""
    tool_id: str = ""
    operation_id: str = "default"
    network: str = "forbidden"
    mutation: str = "read-only"
    plan_sha256: str = ""


@dataclass(frozen=True)
class ExecutionReadback:
    """Native process output and failure classification."""

    plan_sha256: str
    skill_id: str
    command_id: str
    tool_id: str
    operation_id: str
    argv: tuple[str, ...]
    cwd: str
    selected_environment_keys: tuple[str, ...]
    exit_code: int | None
    stdout_log: str
    stderr_log: str
    status: str


@dataclass(frozen=True)
class PublicCommandProjection:
    """Documentation-only projection of a resolved plan."""

    logical_command: str
    layout: str
    public_cwd: str
    public_env: tuple[tuple[str, str], ...]
    public_argv: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    """One generated projection finding."""

    check: str
    path: str
    detail: str

    def render(self) -> str:
        """Render one stable finding."""
        return f"SKILL_TOOL_COMMANDS_FINDING={self.check}:{self.path}:{self.detail}"


@dataclass(frozen=True)
class SkillCommandPacket:
    """Packet preserving the historical text/JSON and resolved-row shape."""

    skill: str
    runtime_skill: str
    canonical_doc: str
    related_skills: tuple[str, ...]
    required_commands: tuple[str, ...]
    discovered_commands: tuple[str, ...]
    conditional_commands: tuple[str, ...]
    maintenance_commands: tuple[str, ...]
    resolved_required_commands: tuple[tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...]
    resolved_discovered_commands: tuple[tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...]
    resolved_conditional_commands: tuple[tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...]
    resolved_maintenance_commands: tuple[tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...]
    validation_commands: tuple[str, ...]
    command_tool_ids: tuple[tuple[str, ...], ...] = ()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise StructuredCommandError("invalid-input", f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _catalog(root: Path, relative: Path) -> Mapping[str, object]:
    try:
        value = yaml.safe_load((root / relative).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise StructuredCommandError("invalid-input", f"catalog unreadable: {relative}") from exc
    return _mapping(value, relative.as_posix())


def _strings(value: object, field: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (required and not value):
        raise StructuredCommandError("invalid-input", f"{field} must be a string list")
    if any(not isinstance(item, str) or not item for item in value):
        raise StructuredCommandError("invalid-input", f"{field} contains a non-string")
    return tuple(value)


def _entries(root: Path) -> dict[str, Mapping[str, object]]:
    data = _catalog(root, TOOLS_CATALOG_PATH)
    raw = data.get("entries")
    if not isinstance(raw, list):
        raise StructuredCommandError("invalid-input", "tools.catalog.entries must be a list")
    result: dict[str, Mapping[str, object]] = {}
    for index, value in enumerate(raw):
        entry = _mapping(value, f"tools.catalog.entries[{index}]")
        tool_id = entry.get("id")
        if not isinstance(tool_id, str) or not tool_id:
            raise StructuredCommandError("invalid-input", f"tools.catalog.entries[{index}].id is invalid")
        result[tool_id] = entry
    return result


def _skill_items(root: Path, skill: str) -> dict[str, tuple[Mapping[str, object], ...]]:
    data = _catalog(root, CATALOG_PATH)
    families = data.get("skill_families")
    if not isinstance(families, list):
        raise StructuredCommandError("invalid-input", "skill_families must be a list")
    for raw in families:
        entry = _mapping(raw, "skill_families[]")
        if entry.get("id") != skill:
            continue
        commands = _mapping(entry.get("tool_commands"), f"{skill}.tool_commands")
        result: dict[str, tuple[Mapping[str, object], ...]] = {}
        for phase in PHASES:
            values = commands.get(phase, [])
            if not isinstance(values, list):
                raise StructuredCommandError("invalid-input", f"{skill}.{phase} must be a list")
            items: list[Mapping[str, object]] = []
            for index, item in enumerate(values):
                record = _mapping(item, f"{skill}.{phase}[{index}]")
                has_catalog = isinstance(record.get("tool_id"), str)
                has_native = isinstance(record.get("executable"), str)
                if has_catalog == has_native:
                    raise StructuredCommandError("invalid-input", f"{skill}.{phase}[{index}] must be catalog or native")
                if has_catalog:
                    operation_id = record.get("operation_id", "default")
                    if not isinstance(operation_id, str) or not operation_id:
                        raise StructuredCommandError("invalid-input", f"{skill}.{phase}[{index}].operation_id is invalid")
                    suffix = record.get("argv_suffix", [])
                    _strings(suffix, f"{skill}.{phase}[{index}].argv_suffix")
                    bindings = record.get("bindings", {})
                    _mapping(bindings, f"{skill}.{phase}[{index}].bindings")
                else:
                    _strings(record.get("argv"), f"{skill}.{phase}[{index}].argv", required=True)
                items.append(record)
            result[phase] = tuple(items)
        return result
    raise StructuredCommandError("invalid-input", f"unknown skill: {skill}")


def _relative_path(root: Path, value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise StructuredCommandError("invalid-input", f"{field} must be a path")
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise StructuredCommandError("invalid-input", f"{field} escapes source root") from exc


def _typed(value: object, spec: Mapping[str, object], root: Path, field: str) -> tuple[object, ...]:
    kind = spec.get("type")
    repeat = spec.get("repeat", str(kind).endswith("-list"))
    if not isinstance(repeat, bool):
        raise StructuredCommandError("invalid-input", f"{field}.repeat is invalid")
    if str(kind).endswith("-list") and not isinstance(value, (list, tuple)):
        raise StructuredCommandError("invalid-input", f"{field} must be a list")
    values = tuple(value) if isinstance(value, (list, tuple)) else (value,)
    if isinstance(value, (list, tuple)) and not repeat:
        raise StructuredCommandError("invalid-input", f"{field} must be scalar")
    if not repeat and len(values) > 1:
        raise StructuredCommandError("invalid-input", f"{field} has too many values")
    output: list[object] = []
    for item in values:
        if kind in {"path", "path-list"}:
            output.append(_relative_path(root, item, field))
        elif kind in {"string", "literal"} and isinstance(item, str) and item:
            output.append(item)
        elif kind == "enum" and isinstance(item, str) and item in spec.get("choices", []):
            output.append(item)
        elif kind in {"integer", "issue-number"} and isinstance(item, int) and not isinstance(item, bool) and (kind != "issue-number" or item > 0):
            output.append(item)
        elif kind == "boolean" and isinstance(item, bool):
            output.append(item)
        elif kind == "oid" and isinstance(item, str) and len(item) == 40 and all(char in "0123456789abcdefABCDEF" for char in item):
            output.append(item)
        else:
            raise StructuredCommandError("invalid-input", f"{field} has wrong type")
    if spec.get("required", False) and not output:
        raise StructuredCommandError("invalid-input", f"{field} is required")
    return tuple(output)


def _dispatch(entry: Mapping[str, object], operation_id: str) -> tuple[tuple[str, ...], Mapping[str, object]]:
    dispatch = entry.get("dispatch")
    if dispatch is None:
        if operation_id != "default":
            raise StructuredCommandError("invalid-input", f"operation unavailable: {entry.get('id')}:{operation_id}")
        return (), {}
    mapping = _mapping(dispatch, f"{entry.get('id')}.dispatch")
    argv = _strings(mapping.get("argv"), f"{entry.get('id')}.dispatch.argv", required=True)
    return argv, mapping


def _executable(root: Path, argv: Sequence[str], native: str | None = None) -> str:
    value = native or (argv[0] if argv else "")
    if value.startswith(("/", "./", "../", "tools/", "scripts/")):
        path = Path(value) if value.startswith("/") else root / value
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise StructuredCommandError("tool-unavailable", f"executable unavailable: {value}") from exc
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise StructuredCommandError("tool-unavailable", f"executable unavailable: {value}")
        return str(resolved)
    located = shutil.which(value)
    if located is None:
        raise StructuredCommandError("tool-unavailable", f"executable unavailable: {value}")
    return located


def _pathify(root: Path, argv: list[str]) -> list[str]:
    if argv and argv[0] in {"python", "python3", "bash"} and len(argv) > 1 and argv[1].startswith(("./", "tools/", "scripts/")):
        argv[1] = str((root / argv[1]).resolve())
    elif argv and argv[0].startswith(("./", "tools/", "scripts/")):
        argv[0] = str((root / argv[0]).resolve())
    return argv


def _binding_values(item: Mapping[str, object], dispatch: Mapping[str, object], inputs: Mapping[str, object], root: Path, *, allow_unbound: bool = False) -> list[str]:
    specs = dict(_mapping(dispatch.get("arguments", {}), "dispatch.arguments"))
    bindings = _mapping(item.get("bindings", {}), "command.bindings")
    for name, value in bindings.items():
        if name not in specs:
            binding = _mapping(value, f"command.bindings.{name}")
            if "type" in binding:
                specs[name] = binding
    unknown = set(bindings) - set(specs)
    if unknown:
        raise StructuredCommandError("invalid-input", f"unknown binding: {sorted(unknown)[0]}")
    result: list[str] = []
    for name, raw_spec in specs.items():
        spec = _mapping(raw_spec, f"dispatch.arguments.{name}")
        raw_binding = bindings.get(name)
        if raw_binding is None:
            if spec.get("required", False):
                if allow_unbound:
                    continue
                raise StructuredCommandError("invalid-input", f"missing required binding: {name}")
            continue
        binding = _mapping(raw_binding, f"command.bindings.{name}")
        source = binding.get("from")
        if not isinstance(source, str) or source not in inputs:
            if allow_unbound:
                continue
            raise StructuredCommandError("invalid-input", f"missing input: {source or name}")
        values = _typed(inputs[source], spec, root, name)
        flag = spec.get("flag")
        for value in values:
            if spec.get("type") == "boolean":
                if value and isinstance(flag, str):
                    result.append(flag)
            else:
                if isinstance(flag, str):
                    result.append(flag)
                result.append(str(value))
    if inputs and set(inputs) - {cast(str, _mapping(value, "binding").get("from")) for value in bindings.values()}:
        unknown_input = sorted(set(inputs) - {cast(str, _mapping(value, "binding").get("from")) for value in bindings.values()})[0]
        raise StructuredCommandError("invalid-input", f"unknown input: {unknown_input}")
    return result


def _resolve_item(root: Path, skill: str, command_id: str, item: Mapping[str, object], entries: Mapping[str, Mapping[str, object]], inputs: Mapping[str, object], *, check_tool: bool, allow_unbound: bool = False) -> CommandPlan:
    if isinstance(item.get("tool_id"), str):
        tool_id = cast(str, item["tool_id"])
        entry = entries.get(tool_id)
        if entry is None:
            raise StructuredCommandError("invalid-input", f"tool unavailable: {tool_id}")
        operation_id = cast(str, item.get("operation_id", "default"))
        prefix, dispatch = _dispatch(entry, operation_id)
        suffix = list(_strings(item.get("argv_suffix", []), "argv_suffix"))
        argv = [*prefix, *suffix]
        if not argv:
            path = entry.get("path")
            if not isinstance(path, str):
                raise StructuredCommandError("invalid-input", f"tool {tool_id} has no default argv")
            argv = [path]
        argv.extend(_binding_values(item, dispatch, inputs, root, allow_unbound=allow_unbound))
        executable = _executable(root, argv) if check_tool else (argv[0] if argv else "")
    else:
        executable = cast(str, item["executable"])
        argv = [executable, *_strings(item.get("argv"), "argv", required=True)]
        if check_tool:
            executable = _executable(root, argv, executable)
    argv = _pathify(root, argv)
    if argv and argv[0] == executable:
        argv[0] = executable
    cwd = str(root.resolve())
    environment: tuple[tuple[str, str], ...] = ()
    fields = {"skill": skill, "command": command_id, "argv": argv, "cwd": cwd, "env": [], "tool": item.get("tool_id", "native")}
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return CommandPlan(json.dumps(argv, ensure_ascii=False), str(root.resolve()), cwd, environment, tuple(argv), skill, command_id, cast(str, item.get("tool_id", "")), cast(str, item.get("operation_id", "default")), "forbidden", "read-only", digest)


def resolve_command(root: Path, skill: str, command_id: str, inputs: Mapping[str, object] | None = None) -> CommandPlan:
    """Resolve one phase-index command using only typed catalog records."""
    items = _skill_items(root, skill)
    try:
        phase, raw_index = command_id.split(":", 1)
        index = int(raw_index)
    except (ValueError, TypeError) as exc:
        raise StructuredCommandError("invalid-input", f"command id must be phase:index: {command_id}") from exc
    if phase not in PHASES or index < 0 or index >= len(items[phase]):
        raise StructuredCommandError("invalid-input", f"unknown command: {skill}:{command_id}")
    return _resolve_item(root, skill, command_id, items[phase][index], _entries(root), dict(inputs or {}), check_tool=True)


def execute_plan(plan: CommandPlan, *, runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run) -> ExecutionReadback:
    """Execute one plan with shell disabled and native output readback."""
    selected = tuple(key for key, _ in plan.execution_env)
    try:
        result = runner(list(plan.execution_argv), cwd=plan.execution_cwd, env=dict(plan.execution_env), shell=False, check=False, capture_output=True)
    except FileNotFoundError as exc:
        return ExecutionReadback(plan.plan_sha256, plan.skill_id, plan.command_id, plan.tool_id, plan.operation_id, plan.execution_argv, plan.execution_cwd, selected, None, "", str(exc), "tool-unavailable")
    except (OSError, subprocess.SubprocessError) as exc:
        return ExecutionReadback(plan.plan_sha256, plan.skill_id, plan.command_id, plan.tool_id, plan.operation_id, plan.execution_argv, plan.execution_cwd, selected, None, "", str(exc), "spawn-failed")
    try:
        stdout = result.stdout.decode("utf-8")
        stderr = result.stderr.decode("utf-8")
    except (AttributeError, UnicodeDecodeError) as exc:
        return ExecutionReadback(plan.plan_sha256, plan.skill_id, plan.command_id, plan.tool_id, plan.operation_id, plan.execution_argv, plan.execution_cwd, selected, result.returncode, "", str(exc), "readback-failed")
    status = "completed" if result.returncode == 0 else "command-failed"
    return ExecutionReadback(plan.plan_sha256, plan.skill_id, plan.command_id, plan.tool_id, plan.operation_id, plan.execution_argv, plan.execution_cwd, selected, result.returncode, stdout, stderr, status)


def execute_command(root: Path, skill: str, command_id: str, inputs: Mapping[str, object] | None = None) -> ExecutionReadback:
    """Resolve then execute one typed command."""
    try:
        return execute_plan(resolve_command(root, skill, command_id, inputs))
    except StructuredCommandError as exc:
        return ExecutionReadback("", skill, command_id, "", "", (), str(root.resolve()), (), None, "", exc.detail, exc.status)


def native_make_target_introspection(root: Path, target: str) -> ExecutionReadback:
    """Use GNU Make dry-run introspection; never parse Makefile source."""
    if not target or target.startswith("-") or "\x00" in target:
        return ExecutionReadback("", "", target, "gnu-make", "default", (), str(root.resolve()), (), None, "", "invalid target", "invalid-input")
    make = shutil.which("make")
    if make is None:
        return ExecutionReadback("", "", target, "gnu-make", "default", (), str(root.resolve()), (), None, "", "make unavailable", "tool-unavailable")
    try:
        result = subprocess.run([make, "--no-print-directory", "-n", "--", target], cwd=root.resolve(), env={}, shell=False, check=False, capture_output=True)
    except OSError as exc:
        return ExecutionReadback("", "", target, "gnu-make", "default", (), str(root.resolve()), (), None, "", str(exc), "spawn-failed")
    try:
        stdout, stderr = result.stdout.decode("utf-8"), result.stderr.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ExecutionReadback("", "", target, "gnu-make", "default", (), str(root.resolve()), (), result.returncode, "", str(exc), "readback-failed")
    argv = (make, "--no-print-directory", "-n", "--", target)
    return ExecutionReadback("", "", target, "gnu-make", "default", argv, str(root.resolve()), (), result.returncode, stdout, stderr, "completed" if result.returncode == 0 else "command-failed")


def make_target_is_explicit(root: Path, target: str) -> bool:
    """Compatibility name backed by native Make introspection."""
    return native_make_target_introspection(root, target).status == "completed"


def validate_command_plan_executables(
    resolution: RootResolution, packet: SkillCommandPacket
) -> None:
    """Validate source-local executable argv positions for an existing packet."""
    del resolution
    rows = (
        *packet.resolved_required_commands,
        *packet.resolved_conditional_commands,
        *packet.resolved_maintenance_commands,
    )
    for _, _, _, _, argv in rows:
        if not argv:
            raise SourceRootFailure("agent_canon_command_preflight_invalid", "empty command")
        executable = Path(argv[0])
        if executable.is_absolute() and (not executable.is_file() or not os.access(executable, os.X_OK)):
            raise SourceRootFailure(
                "agent_canon_command_preflight_missing",
                f"command executable is missing: {executable}",
            )


def project_public_command(plan: CommandPlan, resolution: RootResolution) -> PublicCommandProjection:
    """Project an already resolved plan without parsing command text."""
    if not isinstance(plan, CommandPlan):
        raise SourceRootFailure("agent_canon_public_command_invalid", "CommandPlan required")
    return PublicCommandProjection(plan.logical_command, resolution.layout, ".", plan.execution_env, plan.execution_argv)


def project_public_command_for_layout(plan: CommandPlan, *, layout: str) -> PublicCommandProjection:
    """Project an already resolved plan for a public layout."""
    if layout not in {"standalone", "external"}:
        raise SourceRootFailure("agent_canon_public_command_invalid", f"unknown layout: {layout}")
    return project_public_command(plan, RootResolution(Path("."), Path("."), layout, Path("."), Path("tools")))


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def packet_for_skill(resolution: RootResolution, skill: str) -> SkillCommandPacket:
    """Build the historical packet shape from structured records."""
    root = resolution.source_root
    items = _skill_items(root, skill)
    entries = _entries(root)
    examples: dict[str, tuple[str, ...]] = {}
    resolved: dict[str, tuple[tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]], ...]] = {}
    for phase in PHASES:
        display: list[str] = []
        rows: list[tuple[str, str, str, tuple[tuple[str, str], ...], tuple[str, ...]]] = []
        for index, item in enumerate(items[phase]):
            command_id = f"{phase}:{index}"
            try:
                plan = _resolve_item(root, skill, command_id, item, entries, {}, check_tool=False, allow_unbound=True)
            except StructuredCommandError as exc:
                if exc.status != "invalid-input":
                    raise
                plan = _resolve_item(root, skill, command_id, item, entries, {}, check_tool=False, allow_unbound=True)
            display.append(plan.logical_command)
            rows.append((plan.logical_command, plan.source_root, plan.execution_cwd, plan.execution_env, plan.execution_argv))
        examples[phase] = tuple(display)
        resolved[phase] = tuple(rows)
    command_tool_ids = tuple(
        tuple(cast(str, item.get("tool_id", "")) for item in items[phase])
        for phase in PHASES
    )
    return SkillCommandPacket(skill, _relative(root, root / RUNTIME_SKILL_ROOT / skill / "SKILL.md"), _relative(root, root / HUMAN_SKILL_ROOT / f"{skill}.md"), load_skill_related_map(root).get(skill, ()), examples["required"], examples["conditional"], examples["conditional"], examples["maintenance"], resolved["required"], resolved["conditional"], resolved["conditional"], resolved["maintenance"], examples["maintenance"], command_tool_ids)


def runtime_skill_paths(root: Path) -> list[Path]:
    """Return generated runtime skill files in stable order."""
    return sorted((root / RUNTIME_SKILL_ROOT).glob("*/SKILL.md"))


def skill_name_from_path(path: Path) -> str:
    """Return the runtime skill directory name."""
    return path.parent.name


def check(root: Path) -> tuple[Finding, ...]:
    """Check generated sections without interpreting Markdown as commands."""
    findings: list[Finding] = []
    paths = runtime_skill_paths(root)
    if not paths:
        findings.append(Finding("skill_tool_commands", RUNTIME_SKILL_ROOT.as_posix(), "missing-skill-root"))
    try:
        catalog = _catalog(root, CATALOG_PATH)
        families = catalog.get("skill_families", [])
        if not isinstance(families, list):
            raise StructuredCommandError("invalid-input", "skill_families must be a list")
    except StructuredCommandError as exc:
        return (Finding("skill_tool_commands", CATALOG_PATH.as_posix(), exc.detail),)
    for path in paths:
        skill = skill_name_from_path(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = _relative(root, path)
        if SECTION_HEADING not in text:
            findings.append(Finding("skill_tool_commands", relative, "missing-tool-commands-section"))
        elif SECTION_START not in text or SECTION_END not in text:
            findings.append(Finding("skill_tool_commands", relative, "missing-section-markers"))
        if text.count(COMMAND_TEMPLATE.format(skill=skill)) != 1:
            findings.append(Finding("skill_tool_commands", relative, "missing-command-packet-entry"))
    return tuple(findings)


def render_packet_text(packet: SkillCommandPacket) -> str:
    """Render text and argv projections for a packet."""
    lines = [f"SKILL_TOOL_COMMANDS_SKILL={packet.skill}", f"SKILL_TOOL_COMMANDS_RUNTIME_SKILL={packet.runtime_skill}", f"SKILL_TOOL_COMMANDS_CANONICAL_DOC={packet.canonical_doc}", "SKILL_TOOL_COMMANDS_RELATED_SKILLS=" + (",".join(f"${skill}" for skill in packet.related_skills) if packet.related_skills else "-")]
    for phase, commands, rows in (("REQUIRED", packet.required_commands, packet.resolved_required_commands), ("CONDITIONAL", packet.conditional_commands, packet.resolved_conditional_commands), ("MAINTENANCE_ONLY", packet.maintenance_commands, packet.resolved_maintenance_commands)):
        lines.append(f"SKILL_TOOL_COMMANDS_{phase}:")
        lines.extend(f"- {command}" for command in commands)
        lines.append(f"SKILL_TOOL_COMMANDS_{phase}_RESOLUTION:")
        for logical, source, cwd, env, argv in rows:
            lines.extend((f"- logical={logical}", f"- source_root={source}", f"- execution_cwd={cwd}", f"- execution_env={json.dumps(list(env))}", f"- execution_argv={json.dumps(list(argv))}"))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Create the structured command CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    subparsers = parser.add_subparsers(dest="command", required=True)
    show = subparsers.add_parser("show")
    show.add_argument("--skill", required=True)
    show.add_argument("--format", choices=("text", "json"), default="text")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--format", choices=("text", "json"), default="text")
    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--skill", required=True)
    resolve.add_argument("--command", dest="command_id", required=True)
    resolve.add_argument("--inputs", default="{}")
    execute = subparsers.add_parser("execute")
    execute.add_argument("--skill", required=True)
    execute.add_argument("--command", dest="command_id", required=True)
    execute.add_argument("--inputs", default="{}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one packet, validation, resolution, or execution operation."""
    args = build_parser().parse_args(argv)
    try:
        resolution = resolve_agent_canon_source_root(Path(args.root))
        root = resolution.source_root
        if args.command == "show":
            packet = packet_for_skill(resolution, args.skill)
            print(render_packet_text(packet) if args.format == "text" else json.dumps(asdict(packet), indent=2, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "check":
            findings = check(root)
            if args.format == "json":
                print(json.dumps({"status": "pass" if not findings else "fail", "findings": [asdict(item) for item in findings]}, indent=2, ensure_ascii=False, sort_keys=True))
            else:
                for finding in findings:
                    print(finding.render())
                print(f"SKILL_TOOL_COMMANDS_FINDINGS={len(findings)}")
                print(f"SKILL_TOOL_COMMANDS={'pass' if not findings else 'fail'}")
            return 0 if not findings else 1
        try:
            inputs = json.loads(args.inputs)
        except json.JSONDecodeError as exc:
            raise StructuredCommandError("invalid-input", str(exc)) from exc
        if not isinstance(inputs, Mapping):
            raise StructuredCommandError("invalid-input", "inputs must be an object")
        if args.command == "resolve":
            print(json.dumps(asdict(resolve_command(root, args.skill, args.command_id, inputs)), indent=2, ensure_ascii=False, sort_keys=True))
            return 0
        result = execute_command(root, args.skill, args.command_id, inputs)
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False, sort_keys=True))
        return 0 if result.status == "completed" else 1
    except (StructuredCommandError, SourceRootFailure) as exc:
        print(json.dumps({"status": getattr(exc, "status", getattr(exc, "code", "invalid-input")), "detail": getattr(exc, "detail", str(exc))}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
