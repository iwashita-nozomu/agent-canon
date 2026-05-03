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

- goal_status: achieved
- run_safety_cap: 5
- current_iteration: 0
- active_run_id: 20260503-070655-strengthen-hypothesis-to-validation-flow
- stop_reason:

## Objective

Strengthen the code-improvement hypothesis-to-validation flow from both skill
and workflow surfaces. The updated canon must force agents to state improvement
hypotheses, compare alternative fix surfaces, define disconfirming evidence,
validate before editing, and check post-change evidence before claiming the
hypothesis was supported.

## Exit Criteria

- [x] G1: Repository dependency review passes with `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`.
- [x] G2: Hypothesis-validation workflow defines code-improvement hypothesis, alternative-surface comparison, disconfirming evidence, pre-edit validation, and post-change support / reject decisions.
- [x] G3: Relevant skill surfaces route code improvement through the strengthened hypothesis-validation workflow.
- [x] G4: Prompt eval manifest checks the strengthened skill/workflow wording and passes.
- [x] G5: Dependency review, targeted prompt eval tests, and template `make ci` pass after snapshot update.
- [x] G6: AgentCanon main and template snapshot branch are updated and pushed.

## Backlog

- [x] B1: Freeze prompt eval checks for hypothesis-validation and adaptive-improvement surfaces.
- [x] B2: Update `hypothesis-validation-workflow.md` with explicit H1-H5 hypothesis lifecycle gates.
- [x] B3: Update skill shims / human-facing skills so code improvement invokes dependency analysis plus hypothesis validation before implementation.
- [x] B4: Run prompt evals and targeted tests; repair wording until they pass.
- [x] B5: Update template snapshot and run template validation.
- [x] B6: Recheck `goal_loop.py status`; close only when all criteria are checked.

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
- iteration 0 result: added execution-path comparison tooling, behavior eval
  failure for inefficient route selection, static-analysis feedback monitoring,
  adaptive-improvement prompt repairs, and tool-index documentation. AgentCanon
  main and the template snapshot branch were pushed during closeout.
- iteration 0: initialized goal for code-improvement hypothesis-to-validation
  flow strengthening across skill and workflow surfaces.
- iteration 0 result: strengthened hypothesis-validation gates, dependency
  analysis routing, adaptive-improvement skill guidance, and prompt eval
  coverage. AgentCanon validation passed, the template snapshot was refreshed,
  and template `make ci` passed before closeout.
