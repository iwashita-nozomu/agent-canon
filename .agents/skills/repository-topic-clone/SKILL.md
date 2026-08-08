---
name: repository-topic-clone
description: "Use for any parent, dependency, or standalone repository topic clone lifecycle under workspace/<topic>/<repo>; repository kind is a post-clone policy decorator."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"a117b0ba58a116ad820bb8829a1caf8a766484f80a5ec7cbe065339e0d1cc2d8"} -->

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
