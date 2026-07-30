---
name: md-style-check
description: "Use when Markdown files changed, docs formatter/fixer output must be checked, or `agent-canon docs` formatting, heading, math, Mermaid, and link checks are in scope."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:md-style-check -->
<!-- canonical: agents/skills/md-style-check.md sha256=d2c7e2118a6ee107eb96914fc692d6793cd2cf36ae287a734f71adfe1f6bdfc7 -->
<!-- route: agents/skills/catalog.yaml#skill:md-style-check.routing digest=426e39d6eba9366369b3bd6b16d48d3ff8e4e37fec98ba679e79704e9a737c76 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:md-style-check digest=234e511e80ba3cc7a9dcd412ab4d182d04bd53fbadc416a79d946f0d123b49e7 -->
<!-- commands: agents/skills/catalog.yaml#skill:md-style-check.tool_commands digest=4c15f64eb1db60c5ffcdd089e56ba0ebcc05a95569c6ac63524320b6f3c916a4 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/md-style-check.md
@dependency-end
-->

# md-style-check

## Canonical Skill

Canonical workflow and policy: [md-style-check](../../../agents/skills/md-style-check.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill md-style-check --format text`; schema `skill_tool_commands.v2`, digest: `4c15f64eb1db60c5ffcdd089e56ba0ebcc05a95569c6ac63524320b6f3c916a4`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
