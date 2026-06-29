# adaptive-improvement-loop
<!--
@dependency-start
contract skill
responsibility Documents adaptive-improvement-loop for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Reader Map

- Purpose: manages experiments, research, tuning, and iterative code
  improvement as one backlog-driven agile outer loop.
- Use When: work will iterate over hypotheses, measurements, implementation
  changes, and review decisions rather than a single fixed patch.
- Section path: Purpose, Use When, and Core References set scope; Operating
  Rules and Required Records are the mandatory checklist; Boundary limits local
  improvisation.
- Boundary: individual runs do not count as accepted results without backlog,
  evidence, and review closure.

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
- `agents/workflows/goal-plan-implementation-loop.md`
- `agents/workflows/research-workflow.md`
- `agents/workflows/experiment-workflow.md`
- `agents/workflows/implementation-waterfall-workflow.md`
- `agents/skills/research-workflow.md`
- `agents/skills/experiment-lifecycle.md`

## Operating Rules

- 最初に top-level `goal.md` を更新し、今回の `Objective`、`Exit Criteria`、`Backlog`、`Loop Log` を固定します。これを tool 追加や prompt 修正より後回しにせず、`python3 tools/agent_tools/goal_loop.py status --goal-file goal.md` で確認します。
- user が goal-driven intent を示したが exact objective を渡していない場合は、parent が conservative な objective draft を `goal.md` に作り、`/goal` 確定前に read-only subagent fan-out、または explicit spawn authorization が無い session では許可待ち handoff plan で要求整理、repo survey、first-slice plan を確認します。
- 各 iteration の開始前と closeout 前に `python3 tools/agent_tools/goal_loop.py status --goal-file goal.md` を見ます。`NEXT_ACTION=run_next_iteration` の間は次 backlog iteration へ進み、user-facing completion にしません。
- outer loop は agile、repo に持ち帰る各 change pass は waterfall にします。
- Goal-driven iteration では `plan -> implementation -> evidence -> next-action` の短い loop を使い、次 slice が実装可能になったら planning を止めて編集へ戻ります。
- 1 iteration につき 1 extension、1 waterfall run-id、1 change pass、1 decision state にします。
- iteration 数は進捗カウンタであり、終了条件ではありません。loop は backlog と exit criteria で継続判断し、明示的な `goal_status: achieved` なしに完了扱いしません。
- `Improvement Backlog:` を持ち、次に試す候補を優先順で管理します。
- skill を使う run では `python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml --accumulate --run-id <run-id> --skill-used <skill>` を実行し、`EVAL_RUN_ID` と `EVAL_ACCUMULATED_REPORT` を evidence にします。
- skill/workflow prompt を改善する場合は、変更前にテスト対象ごとの eval を `evidence/agent-evals/skill_workflow_prompt_eval.toml` に固定します。
- prompt 修正前後で同じ eval を実行し、`EVAL_STATUS=pass` を evidence にします。詳細 report は `.agent-canon/log-archive/eval-results/skill-workflow-prompt/` に `<eval_run_id>-<status>-<skill-slug>.md` として蓄積し、既存 report を上書きしません。
- eval drift が出た場合は、脱線した skill/workflow prompt を修正し、同じ eval を rerun します。no eval deviation になるまで loop を閉じません。
- agent 行動を改善する場合は、skill invocation、stage / subagent routing、tool gate、accumulated prompt eval、review feedback、subagent lifecycle、diff-check、static-analysis feedback、execution path comparison を `workflow_monitor.py --behavior-event` で run bundle に蓄積します。
- 利用中に得られた user / reviewer feedback は、raw prose のまま放置せず `workflow_monitor.py --runtime-feedback "source=<...> target=<skill-or-workflow-or-eval> action=<prompt_repair|eval_update|memory_record|no_op> ..."` で構造化し、同じ iteration 内で対象 skill prompt、workflow prompt、eval、memory のいずれかへ還元します。
- `action=prompt_repair` または `action=eval_update` の feedback は、対応する `evidence/agent-evals/skill_workflow_prompt_eval.toml` の entry を先に更新または確認し、prompt repair 後に同じ eval を rerun します。
- static analysis が workflow / skill / prompt の弱さを示した場合は、結果を `static_analysis_feedback=applied|recorded` として監視し、還元先の skill / workflow / eval を明示します。未処理の `static_analysis_feedback=pending` を残して loop を閉じません。
- 同じ goal に対して 2 回の実行経路があり得る場合は、`tools/agent_tools/compare_agent_run_paths.py --baseline-run <run-a> --candidate-run <run-b>` で `execution_path`、`route_efficiency`、`static_analysis_feedback` を比較します。`route_efficiency=inefficient` または `selected_inefficient_route=yes` が出た場合は、agent behavior eval が fail するようにし、非効率経路を選ばないよう skill / workflow prompt を修正します。
- コード改善 iteration では、`agents/workflows/hypothesis-validation-workflow.md` を overlay にし、`Observation`、`Hypothesis`、`Expected Mechanism`、`Candidate Comparison`、`Disconfirming Evidence`、`Support Evidence`、`Hypothesis Decision` を iteration artifact に残します。`Hypothesis Decision` が `supported` でない場合は、同じ pass を拡張せず次仮説へ戻します。
- closeout 前に `python3 tools/agent_tools/evaluate_agent_run.py --report-dir <run> --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml --write` を実行し、`AGENT_EVALUATION_STATUS=pass` まで workflow artifact または prompt を修正します。
- 2 つ目の extension に進む前に、直前 extension の `waterfall-gate-check`、final review、`task-close`、commit / push を完了させます。
- baseline、comparison target、fairness rule は iteration ごとに勝手にずらしません。
- `report_rewrite_required`、`extra_validation_required`、`rerun_required`、`direction_rethink_required` が残る限り loop を閉じません。
- `goal_loop.py status` が `NEXT_ACTION=run_next_iteration` を返す限り loop を閉じません。
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
- `Hypothesis:`
- `Expected Mechanism:`
- `Candidate Comparison:`
- `Disconfirming Evidence:`
- `Support Evidence:`
- `Hypothesis Decision:`
- `Decision:`
- `Next Backlog Item:`
- `Skill/Workflow Eval Manifest:`
- `Prompt Eval Command:`
- `Prompt Eval Result:`
- `Behavior Eval Manifest:`
- `Behavior Event Log:`
- `Static Analysis Feedback Target:`
- `Two-Run Path Comparison:`
- `Execution Path Efficiency Decision:`
- `Agent Behavior Eval Result:`
- `Goal Loop Status:`

## Boundary

- 外部調査そのものは `literature-survey` を追加します。
- 単一 run の実行と rerun 分岐は `experiment-lifecycle` を使います。
- repo-wide な feature delivery には使わず、`implementation-waterfall-workflow.md` を使います。
