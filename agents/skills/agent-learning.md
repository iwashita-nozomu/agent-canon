# agent-learning
<!--
@dependency-start
contract skill
responsibility Documents agent-learning for this repository.
upstream design ../canonical/skills.md skill canon registry
@dependency-end
-->


## Reader Map

- Purpose: records agent-side lessons and recurrence-prevention notes without
  mixing task-local observations into user preferences.
- Use When: feedback concerns agent behavior, routing misses, retrospectives,
  repeated workflow mistakes, or skill invocation gaps.
- Section path: Purpose, Use When, and Core References set scope; Mandatory
  Checklist and Default Commands contain operational rules; Boundary defines
  what must not become memory.
- Boundary: durable user preference sync belongs to the preference route, not
  this learning log route.

## Purpose

agent の作業哲学、対話から得た学習、task retrospective を `memory/AGENT_PHILOSOPHY.md` に蓄積し、stable な項目だけを workflow や `AGENTS.md` へ昇格します。

## Use When

- user request が plain `agent-learning` または `$agent-learning` を挙げている
- user が agent の人格形成、作業哲学、対話からの継続学習を求めている
- user / reviewer feedback が agent 行動、routing miss、skill の呼び出し漏れ、
  関連 skill 候補の狭さ、再発防止、task retrospective、または agent-side
  memory update を要求している
- user / reviewer feedback が、test を pass させるために agent が intended
  behavior を単純化、revert、削除、oracle weakening したこと、または test planning
  を過剰に重視して owning code repair を止めたことを指摘している
- user / reviewer feedback が、algorithm repair で test 変更や expected value
  変更から着手し、algorithm contract、public entrypoint、recurrence / state
  transition、invariant、stopping / acceptance rule、failure semantics、code-side
  repair route の確定が遅れたことを指摘している
- task closeout で、次回以降の agent 行動を変える観測がある
- run bundle を評価し、agent feedback action を closeout 前に潰したい
- `USER_PREFERENCES.md` には入らない agent-side の学習を残したい
- raw chat ではなく、evidence 付きの短い observation として残したい
- self-learning と対話記録の追記を shared canon 側の責務として閉じたい

## Core References

- `agents/workflows/agent-learning-workflow.md`
- `memory/AGENT_PHILOSOPHY.md`
- `memory/USER_PREFERENCES.md`
- `notes/guardrails/engineering_avoidances.md`
- `documents/notes-lifecycle.md`
- `agents/workflows/workflow-references.md`
- `tools/agent_tools/log_agent_learning.py`
- `tools/agent_tools/evaluate_agent_run.py`
- `tools/agent_tools/workflow_monitor.py`
- `evidence/agent-evals/agent_behavior_eval.toml`

## Mandatory Checklist

- user preference と agent-side learning を分ける
- raw transcript を貼らず、短い observation に圧縮する
- source、evidence、scope、confidence を書く
- task-local な一時指示を stable philosophy にしない
- `evaluate_agent_run.py --write` で `agent_evaluation.md` を作り、feedback action を closeout 前に解決する
- eval / hook / skill feedback の結果を書き出すときは `result-artifact-writeout` を使い、raw evidence、summary、manifest、unique artifact path を分ける
- `workflow_monitor.py --behavior-event` で skill invocation、subagent routing、tool gate、prompt eval、review feedback、subagent lifecycle、diff-check decision を run 中に蓄積する
- 利用中に得られた user / reviewer feedback は `workflow_monitor.py --runtime-feedback "source=<user|reviewer|eval> target=<skill-or-workflow-or-eval> action=<prompt_repair|eval_update|memory_record|no_op> ..."` で構造化し、skill prompt、workflow prompt、eval、memory のどれへ還元したかを残す
- feedback が利用中の skill の弱さ、浅さ、遅さ、routing miss、または修正不足を指摘している場合は、active skill set を first repair candidate として owner を確認する。固定する前の calibration step では、指摘をどの強さで反映するかを決める。単発の観測は scoped guidance や example に留められるかを先に見る。hard rule は invariant、checker-backed、または反復観測された失敗に限る。skill prompt を変える場合は、discoverable runtime `SKILL.md` と canonical `agents/skills/<skill>.md` をそろえ、対応する prompt eval を更新または確認する
- test を pass させるための simplification、revert、intended behavior deletion、
  oracle weakening、または test planning の過剰重視で owning code repair が止まる
  feedback は、`test-design` と
  implementation workflow への active skill feedback として扱う。
  `workflow_monitor.py --runtime-feedback` で
  `target=test-design` または implementation workflow を指し、
  `action=prompt_repair|eval_update` を記録して prompt、eval、または tool repair
  で解決する。memory-only で閉じない
- algorithm repair で test 変更から入ったという feedback は、
  `computational-optimization`、`algorithm-proof-exploration`、`test-design`、
  および implementation workflow への active skill feedback として扱う。
  algorithm contract と code-side repair route を先に置く prompt repair で解決し、
  memory-only で閉じない
- input token 過多、context の重複読み込み、raw log の再投入、広い prose の model 投入が feedback された場合は、active routing / context skill を first repair candidate にする。owner / dependency evidence は落とさず、構造読み込みを protocol-owned `Structure Intake Packet` へ寄せ、重複または bulky な raw material を artifact と構造要約へ移す prompt repair として扱う。必要 context の省略を一般 rule にしない
- active skill feedback で `skill_improvement_decision=applied` と記録できるのは、対象 skill prompt または eval anchor を実際に変更し、対応 validation を rerun した場合です。memory-only や issue 化だけの場合は `recorded` にする
- behavior eval は `evidence/agent-evals/agent_behavior_eval.toml` を正本にし、`AGENT_EVALUATION_STATUS=pass` まで feedback action を閉じる
- `memory/` への追記を template local artifact や submodule dirty state だけで終わらせず、`persist_agent_memory.py` で shared canon commit / push と template pin 更新まで closeout する
- promotion candidate は `AGENTS.md` へ直書きせず、periodic sweep で昇格する
- 確定した禁止事項は `engineering_avoidances.md` への昇格候補にする

## Default Commands

```bash
python3 tools/agent_tools/evaluate_agent_run.py \
  --report-dir reports/agents/<run-id> \
  --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml \
  --write
```

```bash
python3 tools/agent_tools/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --behavior-event "skill_invocation=$agent-learning status=observed"
```

```bash
python3 tools/agent_tools/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --runtime-feedback "source=user target=.agents/skills/<active-skill>/SKILL.md action=prompt_repair evidence=<short-observation>"
```

```bash
python3 tools/agent_tools/log_agent_learning.py \
  --kind interaction-observation \
  --statement "<agent-side learning>" \
  --source chat \
  --evidence "<short evidence>" \
  --scope repo-wide \
  --confidence tentative
```

```bash
python3 tools/agent_tools/log_agent_learning.py \
  --kind task-retrospective \
  --statement "<what should change next time>" \
  --source closeout \
  --evidence "<task/run/commit>" \
  --scope task-family \
  --confidence tentative
```

```bash
python3 tools/agent_tools/persist_agent_memory.py \
  --commit \
  --push \
  --commit-superproject \
  --push-superproject
```

## Boundary

- user の coding preference は `user-preference-sync` を使います。
- failure として確定した禁止事項は `notes/guardrails/engineering_avoidances.md` へ移します。
- 文献調査で学習 workflow を変える場合は `literature-survey` も使います。
