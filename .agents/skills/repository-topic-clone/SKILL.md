---
name: repository-topic-clone
description: "Use for any parent, dependency, or standalone repository topic clone lifecycle under workspace/<topic>/<repo>; repository kind is a post-clone policy decorator."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"2550e0c6b676e06371be7b827d6ab49d8879f7d8d620c89e9a96736c525bb8b9"} -->

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
