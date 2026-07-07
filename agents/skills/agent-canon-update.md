# AgentCanon Update Skill
<!--
@dependency-start
contract skill
responsibility Documents AgentCanon Update Skill for this repository.
upstream design ../canonical/skills.md skill canon registry
upstream design ../../documents/agent-canon-update-route.md canonical AgentCanon update route
upstream design ../../documents/agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
upstream implementation ../../tools/update_agent_canon.sh high-level AgentCanon update wrapper
upstream implementation ../../tools/sync_agent_canon.sh root-view and submodule sync helper
downstream design ./agent-update-branch.md separates parent update branch lanes from source AgentCanon PR work
@dependency-end
-->

Use this skill when the task is about bringing AgentCanon itself, a vendored
`vendor/agent-canon` pin, root runtime views, or parent-repo AgentCanon update
TODO state up to date.

## Reader Map

- Purpose: describes the route for updating AgentCanon itself, parent submodule
  pins, shared root views, and AgentCanon update TODOs.
- Use When: the task touches `vendor/agent-canon/`, AgentCanon pins, root view
  repair, or latest-state update checks.
- Section path: Use When identifies triggers; Core References lists owner
  documents; Route contains the operational rules; Closeout Evidence names the
  required validation and PR evidence.
- Boundary: parent pin updates must not hide dirty AgentCanon source changes.

## Use When

- The user asks to update, latest, refresh, or sync AgentCanon.
- `make agent-canon-ensure-latest`, `make agent-canon-latest`,
  `tools/update_agent_canon.sh`, or `tools/sync_agent_canon.sh` is the likely
  entrypoint.
- A parent repo has AgentCanon submodule pin drift, root-view drift, safe
  dirty checkout state, or pending `.agent-canon/update-state.toml` TODOs.
- `vendor/agent-canon/` contains local AgentCanon source commits that need a
  standalone AgentCanon branch/PR before the parent pin can move.

## Core References

- `documents/agent-canon-update-route.md`
- `documents/agent-canon-parent-repo-latest-checklist.md`
- `documents/SHARED_RUNTIME_SURFACES.md`
- `tools/update_agent_canon.sh`
- `tools/sync_agent_canon.sh`
- `agents/skills/agent-update-branch.md`

## Route

1. Classify the repo shape before editing:
   - standalone AgentCanon source repo
   - parent repo with `vendor/agent-canon` submodule
   - legacy subtree or committed snapshot compatibility repo
1. In parent repos, classify the dirty state by update surface, not by the
   whole worktree. Unrelated parent dirty paths do not block the update.
1. Use the high-level route first:

```bash
make agent-canon-update-plan
make agent-canon-ensure-latest
```

1. Let `make agent-canon-ensure-latest` classify dirty submodule state. When the
   dirty checkout can be preserved mechanically, it runs the preserve-dirty
   route, restores the dirty state after merging AgentCanon `main`, repairs root
   views, and checks shared-surface drift.
   Do not replace that route with a manual stop-first rule.

1. If `vendor/agent-canon/` has local source commits, or latest reports a
   detached head, merge conflict, restore conflict, or other unsafe state, move
   the work through an AgentCanon source branch/PR:

```bash
bash tools/update_agent_canon.sh merge-main-into-current-preserve-dirty
git -C vendor/agent-canon push origin HEAD
```

   Reuse the current AgentCanon source branch / PR when it already owns the
   shared-canon work. Do not create a fresh AgentCanon branch only because the
   user added an instruction, the diff is a bounded follow-up, or the parent pin
   has not moved yet. A new AgentCanon branch requires a recorded reason such as
   a merged / closed / unpushable current PR, an unrelated ownership surface, a
   required review-isolation boundary, or unsafe divergent state.

1. After a safe update or PR merge, repair and verify root runtime views:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

   This is the mandatory `agentcanon_structure_followup` gate for every
   AgentCanon source change, parent submodule pin change, `.gitmodules` change,
   AgentCanon-owned root runtime view change, shared root-copy surface change,
   and parent root sync PR. Record `agentcanon_structure_followup=required`
   when the task enters one of those surfaces, and record
   `agentcanon_structure_followup=pass` only after `link-root` and `check` both
   complete from the owning parent root. When the source change is made in
   standalone AgentCanon or inside `vendor/agent-canon/`, run the parent /
   derived root follow-up after the source PR is integrated or while preparing
   the parent pin/root-view PR; do not close the source/pin lane with an
   optional or "if needed" sync note.

1. Handle parent update TODOs before unrelated work:

```bash
python3 tools/agent_tools/agent_canon_update_todos.py status
python3 tools/agent_tools/agent_canon_update_todos.py plan --write
```

1. For parent-repo pin isolation, pair this skill with
   `$agent-update-branch` and use the `canon-pin` lane. Do not use
   `$agent-update-branch` as the source AgentCanon PR route. Do not create a
   separate parent `canon-pin` branch when the current parent branch already
   carries the same pin/update lane.

## Closeout Evidence

Record:

- update route decision and dirty-surface classification
- `git submodule status vendor/agent-canon` or standalone AgentCanon commit
- AgentCanon PR URL or GitHub `main` SHA when source work was involved
- `agentcanon_structure_followup=required` and
  `agentcanon_structure_followup=pass` evidence, including
  `bash tools/sync_agent_canon.sh link-root` and
  `bash tools/sync_agent_canon.sh check`
- parent update TODO status and completed / deferred task IDs
- validation selected from `documents/runtime-profiles-and-check-matrix.md`
