#!/usr/bin/env python3
# @dependency-start
# responsibility Logs user preference records for agent workflows.
# upstream design ../README.md shared automation index
# @dependency-end

"""Append one observed user preference to the canonical note."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_NOTE_PATH = "memory/USER_PREFERENCES.md"
SECTION_HEADERS = {
    "stable": "## Stable Preferences",
    "provisional": "## Provisional Preferences",
    "promotion-candidate": "## Promotion Candidates",
    "recent": "## Recent Observations",
}
DEFAULT_NOTE_TEXT = """# User Preferences

この file は、会話から抽出した user の coding philosophy、review expectation、
document preference を逐次追記する append-first note です。
`AGENTS.md` へ入れる前の観測をここへ集め、十分に安定した項目だけを periodic sweep で昇格させます。

## Use

- user が明示した repo-wide preference を観測したら追記します。
- task 固有の一時指示ではなく、今後も効く傾向だけを残します。
- `AGENTS.md` に直接書かず、まずこの note に入れます。
- periodic sweep では repeated で durable な項目だけを `AGENTS.md` へ昇格します。
- shared canon の `memory/` を正本にし、template 側では runtime view を使います。

## Stable Preferences

- まだなし

## Provisional Preferences

- まだなし

## Promotion Candidates

- まだなし

## Recent Observations

- まだなし
"""


@dataclass(frozen=True)
class PreferenceEntry:
    """Represent one preference observation."""

    preference: str
    kind: str
    source: str
    rationale: str | None
    observed_on: str


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Append one user preference observation.")
    parser.add_argument(
        "--preference",
        required=True,
        help="Observed durable preference statement.",
    )
    parser.add_argument(
        "--kind",
        default="provisional",
        choices=("stable", "provisional", "promotion-candidate", "recent"),
        help="Preference bucket. Default: provisional",
    )
    parser.add_argument("--source", default="chat", help="Source label. Default: chat")
    parser.add_argument("--rationale", help="Optional reason or evidence summary.")
    parser.add_argument(
        "--observed-on",
        default=str(date.today()),
        help="Observation date. Default: today",
    )
    parser.add_argument(
        "--note-path",
        default=DEFAULT_NOTE_PATH,
        help=f"Preference note path. Default: {DEFAULT_NOTE_PATH}",
    )
    return parser


def ensure_note_exists(note_path: Path) -> None:
    """Create the note file when it does not exist."""
    if note_path.exists():
        return
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(DEFAULT_NOTE_TEXT, encoding="utf-8")


def entry_text(entry: PreferenceEntry) -> str:
    """Render one note entry."""
    parts = [
        f"- {entry.observed_on} | {entry.preference}",
        f"  - source: {entry.source}",
    ]
    if entry.rationale:
        parts.append(f"  - rationale: {entry.rationale}")
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
    """Append one preference entry."""
    args = build_parser().parse_args()
    note_path = Path(args.note_path)
    ensure_note_exists(note_path)
    note_text = note_path.read_text(encoding="utf-8")
    rendered = entry_text(
        PreferenceEntry(
            preference=args.preference.strip(),
            kind=args.kind,
            source=args.source.strip(),
            rationale=args.rationale.strip() if args.rationale else None,
            observed_on=args.observed_on.strip(),
        )
    )
    updated = insert_under_section(note_text, SECTION_HEADERS[args.kind], rendered)
    note_path.write_text(updated, encoding="utf-8")
    print(f"PREFERENCE_NOTE={note_path}")
    print(f"PREFERENCE_KIND={args.kind}")
    print(f"PREFERENCE_TEXT={args.preference.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
