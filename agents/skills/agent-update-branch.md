# Agent Update Branch Skill
<!--
@dependency-start
contract skill
responsibility Documents Agent Update Branch Skill for this repository.
upstream design ../canonical/CODEX_WORKFLOW.md provides branch and closeout policy
upstream design ../../documents/operations/BRANCH_SCOPE.md commit/push authority and local-only state
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
- `integration`: combines update branches before `main`; local merge ordering,
  conflict preservation, and integrated-head readback belong to `$integration`.

The parent repository never becomes an AgentCanon update hub and no source pin
or projection is maintained. `repository-topic-clone` owns the qualified
checkout path, selected mode, and cleanup; this skill owns lane selection only.

## Knowledge-Eval Lane

Change only `eval/` source contracts, `.codex/personal/skills/*/SKILL.md`, or
run-local evaluation inputs that document private feedback. Producers,
checkers, and static fixtures remain under `eval/`; generated reports and
packets go to the explicit external runtime spool and are published through
the `agent-canon-log` archive.

Commit with a message identifying this as a private knowledge/eval-only update
only when the current task authorizes that commit. Push through the lane adapter
only when task authority selects publication to the designated remote:

```bash
bash tools/repository/git/agent_update_branch.sh push knowledge-eval <branch>
```

Lane selection and validation grant neither commit nor push authority. When
either action is not selected, preserve that local state and report it.

## AgentCanon Source Updates

Use the qualified standalone AgentCanon development checkout prepared by
`repository-topic-clone` and keep the parent
tracked tree unchanged. `$agent-canon-update` owns the source Issue, source
PR, runtime validation, and `main` readback; do not duplicate that route here.

## Integration Handoff

When update branches must be combined, hand the branch set and dependency order
to `$integration`. That skill owns fetching, merge/conflict resolution,
integrated-head validation, push/readback, and the final `main` merge. This
skill does not repeat integration commands or merge gates.

## Validation

Before a local commit or handoff, validate the selected lane's changed paths:

```bash
bash tools/repository/git/agent_update_branch.sh validate <lane>
```

When an authorized `push` is selected, the adapter performs the same lane
validation; run the standalone command only when a pre-commit result could change
the commit decision. Run convention compliance when the selected change touches
a convention contract it checks. Integration dependency review and repository
static analysis are selected by `$integration`; they do not apply to other
lanes.
