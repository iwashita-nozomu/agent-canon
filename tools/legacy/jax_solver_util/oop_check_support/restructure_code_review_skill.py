#!/usr/bin/env python3
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design README.md legacy OOP check support policy
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

from __future__ import annotations

import argparse
import re
from pathlib import Path

SECTION_HEADER_RE = re.compile(r"^##\s+(\d+)\.")
SUBSECTION_HEADER_RE = re.compile(r"^###\s+(\d+\.\d+)")


def read_skill_file(path: Path) -> str:
    """ファイルを読み込む。"""
    return path.read_text(encoding="utf-8")


def write_skill_file(path: Path, content: str) -> None:
    """ファイルに書き込む。"""
    path.write_text(content, encoding="utf-8")


def extract_section_by_header(content: str, header: str) -> tuple[int, int, str]:
    """
    指定ヘッダーのセクション開始行と終了行を取得。

    Returns:
        (start_line, end_line, section_content)
    """
    lines = content.split("\n")
    start_idx = find_header_index(lines, header)
    header_level = len(header) - len(header.lstrip("#"))
    end_idx = find_section_end(lines, start_idx, header_level)
    return start_idx, end_idx, "\n".join(lines[start_idx : end_idx + 1])


def find_header_index(lines: list[str], header: str) -> int:
    """指定ヘッダーに一致する行番号を返す。"""
    for line_index, line in enumerate(lines):
        if line.startswith(header):
            return line_index
    raise ValueError(f"Header not found: {header}")


def find_section_end(lines: list[str], start_idx: int, header_level: int) -> int:
    """同レベル以上の次ヘッダー直前を返す。"""
    for line_index in range(start_idx + 1, len(lines)):
        line = lines[line_index]
        if line.strip().startswith("#") and heading_level(line) <= header_level:
            return line_index - 1
    return len(lines) - 1


def heading_level(line: str) -> int:
    """Markdown heading level を返す。"""
    return len(line) - len(line.lstrip("#"))


def split_top_sections(content: str) -> tuple[str, dict[int, str]]:
    """本文をトップレベル numbered section に分割する。"""
    lines = content.split("\n")
    starts = numbered_section_starts(lines)
    if not starts:
        return content, {}

    prefix = "\n".join(lines[: starts[0][0]])
    sections: dict[int, str] = {}
    for item_index, (start_idx, section_num) in enumerate(starts):
        next_start = starts[item_index + 1][0] if item_index + 1 < len(starts) else len(lines)
        sections[section_num] = "\n".join(lines[start_idx:next_start]).rstrip("\n")
    return prefix, sections


def numbered_section_starts(lines: list[str]) -> list[tuple[int, int]]:
    """`## N.` 形式の section 開始位置を返す。"""
    starts: list[tuple[int, int]] = []
    for line_index, line in enumerate(lines):
        match = SECTION_HEADER_RE.match(line)
        if match:
            starts.append((line_index, int(match.group(1))))
    return starts


def restructure_sections(content: str) -> str:
    """セクション再構成を実行。"""
    prefix, sections = split_top_sections(content)
    if not sections:
        return content

    rebuilt = nonempty_blocks(
        [
            prefix.strip("\n"),
            section_without_subsections(sections[1], ("1.2", "1.3")),
            section_without_subsections(sections[2], ("2.2",)),
            sections[3],
            create_new_section_4_and_5(content),
            renumber_existing_section(sections, 5, 6),
            renumber_existing_section(sections, 4, 7),
            renumber_existing_section(sections, 7, 8),
            renumber_existing_section(sections, 6, 9),
            *renumber_remaining_sections(sections),
        ]
    )
    return "\n\n".join(rebuilt) + "\n"


def nonempty_blocks(blocks: list[str | None]) -> list[str]:
    """空 block を取り除く。"""
    return [block.rstrip("\n") for block in blocks if block and block.strip()]


def section_without_subsections(section: str, prefixes: tuple[str, ...]) -> str:
    """指定番号の subsection block を section から除外する。"""
    output: list[str] = []
    skipping = False
    for line in section.split("\n"):
        subsection = SUBSECTION_HEADER_RE.match(line)
        if subsection:
            skipping = subsection.group(1) in prefixes
        elif SECTION_HEADER_RE.match(line):
            skipping = False
        if not skipping:
            output.append(line)
    return "\n".join(output).rstrip("\n")


def create_new_section_4_and_5(content: str) -> str:
    """新セクション 4 と 5 を作成（旧 1.2, 1.3, 2.2 から）。"""
    section_1_2 = subsection_as_new_number(content, "1.2", "4.1")
    section_1_3 = subsection_as_new_number(content, "1.3", "4.2")
    section_2_2 = subsection_as_new_number(content, "2.2", "")

    new_section_4 = f"""---

## 4. Python テスト・アーキテクチャ検証

{section_1_2}

{section_1_3}"""

    new_section_5 = f"""---

## 5. C++ スタイル・ベストプラクティス

{section_2_2.strip()}"""

    return new_section_4 + "\n\n" + new_section_5


def subsection_as_new_number(content: str, old_num: str, new_num: str) -> str:
    """既存 subsection を抽出して番号を更新する。"""
    section = extract_subsection_by_number(content, old_num)
    if not new_num:
        return remove_first_subsection_heading(section, old_num)
    return re.sub(
        rf"^###\s+{re.escape(old_num)}",
        f"### {new_num}",
        section,
        count=1,
        flags=re.MULTILINE,
    )


def extract_subsection_by_number(content: str, subsection_num: str) -> str:
    """`### N.N` の subsection をタイトル非依存で抽出する。"""
    lines = content.split("\n")
    header_idx = find_subsection_header_index(lines, subsection_num)
    end_idx = find_section_end(lines, header_idx, 3)
    return "\n".join(lines[header_idx : end_idx + 1])


def find_subsection_header_index(lines: list[str], subsection_num: str) -> int:
    """指定番号の subsection heading 行を返す。"""
    pattern = re.compile(rf"^###\s+{re.escape(subsection_num)}(?:\s|$)")
    for line_index, line in enumerate(lines):
        if pattern.match(line):
            return line_index
    raise ValueError(f"Subsection not found: {subsection_num}")


def remove_first_subsection_heading(section: str, old_num: str) -> str:
    """先頭 subsection 見出しだけを外す。"""
    lines = section.split("\n")
    if lines and lines[0].startswith(f"### {old_num}"):
        return "\n".join(lines[1:]).lstrip("\n")
    return section


def renumber_existing_section(
    sections: dict[int, str],
    old_num: int,
    new_num: int,
) -> str | None:
    """存在する section を renumber する。"""
    section = sections.get(old_num)
    if section is None:
        return None
    return update_section_numbers(section, old_num, new_num)


def renumber_remaining_sections(sections: dict[int, str]) -> list[str]:
    """old section 8 以降を +2 で renumber する。"""
    remapped: list[str] = []
    for old_num in sorted(num for num in sections if num >= 8):
        remapped.append(update_section_numbers(sections[old_num], old_num, old_num + 2))
    return remapped


def update_section_numbers(content: str, old_num: int, new_num: int) -> str:
    """セクション内の番号を更新。"""
    content = content.replace(f"## {old_num}.", f"## {new_num}.", 1)
    content = re.sub(
        rf"^### {re.escape(str(old_num))}\.",
        f"### {new_num}.",
        content,
        flags=re.MULTILINE,
    )
    for subsection_num in range(10):
        content = content.replace(
            f"### {old_num}.{subsection_num}.",
            f"### {new_num}.{subsection_num}.",
        )
    return content


def build_parser() -> argparse.ArgumentParser:
    """CLI parser を作る。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=".code-review-SKILL.md",
        help="Restructure target markdown file. Default: .code-review-SKILL.md",
    )
    return parser


def main() -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args()
    file_path = Path(args.path)

    print(f"読み込み中: {file_path}")
    content = read_skill_file(file_path)

    print("セクション再構成中...")
    new_content = restructure_sections(content)

    print(f"書き込み中: {file_path}")
    write_skill_file(file_path, new_content)

    print("完了")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
