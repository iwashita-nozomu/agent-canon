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
downstream design ROOT_AGENTS.md explicit live-integration root entrypoint
downstream implementation tools/validation/semantic/entrypoint/check_entrypoint_owner_map.py validates thin entrypoint structure
downstream implementation tools/validation/semantic/runtime/check_agent_runtime_alignment.py validates runtime owner-map alignment
@dependency-end
-->

This tree is the standalone AgentCanon source of truth. This file is a reader
and owner map only. Task procedures, command recipes, role lifecycles,
implementation policy, and closeout schemas remain in the canonical surfaces
named below.

## Repository Role

Use this entrypoint when the detected repository root is the AgentCanon source
checkout. A default `project_template` or derived repository owns its tracked
instructions directly and does not acquire live AgentCanon runtime behavior by
mentioning this repository. `ROOT_AGENTS.md` applies only to an explicitly
selected `live-agent-canon` integration.

Directory-local `AGENTS.md` files may narrow behavior for their subtree. They
must add only the responsibility owned by that subtree and must not copy a
root, workflow, or Skill policy for visibility.

## Reader Map

| Task intent | Canonical owner |
| --- | --- |
| ChatGPT conversation closure vs Codex workspace execution | `agents/internal-routines/chatgpt-codex-routing.md` |
| request interpretation and task transport after Codex admission | `agents/skills/agent-orchestration.md`, `agents/skills/codex-task-workflow.md`, `agents/canonical/CODEX_WORKFLOW.md` |
| contract-complete implementation and engineering basis | `documents/conventions/software-engineering-principles.md`, `agents/skills/comprehensive-development.md`, task-specific implementation Skills |
| mathematical, algorithmic, and numerical obligation ownership | `documents/design/semantic-responsibility-contract.md`, `documents/design/algorithm-implementation-boundary.md`, selected proof / optimization Skill |
| design-to-implementation correspondence | `agents/internal-routines/design-implementation-correspondence.md` |
| repository structure and responsibility boundaries | `agents/skills/structure-refactor.md`, `documents/structure/repo-structure-contract.toml` |
| branch, worktree, and destructive Git safety | `agents/skills/worktree-health.md`, `agents/canonical/CODEX_WORKFLOW.md`, `.codex/hooks/` |
| AgentCanon source update and publication | `agents/skills/agent-canon-update.md`, `agents/skills/pr-processing.md` |
| subagent activation and handoff | `agents/skills/agent-orchestration.md`, `agents/skills/subagent-bootstrap.md`, `agents/canonical/CODEX_SUBAGENTS.md` |
| validation profile and closeout | `documents/runtime/runtime-profiles-and-check-matrix.md`, `agents/canonical/CODEX_WORKFLOW.md`, `tools/runtime/lifecycle/task_close.py` |
| GitHub Issue / PR publication and status | `agents/skills/pr-processing.md`, `agents/internal-routines/github-status-lifecycle.md` |

## Always-On Boundary

The explicit user request and the current tracked canonical owner are the
source of truth. Preserve unknown dirty, staged, untracked, branch, and worktree
state until the Git safety owner classifies it. Follow the selected owner and
its validation route rather than inventing a fallback, wrapper, compatibility
path, or local copy of policy.

Implementation sufficiency is not defined in this entrypoint. The implementation
owner selects the smallest contract-complete owning unit and records material
mathematical, domain, or engineering grounds and a validation oracle. Detailed
admission and blocker rules belong to the implementation and review Skills, not
here.

## Runtime Owner Map

| Responsibility | Canonical owner | Validation / reader route |
| --- | --- | --- |
| root runtime entrypoint | `bootstrap.sh` | `bash bootstrap.sh --help` |
| workflow family, spawn budget, role topology | `agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |
| public skill registry | `agents/skills/catalog.yaml` | `check_agent_runtime_alignment.py` |
| AgentCanon source publication | `agents/skills/agent-canon-update.md`, `agents/skills/pr-processing.md` | repository-topic-clone and PR checks |
| entrypoint responsibility grammar | `documents/design/entrypoint-owner-map.md` | `check_entrypoint_owner_map.py` |
| implementation decision precedence | `documents/conventions/software-engineering-principles.md` | task-specific Skill and review evidence |

## Task Entry

Resolve request modality through
`agents/internal-routines/chatgpt-codex-routing.md` before repository
orchestration. A `chatgpt` route closes in conversation without workspace
execution. A `codex` route hands its typed scope and validation oracle to
`agent-orchestration` before task-shape skill selection.

Resolve the task shape and canonical owner from the reader map and public Skill
registry only after Codex admission. Read the selected owner surface before
editing. A bounded request with an identified owner, path, and targeted
validation stays bounded; broader design, orchestration, research, or subagent
machinery activates only when its owner-defined condition is present.

Read-only web, connector, and supplied-material analysis remain ChatGPT work
unless the requested result depends on repository-local state, command
observation, mutation, iterative validation, or durable repository delivery.
Repository-changing work follows the selected Skill and workflow; this
entrypoint does not restate their sequence.

## Validation Routing

Use the validation route owned by the changed responsibility and active runtime
profile. Validate the contract and failure semantics that changed, then use the
canonical closeout owner for repository-wide evidence when the selected route
requires it. Do not turn the examples or commands in another owner into a
universal checklist.
