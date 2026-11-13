# Request intent and continuing work

<!--
@dependency-start
contract design
responsibility Relates user questions, authorized edits, continuation and task-owned cleanup.
upstream design ../../ROOT_AGENTS.md user authority and safety boundaries
upstream design ../../agents/skills/agent-orchestration.md task routing
upstream design ../../agents/skills/codex-task-workflow.md implementation and validation
upstream design ../../agents/COMMUNICATION_PROTOCOL.md native handoff
upstream design ../../agents/canonical/CODEX_SUBAGENTS.md selected agent lifecycle
upstream design ../../agents/skills/dependency-module-change.md checkout cleanup
upstream design ../runtime/runtime-log-archive.md durable evidence publication
@dependency-end
-->

## Scope

The current conversation holds the agreed outcome, scope, acceptance and next
work. Inspect the relevant source, prior agreement and actual Git state before
asking for facts they already establish. Ask before changing scope, expected
results or a major approach; continue independent authorized work while waiting.

A question during ongoing work usually steers that work. Answer it and continue
the original outcome unless the user cancels it or selects an incompatible task.
Diagnosis, a child handback, or a saved checkpoint does not complete unfinished
implementation or authorized delivery.

## Existing owners

- `agent-orchestration` selects the applicable workflow and roles.
- `codex-task-workflow` owns implementation units, retirement review and validation.
- Native Codex tools provide collaboration and carry bounded handoffs. Git and
  the conversation preserve the selected scope and actual results.
- `dependency-module-change` and the existing checkout lifecycle own removal of
  task-owned checkouts. Preserve unknown changes and read back selected publication.
- Runtime log and Eval owners preserve selected evidence outside source.

## Related Document Closure

Use [design-to-diff review](../../agents/internal-routines/design-implementation-correspondence.md#related-document-closure)
when a selected design needs comparison with the implementation. Follow only
references needed for that decision. Mathematical and experiment artifacts retain
their domain contracts.

## Completion

Complete the agreed implementation, remove replaced code and stale callers,
then validate the final responsibility unit. Finish authorized publication and
read back its result. Remove task-owned temporary resources when their use ends.
Report what changed, the evidence, relevant rejected approaches and remaining
limits. Custom run bundles, task manifests, progress ledgers and terminal gates
are retired.
