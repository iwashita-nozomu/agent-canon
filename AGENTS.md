@ROOT_AGENTS.md
# AgentCanon Repository Instructions
<!--
@dependency-start
contract agent-runtime
responsibility Provides the AgentCanon source-editing scope and conditional owner route.
upstream design documents/design/entrypoint-owner-map.md reading boundary
upstream design ROOT_AGENTS.md portable common constraints
upstream design documents/operations/BRANCH_SCOPE.md branch operating contract
upstream design documents/conventions/coding-conventions-testing.md test responsibility contract
upstream design documents/design/rust-agent-tool-migration.md AgentCanon tool migration owner
upstream design agents/skills/empirical-prompt-tuning.md evidence-based Skill revision
downstream design agents/canonical/SOURCE_ROUTING.md optional source owner index
@dependency-end
-->

## Repository Role

These source-only rules extend `@ROOT_AGENTS.md`. Consumer composition uses the
portable ROOT contract, not this entrypoint. Apply the matching row when that
operation is selected; this is not a checklist for every task.

## Runtime Owner Map

| Operation | Required action | Canonical owner |
| --- | --- | --- |
| Branch lifecycle | Use an Issue-qualified topic and current handoff scope. Preserve unknown state, integrate by real merge, and read back selected publication/cleanup. | [branch contract](documents/operations/BRANCH_SCOPE.md), [checkout lifecycle](documents/rule/repository-topic-clone.md) |
| Skill improvement cycle | Define outcome/evidence, revise the canonical Skill, validate/review/evaluate as selected, and record adoption/rejection. Selected delivery includes publication/readback; static checks cannot prove improved agent behavior. | [empirical revision](agents/skills/empirical-prompt-tuning.md), [source delivery](agents/skills/agent-canon-update.md) |
| Test responsibility | Setup supplies inputs, the product API performs the action, and an independent oracle checks the result. Repair the owning failure; do not implement the product in tests, weaken the oracle, or infer defects from unrun tests. Changes to input assumptions, scope, required properties, or major approach need prior agreement. | [test-role contract](documents/conventions/coding-conventions-testing.md#3-unit-test-contract) |
| AgentCanon tool migration | All AgentCanon-owned tool implementations, including orchestration, target Rust through the existing owner in bounded units. Preserve command/output contracts and retire replaced implementations. Consumer product and test code keep their own language choices. | [tool migration](documents/design/rust-agent-tool-migration.md) |
| Unresolved source owner | Read the selected owner row only. | [source map](agents/canonical/SOURCE_ROUTING.md) |

When a selected Skill's adapter or command context is unresolved, use
[Skill Paths](agents/canonical/skills.md#skill-paths). For formatting AgentCanon
files, use [formatter settings](documents/design/formatting.md#ownership-and-purpose).
