---
name: algorithm-proof-exploration
description: "Use when exploring, refactoring, or choosing an algorithm under proof obligations; builds JIT-canonical IR, lemma dependency graphs, algorithmic blocker frontiers, and algorithm-change guidance before handing terminal proof work to formal-proof-workflow."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"08a5b00e49d1bc6b9447e5957845125bde263c87e45da406284a7b0c02556533"} -->

<!--
@dependency-start
contract skill
responsibility Exposes algorithm-proof-exploration for runtime discovery.
upstream design ../../../agents/skills/algorithm-proof-exploration.md owner
@dependency-end
-->

# algorithm-proof-exploration

## Canonical Skill

Canonical workflow and policy: [algorithm-proof-exploration](../../../agents/skills/algorithm-proof-exploration.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill algorithm-proof-exploration --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
