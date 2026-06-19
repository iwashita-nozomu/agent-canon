#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Fixes markdown code blocks documentation formatting.
# upstream design ../README.md shared automation index
# @dependency-end

"""Markdown code block language fixer.

MD040 違反（言語指定なしコードブロック）を自動修正します。
言語指定なしの ``` を検出する言語に自動変換します。

使用方法:
    python3 fix_markdown_code_blocks.py [FILES...]

例:
    python3 fix_markdown_code_blocks.py documents/
"""

import argparse
import glob
import json
import re
import sys
from pathlib import Path


def infer_language(content: str) -> str:
    """Infer a code block language from content."""
    content_lower = content.lower()

    # Python
    if (
        "import " in content
        or "def " in content
        or "class " in content
        or "print(" in content
        or "for " in content
        or "if __name__" in content
    ):
        return "python"

    # Bash/Shell
    if content.startswith("#!") or "#!/bin/bash" in content or "$(" in content:
        return "bash"

    # JavaScript/TypeScript
    if (
        "function " in content
        or "const " in content
        or "let " in content
        or "=>" in content
        or "console.log" in content
    ):
        return "javascript"

    # JSON
    if content.strip().startswith("{") or content.strip().startswith("["):
        try:
            json.loads(content)
            return "json"
        except json.JSONDecodeError:
            pass

    # YAML
    if ":" in content and content.count(":") > content.count("://"):
        return "yaml"

    # SQL
    if any(keyword in content_lower for keyword in ["select ", "insert ", "update ", "delete "]):
        return "sql"

    # Dockerfile
    if "FROM " in content or "RUN " in content:
        return "dockerfile"

    # Default
    return "text"


def fix_code_blocks(content: str) -> tuple[str, list[str]]:
    """Fix code blocks that do not declare a language."""
    lines = content.split("\n")
    fixed_lines = []
    changes = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Opening code fence (言語指定なし)
        if re.match(r"^```\s*$", line):
            # コードブロックの内容を収集
            code_content = []
            i += 1
            while i < len(lines) and not re.match(r"^```", lines[i]):
                code_content.append(lines[i])
                i += 1

            # 言語を推定
            inferred_lang = infer_language("\n".join(code_content))
            new_fence = f"```{inferred_lang}"
            fixed_lines.append(new_fence)
            changes.append(f"Line {len(fixed_lines)}: Add language '{inferred_lang}' to code block")

            # コンテンツを追加
            fixed_lines.extend(code_content)

            # Closing fence
            if i < len(lines):
                fixed_lines.append(lines[i])
                i += 1
        else:
            fixed_lines.append(line)
            i += 1

    return "\n".join(fixed_lines), changes


def process_file(filepath: str) -> tuple[bool, list[str]]:
    """Process one Markdown file."""
    try:
        path = Path(filepath)
        original_content = path.read_text(encoding="utf-8")

        fixed_content, changes = fix_code_blocks(original_content)

        if changes:
            path.write_text(fixed_content, encoding="utf-8")
            return True, changes
        return False, []
    except Exception as e:
        print(f"❌ Error processing {filepath}: {e}", file=sys.stderr)
        return False, []


def main() -> int:
    """Run the CLI."""
    parser = argparse.ArgumentParser(description="Fix Markdown Code Block Language Specifications (MD040)")
    parser.add_argument("files", nargs="*", default=["."], help="Files or directories to process")
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

    # フィルタリング
    md_files = [
        str(f)
        for f in md_files
        if not any(x in str(f) for x in [".git", ".worktrees", "__pycache__", "Archive"])
    ]
    md_files = list(set(md_files))

    if not md_files:
        print("No markdown files found.")
        return 0

    total_changes = 0
    modified_files = 0

    for filepath in sorted(md_files):
        has_changes, changes = process_file(filepath)
        if has_changes:
            rel_path = filepath.replace("./", "").replace("/workspace/", "")
            print(f"\n📄 {rel_path}:")
            for change in changes[:10]:
                print(f"  {change}")
                total_changes += 1
            if len(changes) > 10:
                print(f"  ... and {len(changes) - 10} more")
                total_changes += len(changes) - 10
            modified_files += 1

    print(f"\n✅ Fixed: {total_changes} code block(s) in {modified_files} file(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
