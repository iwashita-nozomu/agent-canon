# Agent Update Branch Skill
<!--
@dependency-start
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

## Required Gates

- Validate the lane with `bash tools/agent_tools/agent_update_branch.sh validate <lane>`.
- Push the branch with `bash tools/agent_tools/agent_update_branch.sh push <lane> <branch>`.
- For integration branches, run `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing` and repo static analysis before merging to `main`.
