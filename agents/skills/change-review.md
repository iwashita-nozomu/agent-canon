# change-review
<!--
@dependency-start
contract skill
responsibility Documents change-review for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../issues/README.md durable issue and GitHub mirror policy
@dependency-end
-->


## Reader Map

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

- `documents/REVIEW_PROCESS.md`

## Expected Outcome

- findings が summary より先に並んでいる
- `fix now` と `follow-up` が分かれている
- `revise`、`required_change`、rejected diff、requested-change review が user
  request を戻す権限として扱われていない。各 finding は保持する request clause
  または design intent を示し、修正、再設計、または escalation に接続している
- 各 finding に `issue_route` があり、既存 issue、new local issue、
  GitHub mirror plan、または run-local resolution のいずれかへ分類されている
- review で見ていない範囲や validation gap が残っている

## Mandatory Checklist

- 実際の diff を先に読んでいる
- change set の意図と影響範囲を把握している
- `bash tools/agent_tools/run_repo_dependency_review.sh` を全 repo に対して実行し、`--changed` だけで済ませていない
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

## Default Sequence

1. `git diff --stat` と `git diff --name-only` で変更面を固定します。
1. 破壊的変更、削除、rename、config 変更を先に見ます。
1. docs と tests が実装に追随しているか確認します。
1. Python の class、dataclass、`Protocol`、継承、public API、型境界、依存方向が変わる場合は `python-review` を追加し、`$oop-readability-check` と `check_solid_evidence.py` の evidence を review input にします。
1. `bash tools/agent_tools/run_repo_dependency_review.sh` を実行し、全 repo の dependency manifest coverage / format / graph を確認します。
1. findings を priority 順に並べ、evidence を付けます。
1. 各 finding に `issue_route` を付けます。現在の review loop で閉じるものは
   `run_local_resolution`、運用上残すものは既存 `issues/open/` または新規
   local issue、外部 triage が必要なものは `issue_sync.py` による GitHub mirror
   plan へ接続します。
1. summary は findings の後に短く付けます。

## Findings Buckets

- `fix now`
- `follow-up`
- `delete-ok`

Finding rows include:

- `severity`
- `evidence`
- `required_action`
- `intent_preservation`
- `issue_route`
- `rerun_review_required`

## Boundary

- Python 差分で型と test を強く見る場合は `python-review` を追加します。
- Python 差分が SOLID-sensitive boundary を持つ場合は `python-review` と `$oop-readability-check` を追加し、`python3 tools/agent_tools/check_solid_evidence.py --root . <changed-python-paths> --evidence <oop-readability-report>` の結果を review evidence に含めます。
- C / C++ 差分で build、header、ownership を強く見る場合は `cpp-review` を追加します。
