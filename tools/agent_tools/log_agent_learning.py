#!/usr/bin/env python3
"""Append one observed agent-learning entry to the canonical note."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_NOTE_PATH = "memory/AGENT_PHILOSOPHY.md"
SECTION_HEADERS = {
    "work-principle": "## Working Principles",
    "interaction-observation": "## Interaction Observations",
    "task-retrospective": "## Task Retrospectives",
    "promotion-candidate": "## Promotion Candidates",
    "open-question": "## Open Questions",
    "stable": "## Stable Philosophy",
    "failure-avoidance": "## Promotion Candidates",
}
DEFAULT_NOTE_TEXT = """# Agent Philosophy

この file は、agent の作業哲学、対話から得た学習、repo-wide な判断原則を
逐次追記する append-first note です。
`AGENTS.md` や workflow 正本へ入れる前の観測をここへ集め、
十分に安定した項目だけを periodic sweep で昇格させます。

## Use

- user preference は `memory/USER_PREFERENCES.md` に残します。
- agent 自身の作業哲学、判断癖、対話上の再発防止、作業後 retrospective はこの note に残します。
- 会話ログを raw に貼らず、1 observation 1 entry の短い抽象化として残します。
- source、evidence、scope、confidence を明示し、推測と確定事項を混ぜません。
- stable な運用 rule へ昇格するまでは、`AGENTS.md` や runtime entrypoint へ直接書きません。
- shared canon の `memory/` を正本にし、template 側では runtime view を使います。

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
    parser.add_argument(
        "--note-path",
        default=DEFAULT_NOTE_PATH,
        help=f"Agent philosophy note path. Default: {DEFAULT_NOTE_PATH}",
    )
    return parser


def ensure_note_exists(note_path: Path) -> None:
    """Create the note file when it does not exist."""
    if note_path.exists():
        return
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(DEFAULT_NOTE_TEXT, encoding="utf-8")


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
    note_path = Path(args.note_path)
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
    print(f"AGENT_PHILOSOPHY_NOTE={note_path}")
    print(f"AGENT_LEARNING_KIND={args.kind}")
    print(f"AGENT_LEARNING_TEXT={args.statement.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
