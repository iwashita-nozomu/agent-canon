---
name: test-design
description: "Use after the owning implementation mechanism exists to proactively design a logically minimal test set; classify unresolved oracle, specification, regression, and failure-mode risk before adding cases."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"10033cfc8ca503bac275ccc61889027bad4ce9df13926e24d0946757eede5594"} -->

<!--
@dependency-start
contract skill
responsibility Exposes test-design for runtime discovery.
upstream design ../../../agents/skills/test-design.md owner
@dependency-end
-->

# test-design

## Canonical Skill

Canonical workflow and policy: [test-design](../../../agents/skills/test-design.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill test-design --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
