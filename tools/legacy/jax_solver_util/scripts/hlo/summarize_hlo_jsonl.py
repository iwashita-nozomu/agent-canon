# @dependency-start
# upstream implementation ../README.md directory index and local context contract
# @dependency-end
from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from collections import Counter
from pathlib import Path
from typing import Any


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    """JSONL を 1 行ずつ読み込みます。"""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            obj = json.loads(s)
            if isinstance(obj, dict):
                yield obj


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


def _get_record_key(rec: dict[str, Any], key: str) -> str:
    value = rec.get(key)
    if value is None:
        return ""
    return str(value)


def _count_lines(text: str) -> int:
    return len([line for line in text.splitlines() if line.strip()])


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize HLO JSONL.")
    parser.add_argument("jsonl", type=str, help="Path to JSONL (produced by jax_util.hlo.dump or dump_hlo_jsonl).")
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

    out: dict[str, Any] = {
        "jsonl": str(path),
        "total_records": total_records,
        "total_selected": total_selected,
        "filter": {"only_case": args.only_case},
        "tags": tags.most_common(),
        "dialects": dialects.most_common(),
        "hlo_text": {
            "total_lines": hlo_lines_total,
            "total_chars": hlo_chars_total,
        },
        "top_ops": ops_total.most_common(args.top),
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
