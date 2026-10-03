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

ユーザーが明示したときだけ、debug / repair / refactor を 1 件ずつ進め、各修正の前後でユーザーが設計判断を差し込めるようにします。親エージェントが直接担当し、サブエージェントは使いません。

## Use When

- user が「1 個ずつ」「一緒にデバッグ」「ユーザー主導リファクタ」「直す前に問題点を出して」などを明示した
- finding、test failure、runtime failure、hook failure を順番に修正する
- 修正方針にユーザーの設計判断が入る可能性が高い

## Execution Ownership

親エージェントが調査・原因特定・修正・ユーザーが指示した検証・結果共有を直接担当します。
read-only の探索やレビューも含め、新規起動・既存 child の再利用・並行する別調査へ委譲しません。
ユーザーの判断と観測が次の操作を決める直列ループなので、対話 context と規定の実行経路を分断しません。
[共通境界](../../ROOT_AGENTS.md#task-entry) が一般の orchestrator-only / child-handoff 規定に優先します。

## Diagnostic selection

実行時の観測が必要になった時点で、[標準診断の選択表](../../documents/design/runtime-debugging.md#tool-selection)
から症状に対応する節だけ読みます。source / 既存ログで足りるなら追加ツールを起動しません。
診断でも規定 runner と下記 cadence を維持し、ツールの提供を追加実行・再実行や
修正後検証の許可として扱いません。

## Core Loop

1. 次に直す対象を 1 件選ぶ。
1. 編集前に、チャットで対象 object、問題点、根拠、修復面を短く提示してから、その問題を親が修正する。
1. 根本原因が別 object に移ったら、編集前に新しい問題点を提示する。
1. この cadence では、修正後に test、smoke run、lint、docs check、benchmark、その他 validation command を実行しない。patch 後にユーザーが明示した場合だけ実行する。
1. patch 後にユーザーが validation 実行を明示し、その validation が fail した場合は、次の edit 方針を示す前に
   `failing_contract`、`observation_level`、`cause_classification`、
   `intent_preservation`、`evidence` を提示する。`intent_preservation` は
   same-intent repair / escalation route を示す。pass 目的の単純化、revert、
   intended behavior / test 削除、oracle weakening、validation downscope は、この
   5-field 分類なしに行わない。
1. patch 結果を報告し、validation を省略した場合は未実行と明記して、次の concrete issue を提示する。

## Boundary

- この skill はユーザー明示時だけ使います。
- `agent-orchestration` の既定 routing には入れません。
- validation 実行はこの cadence の既定動作ではありません。必要な validation route は提示できますが、実行はユーザーの明示指示後に限ります。
- 難易度・複数ファイル・検証失敗を理由に自律 wave へ切り替えません。ユーザーが自律作業への切替を明示した場合だけ通常の routing に戻し、大規模 repair は [refactor-loop](refactor-loop.md) の責務とします。
- report や artifact 作成が必要なら `tool-finding-report` / `report-writing` を併用します。
