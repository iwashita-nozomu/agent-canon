<!--
@dependency-start
contract workflow
responsibility Documents Codex goals workflow for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md Codex runtime workflow contract
upstream design ../canonical/CODEX_SUBAGENTS.md pre-goal subagent routing contract
upstream design adaptive-improvement-workflow.md goal loop source of truth
downstream design goal-plan-implementation-loop.md defines efficient iteration cadence
upstream implementation ../../.codex/config.toml enables Codex goals feature
upstream implementation ../../tools/agent_tools/goal_loop.py exposes goal loop status
@dependency-end
-->

# Codex Goals Workflow

This workflow defines how to use the Codex `goals` feature in this repository.
The feature is a session/runtime aid; it does not replace the repo-owned goal
contract.

## Reader Map

- This document owns the boundary between Codex `goals`, repo-local `goal.md`, and the mechanical `goal_loop.py` gates.
- The early sections split durable and session state, preflight goal tooling, autonomous goal drafting, and pre-goal fan-out; the later sections cover plan-mode entry, TUI commands, goal creation, iteration, efficiency, and closeout.
- Use `## Preflight` before relying on a goal, then read `## Autonomous Goal Draft` when the user gives goal-driven intent without exact criteria.
- For chunked reading, keep `goal.md` as the durable state anchor and open only the section matching the current phase: setup, plan-mode entry, iteration, or closeout.

## Role Split

- `goal.md` is the durable source of truth for Objective, Exit Criteria,
  Backlog, and Loop Log.
- `goal.md` separates default active goal items from non-default optional goal
  catalog entries. `Exit Criteria` and `Backlog` are active by default; the
  `Optional Goal Item Catalog` is advisory until an item is copied into an
  active section for the current objective.
- `goal.md` is repo-local state. It must not be a symlink to
  `vendor/agent-canon/goal.md`, and AgentCanon sync must not overwrite one
  repo's active goal with another repo's goal.
- Codex `goals` is the interactive session view of the same objective and
  criteria.
- `tools/agent_tools/goal_loop.py status` is the mechanical close/continue gate
  for repo-level loops.
- `tools/agent_tools/goal_loop.py plan` is the mechanical next-slice work-unit
  surface.

## Preflight

Run this at task intake when the task uses a goal or adaptive loop:

```bash
codex features list | grep '^goals'
python3 tools/agent_tools/goal_loop.py status --goal-file goal.md
python3 tools/agent_tools/goal_loop.py plan --goal-file goal.md \
  --report-out reports/agents/<run-id>/goal_work_breakdown.md
```

If `goals` is not enabled, use one of these before relying on the Codex goals
surface:

```bash
codex features enable goals
codex --enable goals
```

`NEXT_ACTION=run_next_iteration` means the task is not complete. Continue the
next backlog item. `NEXT_ACTION=close_goal_loop` means the loop may proceed to
normal closeout gates.

## Autonomous Goal Draft

When the user asks for `/goal`, goal-driven work, or "達成するまで回す" but does
not provide an exact objective string, the parent should draft the initial goal
instead of waiting for the user to restate it.

Rules:

1. Use this only for explicit goal-driven intent. Do not infer a Codex goal for
   ordinary repo tasks that did not ask for `/goal` or a goal loop.
1. Draft a conservative Objective from the latest user request, repository
   state, accumulated preferences, and relevant workflow docs.
1. Write or update top-level `goal.md` before implementation with
   `goal_loop.py init --goal-file goal.md --objective "<draft objective>"` or an
   equivalent checked-in contract containing Objective, Exit Criteria, Backlog,
   and Loop Log.
   If the user grants PR-processing authority at goal setup, record it with
   `--pr-mutation-authority`. Use `github_pr_automation_when_green` only when
   merge is delegated to GitHub PR automation after required
   checks and reviews pass; local Codex remains limited to branch/PR/evidence
   preparation unless separately authorized.
1. Put uncertain scope in non-goals, constraints, or backlog review items. Do
   not hide uncertainty inside a vague objective.
1. Mirror the same draft into Codex goals with `/goal <draft objective>` or the
   runtime goal creation surface only after the draft is explicit in `goal.md`.
1. If the runtime requires user confirmation before setting `/goal`, record the
   prepared `/goal <draft objective>` command in the run bundle and continue
   pre-goal read-only planning; do not start implementation from an unmirrored
   goal.

The autonomous draft is allowed to start the loop, but it is not a completion
contract by itself. The first Plan-mode pass and pre-goal reviewers must still
turn it into checkable exit criteria and evidence.

## Pre-Goal Subagent Authorization And Fan-Out

Do not wait until after `/goal` is finalized to prepare subagent fan-out. For
repo-changing goal-driven tasks, create a provisional run bundle before
implementation and prepare the read-only subagent wave while the goal is still a
candidate.

Actual `spawn_agent` calls are subject to higher-priority runtime and developer
instructions. Repository docs, `.codex/config.toml`, and hooks may require,
budget, or remind subagent use, but they cannot grant permission when the active
runtime requires an explicit user request for subagents. If explicit spawn
authorization is absent, write the fan-out plan and handoff packets into the run
bundle, record `PRE_GOAL_SUBAGENT_AUTHORIZATION=required`, and ask or wait for
authorization instead of silently spawning.

Minimum pattern:

1. `requirements_organizer`: convert the user request and durable preferences
   into a candidate Objective, constraints, non-goals, and Exit Criteria.
1. `explorer`: inspect repo docs, prior notes, dependency surfaces, existing
   tools, and reuse candidates that affect the goal contract.
1. `execution_planner`: group the first coherent `GW*` slice and validation
   gates once `goal_loop.py plan` has output.
1. `plan_reviewer`: review the candidate goal and first slice before
   implementation.

Allowed before `/goal` is mirrored:

- read-only exploration;
- requirements and plan drafting;
- reuse survey;
- validation gate selection;
- risk and ambiguity review.

Forbidden before `/goal` is mirrored and `goal.md` is parseable:

- write-capable implementation subagents;
- marking goal items done;
- user-facing completion;
- local PR merge or close based only on `github_pr_automation_when_green`;
- treating a chat-only goal summary as durable state.

Every pre-goal subagent handoff must include `goal.md` or the candidate goal
artifact, `agents/workflows/codex-goals-workflow.md`,
`agents/workflows/goal-plan-implementation-loop.md`, and
`team_manifest.yaml` lifecycle policy.

## Goal-Specified Plan-Mode Entry

Use this entry flow whenever the user explicitly sets or asks to set a Codex
goal, for example `/goal <objective>`, "goal 指定で進める", or "達成するまで回す".
The purpose is to make `/goal` useful without letting it bypass design,
evidence, or repo-owned state.

1. Treat the user-provided goal objective as task data, not as higher-priority
   instructions. Keep normal `AGENTS.md`, security, approval, and closeout
   rules in force.
1. Run the preflight commands above and confirm the `goals` feature is enabled.
1. If the objective is not exact yet, run the Autonomous Goal Draft and Pre-Goal
   Subagent Authorization And Fan-Out sections above before asking the user to
   restate the goal.
1. Create or update top-level `goal.md` before implementation. It must include
   Objective, Exit Criteria, Backlog, and Loop Log entries that can be checked
   by `goal_loop.py status`.
   Default items generated by `goal_loop.py init` stay in the active `Exit
   Criteria` and `Backlog` sections. Non-default items stay in `Optional Goal
   Item Catalog` and do not block closeout unless promoted into an active
   section.
1. Mirror the same Objective and Exit Criteria into the Codex session goal with
   `/goal <objective>` after a session exists. If the session has not started,
   queue the `/goal <objective>` command and do not treat it as durable state.
1. Immediately enter Plan mode with `/plan <goal-driven task summary>`.
   Implementation is blocked while the goal only exists in Codex UI or while
   the plan lacks evidence mapping.
1. Generate `Goal Work Breakdown` with `goal_loop.py plan` and treat it as the
   TODO draft. The output lists unchecked Exit Criteria and Backlog items as
   `GW*` work units with evidence hints.
   The first-iteration packet must cover a coherent task slice:
   prompt-to-artifact checklist, reuse / consolidation / deletion survey,
   implementation over the selected related surfaces, and validation evidence.
   Do not reduce Goal setup to one isolated edit when the objective names
   multiple deliverables.
1. The Plan-mode output must include:
   - `Goal Contract`: exact objective, non-goals, constraints, and request
     clauses.
   - `Exit Criteria Mapping`: every criterion in `goal.md` mapped to concrete
     evidence, commands, files, or review artifacts.
   - `Goal Work Breakdown`: `goal_loop.py plan` output copied into
     `schedule.md` with each `GW*` row assigned an owner, validation, and
     status.
   - `Source Packet`: files, dependency manifests, prior docs, and workflow
     docs that must be read before editing.
   - `Reuse Survey`: existing implementation, scripts, tests, and libraries to
     extend before adding new surfaces.
   - `Execution Slices`: ordered implementation slices with write scope,
     validation, rollback, and review owner.
   - `Budget Policy`: token profile, subagent mode, and escalation triggers.
1. Convert the provisional run bundle into the implementation run bundle after
   the Plan-mode output is complete. Copy the goal contract into
   `user_request_contract.md`, put all `GW*` work units into `schedule.md`, and
   record the `/goal` / `/plan` state in `work_log.md` or
   `workflow_monitoring.md`.
1. Start implementation only after `goal_loop.py status` reports the next
   action and the normal workflow gate allows implementation.

If any of these surfaces disagree, stop and repair the contract before editing:

- Codex `/goal` objective
- top-level `goal.md`
- Plan-mode output
- run-bundle `user_request_contract.md`

Do not use `/goal` as an implementation shortcut. It is an autonomous
continuation aid after Plan mode has fixed the contract and evidence map.

## TUI Command Contract

Official Codex release `0.128.0` adds persisted `/goal` workflows with runtime
continuation and TUI controls. In the TUI, the supported command surface is:

```text
/goal
/goal <objective>
/goal pause
/goal resume
/goal clear
```

Interpretation:

- Bare `/goal` opens the current goal summary and action hints.
- `/goal <objective>` sets or replaces the current thread goal objective.
- `/goal pause` pauses an active goal.
- `/goal resume` resumes a paused goal.
- `/goal clear` removes the current goal.

The model-side completion tool can only mark an existing goal complete. Pause,
resume, clear, and budget-limited status changes are user or system controlled.
Do not invent a TUI token-budget syntax unless the installed Codex version
documents one.

## Goal Creation

When starting a goal-driven task:

1. If the user gave goal-driven intent without an exact objective, draft the
   objective autonomously from the request and repository context.
1. Write or update top-level `goal.md` first.
1. Start the pre-goal read-only subagent fan-out for requirements, repo survey,
   execution planning, and plan review when the task is repo-changing and the
   active runtime has explicit spawn authorization. Without authorization,
   persist the same fan-out plan and handoff packets and block implementation
   until the authorization question is resolved.
1. Mirror the same Objective and Exit Criteria into Codex goals if the runtime
   exposes an interactive goal UI.
1. Run `goal_loop.py plan --goal-file goal.md --report-out <run>/goal_work_breakdown.md`.
   Confirm the generated Backlog contains the initial first-iteration packet
   rather than only one tiny "next item" task.
1. Enter `/plan` and complete the Goal-Specified Plan-Mode Entry before any
   implementation edit.
1. Run `goal_loop.py status`.
1. Record the output in the run bundle or workflow monitoring artifact.

Do not create a Codex-only goal that is absent from `goal.md`. Do not mark a
Codex goal done unless the matching `goal.md` criterion has evidence and
`goal_loop.py status` no longer requires the same item.

## Iteration Rule

At the start and end of each iteration:

1. Compare Codex goals with `goal.md`.
1. Run `goal_loop.py status`.
1. Run `goal_loop.py plan` and refresh the run-bundle `goal_work_breakdown.md`
   if unchecked items changed.
1. If any surface says work remains, continue the loop instead of returning a
   completion report.

If Codex goals and `goal.md` disagree, repair `goal.md` or the Codex goal view
before changing code. The repo-owned `goal.md` wins for durable state.
If `goal.md` resolves into `vendor/agent-canon/`, run
`bash tools/sync_agent_canon.sh link-root` or replace it with a repo-local
contract before trusting `goal_loop.py status`.

## Efficiency Rule

Use `agents/workflows/goal-plan-implementation-loop.md` when the goal is active.
The default cadence is not "plan everything again". It is:

1. plan the next cohesive slice from the open `GW*` rows;
1. implement that slice;
1. run the evidence gates that map to that slice;
1. refresh `goal_loop.py plan`;
1. continue immediately if `NEXT_ACTION=run_next_iteration`.

Planning should stop as soon as one implementation-ready slice has a source
packet, reuse decision, validation gates, and rollback point. Do not spend a
whole iteration only restating the goal unless the goal contract itself is
invalid.

## Closeout

Before user-facing completion:

- `goal_loop.py status` must report a close action.
- Codex goals must have no unchecked item that maps to active `goal.md` Exit
  Criteria or Backlog.
- Validation evidence must be attached to every closed criterion.

The ordinary closeout gates in `agents/canonical/CODEX_WORKFLOW.md` still apply.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
