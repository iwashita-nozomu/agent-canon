---
name: dependency-design
description: "Define and validate the typed declarative devcontainer dependency design packet before changing mounted developer or agent tools, manifests, bootstrap, or dependency installation order."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"c4f55f49c78e45e0913e4eb948599829d78aa252887cfe6047fedfe5a8796d1d"} -->

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
