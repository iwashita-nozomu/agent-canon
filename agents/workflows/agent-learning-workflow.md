# Agent Learning Workflow

<!--
@dependency-start
contract workflow
responsibility Routes agent-side recurrence learning to private knowledge/feedback, owners, Issues, failures, or evidence.
upstream design ../skills/agent-learning.md learning skill contract
upstream design ../../documents/runtime/private-feedback-knowledge.md external private log contract
upstream implementation ../../tools/runtime/archive/private_feedback.py metadata-only adapter
downstream implementation ../../tools/runtime/lifecycle/workflow_monitor.py runtime observation route
@dependency-end
-->

この workflow は、task中またはcloseoutで得た観測を、次回同じ問題に遭遇したときに使える
private knowledge / feedbackへ変換するrouteです。AgentCanon source treeへ本文を置かず、
private `agent-canon-log` をcontent ownerとします。

## 1. Classify Before Writing

観測は最初に次のいずれかへ分類します。

- raw chat、時系列、hook/event、run bundle evidence: runtime log/evidence owner
- actionable defectと修正action: repository-qualified GitHub Issue URL/number
- 再発したfailure pattern: `documents/notes/failures/`
- ownerを参照する独立したproblem-solving knowledge: private `agent-canon-log/knowledge/`
- repo-wide rule、workflow、stable preference: canonical ownerへの明示変更
- `documents/notes/knowledge/`: 人間向け短文資料であり、private logの代替ではない

一度きりの指示、既にownerに昇格した規約、user preferenceの複製はprivate knowledgeに
しません。安定したpreferenceは対象の`AGENTS.md`またはcanonical ownerへ直接変更します。

## 2. Search Before Create

search inputはkeywordだけでなく、決定済みのowner/path、failure evidence、recurrence
decisionから組み立てます。

```bash
agent-canon k search --query "repeated routing miss"
agent-canon k read <topic>
```

同じtopicなら同じtopicへ追加し、独立topicだけを新規追加します。private logの本文は
通常のreceipt、dashboard、Issue、PR、agent handoffへ出しません。検索・追加は外部runtime
rootに向け、source checkoutを書き換えません。

## 3. Record Private Knowledge or Feedback

```bash
printf '%s\n' "<evidence-backed reusable knowledge>" \
  | agent-canon k add <topic> --stdin
printf '%s\n' "<repair feedback>" \
  | agent-canon f add <topic> --stdin
agent-canon k status
agent-canon f status
```

`k/f` は外部private logのmetadata-only spoolを作り、host archive adapterが同期します。
ネットワークやarchive失敗時はspoolを残し、別のsource-tree writerやIssue mirrorを作りません。

## 4. Runtime Feedback and Behavior Evaluation

利用中のskill invocation、routing、review feedback、hook/tool gateは、必要なら
`workflow_monitor.py` のbehavior/runtime feedbackとしてraw evidence ownerに記録します。
prompt、workflow、evalの修理が必要なfeedbackはそのownerを更新し、private-log-onlyで閉じません。

### Behavior Events

agent behaviorは最終結果の要約ではなく、`workflow_monitor.py --behavior-event` で観測可能な
eventとして `## Behavior Events` に蓄積します。最低限、skill invocation、stage/subagent routing、
tool gate、prompt eval run、review feedback、subagent lifecycle、diff-check decisionを記録します。

```bash
python3 tools/runtime/lifecycle/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --behavior-event "skill_invocation=agent-learning status=observed"
```

### Runtime Feedback Closure Loop

user / reviewer / eval feedbackは `runtime_feedback=observed` を含むstructured eventとして
記録します。反映先はprompt、workflow、eval、private knowledge、Issue、またはno-opです。

```bash
python3 tools/runtime/lifecycle/workflow_monitor.py \
  --report-dir reports/agents/<run-id> \
  --runtime-feedback "source=user target=<skill-or-workflow-or-eval> action=<prompt_repair|eval_update|knowledge_record|no_op> runtime_feedback=observed evidence=<short-observation>"
```

active skillの挙動を示すfeedbackはactive skill setをfirst repair candidateとしてownerを確認します。
単発feedbackはscoped guidance、example、private knowledgeで足りるかを先に見て、hard ruleは
invariant、checker-backed、または反復観測された失敗に限ります。

`skill_improvement_decision=applied` はprompt/eval anchorを実際に変更して対応validationを
rerunした場合だけ記録します。private knowledgeへの記録は
`knowledge_learning_decision=recorded` とし、public skillの自動生成・catalog変更は行いません。

### Agent Run Evaluation

behavior evalのrubricは `eval/definitions/agent_behavior_eval.toml` を正本とします。
closeout前に `evaluate_agent_run.py` でbehavior manifestを指定して評価し、feedback actionsを
解決して `AGENT_EVALUATION_STATUS=pass` になるまで閉じません。

```bash
python3 eval/producers/evaluate_agent_run.py \
  --report-dir reports/agents/<run-id> \
  --behavior-manifest eval/definitions/agent_behavior_eval.toml \
  --write
```

## 5. Closeout

closeout packetには、分類（private knowledge update、private feedback、owner change、
Issue/failure/evidence/no-op）、search context、topic、validation resultを記録します。
raw chronologyやsource-treeへのprivate log mirrorを成功条件にしません。behavior events、
runtime feedback、feedback actions、improvement decisions、`AGENT_EVALUATION_STATUS=pass`を
closeout evidenceに含めます。
