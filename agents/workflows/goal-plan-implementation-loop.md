# Goal Plan-Implementation Loop
<!--
@dependency-start
contract workflow
responsibility Defines the fast plan-to-implementation loop for goal-driven tasks.
upstream design codex-goals-workflow.md defines durable goal state and MCP gates
upstream design implementation-waterfall-workflow.md defines implementation and closeout gates
downstream design ../skills/adaptive-improvement-loop.md uses this loop for goal iteration efficiency
downstream implementation ../../tools/agent_tools/goal_loop.py generates work breakdown inputs
@dependency-end
-->

This workflow prevents goal-driven work from spending too long in planning.
The goal loop should alternate between a short planning checkpoint and a
concrete implementation slice until `goal_loop.py status` allows closeout.

## Reader Map

This workflow owns the fast loop for goal-driven implementation once a durable
goal exists. Read `Core Rule` and `Timebox` to keep the loop bounded, then use
`Planning Checkpoint`, `Implementation Checkpoint`, `Evidence Checkpoint`, and
`Next-Action Checkpoint` as the repeated sequence. Its boundary is goal-loop
execution: broader design expansion, unproven goal completion, and closeout
decisions remain gated by the named evidence and `goal_loop.py status`.

## Core Rule

Use a `plan -> implementation -> evidence -> next-action` loop.
Do not expand planning into a second full design project unless the next slice is
blocked by an actual design gap.

## Timebox

- Planning checkpoint: enough to select one cohesive slice and evidence gates.
- Implementation slice: large enough to complete one meaningful group of related
  Goal Work Breakdown rows.
- Evidence checkpoint: run the task-relevant commands and mark only proven
  `goal.md` items.
- Next-action checkpoint: read `goal_loop.py status`.

If `NEXT_ACTION=run_next_iteration`, immediately choose the next slice instead
of returning a partial status as completion.

## Planning Checkpoint

Planning produces the initial owned packet needed to implement the next slice:

- `Goal Contract`: objective, non-goals, constraints, and active clauses.
- `Slice Selection`: the `GW*` rows that will move together.
- `Source Packet`: files and docs that must be read before editing.
- `Reuse Decision`: existing tool/doc/code surface to extend first.
- `Validation Gates`: exact commands needed before marking items done.
- `Rollback Point`: the commit, branch, or file set that bounds the slice.

Do not write speculative long-form architecture when the next slice is obvious.
Do not wait for every future slice to be designed before implementing the first
cohesive slice.

## Implementation Checkpoint

Implementation starts as soon as the planning packet above is complete.
Each implementation checkpoint must:

- edit only the selected slice surface;
- update the run-bundle `schedule.md` and `work_log.md`;
- keep reuse-first discipline;
- avoid creating parallel truth surfaces;
- stop and return to planning only when a new dependency, conflict, or design gap
  blocks the selected slice.

## Evidence Checkpoint

After each slice:

1. Run the dependency, code dependency, OOP/readability, prompt eval, docs, or CI
   gates that map to the touched surface.
1. Record outputs in the run bundle.
1. Mark `goal.md` criteria/backlog items only when the evidence directly covers
   them.
1. Regenerate `goal_work_breakdown.md`.

Passing unrelated checks is not enough to mark a Goal item complete.

## Next-Action Checkpoint

Use this exact decision:

- `NEXT_ACTION=run_next_iteration`: start the next planning checkpoint
  immediately.
- `NEXT_ACTION=repair_goal_md`: repair the contract before implementation.
- `NEXT_ACTION=wait_for_unblock`: stop the active iteration and keep the
  blocker in `goal.md`, PR body, issue, or run bundle until the external event
  changes.
- `NEXT_ACTION=stop_goal_loop`: stop without claiming goal achievement.
- `NEXT_ACTION=close_goal_loop`: enter normal closeout gates.

Goal-driven work is slow when the agent returns to broad planning after every
small edit. The correct behavior is to use the previous evidence checkpoint as
the context for the next slice and keep moving.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
