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

## Goal Creation

When starting a goal-driven task:

1. Write or update top-level `goal.md` first.
1. Mirror the same Objective and Exit Criteria into Codex goals if the runtime
   exposes an interactive goal UI.
1. Run `goal_loop.py status` and MCP `goal.loop_status`.
1. Record both outputs in the run bundle or workflow monitoring artifact.

Do not create a Codex-only goal that is absent from `goal.md`. Do not mark a
Codex goal done unless the matching `goal.md` criterion has evidence and
`goal_loop.py status` no longer requires the same item.

## Iteration Rule

At the start and end of each iteration:

1. Compare Codex goals with `goal.md`.
1. Run `goal_loop.py status`.
1. Run MCP `goal.loop_status` when available.
1. If any surface says work remains, continue the loop instead of returning a
   completion report.

If Codex goals and `goal.md` disagree, repair `goal.md` or the Codex goal view
before changing code. The repo-owned `goal.md` wins for durable state.

## Closeout

Before user-facing completion:

- `goal_loop.py status` must report a close action.
- MCP `goal.loop_status` must not report `NEXT_ACTION=run_next_iteration`.
- Codex goals must have no unchecked item that maps to active `goal.md` Exit
  Criteria or Backlog.
- Validation evidence must be attached to every closed criterion.

The ordinary closeout gates in `agents/canonical/CODEX_WORKFLOW.md` still apply.
