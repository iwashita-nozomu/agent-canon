# Agent Philosophy

この file は、agent の作業哲学、対話から得た学習、repo-wide な判断原則を逐次追記する append-first note です。
`AGENTS.md` や workflow 正本へ入れる前の観測をここへ集め、十分に安定した項目だけを periodic sweep で昇格させます。

## Use

- user preference は `memory/USER_PREFERENCES.md` に残します。
- agent 自身の作業哲学、判断癖、対話上の再発防止、作業後 retrospective はこの note に残します。
- 会話ログを raw に貼らず、1 observation 1 entry の短い抽象化として残します。
- source、evidence、scope、confidence を明示し、推測と確定事項を混ぜません。
- stable な運用 rule へ昇格するまでは、`AGENTS.md` や runtime entrypoint へ直接書きません。
- shared canon の `memory/` を正本にし、template 側では runtime view を使います。

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

- 2026-04-10 | work-principle | waterfall workflow は最終 closeout だけでなく、requirements、plan、design、test、implementation、final の中間 gate を機械チェックで fail closed にする
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request reporting weak waterfall flow and mid-process errors

- 2026-04-10 | work-principle | adaptive improvement は agile outer loop に Extension Backlog を持たせ、各 extension を 1 waterfall run-id、1 change pass、1 decision state として閉じてから次へ進む
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to strengthen Agile as one waterfall loop per extension

- 2026-04-10 | work-principle | implementation は approved design packet を読んで artifact/section を引用してから始め、設計と違う場合は Gate 5/6 に戻す
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to organize implementation around existing documents/design

- 2026-04-10 | work-principle | requirements は user に戻す前に accumulated context sweep で解決し、残った unknown だけを deferred/escalation に残す
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to avoid unnecessary runtime stops by using past logs and accumulated information

- 2026-04-10 | work-principle | Spark は design trace が固定済みの狭い implementation slice に使い、requirements/design/review/final judgment には使わない
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to delegate possible work to Codex Spark because rate limits are strict

- 2026-04-10 | work-principle | chunks, slices, checkpoints, and subpasses are internal progress; user-facing completion waits for all planned work units, active clauses, final review, validation, closeout gate, commit, and push
  - source: chat
  - scope: repo-wide
  - confidence: likely
  - evidence: 2026-04-10 request to fix the habit of stopping after work-unit decomposition

## Interaction Observations

- 2026-04-10 | interaction-observation | agent personality は自由作文ではなく、source/evidence/scope/confidence を持つ作業哲学として repo に蓄積する
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: 2026-04-10 request about agent knowledge/philosophy/personality formation

- 2026-04-10 | interaction-observation | Closeout must verify specification-to-product coverage and review-finding incorporation, not just that a minimal implementation and tests exist.
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: User reported a recurring pattern of closing after minimal implementation, possibly ignoring code review, and implementing only part of the specification.

- 2026-04-11 | interaction-observation | When push is a natural completion step for a tracked repo change, do not surface a separate push proposal; execute push directly unless the user explicitly forbids it or an external block exists.
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: 2026-04-11 user: '毎回Pushの運用はやりすぎかもしれません... Pushするのが自然なら許可を取らずにpushです'

- 2026-04-11 | interaction-observation | 文書導線を tree-first にすると sibling docs への注意が落ちやすいので、subagent handoff は cross-cutting packet を先に固定してから task packet に入れる
  - source: chat
  - scope: repo-wide
  - confidence: tentative
  - evidence: 2026-04-11 user feedback on document intake and subagent startup

## Task Retrospectives

- まだなし

## Promotion Candidates

- まだなし

## Open Questions

- まだなし
