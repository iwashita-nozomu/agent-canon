# AgentCanon Repository Instructions
<!--
@dependency-start
contract agent-runtime
responsibility Documents AgentCanon Repository Instructions for this repository.
downstream design README.md shared canon overview must reflect runtime contract
downstream design ROOT_AGENTS.md template-root runtime entrypoint owner map
downstream implementation tools/agent_tools/check_agent_runtime_alignment.py validates runtime owner-map alignment
downstream implementation .codex/hooks/branch_worktree_guard.py blocks unconfirmed shared-checkout Git mutations
@dependency-end
-->

This tree is the standalone AgentCanon source of truth. Template and derived
repositories consume it through `vendor/agent-canon/` and root runtime views.

## Reader Map

This repository entrypoint maps agents working inside the standalone
AgentCanon source tree to the canonical owner surfaces. Use `Read First` for
the initial document path, `Scope` to identify the source area, `Runtime Owner
Map` to find the owner of runtime contracts, `Task Entry` to start
repo-changing work, and `Validation` before closeout. This file routes readers;
the detailed workflow, skill, role, profile, and closeout rules remain in the
owner surfaces it names.
- After context compaction, invoke the final-objective declaration required by
  `agents/COMMUNICATION_PROTOCOL.md` section `Post-Compaction Objective
  Re-Declaration Contract` before any work resumes.

## Codex Loading Priority In This Tree

Codex still applies global Codex-home guidance before repository guidance. For
repository guidance, it walks from the detected project root to the current
working directory, selecting at most one instruction file in each directory:
`AGENTS.override.md`, then `AGENTS.md`, then fallback names listed in
`project_doc_fallback_filenames`. Empty instruction files are skipped, and
Codex stops adding project-doc content when the combined size reaches
`project_doc_max_bytes`.

When the detected project root is this AgentCanon checkout, this `AGENTS.md` is
the source-tree repo instruction entrypoint. When Codex starts from a template
or derived parent root, the parent `/AGENTS.md` runtime view loads
`ROOT_AGENTS.md` instead. In that parent-root session, this file is not
automatically loaded merely because a task mentions AgentCanon or edits
`vendor/agent-canon/`; read it manually only when the AgentCanon source
checkout is selected as owner evidence. It becomes automatic repo instruction
context only when Codex's project-root/CWD chain is inside the AgentCanon
checkout.

Do not copy rules between these files to "make sure" Codex sees them. Put
template-root runtime behavior in `ROOT_AGENTS.md`, standalone AgentCanon source
entry behavior in this file, GitHub-subtree overlay behavior in
`.github/AGENTS.md`, and workflow / skill / closeout policy in the owner
surfaces listed below.

## Read First

- `README.md`
- `documents/README.md`
- `agents/README.md`
- `agents/workflows/README.md`
- `agents/canonical/README.md`
- `.codex/README.md`

## Scope

- root runtime entrypoint source: `ROOT_AGENTS.md`
- Codex runtime defaults: `.codex/`
- public skill registry and shims: `agents/skills/`, `.agents/skills/`
- internal workflow routines: `agents/internal-routines/`
- workflow, subagent, and review contracts: `agents/`
- shared runtime surface ownership: `documents/`
- agent support tools and validation: `tools/`
- agent-specific regression tests: `tests/agent_tools/`

Multiple chats or sessions may use this checkout concurrently. Treat every
unknown dirty, staged, untracked, branch, and worktree state as owned by the
user or another chat, and preserve that state across routing and repair.
Protected Git operations include `git restore`, `git reset`, forced `git clean`,
mutating `git stash`, checkout/switch, and branch/worktree create, delete, move,
rename, or prune. Proven exact task ownership only bounds which paths may be
named in an approval request; explicit destructive approval remains required.
A protected mutation proceeds only when the user
explicitly approves it and the same command segment carries
`AGENT_CANON_DESTRUCTIVE_GIT_AUTHORITY=explicit_user_approval` plus a nonempty
`AGENT_CANON_DESTRUCTIVE_GIT_REASON`. Branch/worktree creation additionally
requires same-segment `AGENT_CANON_BRANCH_WORKTREE_AUTHORITY=user_request` or
`agent_canon_workflow` plus a nonempty `AGENT_CANON_BRANCH_WORKTREE_REASON`;
the creation and destructive requirements are an AND gate. Collision handling keeps the current
branch/worktree and requests user direction.

## Runtime Owner Map

| Contract | Owner Surface | Validation |
| -------- | ------------- | ---------- |
| root runtime entrypoint | `ROOT_AGENTS.md`; `documents/shared-runtime-surfaces.toml` | `bash tools/sync_agent_canon.sh check` |
| workflow family, spawn budget, role topology | `agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |
| role behavior and stage conditions | `.codex/agents/*.toml`; `agents/agents_config.json` | `check_agent_runtime_alignment.py` |
| public skill registry | `agents/skills/catalog.yaml`; `.agents/skills/*/SKILL.md` | `check_agent_runtime_alignment.py` |
| internal routine placement | `agents/internal-routines/README.md`; `documents/repo-structure-contract.toml` | `repo_structure_contract.py` |
| implementation flow and handoff packet | `agents/workflows/implementation-waterfall-workflow.md`; `agents/COMMUNICATION_PROTOCOL.md` | task run bundle review |
| shared-checkout Git mutation and branch/worktree creation route | `agents/canonical/CODEX_WORKFLOW.md`; `.codex/hooks/branch_worktree_guard.py`; `agents/skills/worktree-health.md` | explicit destructive approval AND `branch_creation_reason=<reason>` / `worktree_creation_reason=<reason>`; critical PreToolUse guard; `check_convention_compliance.py` |
| runtime profile and validation routing | `documents/runtime-profiles-and-check-matrix.md` | profile-specific checks |
| closeout evidence | `tools/agent_tools/task_close.py`; `tools/agent_tools/report_artifact_checks.py` | closeout artifact gate |
| AgentCanon update transaction | `documents/agent-canon-update-route.md`; `tools/agent_tools/update_lifecycle_contract.py` | boundary-owned G1-G6 receipts; `tools/agent_tools/task_close.py` |

Update the owner surface first, then adjust this entrypoint when reader routing
changes. `AGENTS.md` is a repository-local map; it is not the policy source for
workflow stages, skill routing, role behavior, or closeout gates.

## Task Entry

AgentCanon source updates enter only through
`documents/agent-canon-update-route.md`. Its machine-readable transaction and
ToolCall records are owned by `tools/agent_tools/update_lifecycle_contract.py`;
the Decision Sufficiency policy remains owned by
`agents/skills/agent-orchestration.md#Decision Sufficiency Packet`.

For repo-changing work, create or reuse the run bundle and follow the
machine-readable packet emitted by:

```bash
python3 tools/agent_tools/task_start.py \
  --task "short task summary" \
  --owner "codex" \
  --workspace-root "$PWD"
```

For a new run directory:

```bash
python3 tools/agent_tools/bootstrap_agent_run.py \
  --task "short task summary" \
  --owner "codex" \
  --workspace-root "$PWD"
```

The emitted workflow, skills, review roles, document packets, wave plan, and
validation route are the task packet for downstream agents.

## Validation

- runtime alignment: `python3 tools/agent_tools/check_agent_runtime_alignment.py`
- structure contract: `python3 tools/agent_tools/repo_structure_contract.py --root . --contract documents/repo-structure-contract.toml`
- responsibility scope: `python3 tools/agent_tools/responsibility_scope.py --root .`
- shared runtime views: `bash tools/sync_agent_canon.sh check`
- closeout: `python3 tools/agent_tools/task_close.py ...`
