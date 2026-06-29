# Memory
<!--
@dependency-start
contract data
responsibility Documents Memory for this repository.
upstream design ../README.md shared canon overview
upstream design ../PHILOSOPHY.md stable design-time philosophy canon
@dependency-end
-->


`memory/` は、shared canon が責務を持つ durable memory の置き場です。
自己学習、対話から抽出した preference、agent-side philosophy のように、次回 task でも毎回読むべき runtime memory をここへ置きます。
設計時哲学の安定正本は standalone AgentCanon では `PHILOSOPHY.md`、template root
では `vendor/agent-canon/PHILOSOPHY.md` です。`PHILOSOPHY.md` は root view の
同期対象ではありません。
`memory/AGENT_PHILOSOPHY.md` は、その正本へ昇格する前の観測と retrospective を蓄積します。

## Canonical Files

- [USER_PREFERENCES.md](USER_PREFERENCES.md)
  - 会話から得た durable user preference の正本
- [AGENT_PHILOSOPHY.md](AGENT_PHILOSOPHY.md)
  - agent の作業哲学、対話学習、task retrospective の昇格前ログ

## Rules

- `memory/` は shared canon 側の正本です。
- template / derived repo root の `memory/` は shared canon memory の runtime view です。closeout では shared canon update として扱います。
- `notes/themes/USER_PREFERENCES.md` と `notes/themes/AGENT_PHILOSOPHY.md` は removed legacy path です。復元せず、新しい durable memory は `memory/` に追加します。
- topic synthesis や一般的な theme note は `notes/themes/` に置けますが、durable preference / philosophy memory の正本にはしません。
