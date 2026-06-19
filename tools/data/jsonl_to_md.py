#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Converts JSONL result records into a compact Markdown report.
# upstream design ../README.md shared tool index
# downstream design ../../documents/result-log-retention-and-visualization.md result policy
# @dependency-end
"""Convert JSONL records into a compact Markdown report."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeAlias, cast

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

PREFERRED_KEYS = (
    "case",
    "source_file",
    "test",
    "func",
    "event",
    "iter",
    "step",
    "num_iter",
)


def _format_value(value: JsonValue) -> str:
    """Render a JSON value safely inside a Markdown table cell."""
    if isinstance(value, Mapping | Sequence) and not isinstance(value, str):
        rendered = json.dumps(value, ensure_ascii=False)
    else:
        rendered = str(value)
    return rendered.replace("|", "\\|").replace("\n", "<br>")


def _ordered_items(record: Mapping[str, JsonValue]) -> list[tuple[str, JsonValue]]:
    """Return preferred keys first, then remaining keys in lexical order."""
    items: list[tuple[str, JsonValue]] = []
    used: set[str] = set()
    for key in PREFERRED_KEYS:
        if key in record:
            items.append((key, record[key]))
            used.add(key)
    items.extend((key, record[key]) for key in sorted(record) if key not in used)
    return items


def iter_jsonl_records(path: Path) -> list[JsonObject]:
    """Read JSON object records from a JSONL file, skipping malformed lines."""
    records: list[JsonObject] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = cast(object, json.loads(stripped))
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(cast(JsonObject, value))
    return records


def render_markdown(input_path: Path, records: Sequence[Mapping[str, JsonValue]]) -> str:
    """Render records as a Markdown document."""
    lines = [
        "# JSONL Report",
        "",
        f"- input: `{input_path}`",
        f"- records: {len(records)}",
        "",
    ]
    for index, record in enumerate(records, 1):
        title = str(record.get("case", f"record-{index}"))
        lines.extend(
            [
                f"## {title}",
                "",
                "| key | value |",
                "| --- | --- |",
            ]
        )
        for key, value in _ordered_items(record):
            lines.append(f"| {key} | {_format_value(value)} |")
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input JSONL file.")
    parser.add_argument("output", type=Path, help="Output Markdown file.")
    return parser


def main() -> int:
    """Run the JSONL-to-Markdown converter."""
    args = build_parser().parse_args()
    if not args.input.is_file():
        print(f"Input not found: {args.input}")
        return 2
    records = iter_jsonl_records(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(args.input, records), encoding="utf-8")
    print(f"written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
