# Agent Update Branch Workflow
<!--
@dependency-start
responsibility Defines branch lanes for Template and AgentCanon runtime updates.
upstream design ../canonical/CODEX_WORKFLOW.md provides closeout gates
downstream implementation ../../tools/agent_tools/agent_update_branch.sh validates lane-specific diffs
downstream design ../skills/agent-update-branch.md exposes the workflow as a skill
@dependency-end
-->

This workflow makes the template repository the update hub for AgentCanon pins,
memory feedback, and eval feedback without mixing those updates into feature branches.

## Branch Lanes

- `agent-updates/memory-eval/<slug>`: memory and eval-only updates.
- `agent-updates/canon-pin/<slug>`: AgentCanon submodule pin, AgentCanon update-state, and root runtime view updates.
- `agent-updates/integration/<slug>`: merges update branches and validates them before `main`.

## Memory/Eval Branch

1. Start from `template/main`.
1. Create `agent-updates/memory-eval/<slug>`.
1. Change only `memory/`, `agents/evals/`, `.agents/skills/*/SKILL.md`, or run-local evaluation artifacts that document feedback.
1. Run `bash tools/agent_tools/agent_update_branch.sh validate memory-eval`.
1. Commit with a message that states this is a memory/eval-only agent update branch.
1. Push with `bash tools/agent_tools/agent_update_branch.sh push memory-eval <branch>`.

## Canon Pin Branch

1. Start from `template/main`.
1. Create `agent-updates/canon-pin/<slug>`.
1. Update the AgentCanon submodule pin, `.agent-canon/update-state.toml`, and root runtime links.
1. Run `bash tools/sync_agent_canon.sh plan`, `bash tools/sync_agent_canon.sh check`, and `bash tools/agent_tools/agent_update_branch.sh validate canon-pin`.
1. Commit with the AgentCanon target commit in the message.
1. Push the branch.

## Integration Branch

1. Start from `template/main`.
1. Create `agent-updates/integration/<slug>`.
1. Fetch the update branches and merge them one by one.
1. Resolve conflicts in the integration branch, not on `main`.
1. Run:

```bash
bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing
make agent-checks
make docs-check
make ci
```

1. Push the integration branch.
1. Merge to `main` only after the integration branch is clean, validated, and reviewed.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/agent_tools/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
