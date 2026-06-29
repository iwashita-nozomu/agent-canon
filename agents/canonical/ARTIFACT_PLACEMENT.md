# Artifact Placement
<!--
@dependency-start
contract agent-runtime
responsibility Documents Artifact Placement for this repository.
upstream design README.md canonical workflow index
@dependency-end
-->


この文書は、task 実行中に増える文書や補助出力の置き場の正本です。
run ごとの一時 artifact と、repo に長く残す文書を分けて扱います。

## この文書の読み方

この文書は、run-local artifact、repo-wide 正本文書、cross-run に残す
agent report の置き場を決めます。まず `置き場ルール` と `Task 中の拡張文書`
で判断軸を確認し、具体的な保存先は `どこへ置くか` の
`reports/agents/<run-id>/`、`documents/`、`agents/`、`notes/` を読み分けます。
`Subagent と補助文書` と `禁止事項` は、task 固有メモを repo 正本へ
昇格させる前の境界確認に使います。

## 置き場ルール

- repo-wide の正本:
  - agent 運用は `agents/`
  - 一般ルールや workflow は `documents/`
  - 再利用する知見や cross-run 要約は `notes/`
  - 開発環境は `docker/`
- run-local の artifact:
  - `reports/agents/<run-id>/`
- cross-run に蓄積する agent report:
  - `.agent-canon/log-archive/agent-reports/<repo-key>/<run-id>/`
  - log archive branch は `logs/<repo-key>`
  - 具体値は `python3 tools/agent_tools/runtime_log_archive_git.py status` の
    `RUNTIME_LOG_ARCHIVE_REPORTS_*` 行を見る
- 一時的な runtime output:
  - current checkout の run-local handoff、`team_manifest.yaml` write policy、または `task_authority.yaml` `allowed_paths` に明示された場所
  - `WORKTREE_SCOPE.md` は legacy cleanup evidence であり、新しい runtime output や write scope の authority ではありません

## Task 中の拡張文書

- その run だけで意味を持つメモは、新しい repo-wide 文書にしません。
- run 固有の判断、review、handoff は既存 artifact に追記します。
- 追加の reader-facing 説明が必要なら、まず file / document responsibility から次のどれに属するか判断します。

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
- cross-run で残す必要がある agent report は、agent が手で別 report を作らず
  通常は `python3 tools/agent_tools/runtime_log_archive_git.py sync` で
  `reports/agents/` 全体を `.agent-canon/log-archive/agent-reports/<repo-key>/`
  へ機械的に同期します。特定 run の immutable snapshot が必要なときだけ
  `archive-agent-report --report-dir reports/agents/<run-id>` を使い、push は同じ
  helper の `push` command が担当します。
- closeout 前に、`task_close.py` が report artifact placement を確認します。
  tracked durable report は repo canon として許可します。untracked または
  ignored な report file は current run の `reports/agents/<run-id>/` の下だけを
  許可します。古い run bundle は archive / closeout の対象であり、current run
  へ手でコピーして残しません。
- 機械的に再生成できる report root は残しません。
  `reports/agent-eval-runs/`、`reports/dependency-review/`,
  `reports/agent-runtime-dashboard/`, `reports/agent-improvement-guide/`,
  `reports/hooks/`, `reports/.cache/`, `reports/*.json`, `reports/*.patch`,
  `reports/*.txt` は `generated_artifact_guard.py` の対象です。必要なら
  producer を再実行します。知見を残す場合は report file ではなく、
  `documents/` / `agents/` / `notes/` へ責務と dependency manifest 付きで
  昇格します。

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
- Codex で再利用したい
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

- subagent 自体の利用方針は `agents/` に置きます。
- 特定エージェント専用の prompt 断片を repo-wide 正本に昇格させないでください。

## 禁止事項

- 一時的な run メモを `documents/` に混ぜない
- agent ごとの CLI 実験ログを repo 正本にしない
- 古い例示コマンドを runtime truth として残さない
