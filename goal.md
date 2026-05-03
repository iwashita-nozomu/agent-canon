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
- active_run_id: 20260503-074518-add-convention-compliance-verifier-and-w
- stop_reason:

## Objective

Create a convention-compliance verifier that maps repository conventions and
workflow prohibitions to concrete mechanical gates. Ensure every workflow prompt
calls the verifier, skill-routing prompts invoke the appropriate skills, prompt
evals verify that routing, and tool-owned checks replace duplicated prompt-only
instructions where practical.

## Exit Criteria

- [x] G1: Repository dependency review passes with `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`.
- [x] G2: A convention-compliance verifier exists, is tested, and checks convention source inventory, workflow prohibition hooks, workflow verifier invocation, skill routing hooks, and tool-gate wiring.
- [x] G3: Every workflow prompt in `agents/workflows/*.md` calls `check_convention_compliance.py` before closeout or handoff.
- [x] G4: Skill-routing prompts and evals verify `$agent-orchestration` first, task-shape skill selection, and convention-compliance gate usage.
- [x] G5: Tool-owned convention checks are documented as mechanical gates so prompt surfaces do not duplicate detailed tool logic.
- [ ] G6: Prompt evals, targeted tests, convention verifier, dependency review, and template `make ci` pass after snapshot update.
- [ ] G7: AgentCanon main and template snapshot branch are updated and pushed.

## Backlog

- [x] B1: Build a prompt-to-artifact checklist for every explicit requirement in the objective.
- [x] B2: Inventory convention docs, workflow prohibition sources, existing tools, and prompt eval surfaces.
- [x] B3: Implement the smallest verifier that checks the current manifestable convention gates.
- [x] B4: Add tests and prompt eval coverage for workflow verifier hooks and skill-call routing.
- [x] B5: Update workflow / skill prompts to call the verifier and remove or centralize tool-owned details where practical.
- [ ] B6: Run AgentCanon validation, sync template snapshot, run template validation, and close only after `NEXT_ACTION=close_goal_loop`.

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
- iteration 0: initialized convention-compliance verifier objective with
  workflow hook, skill-call eval, tool/prompt split, and template snapshot
  closeout gates.
