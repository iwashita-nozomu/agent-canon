---
name: wiki-publication
description: "Use this when publishing AgentCanon wiki pages to a dedicated wiki sidecar with default-branch-only, source-bound publication checks."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"ab66efa4b3485daee0501d033f02c15e9a15fd846bc9e5c7da2ac916f627e9ab"} -->

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
