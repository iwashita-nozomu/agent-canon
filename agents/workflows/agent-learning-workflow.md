# Agent Learning Workflow
<!--
@dependency-start
responsibility Documents Agent Learning Workflow for this repository.
upstream design README.md workflow catalog
upstream design ../../issues/README.md durable operational finding storage
upstream implementation ../../tools/agent_tools/evaluate_agent_run.py evaluates run bundles
upstream implementation ../../tools/agent_tools/workflow_monitor.py appends monitoring evidence
@dependency-end
-->


この文書は、agent の作業哲学と対話から得た学習を、会話文脈ではなく shared canon の `memory/` と tool へ固定する手順です。

## Purpose

- user preference と agent philosophy を混同しない
- raw chat ではなく、短い observation と evidence に圧縮して残す
- 毎 task の closeout で、学習すべき項目があるか確認する
- 毎 task の closeout で、run bundle を評価し、agent feedback action を明示する
- stable になった項目だけを `AGENTS.md`、workflow、review rule へ昇格する
- 自己学習と対話記録の追記を template local artifact ではなく shared canon workflow の責務として扱う
- workflow defect は run bundle だけに残さず、`issues/`、`memory/`、または `notes/failures/` へ durable record として昇格する

## Literature Basis

- reflective equilibrium は、個別判断と一般原則を相互調整する考え方です。この repo では、個別 task の観測と agent の作業原則を `AGENT_PHILOSOPHY.md` で照合し、矛盾が増えたら workflow 正本を見直します。
- reflective practice は、専門家が作業中と作業後の reflection で暗黙知を言語化する考え方です。この repo では、task 中の気づきと closeout retrospective を `log_agent_learning.py` で短く残します。
- situated knowledges は、知識を特定の立場と実践に結び付いたものとして扱います。この repo では、observation に source、scope、confidence を付け、どこまで一般化できるかを明示します。
- Value Sensitive Design は、価値を設計過程全体で扱う方法論です。この repo では、user preference、agent philosophy、repo rule、review gate を分けて、価値の出所を追跡可能にします。
- extended mind は、外部 notebook や言語的 scaffold が認知の一部になり得ると見る立場です。この repo では、notes を agent の外部記憶として扱い、入口文書で毎回読む対象にします。
- human-feedback preference learning は、対話や評価から preference を更新する実装上の比喩を与えます。ただし、この repo では raw feedback を自動学習せず、agent が evidence 付き observation として明示的に記録します。

## External Evaluation Basis

- OpenAI の agent eval guidance は、debug 中は trace grading で tool call、handoff、policy adherence、prompt/routing change の影響を見ることを推奨しています。Source: https://platform.openai.com/docs/guides/agent-evals
- OpenAI の trace grading guidance は、end-to-end trace に structured score / label を付け、workflow がどこで成功・失敗したかを特定する考え方を説明しています。Source: https://platform.openai.com/docs/guides/trace-grading
- OpenAI の Codex 運用記事は、agent が失敗したときに「何の tool / guardrail / documentation が足りないか」を repo に戻し、review feedback と validation を loop 化する方針を説明しています。Source: https://openai.com/index/harness-engineering/
- この repo では外部 API 依存を closeout gate に入れず、同じ原則を `reports/agents/<run-id>/agent_evaluation.md` と `tools/agent_tools/evaluate_agent_run.py` に写像します。

## Canonical Notes

- `memory/USER_PREFERENCES.md`
  - user の coding philosophy、review expectation、document preference
- `memory/AGENT_PHILOSOPHY.md`
  - agent の作業哲学、判断原則、対話から得た再発防止、task retrospective
- `notes/guardrails/engineering_avoidances.md`
  - 既に失敗ログから確定した禁止事項
- `issues/`
  - workflow、tool、PR gate、closeout、search、memory persistence の運用 defect backlog

`memory/` は shared canon 側の正本です。template root では runtime view を使いますが、closeout では canon update として扱います。

## Logging Rule

durable な観測を得たら次を使います。

```bash
python3 tools/agent_tools/log_agent_learning.py \
  --kind interaction-observation \
  --statement "ユーザーは agent の人格形成を raw chat ではなく repo 内の更新可能な作業哲学として扱いたい" \
  --source chat \
  --evidence "2026-04-10 request about agent knowledge/philosophy updates" \
  --scope repo-wide \
  --confidence tentative
```

user preference そのものは既存の次を使います。

```bash
python3 tools/agent_tools/log_user_preference.py \
  --preference "agent の作業哲学を task / dialogue ごとに更新したい" \
  --kind provisional \
  --source chat
```

`memory/` は AgentCanon submodule の実体を更新します。追記だけで止めると
submodule の未コミット差分になり、latest sync や別 repo では durable memory
として読まれません。memory を残した run では、closeout 前に次で AgentCanon
commit、push、必要なら template pin commit まで閉じます。

```bash
python3 tools/agent_tools/persist_agent_memory.py \
  --commit \
  --push \
  --commit-superproject \
  --push-superproject
```

## Agent Run Evaluation

closeout 前に run bundle を評価し、採点結果と feedback action を `agent_evaluation.md` に固定します。

```bash
python3 tools/agent_tools/evaluate_agent_run.py \
  --report-dir reports/agents/<run-id> \
  --write
```

評価対象:

- request clause traceability
- schedule / work log の completeness
- workflow monitoring: selected skills、stage / subagent routing、MCP preflight、repo dependency intake、web research decision、behavior events、intervention history
- behavior eval: skill invocation、subagent routing、tool gates、prompt eval baseline/rerun、review feedback resolution、subagent lifecycle closeout、diff-check approval
- review feedback の resolution
- validation / commit / push evidence
- dependency manifest と canonical tree-head evidence
- retrospective と skill / config / workflow / memory への self-improvement decision

`AGENT_EVALUATION_STATUS=revise` の場合は、出力された feedback action を schedule/work_log/該当 artifact に反映し、再度 evaluation を通します。
`AGENT_EVALUATION_STATUS=pass` になり、`agent_evaluation.md` の `feedback_actions_resolved: yes` と `learning_capture_complete: yes` が揃うまで、`task_close.py` は user-facing completion を許可しません。
behavior eval の rubric は `agents/evals/agent_behavior_eval.toml` を正本にし、skill / workflow を変えたのに agent 行動が変わっていない場合は revise として扱います。

## Workflow Monitoring

repo-changing task は `workflow_monitoring.md` を run bundle 内の監視正本として維持します。
この artifact は conversation summary ではなく、workflow が実際に観測した signals と介入を記録します。
`workflow_monitor.py` を使うと、監視項目を手書きではなく機械的に蓄積できます。
`bootstrap_agent_run.py` / `task_start.py` は routing と preflight の初期 signals を自動追記します。
`check_mcp_inventory.py --report-dir <run>` と `run_repo_dependency_review.sh --report-dir <run>` はそれぞれ MCP preflight と dependency review の evidence を追記します。
agent 行動は `workflow_monitor.py --behavior-event "..."` で `## Behavior Events` に蓄積します。ここには最終結果の要約ではなく、skill invocation、subagent spawn / close、tool call、prompt eval run、review decision、feedback action、diff-check decision のような観測可能 event を書きます。
利用中の user / reviewer feedback は `workflow_monitor.py --runtime-feedback "source=<user|reviewer|eval> target=<skill-or-workflow-or-eval> action=<prompt_repair|eval_update|memory_record|no_op> evidence=<short-observation>"` で記録します。`prompt_repair` と `eval_update` は対象 prompt / eval の更新と rerun evidence まで同じ run に残し、`memory_record` は `log_agent_learning.py` または preference sync へ接続します。`no_op` は捨てる判断ではなく、なぜ durable prompt に反映しないかを evidence に残す判断です。

必須 signals:

- `skills=` または `$agent-orchestration` など、選択した skill surface
- stage owner、subagent routing、または `parent_direct_reason` / `trivial_direct_edit`
- MCP preflight 結果、または `mcp_preflight_not_required`
- repo dependency intake 結果、または `repo_dependency_intake_not_required`
- web research / external research 結果、または `web_research_not_required`
- behavior event: skill invocation、stage / subagent routing、tool gate、prompt eval、review feedback、subagent lifecycle、diff-check のいずれか
- runtime feedback event: `runtime_feedback=observed` または feedback が無い場合の `runtime_feedback_not_observed`

closeout では `skill_improvement_decision`、`config_improvement_decision`、`workflow_improvement_decision`、`memory_learning_decision` を `applied`、`recorded`、`not_applicable` のいずれかにします。
`pending` のまま Eval を通してはいけません。

## Operational Issue Capture

user、reviewer、runtime、CI が workflow defect を指摘した場合は、run bundle への記録だけでは未完了です。
次のどれかに durable record を残します。

- `issues/open/AC-YYYYMMDD-<slug>.md`: workflow/tool/PR gate/search/closeout など、修正 action と affected surface を持つ運用 finding
- `memory/AGENT_PHILOSOPHY.md`: agent の作業原則として再利用する短い observation
- `notes/failures/`: 再発防止の failure analysis

workflow defect の affected surface を探すときは、raw search hit を dependency graph に通します。

```bash
rg -l "topic keywords" > reports/search_hits.txt
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --search-hits-file reports/search_hits.txt
```

`issues/` に入れる finding は `issues/README.md` の required fields を満たし、`edit_scope` に `dependency_edit_scope.txt` または主要 `DEPENDENCY_EDIT_SCOPE_PATH` を残します。

## Kind Definitions

- `interaction-observation`
  - user との対話から得た agent 側の振る舞い改善
- `work-principle`
  - 今後の task execution に使う作業原則
- `failure-avoidance`
  - 同じ失敗を防ぐための観測。確定したら `notes/guardrails/engineering_avoidances.md` へ昇格する
- `task-retrospective`
  - closeout 時の作業後 reflection
- `promotion-candidate`
  - `AGENTS.md`、workflow、review rule へ上げる候補
- `open-question`
  - まだ判断原則へ上げない未確定点

## Closeout Gate

closeout 前に次を確認します。

1. `tools/agent_tools/evaluate_agent_run.py --report-dir <run> --write` が pass したか
1. `agent_evaluation.md` の feedback action が解決済みか
1. user preference は `USER_PREFERENCES.md` に入れるべきか
1. agent の作業哲学や対話上の再発防止は `AGENT_PHILOSOPHY.md` に入れるべきか
1. 確定した禁止事項は `engineering_avoidances.md` に昇格すべきか
1. stable な項目は `AGENTS.md`、`CODEX_WORKFLOW.md`、review TOML に昇格すべきか
1. `memory/` への追記が `persist_agent_memory.py --commit --push` で shared canon 側の更新として commit / push まで反映されたか
1. template root から作業した場合、`persist_agent_memory.py --commit-superproject` または同等の commit で `vendor/agent-canon` pin が更新されたか

## Promotion Rule

- 1 回限りの task-local 指示は昇格しません。
- 反復して観測された、または user が明示的に durable とした項目だけを promotion candidate にします。
- `AGENTS.md` へ昇格するときは短い rule にし、source、rationale、例は note 側に残します。
- agent personality は自由作文にしません。repo の作業品質を改善する observable rule として残します。

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
