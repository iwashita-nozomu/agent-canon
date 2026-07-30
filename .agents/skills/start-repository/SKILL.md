---
name: start-repository
description: "Use when starting a new GitHub/submodule-first repository from this template after clone, including project slug/display-name setup and AgentCanon submodule validation."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:start-repository -->
<!-- canonical: agents/skills/start-repository.md sha256=b8082ae1184f6e31e396757bcfda0cdd4de7732f25aafd01e8a57b2f7561cc19 -->
<!-- route: agents/skills/catalog.yaml#skill:start-repository.routing digest=833ea3b9cdd7836cde78621fbd8e242bcf8ebd3e01f76cbdcaea1baa3ad68712 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:start-repository digest=83944f0fc56d48f7819caf0fab6d949c12575b4baafefa707a5f2f0268f9eaf7 -->
<!-- commands: agents/skills/catalog.yaml#skill:start-repository.tool_commands digest=c6b28cecb612f62c1a4e806f8c54c83d6d99961163038058a7398d111395e25e -->
<!-- host-config: path=../.agents/skills/start-repository/SKILL.md index=48 order=48 enabled=true digest=640ca8ee221fa8687af3532c3ed7e3946174cbc3159db72bcc64e066c76be70c -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=4d6fc8e18b4ad043a8db8394398208c1c0ac4c7cd89efeb9ca1392b6032db5e2 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/start-repository.md
@dependency-end
-->

# start-repository

## Canonical Skill

Canonical workflow and policy: [start-repository](../../../agents/skills/start-repository.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill start-repository --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
