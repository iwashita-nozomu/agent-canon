---
name: runtime-log-repair
description: "Use when AgentCanon runtime dashboard evidence should be turned into owner-routed repair work, including dashboard next actions, repair failing hook evidence, hook entries status=fail, missing actual wave rows, workflow attribution gaps, consulted source URLs, reference missing URLs, AGENT_RUNTIME_DASHBOARD_WAVE_MISSING_ACTUAL, AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING, or AGENT_RUNTIME_DASHBOARD_REFERENCE_MISSING_URLS."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"fe926fcb5fa981920cf20a56e46a43d94ae64b1bcf959b8a6104f7b1b605b61c"} -->

<!--
@dependency-start
contract skill
responsibility Exposes runtime-log-repair for runtime discovery.
upstream design ../../../../agents/skills/runtime-log-repair.md owner
@dependency-end
-->

# runtime-log-repair

## Canonical Skill

Canonical workflow and policy: [runtime-log-repair](../../../../agents/skills/runtime-log-repair.md).

1. Read the canonical owner before applying this skill.
