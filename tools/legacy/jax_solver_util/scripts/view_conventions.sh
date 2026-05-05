#!/bin/bash
# @dependency-start
# upstream implementation README.md directory index and local context contract
# @dependency-end
# ═══════════════════════════════════════════════════════════════════════════
# 規約ファイルの表示スクリプト
# 使用方法: ./scripts/view_conventions.sh [search-term]
# ═══════════════════════════════════════════════════════════════════════════

set -e

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE_ROOT"

clear

echo "════════════════════════════════════════════════════════════════════════"
echo "プロジェクト規約 - 一覧表示"
echo "════════════════════════════════════════════════════════════════════════"
echo ""

# Python規約のカウント
PYTHON_COUNT=$(find documents/conventions/python -name "*.md" 2>/dev/null | wc -l)
COMMON_COUNT=$(find documents/conventions/common -name "*.md" 2>/dev/null | wc -l)
PROJECT_COUNT=$(find documents/conventions/project -name "*.md" 2>/dev/null | wc -l)

echo "📚 規約構成:"
echo "  • Python規約: $PYTHON_COUNT 章"
echo "  • 共通規約: $COMMON_COUNT 章"
echo "  • プロジェクト固有規約: $PROJECT_COUNT 章"
echo ""
echo "─────────────────────────────────────────────────────────────────────────"
echo ""

# Python規約
echo "【Python規約】 ($PYTHON_COUNT章)"
echo ""
find documents/conventions/python -name "*.md" | sort | nl | while read num file; do
    title=$(head -1 "$file" | sed 's/^# //' | sed 's/# //')
    echo "  $num. $title"
    echo "     📄 $(basename "$file")"
done

echo ""
echo "─────────────────────────────────────────────────────────────────────────"
echo ""

# Common規約
echo "【共通規約】 ($COMMON_COUNT章)"
echo ""
find documents/conventions/common -name "*.md" | sort | nl | while read num file; do
    title=$(head -1 "$file" | sed 's/^# //' | sed 's/# //')
    echo "  $num. $title"
    echo "     📄 $(basename "$file")"
done

echo ""
echo "─────────────────────────────────────────────────────────────────────────"
echo ""

# Project規約
if [ $PROJECT_COUNT -gt 0 ]; then
    echo "【プロジェクト固有規約】 ($PROJECT_COUNT)"
    echo ""
    find documents/conventions/project -name "*.md" | sort | nl | while read num file; do
        title=$(head -1 "$file" | sed 's/^# //' | sed 's/# //')
        echo "  $num. $title"
        echo "     📄 $(basename "$file")"
    done
    echo ""
fi

echo "════════════════════════════════════════════════════════════════════════"
echo ""
echo "📖 特定の規約を確認:"
echo ""
echo "  Python規約 (e.g., 型アノテーション):"
echo "    less documents/conventions/python/04_type_annotations.md"
echo ""
echo "  共通規約 (e.g., Markdown):"
echo "    less documents/conventions/common/05_docs.md"
echo ""
echo "  コーディング規則 (プロジェクト全体):"
echo "    less documents/coding-conventions-project.md"
echo ""
echo "════════════════════════════════════════════════════════════════════════"
