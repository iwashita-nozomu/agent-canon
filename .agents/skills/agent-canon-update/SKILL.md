---
name: agent-canon-update
description: Use when updating AgentCanon itself, refreshing a vendored vendor/agent-canon submodule pin, repairing AgentCanon root runtime views, applying AgentCanon update TODOs, or routing local AgentCanon source commits through a proper AgentCanon branch and PR before parent pin updates.
---
<!--
@dependency-start
contract skill
responsibility Documents AgentCanon Update for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/agent-canon-update.md human-facing skill canon
upstream design ../../../documents/agent-canon-update-route.md canonical AgentCanon update route
upstream design ../../../documents/agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
upstream implementation ../../../tools/update_agent_canon.sh high-level AgentCanon update wrapper
upstream implementation ../../../tools/sync_agent_canon.sh root-view and submodule sync helper
upstream implementation ../../../tools/agent_tools/agent_canon_preflight.py blocks unsafe task-entry updates
@dependency-end
-->

# AgentCanon Update

## Reader Map

- Purpose: runtime skill for AgentCanon source updates, parent submodule pin
  refreshes, root-view repair, and latest-state checklist work.
- Use When: updating `vendor/agent-canon/`, applying AgentCanon update TODOs,
  or routing local AgentCanon commits through source PRs before parent pins.
- Tool Commands: run this skill's command packet, then read the canonical
  update-route and parent latest-state documents.
- Boundary: do not hide dirty AgentCanon source work inside a parent pin update
  or create branches without the documented reason.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill agent-canon-update --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/agent-canon-update.md`.
1. Read `documents/agent-canon-update-route.md` and
   `documents/agent-canon-parent-repo-latest-checklist.md`.
1. Classify the repo as standalone AgentCanon, parent submodule repo, or legacy
   compatibility repo before running update commands.
1. In parent repos, classify dirty state by AgentCanon update surface:
   `vendor/agent-canon/`, parent gitlink, `.gitmodules`, and AgentCanon-owned
   root views. Do not let unrelated parent dirty files block the update route.
1. Before the high-level update runs, task-start preflight fails closed when an
   exact `reports/agent-eval-runs/<run-id>/<producer>.stdout.txt` or
   `.stderr.txt` capture remains tracked, untracked, or ignored. Preserve the
   capture, sync and verify the eval archive, write its bounded summary, delete
   the transient explicitly, and rerun preflight. Ordinary unrelated parent
   dirt remains allowed.
1. Prefer the high-level parent route:

Run `make agent-canon-update-plan` first. If it reports an update, request
current-task user approval and rerun `make agent-canon-ensure-latest` with all
four inline Git authority/reason fields in the same command segment.

1. If `vendor/agent-canon/` contains local AgentCanon source commits or source
   dirty state, do not hide them in a parent pin update. Route them through an
   AgentCanon branch/PR first:

After current-task user approval, invoke the protected merge wrapper with all
four inline Git authority/reason fields, then push the already-current branch.
Do not switch or create a checkout as a recovery shortcut.

   Reuse the current AgentCanon source branch / PR when it already owns the
   shared-canon work. Do not create a fresh branch for a bounded follow-up,
   mid-task user instruction, dirty-state avoidance, or checklist addendum.
   Record a reason before requesting approval for any new branch. A reason or
   workflow route does not authorize creation: current-task user approval and
   all four same-command authority/reason values are required.

1. After a safe update or PR merge, repair and verify root views:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

   Treat this as the mandatory `agentcanon_structure_followup` gate whenever
   AgentCanon source, the parent submodule pin, `.gitmodules`, root runtime
   views, shared root-copy surfaces, or parent root sync state changed. Record
   `agentcanon_structure_followup=required` before the commands and
   `agentcanon_structure_followup=pass` only after the sync check passes.
   Template / derived parent roots must run this gate from the parent root after
   AgentCanon source changes are integrated, or while preparing the parent
   pin/root-view PR.

1. Check and apply parent update TODOs before unrelated work:

```bash
python3 tools/agent_tools/agent_canon_update_todos.py status
python3 tools/agent_tools/agent_canon_update_todos.py plan --write
```

1. Use `$agent-update-branch` only for parent-repo `canon-pin` update branches.
   AgentCanon source edits use a standalone AgentCanon branch and PR. Reuse the
   current parent branch if it already owns the same pin/update lane.
1. Close out with update route, dirty-surface classification, submodule pin or
   AgentCanon commit, PR URL if any, root-view check, TODO status, and selected
   validation evidence.
