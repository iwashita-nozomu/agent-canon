#!/usr/bin/env python3
"""Append one observed agent-learning entry to the canonical note."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

DEFAULT_NOTE_PATH = "memory/global/AGENT_PHILOSOPHY.md"
DEFAULT_LOADOUT_PATH = "memory/subagent_loadouts.yaml"
SECTION_HEADERS = {
    "work-principle": "## Working Principles",
    "interaction-observation": "## Interaction Observations",
    "task-retrospective": "## Task Retrospectives",
    "promotion-candidate": "## Promotion Candidates",
    "open-question": "## Open Questions",
    "stable": "## Stable Philosophy",
    "failure-avoidance": "## Promotion Candidates",
}


def default_note_text(title: str, layer_description: str) -> str:
    """Return default note content for one learning layer."""
    return f"""# {title}

この file は、{layer_description} を置く append-first note です。
raw chat を直接置かず、短い observation と evidence に圧縮して残します。

## Stable Philosophy

- まだなし

## Working Principles

- まだなし

## Interaction Observations

- まだなし

## Task Retrospectives

- まだなし

## Promotion Candidates

- まだなし

## Open Questions

- まだなし
"""


@dataclass(frozen=True)
class AgentLearningEntry:
    """Represent one agent-learning observation."""

    kind: str
    statement: str
    source: str
    evidence: str | None
    scope: str
    confidence: str
    observed_on: str


def load_loadout_config(loadout_path: Path) -> dict[str, object]:
    """Load the machine-readable role routing config."""
    data = yaml.safe_load(loadout_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"memory loadout config must parse as a mapping: {loadout_path}")
    return data


def resolve_loadout_relative_path(loadout_path: Path, configured_path: str) -> Path:
    """Resolve a configured path relative to the loadout file when needed."""
    candidate = Path(configured_path)
    if candidate.is_absolute():
        return candidate
    return (loadout_path.parent / candidate).resolve()


def resolve_note_path(
    *,
    note_path_arg: str | None,
    loadout_path: Path,
    role: str | None,
    target_layer: str | None,
    method: str | None,
) -> tuple[Path, str]:
    """Resolve the target note path and effective layer."""
    if role is None:
        if note_path_arg is not None:
            return Path(note_path_arg), target_layer or "global"
        return Path(DEFAULT_NOTE_PATH), target_layer or "global"

    if note_path_arg is not None:
        raise ValueError("--note-path cannot be combined with --role; use fixed routing")

    config = load_loadout_config(loadout_path)
    role_loadouts = config.get("role_loadouts")
    method_files = config.get("method_files")
    candidate_files = config.get("candidate_files")
    if not isinstance(role_loadouts, dict):
        raise RuntimeError("role_loadouts must be a mapping")
    if not isinstance(method_files, dict):
        raise RuntimeError("method_files must be a mapping")
    if not isinstance(candidate_files, dict):
        raise RuntimeError("candidate_files must be a mapping")
    if role not in role_loadouts or not isinstance(role_loadouts[role], dict):
        raise ValueError(f"unknown role in loadout config: {role}")
    entry = role_loadouts[role]
    effective_layer = target_layer or "candidate"

    if effective_layer == "candidate":
        candidate_key = entry.get("candidate_file")
        if not isinstance(candidate_key, str):
            raise ValueError(f"role {role} does not declare a candidate route")
        relative = candidate_files.get(candidate_key)
        if not isinstance(relative, str):
            raise ValueError(f"candidate route missing for key: {candidate_key}")
        return resolve_loadout_relative_path(loadout_path, relative), effective_layer

    if effective_layer == "method":
        if not bool(entry.get("allow_method_write", False)):
            raise ValueError(f"role {role} may not write method memory directly")
        if method is None:
            raise ValueError("--method is required when --target-layer method is used")
        relative = method_files.get(method)
        if not isinstance(relative, str):
            raise ValueError(f"unknown method memory key: {method}")
        return resolve_loadout_relative_path(loadout_path, relative), effective_layer

    if effective_layer == "global":
        if not bool(entry.get("allow_global_write", False)):
            raise ValueError(f"role {role} may not write global memory directly")
        return Path(DEFAULT_NOTE_PATH), effective_layer

    raise ValueError(f"unsupported target layer: {effective_layer}")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Append one agent-learning observation.")
    parser.add_argument(
        "--kind",
        default="interaction-observation",
        choices=tuple(SECTION_HEADERS),
        help="Learning bucket. Default: interaction-observation",
    )
    parser.add_argument("--statement", required=True, help="Short durable observation.")
    parser.add_argument("--source", default="chat", help="Source label. Default: chat")
    parser.add_argument("--evidence", help="Optional short evidence summary.")
    parser.add_argument("--scope", default="repo-wide", help="Scope label. Default: repo-wide")
    parser.add_argument(
        "--confidence",
        default="tentative",
        choices=("tentative", "likely", "stable"),
        help="Confidence label. Default: tentative",
    )
    parser.add_argument("--observed-on", default=str(date.today()), help="Observation date.")
    parser.add_argument("--role", help="Optional role id used for fixed route resolution.")
    parser.add_argument(
        "--target-layer",
        choices=("candidate", "method", "global"),
        help="Optional explicit layer. With --role, default is candidate. Without --role, default is global.",
    )
    parser.add_argument("--method", help="Method memory key when --target-layer method is used.")
    parser.add_argument(
        "--loadout-path",
        default=DEFAULT_LOADOUT_PATH,
        help=f"Role loadout config path. Default: {DEFAULT_LOADOUT_PATH}",
    )
    parser.add_argument(
        "--note-path",
        help=f"Optional explicit note path. Without --role, default: {DEFAULT_NOTE_PATH}",
    )
    return parser


def ensure_note_exists(note_path: Path) -> None:
    """Create the note file when it does not exist."""
    if note_path.exists():
        return
    note_path.parent.mkdir(parents=True, exist_ok=True)
    title = note_path.stem.replace("_", " ").title()
    note_path.write_text(default_note_text(title, note_path.name), encoding="utf-8")


def entry_text(entry: AgentLearningEntry) -> str:
    """Render one note entry."""
    parts = [
        f"- {entry.observed_on} | {entry.kind} | {entry.statement}",
        f"  - source: {entry.source}",
        f"  - scope: {entry.scope}",
        f"  - confidence: {entry.confidence}",
    ]
    if entry.evidence:
        parts.append(f"  - evidence: {entry.evidence}")
    return "\n".join(parts)


def insert_under_section(text: str, section_header: str, rendered_entry: str) -> str:
    """Insert one rendered entry under the target section."""
    if section_header not in text:
        raise ValueError(f"Missing section header: {section_header}")
    lines = text.splitlines()
    header_index = lines.index(section_header)
    insert_at = header_index + 1

    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    if insert_at < len(lines) and lines[insert_at].strip() == "- まだなし":
        del lines[insert_at]

    while insert_at < len(lines) and not lines[insert_at].startswith("## "):
        insert_at += 1

    payload = rendered_entry.splitlines()
    if insert_at > 0 and lines[insert_at - 1].strip() != "":
        payload.insert(0, "")
    if insert_at < len(lines) and lines[insert_at].startswith("## "):
        payload.append("")
    lines[insert_at:insert_at] = payload
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    """Append one agent-learning entry."""
    args = build_parser().parse_args()
    note_path, effective_layer = resolve_note_path(
        note_path_arg=args.note_path,
        loadout_path=Path(args.loadout_path),
        role=args.role.strip() if args.role else None,
        target_layer=args.target_layer,
        method=args.method.strip() if args.method else None,
    )
    ensure_note_exists(note_path)
    note_text = note_path.read_text(encoding="utf-8")
    rendered = entry_text(
        AgentLearningEntry(
            kind=args.kind.strip(),
            statement=args.statement.strip(),
            source=args.source.strip(),
            evidence=args.evidence.strip() if args.evidence else None,
            scope=args.scope.strip(),
            confidence=args.confidence.strip(),
            observed_on=args.observed_on.strip(),
        )
    )
    updated = insert_under_section(note_text, SECTION_HEADERS[args.kind], rendered)
    note_path.write_text(updated, encoding="utf-8")
    print(f"AGENT_LEARNING_NOTE={note_path}")
    print(f"AGENT_LEARNING_LAYER={effective_layer}")
    if args.role:
        print(f"AGENT_LEARNING_ROLE={args.role.strip()}")
    print(f"AGENT_LEARNING_KIND={args.kind}")
    print(f"AGENT_LEARNING_TEXT={args.statement.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
