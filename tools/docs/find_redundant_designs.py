#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Finds exact duplicate design documents for consolidation review.
# upstream design ../README.md shared tool index
# downstream design ../../documents/design/README.md documents design placement
# @dependency-end
"""
find_redundant_designs.py

Detect exact-duplicate markdown files under documents/design/ and optionally
delete redundant copies while keeping a canonical file per group.

Usage:
  python3 scripts/tools/find_redundant_designs.py [--delete]

Report written to: reports/redundant_designs.txt
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path('.').resolve()
DESIGN_DIR = ROOT / 'documents' / 'design'
REPORT = ROOT / 'reports' / 'redundant_designs.txt'


def normalize(text: str) -> str:
    # Basic normalization: strip, collapse whitespace
    return ' '.join(text.split())


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def find_md_files():
    if not DESIGN_DIR.exists():
        return []
    return [p for p in DESIGN_DIR.rglob('*.md') if 'template' not in p.name]


def choose_canonical(paths):
    # Prefer files inside documents/design/<submodule>/ (i.e., depth >=2)
    subs = [p for p in paths if len(p.relative_to(DESIGN_DIR).parts) >= 2]
    if subs:
        # pick the shortest relative path among subs
        return sorted(subs, key=lambda p: len(str(p)))[0]
    # otherwise pick shortest path
    return sorted(paths, key=lambda p: len(str(p)))[0]


def main():
    md = find_md_files()
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    groups = {}
    for p in md:
        try:
            text = p.read_text(encoding='utf-8')
        except Exception:
            text = ''
        key = sha(normalize(text))
        groups.setdefault(key, []).append(p)

    lines = []
    deletions = []
    for h, paths in groups.items():
        if len(paths) <= 1:
            continue
        lines.append('DUP_GROUP:')
        for pp in paths:
            lines.append('  ' + str(pp))
        canonical = choose_canonical(paths)
        lines.append('  KEEP: ' + str(canonical))
        for pp in paths:
            if pp != canonical:
                lines.append('  DELETE: ' + str(pp))
                deletions.append(pp)
        lines.append('')

    if not lines:
        lines = ['No exact-duplicate design files found.']

    REPORT.write_text('\n'.join(lines), encoding='utf-8')
    print('Report written to', REPORT)

    if '--delete' in sys.argv:
        if not deletions:
            print('No files to delete.')
            return
        for p in deletions:
            try:
                p.unlink()
                print('Deleted', p)
            except Exception as e:
                print('Failed to delete', p, e)
        # write deletions summary
        deleted_lines = lines + ['\nDELETED:\n'] + [str(p) for p in deletions]
        REPORT.write_text('\n'.join(deleted_lines), encoding='utf-8')
        print('Deletions complete; updated report at', REPORT)


if __name__ == '__main__':
    main()
