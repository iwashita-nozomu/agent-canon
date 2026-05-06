# AgentCanon Pull Request Checklist
<!--
@dependency-start
responsibility Documents the standalone AgentCanon pull request checklist.
upstream design ../ROOT_AGENTS.md defines AgentCanon closeout requirements
upstream design ../agents/workflows/agent-canon-pr-workflow.md defines shared canon PR flow
upstream design ../documents/SHARED_RUNTIME_SURFACES.md defines synced root surfaces
downstream design PULL_REQUEST_TEMPLATE/agent_canon.md supports template-side AgentCanon PRs
@dependency-end
-->

## Summary

- AgentCanon surface changed:
- Why this belongs in AgentCanon instead of one derived repo:
- Compatibility risk:

## Scope

- [ ] Skill / workflow / subagent prompt
- [ ] Codex / Claude / Copilot runtime entrypoint
- [ ] Tooling or validation command
- [ ] Dependency manifest or graph policy
- [ ] Memory / eval / feedback loop
- [ ] GitHub Actions / PR checklist
- [ ] Documentation only

## Canon Discipline

- [ ] The source of truth was edited in AgentCanon, not only through a derived repo root view.
- [ ] New shared surfaces are listed in `documents/SHARED_RUNTIME_SURFACES.md` or explicitly documented as standalone-only.
- [ ] `.agents/skills` and `.claude/skills` mirrors are synchronized when skill prompts changed.
- [ ] Root-copy surfaces are synchronized through `bash tools/sync_agent_canon.sh link-root` when applicable.
- [ ] No derived-repo project-specific policy leaked into AgentCanon.

## Validation Evidence

- [ ] `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`
- [ ] `python3 tools/docs/mirror_skill_shims.py --target .claude/skills --prune --check`
- [ ] `python3 tools/agent_tools/check_agent_runtime_alignment.py`
- [ ] `python3 tools/agent_tools/check_convention_compliance.py`
- [ ] GitHub workflow / PR template changes: `python3 tools/ci/check_github_workflows.py`
- [ ] GitHub workflow changes: private AgentCanon submodule checkout uses `bash .github/scripts/checkout_agent_canon_submodule.sh` instead of automatic `actions/checkout` submodules.
- [ ] GitHub workflow changes: `AGENT_CANON_REPO_TOKEN` or an equivalent documented GitHub App token covers private AgentCanon reads.
- [ ] Relevant `pytest` target:
- [ ] Relevant `pyright` / `ruff` / `bash -n` target:

Validation output:

```text
paste the key pass lines here
```

## Propagation

- [ ] AgentCanon GitHub `main` will be updated first.
- [ ] Template `vendor/agent-canon` pin will be updated after AgentCanon merge.
- [ ] Template `.gitmodules` impact was reviewed when URL, branch, or checkout behavior is affected.
- [ ] Local bare mirror, if used, is compatibility-only and not the latest source of truth.
- [ ] Derived repos that need the update are listed or intentionally deferred.

## Submodule Pin Impact

- [ ] This PR requires a template `vendor/agent-canon` submodule pin update after merge.
- [ ] This PR does not require a template submodule pin update.

- AgentCanon GitHub SHA:
- expected template submodule SHA:
- submodule pin changed / unchanged rationale:

## Review Focus

- behavior change:
- backward compatibility:
- stale root surface risk:
- follow-up explicitly not included:
