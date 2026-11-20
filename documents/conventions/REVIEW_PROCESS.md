<!--
@dependency-start
contract reference
responsibility Documents レビュー手順とポリシー for this repository.
upstream design README.md durable document index
upstream design ../runtime/private-feedback-knowledge.md GitHub Issue authority and private packet policy
upstream design ../runtime/runtime-profiles-and-check-matrix.json validation profile taxonomy owner
downstream design ../design/algorithm-implementation-boundary.md algorithm math-to-code boundary policy
@dependency-end
-->

# レビュー手順とポリシー

この文書は、コード、文書、workflow、環境設定の変更を main-first 運用で安全に閉じるための review 手順を定めます。
現行の agent canon と skill canon に合わせて、必要な review family と実装判断を定めます。

## この文書の読み方

この文書は、変更 scope と受け入れ条件、review family の選び方、validation、finding disposition、merge 条件を説明します。レビュー結果は現在の Codex conversation と Git / PR / Issue の文脈で扱います。

## 適用範囲

- 既定の統合先は `main` です。
- レビューが必要な変更では、コード、テスト、文書、必要なら環境設定をまとめて確認します。
- repo-wide な workflow 改造、agent system の変更、研究系の完了判定にも適用します。

## 変更前に確認すること

合意した範囲と受け入れ条件を把握します。レビューと検証は、変更した性質と
残る不確実性に合わせて選びます。

## Review Family の選び方

変更の根拠と回帰は [change-review](../../agents/skills/change-review.md) で扱います。
言語、設計、文書、研究の独立した判断が必要な場合は対応するレビューを選びます。
C++ のビルドとテストは、変更対象を所有するプロジェクトの
[ビルド契約](../design/cpp-build-layout.md) に従います。

## Decision ownership and selected reruns

レビュー結果は、判断と根拠を該当箇所と共に示します。修正で根拠が変わった範囲を
確認し直します。合意した結果や範囲を変える判断はユーザーに確認します。

## 実行チェック

変更した性質を確かめる方法は
[検証の指針](../../agents/canonical/CODEX_COMPLETION.md#6-validation) と対象の契約から選びます。
文書の体裁は [md-style-check](../../agents/skills/md-style-check.md)、
読みやすさと根拠のつながりは対象本文で確かめます。

## Review Flow

要求と最終差分を照合し、保証を変えた箇所、参照の削除漏れ、根拠の不足を確認します。
数式や仕様に基づく変更は [実装境界](../design/algorithm-implementation-boundary.md) と照合します。
結果が期待と違う場合や未検証の場合は
[テストの責務](coding-conventions-testing.md#3-unit-test-contract) に従い、
前提、入力、実装、判定のどこが原因かを調べます。

## マージ条件

合意した成果、必要な検証と選択したレビューの結果を統合する差分に照らします。
統合と公開は [PRの手順](../../agents/skills/pr-processing.md#base-integration-and-merge-readiness)
と [ブランチ運用](../operations/BRANCH_SCOPE.md) に従います。

## エビデンス保存

- project-wide な分析や再利用する長文 report は `reports/` に置きます。
- 一時メモや cross-run の補助知見は `documents/notes/` に置きます。
- review context は current Codex conversation と Git / PR state で扱い、experiment、Eval、hook log、user-facing report の output は各 existing owner に置きます。

## Findings の扱い

- `fix now` は、合意した成果を損なう回帰、矛盾、検証不足です。影響した根拠を確認します。
- `follow-up` は、今回の受け入れ範囲とは独立して扱う課題です。
- `delete-ok` は、用途を確認した結果、削除できる旧経路や重複資産です。

## Review Finding Issue Routing

Current diff で解決する finding は selected review gate に戻します。後続の作業として
durable に残す defect は既存または新規の repository-qualified GitHub Issue へつなぎ、
Issue を唯一の durable authority とします。

Durable operational defect は GitHub Issue を正本にします。オフライン時は
private `agent-canon-log/feedback/issue-packets/pending/` にlocator/digestだけを置き、
host adapterが `agent-canon issue-sync --sync-pending --repo <owner>/<repo>`
で公開し、URL/number/title/body/stateをreadbackしてpacketを解決します。

## 関連正本

- [agents/TASK_WORKFLOWS.md](../../agents/TASK_WORKFLOWS.md)
- [agents/canonical/ARTIFACT_PLACEMENT.md](../../agents/canonical/ARTIFACT_PLACEMENT.md)
- [agents/skills/README.md](../../agents/skills/README.md)
- [agents/workflows/workflow-references.md](../../agents/workflows/workflow-references.md)
