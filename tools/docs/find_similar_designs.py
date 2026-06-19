#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Finds similar design documents for consolidation review.
# upstream design ../README.md shared tool index
# downstream design ../../documents/design/README.md documents design placement
# @dependency-end
"""
find_similar_designs.py

Detect similar markdown design documents under `documents/design/` using
pairwise similarity (difflib) and produce a report with candidate groups.

Usage:
  python3 scripts/tools/find_similar_designs.py [--min 0.6]

Report: reports/similar_designs_report.txt
"""
import argparse
import difflib
import itertools
import re
from pathlib import Path

ROOT = Path('.').resolve()
DESIGN_DIR = ROOT / 'documents' / 'design'
REPORT = ROOT / 'reports' / 'similar_designs_report.txt'


def normalize_text(t: str) -> str:
    # remove code blocks, collapse whitespace, strip markdown links
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    t = re.sub(r"[#>*`-]", " ", t)
    t = ' '.join(t.split())
    return t.lower()


def read_files():
    files = [p for p in DESIGN_DIR.rglob('*.md')]
    # exclude templates
    files = [p for p in files if 'template' not in p.name]
    return sorted(files)


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--min', type=float, default=0.6)
    args = p.parse_args()

    files = read_files()
    texts = {f: normalize_text(f.read_text(encoding='utf-8')) for f in files}

    pairs = []
    for a, b in itertools.combinations(files, 2):
        sim = similarity(texts[a], texts[b])
        if sim >= args.min:
            pairs.append((sim, a, b))

    pairs.sort(reverse=True)
    lines = []
    if not pairs:
        lines.append(f'No similar design files found with threshold >= {args.min}')
    else:
        lines.append(f'Similar design file pairs (threshold >= {args.min})')
        for sim, a, b in pairs:
            lines.append(f'{sim:.3f}  {a}  {b}')

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text('\n'.join(lines), encoding='utf-8')
    print('Report written to', REPORT)


if __name__ == '__main__':
    main()
