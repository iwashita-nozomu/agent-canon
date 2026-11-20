# refactor-loop
<!--
@dependency-start
contract skill
responsibility Documents refactor-loop for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design structure-planning.md reusable refactor structure contract
upstream design dependency-analysis.md unified change-impact and repair-planning packet
upstream design tool-finding-report.md tool-based finding packet and prompt feedback loop
upstream design ../../documents/design/semantic-responsibility-contract.md semantic delta and verification-owner contract
upstream design ../../documents/design/responsibility-cleanup.md replacement retirement and necessary consumer migration
upstream design ../../documents/conventions/software-engineering-principles.md contract-first refactor precedence and abstraction admission
upstream design ./agent-orchestration.md write-capable handoff validation trust boundary and work-conservation owner
upstream design ../internal-routines/design-implementation-correspondence.md design read, clause fingerprint, and drift-block route
@dependency-end
-->


## Reader Map

局所 refactor は対象、差分、既存契約から始めます。refactor の変更方針と review は
この skill の owner であり、design drift invariant は routine に委譲します。一般原則の意味、
競合時の優先順位、KISS / YAGNI / DRY、abstraction admission は
[documents/conventions/software-engineering-principles.md](../../documents/conventions/software-engineering-principles.md)
が所有します。

- Purpose: manage large refactors as behavior-preserving reorganizations with
  explicit scope, deltas, and review gates.
- Section path: Purpose, Use When, and Core References lead into the conditional
  Procedure; later sections cover dependency ordering, Subagent Routing, and
  Review Emphasis.
- Use when: file splits, renames, module boundaries, dependency direction, or
  implementation replacement require a controlled refactor loop.
- Boundary: feature additions and API-shaping choices need explicit contracts;
  structure surface classification belongs to `structure-refactor`.

## Purpose

大きめの refactor を、feature 追加ではなく挙動保存つきの再編として扱います。

通常の置換・統合と重複旧実装の廃止に
[RC-09](../../documents/design/responsibility-cleanup.md#duplicate-implementation-retirement)
を適用します。差分量ではなく SEP-06 の完成後のコードスペースを基準に設計し、依頼に含まれる
旧コード削除と必要な usage-surface repair を同じ修正で閉じます。別の廃止依頼や利用者ゼロを待たず、
無関係な改善は加えません。挙動保存は旧実装・旧構造の温存を意味しません。

## Software Engineering Principle Route

refactor は、[ソフトウェア工学原則](../../documents/conventions/software-engineering-principles.md)
の選択された clause を消費します。原則の意味、優先順位、誤用防止、抽象化の admission、
変更範囲の境界は canonical owner に委譲し、この skill や refactor packet で再定義しません。
抽象化や scope の判断では、canonical policy の
[`SEP-06`](../../documents/conventions/software-engineering-principles.md#sep-06-kiss)、
[`SEP-07`](../../documents/conventions/software-engineering-principles.md#sep-07-yagni)、
[`SEP-08`](../../documents/conventions/software-engineering-principles.md#sep-08-dry-and-abstraction-admission)、
[`SEP-09`](../../documents/conventions/software-engineering-principles.md#sep-09-evidence-bounded-complete-owning-unit)
を直接参照します。

挙動保存に必要な判断を、変更の依存関係に沿って閉じます。意味上の変更に
先立って `Behavior Contract`、invariant、state / lifecycle owner、root mechanism
を解決し、必要な範囲だけから replaceable unit を選びます。移動、rename、split、
abstraction の変更があるときは、`Allowed Structural Delta` と
`Forbidden Semantic Delta` を区別して契約、failure semantics、lifecycle を守ります。
判断に必要な契約と根拠は現在の context に揃えます。

## Validation route

validation command の正本は
[agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary](agent-orchestration.md#write-capable-handoff-validation-trust-boundary) です。
変更した保証に対応する検証を選びます。委譲された作業では合意した検証範囲を使い、
必要な性質が未検証なら、範囲内の方法を見直すか阻害要因を親へ返します。

## 共有構造 refactor の依存順

共有 source と consumers の変更が一つの topology をまたぐ場合、実在する
dependency edge で作業を順序付けます。利用側が公開 source revision を必要とするときは、
source の検証・公開後に既存 pin / 解決規約で dependent を更新します。生成 projection は
canonical source から更新し、影響する consumer だけを新契約へ移行します。独立して検証できる
consumer 作業は、write scope と source availability が衝突しない範囲で並行できます。
具体的な cross-repository 順序は
[cross-module resolution](dependency-analysis.md#conditional-cross-module-resolution) に従います。

source 単位の検証・公開と、全体移行の完了は別です。未公開 source を必要とする
利用側の実行成功を、その source の公開条件に戻してはいけません。同一 repository
で互換性なく同時変更する組は一つの検証可能な commit に閉じます。変更依存が
循環する組を別 wave にして相互の完了を待たず、既存の
[commit 境界](../../documents/operations/BRANCH_SCOPE.md#commit-correctness-contract) で単位をまとめます。
移行先、必要な利用側、旧実装の整理を揃えてから最終状態をまとめて検証します。
この実行順の所有者は `refactor-loop` であり、`structure-refactor` は構造
surface / runtime boundary の分類を、`agent-canon-update` は AgentCanon 固有の
source / pin routing を参照として担当します。

## Use When

- file 分割、rename、module 境界整理
- 依存方向の整理
- implementation の差し替えを伴う構造再編
- branch 側で file 構成変更を含む整理

## Core References

- [documents/conventions/software-engineering-principles.md](../../documents/conventions/software-engineering-principles.md)
- [agents/TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md)
- [documents/conventions/REVIEW_PROCESS.md](../../documents/conventions/REVIEW_PROCESS.md)
- [agents/skills/codex-task-workflow.md](codex-task-workflow.md)
- [agents/skills/integration.md](integration.md)
- [documents/conventions/coding-conventions-cpp.md](../../documents/conventions/coding-conventions-cpp.md)
- [agents/skills/cpp-review.md](cpp-review.md)

## C++ project migration projection

For a C++ path or build-layout refactor, start from the consumer's selected profile
in [cpp-build-layout.md](../../documents/design/cpp-build-layout.md). The
`root-aggregate` profile uses its project root CMake entrypoint; the
`consumer-local` profile uses the selected consumer manifest. Production path
ownership and target-graph topology are separate review axes: do not infer one
from the other's directory shape.

Targets and build/install paths are project-owned. The target graph remains
consumer-to-provider; individual tests and experiments consume the project's
production target when that relation exists. Run, config, result, and retention
records remain with the existing experiment lifecycle and save-results owners.
Refactor review reads back the selected profile and actual CMake commands before
accepting a path or dependency-direction change.

## Procedure

現在の対象と契約から再利用先、変更する責務、残す挙動を決めます。
実装・利用側の移行・旧経路の削除・最終検証は
[実装の共通手順](../canonical/CODEX_IMPLEMENTATION.md#5-implementation) に従います。
移動や削除の対応表は、公開面や利用側の判断に役立つ場合に使います。
計画を変更したときは、影響した根拠を見直します。

## Subagent Routing

Use delegation only when the selected coordination route requires a replaceable
writer or independent review. The parent supplies the current problem, allowed
scope, forbidden semantic change, and selected validation; the implementer
consumes the route verdict and the reviewer remains read-only. Keep same-root
writers serial and distinct-root workstreams parallel under the existing
Parallel Write Safety owner. Add a test designer only for an unresolved
runtime-risk oracle after the mechanism is established.

## Review Emphasis

Review the current diff against the changed behavior, ownership, consumer
migration, and selected validation. Treat reviewer findings as hypotheses and
repair only source-backed reachable effects. Language or document specialists
are conditional on the changed surface; they do not replace the owning review.
