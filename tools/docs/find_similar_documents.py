#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides find similar documents documentation tooling.
# upstream design ../README.md shared automation index
# @dependency-end

"""
find_similar_documents.py

Detect similar markdown documents under `documents/` (excluding templates and legacy backup files)
and produce a report plus simple merge-draft files for manual review.

Usage:
  python3 tools/docs/find_similar_documents.py [--min 0.5]

Outputs are written beneath the explicit external runtime root, under a
run-scoped directory. Set ``AGENT_CANON_RUNTIME_ROOT`` or pass
``--runtime-root``; the source checkout is never an implicit output location.
"""
import argparse
import difflib
import itertools
import re
import sys
import tempfile
from pathlib import Path

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
    t = re.sub(r"[#>*`-]", " ", t)
    t = " ".join(t.split())
    return t.lower()


def read_files(root: Path):
    files = [p for p in root.rglob('*.md') if p.is_file()]
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


def create_output_dir(root: Path, runtime_root: str | None) -> Path:
    """Create one symlink-safe external output directory for this run."""
    boundary: RuntimeArtifactBoundary = runtime_artifact_boundary(
        root, runtime_root, create=True
    )
    parent = boundary.ensure_directory(Path("tasks") / "similar-documents")
    return Path(tempfile.mkdtemp(prefix="run-", dir=str(parent)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--min', type=float, default=0.6)
    p.add_argument(
        '--runtime-root',
        help='External runtime root (or AGENT_CANON_RUNTIME_ROOT).',
    )
    args = p.parse_args()

    ROOT = PROJECT_ROOT
    DOC_ROOT = ROOT / 'documents'
    try:
        output_dir = create_output_dir(ROOT, args.runtime_root)
    except RuntimeArtifactError as exc:
        p.error(f"runtime_root_error: {exc}")
    REPORT = output_dir / 'similar_documents_report.txt'
    MERGE_DIR = output_dir / 'merge_candidates'

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
