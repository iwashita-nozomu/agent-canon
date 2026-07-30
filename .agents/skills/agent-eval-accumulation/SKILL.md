---
name: agent-eval-accumulation
description: "Use when accumulated AgentCanon eval evidence is missing, stale, or failing; runs registered eval producers, validates eval family accumulation, and stores evidence through the log archive instead of hand-writing reports."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-eval-accumulation -->
<!-- canonical: agents/skills/agent-eval-accumulation.md sha256=f52a09ada66454f9608306d99697d93f353cb789767e04d407d9d86ff355ac3d -->
<!-- route: agents/skills/catalog.yaml#skill:agent-eval-accumulation.routing digest=82fd113d81262b8d7b75a47957fd861829b51a5fd467126ed3f04dc60c578b70 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-eval-accumulation digest=2ba8693a0245e679ab9fdb4e0e25448a861704470bc21c216894baa6031a5a83 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-eval-accumulation.tool_commands digest=1b1666714f2b60970d77ddbbc07299de855c21cf190f05fe17ef27694251c639 -->
<!-- host-config: path=../.agents/skills/agent-eval-accumulation/SKILL.md index=4 order=4 enabled=true digest=4a3bc59e61f2ddf69c70b3ca54d90838434ab3e871f7e7ea95971c6ee57d434c -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=d561a8d5a57efb31efee6513eb6bd41514df3f1b20e6d8bf7f33bd0f8a53c720 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-eval-accumulation as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/agent-eval-accumulation.md canonical skill owner
@dependency-end
-->

# agent-eval-accumulation

## Canonical Skill

Canonical workflow and policy: [agent-eval-accumulation](../../../agents/skills/agent-eval-accumulation.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill agent-eval-accumulation --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
