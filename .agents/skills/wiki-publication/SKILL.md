---
name: wiki-publication
description: "Use this when publishing AgentCanon wiki pages to a dedicated wiki sidecar with default-branch-only, source-bound publication checks."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"cfe679fb8211e4ce667c8907ff0b04886a4be0b03df51c5bfddd1669bdaa48bb"} -->

<!--
@dependency-start
contract skill
responsibility Exposes wiki-publication for runtime discovery.
upstream design ../../../agents/skills/wiki-publication.md owner
@dependency-end
-->

# wiki-publication

## Canonical Skill

Canonical workflow and policy: [wiki-publication](../../../agents/skills/wiki-publication.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill wiki-publication --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
