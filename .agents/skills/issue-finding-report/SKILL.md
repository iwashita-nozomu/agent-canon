---
name: issue-finding-report
description: "Use when converting accumulated prompt history, run bundles, hook logs, skill/tool/workflow routing evidence, eval summaries, or agent reports into durable AgentCanon skill issues; groups repeated evidence by abstract cause, shards multi-agent review by evidence partition, and writes issue candidates from structured dashboard artifacts."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":1,"record_digest":"2970681a62e2a30b73d272df08e8e79ed8d64936ad75680076d1b9e23d3d74f4"} -->

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
