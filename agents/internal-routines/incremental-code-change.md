# 依存順に揃えるコード移行

<!--
@dependency-start
contract workflow
responsibility Connects bounded coverage traversal, incremental repair, evidence invalidation, and dependency-complete commit boundaries without a second workflow engine.
downstream design ../skills/code-cleanup.md consumes the shared asset universe and streaming semantic cleanup
upstream design ../skills/dependency-analysis.md owns dependency discovery and the Change Impact Packet
upstream design ../skills/refactor-loop.md owns behavior-preserving repair batches and selected validation
upstream design ../../documents/operations/BRANCH_SCOPE.md owns dependency-complete commit planning and exact-tree validation
upstream design ../skills/change-review.md owns independent review and focused rechecks
upstream design ../COMMUNICATION_PROTOCOL.md owns bounded handoff and context reuse
upstream design ../skills/tokens.md owns measured token-efficiency claims
upstream design github-status-lifecycle.md owns Issue and PR status readback
downstream design README.md indexes this internal workflow
@dependency-end
-->

## 選択と責務

対象をまたぐ修正・置換では、既存の `dependency-analysis`、`refactor-loop`、
`change-review` を使います。実行順は
[CODEX_IMPLEMENTATION](../canonical/CODEX_IMPLEMENTATION.md#5-implementation) に従います。

## 対象と修正方針

依頼、現在の差分、既存契約から、何をどう変更・削除するかを最初に決めます。
提供側の API、必要な利用側、登録・設定、生成元、テストと文書まで、変更に必要な
範囲を確認します。依存する変更を一組にし、修正単位と順序を現在の会話で共有します。

既存の機能・API を組み合わせ、具体的な不足だけをその owner で補います。
未解決の前提は編集前に調べます。無関係な全 repository の再調査は追加しません。
Git の差分と path 一覧を必要に応じて参照し、作業台帳、読了表、状態集合、単位/SHA表は
作成・更新しません。

## 実装と旧コードの整理

決めた単位を依存順に実装し、必要な利用側と設定を一緒に揃えます。行・helper・
ファイルごとの修正を独立した検証段階にしません。

予定した実装が揃ったら、差分全体と利用側を確認し、旧実装、参照、専用補助、
不要な wrapper、重複設定、生成物の削除漏れを修正します。
意図した削除は [integration](../skills/integration.md) の削除優先で統合し、
古い branch の編集によって復活させません。

## 最終検証と公開

旧コードと参照の整理まで終えた最終状態を整形し、変更契約に必要な検証をまとめて
実行します。commit ごと、編集途中、移行の各段階のためだけのテストは要求しません。
検証済み source と実際の結果を報告し、未実施や失敗を成功とは扱いません。
同じ根拠が有効な検証を繰り返しません。

commit / push / merge は [BRANCH_SCOPE](../../documents/operations/BRANCH_SCOPE.md) に従います。
小さな commit と、最終状態をまとめて検証することは両立します。

## 引継ぎ

未完了の目的、必要な契約、変更方針、残る操作を会話または native handoff へ渡します。
既存の source、差分、実行結果を直接使い、進捗ファイルや管理表を別に維持しません。
トークンや実行量の改善を主張するときは、実測結果に基づきます。
