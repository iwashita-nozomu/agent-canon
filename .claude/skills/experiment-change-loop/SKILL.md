---
name: experiment-change-loop
description: Use when benchmark-driven code changes should continue through implement, run, review, and explicit decision states until the loop can be closed.
---

# Experiment Change Loop

1. Read `agents/skills/experiment-change-loop.md`.
1. Read `documents/research-workflow.md`.
1. Read `documents/experiment-workflow.md`.
1. Start from `agents/templates/experiment_change_loop.md` when a durable loop record is needed.
1. Fix `Question`, `Comparison Target`, and `Exit Criteria` before editing code.
1. Keep one code change per iteration.
1. Do not close the loop while `report_rewrite_required`, `extra_validation_required`, or `rerun_required` remains.
1. If the loop needs Docker, dependency, or CI changes, also use `environment-maintenance`.
