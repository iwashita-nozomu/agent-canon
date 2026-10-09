---
name: agent-log-analysis
description: "Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, missed or late skill invocation, routing misses, weak skills, over-constrained related-skill coverage, or selection gaps; reuse existing structured summaries and use bounded snapshot-qualified drilldown when needed. Archive maintenance, dashboard repair, and eval reruns are separate selected operations, not analysis prerequisites."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"6339437374325d2aaf67b005d4e17c884e401c5de823de87300d1933fbb4a5b6"} -->

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

1. Read the canonical owner before applying this skill.
