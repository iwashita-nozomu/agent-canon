---
name: dependency-design
description: "Define and validate the typed declarative devcontainer dependency design packet before changing mounted developer or agent tools, manifests, bootstrap, or dependency installation order."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"4d06f9a09cd6e89c4feeb93929846776c33f64edcaf04c8db6d78e9e456c7c30"} -->

<!--
@dependency-start
contract skill
responsibility Exposes dependency-design for runtime discovery.
upstream design ../../../agents/skills/dependency-design.md owner
@dependency-end
-->

# dependency-design

## Canonical Skill

Canonical workflow and policy: [dependency-design](../../../agents/skills/dependency-design.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-design --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
