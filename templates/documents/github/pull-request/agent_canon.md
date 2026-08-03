<!--
@dependency-start
contract reference
responsibility Upstream sync note:.
upstream design ../../../../agents/workflows/agent-canon-pr-workflow.md agent-canon PR workflow
upstream design ../../../../issues/README.md durable operational issue storage
upstream design ../../../../tools/catalog.yaml structured tool catalog
downstream implementation ../../../../tools/ci/check_github_workflows.py validates PR checklist and workflow conventions
downstream implementation ../../../../tools/agent_tools/tool_drift.py validates PR/tool trace contracts
downstream implementation ../../../../tools/agent_tools/issue_sync.py validates local/GitHub issue sync state
downstream implementation ../../../../tools/agent_tools/check_convention_compliance.py validates PR Essence checklist wiring
upstream design ../../README.md canonical template owner and projection boundary
upstream design ../../../../documents/operations/issue-label-taxonomy.md issue/eval routing taxonomy
upstream design ../../../../.github/AGENTS.md GitHub subtree instructions
@dependency-end
-->

<!-- canonical source は templates/documents/github/pull-request/agent_canon.md です。generated projection は .github/PULL_REQUEST_TEMPLATE/agent_canon.md を対象とするため、この source だけを編集します。 -->

## Reader Map

- この template は、template または derived repository を通じた AgentCanon change の PR checklist を所有します。
- `PR Essence`、`Summary`、`Scope` で change route を示し、branch、authority、automation、plan、orchestration、issue、validation、integration、sync、mirror、risk section に必要な evidence を記録します。
- shared canon surface の変更、または AgentCanon pin/root view の更新を行う template-side PR を作成・review するときに読みます。

## PR Essence

- Problem / user request:
- Design intent:
- Canonical owner:
- Behavior or contract delta:
- Evidence route:
- Replaceable responsibility unit:
- Public/API/schema impact:
- Explicit non-goals:

## Reader Map And Contents

この PR template は、変更の本質、canonical owner、設計から実装への trace、依存/副作用、
validation、projection、cleanup を一つの reviewer path にまとめます。読者は `PR Essence`
と `Scope` で判断対象を固定し、`Validation Trust Boundary` と `Artifact And Clone Cleanup`
で完了証拠を read back します。

- intended reader and decision:
- what this PR contains:
- canonical source / generated projection / run-local artifact:
- owner and responsibility / OOP boundary:
- required formatter, parse, projection, and post-format readback:
- lifecycle retention and cleanup owner:

## Design, Algorithm, And Oracle Trace

- design-to-implementation trace:
- algorithm/state contract before tests:
- necessary observations:
- sufficient observations:
- not proven by this oracle:
- test activation or static-only reason:
- dependency and side-effect map:
- failure-cause classification and preserved artifacts:
- conflict intent and escalation owner:

## Alternatives And Independent Review

| option | mechanism | evidence needed | cost/risk | status |
| --- | --- | --- | --- | --- |
| A | `<mechanism>` | `<evidence>` | `<risk>` | selected / rejected |
| B | `<mechanism>` | `<evidence>` | `<risk>` | selected / rejected |

- selected option and selection rule:
- rejected rationale:
- independent reviewer:
- source snapshot and review readback:

## Dependency Closure

- upstream design / contract:
- implementation owner and source path:
- downstream consumers:
- changed dependency edges and why they are closed:
- intentionally unchanged adjacent surfaces:

## Candidate Commit And Publication Identity

- `origin/main` merge-base:
- candidate commit:
- local HEAD:
- pushed branch:
- PR head:
- local = push = PR head evidence:
- submodule / generated projection identity:

## Summary

- changed shared canon surfaces:
- why shared canon needs this change:
- derived repo or template issue that exposed the need:
- AgentCanon source PR:
- template PR:

## Scope

- [ ] This PR edits `vendor/agent-canon/` as the source of truth.
- [ ] This PR does not mix repo-local implementation work with shared canon changes.
- [ ] Root symlink views were not edited directly.
- [ ] Standalone AgentCanon PR checklist was considered when the change should land in `iwashita-nozomu/agent-canon` first.
- [ ] Template / derived repo PR routing is separated from standalone AgentCanon repository PR routing.

## Branch And Change Route

- [ ] AgentCanon source change was pushed to a dedicated GitHub branch before this template / derived PR.
- [ ] Tool additions or tool behavior changes are represented by an AgentCanon source PR, not only by this template pin/root-view PR.
- [ ] Memory additions, agent-learning updates, skill eval results, or feedback-loop changes are represented by an AgentCanon source PR, not only by this template pin/root-view PR.
- [ ] This PR is a pin/root-view update after the AgentCanon source PR, or the deferred upstream-sync reason is documented below.
- [ ] This PR records `agentcanon_structure_followup=required` for AgentCanon source, pin, root-view, root-copy, or parent sync changes.

Route notes:

## PR Mutation Authority

- [ ] This PR only required inspection, branch push, PR creation, title/body update, evidence comments, draft-state preservation, or conversion to draft.
- [ ] Merge / close / ready-for-review / reviewer request / review dismissal / auto-merge / branch deletion was explicitly authorized by the user for this task, or was not performed.
- [ ] If merge, close, or ready-for-review is still required, the blocker and required human/maintainer action are recorded below instead of being guessed from `gh` availability.
- [ ] If `pr_mutation_authority: github_copilot_merge_when_green` is used, the PR has Copilot-visible evidence and local Codex did not perform the merge.

Authority / blocker notes:

## Copilot / Automation Output

- goal `pr_mutation_authority`:
- `COPILOT_PR_AUTHORITY=`:
- `COPILOT_PR_DECISION=`:
- `COPILOT_PR_CHECKS=`:
- `COPILOT_VISIBLE_EVIDENCE=`:
- `COPILOT_BLOCKER=`:
- `gh pr checks` summary:

## Plan Mode Evidence

- [ ] Plan mode was used before non-trivial AgentCanon sync, Copilot, PR-template, GitHub Actions, or shared runtime-surface changes.
- [ ] Written plan is included in the PR body, issue, run bundle, or linked comment when the runtime did not expose an explicit Plan mode.
- [ ] Trivial-change exception is explained below when Plan mode was not used.

Plan / exception:

## Agent Orchestration Evidence

- [ ] First work update, run bundle, or linked PR comment recorded `workflow=<family>`, `skills=$agent-orchestration,...`, and `review=<...>` before implementation.
- [ ] `python3 tools/agent-canon/agent_tools/route.py --prompt "<user request>" --format json` was reviewed, or the no-repo-task / routing-only exception is recorded below.
- [ ] If `$agent-orchestration` was not selected first, this PR is paused until the exception is explicit and reviewed.

Orchestration evidence:

## Review Adjudication

- reviewer roles / identities:
- review findings:
- adjudication for each finding: accepted / rejected / deferred:
- rejected rationale and governing contract:
- unresolved blocker and owner:
- final review decision: pass / revise / escalate:

## Operational Findings / Issues

- [ ] `vendor/agent-canon/issues/README.md` was reviewed.
- [ ] Existing durable findings were searched in `vendor/agent-canon/issues/open/`, `vendor/agent-canon/issues/closed/`, `vendor/agent-canon/memory/`, `vendor/agent-canon/notes/failures/`, relevant workflow docs, and prior run-bundle evidence when available.
- [ ] New user / reviewer / runtime / CI workflow defect findings were written to `vendor/agent-canon/issues/open/AC-YYYYMMDD-<slug>.md`, `vendor/agent-canon/memory/`, or `vendor/agent-canon/notes/failures/` before closeout.
- [ ] Structure intake, responsibility-scope, or dependency-review evidence used to choose the fix surface is cited below.
- [ ] `python3 tools/agent-canon/agent_tools/issue_sync.py --repo iwashita-nozomu/agent-canon --github-check` was run; any missing GitHub mirrors are listed as `ISSUE_SYNC_PLAN=` or intentionally deferred.
- [ ] No new durable operational finding is required, and the reason is stated below.
- [ ] Agent Improvement Guide artifact from `.github/workflows/agent-improvement-guide.yml` was reviewed when available.
- [ ] Issue Mirror artifact / Step Summary from `.github/workflows/issue-mirror.yml` was reviewed when available.

Issue / edit-scope evidence:

## Copilot Configuration Impact

- [ ] `vendor/agent-canon/documents/codex/github-copilot-configuration.md` was
  reviewed in template roots, or `documents/codex/github-copilot-configuration.md`
  was reviewed in standalone AgentCanon.
- [ ] Existing Copilot instruction surfaces changed / reviewed / not affected.
- [ ] Optional future `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`, or `.github/agents/*.md` surfaces were not introduced accidentally.
- [ ] GitHub Copilot MCP, `copilot-setup-steps.yml`, or Copilot environment settings changed / reviewed / not affected.
- [ ] PR template routing still separates this template / derived repo AgentCanon-pin PR from standalone AgentCanon repository PRs.

Impact notes:

## Validation

- [ ] Validation failure response, if any, cites `vendor/agent-canon/documents/runtime/runtime-profiles-and-check-matrix.json` as the canonical taxonomy owner; `vendor/agent-canon/documents/runtime/runtime-profiles-and-check-matrix.md` is the generated reader projection. PR evidence records the required evidence and same-intent repair / escalation result.
- [ ] `bash tools/agent-canon/sync_agent_canon.sh link-root`
- [ ] `bash tools/agent-canon/sync_agent_canon.sh check`
- [ ] `make agent-canon-pr-check`
- [ ] Standalone AgentCanon source: existing `static-gates` owns shared AgentCanon surfaces; no repository-wide project-quality job is added.
- [ ] Derived parent: `AGENT_CANON_PR_PROJECT_QUALITY=delegated` with owner `parent_ci`; the parent workflow exposes the canonical `make ci` command under that owner, independent of job name.
- [ ] Derived parent shared gate owns AgentCanon pin/projection/header/graph/workflow/skill-command surfaces only; development prompt and accumulated evals run only in the standalone AgentCanon static owner.
- [ ] Parent gate dependency graph receipt is `prepared` when parent graph
  migration, a touched canonical dependency surface/manifest, or the selected
  canonical validation profile requires strict completeness; otherwise it is
  `skipped` with selector reason/evidence.
- [ ] `python3 tools/agent-canon/agent_tools/check_agent_runtime_alignment.py`
- [ ] `python3 tools/agent-canon/agent_tools/check_convention_compliance.py`
- [ ] `python3 tools/agent-canon/agent_tools/tool_catalog.py`
- [ ] `python3 tools/agent-canon/agent_tools/tool_drift.py`
- [ ] `python3 tools/agent-canon/agent_tools/responsibility_scope.py`
- [ ] `python3 tools/agent-canon/agent_tools/issue_sync.py --repo iwashita-nozomu/agent-canon --github-check`
- [ ] Standalone AgentCanon only: prompt/accumulated eval evidence is supplied by the standalone static-gates owner when evaluator review is in scope.
- [ ] AgentCanon pin/update path: `bash tools/agent-canon/update_agent_canon.sh rebuild-tools` or a documented `AGENT_CANON_TOOL_REBUILD_*` skip reason.
- [ ] GitHub workflow / PR template changes: `python3 tools/agent-canon/ci/check_github_workflows.py`
- [ ] GitHub workflow changes: every `actions/checkout` job uses `submodules: false`, then runs `.github/scripts/checkout_agent_canon_submodule.sh` in template / derived roots or `tools/ci/checkout_agent_canon_submodule.sh` in standalone AgentCanon source when AgentCanon is needed.
- [ ] Private AgentCanon submodule access is covered by repository secret `AGENT_CANON_REPO_TOKEN`, `AGENT_CANON_REPO_SSH_KEY` from a read-only deploy key, or the PR explains why the workflow does not need it.
- [ ] GitHub workflow changes: `persist-credentials: false` is set unless the job has documented write intent.
- [ ] GitHub workflow changes: `permissions:` is set at workflow or job level.
- [ ] GitHub workflow changes: `concurrency:` is present or explicitly not needed.

Validation output:

```text
paste the key pass lines here
```

## Validation Trust Boundary And Format

- validation command:
- what the command proves:
- what it cannot prove:
- production behavior versus test-only evidence:
- format / lint / parse result:
- artifact path, producer, digest, and readback:
- validation failure semantics and escalation:
- Markdown/math/Mermaid command: `tools/bin/agent-canon docs check <changed-markdown-paths>`
- formatter/fixer command, if any:
- post-format source readback and projection identity:
- TOML/YAML/JSON parse evidence:

## Shared Surface Changes

- new surfaces:
- removed surfaces:
- root copy surfaces touched:
- link spec changes:
- `.gitmodules` changed / reviewed:
- generated copy/form producer:
- generated paths read back:

## Integration

- [ ] No file-structure change is included
- [ ] File-structure change is included and `agents/workflows/main-integration-workflow.md` will be used

Integration notes:

## Upstream Sync

- [ ] AgentCanon source PR was opened and merged before this template pin update, or this is a pin-only update to existing AgentCanon `main`.
- [ ] After AgentCanon merge, ran `make agent-canon-ensure-latest`.
- [ ] Compiled AgentCanon tools were rebuilt by the latest/ensure path, or `AGENT_CANON_TOOL_REBUILD_*` explains why rebuild is deferred to DevContainer.
- [ ] `agentcanon_structure_followup=required` is recorded for this parent pin/root-view PR.
- [ ] Ran `bash tools/agent-canon/sync_agent_canon.sh link-root` and `bash tools/agent-canon/sync_agent_canon.sh check` from the template / derived parent root.
- [ ] `agentcanon_structure_followup=pass` is recorded only after both parent-root sync commands passed.
- [ ] Direct `bash tools/agent-canon/sync_agent_canon.sh push` was not used, or a maintainer direct-push exception is explained below.
- [ ] Any upstream sync blocker is recorded below; deferred sync is not PR completion evidence for AgentCanon source/pin/root-view changes.

Upstream sync note:

## Artifact And Clone Cleanup

- temporary clone/worktree paths:
- run-local reports and raw logs:
- generated artifacts retained:
- cleanup command and owner:
- cleanup result / explicit preservation reason:
- generic topic-clone lifecycle/materialization manifest:
- source remote / branch / base SHA readback:
- local-only commit or untracked artifact decision:
- reconstructibility evidence before removal:
- cleanup failure cause and typed hold condition:

## Submodule Pin Change

- [ ] Template `vendor/agent-canon` pin changed.
- [ ] Template `vendor/agent-canon` pin unchanged.

Pin unchanged justification:

## GitHub Mirror / Submodule Evidence

- AgentCanon GitHub repo: `iwashita-nozomu/agent-canon`
- Template GitHub repo:
- template PR URL:
- AgentCanon PR URL or commit:
- template `vendor/agent-canon` pin:
- AgentCanon GitHub `main` SHA:
- AgentCanon GitHub SHA:
- template submodule SHA:
- template GitHub `main` SHA:
- local bare mirror SHA:
- `git submodule status vendor/agent-canon`:
- branch protection / vulnerability alert / Dependabot status:
- GitHub Actions workflow affected:
- private AgentCanon submodule secret affected:
- PR checklist affected:

## Risks

- stale route risk:
- backward drift risk:
- reviewer focus:
