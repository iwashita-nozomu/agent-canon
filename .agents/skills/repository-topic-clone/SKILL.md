---
name: repository-topic-clone
description: "Use for any parent, dependency, or standalone repository topic clone lifecycle under workspace/<topic>/<repo>; repository kind is a post-clone policy decorator."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"f89ea581e5fade8166e85968cae8c1932190611d21bcb8262077c764b7490d25"} -->

<!--
@dependency-start
contract skill
responsibility Exposes repository-topic-clone for runtime discovery.
upstream design ../../../agents/skills/repository-topic-clone.md owner
@dependency-end
-->

# repository-topic-clone

## Canonical Skill

Canonical workflow and policy: [repository-topic-clone](../../../agents/skills/repository-topic-clone.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill repository-topic-clone --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
