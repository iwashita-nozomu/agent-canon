---
name: issue-finding-report
description: "Use when converting accumulated prompt history, run bundles, hook logs, skill/tool/workflow routing evidence, eval summaries, or agent reports into durable AgentCanon skill issues; groups repeated evidence by abstract cause, shards multi-agent review by evidence partition, and writes issue candidates from structured dashboard artifacts."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"29efbbad89e482c79fabd73073bb189c582f3e3b86f6901c2eafa2ee6f33f377"} -->

<!--
@dependency-start
contract skill
responsibility Exposes issue-finding-report for runtime discovery.
upstream design ../../../agents/skills/issue-finding-report.md owner
@dependency-end
-->

# issue-finding-report

## Canonical Skill

Canonical workflow and policy: [issue-finding-report](../../../agents/skills/issue-finding-report.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill issue-finding-report --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
