# adaptive-improvement-loop

## Purpose

実験、調査、チューニング、比較検証をまとめて回しながら、改善 backlog を iteration 単位で潰していく outer loop を定めます。
実装 pass は waterfall に固定し、改善全体だけを agile に扱います。

## Use When

- benchmark を見ながら複数回の改善 iteration を回したい
- 1 回の change で終わらず、調査、run、report、次の tuning を継続させたい
- 「どれが効くか未確定」の探索的改善を、decision state 付きで進めたい
- tuning、protocol refinement、code change を同じ umbrella loop で扱いたい

## Core References

- `documents/adaptive-improvement-workflow.md`
- `documents/research-workflow.md`
- `documents/experiment-workflow.md`
- `documents/implementation-waterfall-workflow.md`
- `agents/skills/research-workflow.md`
- `agents/skills/experiment-lifecycle.md`

## Operating Rules

- outer loop は agile、repo に持ち帰る各 change pass は waterfall にします。
- 1 iteration につき 1 extension、1 waterfall run-id、1 change pass、1 decision state にします。
- `Improvement Backlog:` を持ち、次に試す候補を優先順で管理します。
- 2 つ目の extension に進む前に、直前 extension の `waterfall-gate-check`、final review、`task-close`、commit / push を完了させます。
- baseline、comparison target、fairness rule は iteration ごとに勝手にずらしません。
- `report_rewrite_required`、`extra_validation_required`、`rerun_required`、`direction_rethink_required` が残る限り loop を閉じません。
- 改善を採用しないときも、`What We Learned:` を note に残します。

## Required Records

- `Question:`
- `Comparison Target:`
- `Exit Criteria:`
- `Stop Budget:`
- `Improvement Backlog:`
- `Iteration Goal:`
- `Extension:`
- `Waterfall Run ID:`
- `Candidate Change:`
- `Expected Effect:`
- `Validation Plan:`
- `Decision:`
- `Next Backlog Item:`

## Boundary

- 外部調査そのものは `literature-survey` を追加します。
- 単一 run の実行と rerun 分岐は `experiment-lifecycle` を使います。
- repo-wide な feature delivery には使わず、`implementation-waterfall-workflow.md` を使います。
