---
name: agent-eval-accumulation
description: "Use when AgentCanon eval collection or repair is selected to establish required evidence; runs registered producers, validates family accumulation, and archives reports. Read-only observation of missing, stale, or failing evidence alone does not activate this repair loop."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"a92bcbd81c970622698864a059307e5c286e9780abd8de303ad540b6c5002c61"} -->

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
