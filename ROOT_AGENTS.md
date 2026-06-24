<!--
@dependency-start
contract agent-runtime
responsibility Documents Agent Instructions for this repository.
upstream design README.md repository entrypoint and clone/update guidance.
upstream design documents/SHARED_RUNTIME_SURFACES.md shared AgentCanon surface policy.
upstream design documents/runtime-profiles-and-check-matrix.md runtime profile and validation routing policy.
upstream design documents/template-agent-canon-audit-resolution.md audit resolution ledger for profile and gate simplification.
upstream design issues/README.md durable AgentCanon operational finding storage.
downstream implementation tools/sync_agent_canon.sh updates AgentCanon submodule pins and shared root views.
downstream implementation tools/agent_tools/task_start.py emits task workflow packets.
downstream implementation tools/agent_tools/bootstrap_agent_run.py creates run bundles.
downstream implementation tools/agent_tools/task_close.py validates run-bundle closeout gates.
downstream implementation tools/agent_tools/check_agent_runtime_alignment.py validates runtime owner-map alignment.
@dependency-end
-->

# Agent Instructions

This file is the template-root runtime entrypoint for Codex. The shared agent
canon lives in `vendor/agent-canon/`; root discovery paths are runtime views into
that pin.

Path note: `documents/...` entries in AgentCanon-owned packets are logical
AgentCanon source paths. In standalone AgentCanon they resolve under `documents/`.
In template or derived repo roots they resolve under
`vendor/agent-canon/documents/` unless `documents/README.md` lists a
template-owned active contract.

## Runtime Owner Map

| Contract | Owner Surface | Evidence / Checker |
| -------- | ------------- | ------------------ |
| workflow family, spawn budget, role topology | `vendor/agent-canon/agents/task_catalog.yaml` | `task_start.py`; `bootstrap_agent_run.py`; `check_agent_runtime_alignment.py` |
| task bootstrap and CLI entrypoints | `vendor/agent-canon/agents/canonical/CLI_ENTRYPOINTS.md`; `task_start.py`; `bootstrap_agent_run.py` | generated task packet |
| subagent lifecycle, same-role instances, wave ledger | `vendor/agent-canon/agents/canonical/CODEX_SUBAGENTS.md`; `team_manifest.yaml`; `schedule.md`; `workflow_monitoring.md` | `workflow_monitor.py`; closeout lifecycle evidence |
| role behavior and stage conditions | `vendor/agent-canon/.codex/agents/*.toml`; `vendor/agent-canon/agents/agents_config.json` | `check_agent_runtime_alignment.py` |
| skill routing and public skill surface | `vendor/agent-canon/agents/skills/catalog.yaml`; `vendor/agent-canon/.agents/skills/*/SKILL.md` | `python3 tools/agent_tools/route.py --prompt`; `check_agent_runtime_alignment.py` |
| internal workflow routines | `vendor/agent-canon/agents/internal-routines/README.md` | `repo_structure_contract.py`; runtime alignment |
| implementation flow graph and source packet | run bundle design packet; `vendor/agent-canon/agents/workflows/implementation-waterfall-workflow.md`; `vendor/agent-canon/agents/COMMUNICATION_PROTOCOL.md` | design review; dependency review |
| search, read scope, and reuse survey | semantic-index, local-llm search, dependency review artifacts | `run_repo_dependency_review.sh`; bounded search artifacts |
| repo structure and root views | `vendor/agent-canon/documents/repo-structure-contract.toml`; `responsibility-scope.toml`; `documents/shared-runtime-surfaces.toml` | structure/scope/import tools; `sync_agent_canon.sh` |
| runtime profile and validation route | `vendor/agent-canon/documents/runtime-profiles-and-check-matrix.md` | profile-selected validation |
| report and closeout structure | `task_close.py`; `report_artifact_checks.py`; run bundle `closeout_gate.md` | closeout gate |
| shared AgentCanon update | `vendor/agent-canon/tools/update_agent_canon.sh`; `tools/sync_agent_canon.sh`; AgentCanon PR workflow | submodule pin and PR evidence |

This entrypoint routes the reader to owner surfaces. Stage rules, skill
selection, role behavior, validation matrices, and closeout gates are updated in
their owner surfaces first.

## Task Entry

Task bootstrap commands and CLI-specific entry behavior are owned by
`vendor/agent-canon/agents/canonical/CLI_ENTRYPOINTS.md`. Generated task packets
from `task_start.py` or `bootstrap_agent_run.py` provide the active
`workflow=...`, `skills=...`, `review=...`, source packet, wave plan, and
validation route.

## Base Runtime Packet Owner

- `README.md`
- `vendor/agent-canon/agents/README.md`
- `vendor/agent-canon/agents/TASK_WORKFLOWS.md`
- `vendor/agent-canon/agents/canonical/CODEX_WORKFLOW.md`
- `vendor/agent-canon/agents/canonical/CODEX_SUBAGENTS.md`
- `vendor/agent-canon/documents/runtime-profiles-and-check-matrix.md`
- `vendor/agent-canon/documents/SHARED_RUNTIME_SURFACES.md`

Task-specific packet expansion is owned by the generated task packet,
semantic-index/local-llm search, and dependency review artifacts.

## Template Context

- Human-facing primary language is Japanese.
- The default integration branch is `main`.
- Template-default implementation lives in `python/`.
- Template-default environment and runtime guidance lives in `docker/`.
- Repo-wide durable contracts live in `documents/`.

## Shared Canon Flow

AgentCanon source changes are made in `vendor/agent-canon/`, reviewed through
the AgentCanon branch / PR workflow, then reflected in the template through the
submodule pin and shared root views. Root view repair is owned by:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

## Closeout Evidence

Closeout cites the generated run bundle, validation outputs, dependency review,
subagent lifecycle evidence, shared-canon sync evidence, and PR / commit
evidence required by the active runtime profile. Mechanical readiness is owned by
`task_close.py` and `report_artifact_checks.py`.

## Validation Commands

- `python3 vendor/agent-canon/tools/agent_tools/check_agent_runtime_alignment.py`
- `python3 vendor/agent-canon/tools/agent_tools/repo_structure_contract.py --root vendor/agent-canon --contract vendor/agent-canon/documents/repo-structure-contract.toml`
- `python3 vendor/agent-canon/tools/agent_tools/responsibility_scope.py --root .`
- `bash tools/sync_agent_canon.sh check`
- `python3 vendor/agent-canon/tools/agent_tools/task_close.py ...`
