# Agent Update Branch Skill
<!--
@dependency-start
contract skill
responsibility Documents Agent Update Branch Skill for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md provides branch and closeout policy
upstream design ./agent-canon-update.md owns standalone AgentCanon source PRs
upstream implementation ../../tools/repository/git/agent_update_branch.sh validates update branch lanes
@dependency-end
-->

Use this skill when agent-runtime updates should not be mixed into ordinary feature work.

## Branch Reuse

Do not create an `agent-updates/*` branch when the current branch / PR already
owns the same lane. Continue the existing branch / PR for added user
instructions, bounded follow-ups, checklist evidence, and parent pin updates
that belong to the same route. A new branch requires a recorded
`branch_creation_reason=<reason>`, current-task user approval, and one of:

- the current branch / PR is merged, closed, or unpushable;
- the update belongs to a different lane or ownership surface;
- explicit review isolation is required;
- continuing would mix incompatible pin, private knowledge, eval, or protected-surface work; or
- the user explicitly asks for a separate branch.

The reason and workflow condition only bound the approval request. Normal
creation requires creation authority/reason in the same command segment.
Force-create or ref-overwrite routes additionally require destructive
authority/reason in that segment. A collision keeps the current checkout
unchanged and returns to the user.

## Lanes

- `knowledge-eval`: private knowledge/feedback, eval manifests, eval results,
  and skill prompt feedback only.
- `canon-source`: standalone AgentCanon source and runtime updates; route these
  changes to `$agent-canon-update` rather than mixing them into parent work.
- `integration`: combines update branches before `main`; local merge ordering,
  conflict preservation, and integrated-head readback belong to `$integration`.

The parent repository never becomes an AgentCanon update hub and no source pin
or projection is maintained. `repository-topic-clone` owns the qualified clone
path and cleanup; this skill owns lane selection only.

## Knowledge-Eval Lane

Change only `eval/` source contracts, `.codex/personal/skills/*/SKILL.md`, or
run-local evaluation inputs that document private feedback. Producers,
checkers, and static fixtures remain under `eval/`; generated reports and
packets go to the explicit external runtime spool and are published through
the `agent-canon-log` archive.

Run the lane validator, then commit with a message identifying this as a
private knowledge/eval-only update and push through the lane adapter:

```bash
bash tools/repository/git/agent_update_branch.sh validate knowledge-eval
bash tools/repository/git/agent_update_branch.sh push knowledge-eval <branch>
```

## Canon-Source Lane

Use the qualified standalone AgentCanon development clone and keep the parent
tracked tree unchanged. `$agent-canon-update` owns the source Issue, source
PR, runtime validation, and `main` readback; do not duplicate that route here.

## Integration Handoff

When update branches must be combined, hand the branch set and dependency order
to `$integration`. That skill owns fetching, merge/conflict resolution,
integrated-head validation, push/readback, and the final `main` merge. This
skill does not repeat integration commands or merge gates.

## Required Gates

- Validate the lane with `bash tools/repository/git/agent_update_branch.sh validate <lane>`.
- Push the branch with `bash tools/repository/git/agent_update_branch.sh push <lane> <branch>`.
- Run the convention compliance check before handoff or closeout:

```bash
python3 tools/validation/semantic/convention/check_convention_compliance.py
```

Integration dependency review and repository static analysis are selected by
`$integration`; do not treat them as an additional gate for non-integration
lanes.
