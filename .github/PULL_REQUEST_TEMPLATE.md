# AgentCanon Pull Request Checklist
<!--
@dependency-start
contract reference
responsibility Documents the standalone AgentCanon pull request checklist.
upstream design ../ROOT_AGENTS.md defines AgentCanon closeout requirements
upstream design ../agents/workflows/agent-canon-pr-workflow.md defines shared canon PR flow
upstream design ../documents/SHARED_RUNTIME_SURFACES.md defines synced root surfaces
upstream design ../issues/README.md defines durable operational issue storage
upstream design ../tools/catalog.yaml defines structured tool catalog
downstream implementation ../tools/ci/check_github_workflows.py validates PR checklist and workflow conventions
downstream implementation ../tools/agent_tools/tool_drift.py validates PR/tool trace contracts
downstream implementation ../tools/agent_tools/issue_sync.py validates local/GitHub issue sync state
downstream implementation ../tools/agent_tools/check_convention_compliance.py validates PR Essence checklist wiring
downstream design PULL_REQUEST_TEMPLATE/agent_canon.md supports template-side AgentCanon PRs
@dependency-end
-->

## Reader Map

- This checklist owns the standalone AgentCanon PR body structure and closeout evidence prompts.
- Use `PR Essence`, `Summary`, and `Scope` to describe the shared-canon change; use the branch, authority, automation, canon discipline, plan, orchestration, issue, validation, propagation, submodule pin, and review-focus sections to record evidence.
- Read it when opening or reviewing a PR against the standalone AgentCanon repository.

## PR Essence

- Problem / user request:
- Design intent:
- Canonical owner:
- Behavior or contract delta:
- Evidence route:

## Summary

- AgentCanon surface changed:
- Why this belongs in AgentCanon instead of one derived repo:
- Compatibility risk:
- standalone AgentCanon repository PR / template-derived propagation:

## Scope

- [ ] Skill / workflow / subagent prompt
- [ ] Codex runtime entrypoint
- [ ] Tooling or validation command
- [ ] Dependency manifest or graph policy
- [ ] Memory / eval / feedback loop
- [ ] Operational issue / durable finding
- [ ] GitHub Actions / PR checklist
- [ ] Documentation only

## Branch And Change Route

- [ ] Tool additions or tool behavior changes are on a dedicated `canon/<topic>-YYYYMMDD` branch and standalone AgentCanon PR.
- [ ] Memory additions, agent-learning updates, skill eval results, or feedback-loop changes are on a dedicated AgentCanon branch / PR and are not hidden inside a template-only pin update.
- [ ] Template / derived repo pin update will be a separate PR after the AgentCanon source PR lands.
- [ ] No direct `sync_agent_canon.sh push` or template-only bypass was used for shared-canon source changes.

Route notes:

## PR Mutation Authority

- [ ] This PR only required inspection, branch push, PR creation, title/body update, evidence comments, or draft-state preservation.
- [ ] Merge / close / ready-for-review / reviewer request / review dismissal / auto-merge / branch deletion was explicitly authorized by the user for this task, or was not performed.
- [ ] If merge or close is still required, the blocker and required human/maintainer action are recorded below instead of being guessed from `gh` availability.
- [ ] If `pr_mutation_authority: github_pr_automation_when_green` is used, the PR has GitHub automation visible evidence and local Codex did not perform the merge.

Authority / blocker notes:

## GitHub Automation Output

- goal `pr_mutation_authority`:
- `GITHUB_PR_AUTOMATION_AUTHORITY=`:
- `GITHUB_PR_AUTOMATION_DECISION=`:
- `GITHUB_PR_AUTOMATION_CHECKS=`:
- `GITHUB_AUTOMATION_VISIBLE_EVIDENCE=`:
- `GITHUB_AUTOMATION_BLOCKER=`:
- `gh pr checks` summary:

## Canon Discipline

- [ ] This PR targets the standalone AgentCanon repository, not a template / derived repo pin PR.
- [ ] Template / derived repo follow-up, if needed, will use `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` after this source change lands.
- [ ] The source of truth was edited in AgentCanon, not only through a derived repo root view.
- [ ] New shared surfaces are listed in `documents/SHARED_RUNTIME_SURFACES.md` or explicitly documented as standalone-only.
- [ ] `agentcanon_structure_followup=required` was recorded for this AgentCanon source / synced-surface change.
- [ ] `bash tools/sync_agent_canon.sh link-root` and `bash tools/sync_agent_canon.sh check` passed from the template / derived parent root, or this source PR records the parent pin/root-view PR that must provide `agentcanon_structure_followup=pass`.
- [ ] No derived-repo project-specific policy leaked into AgentCanon.

## Plan Mode Evidence

- [ ] Plan mode was used before non-trivial AgentCanon, PR-template, GitHub Actions, or shared runtime-surface changes.
- [ ] Written plan is included in the PR body, issue, run bundle, or linked comment when the runtime did not expose an explicit Plan mode.
- [ ] Trivial-change exception is explained below when Plan mode was not used.

Plan / exception:

## Agent Orchestration Evidence

- [ ] First work update, run bundle, or linked PR comment recorded `workflow=<family>`, `skills=$agent-orchestration,...`, and `review=<...>` before implementation.
- [ ] `python3 tools/agent_tools/route.py --prompt "<user request>" --format json` was reviewed, or the no-repo-task / routing-only exception is recorded below.
- [ ] If `$agent-orchestration` was not selected first, this PR is paused until the exception is explicit and reviewed.

Orchestration evidence:

## Operational Findings / Issues

- [ ] `issues/README.md` was reviewed.
- [ ] AgentCanon maintenance issues use `.github/ISSUE_TEMPLATE/agentcanon-maintenance.yml` fields or explain why an older issue shape is sufficient.
- [ ] Skill/prompt/workflow behavior defects are evaluated against `documents/prompt-skill-evaluation-checklist.md` and `evidence/agent-evals/issue_eval_manifest.toml`, or the PR explains why no eval applies.
- [ ] Existing durable findings were searched in `issues/open/`, `issues/closed/`, `memory/`, `notes/failures/`, relevant workflow docs, and prior run-bundle evidence when available.
- [ ] New user / reviewer / runtime / CI workflow defect findings were written to `issues/open/AC-YYYYMMDD-<slug>.md`, `memory/`, or `notes/failures/` before closeout.
- [ ] Raw `rg` hits, if used to choose the fix surface, were expanded with `run_repo_dependency_review.sh --search-hits-file` and dependency-expanded edit scope is cited below.
- [ ] `python3 tools/agent_tools/issue_sync.py --repo iwashita-nozomu/agent-canon --github-check` was run; any missing GitHub mirrors are listed as `ISSUE_SYNC_PLAN=` or intentionally deferred.
- [ ] No new durable operational finding is required, and the reason is stated below.
- [ ] Agent Improvement Guide artifact from `.github/workflows/agent-improvement-guide.yml` was reviewed when available.
- [ ] Issue Mirror artifact / Step Summary from `.github/workflows/issue-mirror.yml` was reviewed when available.
- [ ] AgentCanon Static Gates from `.github/workflows/agent-canon-static-gates.yml` are passing when available.

Issue / edit-scope evidence:

## Validation Evidence

- [ ] Validation failure response, if any, cites the owner contract in `agents/canonical/CODEX_WORKFLOW.md` or `documents/runtime-profiles-and-check-matrix.md` and records same-intent repair / escalation evidence.
- [ ] `PR_CHECK_TMP="$(mktemp -d "${TMPDIR:-/tmp}/agent-canon-pr-check.XXXXXX")"` and dependency review reports were written under `$PR_CHECK_TMP`, not `reports/`
- [ ] `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing --cycle-report-only --report-dir "$PR_CHECK_TMP/dependency-review/agent-canon-pr"`
- [ ] `python3 tools/agent_tools/render_dependency_manifest_graph.py --graph-tsv "$PR_CHECK_TMP/dependency-review/agent-canon-pr/dependency_graph.tsv" --markdown-out "$PR_CHECK_TMP/dependency-review/agent-canon-pr/dependency_manifest_graph.md" --dot-out "$PR_CHECK_TMP/dependency-review/agent-canon-pr/dependency_manifest_graph.dot"`
- [ ] `python3 tools/agent_tools/check_agent_runtime_alignment.py`
- [ ] `python3 tools/agent_tools/evaluate_skill_workflow_prompts.py --manifest evidence/agent-evals/skill_workflow_prompt_eval.toml`
- [ ] `python3 tools/agent_tools/check_convention_compliance.py`
- [ ] `python3 tools/agent_tools/tool_catalog.py`
- [ ] `python3 tools/agent_tools/tool_drift.py`
- [ ] `python3 tools/agent_tools/generated_artifact_guard.py`
- [ ] `python3 tools/agent_tools/responsibility_scope.py`
- [ ] `python3 tools/agent_tools/issue_sync.py --repo iwashita-nozomu/agent-canon --github-check`
- [ ] `python3 tools/agent_tools/eval_accumulation_check.py`
- [ ] `tools/bin/agent-canon local-llm eval`
- [ ] GitHub workflow / PR template changes: `python3 tools/ci/check_github_workflows.py`
- [ ] Path/risk smoke, when relevant: `python3 tools/agent_tools/classify_path_risk.py --paths-file <changed-paths>`
- [ ] `tools/bin/agent-canon docs check`
- [ ] `bash tools/ci/run_all_checks.sh --quick`
- [ ] GitHub workflow changes: private AgentCanon submodule checkout uses `.github/scripts/checkout_agent_canon_submodule.sh` in template / derived roots, or `tools/ci/checkout_agent_canon_submodule.sh` in standalone AgentCanon source, instead of automatic `actions/checkout` submodules.
- [ ] GitHub workflow changes: `AGENT_CANON_REPO_TOKEN`, `AGENT_CANON_REPO_SSH_KEY` from a read-only deploy key, or an equivalent documented GitHub App token covers private AgentCanon reads.
- [ ] Relevant `pytest` target:
- [ ] Relevant `pyright` / `ruff` / `bash -n` target:

Validation output:

```text
paste the key pass lines here
```

## Propagation

- [ ] AgentCanon GitHub `main` will be updated first.
- [ ] Template `vendor/agent-canon` pin will be updated after AgentCanon merge.
- [ ] Template / derived repo will bring the change back with `make agent-canon-ensure-latest` and `bash tools/sync_agent_canon.sh link-root`, not by direct `sync_agent_canon.sh push`.
- [ ] Template / derived repo follow-up will record `agentcanon_structure_followup=pass` after `bash tools/sync_agent_canon.sh link-root` and `bash tools/sync_agent_canon.sh check`.
- [ ] Template `.gitmodules` impact was reviewed when URL, branch, or checkout behavior is affected.
- [ ] Local bare mirror, if used, is compatibility-only and not the latest source of truth.
- [ ] Derived repos that need the update are listed or intentionally deferred.

## Submodule Pin Impact

- [ ] This PR requires a template `vendor/agent-canon` submodule pin update after merge.
- [ ] This PR does not require a template submodule pin update.

- AgentCanon GitHub SHA:
- expected template submodule SHA:
- submodule pin changed / unchanged rationale:
- `agentcanon_structure_followup=`:

## Review Focus

- behavior change:
- backward compatibility:
- stale root surface risk:
- follow-up explicitly not included:
