# adaptive-improvement-loop

## Purpose

実験、調査、チューニング、比較検証をまとめて回しながら、改善 backlog を iteration 単位で潰していく outer loop を定めます。
通常の実装 pass は waterfall のままにし、改善全体だけを agile に扱います。

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
- `agents/skills/experiment-change-loop.md`
- `agents/skills/research-workflow.md`
- `agents/skills/report-review.md`

## Operating Rules

- outer loop は agile、repo に持ち帰る各 change pass は waterfall にします。
- 1 iteration につき 1 goal、1 change pass、1 decision state を基本にします。
- `Improvement Backlog:` を持ち、次に試す候補を優先順で管理します。
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
- `Candidate Change:`
- `Expected Effect:`
- `Validation Plan:`
- `Decision:`
- `Next Backlog Item:`

## Boundary

- 外部調査そのものは `literature-survey` を追加します。
- 単一 run の実行と rerun 分岐だけなら `experiment-lifecycle` を使います。
- 実験結果で code change を 1 本ずつ回す内側の loop は `experiment-change-loop` を使います。
- repo-wide な通常開発や feature delivery には使わず、`implementation-waterfall-workflow.md` を使います。
