---
name: test-design
description: "Use after the owning implementation mechanism exists to proactively design a logically minimal test set; classify unresolved oracle, specification, regression, and failure-mode risk before adding cases."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"568607dbaca2986a0bafae1086d4d0eeb055d39e32945111692b24e47c9c93fa"} -->

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
