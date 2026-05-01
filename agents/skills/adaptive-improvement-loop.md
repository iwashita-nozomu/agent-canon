# adaptive-improvement-loop
<!--
@dependency-start
responsibility Documents adaptive-improvement-loop for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Purpose

実験、調査、チューニング、比較検証をまとめて回しながら、改善 backlog を iteration 単位で潰していく outer loop を定めます。
実装 pass は waterfall に固定し、改善全体だけを agile に扱います。

## Use When

- benchmark を見ながら複数回の改善 iteration を回したい
- 1 回の change で終わらず、調査、run、report、次の tuning を継続させたい
- 「どれが効くか未確定」の探索的改善を、decision state 付きで進めたい
- tuning、protocol refinement、code change を同じ umbrella loop で扱いたい

## Core References

- `agents/workflows/adaptive-improvement-workflow.md`
- `agents/workflows/research-workflow.md`
- `agents/workflows/experiment-workflow.md`
- `agents/workflows/implementation-waterfall-workflow.md`
- `agents/skills/research-workflow.md`
- `agents/skills/experiment-lifecycle.md`

## Operating Rules

- 最初に top-level `goal.md` を更新し、今回の `Objective`、`Exit Criteria`、`Backlog`、`Loop Log` を固定します。これを tool 追加や prompt 修正より後回しにせず、`python3 tools/agent_tools/goal_loop.py status --goal-file goal.md` で確認します。
- outer loop は agile、repo に持ち帰る各 change pass は waterfall にします。
- 1 iteration につき 1 extension、1 waterfall run-id、1 change pass、1 decision state にします。
- `Improvement Backlog:` を持ち、次に試す候補を優先順で管理します。
- skill/workflow prompt を改善する場合は、変更前にテスト対象ごとの eval を `agents/evals/skill_workflow_prompt_eval.toml` に固定します。
- prompt 修正前後で `python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest agents/evals/skill_workflow_prompt_eval.toml` を実行し、`EVAL_STATUS=pass` を evidence にします。
- eval drift が出た場合は、脱線した skill/workflow prompt を修正し、同じ eval を rerun します。no eval deviation になるまで loop を閉じません。
- agent 行動を改善する場合は、skill invocation、stage / subagent routing、tool gate、prompt eval、review feedback、subagent lifecycle、diff-check を `workflow_monitor.py --behavior-event` で run bundle に蓄積します。
- closeout 前に `python3 tools/agent_tools/evaluate_agent_run.py --report-dir <run> --behavior-manifest agents/evals/agent_behavior_eval.toml --write` を実行し、`AGENT_EVALUATION_STATUS=pass` まで workflow artifact または prompt を修正します。
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
- `Skill/Workflow Eval Manifest:`
- `Prompt Eval Command:`
- `Prompt Eval Result:`
- `Behavior Eval Manifest:`
- `Behavior Event Log:`
- `Agent Behavior Eval Result:`

## Boundary

- 外部調査そのものは `literature-survey` を追加します。
- 単一 run の実行と rerun 分岐は `experiment-lifecycle` を使います。
- repo-wide な feature delivery には使わず、`implementation-waterfall-workflow.md` を使います。
