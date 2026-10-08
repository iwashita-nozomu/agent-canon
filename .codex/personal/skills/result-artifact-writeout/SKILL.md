---
name: result-artifact-writeout
description: "Use when writing, exporting, saving, accumulating, or reporting tool/checker/hook/skill/eval/experiment results; creates durable raw and summary artifacts with unique IDs and no accidental overwrite."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"90fc44ac96426942453e4e0a31b4e078f86a85b62941b8dca255f0ace5489159"} -->

<!--
@dependency-start
contract skill
responsibility Exposes result-artifact-writeout for runtime discovery.
upstream design ../../../../agents/skills/result-artifact-writeout.md owner
@dependency-end
-->

# result-artifact-writeout

## Canonical Skill

Canonical workflow and policy: [result-artifact-writeout](../../../../agents/skills/result-artifact-writeout.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill result-artifact-writeout --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
