# Agent Update Branch Workflow
<!--
@dependency-start
contract workflow
responsibility Defines branch lanes for Template and AgentCanon runtime updates.
upstream design ../canonical/CODEX_WORKFLOW.md provides closeout gates
downstream implementation ../../tools/agent_tools/agent_update_branch.sh validates lane-specific diffs
downstream design ../skills/agent-update-branch.md exposes the workflow as a skill
@dependency-end
-->

This workflow makes the template repository the update hub for AgentCanon pins,
memory feedback, and eval feedback without mixing those updates into feature branches.

## Branch Reuse Gate

Do not create an `agent-updates/*` branch when the current branch / PR already
owns the same lane. Continue the existing branch for added user instructions,
bounded follow-ups, checklist evidence, and parent pin updates that belong to the
same AgentCanon PR route. A new branch requires a recorded
`branch_creation_reason=<reason>` and one of these conditions:

- the current branch / PR is merged, closed, or unpushable
- the update belongs to a different lane or ownership surface
- explicit review isolation is required
- continuing would mix incompatible pin, memory, eval, or protected-surface work
- the user explicitly asks for a separate branch

## Branch Lanes

- `agent-updates/memory-eval/<slug>`: memory and eval-only updates.
- `agent-updates/canon-pin/<slug>`: AgentCanon submodule pin, AgentCanon update-state, and root runtime view updates.
- `agent-updates/integration/<slug>`: merges update branches and validates them before `main`.

## Memory/Eval Branch

1. Reuse the current branch if it already owns this memory/eval lane.
1. Otherwise start from `template/main` and create `agent-updates/memory-eval/<slug>` only after recording `branch_creation_reason=<reason>`.
1. Change only `memory/`, `evidence/agent-evals/`, `.agents/skills/*/SKILL.md`, or run-local evaluation artifacts that document feedback.
1. Run `bash tools/agent_tools/agent_update_branch.sh validate memory-eval`.
1. Commit with a message that states this is a memory/eval-only agent update branch.
1. Push with `bash tools/agent_tools/agent_update_branch.sh push memory-eval <branch>`.

## Canon Pin Branch

1. Reuse the current branch if it already owns this canon-pin lane.
1. Otherwise start from `template/main` and create `agent-updates/canon-pin/<slug>` only after recording `branch_creation_reason=<reason>`.
1. Update the AgentCanon submodule pin, `.agent-canon/update-state.toml`, and root runtime links.
1. Run `bash tools/sync_agent_canon.sh plan`, `bash tools/sync_agent_canon.sh check`, and `bash tools/agent_tools/agent_update_branch.sh validate canon-pin`.
1. Commit with the AgentCanon target commit in the message.
1. Push the branch.

## Integration Branch

1. Reuse the current integration branch if it already owns this integration lane.
1. Otherwise start from `template/main` and create `agent-updates/integration/<slug>` only after recording `branch_creation_reason=<reason>`.
1. Fetch the update branches and merge them one by one.
1. Resolve conflicts in the integration branch, not on `main`.
1. Run:

```bash
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
make agent-checks
tools/bin/agent-canon docs check
make ci
```

1. Push the integration branch.
1. Merge to `main` only after the integration branch is clean, validated, and reviewed.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
