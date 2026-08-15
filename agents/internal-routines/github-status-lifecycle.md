# GitHub status lifecycle

<!--
@dependency-start
contract agent-runtime
responsibility Defines deterministic GitHub Issue status-label lifecycle reconciliation, evidence, concurrency, and readback requirements.
upstream design ../../documents/conventions/software-engineering-principles.md shared correctness, ownership, failure, and traceability precedence
upstream design ../../documents/operations/issue-label-taxonomy.toml machine-readable repository label mapping
upstream design ../../issues/README.md durable issue-file and GitHub mirror convention
downstream design ../skills/pr-processing.md invokes this routine inside the GitHub publication boundary
downstream implementation ../../.agents/skills/_github-status-lifecycle/SKILL.md exposes this routine as a private runtime skill
downstream implementation ../../tools/agent_tools/github_status_lifecycle.py projects the transport and reconciliation contract
@dependency-end
-->

## Reader Map

この文書は GitHub Issue status-label reconciliation の意味論の正本です。
`pr-processing` が対象 Issue、fresh remote state、write authority、PR/Issue
publication を所有し、この routine は lifecycle classification、evidence admission、
ordered transition、observable concurrency stop、final predicate を所有します。
実装は `tools/agent_tools/github_status_lifecycle.py` の機械的投影であり、第二の
state machine や別の label taxonomy を定義しません。

## Activation Gate

次をすべて満たす場合だけ active です。

1. repository-changing work に対応する Issue が確定している。
2. user request または repository policy が status label mutation を要求している。
3. `pr-processing` が対象、fresh state、write authority を確認している。

Read-only inspection、通常の review、Issue triage、taxonomy 設計だけでは active に
しません。Issue や label を推測・新規作成しません。

## Responsibility Boundary

| Surface | Owner | This routine owns | This routine does not own |
| --- | --- | --- | --- |
| Issue / PR fresh state | `pr-processing` | status 計算に必要な入力条件 | Issue/PR discovery、queue planning、mergeability |
| Write authority | `pr-processing` | authority がない場合の停止条件 | permission、approval、merge |
| Status lifecycle | this routine | lifecycle、managed set、transition、final predicate | repository label taxonomy の定義 |
| Evidence comment | this routine | required fields、retry identity、duplicate/conflict stop | implementation/validation result の生成 |
| GitHub transport | `GhStatusAdapter` | snapshot、comment、single-label API、readback | lifecycle の意味論、full-label replacement |
| Label mutation publication | `pr-processing` | caller authority and publication readback | second transition table or predicate |
| Durable issue mirror | `issues/README.md` | comment から mirror/PR に辿れる要求 | issue-sync protocol |

`pr-processing` は target resolution、fresh initial read、authority、adapter invocation、
publication closeout のみを行います。mutation order、retry identity、success predicate
を再掲しません。

## Canonical label mapping

`documents/operations/issue-label-taxonomy.toml` が repository taxonomy の唯一の機械可読
owner です。`[status_lifecycle]` は `active`、`ready_for_review`、
`needs_verification` の3つの non-empty な canonical name と、
`[status_lifecycle.legacy_aliases]` の3つの optional string arrays を持ちます。
Parser は `tomllib`（Python 3.10 では repository precedent の `tomli` fallback）を使い、
unknown key、empty/duplicate name、canonical name と一致する alias を拒否します。

Tool は canonical name が remote label catalog に存在することを mutation 前に確認します。
不足は `label_mapping_invalid` とし、label の作成・rename・color 変更・推測をしません。
明示された legacy alias だけを managed set に含め、alias が remote catalog にないことは
勝手な必須 label として扱いません。unrelated labels は常に保存します。

## Lifecycle Model

| state | admission | desired canonical set `D` |
| --- | --- | --- |
| `active` | work started、handoff not ready または validation failure | `{active}` |
| `review-ready` | handoff ready、selected validation complete、gap なし | `{ready_for_review}` |
| `review-ready-unverified` | handoff ready、実装可、外部 unavailable gap が完全 | `{ready_for_review, needs_verification}` |

`needs_verification` は単独では使いません。implementation failure、failing/unknown
validation、未修正 finding は unavailable gap ではなく `active` または blocked work です。
desired set は現在の label toggle から推測しません。

## Evidence Comment Contract

final transition の前に、Issue comment は次を含みます: lifecycle、baseline、branch、exact
head、PR identity、changed scope と non-goals、validation command/result、remaining
verification の property/reason/attempt/observed result/environment/owner/next command、
mutation 後の readback expectation。

Body の marker は次の形式です。

```text
<!-- agent-canon:github-status-lifecycle:v1 key=sha256:<attempt-key> -->
```

Canonical payload は required evidence、exact PR identity、taxonomy mapping digest、fresh
preflight source snapshot digest を含みます。`evidence_payload_digest` は canonical JSON
の SHA-256、`attempt_key` は `{repo, issue, evidence_payload_digest, pr_identity,
source_snapshot_digest}` の canonical JSON の SHA-256 です。read timestamps と pagination
cursor は digest に含めません。

GitHub comment API には create-if-absent/CAS がありません。従って、既存の exact payload
1件は再利用し、同じ marker key の異なる payload は `evidence_conflict`、同じ payload の
複数件は `evidence_duplicate` として停止します。未作成なら POST を1回だけ行い、fresh
comment readback が exactly one になるまで進みません。POST 応答を失った場合に blind retry
しません。過去のコメントを自動編集・削除しません。

## Reconciliation Algorithm

1. `pr-processing` が対象/authority/初期事実を確定し、adapter が Issue snapshot、comments、
   repository label catalog を fresh read する。
2. taxonomy を parse し canonical labels の catalog presence を確認する。
3. facts から state と `D` を純粋に計算し、evidence comment を reuse または1回だけ create
   して readback する。
4. evidence 前の全 labels と直後の全 labels を比較する。不一致は
   `concurrent_status_drift` で、label mutation を開始しない。
5. `M = canonical labels ∪ declared aliases`、`O = observed ∩ M` とし、
   `remove = O - D`、`add = D - O` を順に計画する。full-label replacement は使いません。
6. 各 operation の直前に全 labels を read して前の expected state と比較し、single-label
   POST/DELETE を1回行い、直後に全 labels を read して次の expected state と比較します。
   mismatch、API error、unknown response は exact state と completed prefix を返して停止します。
7. 最後に Issue labels と comments を fresh read し、次の predicate が全て true の場合だけ成功します。

```text
observed_canonical_managed_labels == D
declared_legacy_aliases_absent
observed_unrelated_labels == initial_unrelated_labels
exact_evidence_payload_count == 1
```

GitHub に version/CAS token がないため、read-to-write gap と ABA (`A -> B -> A`) は観測
不能です。Tool はそれを exclusive ownership や CAS success と主張しません。

## Failure Semantics

全 typed failure は `code_owner` と `responsibility_scope` を含みます。主な code は
`issue_unresolved`、`authority_missing`、`label_mapping_invalid`、
`lifecycle_facts_incomplete`、`verification_gap_incomplete`、`evidence_conflict`、
`evidence_duplicate`、`evidence_readback_unavailable`、`concurrent_status_drift`、
`mutation_partial`、`readback_mismatch` です。transport error は
`github-api-transport`、lifecycle error は `status-label-lifecycle` として報告し、
環境失敗を policy failure に混ぜません。

`mutation_partial` は completed operations、failed/ambiguous operation、exact observed
labels、desired labels、unrelated before/after、`rollback=not-attempted`、
`next_action=fresh-reconcile-after-owner-review` を返します。rollback は同じ absent-CAS
問題を持つため自動実行しません。failure を warning-only success に格下げせず、Issue close、
PR approval、PR merge もこの routine の副作用にしません。

## Completion Output

成功結果は Issue、target lifecycle、before/after managed labels、added/removed labels、
evidence comment id/url、completed operations、fresh readback、`code_owner`、
`responsibility_scope` を返します。caller はこの result を既存 publication closeout に
投影し、第二の queue、approval、merge、close workflow を作りません。
