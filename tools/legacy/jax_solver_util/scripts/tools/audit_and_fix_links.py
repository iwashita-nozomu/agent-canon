#!/usr/bin/env python3
# @dependency-start
# upstream implementation ../README.md directory index and local context contract
# @dependency-end
"""
Audit markdown documents for broken links and attempt to auto-fix resolvable ones.

Actions:
- Scan `documents/` for markdown files
- Find markdown links `[text](target)` where target is a relative path
- If target does not exist, search workspace for files with same basename
  - If exactly one candidate found, replace link target with correct relative path
  - Otherwise record as unresolved in `reports/broken_links.txt`

Usage:
  python3 scripts/tools/audit_and_fix_links.py [--apply]
"""
from pathlib import Path
import re
import argparse
import sys


ROOT = Path('.').resolve()
DOC_ROOT = ROOT / 'documents'
REPORT = ROOT / 'reports' / 'broken_links.txt'


def find_markdown_links(text: str):
    # match [text](target)
    return re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text)


def replace_link_targets(text: str, replacements: dict) -> str:
    def repl(match):
        label, target = match.group(1), match.group(2)
        if target in replacements:
            return f'[{label}]({replacements[target]})'
        return match.group(0)

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl, text)


def relpath(from_path: Path, to_path: Path) -> str:
    try:
        return str(Path(to_path).relative_to(from_path.parent))
    except Exception:
        return str(Path(to_path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    md_files = list(DOC_ROOT.rglob('*.md'))
    # build basename index
    all_files = list(ROOT.rglob('*'))
    name_index = {}
    for p in all_files:
        if p.is_file():
            name_index.setdefault(p.name, []).append(p)

    unresolved = []
    fixes_made = 0

    for md in md_files:
        text = md.read_text(encoding='utf-8')
        links = find_markdown_links(text)
        replacements = {}
        for label, target in links:
            # ignore url links (http:// or mailto:)
            if re.match(r'^[a-z]+://', target) or target.startswith('mailto:'):
                continue
            # strip anchors
            target_path = target.split('#')[0]
            # resolve relative path
            cand = (md.parent / target_path).resolve()
            if cand.exists():
                continue
            # try to find candidate by basename
            basename = Path(target_path).name
            candidates = name_index.get(basename, [])
            # filter out legacy backup files if they still exist
            candidates = [c for c in candidates if not str(c).endswith('.bak')]
            if len(candidates) == 1:
                new_rel = relpath(md, candidates[0])
                # preserve anchor if present
                if '#' in target:
                    new_rel = new_rel + '#' + target.split('#',1)[1]
                replacements[target] = new_rel
            else:
                unresolved.append((md, target, candidates))

        if replacements:
            new_text = replace_link_targets(text, replacements)
            if args.apply:
                md.write_text(new_text, encoding='utf-8')
                fixes_made += 1
            else:
                print(f'Would fix links in {md}:', replacements)

    # write unresolved report
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for md, target, cands in unresolved:
        lines.append(f'File: {md}')
        lines.append(f'  Missing: {target}')
        if cands:
            lines.append('  Candidates:')
            for c in cands[:10]:
                lines.append(f'    {c}')
        else:
            lines.append('  Candidates: none')
        lines.append('')

    REPORT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Report written to {REPORT} -- unresolved: {len(unresolved)}; fixes_made: {fixes_made}')


if __name__ == '__main__':
    main()
