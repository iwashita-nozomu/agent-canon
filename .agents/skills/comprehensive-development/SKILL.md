---
name: comprehensive-development
description: Use when a repo-wide task spans code, docs, tools, workflows, and runtime surfaces and needs explicit subagent routing.
---
<!--
@dependency-start
responsibility Documents Comprehensive Development for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/task_catalog.yaml workflow family spawn budget and role topology owner
upstream design ../../../agents/agents_config.json permanent team role ownership and write policy owner
upstream design ../../../agents/canonical/CODEX_SUBAGENTS.md Codex subagent inventory and activation contract
@dependency-end
-->


# Comprehensive Development

1. Read `agents/skills/comprehensive-development.md`.
1. Set `workflow=Comprehensive Development` and declare `skills=<...>`, `review=<...>`.
1. Read `agents/task_catalog.yaml` for the `comprehensive_development` family `spawn_budget`, `role_topology`, `roles`, and `subagent_prompt`.
1. Read `agents/agents_config.json` for permanent team role ownership, required output, and write policy.
1. Read `agents/canonical/CODEX_SUBAGENTS.md` for Codex inventory, activation, and runtime surface routing.
1. Bootstrap the standard bundle, then mirror catalog / config ownership into `team_manifest.yaml`.
1. Use `project_reviewer` as the repo-wide integration reviewer named by the catalog and config surfaces.
1. Assign colliding writers to later waves in the current checkout when multiple writers are needed.
