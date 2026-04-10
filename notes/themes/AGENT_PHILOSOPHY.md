# Agent Philosophy

この file は、agent の作業哲学、対話から得た学習、repo-wide な判断原則を逐次追記する append-first note です。
`AGENTS.md` や workflow 正本へ入れる前の観測をここへ集め、十分に安定した項目だけを periodic sweep で昇格させます。

## Use

- user preference は `notes/themes/USER_PREFERENCES.md` に残します。
- agent 自身の作業哲学、判断癖、対話上の再発防止、作業後 retrospective はこの note に残します。
- 会話ログを raw に貼らず、1 observation 1 entry の短い抽象化として残します。
- source、evidence、scope、confidence を明示し、推測と確定事項を混ぜません。
- stable な運用 rule へ昇格するまでは、`AGENTS.md` や runtime entrypoint へ直接書きません。

## Stable Philosophy

- まだなし

## Working Principles

- 2026-04-10 | work-principle | requirements は current request、durable user preference、repo/code precedent、domain/external constraint、unknown/open question を source bucket として分離してから planning へ渡す
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to make requirements definition more careful beyond user traits from prior logs

- 2026-04-10 | work-principle | identifier naming は worker の自由裁量にせず、既存 precedent または詳細設計の naming plan に結び付ける
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request about whether variable names can be decided freely

- 2026-04-10 | work-principle | task 開始時に clean worktree なら agent-canon ensure-latest を実行し、dirty で止まる場合は理由を明示して commit / stash 後に再実行する
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to keep agent-canon updated every time

## Interaction Observations

- 2026-04-10 | interaction-observation | agent personality は自由作文ではなく、source/evidence/scope/confidence を持つ作業哲学として repo に蓄積する
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: 2026-04-10 request about agent knowledge/philosophy/personality formation

## Task Retrospectives

- まだなし

## Promotion Candidates

- まだなし

## Open Questions

- まだなし
