---
name: cpp-review
description: "Use when C or C++ code changes need strict review for build evidence, header boundaries, ownership, and native-code behavior."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"1b49ce17e3ec35010ce4d41fdb210f9d0f541f89615a83b26b73015255c0cc84"} -->

<!--
@dependency-start
contract skill
responsibility Exposes cpp-review for runtime discovery.
upstream design ../../../agents/skills/cpp-review.md owner
@dependency-end
-->

# cpp-review

## Canonical Skill

Canonical workflow and policy: [cpp-review](../../../agents/skills/cpp-review.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill cpp-review --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
