<!--
@dependency-start
contract reference
responsibility Documents shortest safe onboarding path for repositories that vendor AgentCanon.
upstream design ../runtime/SHARED_RUNTIME_SURFACES.md defines root view ownership.
upstream design ../agent-canon/agent-canon-parent-repo-latest-checklist.md defines freshness and TODO handling.
upstream design ../agent-canon/agent-canon-submodule-rollback.md defines rollback.
upstream design ../codex/codex-configuration-reference.md defines MCP configuration boundaries.
downstream implementation ../../tools/agent_tools/parent_repo_readiness.py validates derived repo readiness.
@dependency-end
-->

# Derived Repository Bootstrap Runbook

Use this after cloning a repository that vendors AgentCanon under
`vendor/agent-canon/`.

## Clean Clone Checks

```bash
git submodule update --init --recursive
git submodule status vendor/agent-canon
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check
python3 tools/agent_tools/parent_repo_readiness.py --root .
```

If root views are broken:

```bash
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh link-root
PYTHONPATH=vendor/agent-canon/tools:tools python3 -m agent_tools.agent_canon_source_root exec tools/sync_agent_canon.sh check
```

## Source Of Truth

AgentCanon-owned active root surfaces are sourced from `vendor/agent-canon/`:
`AGENTS.md`, `.codex/config.toml`, and `tools/agent-canon`; optional transaction
state may live under `.agent-canon/`. `.agents/`, `agents/`, `.codex/agents/`,
`.devcontainer/`, `.vscode/`, GitHub paths, project implementation, experiments,
reports, scripts, runtime data, and `goal.md` remain parent-owned regular content.

## Failure Triage

| Symptom | First check |
| --- | --- |
| `vendor/agent-canon` missing | `git submodule update --init --recursive` |
| root symlink/copy drift | source-root resolver `check` |
| stale AgentCanon pin | request-evidence-authorized `make agent-canon-ensure-latest` |
| MCP unavailable | `documents/code../codex/codex-configuration-reference.md` |
| GitHub auth or workflow failure | `python3 tools/ci/check_github_workflows.py` |
| need rollback | `documents/agent-cano../agent-canon/agent-canon-submodule-rollback.md` |

Do not fix a generic shared-canon defect only in the derived repo. Open an
AgentCanon branch/PR, merge it, then update the derived repo pin.
