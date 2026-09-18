# AgentCanon Source Routing
<!--
@dependency-start
contract agent-runtime
responsibility Routes standalone AgentCanon source-tree readers to canonical owners without re-owning task procedures.
upstream design ../../documents/design/entrypoint-owner-map.md root entrypoint grammar and responsibility boundary
upstream design ../../documents/conventions/software-engineering-principles.md contract-complete engineering decision policy
upstream design ../../agents/internal-routines/chatgpt-codex-routing.md request modality and Codex handoff owner
upstream design ../../agents/skills/comprehensive-development.md cross-surface implementation-basis consumer
upstream design ../../agents/canonical/CODEX_WORKFLOW.md executable task and closeout owner
upstream design ../../agents/canonical/CODEX_SUBAGENTS.md subagent lifecycle owner
upstream design ../../AGENTS.md minimal always-loaded source entrypoint
downstream implementation ../../tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py validates thin entrypoint structure
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates runtime owner-map alignment
downstream design ../../agents/canonical/ROOT_IMPLEMENTATION.md selected implementation decision detail
downstream design ../../agents/canonical/ROOT_EXECUTION.md selected execution boundary detail
downstream design ../../agents/canonical/ROOT_DELIVERY.md selected evidence and delivery detail
@dependency-end
-->

## Repository Role

Optional source-only index: consult the matching row only when its owner is
unresolved. It is not a startup reading list and does not apply to generated
consumer instructions. Known owners and unchanged decisions bypass this index.

## Reader Map

| Task intent | Canonical owner |
| --- | --- |
| ChatGPT conversation closure vs Codex workspace execution | [agents/internal-routines/chatgpt-codex-routing.md](../../agents/internal-routines/chatgpt-codex-routing.md) |
| request interpretation and task transport after Codex admission | [agents/skills/agent-orchestration.md](../../agents/skills/agent-orchestration.md), [agents/skills/codex-task-workflow.md](../../agents/skills/codex-task-workflow.md), [agents/canonical/CODEX_WORKFLOW.md](../../agents/canonical/CODEX_WORKFLOW.md) |
| contract-complete implementation and engineering basis | [agents/canonical/ROOT_IMPLEMENTATION.md](../../agents/canonical/ROOT_IMPLEMENTATION.md) (selected decision section), [documents/conventions/software-engineering-principles.md](../../documents/conventions/software-engineering-principles.md), [agents/skills/comprehensive-development.md](../../agents/skills/comprehensive-development.md), task-specific implementation Skills |
| mathematical, algorithmic, and numerical obligation ownership | [documents/design/semantic-responsibility-contract.md](../../documents/design/semantic-responsibility-contract.md), [documents/design/algorithm-implementation-boundary.md](../../documents/design/algorithm-implementation-boundary.md), selected proof / optimization Skill |
| configured execution and environment diagnosis | [agents/canonical/ROOT_EXECUTION.md#configured-execution-and-bounded-diagnosis](../../agents/canonical/ROOT_EXECUTION.md#configured-execution-and-bounded-diagnosis) |
| design-to-implementation correspondence | [agents/internal-routines/design-implementation-correspondence.md](../../agents/internal-routines/design-implementation-correspondence.md) |
| repository structure and responsibility boundaries | [agents/skills/structure-refactor.md](../../agents/skills/structure-refactor.md), `documents/structure/repo-structure-contract.toml` |
| branch, worktree, and destructive Git safety | [agents/canonical/ROOT_EXECUTION.md](../../agents/canonical/ROOT_EXECUTION.md) (checkout / cleanup sections), [agents/skills/worktree-health.md](../../agents/skills/worktree-health.md), [agents/canonical/CODEX_WORKFLOW.md](../../agents/canonical/CODEX_WORKFLOW.md), `.codex/hooks/` |
| Git branch scope and annex pointer/payload operations | [documents/operations/BRANCH_SCOPE.md](../../documents/operations/BRANCH_SCOPE.md), [documents/operations/annex.md](../../documents/operations/annex.md) |
| AgentCanon source update and publication | [agents/skills/agent-canon-update.md](../../agents/skills/agent-canon-update.md), [agents/skills/pr-processing.md](../../agents/skills/pr-processing.md) |
| subagent activation and handoff | [agents/skills/agent-orchestration.md](../../agents/skills/agent-orchestration.md), [agents/skills/subagent-bootstrap.md](../../agents/skills/subagent-bootstrap.md), [agents/canonical/CODEX_SUBAGENTS.md](../../agents/canonical/CODEX_SUBAGENTS.md) |
| team composition, role/model/skills/authority/handoff selection | [agents/canonical/ROOT_EXECUTION.md#team-ownership](../../agents/canonical/ROOT_EXECUTION.md#team-ownership), [agents/task_catalog.yaml](../../agents/task_catalog.yaml), [agents/skills/agent-orchestration.md](../../agents/skills/agent-orchestration.md), [agents/skills/subagent-bootstrap.md](../../agents/skills/subagent-bootstrap.md), [agents/canonical/CODEX_SUBAGENTS.md](../../agents/canonical/CODEX_SUBAGENTS.md) |
| validation profile and closeout | [agents/canonical/ROOT_DELIVERY.md#formatting-and-validation](../../agents/canonical/ROOT_DELIVERY.md#formatting-and-validation), [documents/runtime/runtime-profiles-and-check-matrix.md](../../documents/runtime/runtime-profiles-and-check-matrix.md), [agents/canonical/CODEX_WORKFLOW.md](../../agents/canonical/CODEX_WORKFLOW.md), `tools/runtime/lifecycle/task_close.py` |
| GitHub Issue / PR publication and status | [agents/canonical/ROOT_DELIVERY.md](../../agents/canonical/ROOT_DELIVERY.md) (selected evidence / delivery section), [agents/skills/pr-processing.md](../../agents/skills/pr-processing.md), [agents/internal-routines/github-status-lifecycle.md](../../agents/internal-routines/github-status-lifecycle.md) |

The detailed common-boundary rows apply only when that responsibility is active;
read the relevant section, not all three documents at startup. Consumer roots
retain their portable rules and do not read these source-only paths.

## Always-On Boundary

Shared constraints remain in [ROOT_AGENTS.md](../../ROOT_AGENTS.md); this source-only
map owns paths and owner selection, not common behavior or consumer configuration.

## Runtime Owner Map

| Responsibility | Canonical owner | Validation / reader route |
| --- | --- | --- |
| root runtime entrypoint | `bootstrap.sh` | `bash bootstrap.sh --help` |
| workflow family, spawn budget, role topology | `agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |
| public skill registry | `agents/skills/catalog.yaml` | `check_agent_runtime_alignment.py` |
| AgentCanon source publication | [agents/skills/agent-canon-update.md](../../agents/skills/agent-canon-update.md), [agents/skills/pr-processing.md](../../agents/skills/pr-processing.md) | repository-topic-clone and PR checks |
| entrypoint responsibility grammar | [documents/design/entrypoint-owner-map.md](../../documents/design/entrypoint-owner-map.md) | `check_entrypoint_owner_map.py` |
| implementation decision precedence | [documents/conventions/software-engineering-principles.md](../../documents/conventions/software-engineering-principles.md) | task-specific Skill and review evidence |

## Task Entry

Resolve an undecided request modality through the ChatGPT / Codex row before
repository orchestration; reuse an established admission. After Codex admission,
resolve only the missing task shape or owner, and read the selected owner before
editing. Apply the common base's bounded-task activation boundary.

Use the team-composition row only before team selection, change, or delegation.
Do not replace a selected model or omit a selected role without an
evidence-backed handoff update to the responsible owner.

## Validation Routing

Use the active runtime profile and the validation / closeout Reader Map row
for source-wide evidence only when required by the selected route.
