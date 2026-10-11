---
name: agent-log-analysis
description: "Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, missed or late skill invocation, routing misses, weak skills, over-constrained related-skill coverage, or selection gaps; reuse existing structured summaries and use bounded snapshot-qualified drilldown when needed. Archive maintenance, dashboard repair, and eval reruns are separate selected operations, not analysis prerequisites."
---
<!-- materialization-record: {"schema":"agent_canon.skill_runtime_shim.materialization_record","version":3,"record_digest":"c3abc02bf344cd03fff40b5026e82bef3d67a7bf2d7175e2974b468d2e91f6c6"} -->

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
