# Goal
<!--
@dependency-start
responsibility Defines the active convention-compliance goal loop contract.
upstream design README.md repository entrypoint
upstream design agents/workflows/adaptive-improvement-workflow.md loop workflow
downstream implementation tools/agent_tools/goal_loop.py consumes this contract
downstream implementation tools/agent_tools/check_convention_compliance.py verifies convention compliance evidence
@dependency-end
-->

## Loop Contract

- goal_status: active
- run_safety_cap: 5
- current_iteration: 1
- active_run_id: 20260504-convention-compliance-goal
- stop_reason: in progress

## Objective

Make convention compliance mechanically checkable and workflow-enforced across AgentCanon:

1. provide a tool that verifies convention source coverage, convention assertion verification routes, workflow prohibition hooks, convention tool gates, prompt eval coverage, and skill-routing hooks;
1. ensure every workflow invokes that tool before closeout or handoff;
1. inspect both tool behavior and prompt / eval behavior, not only prose instructions;
1. document this Goal as the durable source of truth and add iteration findings to Exit Criteria and Backlog before claiming completion;
1. revise skill prompts so `$agent-orchestration` is first and task-shape skills are selected minimally;
1. add eval coverage that confirms skill-call routing and runtime skill invocation evidence; and
1. gradually delegate tool-covered rules out of skill prompts and into mechanical checks.

## Workflow

1. Confirm MCP inventory and `goal.loop_status` before each iteration.
1. Run the convention checker and prompt eval before editing, then use findings to update this Goal.
1. Strengthen `check_convention_compliance.py` before expanding prose prompts.
1. Update skill / workflow prompts only for routing behavior that cannot be enforced by the tool.
1. Add or update evals for every prompt behavior that must remain prompt-driven.
1. Use read-only review to audit tool coverage, prompt coverage, workflow hook coverage, and Goal accuracy.
1. Close only when all Exit Criteria are checked, `goal_loop.py status` and MCP `goal.loop_status` report `NEXT_ACTION=close_goal_loop`, and repo validation passes.

## Exit Criteria

- [x] C1: `check_convention_compliance.py` exists and verifies convention sources, tool gates, workflow hooks, closeout prohibitions, prompt eval wiring, skill routing, and convention assertion verification routes.
- [x] C2: Every `agents/workflows/*.md` workflow is checked for a positive `python3 tools/agent_tools/check_convention_compliance.py` command and for forbidden suppression text.
- [x] C3: `tools/ci/run_all_checks.sh` invokes `check_convention_compliance.py`.
- [x] C4: `agents/evals/skill_workflow_prompt_eval.toml` includes convention workflow and skill-routing eval coverage.
- [x] C5: `evaluate_agent_run.py` requires runtime skill invocation behavior evidence, not only `Signals` prose.
- [x] C6: `$agent-orchestration` skill prompts require convention verification to stay in the execution path and delegate tool-covered rules to the checker.
- [x] C7: Convention documents with normative assertions expose verification routes, and prohibition-bearing convention documents expose prohibition sections.
- [x] C8: Read-only review approves the current diff after the Goal is updated.
- [x] C9: Validation passes: convention checker, convention checker tests, prompt eval, repo dependency review, `make agent-checks`, and `make ci`.
- [ ] C10: AgentCanon main and the template snapshot branch are pushed with the final convention-compliance state.

## Backlog

- [x] B1: Audit existing convention checker, workflow hooks, prompt evals, skill-routing prompts, and CI wiring.
- [x] B2: Add convention assertion verification-route checks and prohibition-section checks to `check_convention_compliance.py`.
- [x] B3: Fix convention documents surfaced by the stronger checker.
- [x] B4: Strengthen runtime skill invocation evaluation in `evaluate_agent_run.py`.
- [x] B5: Replace stale `goal.md` with this convention-compliance Goal.
- [x] B6: Run focused tests and full validation.
- [x] B7: Run read-only audit and resolve findings.
- [ ] B8: Commit and push AgentCanon, then update and push the template snapshot.

## Loop Log

- iteration 0: read-only audit found that the previous `goal.md` represented an unrelated objective, convention checker was only a wiring checker, and skill-call confirmation relied too much on signals.
- iteration 1: strengthened checker coverage, added convention assertion checks, fixed convention docs to expose prohibition sections and verification routes, tightened runtime skill invocation evidence, and rewrote this Goal around the active objective.
- iteration 2: fixed review-identified Markdown and pycache issues, then reran convention checker, focused tests, prompt eval, repo dependency review, `make agent-checks`, and `make ci` successfully.
- iteration 3: read-only diff reviewer approved the current convention-compliance diff after pycache cleanup, leaving only AgentCanon and template snapshot push closeout.
