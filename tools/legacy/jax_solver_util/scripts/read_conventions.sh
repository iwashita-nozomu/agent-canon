#!/bin/bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end
# 規約ファイルを整理して表示するスクリプト

cd /workspace

echo "════════════════════════════════════════════════════════════════════════════"
echo "プロジェクト規約一覧"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""

# Python規約
echo "【Python規約】"
find documents/conventions/python -name "*.md" | sort | while read file; do
    num=$(basename "$file" | cut -d_ -f1)
    title=$(basename "$file" .md | sed 's/^[0-9]*_//' | tr '_' ' ')
    echo "  ✓ $num: $title"
done
echo ""

# Common規約
echo "【共通規約】"
find documents/conventions/common -name "*.md" | sort | while read file; do
    num=$(basename "$file" | cut -d_ -f1)
    title=$(basename "$file" .md | sed 's/^[0-9]*_//' | tr '_' ' ')
    echo "  ✓ $num: $title"
done
echo ""

# プロジェクト固有規約
echo "【プロジェクト固有規約】"
ls -1 documents/conventions/project/ 2>/dev/null | grep "\.md$" | while read file; do
    echo "  ✓ $file"
done
echo ""

echo "全規約ファイルを確認しました"
echo "════════════════════════════════════════════════════════════════════════════"
