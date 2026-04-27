# Notes Lifecycle
<!--
@dependency-start
upstream design README.md durable document index
@dependency-end
-->


この文書は、`notes/` を使うほど充実する形に保つための正本です。
action log、実験メモ、知識メモ、theme note、failure note を別々に持ちつつ、closeout ごとに昇格先を決めます。

## Purpose

- worktree 中の局所ログを、`main` から辿れる再利用知識へ育てる
- run-local な観測と repo-wide な知見を混ぜない
- 「残したが再利用されない note」を減らす
- closeout 時に notes を更新する判断を既定動作にする

## Default Flow

### 1. During Execution

- 一挙手一投足は `notes/worktrees/` の action log に残します。
- 実験 topic の結果要約は `notes/experiments/` に残します。
- branch / worktree の入口整理は `notes/branches/` に残します。

### 2. At Review / Closeout

closeout 前に、action log と report を見て次のどれへ昇格するかを決めます。

- `notes/knowledge/`
  - 何度も参照する短い横断知識
- `notes/themes/`
  - 複数 run から得た topic-level synthesis
- `memory/USER_PREFERENCES.md`
  - 会話から得た durable preference の蓄積と、`AGENTS.md` 昇格前の整理
- `memory/AGENT_PHILOSOPHY.md`
  - agent の作業哲学、対話から得た学習、task retrospective の蓄積と、workflow / guardrail / `AGENTS.md` 昇格前の整理
- `notes/failures/`
  - 再発防止のために残す failure pattern
- `documents/`
  - repo 正本として固定すべき rule

### 3. Keep The Worktree Log Thin

- action log は時系列と quick reference を担当します。
- 長く残る一般化は `knowledge` / `themes` / `failures` へ抜きます。
- action log 自体を巨大な最終成果物にしません。

## Promotion Rules

### Promote To `notes/knowledge/`

- 同じ command、path、environment rule、tool behavior を今後も参照しそう
- 1 topic 1 file の短い practical memo に落とせる

### Promote To `notes/themes/`

- 複数 run、複数 experiment、複数文献をまたいで言える
- `Known`, `Likely`, `Open`, `Worked`, `Did Not Work` で整理できる

### Promote To `notes/failures/`

- 同じ失敗を次回も踏みやすい
- trigger と safe alternative が書ける

### Promote To `documents/`

- repo-wide rule、workflow、review gate、environment contract として固定すべき

## Minimum Closeout Questions

closeout ごとに最低限次を確認します。

1. 今回の action log から、再利用知識に昇格すべき項目はあるか
1. 失敗として残すべきものはあるか
1. 既存 note を追記すべきか、新規 note を起こすべきか
1. 文書正本へ上げるべき rule change はあるか
1. 会話から得た durable preference を `memory/USER_PREFERENCES.md` に追記したか
1. agent-side の作業哲学、対話上の再発防止、task retrospective を `memory/AGENT_PHILOSOPHY.md` に追記したか
1. `memory/` への追記が shared canon update として closeout されたか
1. `AGENTS.md`、workflow、guardrail に昇格すべき stable preference や stable philosophy が増えていないか

## Templates

- `notes/worktrees/WORKTREE_LOG_TEMPLATE.md`
- `notes/branches/BRANCH_NOTE_TEMPLATE.md`
- `notes/knowledge/KNOWLEDGE_NOTE_TEMPLATE.md`
- `notes/themes/THEME_NOTE_TEMPLATE.md`
- `memory/AGENT_PHILOSOPHY.md`
- `notes/failures/FAILURE_NOTE_TEMPLATE.md`
