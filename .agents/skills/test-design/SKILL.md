---
name: test-design
description: "Use after the owning implementation mechanism exists to proactively design a logically minimal test set; classify unresolved oracle, specification, regression, and failure-mode risk before adding cases."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"fb592ca68c1cd3db213ff92a977e22df211e8ed8c6efc72e25a68eda4337fbff"} -->

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
