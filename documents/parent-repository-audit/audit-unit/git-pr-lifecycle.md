# Git And PR Lifecycle Audit Unit
<!--
@dependency-start
contract design
responsibility Audits Git state, remotes, branch/PR lifecycle, checklists, and publication authority.
upstream design ../README.md owns source/parent publication boundary
upstream design ../../../agents/workflows/agent-canon-pr-workflow.md owns AgentCanon PR lifecycle
upstream implementation ../../../agents/skills/pr-processing.md owns PR processing and integration routing
downstream implementation ../../../agents/skills/agent-canon-update.md owns source/pin update separation
@dependency-end
-->

## Reader Map

作業開始時の dirty state、remote/branch、source PR、親 PR、review、CI、commit/push、closeout
の順に読みます。source main と parent main、worker と integrator の authority を分離します。

## Owner Responsibility

`pr-processing` が review、PR lifecycle、integration order を所有し、`agent-canon-update`
が AgentCanon source/pin の分離を所有します。worker は PR create/merge/close/admin override
を行わず、親 integrator がその authority を持ちます。

## Invariant

変更は正しい branch と canonical remote にあり、dirty file、commit、push、review、CI、
merge、closeout の状態を証拠付きで追跡できる。source PR と親 PR は混同せず、未実行 check
を pass と報告しない。危険な Git mutation は明示 authority と reason を伴う。

## Evidence Sources

- `git status --short --branch --untracked-files=all`
- `git remote -v`、branch/upstream、`git log`
- `.github/` workflow、PR template、`agent-canon-pr-workflow.md`
- review/CI/check receipts
- parent integrator の merge/readback packet

## Repair Route

owner skill は `pr-processing` と `agent-canon-update`。worker は bounded commit/push まで
行い、PR create/merge/close は親へ handoff します。dirty state は保存し、破壊的操作を
推測で実行しません。

## Validation

Git state、remote、branch、commit、push、PR/CI template の static/readback evidence を
対象にします。GitHub auth/network は必要な lifecycle item のみ条件付きで実行します。

## Close Condition

対象 commit が branch/remote に readback され、レビューと CI の状態、未完了判断、親への
handoff authority が明示される。worker closeout は PR create/merge ではなく push receipt
までで完了します。

## Related Change Surfaces

`surface:git.pr-lifecycle`、`surface:github.workflow`、`surface:pr.template`、
`surface:agentcanon.publication`。branch/remote/PR template/workflow/merge authority の変更時
だけ本 unit を更新します。

## Scope Patterns

- `pattern:.github/**`
- `pattern:.gitmodules`
- `pattern:README.md`
- `pattern:AGENTS.md`
- `pattern:vendor/agent-canon/.github/**`

## Legacy Migration IDs

PRA-C001 PRA-C002 PRA-C003 PRA-C004 PRA-C005 PRA-C006 PRA-C088 PRA-C097 PRA-C098 PRA-C099 PRA-C100 PRA-C102 PRA-C103 PRA-C104 PRA-C105 PRA-X001 PRA-X002 PRA-X003 PRA-X004 PRA-X047 PRA-X050 PRA-X051 PRA-X052 PRA-X053
