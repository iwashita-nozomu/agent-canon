---
name: agent-log-analysis
description: "Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, missed or late skill invocation, routing misses, weak skills, over-constrained related-skill coverage, or selection gaps; reuse existing structured summaries and use bounded snapshot-qualified drilldown when needed. Archive maintenance, dashboard repair, and eval reruns are separate selected operations, not analysis prerequisites."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"6e06ffbafa03d1dad033c9ae3eafaa63250c5ce5ace0575eb5348d9d2b63efcf"} -->

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
