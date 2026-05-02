# Goal
<!--
@dependency-start
responsibility Defines the top-level goal loop contract for this repository.
upstream design README.md repository entrypoint
upstream design agents/workflows/adaptive-improvement-workflow.md loop workflow
downstream implementation tools/agent_tools/goal_loop.py consumes this contract
@dependency-end
-->

## Loop Contract

- goal_status: active
- run_safety_cap: 5
- current_iteration: 0
- active_run_id: 20260502-132243-add-execution-path-comparison-eval-for-w
- stop_reason:

## Objective

Organize skill, workflow, and eval surfaces so static-analysis and run-behavior
findings are fed back into skills. Execute and compare two run paths when
behavior may differ; if the paths differ, analyze the difference, add an eval
that fires when the inefficient path is selected, and repair skill/workflow
prompts until the workflow has no remaining improvement action.

## Exit Criteria

- [x] G1: Repository dependency review passes with `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`.
- [x] G2: Skill/workflow prompt evals pass with `python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest agents/evals/skill_workflow_prompt_eval.toml`.
- [x] G3: Agent behavior eval detects inefficient execution path selection and passes after prompt/workflow repair.
- [x] G4: A mechanical two-run path comparison tool exists, is tested, and emits evidence suitable for `workflow_monitoring.md`.
- [x] G5: Static-analysis feedback is represented in workflow monitoring and skill/workflow prompts as a feedback-to-skill loop.
- [x] G6: Targeted static analysis and tests for the changed surfaces pass.
- [ ] G7: AgentCanon main and the template snapshot are updated and pushed.

## Backlog

- [x] B1: Freeze the prompt-to-artifact checklist for skill/workflow/eval organization and static-analysis feedback.
- [x] B2: Add or extend eval criteria so inefficient route selection fails mechanically.
- [x] B3: Add the two-run execution path comparison tool and unit tests.
- [x] B4: Update adaptive-improvement skill/workflow prompts to require static-analysis feedback and two-run path comparison when behavior may differ.
- [x] B5: Run baseline and rerun evals; repair drift until prompt eval and behavior eval pass.
- [x] B6: Update the current run bundle with comparison, validation, and feedback evidence.
- [x] B7: Recheck `goal_loop.py status`; continue if `NEXT_ACTION=run_next_iteration`.

## Optional Goal Item Catalog

These are non-default goal items. They are not active closeout gates and are not
emitted as `GW*` work units unless copied into `Exit Criteria` or `Backlog` for
this objective.

- [ ] O1: (research) External web research is required, with source links and current-date verification recorded in the run bundle.
- [ ] O2: (benchmark) Benchmark or experiment evidence is required, with reproducible commands, seeds, environment, and comparison artifacts.
- [ ] O3: (docs) Long-form documentation, slide, or user-guide review is required before closeout.
- [ ] O4: (release) Release, branch-integration, push, or downstream template snapshot coordination is required.
- [ ] O5: (subagents) Explicit read-only specialist review or implementation handoff is required for the goal.

## Loop Log

- iteration 0: initialized goal for skill/workflow/eval feedback-loop repair and two-run execution path comparison.
