---
name: agent-log-analysis
description: Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, routing misses, weak skills, or selection gaps; first convert raw logs into a token-light compact summary with generate_agent_runtime_dashboard.py before reading or interpreting evidence.
---
<!--
@dependency-start
responsibility Documents Agent Log Analysis for this repository.
upstream design ../../../agents/skills/agent-log-analysis.md documents the human-facing skill
upstream implementation ../../../tools/agent_tools/generate_agent_runtime_dashboard.py generates compact runtime summaries
@dependency-end
-->


# Agent Log Analysis

1. Read `agents/skills/agent-log-analysis.md`.
1. Do not broad-search raw accumulated logs with `rg -n`.
1. Generate a compact summary first:

```bash
python3 tools/agent_tools/generate_agent_runtime_dashboard.py \
  --root . \
  --out reports/agent-runtime-dashboard/agent-runtime-dashboard.md \
  --compact-out reports/agent-runtime-dashboard/agent-runtime-compact.md
```

1. Read `reports/agent-runtime-dashboard/agent-runtime-compact.md` as the default analysis input.
1. Use the generated `Evidence Drilldown` section before consulting any raw evidence.
1. If the compact report lacks enough context for a specific claim, extend or rerun the dashboard tool with a more specific generated summary instead of opening raw JSONL.
1. Treat raw JSONL as tool-development or corruption-audit input only; record an explicit rationale before reading it.
1. Report observations separately from interpretation, repair target, and unknowns.
1. If the analysis drives a prompt, skill, workflow, or tool change, add the responsible skill such as `$agent-learning`, `$md-style-check`, or the target skill before editing.
1. If the user asks for a durable report, pair this skill with `$result-artifact-writeout`.
