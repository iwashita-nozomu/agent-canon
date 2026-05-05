#!/bin/bash
# @dependency-start
# responsibility Preserves imported jax_solver_util legacy script for provenance.
# upstream design ../README.md legacy import policy
# @dependency-end
# ═══════════════════════════════════════════════════════════════════════════
# プロジェクト規約・ワークツリー統合ガイド
# ═══════════════════════════════════════════════════════════════════════════

set -e

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE_ROOT"

clear

cat << 'EOF'
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║          JAX Utils - 作業用ワークツリーセットアップガイド                  ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝

📋 目的: 規約に従った新しい作業ブランチとワークツリーを作成します

════════════════════════════════════════════════════════════════════════════

【ステップ1】 規約の確認

  ✓ 実行コマンド:
    bash scripts/view_conventions.sh

  ✓ 主要規約:
    - 型アノテーション (04_type_annotations.md)
    - 責務分離 (09_file_roles.md)
    - ニューラルネット (18_neuralnetwork.md)
    - ドキュメント (common/05_docs.md)

════════════════════════════════════════════════════════════════════════════

【ステップ2】 ワークツリーの作成

  ✓ 実行コマンド:
    bash scripts/worktree_start.sh <branch-name> [worktree-path]

  ✓ 例:
    bash scripts/worktree_start.sh work/protocol-improvements-20260330
    
    bash scripts/worktree_start.sh results/smolyak-validation-20260328 \
      .worktrees/results-smolyak-validation-20260328

  ✓ 自動作成される内容:
    • ブランチ: 指定した branch 名をそのまま使用
    • ワークツリー: 既定では .worktrees/<branch-name を /→- に置換>
      例: work/my-feature-20260330 → .worktrees/work-my-feature-20260330
    • kickoff summary: required references / checks / next skill を表示

════════════════════════════════════════════════════════════════════════════

【ステップ3】 ワークツリーで作業開始

  cd .worktrees/work-feature-xyz-20260330
  
  # current worktree の kickoff summary 再確認
  bash scripts/worktree_start.sh --current

  # 規約確認
  bash scripts/view_conventions.sh

════════════════════════════════════════════════════════════════════════════

【ステップ4】 作業完了後のプッシュ

  git add -A
  git commit -m "category: 説明"
  bash scripts/push_origin.sh

  📌 コミットメッセージ例:
    • feat: 新機能追加
    • fix: バグ修正
    • docs: ドキュメント更新
    • refactor: コード改善
    • test: テスト追加

════════════════════════════════════════════════════════════════════════════

【ステップ5】 ワークツリーのクリーンアップ

  # ワークツリーを削除
  git worktree remove .worktrees/work-feature-xyz-20260330

  # ローカルブランチを削除（マージ後）
  git branch -d <branch-name>

════════════════════════════════════════════════════════════════════════════

🔍 ワークツリー・ブランチの確認

  # 現在のワークツリー一覧
  git worktree list

  # ブランチ一覧
  git branch -v

  # リモートブランチ一覧
  git branch -r

════════════════════════════════════════════════════════════════════════════

📚 规约キーワードマップ

  型安全性:
    ← 04_type_annotations.md
    ← 07_type_checker.md

  コード構成:
    ← 09_file_roles.md
    ← 10_dependencies.md

  命名规則:
    ← 11_naming.md (Python)
    ← 02_naming.md (共通)

  テスト・実装:
    ← documents/coding-conventions-project.md

  ドキュメント:
    ← 05_docs.md (共通)

════════════════════════════════════════════════════════════════════════════

✨ 完全なワークフロー例

  # 1. 規約確認
  bash scripts/view_conventions.sh

  # 2. ワークツリー作成
  bash scripts/worktree_start.sh work/feature-xyz-20260330

  # 3. ワークツリーに移動
  cd .worktrees/work-feature-xyz-20260330

  # 4. 作業実施
  # ... ファイル編集 ...

  # 5. テスト・確認
  make ci

  # 6. コミット
  git add -A
  git commit -m "feat: 新機能XYZ実装完了"

  # 7. プッシュ
  bash scripts/push_origin.sh

  # 8. クリーンアップ（マージ後）
  git worktree remove .worktrees/work-feature-xyz-20260330
  git branch -d work/feature-xyz-20260330

════════════════════════════════════════════════════════════════════════════

EOF
 
# ブランチとワークツリーの状況を表示
echo "【現在の状況】"
echo ""
echo "ブランチ:"
git branch -v | head -5
echo ""
echo "ワークツリー:"
git worktree list | head -5
echo ""
