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

refactor target trace を固定する前に、owning design を read し、routine の
clause fingerprint と implementation trace を参照します。refactor の change
mapping と review はこの skill の owner ですが、design drift invariant は
routine に委譲します。一般原則の意味、競合時の優先順位、KISS / YAGNI / DRY、
abstraction admission は [documents/conventions/software-engineering-principles.md](../../documents/conventions/software-engineering-principles.md)
が所有し、この skill では refactor 固有の実行 contract だけを追加します。

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
を適用します。差分量ではなく SEP-06 の完成後のコードスペースを基準に設計し、不要な旧コードの
削除と必要な usage-surface repair を同じ修正で閉じます。別の廃止依頼や利用者ゼロを待たず、
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
判断へ影響した `SEP-*` clause と evidence だけを既存 packet / handoff に記録します。
これらの判断は dependency に従いますが、全タスクへ同じ調査・記録・実装順を要求しません。

## Validation route

validation command の正本は
[agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary](agent-orchestration.md#write-capable-handoff-validation-trust-boundary) です。
refactor-loop は親 packet または変更後 responsibility graph が明示した exact command
だけを消費します。global/full rescan が未指定なら実行せず、`unexpected-action` または
`unresolved-risk` として親へ返します。

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
各編集段階に checker を追加せず、依存が揃った単位と最後の全体で必要な検証を行います。
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

For a C++ path or build-layout refactor, the replaceable project boundary is
`cpp/CMakeLists.txt`. The path map is `cpp/include/` for public headers,
`cpp/src/` for production source, `tests/cpp/` for derived-project CTest-owned test targets, and
`cpp/experiments/` for native experiment targets. The parent root remains
language-neutral; commands use `cmake -S "$ROOT/cpp" -B
"$ROOT/build/cpp/<profile>"` and the matching
`$ROOT/.state/cpp-install/<profile>` install prefix.

The target graph is consumer-to-provider: individual test and experiment targets
consume `cpp-core`, while `cpp-tests` and `cpp-experiments` group builds. Run,
config, result, and retention records remain with the existing experiment
lifecycle and save-results owners. Refactor review reads this mapping back from
the design trace before accepting a path or dependency-direction change.

## Procedure

1. Start from the current cause, required guarantee, most recently incorporated
   implementation, and existing reuse evidence. A prior refactor sequence is not
   a reason to repeat its stages.
2. Follow callers and effects only far enough to select the owning responsibility,
   replaceable unit, mechanism, and validation route. Use `dependency-analysis`
   when that boundary or consumer migration remains unresolved; for a bounded
   non-split edit, keep the existing owner evidence.
3. For a structural refactor, fix the canonical root first, then update the
   affected callers, tests, docs, and generated consumers in the same owning unit.
   Remove obsolete entrypoints, wrappers, aliases, and exclusive support under
   RC-09. Keep API/structure mapping only where the change actually moves or
   deletes a public surface.
4. Preserve the agreed behavior and failure semantics. Add `structure-planning`,
   `tool-finding-report`, or a domain reviewer only when the changed contract or
   unresolved risk requires that owner. Prompt/doc/static-contract changes use the
   selected static or targeted validation route.
5. After each repair unit, inspect the current diff against the changed guarantee
   and run only the selected validation. Review findings are hypotheses: repair
   them only when current source, reachable effects, and evidence change the owner,
   edit, or validation decision. Reuse existing receipts and return unavailable or
   unrelated work to its owner.
6. A selected coordination route may hand off a bounded writer/reviewer. Use the
   existing subagent and parallel-write owners for placement, lifecycle, and
   handback; this skill does not reproduce their field lists or approval gates.

## Shared-structure order

For a refactor spanning a shared source and consumers, use the dependency edges to
order only the required changes: establish the target contract, update the canonical
source and any inseparable consumers, publish when a dependent checkout requires that
revision, then migrate and validate affected consumers. Source publication and
consumer adoption remain separate claims. Independent consumers may proceed in
parallel when their inputs and write scopes are ready; keep dependent changes in one
commit only when they cannot be validated independently.

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

## Runtime Contract Clauses

For replacement or duplicate retirement, apply RC-09: retain the canonical
mechanism, migrate necessary callers, and remove obsolete support. Use
`dependency-analysis` or `tool-finding-report` only when their existing owner is
needed to decide the root or an unresolved risk. Use the selected static or
targeted validation route, inspect the resulting diff, and hand back unavailable
or unrelated work to its owner. Do not add a new packet, field list, approval
stage, full scan, or review gate in this skill.
