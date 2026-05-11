<!--
@dependency-start
responsibility Documents documents/ for this repository.
upstream design ./SHARED_RUNTIME_SURFACES.md documents ownership policy
upstream design ./shared-runtime-surfaces.toml machine-readable ownership manifest
downstream design ./algorithm-implementation-boundary.md algorithm math-to-code boundary policy
downstream design ./codex-configuration-reference.md Codex configuration reference
downstream design ./object-oriented-design.md general OOP coding policy
downstream design ./agent-canon-parent-repo-latest-checklist.md parent repo latest-state checklist
@dependency-end
-->

# documents/

`documents/` is a mixed documentation directory. The root `documents/README.md`
is repo-local and should stay a regular file after template clone. AgentCanon may
seed this file, but derived repositories own their local index.

## Ownership Matrix

| Class | Examples | Edit source |
| --- | --- | --- |
| AgentCanon-owned shared policy symlink | coding conventions, review process, workflow-supporting policies, shared templates, tool docs | `vendor/agent-canon/documents/` |
| Template-owned active contract | bootstrap, host requirements, server contract, remote execution contract, template remote policy | root `documents/` regular files |
| Project-owned docs | architecture notes, project-specific design specs, implementation contracts | root `documents/` regular files |
| Generated or run artifacts | agent reports, experiment outputs, logs | `reports/` or `experiments/`, not `documents/` |

If a file is an AgentCanon-owned symlink, edit the source under
`vendor/agent-canon/` and repair the root view with
`bash tools/sync_agent_canon.sh link-root`. If a file is a template-owned active
contract, edit the root regular file.

## Canon Runtime References

- [Shared Runtime Surfaces](./SHARED_RUNTIME_SURFACES.md): owner classes,
  symlink/copy/regular behavior, and root-view repair rules.
- [Shared Runtime Surface Manifest](./shared-runtime-surfaces.toml):
  machine-readable surface ownership list.
- [AgentCanon Parent Repository Latest-State Checklist](./agent-canon-parent-repo-latest-checklist.md):
  task-start checklist for repos that vendor AgentCanon.
- [Codex Configuration Reference](./codex-configuration-reference.md): Codex CLI
  / config schema / hooks / MCP / skills / subagents reference.
- [AgentCanon GitHub Remote](./agent-canon-github-remote.md): GitHub canonical
  remote and local bare mirror compatibility.
- [GitHub Copilot Configuration](./github-copilot-configuration.md): Copilot
  repository instructions, path-specific instructions, custom agents, MCP, setup
  workflow, and PR template routing.

## Coding Policy References

- [Algorithm Implementation Boundary Policy](./algorithm-implementation-boundary.md):
  math/specification boundary, implementation boundary, change classes, and
  review gates.
- [Object-Oriented Design Policy](./object-oriented-design.md): class,
  dataclass, Protocol, composition, and inheritance policy.
- [Python Coding Conventions](./coding-conventions-python.md): Python-specific
  implementation rules.
- [Project Coding Conventions](./coding-conventions-project.md): project-wide
  environment, dependency, and runtime rules.

## Template-Owned Active Contracts

These files should be regular files in the template or derived repo root:

- [Template Bootstrap](./template-bootstrap.md)
- [Template GitHub Remote](./template-github-remote.md)
- [Linux / WSL Host Requirements](./linux-wsl-host-requirements.md)
- [Server Host Contract](./server-host-contract.md)
- [Remote Execution Repo Contract](./remote-execution-repo-contract.md)

AgentCanon provides reusable contract templates under [templates/](./templates/),
but the active contract for a derived repo belongs to that repo.

## Tooling And Artifact References

- [Result Log Retention And Visualization](./result-log-retention-and-visualization.md):
  run result, summary, visualization artifact, and retention rules.
- [Repo-Local Tool Imports](./repo-local-tool-imports.md): disposition ledger for
  tools that grow in derived repos before AgentCanon promotion.
