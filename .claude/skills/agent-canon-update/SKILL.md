---
name: agent-canon-update
description: Use when updating AgentCanon itself, refreshing a vendored vendor/agent-canon submodule pin, repairing AgentCanon root runtime views, applying AgentCanon update TODOs, or routing local AgentCanon source commits through a proper AgentCanon branch and PR before parent pin updates.
---
<!--
@dependency-start
responsibility Documents AgentCanon Update for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/skills/agent-canon-update.md human-facing skill canon
upstream design ../../../documents/agent-canon-update-route.md canonical AgentCanon update route
upstream design ../../../documents/agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
upstream implementation ../../../tools/update_agent_canon.sh high-level AgentCanon update wrapper
upstream implementation ../../../tools/sync_agent_canon.sh root-view and submodule sync helper
@dependency-end
-->

# AgentCanon Update

1. Read `agents/skills/agent-canon-update.md`.
1. Read `documents/agent-canon-update-route.md` and
   `documents/agent-canon-parent-repo-latest-checklist.md`.
1. Classify the repo as standalone AgentCanon, parent submodule repo, or legacy
   compatibility repo before running update commands.
1. In parent repos, classify dirty state by AgentCanon update surface:
   `vendor/agent-canon/`, parent gitlink, `.gitmodules`, and AgentCanon-owned
   root views. Do not let unrelated parent dirty files block the update route.
1. Prefer the high-level parent route:

```bash
make agent-canon-update-plan
make agent-canon-ensure-latest
```

1. If `vendor/agent-canon/` contains local AgentCanon source commits or source
   dirty state, do not hide them in a parent pin update. Route them through an
   AgentCanon branch/PR first:

```bash
bash tools/update_agent_canon.sh merge-main-into-current
git -C vendor/agent-canon push origin HEAD
```

1. After a safe update or PR merge, repair and verify root views:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

1. Check and apply parent update TODOs before unrelated work:

```bash
python3 tools/agent_tools/agent_canon_update_todos.py status
python3 tools/agent_tools/agent_canon_update_todos.py plan --write
```

1. Use `$agent-update-branch` only for parent-repo `canon-pin` update branches.
   AgentCanon source edits use a standalone AgentCanon branch and PR.
1. Close out with update route, dirty-surface classification, submodule pin or
   AgentCanon commit, PR URL if any, root-view check, TODO status, and selected
   validation evidence.
