---
name: agent-canon-update
description: "Use when updating AgentCanon itself, refreshing a vendored vendor/agent-canon submodule pin, repairing AgentCanon root runtime views, applying AgentCanon update TODOs, or routing local AgentCanon source commits through a proper AgentCanon branch and PR before parent pin updates."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-canon-update -->
<!-- canonical: agents/skills/agent-canon-update.md sha256=bbadd6921d3898bb5764c3bdf3fa3cf1e4a89e7e1cc9713e8fc2ed0390a8130c -->
<!-- route: agents/skills/catalog.yaml#skill:agent-canon-update.routing digest=4ba74601f6db489caeb39270fe520ace1621e68f68b8848d97103b8ee2103614 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-canon-update digest=674cd72a8044b4c5520f0208a04f7bcd191f318bacfe9141c69567653f263692 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-canon-update.tool_commands digest=6f47e09b79e918a2d33664939f965e529b087652c54386db3700b70f6edb5ba3 -->
<!-- host-config: path=../.agents/skills/agent-canon-update/SKILL.md index=3 order=3 enabled=true digest=3d94459de71d170faad0e4f0bc3b513c75dc016425f05e87357eae8874ab6991 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=fc4cc8d608f8d2da12112b88e446cec38741b00d870fe5dd638e782697c54ad0 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-canon-update for runtime discovery.
upstream design ../../../agents/skills/agent-canon-update.md owner
@dependency-end
-->

# agent-canon-update

## Canonical Skill

Canonical workflow and policy: [agent-canon-update](../../../agents/skills/agent-canon-update.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill agent-canon-update --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
