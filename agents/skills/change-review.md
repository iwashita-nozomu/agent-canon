# change-review
<!--
@dependency-start
contract skill
responsibility Documents change-review for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/rule/README.md document rule canon
upstream design ../../documents/design/README.md design canon reader route
upstream design ../../issues/README.md durable issue and GitHub mirror policy
upstream design ../internal-routines/design-implementation-correspondence.md forward/reverse design correspondence and drift block route
upstream design ../../documents/design/request-intent-and-update-relation.md compact request/update and related-document closure flow
@dependency-end
-->


## Reader Map

design-backed diff の review input は、
`../internal-routines/design-implementation-correspondence.md` の clause
fingerprint と forward/reverse coverage です。この skill は findings-first
review の owner であり、universal correspondence policy は複製しません。

### Related Document Closure projection

review packet は DIC `DIC-010` の path+section+clause/ref closure receipt を読み、changed
path から design/projection drift を reverse に確認します。closure traversal は DIC が所有します。
review operation はこの receipt、changed path、design clause を結合し、forward/reverse
coverage-complete state に到達します。completion evidence は design fingerprint、owner
mapping、implementation target、validation route、そして changed path から design clause
への reverse trace の readback です。実装 worker が先に読んだ design と closure packet を
この reverse trace の基準にします。

- Purpose: reviews code, docs, or generated diffs with findings first,
  prioritizing regressions, missing tests, and broken assumptions.
- Use When: a change needs review before acceptance, especially after AI
  generation, implementation slices, or documentation updates.
- Section path: Purpose, Use When, and Core Reference orient scope; Expected
  Outcome, Mandatory Checklist, Default Sequence, and Findings Buckets are the
  operational review rules; Boundary limits review authority.
- Boundary: review findings must be grounded in changed files and validation
  evidence, not broad style preference.

## Purpose

diff を findings-first で読み、回帰、欠落テスト、古い文書を洗います。

## Use When

- code review
- doc review
- AI-generated diff review

## Core Reference

- `documents/conventions/REVIEW_PROCESS.md`

## 文書正本

文書の filename、配置、構成判断は
[`documents/rule/README.md`](../../documents/rule/README.md) を参照します。
個別の target state と実装境界は
[`documents/design/README.md`](../../documents/design/README.md) を参照します。
詳細規則はこの review skill に複製しません。

## Expected Outcome

- findings が summary より先に並んでいる
- `fix now` と `follow-up` が分かれている
- `revise`、`required_change`、rejected diff、requested-change review が user
  request を戻す権限として扱われていない。各 finding は保持する request clause
  または design intent を示し、修正、再設計、または escalation に接続している
- 各 finding に `issue_route` があり、既存 issue、new local issue、
  GitHub mirror plan、または run-local resolution のいずれかへ分類されている
- review で見ていない範囲や validation gap が残っている
- reviewer output is a set of hypotheses, not edit, revert, or publication
  authority. Parent / integration owner adjudicates every hypothesis.
- one owning review gate covers the claims in one replaceable responsibility.
  Add a specialist only for a distinct unresolved claim or risk that the owning
  gate cannot judge.

## Mandatory Checklist

- 実際の diff を先に読んでいる
- change set の意図と影響範囲を把握している
- current source snapshot, reachable input/control path, violated
  request/design/behavior contract, and a witness or static proof are present
  before a finding can be accepted.
- reject hypotheses that are unreachable under type/schema/parser/compiler/static
  invariants, use a stale snapshot, concern a private/incidental detail, duplicate
  an existing finding, lack a witness, fall outside the owner/request contract,
  or conflict with approved design without proving it incorrect. Rejected rows
  carry `reason_code` and `evidence_ref` and do not open a wave or cause rollback.
- `bash tools/agent_tools/run_repo_dependency_review.sh` を全 repo に対して実行するのは、選択された最終候補の責務がその review を必要とするときだけとし、静的解析・targeted validation を先に選ぶ
- 回帰、欠落テスト、stale documentation を優先して見ている
- 必要な validation が走っているか、未実行なら明記している
- validation failure を受けた修正では、pass 目的の単純化、revert、intended
  behavior / test 削除、oracle weakening、validation downscope が入る前に
  `failing_contract`、`observation_level`、`cause_classification`、
  `intent_preservation`、`evidence` が記録されているかを確認する。
  `intent_preservation` は same-intent repair / escalation route を示す。finding は
  approved intent を保持する repair、test / design evidence 修正、owner route、
  residual route、または escalation に接続する
- blanket revert / discard を既定の required action にしない。revert /
  discard を求める場合は、該当 clause が撤回または置換された、canonical
  owner 外だった、または危険で同じ意図の代替修正や escalation に接続した
  evidence を添える
- Python の class、dataclass、`Protocol`、継承、public API、型境界、依存方向を触る diff は `python-review` と `$oop-readability-check` の対象にし、`check_solid_evidence.py` で OOP readability report の path coverage と SOLID principle signal を確認している
- `fix now` と `follow-up` finding には `issue_route` を付けている。
  現在の diff で閉じるものは `run_local_resolution:<evidence>`、
  durable に残すものは `existing_issue:<path-or-url>` または
  `new_local_issue:<issues/open/AC-YYYYMMDD-slug.md>`、
  GitHub 可視化が必要なものは `github_mirror:<issue_sync.py command-or-url>`
  を選ぶ
- durable finding を作る場合は `issues/README.md` の required fields と
  `issue_sync.py` の mirror route を使う
- `no findings` の場合でも residual risk を残している
- validation is static/targeted first. Full suites or remote CI run once for the
  final candidate only when the touched contract requires them.

## Default Sequence

1. `git diff --stat` と `git diff --name-only` で変更面を固定します。
1. 破壊的変更、削除、rename、config 変更を先に見ます。
1. docs と tests が実装に追随しているか確認します。
1. Python の class、dataclass、`Protocol`、継承、public API、型境界、依存方向が変わる場合は `python-review` を追加し、`$oop-readability-check` と `check_solid_evidence.py` の evidence を review input にします。
1. まず static checks と targeted validation を実行し、full repository
   dependency review、full suite、remote CI は最終候補の契約が選択した場合だけ一度実行します。
1. findings を hypothesis として priority 順に並べ、current snapshot、reachable
   path、contract、witness/static proof を付けます。parent / integration owner が
   accept または reject を adjudicate します。
1. 各 finding に `issue_route` を付けます。現在の review loop で閉じるものは
   `run_local_resolution`、運用上残すものは既存 `issues/open/` または新規
   local issue、外部 triage が必要なものは `issue_sync.py` による GitHub mirror
   plan へ接続します。
1. summary は findings の後に短く付けます。

## Findings Buckets

- `fix now`
- `follow-up`
- `delete-ok`
- `rejected` (requires `reason_code` and `evidence_ref`; no repair/review wave)

Finding rows include:

- `severity`
- `evidence`
- `required_action`
- `intent_preservation`
- `issue_route`
- `rerun_review_required`
- `snapshot_ref`
- `reachable_path`
- `contract_ref`
- `witness_or_static_proof`
- `adjudication` (`accepted` or `rejected`)
- `reason_code` and `evidence_ref` for rejected hypotheses

Only an accepted finding that changes requested behavior, owner/design boundary,
correctness, validation, or publication state opens same-owner rework. Duplicate,
stylistic, already-covered, or evidence-free findings are recorded as rejected
and do not create a new wave.

## Boundary

- Python 差分で型と test を強く見る場合は `python-review` を追加します。
- Python 差分が SOLID-sensitive boundary を持つ場合は `python-review` と `$oop-readability-check` を追加し、`python3 tools/agent_tools/check_solid_evidence.py --root . <changed-python-paths> --evidence <oop-readability-report>` の結果を review evidence に含めます。
- C / C++ 差分で build、header、ownership を強く見る場合は `cpp-review` を追加します。
