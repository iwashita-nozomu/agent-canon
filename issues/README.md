# AgentCanon Operational Issues

<!--
@dependency-start
contract issue
responsibility Defines durable AgentCanon operational finding storage and issue-file conventions.
upstream design ../ROOT_AGENTS.md requires durable learning and closeout evidence
upstream design ../agents/workflows/agent-canon-pr-workflow.md requires issue checks in AgentCanon PR flow
upstream design ../documents/dependency-manifest-design.md defines dependency graph and search-to-edit-scope evidence
downstream design closed/AC-20260513-durable-finding-auto-promotion.md records the initial workflow defect
downstream design closed/README.md defines closed finding storage
downstream implementation ../tools/ci/check_github_workflows.py validates issue conventions
downstream implementation ../tools/agent_tools/issue_sync.py validates local issues and plans GitHub Issue sync
@dependency-end
-->

This directory stores durable AgentCanon operational findings.
It is the local durable source of truth; GitHub Issues are an optional visible
mirror created or updated by explicit sync tooling.
It is not a run-bundle scratchpad.
Use it when a user, reviewer, runtime check, CI failure, or agent retrospective exposes a workflow defect that should survive beyond the current run.

## Reader Map

- This README owns the durable local issue-file convention for AgentCanon operational findings.
- `Directory Contract`, `File Naming`, and `Required Fields` define where issue files live and what metadata they carry; the search, PR gate, and GitHub sync sections describe the workflow around them.
- Read it before opening, updating, closing, or mirroring an AgentCanon operational issue.

## Directory Contract

- `issues/open/`: active operational findings that still need workflow, tool, documentation, or policy changes.
- `issues/closed/`: findings that have an implemented and validated fix. Moving a file here requires updating `status`, `resolved_by`, and `close_condition`.
- Run-local details stay in `reports/agents/<run-id>/`. This directory keeps only the durable summary, evidence pointers, affected surfaces, and required action.

## File Naming

Use one file per finding:

```text
issues/open/AC-YYYYMMDD-short-slug.md
```

- `AC` is the AgentCanon operational issue prefix.
- `YYYYMMDD` is the date the finding was created.
- `short-slug` is lowercase ASCII with hyphens.
- Do not reuse IDs. If a later finding is related, link to the older issue instead of appending unrelated scope.
- Closed files keep the same file name under `issues/closed/`.

## Required Fields

Every issue file must contain these machine-readable lines near the top:

```text
issue_id: AC-YYYYMMDD-short-slug
status: open|in_progress|resolved|deferred|wontfix
source: user|reviewer|runtime|ci|retrospective
severity: S0|S1|S2|S3
evidence: <repo-relative path or external PR/issue URL>
affected_surfaces: <comma-separated repo-relative paths>
edit_scope: <dependency-expanded paths or report artifact path>
required_action: <one sentence>
close_condition: <one sentence>
```

Issue text must summarize the behavior and cite evidence.
Do not paste raw chat logs or long run-bundle transcripts.
When an issue is mirrored to GitHub, add this optional field:

```text
github_issue: https://github.com/<owner>/<repo>/issues/<number>
```

Use `github_issue: pending` only while a branch is preparing the GitHub mirror.
Closed issue files must additionally include:

```text
resolved_by: <commit SHA, PR URL, or report path>
```

## Search And Edit-Scope Rule

Before opening, updating, or closing an issue, search durable surfaces first:

```bash
rg -n "topic keywords" vendor/agent-canon/issues vendor/agent-canon/memory vendor/agent-canon/notes/failures vendor/agent-canon/documents vendor/agent-canon/agents
```

When raw text search identifies candidate files, save the hits and expand them through dependency headers:

```bash
rg -l "topic keywords" > reports/search_hits.txt
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review \
  --search-hits-file reports/search_hits.txt
```

Record the relevant `DEPENDENCY_EDIT_SCOPE_PATH` lines or the generated `dependency_edit_scope.txt` path in the issue's `edit_scope` field.
An issue is too coarse if it describes a defect but does not name the files that likely need edits or verification.

## PR Gate

AgentCanon PRs that change workflow, tooling, memory, evaluation, search behavior, PR templates, or closeout policy must either:

- link the issue file that drove the change, or
- state that durable issue search found no existing finding and no new durable operational finding is required.

If a run bundle exposes a workflow defect, the defect is not considered captured until this directory, `memory/`, or `notes/failures/` contains the durable record.
Do not delete closed findings during ordinary cleanup; archive or compact only during an explicit issue-retention pass.

## GitHub Issue Sync

Local issue files remain canonical because they carry dependency headers,
dependency-expanded edit scope, and reviewable history. GitHub Issues are the
operator-facing mirror for triage and branch/PR routing.

Offline validation:

```bash
python3 tools/agent_tools/issue_sync.py --root .
```

Plan missing GitHub mirrors:

```bash
python3 tools/agent_tools/issue_sync.py --root . --repo iwashita-nozomu/agent-canon
```

PR read-only mirror check:

```bash
python3 tools/agent_tools/issue_sync.py \
  --root . \
  --repo iwashita-nozomu/agent-canon \
  --github-check
```

`.github/workflows/issue-mirror.yml` runs the read-only check on PRs and branch
pushes and writes the mirror status, drift, and planned sync commands to the
GitHub Step Summary. Missing `github_issue:` links generate deterministic
`ISSUE_SYNC_PLAN=` lines; they do not fail PRs unless the local issue schema,
status, duplicate IDs, or linked GitHub mirror state is inconsistent.

Apply mode may create GitHub Issues and insert `github_issue:` fields, but it
must be an explicit operator action. GitHub Actions sync mode updates already
linked GitHub Issues on `main` pushes or manual dispatch; it does not commit
new `github_issue:` fields back to the repository.

```bash
python3 tools/agent_tools/issue_sync.py \
  --root . \
  --repo iwashita-nozomu/agent-canon \
  --apply
```

```bash
python3 tools/agent_tools/issue_sync.py \
  --root . \
  --repo iwashita-nozomu/agent-canon \
  --github-check \
  --sync-github
```
