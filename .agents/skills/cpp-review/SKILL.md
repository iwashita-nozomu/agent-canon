---
name: cpp-review
description: "Use when C or C++ code changes need strict review for build evidence, header boundaries, ownership, and native-code behavior."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"a020ee1509f6907bbf6210bbe8da73ab0af8d2b8c51ff258d671c180dd1d829e"} -->

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
