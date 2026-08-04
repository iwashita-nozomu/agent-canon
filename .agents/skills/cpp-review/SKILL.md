---
name: cpp-review
description: "Use when C or C++ code changes need strict review for build evidence, header boundaries, ownership, and native-code behavior."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"80fc21ef2c9974e035e3b8071727ab2c0123f08e473277ac6f0bcdf5cbc38e97"} -->

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
