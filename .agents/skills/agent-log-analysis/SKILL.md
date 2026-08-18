---
name: agent-log-analysis
description: "Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, missed or late skill invocation, routing misses, weak skills, over-constrained related-skill coverage, or selection gaps; first convert raw logs into a structured dashboard summary with AgentCanon source generate_agent_runtime_dashboard.py before reading or interpreting evidence."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":2,"record_digest":"91d80a4db97f2576299134cf38d2f4b0f618468435d7842ca009139d75c45713"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-log-analysis for runtime discovery.
upstream design ../../../agents/skills/agent-log-analysis.md owner
@dependency-end
-->

# agent-log-analysis

## Canonical Skill

Canonical workflow and policy: [agent-log-analysis](../../../agents/skills/agent-log-analysis.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent_tools/skill_tool_commands.py show --skill agent-log-analysis --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
