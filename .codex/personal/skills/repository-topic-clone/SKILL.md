---
name: repository-topic-clone
description: "Use for any parent, dependency, or standalone repository topic checkout under workspace/<topic>/<repo>; linked-worktree or independent-clone mode is selected by repository relationship, and repository kind is a post-checkout policy decorator."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"7a8e2e65c5546ca772cc007d23148d9433b1635f7f97ffcc53ae9c198e4b6315"} -->

<!--
@dependency-start
contract skill
responsibility Exposes repository-topic-clone for runtime discovery.
upstream design ../../../../agents/skills/repository-topic-clone.md owner
@dependency-end
-->

# repository-topic-clone

## Canonical Skill

Canonical workflow and policy: [repository-topic-clone](../../../../agents/skills/repository-topic-clone.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill repository-topic-clone --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
