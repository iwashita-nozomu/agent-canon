# GitHub status lifecycle

<!--
@dependency-start
contract agent-runtime
responsibility Defines deterministic GitHub Issue status-label lifecycle reconciliation, evidence, concurrency, and readback requirements.
upstream design ../../documents/conventions/software-engineering-principles.md shared correctness, ownership, failure, and traceability precedence
upstream design ../../issues/README.md durable issue-file and GitHub mirror convention
downstream design ../skills/pr-processing.md invokes this routine inside the GitHub publication boundary
downstream implementation ../../.agents/skills/_github-status-lifecycle/SKILL.md exposes this routine as a private runtime skill
@dependency-end
-->

## Reader Map

この文書は、repository-changing task に結び付く GitHub Issue の status label を、
観測済み状態から望ましい状態へ決定論的に収束させる内部 routine の正本です。
最初に `Activation Gate` と `Responsibility Boundary` を読み、次に
`Lifecycle Model`、`Reconciliation Algorithm`、`Failure Semantics` を使います。

この routine は GitHub publication 全体を所有しません。`pr-processing` が fresh remote
state、write authority、Issue / PR publication、mutation 後の remote readback を所有し、
この routine は status class、managed-label 差分、証拠の十分条件、競合時の停止条件を
所有します。

## Activation Gate

次をすべて満たす場合だけ active です。

1. repository-changing work に対応する GitHub Issue が確定している。
2. user request または repository policy が Issue status label の変更を要求している。
3. `pr-processing` が mutation 対象、fresh remote state、write authority を確認している。

GitHub-only read inspection、一般的な PR review、Issue triage、GitHub Projects の field 更新、
label taxonomy の設計だけでは active にしません。Issue が確定していない状態で候補 Issue
を推測したり、status label を新規作成したりしません。

## Responsibility Boundary

| Surface | Owner | This routine owns | This routine does not own |
| --- | --- | --- | --- |
| Issue / PR fresh state | `pr-processing` | status 計算に必要な observed snapshot の入力条件 | Issue / PR discovery、queue planning、mergeability 判定 |
| Write authority | `pr-processing` | authority がない場合の停止条件 | permission 取得、approval、merge |
| Status lifecycle | this routine | lifecycle classification、managed set、forbidden combinations | repository 固有 label taxonomy の定義 |
| Evidence comment | this routine | 必須 evidence fields、retry identity、gap completeness | 実装・検証結果そのものの生成 |
| Label mutation | `pr-processing` publication adapter | ordered remove/add plan と成功条件 | GitHub API adapter、label 作成、Issue close |
| Validation | changed-surface owner | completed / unavailable の admission 判定 | test command や validation policy の再定義 |
| Durable issue mirror | `issues/README.md` | status comment から mirror / PR へ辿れる要求 | issue-sync serialization と GitHub mirror protocol |

## Logical Inputs

この routine は永続 schema を新設しません。caller が次の論理入力を fresh snapshot として
渡します。

- Issue locator: repository と Issue number。
- label mapping: `active`、`ready_for_review`、`needs_verification` に対応する、repository が
  既に定義した exact label name。
- observed labels: mutation 直前に読み取った Issue の全 label。
- lifecycle facts: work started、handoff ready、selected validation complete、verification
  unavailable の事実。
- trace evidence: baseline、branch、head commit、PR、changed scope、実行済み validation、結果。
- verification gap: 未検証 property、理由、試行内容、観測結果、必要な環境または owner、次の
  verification command。
- mutation authority と readback route。

label mapping の 3 値は nonempty、pairwise distinct、Issue repository に既存でなければ
なりません。AgentCanon repository での現在の対応例は
`status:in-progress`、`status:ready-for-review`、`status:needs-verification` ですが、
この文字列を他 repository の既定値として hard-code しません。

## Lifecycle Model

managed label set を

```text
M = {active_label, ready_for_review_label, needs_verification_label}
```

とし、Issue の observed managed state を

```text
O = observed_labels ∩ M
```

とします。unrelated labels は status reconciliation の対象外です。

### States

| Lifecycle state | Admission facts | Desired managed set `D` | Forbidden managed labels |
| --- | --- | --- | --- |
| `active` | work started、handoff not ready | `{active_label}` | ready、needs verification |
| `review-ready` | handoff ready、selected validation complete、unavailable gap なし | `{ready_for_review_label}` | active、needs verification |
| `review-ready-unverified` | handoff ready、実装は引継ぎ可能、必要な verification が外部要因で unavailable、gap が完全 | `{ready_for_review_label, needs_verification_label}` | active |

routine が active でない read-only / triage 状態には desired managed set を割り当てません。
既存 status を「整理目的」で勝手に変更しないためです。

### Admission Rules

- `active` は code / document edit を開始したが、変更と handoff evidence がまだ完成していない
  状態です。部分 validation が成功していても handoff ready でなければ `active` のままです。
- `review-ready` は実装、選択済み validation、trace evidence が揃い、他者が review / merge
  判断を引き継げる状態です。
- `review-ready-unverified` は実装が handoff ready で、未検証部分が implementation defect
  ではなく environment、permission、hardware、billing、external service などの unavailable
  reason に分類され、具体的な gap が記録された場合だけ許可します。
- failing validation、未修正 finding、unknown failure、再現不能な実装不具合を
  `needs-verification` に置き換えて handoff ready と扱いません。その場合は `active` または
  blocked work として残します。
- `needs_verification_label` は単独で使いません。これは reviewable implementation に残る
  verification obligation を表すため、必ず `ready_for_review_label` と共存します。

## Invariants

- `GSL-001` managed state は上表の 3 集合のいずれか、または routine 非活性時の未管理状態です。
- `GSL-002` `active_label` は ready / needs-verification と同時に存在しません。
- `GSL-003` `needs_verification_label` は `ready_for_review_label` なしでは存在しません。
- `GSL-004` unrelated labels、assignees、milestone、Issue state は変更しません。
- `GSL-005` label name は repository の既存 taxonomy から解決し、暗黙作成、rename、色変更をしません。
- `GSL-006` final transition の前に Issue から branch、head、PR、validation、remaining risk を
  辿れる evidence comment が存在しなければなりません。
- `GSL-007` desired state は lifecycle facts から計算し、現在 label の toggle や直前操作の
  成否から推測しません。
- `GSL-008` 同じ desired state、head、evidence に対する再実行は managed labels と evidence
  comment を増やさない no-op になります。
- `GSL-009` fresh read 後の concurrent managed-state drift は自動上書きせず、再評価を要求します。
- `GSL-010` mutation 後の readback が `O == D` を満たすまで success を報告しません。
- `GSL-011` API / permission / network の部分失敗を validation pass または publication success
  に変換しません。
- `GSL-012` Issue close、PR approval、PR merge は明示された別 operation であり、この lifecycle
  transition の副作用にしません。

## Evidence Comment Contract

### Required fields

最終 status transition より前に、Issue comment が次を持つ必要があります。

| Field | Required content |
| --- | --- |
| lifecycle | target state と managed labels |
| baseline | branch 起点の base ref と commit SHA |
| branch | Issue number を含む active branch |
| head | evidence が対応する exact commit SHA。commit 前なら current branch と未commit理由 |
| PR | PR URL / number。未作成なら branch から辿れることと PR 未作成理由 |
| scope | changed owner surface と明示的 non-goals |
| validation | command / check、対象 property、pass / fail / unavailable の区別 |
| remaining verification | 未検証 property、reason class、attempt、observed result、required environment / owner、next command |
| readback expectation | mutation 後に期待する exact managed label set |

`review-ready` では remaining verification を `none` と明示します。
`review-ready-unverified` では gap の各 field を省略できません。単に「CI 未確認」や
「環境依存」と書くだけでは admission 条件を満たしません。

### Retry identity

同一 evidence comment の再利用 key は
`(repository, issue number, target lifecycle, branch, head, validation result set)` です。
retry 前に既存 comments を読み、key と evidence payload が一致する comment があれば再利用します。
head または validation result が変わった場合は historical comment を上書きせず、新しい evidence
comment を追加します。これにより履歴を保持しつつ、同一 operation の再実行で重複を増やしません。

## Reconciliation Algorithm

### 1. Preflight

1. Issue、全 labels、関連 PR / branch、comments を fresh read する。
2. write authority、Issue identity、label mapping の存在・一意性を確認する。
3. lifecycle facts を changed-surface owner の evidence から分類する。
4. target lifecycle と desired managed set `D` を一意に計算する。
5. evidence comment を既存 comment から再利用するか、新規追加する。

### 2. Concurrency readback

comment の追加または再利用後、Issue labels を再読します。最初の observed managed set から
他 actor による drift があれば mutation を開始せず、`concurrent_status_drift` として停止します。
caller が fresh facts と authority を再評価した後だけ新しい reconciliation を開始します。

### 3. Difference

fresh observed managed set を `O` として、操作集合を次で求めます。

```text
remove = O - D
add    = D - O
```

`remove` と `add` がともに空なら label mutation は no-op です。evidence key が一致する comment
も既に存在すれば、operation 全体が no-op になります。

### 4. Safe mutation order

GitHub adapter が managed labels だけを原子的に置換でき、fresh unrelated labels を保存できる場合は
単一 mutation を使えます。個別 remove/add の場合は、中間状態で forbidden combination を作らない
次の順序を使います。

1. target が `active` の場合、ready と needs-verification を除去してから active を追加する。
2. target が `review-ready` の場合、active と needs-verification を除去してから ready を追加する。
3. target が `review-ready-unverified` の場合、active を除去し、ready を追加または保持してから
   needs-verification を追加する。
4. unrelated labels は full replacement せず、常に保存する。

途中失敗では次の操作へ進まず、exact observed labels を再読します。temporary no-status state は
conflicting status state より安全ですが、final success ではありません。

### 5. Final readback

mutation 後に Issue を再読し、次をすべて確認します。

```text
observed_labels ∩ M == D
unrelated_labels_after == unrelated_labels_before
required_evidence_comment_exists == true
```

一致した場合だけ target lifecycle を報告します。不一致なら observed / desired / completed
operations / failed operation / next safe action を Issue comment または caller result に残します。

## Failure Semantics

| Failure | Meaning | Required action |
| --- | --- | --- |
| `issue_unresolved` | target Issue が一意でない | mutation せず Issue identity を解決する |
| `label_mapping_invalid` | label が absent、empty、重複 | taxonomy owner に戻し、label を暗黙作成しない |
| `authority_missing` | write permission / user authority がない | read-only result と必要権限を報告する |
| `lifecycle_facts_incomplete` | handoff / validation / gap 判定が不足 | `active` を勝手に解除せず evidence を補完する |
| `verification_gap_incomplete` | unavailable property の具体情報がない | `review-ready-unverified` を拒否する |
| `implementation_failure_disguised_as_unavailable` | failing implementation を環境問題として扱っている | implementation owner に戻し `active` を維持する |
| `evidence_comment_failed` | trace comment を publication できない | final label transition を開始しない |
| `concurrent_status_drift` | preflight 後に managed labels が変化 | mutation せず fresh facts / authority を再評価する |
| `mutation_partial` | remove/add の途中で API failure | exact remote state を再読し、成功を報告しない |
| `readback_mismatch` | final managed set または unrelated labels が不一致 | observed state と repair plan を残す |

failure を warning-only success に格下げしません。external API failure と repository implementation
failure は別分類にし、どちらも evidence なしに `ready-for-review` へ進めません。

## Examples

### Start repository-changing work

- baseline: latest `main` commit
- branch: Issue numberを含む新 branch
- facts: work started、handoff not ready
- desired: `{status:in-progress}`
- action: start evidence comment を残し、ready / needs-verification を除去して active へ収束する

### Validated handoff

- facts: implementation complete、selected validation pass、PR created
- desired: `{status:ready-for-review}`
- action: final evidence comment を先に残し、in-progress / needs-verification を除去して ready へ収束する

### Handoff with unavailable verification

- facts: implementation complete、focused static checks pass、required GPU check は compatible GPU runner
  不在で unavailable、next command と expected environment が記録済み
- desired: `{status:ready-for-review, status:needs-verification}`
- action: in-progress を除去し、ready を確保して needs-verification を追加する

### Failed validation

- facts: selected test failed、root cause 未修正
- result: `review-ready-unverified` には進めない
- action: `status:in-progress` を維持し、failure と次の実装修正を追跡する

### Retry after response loss

- facts: previous mutation response は失われたが、remote readback では desired labels と同一 evidence
  key の comment が存在する
- action: remove/add/comment はすべて no-op とし、readback evidence だけを返す

## Completion Output

caller は少なくとも次を返します。

- Issue URL / number
- target lifecycle
- observed managed set before / after
- added / removed labels
- evidence comment URL / id
- branch、head、PR
- validation summary と remaining verification
- readback result

この output は既存 `pr-processing` closeout に投影し、第二の PR queue、approval、merge、Issue close
workflow を作りません。
