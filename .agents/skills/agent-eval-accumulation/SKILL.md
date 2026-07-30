---
name: agent-eval-accumulation
description: "Use when accumulated AgentCanon eval evidence is missing, stale, or failing; runs registered eval producers, validates eval family accumulation, and stores evidence through the log archive instead of hand-writing reports."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-eval-accumulation -->
<!-- canonical: agents/skills/agent-eval-accumulation.md sha256=f52a09ada66454f9608306d99697d93f353cb789767e04d407d9d86ff355ac3d -->
<!-- route: agents/skills/catalog.yaml#skill:agent-eval-accumulation.routing digest=82fd113d81262b8d7b75a47957fd861829b51a5fd467126ed3f04dc60c578b70 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-eval-accumulation digest=2ba8693a0245e679ab9fdb4e0e25448a861704470bc21c216894baa6031a5a83 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-eval-accumulation.tool_commands digest=aeb8ee6c2a167717f9c8fe0a7e6ac8d74aad12f9c5ee9e911ea66780dd605df0 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/agent-eval-accumulation.md
@dependency-end
-->

# agent-eval-accumulation

## Canonical Skill

Canonical workflow and policy: [agent-eval-accumulation](../../../agents/skills/agent-eval-accumulation.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-eval-accumulation --format text`; schema `skill_tool_commands.v2`, digest: `aeb8ee6c2a167717f9c8fe0a7e6ac8d74aad12f9c5ee9e911ea66780dd605df0`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
