---
applyTo: "**"
---
<!--
@dependency-start
responsibility Documents GitHub Copilot PR processing instructions for all repository paths.
upstream design ../../agents/workflows/github-copilot-workflow.md Copilot PR workflow and error triage
upstream design ../../documents/github-copilot-configuration.md Copilot configuration and PR-template routing
upstream implementation ../../tools/ci/checkout_agent_canon_submodule.sh private AgentCanon checkout diagnostics
downstream implementation ../../tools/ci/check_github_workflows.py enforces Copilot PR instruction availability
@dependency-end
-->

# GitHub Copilot PR Processing

Use this instruction file whenever you create, update, review, or respond to a
pull request.

## Required Triage

- Read `.github/copilot-instructions.md`, `AGENTS.md`, and
  `agents/workflows/github-copilot-workflow.md` before changing PR automation,
  workflow YAML, PR templates, or AgentCanon references.
- Read `documents/github-copilot-configuration.md` before changing Copilot
  settings, custom agents, MCP references, setup workflows, or PR-template
  routing.
- Use Plan mode before non-trivial PR automation, GitHub Actions, Copilot
  settings, PR-template, or AgentCanon sync changes. If the current Copilot
  surface lacks a Plan mode command, write the plan in the issue, PR body, or
  PR comment before editing.
- If a check fails with `AGENT_CANON_SUBMODULE_AUTH=missing` or a private
  `agent-canon.git` clone error, classify it as private submodule authentication,
  not as a code or test failure.
- Do not remove `vendor/agent-canon`, rewrite `.gitmodules`, make AgentCanon a
  copied snapshot, or switch to automatic `actions/checkout` submodules to hide
  a missing secret.
- If a workflow needs private AgentCanon, the expected remediation is a human
  repository or organization secret named `AGENT_CANON_REPO_TOKEN` with
  read-only Contents access to `iwashita-nozomu/agent-canon`,
  `AGENT_CANON_REPO_SSH_KEY` backed by a read-only deploy key, or a documented
  GitHub App token with equivalent read-only scope.
- If `AGENT_CANON_SUBMODULE_AUTH=token_persisted` or
  `AGENT_CANON_SUBMODULE_AUTH=ssh_persisted` appears before a later AgentCanon
  fetch fails with `could not read Username`, classify that as a helper
  persistence regression. Do not patch individual `make` commands to carry
  credentials by hand.
- Do not create, rotate, paste, or expose repository secrets from a PR branch.
  Leave the exact missing-secret evidence in the PR body instead.
- When an error is environment-only, keep the validation checklist item open and
  write the exact blocker. Do not mark the validation as completed.

## PR Evidence

- Fill the PR checklist with command names and key pass/fail lines.
- For AgentCanon-related PRs, include the AgentCanon GitHub SHA, template
  `vendor/agent-canon` pin SHA, and `git submodule status vendor/agent-canon`.
- For workflow changes, include `python3 tools/ci/check_github_workflows.py` and
  show whether the helper checkout path still reports actionable auth failures.
- If the run is from a fork or another context where secrets are unavailable,
  state that explicitly and ask for a trusted maintainer rerun after reviewing
  the workflow diff.

## Visible Copilot Output

Before marking a PR ready, merging, enabling auto-merge, closing, or asking a
human to take one of those actions, publish a PR-visible evidence block in a PR
comment, review body, or PR body update:

```text
COPILOT_PR_AUTHORITY=<inspect_and_prepare_only|ready_for_review_when_green|merge_when_green|github_copilot_merge_when_green>
COPILOT_PR_DECISION=<inspect_only|ready_for_review|merge|blocked|needs_human>
COPILOT_PR_CHECKS=<pass|fail|missing|not_run>
COPILOT_VISIBLE_EVIDENCE=<pr-comment|review|pr-body|check-run>:<url-or-id>
COPILOT_BLOCKER=<none|short blocker>
```

- `github_copilot_merge_when_green` authorizes only GitHub-hosted Copilot / PR
  automation to merge after required checks and reviews are green. It does not
  authorize local Codex to merge, dismiss reviews, bypass checks, or hide the
  decision in chat-only output.
- If the platform cannot write a visible comment, review, check run, or PR body
  update, set `COPILOT_PR_DECISION=blocked` and leave the PR unmerged.
- If required checks are absent, unavailable, or still running, set
  `COPILOT_PR_CHECKS=missing` or `not_run` and do not merge.
