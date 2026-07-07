# Agent Learning Workflow
<!--
@dependency-start
contract workflow
responsibility Documents Agent Learning Workflow for this repository.
upstream design README.md workflow catalog
upstream design ../../issues/README.md durable operational finding storage
upstream implementation ../../tools/agent_tools/evaluate_agent_run.py evaluates run bundles
upstream implementation ../../tools/agent_tools/workflow_monitor.py appends monitoring evidence
@dependency-end
-->


この文書は、agent の作業哲学と対話から得た学習を、会話文脈ではなく shared canon の `memory/` と tool へ固定する手順です。

## Reader Map

- This document owns the workflow for turning task observations, feedback, and agent run evaluation into durable AgentCanon learning surfaces.
- The early sections define purpose, literature basis, external evaluation basis, canonical notes, and logging commands; the later sections cover run evaluation, workflow monitoring, operational issue capture, kind definitions, closeout, and promotion.
- Use `## Logging Rule` when recording a concrete observation, and `## Agent Run Evaluation` / `## Workflow Monitoring` during closeout or behavior feedback repair.
- For chunked reading, first decide whether the input is a user preference, agent philosophy observation, workflow defect, or eval feedback, then read the matching recording and promotion section.

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

- OpenAI / Codex の agent eval、trace grading、Codex 運用 guidance は
  workflow 文書内で個別 URL や alternate route 文書として二重管理しません。
  更新時は `$openai-docs` の source route を使い、Codex manual helper、
  Docs MCP、official-domain web alternate route、または `$openai-docs` が指定する
  bundled alternate route references で確認します。
- この workflow の local authority は、外部 doc の写しではなく
  `evidence/agent-evals/agent_behavior_eval.toml`、
  `reports/agents/<run-id>/agent_evaluation.md`、
  `tools/agent_tools/evaluate_agent_run.py` です。
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
- hook / tool feedback routing: hook、code checker、static analysis、CI、review-tool の結果を parent protocol と subagent protocol へ反映するか、理由付きで反映不要にしたか
- review feedback の resolution
- validation / commit / push evidence
- dependency manifest と canonical tree-head evidence
- retrospective と skill / config / workflow / memory への self-improvement decision

`AGENT_EVALUATION_STATUS=revise` の場合は、出力された feedback action を schedule/work_log/該当 artifact に反映し、再度 evaluation を通します。
`AGENT_EVALUATION_STATUS=pass` になり、`agent_evaluation.md` の `feedback_actions_resolved: yes` と `learning_capture_complete: yes` が揃うまで、`task_close.py` は user-facing completion を許可しません。
behavior eval の rubric は `evidence/agent-evals/agent_behavior_eval.toml` を正本にし、skill / workflow を変えたのに agent 行動が変わっていない場合は revise として扱います。

## Workflow Monitoring

repo-changing task は `workflow_monitoring.md` を run bundle 内の監視正本として維持します。
この artifact は conversation summary ではなく、workflow が実際に観測した signals と介入を記録します。
`workflow_monitor.py` を使うと、監視項目を手書きではなく機械的に蓄積できます。
`bootstrap_agent_run.py` / `task_start.py` は routing と preflight の初期 signals を自動追記します。
`run_repo_dependency_review.sh --report-dir <run>` は dependency review の evidence を追記します。
agent 行動は `workflow_monitor.py --behavior-event "..."` で `## Behavior Events` に蓄積します。ここには最終結果の要約ではなく、skill invocation、subagent spawn / close、tool call、prompt eval run、review decision、feedback action、diff-check decision のような観測可能 event を書きます。
利用中の user / reviewer feedback は `workflow_monitor.py --runtime-feedback "source=<user|reviewer|eval> target=<skill-or-workflow-or-eval> action=<prompt_repair|eval_update|memory_record|no_op> evidence=<short-observation>"` で記録します。`prompt_repair` と `eval_update` は対象 prompt / eval の更新と rerun evidence まで同じ run に残し、`memory_record` は `log_agent_learning.py` または preference sync へ接続します。`no_op` は捨てる判断ではなく、なぜ durable prompt に反映しないかを evidence に残す判断です。
feedback が「利用中の skill 修正が甘い」「skill が弱い」「呼び出しが遅い」「routing が外れた」のように active skill の挙動を指す場合は、active skill set を first repair candidate とします。active skill set は、直近の `skills=...` 宣言、読了した runtime `SKILL.md`、run bundle の selected skill evidence、または `workflow_monitoring.md` の skill invocation event から決めます。
test を pass させるために agent が simplification、revert、intended behavior deletion、oracle weakening、または test planning の過剰重視で owning code repair を止めたという user / reviewer feedback は、`test-design` と implementation workflow への active skill feedback として扱います。`workflow_monitor.py --runtime-feedback` で `target=test-design` または implementation workflow、`action=prompt_repair|eval_update` を記録し、prompt、eval、または tool repair で解決します。memory-only で閉じません。
input token 過多、同じ文書や raw log の重複読み込み、長い evidence の model 投入が feedback された場合も、active routing / context skill を first repair candidate とします。修正は context を省略する方向ではなく、owner / dependency evidence を保ったまま、構造読み込みを `Structure Intake Packet` に正本化し、LLM-visible context へ入れる material を次の判断に効く構造要約へ正規化し、raw bulk は artifact path で参照する方向に寄せます。
prompt を固定する前に calibration step を置き、指摘をどの強さで反映するかを決めます。単発 feedback は scoped guidance、example、issue、memory で足りるかを先に見ます。hard rule は invariant、checker-backed、または反復観測された失敗に限ります。prompt rule にする場合は、適用条件、scope、例外または owner decision を短く添えます。

### Runtime Feedback Closure Loop

user / reviewer が agent の動き、routing、自己改善、tool 化、prompt の弱さを指摘した場合、parent はその場で `$agent-learning` を有効化します。指摘を chat 上の反省で終わらせず、次の順で閉じます。

1. `workflow_monitor.py --runtime-feedback` で `source=... target=... action=... evidence=...` を記録する
1. 指摘の反映先を `skill prompt`、`workflow prompt`、`tool/checker`、`eval rubric`、`memory`、`issue`、`no_op` のどれかに分類する。active skill の挙動に対する feedback は、該当 skill の runtime `SKILL.md` と canonical `agents/skills/<skill>.md` を first repair candidate にする
1. test pass のために simplification、revert、intended behavior deletion、oracle
   weakening、または test planning の過剰重視で owning code repair を止めたという
   feedback は、`test-design` と implementation workflow の active skill feedback
   として分類し、memory-only では閉じない
1. calibration step で反映の強さを決め、過剰固定を避ける。hard rule は invariant、checker-backed、または反復観測された失敗に限り、prompt rule にする場合は適用条件、owner、validation または例外条件を短く添える
1. `skill prompt` を修正する場合は、discoverable runtime `SKILL.md`、canonical skill doc、関連 workflow / handoff surface の順に owner を確認し、必要な prompt eval entry を更新または引用してから rerun する
1. active skill feedback を memory-only で閉じる場合は、feedback が観測メモに留まる理由、または skill owner を変更しない理由を `target=<skill> action=no_op` か durable issue に記録する。単なる observation 追記だけでは `skill_improvement_decision=applied` にしない
1. `action=no_op` 以外では、`skill_improvement_decision`、`config_improvement_decision`、`workflow_improvement_decision`、`memory_learning_decision` の少なくとも 1 つを `applied` または `recorded` にする
1. prompt / tool / eval を更新した場合は、対応する test、checker、prompt eval、または workflow eval を同じ run で再実行する
1. memory に残す場合は `log_agent_learning.py` で短い observation に圧縮し、raw chat を貼らない
1. `evaluate_agent_run.py --write` が `AGENT_EVALUATION_STATUS=pass` になるまで closeout しない

この loop は「最終 retrospective で思い出す」ものではなく、フィードバックを受けた時点で実行する作業です。`runtime_feedback=observed` があるのに improvement decision がすべて `not_applicable` の run は、agent evaluation で revise になります。

### Hook And Tool Protocol Feedback

hook、code checker、static analysis、CI、tool validation の結果は、pass / fail の記録だけで閉じません。
parent は結果を見た時点で、次の route に分類します。

- product fix: 直接の実装、文書、設定、test を直す
- tool / eval update: checker、hook、eval rubric、workflow monitor token を直す
- parent protocol update: `AGENTS.md`、`agents/canonical/CODEX_WORKFLOW.md`、関連 workflow / skill を直す
- subagent protocol update: `agents/canonical/CODEX_SUBAGENTS.md`、`.codex/agents/*.toml`、handoff packet、role prompt を直す
- durable issue / memory: `issues/open/`、`memory/AGENT_PHILOSOPHY.md`、`notes/failures/` に昇格する
- no-op: task-local noise と判断し、理由を evidence として残す

subagent が hook / tool failure の種類を見逃した、または handoff に必要な checker evidence が入っていなかった場合、parent は chat 上の注意だけで済ませません。
該当 role TOML、`CODEX_SUBAGENTS.md`、workflow family prompt、または handoff packet を更新するか、`subagent_protocol_update=not_required` と理由を記録します。

behavior eval 用の必須 token セットは次です。

```text
hook_tool_feedback=reviewed
parent_protocol_update=<applied|recorded|not_required>
subagent_protocol_update=<applied|recorded|not_required>
protocol_feedback_reason=<short-reason>
```

`not_required` は「何もしない」ではなく、結果を確認したうえで protocol 変更に昇格しない判断です。
`protocol_feedback_reason=` に、どの hook / tool 結果を見て、なぜ parent / subagent protocol を変えないかを書きます。

必須 signals:

- `skills=` または `$agent-orchestration` など、選択した skill surface
- stage owner、subagent routing、または `parent_direct_reason` / `trivial_direct_edit`
- repo dependency intake 結果、または `repo_dependency_intake_not_required`
- web research / external research 結果、または `web_research_not_required`
- behavior event: skill invocation、stage / subagent routing、tool gate、prompt eval、review feedback、subagent lifecycle、diff-check のいずれか
- runtime feedback event: `runtime_feedback=observed` または feedback が無い場合の `runtime_feedback_not_observed`
- hook / tool protocol feedback event: `hook_tool_feedback=reviewed` と parent / subagent protocol update decision

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
git grep -l "topic keywords" -- <responsibility-scoped dirs> \
  | sed -n '1,200p' > reports/search_hits.txt
wc -l reports/search_hits.txt > reports/search_hits.count
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
