# agent-learning

<!--
@dependency-start
contract skill
responsibility Owns AgentCanon agent-side recurrence learning and routes private knowledge or feedback to the external log owner.
upstream design ../../documents/runtime/private-feedback-knowledge.md private log command and storage contract
upstream design ../../documents/operations/notes-lifecycle.md failed verification record and topic reuse
upstream implementation ../../tools/runtime/archive/private_feedback.py metadata-only private log adapter
downstream implementation ../../tools/runtime/lifecycle/workflow_monitor.py runtime feedback evidence
@dependency-end
-->

## Reader Map

- Purpose: agent-side recurrence、routing miss、skill gap、task retrospectiveを、外部
  private `agent-canon-log` の knowledge / feedback ownerへ送る。
- Use when: agent behaviorへのFB、失敗した検証の保存、既存の失敗知見の再利用、または
  private FB・知見の記録依頼があるとき。
- Boundary: raw chat、時系列 runtime observation、Issue、公開可能なfailure logは各ownerに置く。
  恒久契約はcanonical ownerへ直接昇格する。

This skill owns behavior feedback, active-skill calibration, and behavior
evaluation routing. Private knowledge is one route among those owners; it is
not a second public canon and is never stored in the AgentCanon source tree.

## Purpose

privateへ記録する観測は、まず`k search`で既存topicを検索し、同じ問題なら同じtopicへ
追記します。独立した問題解決知識を外部`agent-canon-log/knowledge/`に残し、安定した契約は
対象のskill、workflow、AGENTS、またはcanonical documentへ直接反映します。
公開可能な失敗検証は[Notes Lifecycle](../../documents/operations/notes-lifecycle.md)の
既存topic memoへ接続します。

## Use When

- userが`agent-learning`または`$agent-learning`を明示した、またはFB・再利用する知見を
  記録するよう求めた。
- 検証で候補・設定・合成が失敗した、または採用・却下前に既存の失敗知見を参照する。
- agent behavior、routing、skill invocation、review feedback、task retrospectiveに
  次回の実行を変える再発防止判断がある。
- 既存ownerに昇格済みでない、独立したprivate knowledgeまたはfeedbackがある。

Stable user preferenceは対象の[AGENTS.md](../../AGENTS.md)またはcanonical ownerへ反映します。
単発の観測はruntime log/evidence/Issue owner、再利用する検証結果はtopic recordが所有します。

## Core References

- [documents/runtime/private-feedback-knowledge.md](../../documents/runtime/private-feedback-knowledge.md)
- [documents/operations/notes-lifecycle.md](../../documents/operations/notes-lifecycle.md)
- `tools/runtime/archive/private_feedback.py`
- `tools/runtime/lifecycle/workflow_monitor.py`
- `eval/definitions/agent_behavior_eval.toml`

## Mandatory Behavior and Learning Contract

- user preferenceとagent-side learningを分け、raw transcriptを貼らず、source、evidence、
  scope、confidenceを持つ短いobservationに圧縮する。
- `workflow_monitor.py` が所有する behavior-event の記録を使い、skill invocation、subagent
  routing、tool gate、prompt eval、review feedback、subagent lifecycle、diff-check decision
  を behavior evidence として扱う。この skill は event schema や append 処理を再定義しない。
- user / reviewer / eval feedback は `workflow_monitor.py` の runtime-feedback route で記録し、
  source、target、選択した action、観測内容を event owner の schema に従って構造化する。
  この skill は target と action の判断を行うが、feedback event の field や status vocabulary
  を再定義しない。
- feedbackが利用中のskillの弱さ、浅さ、遅さ、routing miss、修正不足を示す場合は、active
  skill setを最初の calibration 候補として owner と原因を確認する。変更する場合は対象、
  変更内容、validation evidence を記録し、変更しない場合はその判断根拠を記録する。
  単発観測は scoped guidance、example、private knowledge を優先し、hard rule は反復観測
  または checker-backed invariant に限る。特定の decision token を必須の完了条件にしない。
- private knowledgeへ記録した場合はその判断と根拠を残し、public skillへ自動昇格しない。
  behavior eval は `eval/definitions/agent_behavior_eval.toml` とその
  owner の評価結果を参照し、feedback action、calibration の判断、変更時の validation
  evidence が追跡できる状態を保つ。

## Operating Route

1. FBや失敗検証を観測したtask内で、目的・候補、source、再現条件、検証手順、期待と実際、
   evidence、確定した結論を短く整理する。[Notes Lifecycle](../../documents/operations/notes-lifecycle.md)
   のtopic recordを使い、観測と原因仮説を区別する。判断に必要な原因は同じtask内で調査・検証し、
   結論と根拠を同じtopicへ追記する。
2. private知識の保存・再利用では、同じcontextの正規実行口で
   `agent-canon k search --query <failure-evidence>` を実行し、hitを`k read <topic>`で読む。
   採用・却下前に既存topicの入力・版・設定・保証を現状と照合する。同じ前提の検証結果を
   再利用し、判断を変え得る前提が変わったときはその点を検証して結論を更新する。
   検索失敗・未実施を「既存topicなし」と扱わず、実際の失敗をCloseout Decisionへ接続する。
3. 選んだownerの記録操作を実行する。user / reviewer / eval feedbackの構造化は上記の
   runtime-feedback契約に従う。独立した修正用FBは `agent-canon f add <topic> --stdin`、
   再利用可能な問題解決知識は `agent-canon k add <topic> --stdin` を使う。
   既存captureを確認し、同じ観測をruntime-feedback、f、kへ重複登録しない。
   失敗検証には再現手順、期待と実際、evidence locator、検証で確定した結論、再利用条件と
   再検証が必要になる変更点を残す。後続の成功・反証は元のtopicへ接続する。
4. stable ruleをownerへ昇格する場合は、許可されたcanonical owner変更とreadbackを行い、
   private logへ規約を複製しない。既に反映済みなら、そのownerを根拠として再登録しない。
5. 今回の記録のreceipt、`k/f status`、targeted readbackを照合する。受付やspool保存を
   remoteへの同期完了と混同しない。同期が必要な場合だけ既存の `k/f sync` を実行し、
   その結果を読み戻す。全体statusや別の記録の成功から今回の成功を推定しない。
   記録・同期・確認の各結果はownerが返す既存identityに結び付け、新しいreceipt schemaを作らない。

既存captureがなく、独立したFBの記録を選んだ場合の例:

```bash
agent-canon k search --query "missing path owner resolution"
printf '%s\n' "観測、判断根拠、対応結果、次回の適用条件と限界" | agent-canon f add path-owner --stdin
agent-canon f status
```

未同期で正規経路が利用可能な場合だけ `agent-canon f sync` とstatusの再確認を行う。
knowledgeを選ぶ場合は `k add` を使い、`k read <topic>` で対象を確認する。
private本文は通常のreceipt、Issue、PR、dashboard、agent handoffへ転載せず、authorized locatorを使う。

## Evidence Boundary

- raw runtime event、chat transcript、日時付き観測: runtime archive / evidence owner
- actionable workflow defect: repository-qualified GitHub Issue
- 公開可能なfailed verification: `documents/notes/failures/` のtopic record
- reusable private knowledge / feedback: private `agent-canon-log`
- repo-wide permanent rule: canonical documents / [AGENTS.md](../../AGENTS.md)
- `documents/notes/knowledge/`: human-readable documentation。private情報はprivate logに保持する。

## Closeout Decision

今回の観測を、既存private knowledgeの更新、新規private feedback、ownerへの明示変更、
Issue/failure/evidence、またはno-opのいずれかに分類します。単なるchronologyや既にownerに
ある内容をprivate logへ重複保存しません。behavior feedbackは `prompt_repair`、`eval_update`、
`knowledge_record`、または `no_op` とimprovement decisionをcloseout evidenceに残します。

失敗した検証は、保存済みtopicの今回の内容を読み戻し、手順・結果・結論・再利用条件を
確認します。今回の採用・却下を裏付ける検証と記録を接続し、独立した失敗知見には記録操作を
実行します。報告は反映先と実行結果、保存・同期・readbackの確認範囲を示します。
`no_op` は同じ検証結果が保存済み等の根拠がある場合に限り、書込み不能の代替にしません。

実行口未検出、権限不足、検索・書込み・同期・readbackの失敗は、実際に確認した操作と結果、
未実施／未確認の範囲、次のowner/actionを既存の作業記録に残します。保存済みspoolは既存ownerの
保持・再試行規約に従い、未保存なら保存済みと報告しません。private本文を公開Issueやsource treeへ
退避させず、別の会話へ移ることを正規経路の代替にしません。無関係なruntime修理やeval全体の
再実行を記録依頼の前提にせず、記録できた結果と残るblockerを分けて引き継ぎます。

## Runtime Contract Clauses

1. Use Whenに該当する指摘・記録依頼・失敗検証では、Operating Routeを同じtask内で実行する。
2. behavior event、runtime feedback、feedback actionの記録先はexternal runtime / private log。
3. 採用・却下の前に関連topicを検索し、検証結果の適用条件を照合して判断へ再利用する。
4. prompt、workflow、eval、private knowledge、Issue、no-opの反映先、根拠、実行結果を明示する。
5. closeout前に behavior-eval owner の評価結果を参照し、feedback action、calibration の
   判断、変更時の validation evidence が解決または明示的に引き継がれていることを確認する。
