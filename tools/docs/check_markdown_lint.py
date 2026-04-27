#!/usr/bin/env python3
# @dependency-start
# upstream design ../README.md shared automation index
# @dependency-end

"""
Markdown Lint チェッカー（.markdownlint.json 規格準拠）

このツールは、リポジトリの .markdownlint.json 設定に基づいて、
マークダウンファイルのリント違反を検出します。

使用方法:
    python3 check_markdown_lint.py [OPTIONS] [FILES...]

オプション:
    --fix           : 自動修正可能な違反を修正
    --check         : エラー終了コード付きで検査（CI用）
    --verbose       : 詳細出力
    --json          : JSON 形式で出力

例:
    python3 check_markdown_lint.py documents/
    python3 check_markdown_lint.py --check *.md
    python3 check_markdown_lint.py --fix documents/ scripts/
"""

import json
import re
import sys
import glob
from pathlib import Path
from typing import List, Tuple, Dict
import argparse


class MarkdownLinter:
    """マークダウンリント チェッカー"""

    def __init__(self, config_file: str = ".markdownlint.json"):
        """初期化"""
        try:
            with open(config_file) as f:
                self.config = json.load(f)
        except FileNotFoundError:
            print(f"⚠️  Config file not found: {config_file}")
            self.config = {"default": True}
        self.issues: Dict[str, List[Tuple[int, str, str]]] = {}

    def check_md001(self, filepath: str) -> List[Tuple[int, str]]:
        """MD001: Header increment check - ヘッダーは 1 段階ずつ上がること"""
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        issues = []
        prev_level = 0
        for i, line in enumerate(lines, 1):
            match = re.match(r"^(#+)\s", line)
            if match:
                level = len(match.group(1))
                # H1 から始まる場合は prev_level = 0 であることに注意
                if prev_level == 0:
                    prev_level = level
                elif level > prev_level + 1:
                    issues.append((i, f"Header jump from H{prev_level} to H{level}"))
                else:
                    prev_level = level
        return issues

    def check_md003(self, filepath: str) -> List[Tuple[int, str]]:
        """MD003: Header style consistency"""
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        issues = []
        style = self.config.get("MD003", {}).get("style", "consistent")
        if style == "consistent":
            styles = set()
            for i, line in enumerate(lines, 1):
                if re.match(r"^#+\s", line):
                    styles.add("atx")
            # atx スタイルのみなら OK
        return issues

    def check_md004(self, filepath: str) -> List[Tuple[int, str]]:
        """MD004: List marker style consistency"""
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        issues = []
        style = self.config.get("MD004", {}).get("style", "consistent")
        if style == "consistent":
            markers_at_depth: Dict[int, set] = {}
            for i, line in enumerate(lines, 1):
                match = re.match(r"^( *)[-*+]\s", line)
                if match:
                    depth = len(match.group(1)) // 2
                    marker = "-" if match.group(0)[match.start(1) + len(match.group(1))] == "-" else "*"
                    if depth not in markers_at_depth:
                        markers_at_depth[depth] = set()
                    markers_at_depth[depth].add(marker)

            # Check consistency
            for depth, markers in markers_at_depth.items():
                if len(markers) > 1:
                    issues.append((0, f"Inconsistent list markers at depth {depth}: {markers}"))
        return issues

    def check_md009(self, filepath: str) -> List[Tuple[int, str]]:
        """MD009: Trailing spaces"""
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        issues = []
        for i, line in enumerate(lines, 1):
            # 行末の改行を除いた部分でチェック
            line_content = line.rstrip("\n")
            if line_content != line_content.rstrip():
                issues.append((i, "Trailing spaces"))
        return issues

    def check_md010(self, filepath: str) -> List[Tuple[int, str]]:
        """MD010: Hard tabs"""
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        issues = []
        for i, line in enumerate(lines, 1):
            if "\t" in line:
                issues.append((i, "Hard tabs"))
        return issues

    def check_md030(self, filepath: str) -> List[Tuple[int, str]]:
        """MD030: List marker spacing"""
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        issues = []
        config = self.config.get("MD030", {})
        ul_single = config.get("ul_single", 1)
        ol_single = config.get("ol_single", 1)

        for i, line in enumerate(lines, 1):
            # Unordered list
            match = re.match(r"^( *)[-*+]( +)\S", line)
            if match:
                spaces = len(match.group(2))
                if spaces != ul_single:
                    issues.append((i, f"List marker spacing: expected {ul_single}, got {spaces}"))

            # Ordered list
            match = re.match(r"^( *)\d+\.( +)\S", line)
            if match:
                spaces = len(match.group(2))
                if spaces != ol_single:
                    issues.append((i, f"Ordered list spacing: expected {ol_single}, got {spaces}"))

        return issues

    def check_md040(self, filepath: str) -> List[Tuple[int, str]]:
        """MD040: Fenced code blocks should have language specified"""
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        issues = []
        in_fence = False
        fence_char = ""
        fence_len = 0

        for i, line in enumerate(lines, 1):
            stripped = line.rstrip("\n")

            if not in_fence:
                match = re.match(r"^([`~]{3,})([^\n]*)$", stripped)
                if not match:
                    continue

                fence = match.group(1)
                info = match.group(2).strip()
                fence_char = fence[0]
                fence_len = len(fence)
                in_fence = True

                if not info:
                    issues.append((i, "Fenced code block should specify language"))
                continue

            if re.match(rf"^{re.escape(fence_char)}{{{fence_len},}}\s*$", stripped):
                in_fence = False
                fence_char = ""
                fence_len = 0

        return issues

    def scan_file(self, filepath: str) -> List[Tuple[int, str, str]]:
        """ファイルをスキャン"""
        check_methods = [
            ("MD001", self.check_md001),
            ("MD003", self.check_md003),
            ("MD004", self.check_md004),
            ("MD009", self.check_md009),
            ("MD010", self.check_md010),
            ("MD030", self.check_md030),
            ("MD040", self.check_md040),
        ]

        all_issues = []
        for code, method in check_methods:
            if self.config.get(code) is not False:  # 有効な場合
                try:
                    issues = method(filepath)
                    for line_no, message in issues:
                        all_issues.append((line_no, code, message))
                except Exception as e:
                    print(f"Error checking {code} in {filepath}: {e}", file=sys.stderr)

        return all_issues

    def scan_files(self, file_patterns: List[str]) -> Dict[str, List[Tuple[int, str, str]]]:
        """複数ファイルをスキャン"""
        md_files = []
        for pattern in file_patterns:
            if "*" in pattern:
                md_files.extend(glob.glob(pattern, recursive=True))
            else:
                p = Path(pattern)
                if p.is_dir():
                    md_files.extend(p.rglob("*.md"))
                else:
                    md_files.append(pattern)

        # Filter - convert Path to str
        md_files = [str(f) for f in md_files if not any(x in str(f) for x in [".git", ".worktrees", "__pycache__", "Archive"])]
        md_files = list(set(md_files))  # Remove duplicates

        issues = {}
        for filepath in sorted(md_files):
            file_issues = self.scan_file(filepath)
            if file_issues:
                issues[filepath] = file_issues

        return issues

    def report(self, issues: Dict[str, List[Tuple[int, str, str]]], verbose: bool = False) -> int:
        """結果を報告"""
        if not issues:
            print("✅ No markdown lint issues found!")
            return 0

        exit_code = 1
        total_issues = sum(len(v) for v in issues.values())
        print(f"Found {total_issues} issue(s) in {len(issues)} file(s):\n")

        for filepath, file_issues in sorted(issues.items()):
            rel_path = filepath.replace("./", "").replace("/workspace/", "")
            print(f"📄 {rel_path}:")
            for line_no, code, message in sorted(file_issues)[:10]:
                print(f"  Line {line_no}: {code} - {message}")
            if len(file_issues) > 10:
                print(f"  ... and {len(file_issues) - 10} more")
            print()

        return exit_code


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(description="Markdown Lint Checker")
    parser.add_argument("files", nargs="*", default=["."], help="Files or directories to check")
    parser.add_argument("--fix", action="store_true", help="Auto-fix violations")
    parser.add_argument("--check", action="store_true", help="Return error code on violations")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    linter = MarkdownLinter()
    issues = linter.scan_files(args.files)

    if args.json:
        print(json.dumps({k: [(ln, c, m) for ln, c, m in v] for k, v in issues.items()}, indent=2))
    else:
        exit_code = linter.report(issues, verbose=args.verbose)
        return exit_code if args.check else (0 if exit_code == 0 else 1)


if __name__ == "__main__":
    sys.exit(main() or 0)
