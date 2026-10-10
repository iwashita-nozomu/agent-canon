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

## Cross-surface work

Start from the user/domain contract and current callers to identify the affected
owners, semantic invariant, state/lifecycle boundary, and root mechanism. Include
the consumer, failure, migration, and validation edges that can change the result;
reuse established capabilities before proposing a new surface. Keep the existing
design trace as the place for cross-surface decisions.

Use actual dependency, collision, authority, and validation relationships to
choose work order and parallelism. Keep each slice a complete responsibility
unit, migrate its affected consumers, and retire superseded support when that
unit requires it. Add a specialist, design review, or test design only for a
decision or changed guarantee that needs it. Validate the affected contract and
connections with the selected owner route. A passing check establishes only the
property it covers.

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
