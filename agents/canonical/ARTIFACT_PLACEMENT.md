# Artifact Placement

この文書は、task 実行中に増える文書や補助出力の置き場の正本です。
run ごとの一時 artifact と、repo に長く残す文書を分けて扱います。

## 置き場ルール

- repo-wide の正本:
  - agent 運用は `agents/`
  - 一般ルールや workflow は `documents/`
  - 再利用する知見や cross-run 要約は `notes/`
  - 開発環境は `docker/`
- run-local の artifact:
  - `reports/agents/<run-id>/`
- 一時的な runtime output:
  - `WORKTREE_SCOPE.md` の `## Runtime Output Directories` に書かれた場所

## Task 中の拡張文書

- その run だけで意味を持つメモは、新しい repo-wide 文書にしません。
- run 固有の判断、review、handoff は既存 artifact に追記します。
- 追加の長文説明が必要なら、まず次のどれに属するか判断します。

## どこへ置くか

### `reports/agents/<run-id>/`

対象:
- intake
- design
- review
- verification
- retrospective
- research / experiment の run 単位メモ

使うファイル:
- `intent_brief.md`
- `decision_log.md`
- `design_brief.md`
- `design_review.md`
- `change_review.md`
- `final_review.md`
- `experiment_change_loop.md`
- `environment_change_proposal.md`
- `verification.txt`
- specialist 用 artifact

補足:
- role write policy は `agents/agents_config.json` に従います。
- artifact-only role は許可された artifact だけを更新します。
- run 固有の追補は既存 artifact の節追加で吸収します。

### `documents/`

対象:
- repo 全体の標準 workflow
- 開発環境運用
- review / experiment / research の恒久手順

判断基準:
- 同種 task で繰り返し参照される
- 特定 run に閉じない
- agent 以外の人間にも読む価値がある

### `agents/`

対象:
- cross-agent の正本
- workflow family
- handoff / review / escalation
- agent 間で共有する CLI / skill / subagent の運用

判断基準:
- Codex / Claude / Copilot 間で揃えたい
- runtime entrypoint には重複させたくない

### `notes/`

対象:
- cross-run の知見
- 実験や調査の要約
- 将来の意思決定に再利用する補助メモ

判断基準:
- 正式ルールではない
- ただし捨てるには惜しい
- 次回の探索開始点として残す

## Subagent と補助文書

- Claude 固有の subagent 定義は `.claude/agents/` に置きます。
- subagent 自体の利用方針は `agents/` に置きます。
- 特定エージェント専用の prompt 断片を repo-wide 正本に昇格させないでください。

## 禁止事項

- 一時的な run メモを `documents/` に混ぜない
- agent ごとの CLI 実験ログを repo 正本にしない
- 古い例示コマンドを runtime truth として残さない
