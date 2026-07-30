---
name: md-style-check
description: "Use when Markdown files changed, docs formatter/fixer output must be checked, or `agent-canon docs` formatting, heading, math, Mermaid, and link checks are in scope."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:md-style-check -->
<!-- canonical: agents/skills/md-style-check.md sha256=f340f6279455f30cb01b24cfcd0849c8e28f07797927fa364fe0b16d87a85927 -->
<!-- route: agents/skills/catalog.yaml#skill:md-style-check.routing digest=426e39d6eba9366369b3bd6b16d48d3ff8e4e37fec98ba679e79704e9a737c76 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:md-style-check digest=234e511e80ba3cc7a9dcd412ab4d182d04bd53fbadc416a79d946f0d123b49e7 -->
<!-- commands: agents/skills/catalog.yaml#skill:md-style-check.tool_commands digest=a1cbf8920bccbd0bc2cff9a6ba80cab4bf7100a274bf4ce3a737e0e062f8c927 -->
<!-- host-config: path=../.agents/skills/md-style-check/SKILL.md index=33 order=33 enabled=true digest=7a3ac978788819d40f8971bb4ae144110b73a92dcb83119974a02fd05cfee345 -->
<!-- toolcalls: tools/agent_tools/agent_team.py#materialize_skill_tool_call_token digest=0b05b06deef875f4119b7d6ae820f898c5a5a760da495b38a2a8d29cd3832bb1 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract skill
responsibility Exposes md-style-check as a Codex runtime discovery adapter.
upstream design ../../../agents/skills/md-style-check.md canonical skill owner
@dependency-end
-->

# md-style-check

## Canonical Skill

Canonical workflow and policy: [md-style-check](../../../agents/skills/md-style-check.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill md-style-check --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
