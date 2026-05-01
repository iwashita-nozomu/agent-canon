# 反復改善ワークフロー
<!--
@dependency-start
responsibility Documents 反復改善ワークフロー for this repository.
upstream design README.md workflow catalog
@dependency-end
-->


この文書は、実験、外部調査、性能計測、チューニング、比較検証を回しながらコードを改善するための正本です。
通常の feature 開発や repo-wide な恒久改修は [implementation-waterfall-workflow.md](implementation-waterfall-workflow.md) を使います。
この文書は、それだけでは扱いにくい tuning / exploration / protocol refinement を、明示的な反復 loop として扱います。
repo-level の長期 loop では top-level `goal.md` を正本にし、`python3 tools/agent_tools/goal_loop.py` で状態確認、iteration 実行、criteria 更新を行います。

## 1. 位置づけ

- 通常の実装:
  - 要件、計画、詳細設計、実装、検証を 1 pass で閉じる waterfall
- 反復改善:
  - backlog を持ち、複数 iteration を回す agile outer loop
  - ただし、repo に持ち帰る各 code/doc/environment change は 1 回ずつ waterfall pass で閉じる

要するに、この workflow は「開発全体を無秩序にアジャイル化する」ものではありません。
outer loop は agile、inner change pass は waterfall です。
各 backlog item は `Extension` と呼び、1 extension は必ず 1 waterfall pass と 1 run-id に対応させます。
同じ iteration で 2 つの extension を混ぜません。

## 2. 対象

- benchmark を見ながらの性能改善
- 実験結果を見ながらの段階的アルゴリズム改造
- parameter tuning と protocol refinement を伴う改善
- 調査、実験、実装、report 更新をまとめて回す改善 loop
- 「何が効くかまだ確定していない」探索的改善

## 3. 基本ルール

- 最初に top-level `goal.md` を更新し、今回の Objective、Exit Criteria、Backlog、Loop Log を固定します。これを tool 追加、prompt repair、workflow 編集より後回しにしてはいけません。
- 1 iteration では、狙いを 1 つの extension に絞ります。
- iteration 番号は進捗記録であり、loop の終了条件ではありません。`goal_loop.py` の `--max-iterations` は単一実行の安全 cap に限り、repo-level loop の終了は exit criteria と明示 decision で決めます。
- 1 extension は、1 `Candidate Change:`、1 waterfall run-id、1 `Decision State:` に固定します。
- 1 iteration で repo に持ち帰る code / docs / environment change は 1 つの waterfall pass として閉じます。
- 2 つ目の extension に入る前に、直前 extension の `make waterfall-gate-check`、final review、`task-close`、commit / push を終えます。
- baseline と comparison target は loop の途中で勝手に差し替えません。
- run ごとの result、decision、next action を明示し、なんとなく次へ進みません。
- `report_rewrite_required`、`extra_validation_required`、`rerun_required` が残る限り loop を閉じません。
- tuning 中でも、既存コード再利用と既存 style の踏襲を優先します。
- `backlog_continue` は次の extension へ進める decision state ですが、直前 extension の waterfall pass が close していない場合は次へ進みません。
- `goal.md` を使う loop では、依存解析、コード依存抽出、OOP/readability 解析、repo-wide 静的解析 / CI、objective 固有 evidence を exit criteria から外しません。
- `goal_loop.py mark` で criteria を done にする前に、対応する command output、report、run bundle artifact のいずれかを残します。
- skill/workflow prompt 改善では、テスト対象ごとに skill/workflow eval を先に固定し、`agents/evals/skill_workflow_prompt_eval.toml` を正本にします。
- prompt repair は eval の failure 行に紐づけ、同じ eval を rerun して `EVAL_STATUS=pass` になるまで loop を閉じません。
- agent 行動改善では、run 中に `workflow_monitor.py --behavior-event` で skill invocation、subagent routing、tool gate、prompt eval、review feedback、subagent lifecycle、diff-check を蓄積し、`agents/evals/agent_behavior_eval.toml` を正本にして `evaluate_agent_run.py` で採点します。
- behavior eval の feedback action は prompt repair、workflow artifact 修正、または monitoring rule 修正のいずれかで閉じ、`AGENT_EVALUATION_STATUS=pass` になるまで loop を閉じません。

## 4. Canonical Outer Loop

1. top-level `goal.md` に今回の Objective、Exit Criteria、Backlog、Loop Log を書く
1. 改善 backlog を固定する
1. `Question:`、`Comparison Target:`、`Exit Criteria:`、`Stop Budget:` を決める
1. repo-level loop の場合は `goal.md` を作成または更新し、`python3 tools/agent_tools/goal_loop.py status --goal-file goal.md` で parse 可能であることを確認する
1. skill/workflow prompt 改善の場合は、各テスト対象の eval を `agents/evals/skill_workflow_prompt_eval.toml` に固定する
1. `python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest agents/evals/skill_workflow_prompt_eval.toml` を baseline として実行する
1. agent 行動改善の場合は、`agents/evals/agent_behavior_eval.toml` の behavior criteria と `workflow_monitoring.md` の required behavior event を固定する
1. backlog から今回の 1 extension を選ぶ
1. extension ごとの waterfall run-id を作る
1. 必要なら外部調査と precedent 調査を追加する
1. baseline か current state を同じ protocol で記録する
1. 今回の 1 extension を waterfall で実行する
1. 各 waterfall gate で `make waterfall-gate-check ARGS="--report-dir <reports/agents/run-id> --gate <gate>"` を通す
1. fresh run で比較する
1. `experiment_reviewer` と `report_reviewer` が iteration outcome をレビューする
1. decision state を確定する
1. eval drift があれば、対応する prompt repair を行い、同じ eval を rerun する
1. prompt eval report が `EVAL_STATUS=pass` になるまで次 extension または closeout に進まない
1. behavior eval feedback があれば、run artifact、workflow prompt、または behavior-event recording rule を修正し、`AGENT_EVALUATION_STATUS=pass` になるまで次 extension または closeout に進まない
1. `goal.md` の exit criteria と backlog を evidence に合わせて更新する
1. waterfall pass の `task-close`、commit、push を終える
1. backlog を更新し、次 extension へ進むか loop を閉じる

## 5. Iteration Backlog

各 extension の着手前に、最低でも次を backlog に持ちます。

- `Backlog ID:`
- `Extension:`
- `Candidate Change:`
- `Why This Iteration Now:`
- `Expected Effect:`
- `Risk:`
- `Validation Plan:`
- `Stop Condition For This Iteration:`
- `Waterfall Run ID:`

backlog は単なる思いつき置き場ではなく、優先順付きの実行待ち列として扱います。

## 6. Decision States

- `approved`
  - 今回の iteration outcome は採用可能
- `backlog_continue`
  - 今回の iteration は完了したが、改善余地があり次の backlog item に進む
- `report_rewrite_required`
  - result は足りているが report が不足
- `extra_validation_required`
  - 追加 case、追加 figure、追加集計が必要
- `rerun_required`
  - fresh rerun が必要
- `direction_rethink_required`
  - backlog の優先順位や比較軸を見直す
- `stop_without_merge`
  - これ以上回しても費用対効果が低いので close

## 7. Required Roles

- `manager`
- `manager_reviewer`
- `scheduler`
- `schedule_reviewer`
- `researcher`
- `research_reviewer`
- `designer`
- `design_reviewer`
- `document_flow_reviewer`
- `test_designer`
- `implementer`
- `change_reviewer`
- `experimenter`
- `experiment_reviewer`
- `report_reviewer`
- `final_reviewer`
- `verifier`
- `auditor`

cost を無視する run では、必要に応じて research perspective review pack も既定で追加します。

## 8. Relationship To Other Workflows

- 外部調査と claim 更新の大枠:
  - [research-workflow.md](research-workflow.md)
- 単一 run と rerun 分岐:
  - `agents/skills/experiment-lifecycle.md`
- repo に持ち帰る各 change pass:
  - [implementation-waterfall-workflow.md](implementation-waterfall-workflow.md)

この workflow は、`research-workflow` よりも「改善 backlog を持って連続 iteration を回す」ことを強く規定します。

## 9. Close Conditions

loop を閉じてよいのは次のどちらかです。

- `Exit Criteria:` を満たし、最終 run、report、decision がそろった
- `stop_without_merge` で閉じ、採用しない理由と学びを note に残した

close 前には、少なくとも次を残します。

- `What Improved:`
- `What Did Not Improve:`
- `What We Learned:`
- `Next Best Backlog Item Or Stop Reason:`
- `Notes Promotion Decision:`
- 各 extension の waterfall run-id、gate evidence、decision state
