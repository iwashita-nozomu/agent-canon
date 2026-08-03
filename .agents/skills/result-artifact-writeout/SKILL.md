---
name: result-artifact-writeout
description: "Use when writing, exporting, saving, accumulating, or reporting tool/checker/hook/skill/eval/experiment results; creates durable raw and summary artifacts with unique IDs and no accidental overwrite."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"9869d206d7b28e2a1ce675f77f39ee76a66ea2c56bd8c6d4d77629362cc8c128"} -->

<!--
@dependency-start
contract skill
responsibility Exposes result-artifact-writeout for runtime discovery.
upstream design ../../../agents/skills/result-artifact-writeout.md owner
@dependency-end
-->

# result-artifact-writeout

## Canonical Skill

Canonical workflow and policy: [result-artifact-writeout](../../../agents/skills/result-artifact-writeout.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill result-artifact-writeout --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
