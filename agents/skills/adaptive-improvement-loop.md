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

対象の改善目標と、依頼・利用可能資源に見合う終了条件を決めます。反復が続く作業には
停止予算または停止条件を置き、未確定の原因は実装前に調べます。`dependency-analysis`
または `change-review` は、依存や実装責務が選択に影響するときに使います。

各意味のある変更・比較は、解釈可能な単位と run identity で記録し、選択された owner
route で実行します。`plan -> implementation -> evidence -> next-action` は考え方の例で、
独立した段階を常にこの順で追加する要求ではありません。結果から改善、反証、追加調査、
report 更新、次の変更、または停止を選び、未解決事項を残す場合は理由を記録します。
iteration 数や run status だけでは完了を示しません。

次の反復が必要なときは、直前の検証・review・closeout を読み返し、再利用できる証拠を
引き継ぎます。commit / push は各 owner の task scope が要求するときにだけ扱います。

## Iteration Record

同じ record で反復を追う場合は、objective、変更/run identity、evidence、decision、次の action
または stop reason が後から読み取れるようにします。task に backlog がない場合は新しく作らず、
behavior/eval/path/token evidence とその command/schema は各 owner に委譲します。

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

反復を閉じるときは、改善・未改善、得た学び、未解決事項、次の backlog item または
stop reason を既存の decision/next-action record に残します。role、評価 producer、runtime
feedback、artifact 配置は各 owner に委譲します。
