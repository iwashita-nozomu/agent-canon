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

Use this entrypoint for the standalone AgentCanon source checkout. Its
source-specific owner maps below supplement the common base; they do not apply
to a consumer's generated instructions.

Directory-local [AGENTS.md](AGENTS.md) files may narrow behavior for their subtree. They
must add only the responsibility owned by that subtree and must not copy a
root, workflow, or Skill policy for visibility.

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
| validation profile and closeout | [documents/runtime/runtime-profiles-and-check-matrix.md](documents/runtime/runtime-profiles-and-check-matrix.md), [agents/canonical/CODEX_WORKFLOW.md](agents/canonical/CODEX_WORKFLOW.md), `tools/runtime/lifecycle/task_close.py` |
| GitHub Issue / PR publication and status | [agents/skills/pr-processing.md](agents/skills/pr-processing.md), [agents/internal-routines/github-status-lifecycle.md](agents/internal-routines/github-status-lifecycle.md) |

## Always-On Boundary

Follow the selected owner and its validation route rather than inventing a
fallback, wrapper, compatibility path, or local copy of policy.

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
editing. A bounded request with an identified owner, path, and targeted
validation stays bounded; broader design, orchestration, research, or subagent
machinery activates only when its owner-defined condition is present.

Use the team-composition Reader Map row for the shared team-selection boundary.
Do not replace a selected model or omit a selected role without an
evidence-backed handoff update to the responsible owner.

## Validation Routing

Use the active runtime profile and the validation / closeout Reader Map row
for source-wide evidence when required by the selected route. Examples or
commands in another owner are not a universal checklist.
