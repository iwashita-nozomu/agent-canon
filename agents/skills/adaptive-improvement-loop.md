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
- Boundary: individual runs are evidence for a backlog decision; they do not
  replace the iteration record, next action, or closeout owned by this skill.

実験開始前の plan は question、comparison、observables、evidence targets、protocol、resource、
operational stop condition を宣言するだけです。結果の解釈や iteration の遷移は run 後の
evidence に基づいて記録し、plan の completion や run 開始条件には結果を仮定しません。

## Purpose

実験、調査、チューニング、比較検証をまとめて回しながら、改善 backlog を iteration 単位で
扱う outer loop を定めます。各変更はその責務を持つ owner の実装・検証 route に委譲します。

## Use When

- benchmark を見ながら複数回の改善 iteration を回したい
- 1 回の change で終わらず、調査、run、report、次の tuning を継続させたい
- 「どれが効くか未確定」の探索的改善を、decision state 付きで進めたい
- tuning、protocol refinement、code change を同じ umbrella loop で扱いたい

## Core References

- `agents/skills/research-workflow.md`
- `agents/skills/experiment-lifecycle.md`
- `agents/skills/comprehensive-development.md`
- `agents/skills/codex-task-workflow.md`

## Operating Rules

- 最初に今回の `Objective`、`Exit Criteria`、`Stop Budget`、`Improvement Backlog` を固定します。durable lifecycle evidence が必要な run では、work unit、iteration result、next action を owner-selected run artifact に記録します。
- user が goal-driven intent を示したが exact objective を渡していない場合は、objective の整理と実行 topology をそれぞれの owner に引き継ぎ、この skill で role や spawn 条件を再定義しません。
- 各 iteration の開始前と closeout 前に iteration record と validation evidence を読み返します。未完了の作業は次の backlog action として記録し、現在の extension の closeout と user-facing completion を混同しません。
- outer loop は backlog と観測に応じて進め、repo に持ち帰る各 change pass は選択された owner
  route に従います。
- Goal-driven iteration では `plan -> implementation -> evidence -> next-action` の短い loop を使い、次 slice が実装可能になったら planning を止めて編集へ戻ります。
- 1 iteration につき 1 extension、1 run identity、1 change pass、1 iteration decision を対応させます。
- iteration 数は進捗カウンタであり、終了条件ではありません。loop は backlog と exit criteria
  で継続判断し、objective に対する evidence を iteration record に残してから完了を記録します。
- `Improvement Backlog:` を持ち、次に試す候補を優先順で管理します。
- 各 code-improvement iteration の前に、依存関係、既存実装、到達可能性、原因候補を調べ、
  `Observation`、`Cause Search`、`Hypothesis`、`Expected Mechanism`、`Candidate Comparison`、
  `Disconfirming Evidence`、`Support Evidence` を記録します。原因が未確定なら実装へ進まず、
  `dependency-analysis` または `change-review` の調査へ戻します。
- behavior event と active-skill calibration は `$agent-learning`、登録済み eval の実行と
  duplicate audit は `$agent-eval-accumulation`、path / token / role footprint の比較は
  `$tokens`、runtime feedback の event 構造化は `workflow_monitor.py` が所有します。この
  skill は各 owner の evidence を iteration decision と next action に消費し、command、
  schema、role、duplicate の定義を再定義しません。
- コード改善 iteration では、原因調査の記録を同じ iteration artifact に残し、run 後に
  `Hypothesis Decision` と次の選択を記録します。原因の証拠が不足する場合は、同じ pass を
  拡張せず原因調査へ戻します。
- 2 つ目の extension に進む前に、直前 extension の owner-selected validation、review、
  closeout、commit / push の結果を記録し、未完了の作業を次の action として引き継ぎます。
- baseline、comparison target、fairness rule は iteration ごとに勝手にずらしません。
- post-run の未解決事項は、iteration decision と次の action または stop reason に明記します。
- backlog を残す場合は次の iteration に引き継ぎ、現在の extension を閉じたことと backlog 全体を
  完了したことを混同しません。
- 改善を採用しないときも、`What We Learned:` を note に残します。

## Required Records

- `Question:`
- `Comparison Target:`
- `Exit Criteria:`
- `Stop Budget:`
- `Improvement Backlog:`
- `Iteration Goal:`
- `Extension:`
- `Run ID:`
- `Candidate Change:`
- `Cause Search:`
- `Expected Effect:`
- `Validation Plan:`
- `Hypothesis:`
- `Expected Mechanism:`
- `Candidate Comparison:`
- `Disconfirming Evidence:`
- `Support Evidence:`
- `Hypothesis Decision:`
- `Decision:`
- `Next Best Backlog Item Or Stop Reason:`
- `What Improved:`
- `What Did Not Improve:`
- `What We Learned:`
- `Notes Promotion Decision:`
- `Extension Decision:`（各 `Extension` ごとに一つ）
- `Prompt Eval Evidence:`
- `Behavior Eval Evidence:`
- `Behavior Event Evidence:`
- `Static Analysis Feedback:`
- `Path Comparison Evidence:`
- `Execution Path Decision:`
- `Agent Behavior Decision:`
- `Iteration State Readback:`

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

各 extension を閉じるときは、既存の `Decision`、`Next Action`、`Iteration State Readback` と
同じ artifact に、次の結果を一度だけ記録します。

- `What Improved:` 今回の extension で観測された改善
- `What Did Not Improve:` 改善しなかった指標、条件、または反証
- `What We Learned:` 次の選択に使える学び
- `Next Best Backlog Item Or Stop Reason:` 次の backlog item、または停止理由
- `Notes Promotion Decision:` topic note / shared knowledge へ持ち上げるか、その理由
- `Extension Decision:` extension の観測結果、未解決事項、次の action または stop reason を記録

closeout は extension 単位で行い、未解決の next action や post-run decision を次の action または
stop reason として残します。role の構成、評価 producer の実行、runtime feedback の構造化、または
artifact の配置はそれぞれの owner に委譲し、この record には結果と handoff だけを残します。

## Runtime Contract Clauses

The runtime discovery adapter delegates these required operating clauses to this canonical owner.

1. Read `agents/skills/adaptive-improvement-loop.md`.
1. Read `agents/skills/research-workflow.md` when external evidence or claim scope is in scope.
1. Read `agents/skills/experiment-lifecycle.md` for one run or fresh rerun.
1. If the user gives goal-driven intent without an exact objective, hand objective clarification and
   execution topology to their canonical owners; do not create role or spawn rules here.
1. When durable lifecycle evidence is required, record work units, iteration evidence, and next action
   in the owner-selected run artifact; do not create a repository mirror of session goal state.
1. Delegate behavior events and active-skill calibration to `$agent-learning`, registered eval
   execution and duplicate audit to `$agent-eval-accumulation`, path and token comparison to `$tokens`,
   and runtime feedback event construction to `workflow_monitor.py`.
1. Consume those owners' returned evidence in `Decision`, `Next Best Backlog Item Or Stop Reason`,
   and the iteration readback; do not recreate their commands, schemas, duplicate definitions, or
   acceptance gates here.
1. For code-improvement iterations, record `Observation`, `Cause Search`, `Hypothesis`, `Expected Mechanism`, `Candidate Comparison`, `Disconfirming Evidence`, `Support Evidence`, and the post-run `Hypothesis Decision` in the iteration artifact; if cause evidence is incomplete, return to `$dependency-analysis` or `$change-review` before editing.
1. If the cause or candidate change is not supported by the observed evidence, return to hypothesis
   selection or cause search instead of widening the current implementation pass.
1. Before closeout, consume behavior, eval, path, and token evidence from their owners; do not redefine
   required roles or duplicate their measurement gates in this skill.
1. Keep the outer loop backlog-driven, and route each repo-changing pass through
   `$comprehensive-development` or `$codex-task-workflow`; do not create a second procedure surface.
1. For goal-driven work, use the fast `plan -> implementation -> evidence -> next-action` loop; once the next cohesive slice is implementation-ready, stop broad planning and edit.
1. Fix `Question`, `Comparison Target`, `Exit Criteria`, `Stop Budget`, and `Improvement Backlog` before choosing the next iteration.
1. Keep one extension, one run identity, one change pass, and one iteration decision at a time.
1. Treat the iteration number as progress metadata, not as a completion condition; only explicit achieved criteria close the loop.
1. Before moving to a second extension, record the previous extension's owner-selected validation,
   review, closeout, commit, and push results.
1. At iteration closeout, record `What Improved`, `What Did Not Improve`, `What We Learned`, `Next Best
   Backlog Item Or Stop Reason`, `Notes Promotion Decision`, and one `Extension Decision` for each
   extension alongside the existing iteration state readback.
