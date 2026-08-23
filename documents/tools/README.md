# AgentCanon Tool Guide

<!--
@dependency-start
contract reference
responsibility Routes readers to standalone AgentCanon tools without recreating Host or parent-repository execution paths.
upstream design ../runtime/bootstrap-runtime.md shared tool runtime and Host adapter boundary
upstream implementation ../../bootstrap.sh sole Host lifecycle entrypoint
upstream implementation ../../tools/catalog.yaml machine-readable tool inventory
downstream design ../../agents/canonical/CLI_ENTRYPOINTS.md typed command examples
@dependency-end
-->

## Execution boundary

AgentCanon tools run in the shared non-root tool container created by
`bootstrap.sh`. The AgentCanon source and selected project targets are mounted
read-only unless an exact mutation capability is registered. Python/Rust
caches, logs, reports, receipts, Cargo targets, and temporary files remain in
the explicit external runtime root.

Project builds, tests, GPU execution, and application dependencies remain in
the project-owned execution environment. The tool container does not execute
project commands.

## Public command routes

- `bootstrap.sh ... tool run --root <target> <catalog-id> -- <args...>` runs a
  parity-verified catalog entry.
- `bootstrap.sh ... exec --root <target> -- <argv...>` retains argv-only
  compatibility for AgentCanon tools that are still classified as
  `legacy-route`.
- `bootstrap.sh ... eval collect` and `eval sync` own evaluation collection and
  publication to `agent-canon-log`.
- `bootstrap.sh ... codex prepare|launch` owns the isolated runtime-local Codex
  home.

There is no `tools/agent-canon` alias, vendor checkout, source projection,
global Python executable, or Host Cargo fallback.

## Tool families

| Family | Canonical owner |
| --- | --- |
| typed dispatch and route selection | `tools/agent_tools/tool_dispatch.py`, `tools/catalog.yaml` |
| source/dependency analysis | `search.py`, `source_dependency_graph.py`, `lsp_code_analysis.py` |
| runtime artifact boundary | `runtime_artifacts.py`, `bootstrap_runtime.py` |
| eval and archive | `run_accumulated_agent_evals.py`, `runtime_log_archive_git.py` |
| docs and structure | Rust `agent-canon docs`, `repo_structure_contract.py`, `check_design_doc_claims.py` |
| review and closeout | `review_dispatch.py`, `task_close.py`, canonical workflow |

Each tool that writes requires an external runtime/output root or an explicit
target mutation capability. Read-only tools must not create a source-local
fallback when that capability is absent.

## Validation

Validate the selected owner rather than every tool family:

```bash
python3 tools/agent_tools/tool_catalog.py
python3 tools/agent_tools/check_convention_compliance.py
python3 tools/agent_tools/skill_tool_commands.py check
python3 tools/docs/check_bootstrap_docs.py --root .
```

Container behavior is validated with `bootstrap.sh install -> start -> target
add -> tool/eval -> stop -> uninstall` and exact resource absence readback.
Do not use `docker system prune`.
