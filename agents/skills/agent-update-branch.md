# Agent Update Branch Skill
<!--
@dependency-start
contract skill
responsibility Documents Agent Update Branch Skill for this repository.
upstream design ../workflows/agent-update-branch-workflow.md defines update branch lifecycle
upstream implementation ../../tools/agent_tools/agent_update_branch.sh validates update branch lanes
@dependency-end
-->

Use this skill when agent-runtime updates should not be mixed into ordinary feature work.

## Lanes

- `memory-eval`: updates durable agent memory, eval manifests, eval result artifacts, and skill prompt feedback.
- `canon-pin`: updates the `vendor/agent-canon` submodule pin, `.agent-canon/update-state.toml`, `.gitmodules`, and root AgentCanon link/copy views.
- `integration`: merges one or more `agent-updates/*` branches into an integration branch before `main`.

`canon-pin` is a parent-repo pin lane only. AgentCanon source edits, local
`vendor/agent-canon` commits, prompt/skill/tool source changes, and update-route
repairs move through `$agent-canon-update` and a standalone AgentCanon
branch/PR first. After that PR lands, the parent repo uses
`make agent-canon-ensure-latest` and root-view sync to advance the pin. See
`documents/agent-canon-update-route.md`.

This skill does not authorize a new branch when the current parent branch
already owns the same lane. Continue the existing branch / PR for added user
instructions, bounded follow-ups, and checklist or evidence updates. Create a new
`agent-updates/*` branch only when the current branch is merged, closed,
unpushable, has an unrelated ownership lane, needs explicit review isolation, or
would mix incompatible pin / memory / eval ownership. Record
`branch_creation_reason=<reason>` before creating it.

## Required Gates

- Validate the lane with `bash tools/agent_tools/agent_update_branch.sh validate <lane>`.
- Push the branch with `bash tools/agent_tools/agent_update_branch.sh push <lane> <branch>`.
- For integration branches, run `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` and repo static analysis before merging to `main`.
