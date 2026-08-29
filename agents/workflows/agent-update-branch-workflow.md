# Agent Update Branch Workflow
<!--
@dependency-start
contract workflow
responsibility Defines branch lanes for Template and AgentCanon runtime updates.
upstream design ../canonical/CODEX_WORKFLOW.md provides closeout gates
downstream implementation ../../tools/repository/git/agent_update_branch.sh validates lane-specific diffs
downstream design ../skills/agent-update-branch.md exposes the workflow as a skill
@dependency-end
-->

This workflow keeps AgentCanon source updates, private knowledge/eval feedback, and parent
project changes in separate ownership lanes. A parent never becomes an update
hub for AgentCanon source, and no source pin or projection is maintained.

## Branch Reuse Gate

Do not create an `agent-updates/*` branch when the current branch / PR already
owns the same lane. Continue the existing branch for added user instructions,
bounded follow-ups, checklist evidence, and parent pin updates that belong to the
same AgentCanon PR route. A new branch requires a recorded
`branch_creation_reason=<reason>`, current-task explicit user approval, and one
of these conditions:

- the current branch / PR is merged, closed, or unpushable
- the update belongs to a different lane or ownership surface
- explicit review isolation is required
- continuing would mix incompatible pin, private knowledge, eval, or protected-surface work
- the user explicitly asks for a separate branch

The reason and workflow condition only bound the approval request. Normal
creation requires creation authority/reason in the same command segment.
Force-create or ref-overwrite routes additionally require destructive
authority/reason in that segment. Ambient variables and prior segments do not
authorize it. A collision keeps the current checkout unchanged and returns to
the user.

## Branch Lanes

- `agent-updates/knowledge-eval/<slug>`: private knowledge and eval-only updates.
- `agent-updates/canon-source/<slug>`: qualified standalone AgentCanon source clone and source PR updates.
- `agent-updates/integration/<slug>`: merges update branches and validates them before `main`.

## Private Knowledge/Eval Branch

1. Reuse the current branch if it already owns this private knowledge/eval lane.
1. Otherwise request user direction and approval for `agent-updates/knowledge-eval/<slug>` after recording `branch_creation_reason=<reason>`; create it only through the same-segment creation-authority guard contract. Add the destructive authority/reason pair only when the route force-creates or overwrites a ref.
1. Change only `evidence/agent-evals/`, `.codex/personal/skills/*/SKILL.md`, or run-local evaluation artifacts that document private feedback.
1. Run `bash tools/repository/git/agent_update_branch.sh validate knowledge-eval`.
1. Commit with a message that states this is a private knowledge/eval-only agent update branch.
1. Push with `bash tools/repository/git/agent_update_branch.sh push knowledge-eval <branch>`.

## Canon Source Branch

1. Reuse the current branch if it already owns this canon-source lane.
1. Otherwise request user direction and approval for `agent-updates/canon-source/<slug>` after recording `branch_creation_reason=<reason>`; create it only through the same-segment creation-authority guard contract. Add the destructive authority/reason pair only when the route force-creates or overwrites a ref.
1. Update the standalone AgentCanon source in the qualified development clone and keep the parent tracked tree unchanged.
1. Run the AgentCanon focused checks, bootstrap runtime checks, and `bash tools/repository/git/agent_update_branch.sh validate canon-source`.
1. Commit with the AgentCanon Issue and source commit in the message.
1. Push the branch.

## Integration Branch

1. Reuse the current integration branch if it already owns this integration lane.
1. Otherwise request user direction and approval for `agent-updates/integration/<slug>` after recording `branch_creation_reason=<reason>`; create it only through the same-segment creation-authority guard contract. Add the destructive authority/reason pair only when the route force-creates or overwrites a ref.
1. Fetch the update branches and merge them one by one.
1. Resolve conflicts in the integration branch, not on `main`.
1. Run:

```bash
bash tools/analysis/dependencies/run_repo_dependency_review.sh --fail-missing
make agent-checks
tools/bin/agent-canon docs check
make ci
```

1. Push the integration branch.
1. Merge to `main` only after the integration branch is clean, validated, and reviewed.

## Convention Compliance Gate

Before closeout or handoff, run `python3 tools/validation/semantic/convention/check_convention_compliance.py` and fix any `CONVENTION_COMPLIANCE=fail` finding. This keeps workflow prohibitions, convention tool gates, and skill-routing hooks mechanically checked instead of relying on prompt memory.
