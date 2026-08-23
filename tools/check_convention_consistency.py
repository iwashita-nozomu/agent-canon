#!/usr/bin/env python3
# @dependency-start
# contract tool
# responsibility Provides check convention consistency repository automation.
# upstream design README.md shared automation index
# @dependency-end

"""
規約矛盾検出スクリプト。

スキルファイル section 12.2 の pseudo-code を実装。
coding-conventions-*.md ファイル間の矛盾を検出。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TypedDict


class Rule(TypedDict):
    """One extracted convention rule."""

    type: str
    subtype: str
    description: str


def load_convention_files() -> dict[str, str]:
    """規約ファイルをロード。"""
    convention_dir = Path("documents")
    files = {}

    for pattern in ["coding-conventions-*.md", "REVIEW_PROCESS.md", "BRANCH_SCOPE.md"]:
        for file in convention_dir.glob(pattern):
            files[file.name] = file.read_text(encoding="utf-8")

    return files


def extract_rules(content: str) -> list[Rule]:
    """規約ファイルから「must」「should」ルールを抽出。"""
    rules: list[Rule] = []

    # パターン1: "must ..." や "must not ..."
    must_pattern = r"(?:- \[)?\s*\[✅\]?\s*(must|must\s+not)\s+(.+?)(?:\n|$)"
    for match in re.finditer(must_pattern, content, re.IGNORECASE | re.MULTILINE):
        rule_type = match.group(1).lower()
        description = match.group(2).strip()
        rules.append({"type": "must", "subtype": rule_type, "description": description})

    # パターン2: "should ..." や "should not ..."
    should_pattern = r"(?:- \[)?\s*\[⚠️\]?\s*(should|should\s+not)\s+(.+?)(?:\n|$)"
    for match in re.finditer(should_pattern, content, re.IGNORECASE | re.MULTILINE):
        rule_type = match.group(1).lower()
        description = match.group(2).strip()
        rules.append({"type": "should", "subtype": rule_type, "description": description})

    return rules


def check_contradiction(
    rules1: list[Rule],
    rules2: list[Rule],
    file1: str,
    file2: str,
) -> list[dict[str, str]]:
    """2つのルールセット間の矛盾を検出。"""
    contradictions = []

    for r1 in rules1:
        # "must do X" vs "must not do X" の矛盾
        if r1["subtype"] == "must":
            for r2 in rules2:
                if r2["subtype"] == "must not":
                    if _similar_descriptions(r1["description"], r2["description"]):
                        contradictions.append({
                            "type": "contradiction",
                            "file1": file1,
                            "rule1": r1["description"],
                            "file2": file2,
                            "rule2": r2["description"],
                        })

    return contradictions


def _similar_descriptions(desc1: str, desc2: str, threshold: float = 0.7) -> bool:
    """2つのルール説明の類似度をチェック（簡易版）。"""
    words1 = set(desc1.lower().split())
    words2 = set(desc2.lower().split())

    if not words1 or not words2:
        return False

    intersection = len(words1 & words2)
    union = len(words1 | words2)
    similarity = intersection / union if union > 0 else 0

    return similarity >= threshold


def main() -> int:
    """規約矛盾検出メイン。"""
    conventions = load_convention_files()
    issues = []

    print("🔍 Checking convention consistency...\n")

    # ファイル間の矛盾をチェック
    files = list(conventions.items())
    for i, (file1, content1) in enumerate(files):
        for file2, content2 in files[i+1:]:
            rules1 = extract_rules(content1)
            rules2 = extract_rules(content2)

            contradictions = check_contradiction(rules1, rules2, file1, file2)
            for contradiction in contradictions:
                issues.append(contradiction)
                print(f"⚠️ CONTRADICTION FOUND:")
                print(f"   {file1}: {contradiction['rule1']}")
                print(f"   {file2}: {contradiction['rule2']}\n")

    print(f"\n📊 Summary: {len(issues)} issues found")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
