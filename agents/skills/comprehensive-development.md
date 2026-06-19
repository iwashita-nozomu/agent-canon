# comprehensive-development
<!--
@dependency-start
contract skill
responsibility Documents comprehensive-development for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../task_catalog.yaml workflow family spawn budget and role topology owner
upstream design ../agents_config.json permanent team role ownership and write policy owner
upstream design ../canonical/CODEX_SUBAGENTS.md Codex subagent inventory and activation contract
@dependency-end
-->


## Purpose

code、docs、tests、workflow、tools、runtime をまたぐ repo-wide な変更を、1 本の umbrella workflow と explicit subagent routing で進めます。
この skill は route packet と reader contract に限定し、spawn budget、role topology、role ownership、write policy は正本 surface へ委譲します。

## Use When

- implementation、docs、tooling、Docker、CI を同時に整理する
- agent canon、workflow、entrypoint、validation tool をまとめて改造する
- 1 つの局所 diff ではなく、複数 surface の整合を取りながら delivery したい

## Core References

- `agents/task_catalog.yaml` (`workflow_families[].id: comprehensive_development`)
- `agents/agents_config.json`
- `agents/TASK_WORKFLOWS.md`
- `agents/canonical/CODEX_SUBAGENTS.md`
- `agents/COMMUNICATION_PROTOCOL.md`

## Standard Bundle

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "comprehensive development pass" \
  --task-id T12 \
  --owner "codex" \
  --workspace-root "$PWD"
```

## Default Sequence

1. family を `Comprehensive Development` に固定します。
1. `agents/task_catalog.yaml` の `comprehensive_development` family から `spawn_budget`、`role_topology`、`roles`、`subagent_prompt` を読みます。
1. `agents/agents_config.json` で permanent team role ownership、required output、write policy を確認します。
1. `agents/canonical/CODEX_SUBAGENTS.md` で Codex inventory、activation、runtime surface を確認します。
1. run bundle を作り、`workflow=<family>`, `skills=<...>`, `review=<...>` と catalog / config 由来の route を宣言します。
1. `agents/COMMUNICATION_PROTOCOL.md` の fresh context capsule と bounded source packet を使って、stage ごとに subagent handoff を作ります。
1. write-capable work は approved design trace から導いた bounded slice に限定し、親が integration order と validation rerun を管理します。
1. closeout では `project_reviewer` を integration gate として使い、catalog / config / inventory と実 diff の同期を確認します。

## Parent-Managed Write Scope

- parent は `team_manifest.yaml` に writer ごとの allowed path / directory、integration order、validation route を固定します。
- colliding writer scope は current checkout 内の後続 wave に serialize します。
- reviewer は read-only を保ち、parent-managed write-scope discipline の確認は `plan_reviewer` と `project_reviewer` が行います。

## Boundary

- 局所修正なら `Scoped Change` を使います。
- chunk ごとに独立 pass を閉じたい delivery なら `Large Delivery` を使います。
- Docker / CI が中心なら `Platform And Environment` を使います。
- 外部調査と experiment が主役なら `Research-Driven Change` を使います。
