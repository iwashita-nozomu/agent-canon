# agent-learning

<!--
@dependency-start
contract skill
responsibility Owns AgentCanon agent-side recurrence learning and routes private knowledge or feedback to the external log owner.
upstream design ../workflows/agent-learning-workflow.md learning workflow and lifecycle
upstream design ../../documents/runtime/private-feedback-knowledge.md private log command and storage contract
upstream implementation ../../tools/runtime/archive/private_feedback.py metadata-only private log adapter
downstream implementation ../../tools/runtime/lifecycle/workflow_monitor.py runtime feedback evidence
@dependency-end
-->

## Reader Map

- Purpose: agent-side recurrence、routing miss、skill gap、task retrospectiveを、外部
  private `agent-canon-log` の knowledge / feedback ownerへ送る。
- Use when: recurrence decision、owner/path、failure evidenceを選べるとき。
- Boundary: raw chat、時系列 runtime observation、Issue、failure logは各ownerに置く。
  恒久契約はcanonical ownerへ直接昇格する。

This skill owns behavior feedback, active-skill calibration, and behavior
evaluation routing. Private knowledge is one route among those owners; it is
not a second public canon and is never stored in the AgentCanon source tree.

## Purpose

会話やtaskの観測をsource-treeにappendしません。まずprivate logの`k search`で既存topicを
検索し、同じ問題なら同じtopicへ`k add`または`f add`で追記します。独立した問題解決知識
だけを外部`agent-canon-log/knowledge/`に残し、安定した契約は対象のskill、workflow、
AGENTS、またはcanonical documentへ直接反映します。

## Use When

- userが`agent-learning`または`$agent-learning`を明示した。
- agent behavior、routing、skill invocation、review feedback、task retrospectiveに
  次回の実行を変える再発防止判断がある。
- 既存ownerに昇格済みでない、独立したprivate knowledgeまたはfeedbackがある。

Stable user preferenceはこのskillの第二正本にしません。安定したpreferenceは対象の
`AGENTS.md`またはcanonical ownerへの明示変更、単発の観測はruntime log/evidence/Issue
ownerへの記録です。

## Core References

- `agents/workflows/agent-learning-workflow.md`
- `documents/runtime/private-feedback-knowledge.md`
- `tools/runtime/archive/private_feedback.py`
- `tools/runtime/lifecycle/workflow_monitor.py`
- `eval/definitions/agent_behavior_eval.toml`

## Mandatory Behavior and Learning Contract

- user preferenceとagent-side learningを分け、raw transcriptを貼らず、source、evidence、
  scope、confidenceを持つ短いobservationに圧縮する。
- `workflow_monitor.py --behavior-event` でskill invocation、subagent routing、tool gate、
  prompt eval、review feedback、subagent lifecycle、diff-check decisionを記録する。
- user / reviewer / eval feedbackは `workflow_monitor.py --runtime-feedback` で
  `source=<user|reviewer|eval> target=<skill-or-workflow-or-eval>
  action=<prompt_repair|eval_update|knowledge_record|no_op> runtime_feedback=observed`
  として構造化する。
- feedbackが利用中のskillの弱さ、浅さ、遅さ、routing miss、修正不足を示す場合は、active
  skill setをfirst repair candidateとしてownerを確認する。単発観測はscoped guidance、
  example、private knowledgeを優先し、hard ruleは反復観測またはchecker-backed invariant
  に限る。
- `skill_improvement_decision=applied` は対象promptまたはeval anchorを変更し、対応validation
  をrerunした場合だけ記録する。private knowledgeへの記録は
  `knowledge_learning_decision=recorded` とし、public skillへの自動昇格はしない。
- behavior evalは `eval/definitions/agent_behavior_eval.toml` を正本とし、feedback action
  とimprovement decisionを解決して `AGENT_EVALUATION_STATUS=pass` にする。

## Operating Route

1. 現在のowner/path、failure evidence、recurrence decisionを選ぶ。
2. 同じcontextで `agent-canon k search --query <failure-evidence>` を読み取り実行する。
3. hitがあれば `agent-canon k add <topic> --stdin` または `agent-canon f add <topic> --stdin`
   で外部logへ記録する。hitがない独立topicだけ新規追加する。
4. stable ruleをownerへ昇格したら、実際のowner変更を別途行い、private logへ複製しない。
5. `k/f status` とtargeted readbackを実行する。本文は通常のreceipt、Issue、PR、dashboard、
   agent handoffへ出さない。

例:

```bash
agent-canon k search --query "missing path owner resolution"
printf '%s\n' "短い再発防止知識" | agent-canon k add path-owner --stdin
printf '%s\n' "修正に必要な feedback" | agent-canon f add path-owner --stdin
agent-canon k status
agent-canon f status
```

## Evidence Boundary

- raw runtime event、chat transcript、日時付き観測: runtime archive / evidence owner
- actionable workflow defect: repository-qualified GitHub Issue
- failure analysis: `documents/notes/failures/`
- reusable private knowledge / feedback: private `agent-canon-log`
- repo-wide permanent rule: canonical documents / `AGENTS.md`
- `documents/notes/knowledge/`: human-readable documentation only。private logの代替ではない。

## Closeout Decision

今回の観測を、既存private knowledgeの更新、新規private feedback、ownerへの明示変更、
Issue/failure/evidence、またはno-opのいずれかに分類します。単なるchronologyや既にownerに
ある内容をprivate logへ重複保存しません。behavior feedbackは `prompt_repair`、`eval_update`、
`knowledge_record`、または `no_op` とimprovement decisionをcloseout evidenceに残します。

## Runtime Contract Clauses

1. `agent-learning`または`$agent-learning`の明示要求、およびagent behavior、routing miss、
   missed skill invocation、recurrence prevention、task retrospectiveのfeedbackでこのskillを選ぶ。
2. behavior event、runtime feedback、feedback actionの記録先はexternal runtime / private log。
3. prompt、workflow、eval、private knowledge、Issue、no-opの反映先と根拠を明示する。
4. closeout前にbehavior manifestを使った `evaluate_agent_run.py --write` を実行し、
   `AGENT_EVALUATION_STATUS=pass` とfeedback action解決を確認する。
