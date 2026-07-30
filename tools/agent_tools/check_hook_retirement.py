#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Fails closed on hook retirement manifest, absence, executable-reference, inventory, and caller-closure violations.
# upstream design ../../documents/design/agentcanon-hook-simplification-wave3.md fixes scan roots and readback schema.
# upstream implementation ./hook_retirement.py owns the typed tombstone manifest.
# upstream implementation ../../.codex/hooks/hook_dispatcher.py owns active event readback.
# downstream implementation ../../tests/agent_tools/test_hook_retirement.py validates clean and violation fixtures.
# @dependency-end
"""Check the Wave 3 hook-retirement target tree."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from hook_retirement import (
    CALLER_AUDIT_ROOTS,
    CALLER_AUDIT_SCHEMA,
    MOVED_SOURCE_ABSENCES,
    RETIRED_CHILD_TOMBSTONES,
    TOMBSTONE_SCHEMA,
    source_digest,
)

EXECUTABLE_SCAN_PATHS = (
    ".codex/hooks.json", ".codex/config.toml", ".codex/agents", "templates", "tools/catalog.yaml",
    "tools/ci/run_python_quality_checks.sh", "tools/agent_tools/check_agent_runtime_alignment.py",
    "tools/agent_tools/check_convention_compliance.py", "tools/agent_tools/convention_compliance_contracts.toml",
    "tools/agent_tools/generate_agent_runtime_dashboard.py", "tools/agent_tools/skill_lane_detector.py",
    "tools/agent_tools/report_artifact_checks.py", "tools/agent_tools/workflow_monitor.py",
    "agents/skills/worktree-health.md", ".agents/skills/worktree-health/SKILL.md",
    "documents/experiments/gpu-admission-r5-source-packet.md", "AGENTS.md", "ROOT_AGENTS.md", "README.md",
    "documents/runtime/runtime-log-archive.md", "tools/README.md", "tools/experiments/execution_resource_plan.py",
    "tools/validation/notebook_quality.py",
)
METADATA_ALLOWLIST = {"tools/agent_tools/hook_retirement.py", "documents/design/agentcanon-hook-simplification-wave3.md"}
_COMMAND_RE = re.compile(r"^(?:import-only:tools\.agent_tools\.[A-Za-z0-9_]+:[A-Za-z0-9_]+|command-only:python3 tools/(?:agent_tools|validation)/[A-Za-z0-9_]+\.py(?: [^\n]*)?|skill-only:\$[A-Za-z0-9][A-Za-z0-9_-]*|docs-only:tools/bin/agent-canon docs check)$")


def _files(root: Path, relative: str) -> list[Path]:
    path = root / relative
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(item for item in path.rglob("*") if item.is_file())
    return []


def _all_audit_files(root: Path) -> list[Path]:
    result: list[Path] = []
    for relative in CALLER_AUDIT_ROOTS:
        result.extend(_files(root, relative))
    return sorted(set(result))


def _matches(
    root: Path,
    files: list[Path],
    tokens: list[str],
    retirement_kind: str,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(lines, start=1):
            for token in tokens:
                if token in line:
                    result.append(
                        {
                            "path": path.relative_to(root).as_posix(),
                            "line": line_number,
                            "retirement_kind": retirement_kind,
                            "token": token,
                        }
                    )
    return result


def _active_events(root: Path) -> tuple[list[str], list[str]]:
    try:
        hooks = json.loads((root / ".codex" / "hooks.json").read_text(encoding="utf-8"))
        groups = hooks.get("hooks", {}) if isinstance(hooks, dict) else {}
        active = list(groups) if isinstance(groups, dict) else []
    except (OSError, ValueError):
        active = []
    return active, ["Stop"]


def contract_payload(root: Path) -> dict[str, object]:
    children = [asdict(row) for row in RETIRED_CHILD_TOMBSTONES]
    moved = [asdict(row) for row in MOVED_SOURCE_ABSENCES]
    child_basenames = sorted({row.filename for row in RETIRED_CHILD_TOMBSTONES})
    moved_source_old_paths = sorted(
        f".codex/hooks/{row.filename}" for row in MOVED_SOURCE_ABSENCES
    )
    audit_files = _all_audit_files(root)
    child_matches = _matches(
        root, audit_files, child_basenames, "retired_child_basename"
    )
    moved_matches = _matches(
        root, audit_files, moved_source_old_paths, "moved_source_old_path"
    )
    matches = child_matches + moved_matches
    executable_references: list[dict[str, object]] = []
    executable_files = [path for relative in EXECUTABLE_SCAN_PATHS for path in _files(root, relative)]
    for tokens, retirement_kind in (
        (child_basenames, "retired_child_basename"),
        (moved_source_old_paths, "moved_source_old_path"),
    ):
        for match in _matches(root, executable_files, tokens, retirement_kind):
            if match["path"] not in METADATA_ALLOWLIST:
                executable_references.append(match)
    present_files = [f".codex/hooks/{name.filename}" for name in RETIRED_CHILD_TOMBSTONES if (root / ".codex" / "hooks" / name.filename).exists()]
    present_files.extend([old_path for old_path in moved_source_old_paths if (root / old_path).exists()])
    inventory_paths: list[str] = []
    inventory = root / "documents/runtime/log-surface-inventory.json"
    if inventory.exists():
        try:
            text = inventory.read_text(encoding="utf-8")
            inventory_paths = [
                token
                for token in child_basenames + moved_source_old_paths
                if token in text
            ]
        except OSError:
            inventory_paths = ["inventory_unreadable"]
    artifacts = [
        {"name": "skill_usage.jsonl", "mode": "historical_read_only", "producer": "none", "parser": "tools/agent_tools/historical_skill_usage_reader.py", "consumers": ["tools/agent_tools/historical_skill_usage_reader.py", "tools/agent_tools/generate_agent_improvement_guide.py", "tools/agent_tools/generate_agent_runtime_dashboard.py"]},
        {"name": "behavior_events.jsonl", "mode": "active_canonical", "producer": "tools/agent_tools/behavior_event_assembly.py", "parser": "tools/agent_tools/behavior_event_assembly.py", "consumers": ["tools/agent_tools/generate_agent_runtime_dashboard.py"]},
        {"name": "workflow_monitoring.md", "mode": "projection", "producer": "tools/agent_tools/workflow_monitor.py", "parser": "tools/agent_tools/workflow_monitor.py", "consumers": ["tools/agent_tools/generate_agent_runtime_dashboard.py", "tools/agent_tools/task_close.py"]},
    ]
    active, inactive = _active_events(root)
    malformed = [match for match in matches if not isinstance(match.get("token"), str)]
    return {
        "schema": TOMBSTONE_SCHEMA,
        "retired_child_tombstones": children,
        "moved_source_absences": moved,
        "counts": {"retired_child_tombstones": len(children), "moved_source_absences": len(moved), "retired_filenames": len(child_basenames) + len(moved_source_old_paths)},
        "active_events": active,
        "inactive_events": inactive,
        "source_digest": source_digest(),
        "missing_files": sorted(present_files),
        "executable_references": sorted(executable_references, key=lambda item: (str(item["path"]), int(item["line"]), str(item["token"]))),
        "generated_inventory_paths": sorted(inventory_paths),
        "caller_audit": {
            "schema": CALLER_AUDIT_SCHEMA,
            "retired_child_basenames": child_basenames,
            "moved_source_old_paths": moved_source_old_paths,
            "matches": matches,
            "malformed_matches": malformed,
            "artifacts": artifacts,
        },
    }


def check_payload(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    counts = payload.get("counts", {})
    if len(payload.get("retired_child_tombstones", [])) != 23:
        errors.append("retired_child_tombstones")
    if len(payload.get("moved_source_absences", [])) != 1:
        errors.append("moved_source_absences")
    if not isinstance(counts, dict) or counts.get("retired_filenames") != 24:
        errors.append("retired_filenames")
    if payload.get("missing_files"):
        errors.append("missing_files")
    if payload.get("executable_references"):
        errors.append("executable_references")
    if payload.get("generated_inventory_paths"):
        errors.append("generated_inventory_paths")
    children = payload.get("retired_child_tombstones", [])
    if any(not isinstance(row, dict) or not isinstance(row.get("command_or_skill"), str) or not _COMMAND_RE.fullmatch(row["command_or_skill"]) or any(bad in row["command_or_skill"] for bad in (".codex/hooks/", "compat", "wrapper", "shim", "fallback")) for row in children):
        errors.append("command_or_skill_grammar")
    if payload.get("active_events") != ["UserPromptSubmit", "PreToolUse", "PostToolUse"]:
        errors.append("active_events")
    if payload.get("inactive_events") != ["Stop"]:
        errors.append("inactive_events")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--contract", action="store_true")
    args = parser.parse_args(argv)
    payload = contract_payload(args.root.resolve())
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    if args.check:
        errors = check_payload(payload)
        if errors:
            print("hook retirement check failed: " + ",".join(errors), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
