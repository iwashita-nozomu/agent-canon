---
name: environment-maintenance
description: "Use when touching Docker, CI, dependencies, runtime compatibility, or repository-level development environment instructions."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:environment-maintenance -->
<!-- canonical: agents/skills/environment-maintenance.md sha256=39f0eb31ff5bd05d93786e55a1700cfe5f4d218981cdd62ac3e30c6dcf89dc4f -->
<!-- route: agents/skills/catalog.yaml#skill:environment-maintenance.routing digest=0f460d67c04f548911076ec4f526824f0a680be1083d2cb20116703055b87b5b -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:environment-maintenance digest=e81908361c85f153092adcecd138091721bedd3f3bd85127c71739767cb4ebda -->
<!-- commands: agents/skills/catalog.yaml#skill:environment-maintenance.tool_commands digest=d01eed504dca9ddb23dbcc6765f7dccd8538c3f9519eb5c5bf24ade17d2578c0 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/environment-maintenance.md
@dependency-end
-->

# environment-maintenance

## Canonical Skill

Canonical workflow and policy: [environment-maintenance](../../../agents/skills/environment-maintenance.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill environment-maintenance --format text`; schema `skill_tool_commands.v2`, digest: `d01eed504dca9ddb23dbcc6765f7dccd8538c3f9519eb5c5bf24ade17d2578c0`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
