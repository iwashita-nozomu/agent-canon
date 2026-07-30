---
name: agent-canon-update
description: "Use when updating AgentCanon itself, refreshing a vendored vendor/agent-canon submodule pin, repairing AgentCanon root runtime views, applying AgentCanon update TODOs, or routing local AgentCanon source commits through a proper AgentCanon branch and PR before parent pin updates."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:agent-canon-update -->
<!-- canonical: agents/skills/agent-canon-update.md sha256=8eb5b177eb693f022b9af4bdd66261db0af42fdd804644c80f0825897a0d91d3 -->
<!-- route: agents/skills/catalog.yaml#skill:agent-canon-update.routing digest=4ba74601f6db489caeb39270fe520ace1621e68f68b8848d97103b8ee2103614 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:agent-canon-update digest=674cd72a8044b4c5520f0208a04f7bcd191f318bacfe9141c69567653f263692 -->
<!-- commands: agents/skills/catalog.yaml#skill:agent-canon-update.tool_commands digest=6f47e09b79e918a2d33664939f965e529b087652c54386db3700b70f6edb5ba3 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/agent-canon-update.md
@dependency-end
-->

# agent-canon-update

## Canonical Skill

Canonical workflow and policy: [agent-canon-update](../../../agents/skills/agent-canon-update.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill agent-canon-update --format text`; schema `skill_tool_commands.v2`, digest: `6f47e09b79e918a2d33664939f965e529b087652c54386db3700b70f6edb5ba3`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
