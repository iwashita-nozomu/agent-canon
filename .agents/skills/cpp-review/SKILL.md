---
name: cpp-review
description: "Use when C or C++ code changes need strict review for build evidence, header boundaries, ownership, and native-code behavior."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"757568e2340b4818a319c334e251cf88f4396c4931de6ae937142911f7645185"} -->

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
