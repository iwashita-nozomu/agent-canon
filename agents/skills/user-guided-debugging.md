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

1. 現在の合意から次の対象を選び、最初の依頼、後続の明示変更、停止や保留を引き継ぐ。具体的なコード変更が指定されていればその変更を実装する。原因診断を求められた場合は、まず対象コード、差分、既存契約、観測ログから原因を確かめる。そこから判断できない具体的な事実が残る場合だけ、その事実を確かめる最小の参照先を示す。推測だけでコードを変えず、調査範囲も暗黙に広げない。
1. 編集前に、対象、観測した問題と根拠、修復内容を短く示す。調査で原因や責務が別 object に移ったら、編集前に更新内容を示す。
1. 合意した修正を実装する。検証の実行だけで依頼されたコード修正を置き換えず、検証環境の障害だけを理由に修正可能なコードを放置しない。
1. 検証はこの依頼でユーザーが明示した、または既に明示的に合意した場合に実行する。「修正」や「完成」だけから検証を追加しない。ユーザーが検証を保留した間は未検証として扱い、結果について推論しない。
1. 実施した検証が失敗した場合は、その観測から変更コードと原因を調べ、意図を保つ修正を行う。pass のために挙動や test を弱めたり、原因を隠したりしない。実際の検証で障害が観測され、得られた事実が支える場合に限って代替案を示し、未実行の案を検証済みと扱わない。
1. 実際の変更と、実行した場合は検証結果を報告してから次の対象へ進む。未実行の検証について pass、fail、環境障害や代替案を推測して報告しない。

## Boundary

- オーケストレーションの子エージェントも適用条件と実行責任を読みます。読込と cadence の適用を分け、ユーザー主導 cadence はユーザー明示時だけ有効にします。
- 通常のオーケストレーションは、選択済み workflow とその検証権限で進めます。
- 「完成させて」「全部直して」「テストまで」等の後続指示は、同じ作業の成果範囲・保留の解除として意味から反映します。特定の切替語や同じ承認の再提出を要求しません。親による直接実行は、ユーザーが委譲方式の変更を明示するまで維持します。
- ユーザーの質問には答え、その質問自体が作業停止・範囲変更を意味しなければ未完了の合意へ戻ります。明示された停止・検証保留、安全性・権限の境界は引き続き守ります。
- validationの種類と範囲はこのcadenceから追加しません。現在のtaskで明示的に合意済みのvalidationを保持し、明示された停止境界だけがその実行を止めます。
- 難易度・複数ファイル・検証失敗を理由に自律 wave へ切り替えません。ユーザーが自律作業への切替を明示した場合だけ通常の routing に戻し、大規模 repair は [refactor-loop](refactor-loop.md) の責務とします。
- report や artifact 作成が必要なら `tool-finding-report` / `report-writing` を併用します。
