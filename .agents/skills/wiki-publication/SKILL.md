---
name: wiki-publication
description: "Use this when publishing AgentCanon wiki pages to a dedicated wiki sidecar with default-branch-only, source-bound publication checks."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"8f7851018673bec9c1e33870b0557513c955742f4e672572b5c8bc90fec79a3b"} -->

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
