---
name: dependency-design
description: "Define and validate the typed declarative devcontainer dependency design packet before changing mounted developer or agent tools, manifests, bootstrap, or dependency installation order."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"aefdca60104aac60ee299ed4d4c7f949c43a55fcf4251715ef6173e8b361c66f"} -->

<!--
@dependency-start
contract skill
responsibility Exposes dependency-design for runtime discovery.
upstream design ../../../../agents/skills/dependency-design.md owner
@dependency-end
-->

# dependency-design

## Canonical Skill

Canonical workflow and policy: [dependency-design](../../../../agents/skills/dependency-design.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill dependency-design --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
