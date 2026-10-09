---
name: agent-log-analysis
description: "Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, missed or late skill invocation, routing misses, weak skills, over-constrained related-skill coverage, or selection gaps; reuse existing structured summaries and use bounded snapshot-qualified drilldown when needed. Archive maintenance, dashboard repair, and eval reruns are separate selected operations, not analysis prerequisites."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"32338bd8d8e54470500783c679fb8c6576656ead353a2e839b44fe00fd20d2cd"} -->

<!--
@dependency-start
contract skill
responsibility Exposes agent-log-analysis for runtime discovery.
upstream design ../../../../agents/skills/agent-log-analysis.md owner
@dependency-end
-->

# agent-log-analysis

## Canonical Skill

Canonical workflow and policy: [agent-log-analysis](../../../../agents/skills/agent-log-analysis.md).

## Tool Commands

<!-- skill-tool-commands:start -->
`python3 tools/agent/skills/skill_tool_commands.py show --skill agent-log-analysis --format text`
<!-- skill-tool-commands:end -->

1. Read the canonical owner before applying this skill.
