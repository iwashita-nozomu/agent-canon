---
name: agent-learning
description: Use when agent-side working philosophy, interaction lessons, or task retrospectives should be logged without mixing them into user preferences.
---
<!--
@dependency-start
responsibility Documents Agent Learning for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Agent Learning

1. Read `agents/skills/agent-learning.md`.
1. Read `agents/workflows/agent-learning-workflow.md`.
1. Separate user preference from agent-side learning.
1. Before closeout, run `python3 tools/agent_tools/evaluate_agent_run.py --report-dir reports/agents/<run-id> --write` and resolve any feedback actions.
1. Log concise evidence-backed observations with `tools/agent_tools/log_agent_learning.py`.
1. Keep raw chat out of notes; record source, evidence, scope, and confidence.
1. Promote only stable items into `AGENTS.md`, workflow docs, or guardrails.
