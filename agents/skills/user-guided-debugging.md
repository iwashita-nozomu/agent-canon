# user-guided-debugging
<!--
@dependency-start
contract skill
responsibility Documents user-guided-debugging for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../ROOT_AGENTS.md shared parent-executed debugging boundary
upstream design ../../documents/design/runtime-debugging.md conditional standard diagnostic selection
downstream implementation ../../.codex/personal/skills/user-guided-debugging/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose

ユーザーが明示したときだけ、debug / repair / refactor を 1 件ずつ進め、各修正の前後でユーザーが設計判断を差し込めるようにします。親エージェントが直接担当し、サブエージェントは使いません。対話の進め方と、合意した成果・検証を完了する責任を分けます。

## Use When

- user が「1 個ずつ」「一緒にデバッグ」「ユーザー主導リファクタ」「直す前に問題点を出して」などを明示した
- finding、test failure、runtime failure、hook failure を順番に修正する
- 修正方針にユーザーの設計判断が入る可能性が高い

## Execution Ownership

親エージェントが調査・原因特定・修正・合意した成果に必要な検証・結果共有を直接担当します。
read-only の探索やレビューも含め、新規起動・既存 child の再利用・並行する別調査へ委譲しません。
ユーザーの判断と観測が次の操作を決める直列ループなので、対話 context と規定の実行経路を分断しません。
[共通境界](../../ROOT_AGENTS.md#task-entry) が一般の orchestrator-only / child-handoff 規定に優先します。
親が直接実行するという選択は、patch ごとに検証権限を失うことを意味しません。

## Diagnostic selection

実行時の観測が必要になった時点で、[標準診断の選択表](../../documents/design/runtime-debugging.md#tool-selection)
から症状に対応する節だけ読みます。source / 既存ログで足りるなら追加ツールを起動しません。
診断でも規定 runner と下記 cadence を維持し、ツールが存在するだけで無関係な検証・
同じ失敗の再試行を追加しません。実行範囲は現在の合意と変更契約から選びます。

## Core Loop

1. 現在の合意から、次に直す対象を 1 件と、その完了に必要な検証を選ぶ。最初の依頼と後続の明示変更を引き継ぎ、patch・質問への回答・再開だけでは合意を作り直さない。
1. 編集前に、チャットで対象 object、問題点、根拠、修復面を短く提示してから、その問題を親が修正する。
1. 根本原因が別 object に移ったら、編集前に新しい問題点を提示する。
1. 修正後は、合意した修正の完了に必要な test、lint、docs check 等を規定経路で実行する。patch 前に成立した同じ作業の検証合意も有効であり、patch 後の再指示を着手条件にしない。ユーザーが「修正だけ、テストは待つ」等を明示している間は、その限定された操作を保留する。
1. validation が fail した場合は、次の edit 方針を示す前に
   `failing_contract`、`observation_level`、`cause_classification`、
   `intent_preservation`、`evidence` を提示する。`intent_preservation` は
   same-intent repair / escalation route を示す。合意した意図を維持する原因修正と、
   その修正で前提が変わった検証を続ける。pass 目的の単純化、revert、
   intended behavior / test 削除、oracle weakening、validation downscope を
   失敗解消の代用にしない。
1. 実際の修正・検証結果を報告し、合意した成果に残る対象へ進む。必須検証が進行中なら同じ実行の結果を確認し、重複起動しない。局所検証の成功だけで、まだ必要な owner-selected 検証を完了扱いにしない。実行不能な検証は理由・観測・次の操作とともに未実施とし、独立して進められる範囲は続ける。

## Boundary

- オーケストレーションの子エージェントも適用条件と実行責任を読みます。読込と cadence の適用を分け、ユーザー主導 cadence はユーザー明示時だけ有効にします。
- 通常のオーケストレーションは、選択済み workflow とその検証権限で進めます。
- 「完成させて」「全部直して」「テストまで」等の後続指示は、同じ作業の成果範囲・保留の解除として意味から反映します。特定の切替語や同じ承認の再提出を要求しません。親による直接実行は、ユーザーが委譲方式の変更を明示するまで維持します。
- ユーザーの質問には答え、その質問自体が作業停止・範囲変更を意味しなければ未完了の合意へ戻ります。明示された停止・検証保留、安全性・権限の境界は引き続き守ります。
- validationの種類と範囲はこのcadenceから追加しません。現在のtaskで合意済みのvalidationを保持し、明示された停止境界だけがその実行を止めます。
- 難易度・複数ファイル・検証失敗を理由に自律 wave へ切り替えません。ユーザーが自律作業への切替を明示した場合だけ通常の routing に戻し、大規模 repair は [refactor-loop](refactor-loop.md) の責務とします。
- report や artifact 作成が必要なら `tool-finding-report` / `report-writing` を併用します。
