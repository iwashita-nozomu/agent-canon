---
name: cpp-review
description: "Use when C or C++ code changes need strict review for build evidence, header boundaries, ownership, and native-code behavior."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"aa8550d5ceeb84f4414649a45a630c6fce05ac853d41f35d48fb990c3c6d7bc2"} -->

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
