# Codex Workflow

<!--
@dependency-start
contract agent-runtime
responsibility Routes to the active phase without loading inactive procedures.
upstream design ../../documents/design/entrypoint-owner-map.md reading boundary
downstream design ./CODEX_INTAKE.md intake and optional context selection
downstream design ./CODEX_ROUTING.md unresolved route selection
downstream design ./CODEX_BOOTSTRAP.md selected run bootstrap
downstream design ./CODEX_IMPLEMENTATION.md design and implementation
downstream design ./CODEX_COMPLETION.md validation and delivery
@dependency-end
-->

## Reader Map

This map selects Codex task phases and their active auxiliary routes. Phase
owners contain the procedures; ROOT owns the shared reading constraints.

| When | Start with |
| --- | --- |
| Task intake or relevant checkout/context changed | [intake](CODEX_INTAKE.md#1-intake) |
| Task family is unresolved | [task classification](CODEX_ROUTING.md#task-classification) |
| Skill selection is unresolved | [Skill selection](CODEX_ROUTING.md#contract-required-skill-set) |
| Validation profile is unresolved | [profile selection](CODEX_ROUTING.md#runtime-profile-and-risk-selection) |
| A file must be placed or moved | [placement](CODEX_ROUTING.md#3-placement) |
| The selected route requires run state | [run bootstrap](CODEX_BOOTSTRAP.md#4-run-bootstrap) |
| Design or implementation is active | [implementation reader map](CODEX_IMPLEMENTATION.md#reader-map) |
| Validation or closeout is due | [completion reader map](CODEX_COMPLETION.md#reader-map) |
| Additional context becomes necessary during the active phase | [context read conditions](CODEX_INTAKE.md#optional-context) and the active Skill's matching conditional link, then return to the interrupted phase |
| Execution fails | [bounded diagnosis](ROOT_EXECUTION.md#configured-execution-and-bounded-diagnosis) |
| Verification fails | [failure record](../../documents/operations/notes-lifecycle.md#failed-verification-record) when the result is observed |

## Completion Readiness

At closeout, use [completion readiness](CODEX_COMPLETION.md#completion-readiness)
for the already selected execution route.
