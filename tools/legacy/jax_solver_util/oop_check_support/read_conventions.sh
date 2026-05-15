#!/bin/bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design README.md legacy OOP check support policy
# @dependency-end
# 規約ファイルを整理して表示するスクリプト

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

repo_root="$(resolve_repo_root "${1:-$PWD}")"
conventions_root="$(resolve_conventions_root "$repo_root")"

echo "════════════════════════════════════════════════════════════════════════════"
echo "プロジェクト規約一覧"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""

# Python規約
echo "【Python規約】"
find "$conventions_root/python" -name "*.md" | sort | while IFS= read -r file; do
    num=$(basename "$file" | cut -d_ -f1)
    title=$(basename "$file" .md | sed 's/^[0-9]*_//' | tr '_' ' ')
    echo "  ✓ $num: $title"
done
echo ""

# Common規約
echo "【共通規約】"
find "$conventions_root/common" -name "*.md" | sort | while IFS= read -r file; do
    num=$(basename "$file" | cut -d_ -f1)
    title=$(basename "$file" .md | sed 's/^[0-9]*_//' | tr '_' ' ')
    echo "  ✓ $num: $title"
done
echo ""

# プロジェクト固有規約
echo "【プロジェクト固有規約】"
if [ -d "$conventions_root/project" ]; then
    find "$conventions_root/project" -maxdepth 1 -name "*.md" -printf '%f\n' | sort | while IFS= read -r file; do
        echo "  ✓ $file"
    done
fi
echo ""

echo "全規約ファイルを確認しました"
echo "════════════════════════════════════════════════════════════════════════════"
