#!/usr/bin/env python3
"""
find_similar_documents.py

Detect similar markdown documents under `documents/` (excluding templates and legacy backup files)
and produce a report plus simple merge-draft files for manual review.

Usage:
  python3 scripts/tools/find_similar_documents.py [--min 0.5]

Outputs:
  - reports/similar_documents_report.txt
  - reports/merge_candidates/*.md (drafts)
"""
from pathlib import Path
import difflib
import argparse
import itertools
import re


def normalize_text(t: str) -> str:
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    t = re.sub(r"[#>*`-]", " ", t)
    t = " ".join(t.split())
    return t.lower()


def read_files(root: Path):
    files = [p for p in root.rglob('*.md')]
    files = [p for p in files if 'template' not in p.name and not p.name.endswith('.bak')]
    return sorted(files)


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def make_merged_draft(a_path: Path, b_path: Path, out_dir: Path, score: float):
    a = a_path.read_text(encoding='utf-8')
    b = b_path.read_text(encoding='utf-8')
    # simple merge: start with A, then append lines from B not present in A
    a_lines = [ln.rstrip() for ln in a.splitlines()]
    b_lines = [ln.rstrip() for ln in b.splitlines()]
    uniq_from_b = [ln for ln in b_lines if ln and ln not in a]

    title = f"MergeDraft-{a_path.stem}--{b_path.stem}".replace(' ', '_')
    out = []
    out.append(f"# Proposed merge: {a_path.name} + {b_path.name}")
    out.append("")
    out.append(f"Similarity score: {score:.3f}")
    out.append("")
    out.append("## Source A: " + str(a_path))
    out.append("")
    out.append(a)
    out.append("")
    out.append("## Source B: " + str(b_path))
    out.append("")
    out.append(b)
    out.append("")
    out.append("## Suggested consolidated content (draft)")
    out.append("")
    out.extend(a_lines)
    if uniq_from_b:
        out.append("")
        out.append("<!-- Additional lines from B not present in A: review and relocate as needed -->")
        out.append("")
        out.extend(uniq_from_b)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / (title + '.md')
    out_file.write_text('\n'.join(out) + '\n', encoding='utf-8')
    return out_file


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--min', type=float, default=0.6)
    args = p.parse_args()

    ROOT = Path('.').resolve()
    DOC_ROOT = ROOT / 'documents'
    REPORT = ROOT / 'reports' / 'similar_documents_report.txt'
    MERGE_DIR = ROOT / 'reports' / 'merge_candidates'

    files = read_files(DOC_ROOT)
    texts = {f: normalize_text(f.read_text(encoding='utf-8')) for f in files}

    pairs = []
    for a, b in itertools.combinations(files, 2):
        sim = similarity(texts[a], texts[b])
        if sim >= args.min:
            pairs.append((sim, a, b))

    pairs.sort(reverse=True)
    lines = []
    if not pairs:
        lines.append(f'No similar files found with threshold >= {args.min}')
    else:
        lines.append(f'Similar document pairs (threshold >= {args.min})')
        for sim, a, b in pairs:
            lines.append(f'{sim:.3f}  {a}  {b}')
            try:
                draft = make_merged_draft(a, b, MERGE_DIR, sim)
                lines.append(f'  Draft: {draft}')
            except Exception as e:
                lines.append(f'  Draft generation failed: {e}')

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Report written to', REPORT)


if __name__ == '__main__':
    main()
