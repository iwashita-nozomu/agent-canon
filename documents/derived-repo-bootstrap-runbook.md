<!--
@dependency-start
contract reference
responsibility Documents shortest safe onboarding path for repositories that vendor AgentCanon.
upstream design ./SHARED_RUNTIME_SURFACES.md defines root view ownership.
upstream design ./agent-canon-parent-repo-latest-checklist.md defines freshness and TODO handling.
upstream design ./agent-canon-submodule-rollback.md defines rollback.
upstream design ./codex-configuration-reference.md defines MCP configuration boundaries.
downstream implementation ../tools/agent_tools/parent_repo_readiness.py validates derived repo readiness.
@dependency-end
-->

# Derived Repository Bootstrap Runbook

Use this after cloning a repository that vendors AgentCanon under
`vendor/agent-canon/`.

## Clean Clone Checks

```bash
git submodule update --init --recursive
git submodule status vendor/agent-canon
bash tools/sync_agent_canon.sh check
python3 tools/agent_tools/parent_repo_readiness.py --root .
```

If root views are broken:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

## Source Of Truth

AgentCanon-owned shared surfaces are sourced from `vendor/agent-canon/`:
`AGENTS.md`, `.agents/`, `.codex/`, `agents/`, `tools/`,
and shared policy docs. Project implementation, experiments, reports, scripts,
runtime data, and `goal.md` remain repo-local.

## Failure Triage

| Symptom | First check |
| --- | --- |
| `vendor/agent-canon` missing | `git submodule update --init --recursive` |
| root symlink/copy drift | `bash tools/sync_agent_canon.sh check` |
| stale AgentCanon pin | `make agent-canon-ensure-latest` |
| MCP unavailable | `documents/codex-configuration-reference.md` |
| GitHub auth or workflow failure | `python3 tools/ci/check_github_workflows.py` |
| need rollback | `documents/agent-canon-submodule-rollback.md` |

Do not fix a generic shared-canon defect only in the derived repo. Open an
AgentCanon branch/PR, merge it, then update the derived repo pin.
