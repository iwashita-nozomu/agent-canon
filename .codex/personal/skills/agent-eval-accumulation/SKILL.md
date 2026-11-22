---
name: agent-eval-accumulation
description: "Use when AgentCanon eval collection or repair is selected to establish required evidence; runs registered producers, validates family accumulation, and archives reports. Read-only observation of missing, stale, or failing evidence alone does not activate this repair loop."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"c7cac6fb0ab892370472be2b4755cf2af6d0d16521cf51c517134173dab5f657"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-eval-accumulation for runtime discovery.
upstream design ../../../../agents/skills/agent-eval-accumulation.md owner
@dependency-end
-->

# agent-eval-accumulation

## Canonical Skill

Canonical workflow and policy: [agent-eval-accumulation](../../../../agents/skills/agent-eval-accumulation.md).

1. Read the canonical owner before applying this skill.
