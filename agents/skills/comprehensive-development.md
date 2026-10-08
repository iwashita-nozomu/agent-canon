# comprehensive-development
<!--
@dependency-start
contract skill
responsibility Documents comprehensive-development for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../task_catalog.yaml workflow family spawn budget and role topology owner
upstream design ../agents_config.json permanent team role ownership and write policy owner
upstream design ../canonical/CODEX_SUBAGENTS.md Codex subagent inventory and activation contract
upstream design ../internal-routines/design-implementation-correspondence.md cross-surface design-to-implementation correspondence route
upstream design ../../documents/conventions/software-engineering-principles.md contract-first decision precedence and responsibility-boundary policy
upstream design ../../documents/conventions/common/03_comments.md material decision-comment policy
upstream design ../../documents/design/semantic-responsibility-contract.md semantic action and verification-owner allocation
upstream design ../../documents/design/entrypoint-owner-map.md root entrypoint responsibility migration boundary
@dependency-end
-->

## Purpose

複数 surface を束ねるときは、各 bounded slice の design locator、clause
fingerprint、implementation target、review evidence を
[../internal-routines/design-implementation-correspondence.md](../internal-routines/design-implementation-correspondence.md) に接続します。
この skill は umbrella integration stage の owner であり、共通 policy の別実装
を作りません。

code、docs、tests、workflow、tools、runtime をまたぐ repo-wide な変更を、1 本の umbrella workflow と explicit subagent routing で進めます。
この skill は route packet と reader contract に限定し、spawn budget、role topology、role ownership、write policy は正本 surface へ委譲します。

## Procedure

1. Fix the user/domain contract, semantic invariant, state/lifecycle owner, and
   root mechanism for the cross-surface change. Start from existing callers and
   capabilities; reuse the established owner before proposing a new surface.
2. Select the smallest complete owning unit that includes affected code, docs,
   tests, workflow/tool consumers, failure handling, migration, and selected
   validation. Cross-surface mechanism decisions remain in the existing design
   trace; this skill adds no second schema or principle checklist.
3. Run the selected implementation slices in dependency order. Activate a
   specialist, design review, or test design only when an unresolved claim or
   changed guarantee needs that owner. Keep bounded slices complete rather than
   turning them into a generic stage sequence.
4. Migrate all affected consumers and retire superseded support in the same
   responsibility unit. Use the existing coordination and writer-safety owners
   when the selected route requires them.
5. Validate the changed contract and consumer connections with the selected
   static/targeted route, then use the selected closeout owner for integration and
   review. A green check alone does not establish an unrun behavior guarantee.

## Use When

- implementation、docs、tooling、Docker、CI を同時に整理する
- agent canon、workflow、entrypoint、validation tool をまとめて改造する
- 1 つの局所 diff ではなく、複数 surface の整合を取りながら delivery したい

## Core References

- `agents/task_catalog.yaml` (`workflow_families[].id: comprehensive_development`)
- `agents/agents_config.json`
- [agents/TASK_WORKFLOWS.md](../TASK_WORKFLOWS.md)
- [agents/canonical/CODEX_SUBAGENTS.md](../canonical/CODEX_SUBAGENTS.md)
- [agents/COMMUNICATION_PROTOCOL.md](../COMMUNICATION_PROTOCOL.md)
- [documents/conventions/software-engineering-principles.md](../../documents/conventions/software-engineering-principles.md)
- [documents/conventions/common/03_comments.md](../../documents/conventions/common/03_comments.md)
- [documents/design/semantic-responsibility-contract.md](../../documents/design/semantic-responsibility-contract.md)

## Parent-Managed Write Scope

- parent は選択した coordination route の writer placement を
  [Parallel Write Safety](../canonical/CODEX_SUBAGENTS.md#parallel-write-safety) に委譲します。
- reviewer は read-only を保ち、parent-managed write-scope discipline の確認は `plan_reviewer` と `project_reviewer` が行います。

## Boundary

- 局所修正なら `Scoped Change` を使います。
- chunk ごとに独立 pass を閉じたい delivery なら `Large Delivery` を使います。
- Docker / CI が中心なら `Platform And Environment` を使います。
- 外部調査と experiment が主役なら `Research-Driven Change` を使います。
- 一般原則の意味、優先順位、誤用防止はこの skill に複製せず、canonical policy を参照します。
- root [AGENTS.md](../../AGENTS.md) / [ROOT_AGENTS.md](../../ROOT_AGENTS.md) は owner route だけを持ち、本節の basis contract を複製しません。
