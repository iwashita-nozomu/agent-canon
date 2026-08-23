# User Request Contract（user request 契約）
<!--
@dependency-start
contract template
responsibility Documents User Request Contract for this repository.
upstream design ../../agents/canonical/ARTIFACT_PLACEMENT.md artifact placement contract
@dependency-end
-->


- Run ID: {\{RUN_ID}}
- Task: {\{TASK}}
- Owner: {\{OWNER}}
- Created At (UTC): {\{CREATED_AT}}

{{>reader_map}}

## Gate Status（gate status）

- all_clauses_resolved: no
- forbidden_drift_detected: no
- deferred_clause_ids:
- unresolved_clause_ids:

## Requirements Resolution Sweep（要件解決 sweep）

<!-- open question を残す前に検索した accumulated context を記録します。memory、notes/themes、notes/guardrails、notes/knowledge、notes/failures、documents、prior log、local code、test、必要な external constraint を含めます。 -->

## Resolved From Accumulated Context（蓄積 context から解決）

| Clause ID | Resolved From | Evidence Path | Resolution | Remaining Risk |
| --------- | ------------- | ------------- | ---------- | -------------- |

## Must-Do Clauses（必須 clause）

| Clause ID | Source Bucket | User Wording Or Evidence | Operational Interpretation | Owner Stage | Evidence Path | Status |
| --------- | ------------- | ------------------------- | -------------------------- | ----------- | ------------- | ------ |

## Must-Not-Do Clauses（禁止 clause）

| Clause ID | Source Bucket | Forbidden Drift | Why It Is Forbidden | Guard Stage | Evidence Path | Status |
| --------- | ------------- | --------------- | ------------------- | ----------- | ------------- | ------ |

## Completion Evidence Clauses（完了 evidence clause）

| Clause ID | Source Bucket | Required Evidence | Where It Must Appear | Owner Stage | Status |
| --------- | ------------- | ----------------- | -------------------- | ----------- | ------ |

## Source Bucket Rules（source bucket 規則）

- Allowed buckets: `current_request`, `durable_user_preference`, `repo_or_code_precedent`, `domain_or_external_constraint`, `unknown_or_open_question`.
- durable user preference は current request または repo evidence が conversion を支える場合だけ task requirement にします。
- unknown は unresolved、deferred、escalated のまま扱い、silent assumption に変換しません。
- active must-do、must-not-do、completion-evidence clause に `unknown_or_open_question` を使わず、解決後の unresolved item は Deferred Or Rejected Clauses に移します。
- accumulated note、repo doc、local code、test、prior log で user intent を変えずに解決できるなら、最初の ambiguity で停止しません。

## Deferred Or Rejected Clauses（deferred/rejected clause）

| Clause ID | Reason | Escalation Or Follow-Up Path | Status |
| --------- | ------ | ---------------------------- | ------ |

## Update Rule（更新規則）

- planning、design、implementation、review の各 artifact は covered clause ID を引用します。
- active work が少なくとも 1 つの must-do clause に対応しなければ、続行せず stop and escalate します。
- すべての must-do/completion-evidence clause が解決し、must-not-do clause が clean になるまで closeout を lock します。
