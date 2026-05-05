#!/usr/bin/env python3
# @dependency-start
# upstream implementation README.md directory index and local context contract
# @dependency-end
"""
.code-review-SKILL.md のセクション分離・再構成スクリプト

タスク:
- Task A: セクション 1 の subsection を独立化
  - 新セクション 4 に統合: 1.2 + 1.3
- Task B: セクション 2 の subsection を独立化
  - 新セクション 5: 2.2
- Task C: セクション 4-18 を 6-20 に繰り上げ（4と5は入れ替え）
"""

import re
from pathlib import Path


def read_skill_file(path: str) -> str:
    """ファイルを読み込む。"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_skill_file(path: str, content: str) -> None:
    """ファイルに書き込む。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def extract_section_by_header(content: str, header: str) -> tuple[int, int, str]:
    """
    指定ヘッダーのセクション開始行と終了行を取得。
    
    Returns:
        (start_line, end_line, section_content)
    """
    lines = content.split("\n")
    start_idx = None
    end_idx = None
    
    for i, line in enumerate(lines):
        if line.startswith(header):
            start_idx = i
            break
    
    if start_idx is None:
        raise ValueError(f"Header not found: {header}")
    
    # 次の同レベル以上のヘッダーを探す
    header_level = len(header) - len(header.lstrip("#"))
    
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        if line.strip().startswith("#"):
            line_level = len(line) - len(line.lstrip("#"))
            if line_level <= header_level:
                end_idx = i - 1
                break
    
    if end_idx is None:
        end_idx = len(lines) - 1
    
    return start_idx, end_idx, "\n".join(lines[start_idx : end_idx + 1])


def restructure_sections(content: str) -> str:
    """
    セクション再構成を実行。
    
    新構成:
    1. Python コードレビュー（必須チェック）
    2. C++ コードレビュー（必須チェック）
    3. ドキュメント レビュー
    4. Python テスト・アーキテクチャ検証 ← 旧1.2 + 旧1.3
    5. C++ スタイル・ベストプラクティス ← 旧2.2
    6. プロジェクト規約との整合性 ← 旧5
    7. 規約ファイル矛盾検出 ← 旧4
    8. 実装⟷Doc⟷テストの三点セット ← 旧7
    9. Docker 環境依存関係の検証 ← 旧6
    10. レビュー実施フロー ← 旧8
    ... (11-20: 旧9-18)
    """
    
    lines = content.split("\n")
    new_lines = []
    skip_until_next_section = False
    current_line_idx = 0
    
    # パターンを定義
    is_section_header = lambda line: re.match(r"^##\s+\d+\.", line) is not None
    is_subsection_header = lambda line: re.match(r"^###\s+\d+\.\d+", line) is not None
    
    while current_line_idx < len(lines):
        line = lines[current_line_idx]
        
        # セクション 1-3 はそのまま (ただしヘッダーは既に修正済み)
        if is_section_header(line):
            match = re.match(r"^## (\d+)\.", line)
            section_num = int(match.group(1))
            
            # セクション 1-3 はそのまま
            if section_num <= 3:
                new_lines.append(line)
                current_line_idx += 1
                continue
            
            # セクション 4 (旧): 規約ファイル矛盾検出 → スキップ (後で処理)
            elif section_num == 4:
                # このセクションの内容をスキップし、後で新セクション 7 として挿入
                _, end_idx, _ = extract_section_by_header(content, "## 4.")
                current_line_idx = end_idx + 1
                continue
            
            # セクション 5 (旧): プロジェクト規約 → 新セクション 6
            elif section_num == 5:
                _, end_idx, section_content = extract_section_by_header(
                    content, "## 5."
                )
                new_section_content = section_content.replace(
                    "## 5.", "## 6."
                ).replace("### 5.", "### 6.")
                new_lines.append(new_section_content)
                current_line_idx = end_idx + 1
                continue
            
            # セクション 6 (旧) 以降: 番号を繰り上げ
            else:
                _, end_idx, section_content = extract_section_by_header(
                    content, f"## {section_num}."
                )
                new_section_num = section_num + 2  # 4, 5は新規セクション, 6は9へ
                if section_num == 4:
                    new_section_num = 7  # 4 → 7 (順序入れ替え)
                elif section_num == 5:
                    new_section_num = 6  # 5 → 6 (順序入れ替え)
                elif section_num == 6:
                    new_section_num = 9  # 6 → 9 (新セクション 4, 5 插入)
                elif section_num >= 7:
                    new_section_num = section_num + 3  # 7 → 10, 8 → 11, etc.
                
                new_section_content = update_section_numbers(
                    section_content, section_num, new_section_num
                )
                new_lines.append(new_section_content)
                current_line_idx = end_idx + 1
                continue
        
        # セクション 3 の直後に新セクション 4, 5 を挿入
        if re.match(r"^## 3\. ", line):
            # セクション 3 をそのまま追加
            _, end_idx, section_3_content = extract_section_by_header(
                content, "## 3."
            )
            new_lines.append(section_3_content)
            
            # ここに新セクション 4, 5 を作成
            new_lines.append("")
            new_lines.append(create_new_section_4_and_5(content))
            
            current_line_idx = end_idx + 1
            continue
        
        # 1.1 subsection は削除（既に処理済み）
        if is_subsection_header(line) and line.startswith("### 1."):
            current_line_idx += 1
            continue
        
        new_lines.append(line)
        current_line_idx += 1
    
    return "\n".join(new_lines)


def create_new_section_4_and_5(content: str) -> str:
    """新セクション 4 と 5 を作成（旧 1.2, 1.3, 2.2 から）。"""
    
    # 旧セクション 1.2 を抽出
    section_1_2_start, section_1_2_end, section_1_2 = extract_section_by_header(
        content, "### 1.2 テストコード"
    )
    section_1_2 = section_1_2.replace("### 1.2 テストコード レビュー（Python）",
                                      "### 4.1 テストコード レビュー（Python）")
    section_1_2 = re.sub(r"^###([ #]+)1\.2", r"###\g<1>4.1", section_1_2, flags=re.MULTILINE)
    
    # 旧セクション 1.3 を抽出
    section_1_3_start, section_1_3_end, section_1_3 = extract_section_by_header(
        content, "### 1.3 アーキテクチャ"
    )
    section_1_3 = section_1_3.replace("### 1.3 アーキテクチャ・設計チェック",
                                      "### 4.2 アーキテクチャ・設計チェック")
    section_1_3 = re.sub(r"^###( #+)1\.3", r"###\g<1>4.2", section_1_3, flags=re.MULTILINE)
    
    # 旧セクション 2.2 を抽出
    section_2_2_start, section_2_2_end, section_2_2 = extract_section_by_header(
        content, "### 2.2 スタイル"
    )
    
    # 新セクション 4
    new_section_4 = f"""---

## 4. Python テスト・アーキテクチャ検証

{section_1_2}

{section_1_3}"""
    
    # 新セクション 5
    new_section_5 = f"""---

## 5. C++ スタイル・ベストプラクティス

{section_2_2.replace("### 2.2 スタイル", "").strip()}"""
    
    return new_section_4 + "\n\n" + new_section_5


def update_section_numbers(content: str, old_num: int, new_num: int) -> str:
    """セクション内の番号を更新。"""
    # メインセクション番号
    content = content.replace(f"## {old_num}.", f"## {new_num}.", 1)
    
    # subsection 番号
    content = re.sub(
        rf"^### {re.escape(str(old_num))}\.",
        f"### {new_num}.",
        content,
        flags=re.MULTILINE
    )
    
    # 細部の subsection
    for i in range(10):
        content = content.replace(
            f"### {old_num}.{i}.", f"### {new_num}.{i}."
        )
    
    return content


if __name__ == "__main__":
    file_path = "/workspace/.code-review-SKILL.md"
    
    print(f"読み込み中: {file_path}")
    content = read_skill_file(file_path)
    
    print("セクション再構成中...")
    new_content = restructure_sections(content)
    
    print(f"書き込み中: {file_path}")
    write_skill_file(file_path, new_content)
    
    print("✅ 完了")
