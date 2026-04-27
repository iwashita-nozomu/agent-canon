---
name: adaptive-improvement-loop
description: Use when experiments, research, tuning, and iterative code improvement must be managed as one backlog-driven agile outer loop.
---
<!--
@dependency-start
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Adaptive Improvement Loop

1. Read `agents/skills/adaptive-improvement-loop.md`.
1. Read `agents/workflows/adaptive-improvement-workflow.md`.
1. Read `agents/workflows/research-workflow.md`.
1. Read `agents/workflows/experiment-workflow.md`.
1. Keep the outer loop agile and backlog-driven, but keep each repo-changing pass inside `agents/workflows/implementation-waterfall-workflow.md`.
1. Fix `Question`, `Comparison Target`, `Exit Criteria`, `Stop Budget`, and `Improvement Backlog` before choosing the next iteration.
1. Keep one extension, one waterfall run id, one change pass, and one decision state at a time.
1. Before moving to a second extension, finish the previous extension's waterfall gate checks, final review, `task-close`, commit, and push.
1. Do not close the loop while `report_rewrite_required`, `extra_validation_required`, `rerun_required`, or `direction_rethink_required` remains.
