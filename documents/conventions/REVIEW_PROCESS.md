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

## 禁止事項

- dated な completion summary や古い review 文書を `documents/` や repo root に残すことを禁止します。
- current tree head 以外の design truth や implementation truth を tracked tree に残すことを禁止します。parallel design doc、implementation copy、snapshot tree、backup file は削除対象です。

## Findings の扱い

findings は少なくとも次に分けます。

- `fix now`
  - この変更で直さないと回帰や矛盾が残るもの
  - 修正後は、selected owning gate の focused rerun を実行する
  - review reject / requested-change への応答が、同じ user request と design
    intent を保つ修正や再設計ではなく、blanket revert、discard、または
    completion scope の縮小になっているもの
  - 旧実装、移行用の別経路、temporary alternate route、copied implementation、古い説明のままの README / guide / workflow を残すもの
  - runtime success はあるが数式、仕様、protocol、reader path と実装 / 文書が一致していないもの
  - 設計上の問題を `design_issue_blocker` として戻さず、local fallback、wrapper、helper、分岐、互換 route、test 緩和、docs 上書きで吸収したもの
  - validation failure を通すために intended behavior/test を削る、oracle を弱める、
    required validation を downscope する、または approved intent 変更前の
    escalation を省くもの
- `follow-up`
  - 今回の受け入れを阻害しないが、後続で管理すべきもの
- `delete-ok`
  - stale asset や重複導線のように安全に削除できるもの
  - non-canonical design doc、implementation copy、dated snapshot のように tree head 以外の truth surface を増やすもの

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
