@ROOT_AGENTS.md
# AgentCanon Repository Instructions
<!--
@dependency-start
contract agent-runtime
responsibility Routes standalone AgentCanon source-tree readers to canonical owners without re-owning task procedures.
upstream design documents/design/entrypoint-owner-map.md root entrypoint grammar and responsibility boundary
upstream design documents/conventions/software-engineering-principles.md contract-complete engineering decision policy
upstream design agents/internal-routines/chatgpt-codex-routing.md request modality and Codex handoff owner
upstream design agents/skills/comprehensive-development.md cross-surface implementation-basis consumer
upstream design agents/canonical/CODEX_WORKFLOW.md executable task and closeout owner
upstream design agents/canonical/CODEX_SUBAGENTS.md subagent lifecycle owner
downstream design ROOT_AGENTS.md common root base read before source-specific map
downstream implementation tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py validates thin entrypoint structure
downstream implementation tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates runtime owner-map alignment
@dependency-end
-->

## Repository Role

Use this entrypoint only for the standalone AgentCanon source checkout. The
leading `@ROOT_AGENTS.md` means: read [ROOT_AGENTS.md](ROOT_AGENTS.md) first, then
return here for source-specific owner selection. It is an explicit read, not
automatic expansion or a runtime import.

The maps below own AgentCanon source, runtime, publication, and validation
routes. They replace the common base's consumer map for this checkout only,
not its shared constraints. This file is not an input to consumer composition
and must not be copied into generated consumer instructions.

## Reader Map

| Task intent | Canonical owner |
| --- | --- |
| ChatGPT conversation closure vs Codex workspace execution | [agents/internal-routines/chatgpt-codex-routing.md](agents/internal-routines/chatgpt-codex-routing.md) |
| request interpretation and task transport after Codex admission | [agents/skills/agent-orchestration.md](agents/skills/agent-orchestration.md), [agents/skills/codex-task-workflow.md](agents/skills/codex-task-workflow.md), [agents/canonical/CODEX_WORKFLOW.md](agents/canonical/CODEX_WORKFLOW.md) |
| contract-complete implementation and engineering basis | [documents/conventions/software-engineering-principles.md](documents/conventions/software-engineering-principles.md), [agents/skills/comprehensive-development.md](agents/skills/comprehensive-development.md), task-specific implementation Skills |
| mathematical, algorithmic, and numerical obligation ownership | [documents/design/semantic-responsibility-contract.md](documents/design/semantic-responsibility-contract.md), [documents/design/algorithm-implementation-boundary.md](documents/design/algorithm-implementation-boundary.md), selected proof / optimization Skill |
| design-to-implementation correspondence | [agents/internal-routines/design-implementation-correspondence.md](agents/internal-routines/design-implementation-correspondence.md) |
| repository structure and responsibility boundaries | [agents/skills/structure-refactor.md](agents/skills/structure-refactor.md), `documents/structure/repo-structure-contract.toml` |
| branch, worktree, and destructive Git safety | [agents/skills/worktree-health.md](agents/skills/worktree-health.md), [agents/canonical/CODEX_WORKFLOW.md](agents/canonical/CODEX_WORKFLOW.md), `.codex/hooks/` |
| Git branch scope and annex pointer/payload operations | [documents/operations/BRANCH_SCOPE.md](documents/operations/BRANCH_SCOPE.md), [documents/operations/annex.md](documents/operations/annex.md) |
| AgentCanon source update and publication | [agents/skills/agent-canon-update.md](agents/skills/agent-canon-update.md), [agents/skills/pr-processing.md](agents/skills/pr-processing.md) |
| subagent activation and handoff | [agents/skills/agent-orchestration.md](agents/skills/agent-orchestration.md), [agents/skills/subagent-bootstrap.md](agents/skills/subagent-bootstrap.md), [agents/canonical/CODEX_SUBAGENTS.md](agents/canonical/CODEX_SUBAGENTS.md) |
| team composition, role/model/skills/authority/handoff selection | [agents/task_catalog.yaml](agents/task_catalog.yaml), [agents/skills/agent-orchestration.md](agents/skills/agent-orchestration.md), [agents/skills/subagent-bootstrap.md](agents/skills/subagent-bootstrap.md), [agents/canonical/CODEX_SUBAGENTS.md](agents/canonical/CODEX_SUBAGENTS.md) |
| formatter settings and direct commands | [documents/design/formatting.md](documents/design/formatting.md) |
| validation profile and closeout | [documents/runtime/runtime-profiles-and-check-matrix.md](documents/runtime/runtime-profiles-and-check-matrix.md), [agents/canonical/CODEX_WORKFLOW.md](agents/canonical/CODEX_WORKFLOW.md), `tools/runtime/lifecycle/task_close.py` |
| GitHub Issue / PR publication and status | [agents/skills/pr-processing.md](agents/skills/pr-processing.md), [agents/internal-routines/github-status-lifecycle.md](agents/internal-routines/github-status-lifecycle.md) |

## Always-On Boundary

Keep AgentCanon-specific paths and owner selection here; use the entrypoint
responsibility grammar row below when changing that boundary. Shared behavior
belongs to the common base; task procedures remain with the selected Skill,
workflow, or internal routine. Consumer-specific instructions belong to that
consumer, not to this source entrypoint.

## Runtime Owner Map

| Responsibility | Canonical owner | Validation / reader route |
| --- | --- | --- |
| root runtime entrypoint | `bootstrap.sh` | `bash bootstrap.sh --help` |
| workflow family, spawn budget, role topology | `agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |
| public skill registry | `agents/skills/catalog.yaml` | `check_agent_runtime_alignment.py` |
| AgentCanon source publication | [agents/skills/agent-canon-update.md](agents/skills/agent-canon-update.md), [agents/skills/pr-processing.md](agents/skills/pr-processing.md) | repository-topic-clone and PR checks |
| entrypoint responsibility grammar | [documents/design/entrypoint-owner-map.md](documents/design/entrypoint-owner-map.md) | `check_entrypoint_owner_map.py` |
| implementation decision precedence | [documents/conventions/software-engineering-principles.md](documents/conventions/software-engineering-principles.md) | task-specific Skill and review evidence |

## Task Entry

Apply the ChatGPT / Codex Reader Map row before repository orchestration.
Only after Codex admission, resolve the task shape and canonical owner through
the Reader Map and public Skill registry, and read the selected owner before
editing.

Use the team-composition Reader Map row for the shared team-selection boundary.
Do not replace a selected model or omit a selected role without an
evidence-backed handoff update to the responsible owner.

## Validation Routing

Use the active runtime profile and the validation / closeout Reader Map row
for source-wide evidence when required by the selected route.
