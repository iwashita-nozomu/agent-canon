<!--
@dependency-start
contract issue
responsibility Tracks deterministic GitHub Issue status lifecycle reconciliation and private runtime skill integration.
upstream design ../README.md durable issue-file convention and GitHub mirror policy
downstream design ../../agents/internal-routines/github-status-lifecycle.md canonical lifecycle, evidence, failure, and readback owner
downstream design ../../agents/skills/pr-processing.md public GitHub publication caller
downstream implementation ../../.agents/skills/_github-status-lifecycle/SKILL.md private runtime discovery shim
@dependency-end
-->

# [GitHub運用] Issue status lifecycle skill を追加する

issue_id: AC-20260815-github-status-lifecycle-skill
status: in_progress
source: user
severity: S2
problem: repository-changing task の GitHub Issue status label 遷移、証拠コメント、競合・部分失敗時の扱いが単一 owner を持たず、相反 label や追跡不能な handoff を生じ得る。
evidence: https://github.com/iwashita-nozomu/agent-canon/issues/719
done: private runtime skill が status を desired-state へ冪等に収束させ、Issue から branch、commit、PR、validation、remaining verification を追跡できる。
affected_surfaces: agents/internal-routines/github-status-lifecycle.md, .agents/skills/_github-status-lifecycle/SKILL.md, agents/skills/pr-processing.md, issues/open/AC-20260815-github-status-lifecycle-skill.md
edit_scope: owner-bounded
required_action: status lifecycle の正本と private runtime shim を追加し、pr-processing の publication boundary から責務を重複せず委譲する。
close_condition: PRがmergeされ、private skill discovery、dependency headers、Markdown、runtime alignment、issue mirror checkがpassしている。
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/719

## Current snapshot

- Baseline: `main@1ebe6726917d2d3d1edfea466adce602ff5ed60e`
- Active branch: `canon/github-status-lifecycle-719`
- Existing duplicate Issue / PR / branch: bounded searchで該当なし
- Existing public owner: `agents/skills/pr-processing.md`
- Current gap: fresh-state / authority / publication readback は存在するが、Issue status の desired-state reconciliation と evidence admission が一意化されていない

## Summary

GitHub Issue の status label 運用を、観測済み状態から望ましい状態へ冪等に収束させる AgentCanon skill を追加する。

## Current gap

`agents/skills/pr-processing.md` は Issue / PR の fresh-state 読み取り、authority 確認、publication readback を所有している。一方で、repository-changing task における次の status lifecycle は単一の owner を持っていない。

- 作業開始時に `status:in-progress` を付ける
- 実装と選択済み検証が完了したら `status:in-progress` を外し、`status:ready-for-review` へ遷移する
- 必要な検証を環境・権限・外部要因で実行できない場合は、handoff 可能な状態を保ったまま `status:needs-verification` と具体的な検証 gap を残す
- Issue から branch、commit、PR、validation、remaining risk を辿れる証拠コメントを残す
- 再実行時に label を toggle せず、同じ観測状態へ収束する

この責務が会話ごとの指示や個別 workflow に分散すると、相反する status label、未解除の `in-progress`、検証不能理由の欠落、成功したように見える部分更新が生じる。

## Ownership decision

公開 skill surface を増やす wrapper にはしない。GitHub status mutation は `pr-processing` の publication boundary 配下でのみ意味を持つため、次の runtime-internal skill として実装する。

- canonical owner: `agents/internal-routines/github-status-lifecycle.md`
- runtime shim: `.agents/skills/_github-status-lifecycle/SKILL.md`
- public caller: `agents/skills/pr-processing.md`
- durable mirror: `issues/open/AC-20260815-github-status-lifecycle-skill.md`

`pr-processing` は fresh remote state、write authority、publication adapter、final remote readback を引き続き所有する。新 routine は status class、desired managed-label set、安全な mutation order、evidence comment の十分条件、concurrency stop、exact success predicate だけを所有する。

## State model

Repository が定義する label 名を入力として、status class を次のように正規化する。

| Lifecycle state | Required labels | Forbidden labels | Required evidence |
| --- | --- | --- | --- |
| `active` | `status:in-progress` | `status:ready-for-review`, `status:needs-verification` | issue、baseline、Issue番号を含むbranch、scope |
| `review-ready` | `status:ready-for-review` | `status:in-progress`, `status:needs-verification` | branch、commit、PR、実行済み validation、結果 |
| `review-ready-unverified` | `status:ready-for-review`, `status:needs-verification` | `status:in-progress` | 上記に加え、未検証 property、理由、attempt、observed result、必要環境 / owner、next command |

`status:needs-verification` は「作業中」の代替ではない。実装が handoff 可能で、remaining verification が具体化されている場合だけ `ready-for-review` と併用する。failing validation や未修正 implementation defect は `needs-verification` に置き換えず、`active` のまま修正する。

## Reconciliation contract

managed set `M`、observed set `O`、desired set `D` に対し、操作は次で決める。

```text
O      = observed_labels ∩ M
remove = O - D
add    = D - O
```

1. Issue、labels、branch / PR state、comments を mutation 直前に読み直す。
2. repository-defined label mapping の存在、一意性、write authority を確認する。
3. lifecycle facts から desired status set `D` を計算する。
4. evidence comment を最終 status 遷移より先に書くか、同じ branch / head / validation payload の既存 comment を再利用する。
5. comment 後に labels を再読し、concurrent managed-state drift があれば自動上書きせず停止する。
6. forbidden combination を作らない順序で remove/add を適用し、unrelated labels を保存する。
7. Issue を再読して `observed_labels ∩ M == D` と evidence comment の存在を確認する。
8. 部分失敗を success に変換しない。readback 不一致は exact observed state と残作業を報告する。

同じ desired state、branch、head、validation payload に対する再実行は comment と label mutation を増やさない no-op になる。toggle、時刻依存遷移、label の暗黙作成、Issue 自動 close、PR 自動 merge は行わない。

## Branch and traceability contract

- implementation branch は最新 `main`、または関連 Issue の active branch を起点にする
- branch 名に Issue 番号を含める
- status mutation を伴う repo change は開始時に `active` へ収束させる
- PR 未完成・検証未完でも、Issue comment から branch、commit / current head、実行済み validation、残作業を辿れるようにする
- handoff 時は `status:in-progress` を解除する
- validation unavailable と implementation failure を区別し、後者を ready state にしない

## Implementation scope

- `agents/internal-routines/github-status-lifecycle.md`
- `.agents/skills/_github-status-lifecycle/SKILL.md`
- `agents/skills/pr-processing.md`
- `issues/open/AC-20260815-github-status-lifecycle-skill.md`

public skill catalog、workflow DAG、GitHub API adapter、label taxonomy、Issue close / PR merge policyは変更しない。

## Acceptance criteria

- runtime-internal skill の canonical owner と discovery shim が追加される
- `pr-processing` が status mutation を新 owner へ委譲し、publication/readback responsibility を重複定義しない
- state table、preconditions、forbidden transitions、idempotent reconciliation、concurrency、partial-failure behavior が明記される
- active、validated handoff、verification unavailable、failed validation、retry/no-op の例がある
- unrelated labels を保存し、label creation、Issue close、PR approval / merge を副作用にしない
- public skill catalog、workflow DAG、checker、schema、receipt を増やさない
- dependency header、Markdown、runtime alignment、repository structure、issue mirror の既存検証が通る
- Issue から branch、commit、PR、validation evidence を追跡できる

## Validation plan

```bash
tools/bin/agent-canon docs check agents/internal-routines/github-status-lifecycle.md agents/skills/pr-processing.md .agents/skills/_github-status-lifecycle/SKILL.md issues/open/AC-20260815-github-status-lifecycle-skill.md
python3 tools/agent_tools/check_skill_frontmatter.py --root .
python3 tools/agent_tools/check_agent_runtime_alignment.py
python3 tools/agent_tools/check_dependency_headers.py --changed
python3 tools/agent_tools/repo_structure_contract.py --root .
python3 tools/agent_tools/issue_sync.py --root . --repo iwashita-nozomu/agent-canon --github-check
```

## Non-goals

- GitHub Projects の custom field / project status の管理
- label の自動作成・rename・色変更
- Issue close、PR approval、merge の自動化
- repository ごとの label 名を AgentCanon に hard-code すること
- `pr-processing` と重複する PR queue / authority / publication workflow を作ること
- status mutation 専用の public wrapper skill、checker、workflow、永続 schema を増やすこと
