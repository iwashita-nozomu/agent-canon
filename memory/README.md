# Memory
<!--
@dependency-start
upstream design ../README.md shared canon overview
@dependency-end
-->


`memory/` は、shared canon が責務を持つ durable memory の置き場です。
自己学習、対話から抽出した preference、agent-side philosophy のように、次回 task でも毎回読むべき runtime memory をここへ置きます。

## Canonical Files

- [USER_PREFERENCES.md](/mnt/l/workspace/project_template/memory/USER_PREFERENCES.md)
  - 会話から得た durable user preference の正本
- [AGENT_PHILOSOPHY.md](/mnt/l/workspace/project_template/memory/AGENT_PHILOSOPHY.md)
  - agent の作業哲学、対話学習、task retrospective の正本

## Rules

- `memory/` は shared canon 側の正本です。
- template root には runtime view を置きますが、closeout では shared canon update として commit / push します。
- `notes/themes/USER_PREFERENCES.md` と `notes/themes/AGENT_PHILOSOPHY.md` は互換 view として残します。
- topic synthesis や一般的な theme note は引き続き `notes/themes/` に置きます。
