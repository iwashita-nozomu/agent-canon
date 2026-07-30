---
name: agent-learning
description: "Use when agent-side working philosophy, interaction lessons, task retrospectives, repeated routing misses, missed skill invocation, or recurrence-prevention feedback should be logged without mixing them into user preferences."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-learning -->
<!-- canonical: agents/skills/agent-learning.md sha256=3d25e79cbd8cda66cd4ceb64cbe5ab3b1d0be99305a93b7054968429476febca -->
<!-- route: agents/skills/catalog.yaml#skill:agent-learning.routing digest=7d92634fcce7234f7eb340873ccb4d93f7e920dcba6cdbe0db55d16ae045d015 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-learning digest=d119e106e2ec69ebe058ffa24352ab745c427743fa2822df9513a021cb6b11e2 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-learning.tool_commands digest=5f56443490fe274ad861af4d9bfc23d962051938b49780315b0143b0fbc32f55 -->
<!-- host-config: path=../.agents/skills/agent-learning/SKILL.md index=2 order=2 enabled=true digest=e85a3904a1eb06394cba8db26d43f8a336fe344c47fafa7410b6029fc1e290a4 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=5444d037c0825e783faf9ab4d98e75706e8c149e34b78e62a120aeb31b7a1e27 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-learning for runtime discovery.
upstream design ../../../agents/skills/agent-learning.md owner
@dependency-end
-->

# agent-learning

## Canonical Skill

Canonical workflow and policy: [agent-learning](../../../agents/skills/agent-learning.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill agent-learning --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
