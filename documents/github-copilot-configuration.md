<!--
@dependency-start
contract reference
responsibility Documents GitHub Copilot and PR automation configuration boundaries.
upstream design ../ROOT_AGENTS.md defines PR mutation authority and Copilot-visible evidence rules.
upstream implementation ../.github/PULL_REQUEST_TEMPLATE/agent_canon.md records template / derived repo AgentCanon-pin PR evidence fields.
downstream implementation ../tools/ci/check_github_workflows.py validates GitHub workflow and PR-template conventions.
@dependency-end
-->

# GitHub Copilot Configuration

This document records the AgentCanon boundary for GitHub Copilot and other
GitHub-side PR automation. It is a routing and evidence document, not a secret
or MCP configuration surface.

## Authority Boundary

Local Codex agents may inspect PR state, push owned branches, create or update
PRs, and add visible evidence comments when the active workflow requires it.
They must not merge, close, mark ready for review, request reviewers, dismiss
reviews, delete branches, enable auto-merge, or bypass checks unless the user
explicitly authorizes that mutation in the current task or a tracked maintainer
policy grants that exact action.

`github_copilot_merge_when_green` is reserved for GitHub-hosted Copilot or
other GitHub-side automation after required checks and reviews are green. It
does not grant local Codex permission to merge from `gh`.

## Visible Evidence Contract

Copilot or PR automation decisions must be visible in the PR through the
following fields before readiness or merge automation acts:

```text
COPILOT_PR_AUTHORITY=<inspect_and_prepare_only|ready_for_review_when_green|merge_when_green|github_copilot_merge_when_green>
COPILOT_PR_DECISION=<inspect_only|ready_for_review|merge|blocked|needs_human>
COPILOT_PR_CHECKS=<pass|fail|missing|not_run>
COPILOT_VISIBLE_EVIDENCE=<pr-comment|review|pr-body|check-run>:<url-or-id>
COPILOT_BLOCKER=<none|short blocker>
```

## Configured Surfaces

AgentCanon currently treats these as the canonical checked-in surfaces for
Copilot / PR automation policy:

- `ROOT_AGENTS.md`: repository-wide PR mutation authority rules.
- `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`: template / derived repo
  AgentCanon-pin PR checklist and evidence fields.
- `tools/ci/check_github_workflows.py`: GitHub workflow and PR-template
  convention checker.

Repository-specific Copilot MCP server settings, Copilot environment variables,
secrets, and setup workflows are not shared by AgentCanon unless a future
AgentCanon PR explicitly adds a reusable non-secret surface.

## Validation

After changing PR automation, Copilot, or GitHub workflow surfaces, run:

```bash
python3 tools/ci/check_github_workflows.py
```

Template or derived repositories that consume AgentCanon should then run:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
make agent-canon-ensure-latest
```
