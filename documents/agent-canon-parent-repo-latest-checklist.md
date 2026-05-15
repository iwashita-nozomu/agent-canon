# AgentCanon Parent Repository Latest-State Checklist
<!--
@dependency-start
responsibility Documents latest-state checklist for parent repositories that vendor AgentCanon.
upstream design ./agent-canon-subtree-migration.md submodule and legacy subtree update policy
downstream design ./agent-canon-update-tasks.toml shared parent-repo update TODO manifest
downstream implementation ../tools/agent_tools/agent_canon_preflight.py emits checklist evidence at task start
downstream implementation ../tools/agent_tools/agent_canon_update_todos.py manages parent update TODO state
downstream implementation ../tools/agent_tools/bootstrap_agent_run.py prints checklist evidence
downstream implementation ../tools/agent_tools/task_start.py prints checklist evidence
@dependency-end
-->

この checklist は、AgentCanon を `vendor/agent-canon/` Git submodule として持つ親 repo で agent task を始める前に確認する最新状態 checklist です。
この template と新規 migration 済み repo の通常系は submodule です。
legacy subtree / committed snapshot repo は末尾の互換 appendix だけを使い、通常の親 repo 構造として扱いません。
agent entrypoint は `tools/agent_tools/agent_canon_preflight.py` 経由でこの checklist の存在と freshness preflight を出力します。

## Expected Parent Repo Structure

親 repo は次の構造を持ちます。

| Path | Expected State | Owner | Check |
| --- | --- | --- | --- |
| `vendor/agent-canon/` | AgentCanon Git submodule checkout and parent gitlink | AgentCanon | `git submodule status vendor/agent-canon` and `git rev-parse HEAD:vendor/agent-canon` |
| `AGENTS.md`, `CLAUDE.md`, `agents/`, `.agents/`, `.claude/`, `.codex/`, `mcp/`, `tools/` | root runtime view of AgentCanon | AgentCanon | `bash tools/sync_agent_canon.sh check` |
| `.github/AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/`, `.github/agents/` | GitHub agent root views | AgentCanon | `bash tools/sync_agent_canon.sh check` |
| `.github/workflows/agent-coordination.yml`, `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`, `.github/scripts/checkout_agent_canon_submodule.sh` | regular root copies forced by GitHub path constraints | AgentCanon source, root copy | `bash tools/sync_agent_canon.sh check` |
| `documents/SHARED_RUNTIME_SURFACES.md`, `documents/shared-runtime-surfaces.toml` | shared surface policy and machine manifest | AgentCanon | `python3 tools/agent_tools/check_convention_compliance.py` |
| `.agent-canon/update-state.toml` | parent-local AgentCanon update TODO boundary | parent repo | `python3 tools/agent_tools/agent_canon_update_todos.py status` |
| `documents/README.md`, template bootstrap / host / server contract docs | parent repo active contracts | template or derived repo | regular file, not root symlink |
| `goal.md`, project notes, experiments, reports | repo-local durable state and generated evidence | parent repo | must not be restored from AgentCanon |

## Latest-State Checklist

Run this sequence before editing shared AgentCanon surfaces or starting a repo-changing task.

1. Confirm MCP inventory when the runtime supports it.

```bash
python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server
```

1. Check the parent worktree and classify dirty state.

```bash
git status --short --branch --untracked-files=all
git -C vendor/agent-canon status --short --branch --untracked-files=all 2>/dev/null || true
```

1. If `vendor/agent-canon/` is a submodule, unrelated parent dirty state does not block an AgentCanon update. The update may proceed when the AgentCanon update surface is clean:

- `vendor/agent-canon/` submodule worktree is clean.
- parent gitlink at `vendor/agent-canon` is not already an unresolved local pin change.
- `.gitmodules` is clean.
- AgentCanon-owned symlink and GitHub copy root views are clean.

Template-owned active contracts such as `documents/README.md`, bootstrap docs, host/server contracts, project notes, experiments, and reports do not block the submodule update just because they are dirty.

1. If the AgentCanon update surface is clean, update AgentCanon before planning or implementation.

```bash
make agent-canon-ensure-latest
```

1. If only unrelated parent paths are dirty, keep those changes intact and still run the latest update. Record that the dirty paths were outside the AgentCanon update surface.

1. If the dirty state is inside AgentCanon source, `.gitmodules`, the parent gitlink, or an AgentCanon-owned root view that `link-root` may overwrite, route the change through a normal AgentCanon GitHub branch and PR first.

```bash
bash tools/update_agent_canon.sh merge-main-into-current
git -C vendor/agent-canon push origin HEAD
```

1. After AgentCanon update or PR merge, restore root views from the manifest and verify drift.

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

1. Generate and apply AgentCanon update TODOs before unrelated repo work.

```bash
python3 tools/agent_tools/agent_canon_update_todos.py status
python3 tools/agent_tools/agent_canon_update_todos.py plan --write
```

`AGENT_CANON_UPDATE_TODO_STATUS=pending` is not a stop-only gate. It means the
parent repo agent must make those TODOs the first work for the current run.
After each TODO is applied, record it:

```bash
python3 tools/agent_tools/agent_canon_update_todos.py complete <task-id> \
  --note "what changed"
```

If the TODO requires a human or repo-owner decision, do not delete it silently.
Record an explicit deferral with owner and reason:

```bash
python3 tools/agent_tools/agent_canon_update_todos.py defer <task-id> \
  --owner "<owner>" \
  --reason "<why this repo cannot apply it now>"
```

When no open TODO remains, advance the parent-local boundary:

```bash
python3 tools/agent_tools/agent_canon_update_todos.py acknowledge
```

1. Record closeout evidence for parent repo runs.

```bash
git submodule status vendor/agent-canon 2>/dev/null || git rev-parse HEAD:vendor/agent-canon
python3 tools/agent_tools/check_convention_compliance.py
```

## Parent Repo Update TODO State

AgentCanon may introduce tasks that every parent repo should consider after
updating `vendor/agent-canon/`. Examples are container policy changes,
task-start protocol changes, new required state files, or workflow evidence
format changes. The shared task list is AgentCanon-owned:

- `vendor/agent-canon/documents/agent-canon-update-tasks.toml`

The per-repo progress is parent-owned:

- `.agent-canon/update-state.toml`

Generated views are intentionally not parent state:

- `.agent-canon/update-todos.generated.md`
- `.agent-canon/update-todos.pending.json`

Initialize a parent repo once after the tool is available:

```bash
python3 tools/agent_tools/agent_canon_update_todos.py init
git add .agent-canon/.gitignore .agent-canon/update-state.toml
```

The generated `.agent-canon/.gitignore` keeps generated TODO views out of git
while allowing only the durable state file to be tracked. This lets different
parent repos advance at different speeds without editing AgentCanon's shared
manifest.

Task manifest entries use `introduced_after`, not a self-referential commit
field. A Git commit cannot contain its own SHA. Add a task in the first commit
after the boundary where the new parent action becomes required, and set
`introduced_after` to the last AgentCanon commit that did not require it.

Task-start behavior:

- `tasks_applied_through` older than the current submodule pin plus pending
  manifest tasks yields `AGENT_CANON_UPDATE_TODO_NEXT=apply_agent_canon_update_todos`.
- Pending output must include both the human markdown view and the machine JSON
  view:
  - `.agent-canon/update-todos.generated.md`
  - `.agent-canon/update-todos.pending.json`
- The JSON view includes `pending_task_details[]` with each task's severity,
  actions, acceptance criteria, and expected paths. Parent agents should use
  those details as the first TODO list for the current run rather than treating
  `AGENT_CANON_UPDATE_TODO_TASKS` as opaque IDs.
- The agent should apply those tasks first, then continue the user's requested
  work in the same repo run when safe.
- For each pending TODO, record exactly one of:
  - `python3 tools/agent_tools/agent_canon_update_todos.py complete <task-id> --note "<evidence>"`
  - `python3 tools/agent_tools/agent_canon_update_todos.py not-applicable <task-id> --reason "<evidence>" --owner "<owner>"`
  - `python3 tools/agent_tools/agent_canon_update_todos.py defer <task-id> --reason "<blocker>" --owner "<owner>"`
- This is deliberately not a pre-tool stop hook. Hooks may log evidence, but the
  task-start/preflight protocol owns routing and repair.

## GitHub Changelog TODO: 2026-05-05 Through 2026-05-13

This section tracks operational TODOs from the last 10 days of GitHub
Changelog entries as of 2026-05-14. Use it when reviewing any repo that vendors
AgentCanon. Keep each unchecked item open until the repo owner can mark it
`done`, `not_applicable`, or `deferred` in the run bundle, issue, or PR body.

Source window:

- [GitHub Changelog May 2026 index](https://github.blog/changelog/page/24/)
- [Start Copilot cloud agent tasks via the REST API](https://github.blog/changelog/2026-05-13-start-copilot-cloud-agent-tasks-via-the-rest-api/)
- [More flexible secrets and variables for Copilot cloud agent](https://github.blog/changelog/2026-05-08-more-flexible-secrets-and-variables-for-copilot-cloud-agent/)
- [Copilot code review: Comment experience improvements](https://github.blog/changelog/2026-05-12-copilot-code-review-comment-experience-improvements/)
- [Copilot code review comment types now in usage metrics API](https://github.blog/changelog/2026-05-08-copilot-code-review-comment-types-now-in-usage-metrics-api/)
- [April reports are now available to prepare for usage-based billing](https://github.blog/changelog/2026-05-12-april-reports-are-now-available-to-prepare-for-usage-based-billing/)
- [Upcoming deprecation of Grok Code Fast 1](https://github.blog/changelog/2026-05-08-upcoming-deprecation-of-grok-code-fast-1/)
- [Upcoming deprecation of GPT-4.1](https://github.blog/changelog/2026-05-07-upcoming-deprecation-of-gpt-4-1/)
- [Claude Sonnet 4 deprecated](https://github.blog/changelog/2026-05-07-claude-sonnet-4-deprecated/)
- [Secret scanning with GitHub MCP Server is now generally available](https://github.blog/changelog/2026-05-05-secret-scanning-with-github-mcp-server-is-now-generally-available/)
- [Dependency scanning with GitHub MCP Server is in public preview](https://github.blog/changelog/2026-05-05-dependency-scanning-with-github-mcp-server-is-in-public-preview/)
- [Synchronous SBOM API deprecated](https://github.blog/changelog/2026-05-12-synchronous-sbom-api-deprecated/)
- [Deprecation notice: `code_scanning_upload` field will be removed from `rate_limit` API endpoint](https://github.blog/changelog/2026-05-05-deprecation-notice-code_scanning_upload-field-will-be-removed-from-rate_limit-api-endpoint/)
- [Cross-org Dependabot access for internal repositories](https://github.blog/changelog/2026-05-11-cross-org-dependabot-access-for-internal-repositories/)
- [Repository rulesets: User bypass and branch renaming](https://github.blog/changelog/2026-05-07-repository-rulesets-user-bypass-and-branch-renaming/)
- [Enterprise-managed plugins in GitHub Copilot CLI are now in public preview](https://github.blog/changelog/2026-05-06-enterprise-managed-plugins-in-github-copilot-cli-are-now-in-public-preview/)
- [GitHub Copilot in Visual Studio Code, April releases](https://github.blog/changelog/2026-05-06-github-copilot-in-visual-studio-code-april-releases/)
- [New enterprise installation API now in public preview](https://github.blog/changelog/2026-05-13-new-enterprise-installation-api-now-in-public-preview/)
- [CodeQL 2.25.4 adds Swift 6.3.1 support, improvements to C# and Java, and more](https://github.blog/changelog/2026-05-12-codeql-2-25-4-adds-swift-6-3-1-support-improvements-to-c-and-java-and-more/)
- [CodeQL 2.25.3 adds Swift 6.3 support](https://github.blog/changelog/2026-05-08-codeql-2-25-3-adds-swift-6-3-support/)

### P0: Date-Bound Breakage Checks

- [ ] Model deprecations: search `.github/`, `.codex/`, `.agents/`,
  `.claude/`, `agents/`, `documents/`, `scripts/`, and CI config for
  `Grok Code Fast 1`, `GPT-4.1`, and `Claude Sonnet 4`.
  - `Claude Sonnet 4` was deprecated on 2026-05-06.
  - `Grok Code Fast 1` is deprecated on 2026-05-15.
  - `GPT-4.1` is deprecated on 2026-06-01.
  - Replace explicit model references with approved alternatives or record
    `not_applicable` with search evidence.
- [ ] REST API compatibility: search tools, scripts, workflows, and docs for
  `code_scanning_upload` and `/rate_limit`. Remove assumptions that
  `resources.code_scanning_upload` exists before 2026-05-19.
- [ ] SBOM API compatibility: search for `/dependency-graph/sbom`. If present,
  migrate the integration to `/{owner}/{repo}/dependency-graph/sbom/generate-report`,
  poll the returned URL, and record the async workflow evidence. The synchronous
  API is deprecated and scheduled for removal on 2026-11-13.

### P1: Copilot Cloud Agent And Review Operations

- [ ] Copilot cloud agent task automation: if the repo or organization starts
  Copilot cloud agent tasks from scripts, portals, or scheduled workflows,
  evaluate the Agent tasks REST API and document token type, permission owner,
  PR mutation authority, and audit trail. Until GitHub App installation token
  support is available, do not silently convert this into an app-token flow.
- [ ] Copilot cloud agent secrets and variables: move shared cloud-agent
  configuration out of ad hoc repository `copilot` environments when org-level
  `Agents` secrets/variables are available. Keep secret-bearing values out of
  the repo. Record which variables are org-level, repo-level, or intentionally
  absent.
- [ ] Copilot code review severity handling: map GitHub Copilot's `High`,
  `Medium`, and `Low` review labels to the repo's S0/S1/S2/S3 finding triage.
  High-severity Copilot findings should be fix-now unless explicitly downgraded
  with evidence.
- [ ] Copilot code review metrics: for orgs or enterprises with usage metrics
  access, add `copilot_suggestions_by_comment_type` to periodic PR/review
  reporting. Track at least `security`, `bug_risk`, applied suggestion counts,
  and any category that repeatedly produces ignored suggestions.
- [ ] Copilot usage-based billing preparation: download April and later Copilot
  usage reports where the repo owner has access. Identify heavy consumers,
  agentic workflow surfaces, and review automation that may need budget caps or
  scheduling changes before 2026-06-01.

### P1: MCP, Security, And Dependency Scanning

- [ ] GitHub MCP Server secret scanning: if the repo has GitHub Secret Protection
  enabled, decide whether Copilot CLI / VS Code / other AI agents should run the
  GitHub MCP Server secret scanning tool before commit or PR. Do not confuse this
  external GitHub MCP Server with the local AgentCanon `repo_mcp_server`.
- [ ] GitHub MCP Server dependency scanning: if Dependabot alerts are enabled,
  decide whether to enable the GitHub MCP Server `dependabot` toolset for
  pre-commit dependency vulnerability scans. Record whether the Advanced
  Security plugin is installed and whether Dependabot CLI diff evidence is used.
- [ ] Cross-org Dependabot access: for enterprise repos with internal
  dependencies hosted in other organizations, ask enterprise admins whether
  cross-org internal repository access should be enabled for Dependabot. Record
  the policy outcome in dependency review evidence.
- [ ] CodeQL updates: review fresh code scanning alerts after CodeQL 2.25.3 and
  2.25.4 roll out. Pay special attention to GitHub Actions artifact-poisoning
  query changes, Swift 6.3 / 6.3.1 projects, C/C++ query promotions, Vercel
  serverless TypeScript routes, and Python 3.15 lazy import syntax.

### P2: Governance, CLI, And Enterprise Integration

- [ ] Repository rulesets: audit whether individual user bypass actors are used
  for agents, service accounts, or maintainers. Prefer minimal bypass scope and
  record the reason in PR mutation authority docs. If renaming protected
  branches, confirm the new name remains inside every applicable ruleset.
- [ ] Enterprise-managed Copilot CLI plugins: if the enterprise uses Copilot
  Business or Enterprise, decide whether AgentCanon skills, hooks, MCP config,
  or plugin marketplaces should be distributed through
  `.github-private/.github/copilot/settings.json`. Keep repo-local plugin
  experiments out of enterprise baseline settings until validated.
- [ ] VS Code Copilot agent controls: review whether domain allowlists, terminal
  read/write permissions, agent debug log retention, and GitHub.com/mobile
  steering of Copilot CLI sessions need a repo or org policy update.
- [ ] GitHub App enterprise installation API: if repo tools enumerate GitHub App
  installations for an enterprise, replace broad pagination with the enterprise
  installation API and record fallback behavior for organizations, repositories,
  and users.

### P3: Watch Or Mark Not Applicable

- [ ] GitHub Enterprise Server release candidates: if the repo targets GHES,
  check whether GHES 3.21 RC / 3.22 timing affects Dependabot, CodeQL, Copilot,
  or ruleset features used by the repo.
- [ ] Repository security advisories: if the repo uses GitHub repository security
  advisories heavily, verify whether the new search/filter bar changes triage
  workflow documentation.
- [ ] User-level commit comments: if agents or maintainers rely on commit
  comments as review evidence, verify whether user-level disabled commit
  comments can hide required evidence and move that evidence to PR reviews or
  run artifacts.
- [ ] GitHub Mobile repository creation: usually not repo-actionable. Mark
  `not_applicable` unless mobile-created repos need template bootstrap or
  AgentCanon onboarding guardrails.

## Agent Task-Start Rule

When an agent starts through `task_start.py` or `bootstrap_agent_run.py`, the output must include:

- `AGENT_CANON_PREFLIGHT_COMMAND`
- `AGENT_CANON_PREFLIGHT_STATUS`
- `AGENT_CANON_PREFLIGHT_REASON`
- `AGENT_CANON_PREFLIGHT_NEXT`
- `AGENT_CANON_PREFLIGHT_CHECKLIST`
- `AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS`
- `AGENT_CANON_UPDATE_TODO_STATUS`
- `AGENT_CANON_UPDATE_TODO_NEXT`
- `AGENT_CANON_UPDATE_TODO_PENDING_COUNT`
- `AGENT_CANON_UPDATE_TODO_RESOLVED_UNACKED_COUNT`
- `AGENT_CANON_UPDATE_TODO_TASKS`
- `AGENT_CANON_UPDATE_TODO_RESOLVED_TASKS`
- `AGENT_CANON_UPDATE_TODO_STATE`
- `AGENT_CANON_UPDATE_TODO_MANIFEST`
- `AGENT_CANON_UPDATE_TODO_GENERATED`
- `AGENT_CANON_UPDATE_TODO_PENDING_JSON`
- `AGENT_CANON_UPDATE_TODO_FIRST_TASK`
- `AGENT_CANON_UPDATE_TODO_FIRST_SEVERITY`
- `AGENT_CANON_UPDATE_TODO_FIRST_ACTION`
- `AGENT_CANON_UPDATE_TODO_FIRST_PATHS`

`AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS=present` means this checklist was found in the parent repo's vendored AgentCanon surface.
`missing` means the parent repo is stale or malformed; the agent must repair AgentCanon checkout/sync before treating repo-changing work as started.

## Failure Routes

- unrelated parent dirty state: allowed for submodule updates when the AgentCanon update surface is clean.
- stale parent gitlink: not latest, even when `vendor/agent-canon` worktree HEAD already equals AgentCanon remote main; commit the parent gitlink pin before treating the parent repo as latest.
- local-ahead parent gitlink: AgentCanon branch / PR required; do not treat `local_contains_remote` as latest.
- `blocked_shared_canon_workflow`: do not hide shared-canon edits in a parent-only diff; commit the AgentCanon branch, merge main into it, and open an AgentCanon PR.
- `skipped_source_canon`: running inside standalone AgentCanon; update parent repos after AgentCanon changes are committed.
- `missing checklist`: restore or update `vendor/agent-canon/`, then rerun `bash tools/sync_agent_canon.sh link-root`.

## Legacy Compatibility Appendix

Legacy subtree or committed snapshot repos should migrate to the submodule structure above.
Until migration, use `bash tools/update_agent_canon.sh plan` only to classify compatibility routes such as `already_current_tree`, `already_current_split`, `snapshot_import_*`, or `subtree_pull`.
Do not copy legacy route language into this template's normal task-start rules.
