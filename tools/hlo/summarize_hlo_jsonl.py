# @dependency-start
# contract tool
# responsibility Summarizes HLO JSONL records into compact JSON metrics.
# upstream design ../README.md shared tool index
# downstream design ../../documents/result-log-retention-and-visualization.md result policy
# @dependency-end
"""Summarize HLO JSONL records."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import TypeAlias, cast

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def _iter_jsonl(path: Path) -> Iterable[JsonObject]:
    """JSONL を 1 行ずつ読み込みます。"""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            obj = cast(object, json.loads(s))
            if isinstance(obj, dict):
                yield cast(JsonObject, obj)


def _count_hlo_ops(hlo_text: str) -> Counter[str]:
    """HLO テキストから雑に命令種別っぽいトークンを数えます。

    Notes
    -----
    - HLO の厳密パーサは導入せず、簡易な統計を取るためのヒューリスティックです。
    - 将来的に stablehlo の構文が変わった場合はここを調整します。
    """
    counter: Counter[str] = Counter()
    for line in hlo_text.splitlines():
        t = line.strip()
        if not t:
            continue
        if t.startswith("//"):
            continue
        if "=" not in t:
            continue
        rhs = t.split("=", 1)[1].strip()
        op = rhs.split("(", 1)[0].strip()
        if not op:
            continue
        counter[op] += 1
    return counter


def _get_record_key(rec: JsonObject, key: str) -> str:
    value = rec.get(key)
    if value is None:
        return ""
    return str(value)


def _count_lines(text: str) -> int:
    return len([line for line in text.splitlines() if line.strip()])


def _counter_pairs(counter: Counter[str], limit: int | None = None) -> list[list[JsonValue]]:
    """Return JSON-compatible pairs instead of tuple values."""
    return [[name, count] for name, count in counter.most_common(limit)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize HLO JSONL.")
    parser.add_argument(
        "jsonl",
        type=str,
        help="Path to JSONL produced by an HLO dumping workflow.",
    )
    parser.add_argument("--top", type=int, default=30, help="Show top-k ops.")
    parser.add_argument(
        "--only-case",
        type=str,
        default="hlo",
        help="Filter by record['case'] (default: hlo). Use empty string to disable.",
    )
    args = parser.parse_args()

    path = Path(args.jsonl)
    total_records = 0
    total_selected = 0
    tags: Counter[str] = Counter()
    dialects: Counter[str] = Counter()
    ops_total: Counter[str] = Counter()
    hlo_lines_total = 0
    hlo_chars_total = 0

    for rec in _iter_jsonl(path):
        total_records += 1
        if args.only_case:
            if _get_record_key(rec, "case") != args.only_case:
                continue

        total_selected += 1
        tag = _get_record_key(rec, "tag")
        if tag:
            tags[tag] += 1

        dialect = _get_record_key(rec, "dialect")
        if dialect:
            dialects[dialect] += 1
        hlo = rec.get("hlo")
        if isinstance(hlo, str):
            ops_total.update(_count_hlo_ops(hlo))
            hlo_lines_total += _count_lines(hlo)
            hlo_chars_total += len(hlo)

    out = cast(JsonObject, {
        "jsonl": str(path),
        "total_records": total_records,
        "total_selected": total_selected,
        "filter": {"only_case": args.only_case},
        "tags": _counter_pairs(tags),
        "dialects": _counter_pairs(dialects),
        "hlo_text": {
            "total_lines": hlo_lines_total,
            "total_chars": hlo_chars_total,
        },
        "top_ops": _counter_pairs(ops_total, args.top),
    })
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
