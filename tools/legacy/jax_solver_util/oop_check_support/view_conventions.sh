#!/bin/bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design README.md legacy OOP check support policy
# @dependency-end
# ═══════════════════════════════════════════════════════════════════════════
# 規約ファイルの表示スクリプト
# 使用方法: ./scripts/view_conventions.sh [search-term]
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

resolve_repo_root() {
    local start_dir="${1:-$PWD}"
    if git -C "$start_dir" rev-parse --show-toplevel >/dev/null 2>&1; then
        git -C "$start_dir" rev-parse --show-toplevel
        return
    fi
    cd "$start_dir"
    pwd
}

resolve_conventions_root() {
    local repo_root="$1"
    for candidate in \
        "$repo_root/documents/conventions" \
        "$repo_root/vendor/agent-canon/documents/conventions"; do
        if has_convention_files "$candidate"; then
            printf '%s\n' "$candidate"
            return
        fi
    done
    echo "conventions directory not found under $repo_root" >&2
    exit 1
}

has_convention_files() {
    local candidate="$1"
    [ -d "$candidate/python" ] || return 1
    [ -d "$candidate/common" ] || return 1
    [ -n "$(find "$candidate/python" "$candidate/common" -name "*.md" -print -quit 2>/dev/null)" ]
}

count_markdown_files() {
    local path="$1"
    if [ ! -d "$path" ]; then
        printf '0\n'
        return
    fi
    find "$path" -name "*.md" 2>/dev/null | wc -l
}

markdown_title() {
    local file="$1"
    awk '/^# / { sub(/^# /, ""); print; exit }' "$file"
}

WORKSPACE_ROOT="$(resolve_repo_root "${1:-$PWD}")"
CONVENTIONS_ROOT="$(resolve_conventions_root "$WORKSPACE_ROOT")"

if [ -t 1 ]; then
    clear
fi

echo "════════════════════════════════════════════════════════════════════════"
echo "プロジェクト規約 - 一覧表示"
echo "════════════════════════════════════════════════════════════════════════"
echo ""

# Python規約のカウント
PYTHON_COUNT=$(count_markdown_files "$CONVENTIONS_ROOT/python")
COMMON_COUNT=$(count_markdown_files "$CONVENTIONS_ROOT/common")
PROJECT_COUNT=$(count_markdown_files "$CONVENTIONS_ROOT/project")

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
find "$CONVENTIONS_ROOT/python" -name "*.md" | sort | nl | while read -r num file; do
    title=$(markdown_title "$file")
    echo "  $num. $title"
    echo "     📄 $(basename "$file")"
done

echo ""
echo "─────────────────────────────────────────────────────────────────────────"
echo ""

# Common規約
echo "【共通規約】 ($COMMON_COUNT章)"
echo ""
find "$CONVENTIONS_ROOT/common" -name "*.md" | sort | nl | while read -r num file; do
    title=$(markdown_title "$file")
    echo "  $num. $title"
    echo "     📄 $(basename "$file")"
done

echo ""
echo "─────────────────────────────────────────────────────────────────────────"
echo ""

# Project規約
if [ "$PROJECT_COUNT" -gt 0 ]; then
    echo "【プロジェクト固有規約】 ($PROJECT_COUNT)"
    echo ""
    find "$CONVENTIONS_ROOT/project" -name "*.md" | sort | nl | while read -r num file; do
        title=$(markdown_title "$file")
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
echo "    less $CONVENTIONS_ROOT/python/04_type_annotations.md"
echo ""
echo "  共通規約 (e.g., Markdown):"
echo "    less $CONVENTIONS_ROOT/common/05_docs.md"
echo ""
echo "  コーディング規則 (プロジェクト全体):"
echo "    less ${CONVENTIONS_ROOT%/conventions}/coding-conventions-project.md"
echo ""
echo "════════════════════════════════════════════════════════════════════════"
