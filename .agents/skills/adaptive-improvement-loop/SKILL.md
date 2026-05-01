---
name: adaptive-improvement-loop
description: Use when experiments, research, tuning, and iterative code improvement must be managed as one backlog-driven agile outer loop.
---
<!--
@dependency-start
responsibility Documents Adaptive Improvement Loop for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Adaptive Improvement Loop

1. Read `agents/skills/adaptive-improvement-loop.md`.
1. Read `agents/workflows/adaptive-improvement-workflow.md`.
1. Read `agents/workflows/research-workflow.md`.
1. Read `agents/workflows/experiment-workflow.md`.
1. Before any implementation or tool addition, update top-level `goal.md` with the current Objective, Exit Criteria, Backlog, and Loop Log entry, then confirm it with `python3 tools/agent_tools/goal_loop.py status --goal-file goal.md`.
1. For skill/workflow prompt tuning, freeze one eval per tested skill/workflow in `agents/evals/skill_workflow_prompt_eval.toml` before changing the prompt under test.
1. Run `python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest agents/evals/skill_workflow_prompt_eval.toml` before and after prompt repair.
1. If the eval reports drift, repair the relevant skill/workflow prompt and rerun the same eval until `EVAL_STATUS=pass`.
1. For agent behavior tuning, record skill invocation, subagent routing, tool gate, prompt eval, review feedback, subagent lifecycle, and diff-check events with `python3 tools/agent_tools/workflow_monitor.py --report-dir <run> --behavior-event "..."`.
1. Before closeout, run `python3 tools/agent_tools/evaluate_agent_run.py --report-dir <run> --behavior-manifest agents/evals/agent_behavior_eval.toml --write` and repair workflow artifacts or prompts until `AGENT_EVALUATION_STATUS=pass`.
1. Keep the outer loop agile and backlog-driven, but keep each repo-changing pass inside `agents/workflows/implementation-waterfall-workflow.md`.
1. Fix `Question`, `Comparison Target`, `Exit Criteria`, `Stop Budget`, and `Improvement Backlog` before choosing the next iteration.
1. Keep one extension, one waterfall run id, one change pass, and one decision state at a time.
1. Treat the iteration number as progress metadata, not as a completion condition; only explicit achieved criteria close the loop.
1. Before moving to a second extension, finish the previous extension's waterfall gate checks, final review, `task-close`, commit, and push.
1. Do not close the loop while `report_rewrite_required`, `extra_validation_required`, `rerun_required`, or `direction_rethink_required` remains.
1. Do not close a skill/workflow improvement loop while prompt eval drift remains.
1. Do not close an agent behavior improvement loop while behavior eval feedback actions remain open.
