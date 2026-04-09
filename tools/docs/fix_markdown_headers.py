#!/usr/bin/env python3
"""
Markdown Header Level Auto-Fixer

MD001 違反（header インクリメント）を自動修正します。
H1 の後に H3 が続く場合、H3 を H2 に変換します。

使用方法:
    python3 fix_markdown_headers.py [FILES...]
    python3 fix_markdown_headers.py --dry-run [FILES...]  # プレビューのみ

例:
    python3 fix_markdown_headers.py documents/
    python3 fix_markdown_headers.py --dry-run *.md
"""

import re
import sys
import glob
from pathlib import Path
import argparse
from typing import List, Tuple


def fix_header_levels(content: str) -> Tuple[str, List[str]]:
    """ヘッダーレベルを修正"""
    lines = content.split("\n")
    fixed_lines = []
    changes = []
    prev_level = 0

    for i, line in enumerate(lines, 1):
        match = re.match(r"^(#+)(\s.*)$", line)
        if match:
            hashes = match.group(1)
            rest = match.group(2)
            level = len(hashes)

            # H1 から始まる場合
            if prev_level == 0:
                prev_level = level
                fixed_lines.append(line)
            # 1 段階ずつ上がっていない場合は修正
            elif level > prev_level + 1:
                # 次のレベルに変更
                next_level = prev_level + 1
                new_hashes = "#" * next_level
                new_line = new_hashes + rest
                fixed_lines.append(new_line)
                changes.append(f"Line {i}: Change H{level} to H{next_level}: {line.strip()[:50]}")
                prev_level = next_level
            else:
                prev_level = level
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)

    return "\n".join(fixed_lines), changes


def process_file(filepath: str, dry_run: bool = False) -> Tuple[bool, List[str]]:
    """ファイルを処理"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            original_content = f.read()

        fixed_content, changes = fix_header_levels(original_content)

        if changes:
            if not dry_run:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(fixed_content)
            return True, changes
        else:
            return False, []
    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}", file=sys.stderr)
        return False, []


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="Fix Markdown Header Levels (MD001)")
    parser.add_argument("files", nargs="*", default=["."], help="Files or directories to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying files")
    args = parser.parse_args()

    # ファイル収集
    md_files = []
    for pattern in args.files:
        if "*" in pattern:
            md_files.extend(glob.glob(pattern, recursive=True))
        else:
            p = Path(pattern)
            if p.is_dir():
                md_files.extend(p.rglob("*.md"))
            else:
                md_files.append(pattern)

    # フィルタリング - Path を str に変換
    md_files = [str(f) for f in md_files if not any(x in str(f) for x in [".git", ".worktrees", "__pycache__", "Archive"])]
    md_files = list(set(md_files))

    if not md_files:
        print("No markdown files found.")
        return 0

    total_changes = 0
    modified_files = 0

    for filepath in sorted(md_files):
        has_changes, changes = process_file(filepath, dry_run=args.dry_run)
        if has_changes:
            rel_path = filepath.replace("./", "").replace("/workspace/", "")
            print(f"\n📄 {rel_path}:")
            for change in changes:
                print(f"  {change}")
                total_changes += 1
            modified_files += 1

    print(f"\n{'📋 Preview' if args.dry_run else '✅ Fixed'}: {total_changes} header level(s) in {modified_files} file(s)")
    if args.dry_run:
        print("(Use without --dry-run to apply changes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
