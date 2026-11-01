# responsibility-cleanup
<!--
@dependency-start
contract skill
responsibility Routes responsibility-unit cleanup from structure observation through owner dispatch, integration, and re-review.
upstream design ./README.md shared public skill canon and source maintenance
upstream design ../../documents/design/responsibility-cleanup.md responsibility-unit cleanup contract
upstream design ./structure-refactor.md structure-first ownership repair
upstream design ./refactor-loop.md behavior-preserving refactor route
upstream design ./agent-orchestration.md dispatch and review routing owner
upstream design ./task-routing.md compact route selection owner
downstream implementation ../../.codex/personal/skills/responsibility-cleanup/SKILL.md runtime discovery shim
downstream implementation ./catalog.yaml public skill registry
downstream implementation ./skill-dependencies.yaml public skill dependency DAG
downstream implementation ../../.codex/config.toml host skill configuration
@dependency-end
-->

## Purpose

責務単位 cleanup の入口です。依頼された範囲と既存 evidence を使って
source/view/generated/project/personal の境界、dependency closure、replaceable responsibility、
specialist dispatch、統合、再レビューを
[`responsibility-cleanup`](../../documents/design/responsibility-cleanup.md)
の RC-01..RC-08 に接続します。

## Use When

- repository の責務単位を整理する
- structure、ownership、dependency closure、root/view/generated 境界を同時に判断する
- environment/code/skill の specialist dispatch と統合後の再レビューを束ねる

## Route

1. Use the target and declared scope to determine the cleanup unit. A requested repository-wide inventory follows [project-review](../internal-routines/project-review.md).
2. Close the selected unit by owner, public contract, selected validation, and rollback. Use the write-capable handoff boundary in `agent-orchestration.md#Write-Capable Handoff Validation Trust Boundary` when a writer handoff is selected.
3. Route only changed surfaces: environment cleanup to `environment-cleanup`, code cleanup to `code-cleanup`, and general skill authoring to the host `$skill-creator`. For AgentCanon registration or distribution changes, read [Updating Skills](README.md#updating-skills) before those operations.
4. Reuse `document-canon-cleanup`, `worktree-health`, `agent-log-analysis`, `runtime-log-repair`, or `result-artifact-writeout` only when the selected unit includes those responsibilities.
5. Preserve `agent-orchestration` and `task-routing` decisions. Integrate and run `change-review`/owner readback when the selected workflow requires them; these are not unconditional stages for every cleanup.

## Tool Commands

For a requested repository-wide inventory, choose from these commands; they are
not a required batch:

```bash
tree -a -J --noreport
python3 tools/validation/semantic/structure/repo_structure_contract.py --root . --contract documents/structure/repo-structure-contract.toml
tools/bin/agent-canon responsibility-scope --root .
python3 tools/agent/skills/skill_dependency_map.py check --root .
```

## Boundary

責務境界、外部 tool、analyzer の扱いと必要な最終検証は設計正本を参照します。
この skill は個別 owner の policy や削除 oracle を複製しません。
