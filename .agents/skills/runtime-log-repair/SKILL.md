---
name: runtime-log-repair
description: "Use when AgentCanon runtime dashboard evidence should be turned into owner-routed repair work, including dashboard next actions, repair failing hook evidence, hook entries status=fail, missing actual wave rows, workflow attribution gaps, consulted source URLs, reference missing URLs, AGENT_RUNTIME_DASHBOARD_WAVE_MISSING_ACTUAL, AGENT_RUNTIME_DASHBOARD_HOOK_WORKFLOW_MISSING, or AGENT_RUNTIME_DASHBOARD_REFERENCE_MISSING_URLS."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:runtime-log-repair -->
<!-- canonical: agents/skills/runtime-log-repair.md sha256=bb2bced6862644fd84069c8ffa77fc277056d5c8da6d2b7cff24d4f2ee0ff303 -->
<!-- route: agents/skills/catalog.yaml#skill:runtime-log-repair.routing digest=d8f8344b96314edd98afa5e599f1a6fdc07615dad08ce84ffee268534e2e1b78 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:runtime-log-repair digest=abb88dcb33ea5faf981313d7242c94577720465a96a91ed277c42834b9be83a8 -->
<!-- commands: agents/skills/catalog.yaml#skill:runtime-log-repair.tool_commands digest=c6630e66570aceebaa644260f89d95425600e6fd94cabac20b31cc3f44a6bf1d -->
<!-- host-config: path=../.agents/skills/runtime-log-repair/SKILL.md index=6 order=6 enabled=true digest=ef31299c1576dcda5f44e9a7ddbfaf490d3c1cd6483c493e58682d1ff70d87be -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=97d727b0ccb0857668942b25154ba25d2015edf5cf309c5b0adc8ef7418787b8 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes runtime-log-repair as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/runtime-log-repair.md canonical skill owner
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
