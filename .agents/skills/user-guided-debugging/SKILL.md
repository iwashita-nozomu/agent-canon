---
name: user-guided-debugging
description: "Use when the user explicitly asks to debug, repair, or refactor one issue at a time with visible problem statements before each edit and a next-issue prompt after each scoped fix."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:user-guided-debugging -->
<!-- canonical: agents/skills/user-guided-debugging.md sha256=b12afba097f856ef9d4547b63ad07df33d9804c6fc976834c1244da684c88598 -->
<!-- route: agents/skills/catalog.yaml#skill:user-guided-debugging.routing digest=e4401791a52cd66e2c19c950ef56663020c18d63f17c40a74ab0b2ca4aed9e63 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:user-guided-debugging digest=75ae011666cdaf1ab2f3f9d866013454a8601e475098b2f396bc09f9c8b54dfd -->
<!-- commands: agents/skills/catalog.yaml#skill:user-guided-debugging.tool_commands digest=8a2ee00298e7fda0bcc90438d91c74b7f6c70640f1d1e369442ccca68e7b6333 -->
<!-- host-config: path=../.agents/skills/user-guided-debugging/SKILL.md index=55 order=55 enabled=true digest=ff72171095201f0aad11cc75bcc2b648cc0a33d56c12307a79120981e44738c5 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=28c8524d9d9d08e0ca64668873be8b062c20ce474392d49686f65df706e73bf2 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes user-guided-debugging for runtime discovery.
upstream design ../../../agents/skills/user-guided-debugging.md owner
@dependency-end
-->

# user-guided-debugging

## Canonical Skill

Canonical workflow and policy: [user-guided-debugging](../../../agents/skills/user-guided-debugging.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill user-guided-debugging --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
