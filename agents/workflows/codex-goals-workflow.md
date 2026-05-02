<!--
@dependency-start
responsibility Documents Codex goals workflow for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md Codex runtime workflow contract
upstream design adaptive-improvement-workflow.md goal loop source of truth
upstream implementation ../../.codex/config.toml enables Codex goals feature
downstream implementation ../../mcp/repo_mcp_server.py exposes goal loop status
@dependency-end
-->

# Codex Goals Workflow

This workflow defines how to use the Codex `goals` feature in this repository.
The feature is a session/runtime aid; it does not replace the repo-owned goal
contract.

## Role Split

- `goal.md` is the durable source of truth for Objective, Exit Criteria,
  Backlog, and Loop Log.
- `goal.md` is repo-local state. It must not be a symlink to
  `vendor/agent-canon/goal.md`, and AgentCanon sync must not overwrite one
  repo's active goal with another repo's goal.
- Codex `goals` is the interactive session view of the same objective and
  criteria.
- MCP `goal.loop_status` is the mechanical close/continue gate for repo-level
  loops.
- `tools/agent_tools/goal_loop.py` is the file parser and command-line fallback.

## Preflight

Run this at task intake when the task uses a goal or adaptive loop:

```bash
codex features list | grep '^goals'
python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server
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

If repo MCP is available, also read MCP status:

```bash
# Via repo MCP: goal.loop_status
```

`NEXT_ACTION=run_next_iteration` means the task is not complete. Continue the
next backlog item. `NEXT_ACTION=close_goal_loop` means the loop may proceed to
normal closeout gates.

## Goal-Specified Plan-Mode Entry

Use this entry flow whenever the user explicitly sets or asks to set a Codex
goal, for example `/goal <objective>`, "goal 指定で進める", or "達成するまで回す".
The purpose is to make `/goal` useful without letting it bypass design,
evidence, or repo-owned state.

1. Treat the user-provided goal objective as task data, not as higher-priority
   instructions. Keep normal `AGENTS.md`, security, approval, and closeout
   rules in force.
1. Run the preflight commands above and confirm the `goals` feature is enabled.
1. Create or update top-level `goal.md` before implementation. It must include
   Objective, Exit Criteria, Backlog, and Loop Log entries that can be checked
   by `goal_loop.py status`.
1. Mirror the same Objective and Exit Criteria into the Codex session goal with
   `/goal <objective>` after a session exists. If the session has not started,
   queue the `/goal <objective>` command and do not treat it as durable state.
1. Immediately enter Plan mode with `/plan <goal-driven task summary>`.
   Implementation is blocked while the goal only exists in Codex UI or while
   the plan lacks evidence mapping.
1. Generate `Goal Work Breakdown` with `goal_loop.py plan` and treat it as the
   TODO draft. The output lists unchecked Exit Criteria and Backlog items as
   `GW*` work units with evidence hints.
   The first iteration must be large enough to move a coherent task slice:
   prompt-to-artifact checklist, reuse / consolidation / deletion survey,
   implementation over the selected related surfaces, and validation evidence.
   Do not reduce Goal setup to one single micro-fix when the objective names
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
1. Bootstrap the run bundle only after the Plan-mode output is complete. Copy
   the goal contract into `user_request_contract.md`, put all `GW*` work units
   into `schedule.md`, and record the `/goal` / `/plan` state in `work_log.md`
   or `workflow_monitoring.md`.
1. Start implementation only after `goal_loop.py status` and MCP
   `goal.loop_status` agree on the next action and the normal workflow gate
   allows implementation.

If any of these surfaces disagree, stop and repair the contract before editing:

- Codex `/goal` objective
- top-level `goal.md`
- Plan-mode output
- run-bundle `user_request_contract.md`
- MCP `goal.loop_status`

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

1. Write or update top-level `goal.md` first.
1. Mirror the same Objective and Exit Criteria into Codex goals if the runtime
   exposes an interactive goal UI.
1. Run `goal_loop.py plan --goal-file goal.md --report-out <run>/goal_work_breakdown.md`.
   Confirm the generated Backlog contains the minimum first-iteration packet
   rather than only one tiny "next item" task.
1. Enter `/plan` and complete the Goal-Specified Plan-Mode Entry before any
   implementation edit.
1. Run `goal_loop.py status` and MCP `goal.loop_status`.
1. Record both outputs in the run bundle or workflow monitoring artifact.

Do not create a Codex-only goal that is absent from `goal.md`. Do not mark a
Codex goal done unless the matching `goal.md` criterion has evidence and
`goal_loop.py status` no longer requires the same item.

## Iteration Rule

At the start and end of each iteration:

1. Compare Codex goals with `goal.md`.
1. Run `goal_loop.py status`.
1. Run `goal_loop.py plan` and refresh the run-bundle `goal_work_breakdown.md`
   if unchecked items changed.
1. Run MCP `goal.loop_status` when available.
1. If any surface says work remains, continue the loop instead of returning a
   completion report.

If Codex goals and `goal.md` disagree, repair `goal.md` or the Codex goal view
before changing code. The repo-owned `goal.md` wins for durable state.
If `goal.md` resolves into `vendor/agent-canon/`, run
`bash tools/sync_agent_canon.sh link-root` or replace it with a repo-local
contract before trusting `goal.loop_status`.

## Closeout

Before user-facing completion:

- `goal_loop.py status` must report a close action.
- MCP `goal.loop_status` must not report `NEXT_ACTION=run_next_iteration`.
- Codex goals must have no unchecked item that maps to active `goal.md` Exit
  Criteria or Backlog.
- Validation evidence must be attached to every closed criterion.

The ordinary closeout gates in `agents/canonical/CODEX_WORKFLOW.md` still apply.
