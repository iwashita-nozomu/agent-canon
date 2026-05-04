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
- active_run_id: 20260504-todo-goal-workflow
- stop_reason:

## Objective

Turn the TODO list into a repeatable goal loop that:

1. dynamically routes coding work to the cheapest suitable model while keeping
   code-reading tasks on `gpt-5.3-codex-spark`;
1. standardizes slide production on a fixed PPT template that can combine text,
   equations, generated images, and references without layout drift;
1. strengthens hypothesis-validation so every slice starts with a read/survey
   pass, a checklist, and tool creation before edits;
1. repairs coding prompts when tools discard or rewrite changes after edit
   attempts; and
1. produces one cumulative quantitative closeout report that records each step's
   intent, path, evidence, and intermediate results.
1. keeps AgentCanon main, the template snapshot, and the repo-local runtime
   views aligned through the canonical update branch lane instead of letting
   drift accumulate across copies.
1. cuts token usage by at least half for the same skill/workflow envelope while
   preserving prompt-eval and behavior-eval pass rates, using the token-
   efficient workflow overlay and measured run comparisons.

## Workflow

1. Intake the TODO, write the goal contract, and mirror the same objective into
   the run bundle and Codex goal view.
1. Use `goal_loop.py status` and `goal_loop.py plan` to turn the goal into a
   concrete work breakdown before editing.
1. For each slice, follow `plan -> implementation -> evidence -> next-action`.
1. For the model-routing slice, survey existing routing prompts and adjust the
   orchestration so simple coding can be delegated to a cheaper model while
   code-reading stays on Spark.
1. For the slide slice, lock the PPT template, then wire image generation,
   textual content, equation content, and reference placement into the same
   workflow.
1. For the hypothesis-validation slice, require repo/document reading,
   checklist creation, reusable tool selection, and post-rejection analysis
   before any edit.
1. For the coding-prompt slice, record which tools rejected or rewrote code,
   then revise the coding workflow prompts and evals to remove the failure mode.
1. For the reporting slice, append the intent, path, validation, and result of
   each step into one cumulative closeout report.
1. For the AgentCanon unification slice, treat vendor/agent-canon as the shared
   canon source, update it through the canonical update branch lane, then
   refresh the template snapshot and repo-local runtime views from that source
   before any further feature edits.
1. For the token-efficiency slice, choose the lowest safe parent profile and
   agent mode, record the baseline token footprint, apply prompt/workflow
   simplifications, then compare the same eval envelope again and keep only
   changes that preserve skill accuracy while reducing tokens by at least half.
1. Keep each iteration narrow enough to complete one cohesive slice, but large
   enough to include validation and evidence.
1. When `goal_loop.py status` and MCP `goal.loop_status` both report
   `NEXT_ACTION=close_goal_loop`, move to normal closeout gates.

## Exit Criteria

- [ ] G1: The goal contract, workflow, and backlog are written from the TODO
  list and can be parsed by `goal_loop.py status`.
- [ ] G2: Model-routing workflow and prompt surfaces route simple coding to the
  cheapest suitable model while keeping code-reading on Spark.
- [ ] G3: Slide workflow uses a fixed PPT template and supports text, equation,
  image, and reference placement with layout review.
- [ ] G4: Hypothesis-validation workflow enforces read-first survey, checklist
  creation, tool selection, and quantitative plus qualitative rejection
  analysis before edits.
- [ ] G5: Coding workflow prompts are revised when tools discard or rewrite
  changes, and the repair path is covered by evals.
- [ ] G6: The goal run produces a cumulative quantitative closeout report that
  records per-step intent, path, evidence, and intermediate results.
- [ ] G7: Repository dependency review, prompt evals, and template `make ci`
  pass after snapshot update.
- [ ] G8: AgentCanon main, the template snapshot branch, and repo-local runtime
  views are updated and pushed through the canonical update lane.
- [ ] G9: The token-efficient workflow slice shows at least 50% lower token
  usage for the same skill/workflow eval envelope, while skill and behavior
  evals remain pass and no inefficient route is selected.

## Backlog

- [ ] B1: Draft the goal work breakdown from the TODO into checkable work
  units, owner notes, and evidence hints.
- [ ] B2: Survey existing routing, slide, hypothesis, coding, and reporting
  surfaces before editing anything.
- [ ] B3: Implement the model-routing slice and its eval coverage first.
- [ ] B4: Implement the slide-workflow slice with template locking and layout
  validation.
- [ ] B5: Implement the hypothesis-validation and coding-prompt repair slices
  with tool and eval updates.
- [ ] B6: Implement the AgentCanon main unification and template snapshot
  synchronization slice through the canonical branch lane.
- [ ] B7: Implement the token-efficiency reduction slice and record the baseline
  and comparison evidence.
- [ ] B8: Implement the cumulative closeout report slice and wire it into the
  goal loop.
- [ ] B9: Run AgentCanon validation, sync the template snapshot, and close only
  after `NEXT_ACTION=close_goal_loop`.

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

- iteration 0: initialized goal from TODO items covering model routing, slide
  workflow, hypothesis validation, coding prompt repair, quantitative
  closeout reporting, AgentCanon unification, and token-efficiency reduction.
