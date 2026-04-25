# Guardrail Notes
<!--
@dependency-start
@dependency-end
-->


このディレクトリは、repo-wide に何度も読み返す禁止事項と anti-pattern の補助 note を置く場所です。

## Must Read

- [engineering_avoidances.md](/mnt/l/workspace/project_template/notes/guardrails/engineering_avoidances.md)

## 使う場面

- 新しい worktree を切った直後
- 既存 worktree を引き継ぐ直前
- 新しい実装を足す前
- 設計拡張や workflow 改造を始める前

## ルール

- `documents/` の正本規約を置き換えるものではなく、繰り返し参照する禁止事項の補助 note として使います。
- 具体的な再発防止は `notes/failures/` へ、repo-wide な避けることはここへ置きます。
- 実装上の avoid と運用上の avoid は混ぜすぎず、検索しやすい単位で分けます。
