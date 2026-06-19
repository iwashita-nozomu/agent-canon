#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Finds TF-IDF-similar Markdown documents and drafts merge candidates.
# upstream design ../README.md shared tool index
# downstream design ../../documents/result-log-retention-and-visualization.md result policy
# @dependency-end
"""
tfidf_similar_docs.py

Simple TF-IDF based similar document detector for markdown files under `documents/`.

Outputs:
 - reports/tfidf_similar_documents_report.txt
 - documents/merge_candidates_tfidf/*.md (drafts)

Usage:
  python3 scripts/tools/tfidf_similar_docs.py --min 0.5

No external dependencies.
"""
import argparse
import itertools
import math
import re
from collections import Counter
from pathlib import Path


def normalize_text(t: str) -> str:
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
    t = re.sub(r"[#>*`\-]", " ", t)
    t = re.sub(r"[^0-9a-zA-Z_\u0080-\uFFFF]+", " ", t)
    t = " ".join(t.split())
    return t.lower()


def read_docs(root: Path):
    files = [
        p
        for p in root.rglob('*.md')
        if 'template' not in p.name and not p.name.endswith('.bak')
    ]
    files = sorted(files)
    docs = {}
    for p in files:
        try:
            docs[p] = normalize_text(p.read_text(encoding='utf-8'))
        except Exception:
            docs[p] = ''
    return docs


def build_tfidf(docs):
    N = len(docs)
    tfs = {}
    df = Counter()
    for p, text in docs.items():
        tokens = text.split()
        tf = Counter(tokens)
        tfs[p] = tf
        for term in set(tokens):
            df[term] += 1

    idf = {term: math.log((N + 1) / (1 + dfcount)) for term, dfcount in df.items()}

    vectors = {}
    for p, tf in tfs.items():
        vec = {}
        for term, freq in tf.items():
            vec[term] = (1 + math.log(freq)) * idf.get(term, 0.0)
        vectors[p] = vec
    return vectors


def cosine_sim(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    num = 0.0
    for k, v in a.items():
        if k in b:
            num += v * b[k]
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return num / (norm_a * norm_b)


def make_merged_draft(a_path: Path, b_path: Path, out_dir: Path, score: float):
    a = a_path.read_text(encoding='utf-8')
    b = b_path.read_text(encoding='utf-8')
    a_lines = [ln.rstrip() for ln in a.splitlines()]
    b_lines = [ln.rstrip() for ln in b.splitlines()]
    uniq_from_b = [ln for ln in b_lines if ln and ln not in a_lines]

    title = f"TFIDF_MergeDraft-{a_path.stem}--{b_path.stem}".replace(' ', '_')
    out = []
    out.append(f"# Proposed TF-IDF merge: {a_path.name} + {b_path.name}")
    out.append("")
    out.append(f"Similarity (TF-IDF cosine): {score:.3f}")
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
        out.append(
            "<!-- Additional lines from B not present in A: "
            "review and relocate as needed -->"
        )
        out.append("")
        out.extend(uniq_from_b)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / (title + '.md')
    out_file.write_text('\n'.join(out) + '\n', encoding='utf-8')
    return out_file


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--min', type=float, default=0.5)
    args = p.parse_args()

    ROOT = Path('.').resolve()
    DOC_ROOT = ROOT / 'documents'
    REPORT = ROOT / 'reports' / 'tfidf_similar_documents_report.txt'
    MERGE_DIR = DOC_ROOT / 'merge_candidates_tfidf'

    docs = read_docs(DOC_ROOT)
    vectors = build_tfidf(docs)

    pairs = []
    for a, b in itertools.combinations(sorted(docs.keys()), 2):
        sim = cosine_sim(vectors[a], vectors[b])
        if sim >= args.min:
            pairs.append((sim, a, b))

    pairs.sort(reverse=True)
    lines = []
    if not pairs:
        lines.append(f'No similar files found with threshold >= {args.min}')
    else:
        lines.append(f'Similar document pairs (TF-IDF threshold >= {args.min})')
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
