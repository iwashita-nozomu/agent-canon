---
name: adaptive-improvement-loop
description: Use when experiments, research, tuning, and iterative code improvement must be managed as one backlog-driven agile outer loop.
---
<!--
@dependency-start
contract skill
responsibility Documents Adaptive Improvement Loop for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Adaptive Improvement Loop

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill adaptive-improvement-loop --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/adaptive-improvement-loop.md`.
1. Read `agents/workflows/adaptive-improvement-workflow.md`.
1. Read `agents/workflows/goal-plan-implementation-loop.md`.
1. Read `agents/workflows/research-workflow.md`.
1. Read `agents/workflows/experiment-workflow.md`.
1. If the user gives goal-driven intent without an exact objective, draft a conservative `goal.md` objective and use read-only pre-goal subagents before implementation when explicit spawn authorization exists. If authorization is absent, record the pre-goal handoff plan and `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` before requesting or waiting for authorization.
1. Confirm MCP loop state with `goal.loop_status` when repo MCP tools are available; if it returns `NEXT_ACTION=run_next_iteration`, continue the next backlog iteration instead of treating the current iteration as completion.
1. Before any implementation or tool addition, update top-level `goal.md` with the current Objective, Exit Criteria, Backlog, and Loop Log entry, then confirm it with `python3 tools/agent_tools/goal_loop.py status --goal-file goal.md`.
1. For skill/workflow prompt tuning, freeze one eval per tested skill/workflow in `evidence/agent-evals/skill_workflow_prompt_eval.toml` before changing the prompt under test.
1. Run `python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml` before and after prompt repair.
1. If the eval reports drift, repair the relevant skill/workflow prompt and rerun the same eval until `EVAL_STATUS=pass`.
1. When user or reviewer feedback is observed during actual use, record it with `python3 tools/agent_tools/workflow_monitor.py --report-dir <run> --runtime-feedback "source=<user|reviewer|eval> target=<skill-or-workflow-or-eval> action=<prompt_repair|eval_update|memory_record|no_op>"`, then update the targeted skill prompt, workflow prompt, eval, or memory note in the same iteration.
1. For agent behavior tuning, record skill invocation, subagent routing, tool gate, prompt eval, review feedback, subagent lifecycle, diff-check, static-analysis feedback, and execution path comparison events with `python3 tools/agent_tools/workflow_monitor.py --report-dir <run> --behavior-event "..."`.
1. If static analysis exposes a skill/workflow weakness, record `static_analysis_feedback=applied|recorded` with the prompt or eval target that received the feedback. Do not close the loop while `static_analysis_feedback=pending` remains.
1. When two executions can take different paths, run `python3 tools/agent_tools/compare_agent_run_paths.py --baseline-run <run-a> --candidate-run <run-b>` and feed its `execution_path_comparison`, `route_efficiency`, `selected_inefficient_route`, and `static_analysis_feedback` tokens into workflow monitoring.
1. If `route_efficiency=inefficient` or `selected_inefficient_route=yes` appears, repair the skill/workflow prompt and behavior eval until the inefficient route no longer passes.
1. For code-improvement iterations, add `agents/workflows/hypothesis-validation-workflow.md` as an overlay and record `Observation`, `Hypothesis`, `Expected Mechanism`, `Candidate Comparison`, `Disconfirming Evidence`, `Support Evidence`, and `Hypothesis Decision`.
1. If `Hypothesis Decision` is `rejected` or `inconclusive`, return to hypothesis selection instead of widening the current implementation pass.
1. Before closeout, run `python3 tools/agent_tools/evaluate_agent_run.py --report-dir <run> --behavior-manifest evidence/agent-evals/agent_behavior_eval.toml --write` and repair workflow artifacts or prompts until `AGENT_EVALUATION_STATUS=pass`.
1. Keep the outer loop agile and backlog-driven, but keep each repo-changing pass inside `agents/workflows/implementation-waterfall-workflow.md`.
1. For goal-driven work, use the fast `plan -> implementation -> evidence -> next-action` loop; once the next cohesive slice is implementation-ready, stop broad planning and edit.
1. Fix `Question`, `Comparison Target`, `Exit Criteria`, `Stop Budget`, and `Improvement Backlog` before choosing the next iteration.
1. Keep one extension, one waterfall run id, one change pass, and one decision state at a time.
1. Treat the iteration number as progress metadata, not as a completion condition; only explicit achieved criteria close the loop.
1. Before moving to a second extension, finish the previous extension's waterfall gate checks, final review, `task-close`, commit, and push.
1. Do not close the loop while `report_rewrite_required`, `extra_validation_required`, `rerun_required`, or `direction_rethink_required` remains.
1. Do not close the loop while MCP `goal.loop_status` or `goal_loop.py status` reports `NEXT_ACTION=run_next_iteration`.
1. Whenever this run uses skills, run `python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml --accumulate --run-id <run-id> --skill-used <skill>` and record `EVAL_RUN_ID` plus `EVAL_ACCUMULATED_REPORT`.
1. Do not close a skill/workflow improvement loop while prompt eval drift remains; accumulated reports live under `.agent-canon/log-archive/eval-results/skill-workflow-prompt/` and must not be overwritten.
1. Do not close an agent behavior improvement loop while behavior eval feedback actions remain open.
