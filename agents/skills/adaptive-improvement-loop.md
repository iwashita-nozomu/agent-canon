# adaptive-improvement-loop
<!--
@dependency-start
contract skill
responsibility Documents adaptive-improvement-loop for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

実験、調査、チューニング、比較検証をまとめて回しながら、改善 backlog を iteration 単位で
扱う outer loop を定めます。各変更はその責務を持つ owner の実装・検証 route に委譲します。

## Use When

- benchmark を見ながら複数回の改善 iteration を回したい
- 1 回の change で終わらず、調査、run、report、次の tuning を継続させたい
- 「どれが効くか未確定」の探索的改善を、decision state 付きで進めたい
- tuning、protocol refinement、code change を同じ umbrella loop で扱いたい

## Core References

- [agents/skills/research-workflow.md](research-workflow.md)
- [agents/skills/experiment-lifecycle.md](experiment-lifecycle.md)
- [agents/skills/comprehensive-development.md](comprehensive-development.md)
- [agents/skills/codex-task-workflow.md](codex-task-workflow.md)

## Procedure

1. `Objective`、`Exit Criteria`、`Stop Budget`、優先順の `Improvement Backlog` を固定する。
2. 依存関係・既存実装・到達可能性を調べ、`Observation`、`Cause Search`、`Hypothesis`、
   `Expected Mechanism`、候補比較を残す。原因が未確定なら編集せず、`dependency-analysis`
   または `change-review` に戻る。
3. 一 iteration を一 extension、一 run identity、一 change pass、一 decision に対応させ、
   `plan -> implementation -> evidence -> next-action` の順で進める。各 change は選択された
   owner route に委譲する。
4. run 後に改善・反証・学習・未解決事項を記録し、backlog の次項目または stop reason を選ぶ。
   iteration 数や run status だけで完了にしない。
5. 次 extension に進む前に、直前の validation、review、closeout、commit/push を読み返す。

## Iteration Record

最低限、objective/backlog、iteration goal/change/run、evidence、decision、next action または
stop reason を同じ record に残します。behavior/eval/path/token evidence は各 owner から受け取り、
この skill で command や schema を再定義しません。

## Boundary

- 外部調査そのものは `literature-survey` を追加します。
- 単一 run の実行と rerun 分岐は `experiment-lifecycle` を使います。
- repo-wide な feature delivery には使わず、`comprehensive-development` と
  `codex-task-workflow` の implementation route を使います。
- role selection、required roles、topology、spawn budget は `$agent-orchestration` と
  `agents/task_catalog.yaml` が所有します。この skill は選択済み role を利用し、role list や
  重複判定を再定義しません。
- behavior event / calibration は `$agent-learning`、登録済み eval と duplicate audit は
  `$agent-eval-accumulation`、token / path comparison は `$tokens`、runtime feedback の構造化は
  `workflow_monitor.py` に委譲します。この skill は返された evidence の iteration 解釈と
  next action だけを所有します。

## Iteration Closeout

各 extension の closeout では、改善した点、改善しなかった点、学び、未解決事項、次の backlog item または stop reason を、
既存の decision/next-action record に一度だけ残します。role、評価 producer、runtime feedback、artifact 配置は各 owner に委譲します。
