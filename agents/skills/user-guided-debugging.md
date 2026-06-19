# user-guided-debugging
<!--
@dependency-start
contract skill
responsibility Documents user-guided-debugging for this repository.
upstream design ../canonical/skills.md skill canon registry
downstream implementation ../../.agents/skills/user-guided-debugging/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->


## Purpose

ユーザーが明示したときだけ、debug / repair を 1 件ずつ進め、各修正の前後でユーザーが設計判断を差し込めるようにします。

## Use When

- user が「1 個ずつ」「一緒にデバッグ」「直す前に問題点を出して」などを明示した
- finding、test failure、runtime failure、hook failure を順番に修正する
- 修正方針にユーザーの設計判断が入る可能性が高い

## Core Loop

1. 次に直す対象を 1 件選ぶ。
1. 編集前に、チャットで対象 object、問題点、根拠、修復面を短く提示する。
1. 問題点を提示する前に patch しない。
1. 根本原因が別 object に移ったら、編集前に新しい問題点を提示する。
1. 修正後に局所 validation を走らせる。
1. 結果を報告し、次の concrete issue を提示する。

## Boundary

- この skill はユーザー明示時だけ使います。
- `agent-orchestration` の既定 routing には入れません。
- 大規模 repair wave 自体は `refactor-loop` の責務です。この skill はその中の user-visible debug cadence を規定します。
- report や artifact 作成が必要なら `tool-finding-report` / `report-writing` を併用します。
