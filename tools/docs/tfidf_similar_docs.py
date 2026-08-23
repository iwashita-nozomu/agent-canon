#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Finds TF-IDF-similar Markdown documents and drafts merge candidates.
# upstream design ../README.md shared tool index
# downstream design ../../documents/experiments/result-log-retention-and-visualization.md result policy
# @dependency-end
"""
tfidf_similar_docs.py

Simple TF-IDF based similar document detector for markdown files under `documents/`.

Outputs are written beneath the explicit external runtime root, under a
run-scoped directory. Set ``AGENT_CANON_RUNTIME_ROOT`` or pass
``--runtime-root``; the source checkout is never an implicit output location,
and missing runtime capability fails before a report is opened.

Usage:
  python3 tools/docs/tfidf_similar_docs.py \
    --runtime-root /abs/path/to/workspace/agent-canon-runtime/<run> --min 0.5 \
    [--documents-root /path/to/documents]

No external dependencies.
"""
import argparse
import itertools
import math
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

# Direct invocation must not turn the source checkout into a Python cache.
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.agent_tools.runtime_artifacts import (  # noqa: E402
    RuntimeArtifactBoundary,
    RuntimeArtifactError,
    runtime_artifact_boundary,
)


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
        if p.is_file()
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


def make_merged_draft(
    a_path: Path,
    b_path: Path,
    out_dir: Path,
    score: float,
    *,
    boundary: RuntimeArtifactBoundary | None = None,
):
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

    out_file = out_dir / (title + '.md')
    content = '\n'.join(out) + '\n'
    if boundary is None:
        raise RuntimeArtifactError(
            "merge-draft output requires the external runtime artifact boundary"
        )
    boundary.atomic_write_text(out_file.relative_to(boundary.root), content)
    return out_file


def create_output_dir(
    root: Path,
    runtime_root: str | None,
    *,
    boundary: RuntimeArtifactBoundary | None = None,
) -> Path:
    """Create one symlink-safe external output directory for this run."""
    boundary = boundary or runtime_artifact_boundary(root, runtime_root, create=True)
    parent = boundary.ensure_directory(Path("tasks") / "tfidf-similar-documents")
    return Path(tempfile.mkdtemp(prefix="run-", dir=str(parent)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--min', type=float, default=0.5)
    p.add_argument(
        '--documents-root',
        help='Read-only Markdown root (defaults to this checkout\'s documents/).',
    )
    p.add_argument(
        '--runtime-root',
        help='External runtime root (or AGENT_CANON_RUNTIME_ROOT).',
    )
    args = p.parse_args()

    ROOT = PROJECT_ROOT
    DOC_ROOT = (
        Path(args.documents_root).expanduser().resolve()
        if args.documents_root
        else ROOT / 'documents'
    )
    try:
        boundary = runtime_artifact_boundary(ROOT, args.runtime_root, create=True)
        output_dir = create_output_dir(ROOT, args.runtime_root, boundary=boundary)
    except RuntimeArtifactError as exc:
        p.error(f"runtime_root_error: {exc}")
    REPORT = output_dir / 'tfidf_similar_documents_report.txt'
    MERGE_DIR = output_dir / 'merge_candidates_tfidf'

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
                draft = make_merged_draft(a, b, MERGE_DIR, sim, boundary=boundary)
                lines.append(f'  Draft: {draft}')
            except RuntimeArtifactError:
                raise
            except Exception as e:
                lines.append(f'  Draft generation failed: {e}')

    boundary.atomic_write_text(
        REPORT.relative_to(boundary.root), '\n'.join(lines) + '\n'
    )
    print('Report written to', REPORT)


if __name__ == '__main__':
    main()
