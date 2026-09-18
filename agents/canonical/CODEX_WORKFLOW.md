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

This entrypoint owns phase selection; the linked documents own the procedures.
Read the named section when its condition applies, not every linked file at startup.
Reuse still-applicable intake and decisions. A link is a read route, not an import,
new activation condition, or instruction to restart the workflow.

| When | Procedure owner | Start with |
| --- | --- | --- |
| Task intake; relevant checkout/context changed | [Codex Intake](CODEX_INTAKE.md) | [1. Intake](CODEX_INTAKE.md#1-intake), then the relevant intake section |
| Select task family, skills, validation profile, or placement | [Codex Routing](CODEX_ROUTING.md) | [Task Classification](CODEX_ROUTING.md#task-classification) |
| Selected route requires run state, goal handling, or token adaptation | [Codex Bootstrap](CODEX_BOOTSTRAP.md) | [4. Run Bootstrap](CODEX_BOOTSTRAP.md#4-run-bootstrap) or the named goal/token section |
| Design or implementation | [Codex Implementation](CODEX_IMPLEMENTATION.md) | [Design Integrity Gate](CODEX_IMPLEMENTATION.md#design-integrity-gate), [5. Implementation](CODEX_IMPLEMENTATION.md#5-implementation) |
| Validation, completion evidence, or closeout | [Codex Completion](CODEX_COMPLETION.md) | [6. Validation](CODEX_COMPLETION.md#6-validation), [Completion Readiness](CODEX_COMPLETION.md#completion-readiness) |

Required means applicable to the selected action, not mandatory on every run.
Do not reread AGENTS, enumerate all Skills, or load every packet/phase to start.
Select additional context only through [its read conditions](CODEX_INTAKE.md#optional-context).
An already resolved owner, route, and validation need no new routing pass.
