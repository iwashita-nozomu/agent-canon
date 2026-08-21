---
name: runtime-log-repair
description: "Use when AgentCanon runtime dashboard evidence should be turned into owner-routed repair work, including dashboard next actions, repair failing hook evidence, hook entries status=fail, missing actual wave rows, workflow attribution gaps, consulted source URLs, reference missing URLs, AGENT_RUNTIME_DASHBOARD_WAVE_MISSING_ACTUAL, AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING, or AGENT_RUNTIME_DASHBOARD_REFERENCE_MISSING_URLS."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"40a05c1ce437d579299474d9e73299df528c05046151e840d914e899e902c771"} -->

<!--
@dependency-start
contract skill
responsibility Exposes runtime-log-repair for runtime discovery.
upstream design ../../../agents/skills/runtime-log-repair.md owner
@dependency-end
-->

# runtime-log-repair

## Canonical Skill

Canonical workflow and policy: [runtime-log-repair](../../../agents/skills/runtime-log-repair.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill runtime-log-repair --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
