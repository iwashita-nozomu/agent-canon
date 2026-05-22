---
name: agent-update-branch
description: Use when Memory, eval results, AgentCanon pins, or other agent-runtime updates should be isolated on template-derived update branches and later integrated through a controlled branch workflow.
---
<!--
@dependency-start
responsibility Documents Agent Update Branch skill for this repository.
upstream design ../../../agents/workflows/agent-update-branch-workflow.md defines branch lanes and integration gates
upstream implementation ../../../tools/agent_tools/agent_update_branch.sh validates and pushes update branches
@dependency-end
-->

# Agent Update Branch

1. Read `agents/workflows/agent-update-branch-workflow.md`.
1. Classify the update lane:
   - `memory-eval`: only `memory/`, `agents/evals/`, `.agents/skills/*/SKILL.md`, or run-local evaluation artifacts intended for feedback capture
   - `canon-pin`: `.gitmodules`, `.agent-canon/update-state.toml`, `vendor/agent-canon`, and root AgentCanon symlink/copy surfaces
   - `integration`: a branch that merges one or more `agent-updates/*` branches back toward `main`
1. Use a template-derived branch name:
   - `agent-updates/memory-eval/<slug>`
   - `agent-updates/canon-pin/<slug>`
   - `agent-updates/integration/<slug>`
1. Before pushing, run the lane validator:

```bash
bash tools/agent_tools/agent_update_branch.sh validate <lane>
```

1. Push with:

```bash
bash tools/agent_tools/agent_update_branch.sh push <lane> <branch>
```

1. For integration, do not squash away evidence. Merge update branches on an integration branch, run dependency review and static analysis, then fast-forward or merge to `main` only after the integration gate passes.
