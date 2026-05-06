---
applyTo: "**"
---
<!--
@dependency-start
responsibility Documents GitHub Copilot PR processing instructions for all repository paths.
upstream design ../../agents/workflows/github-copilot-workflow.md Copilot PR workflow and error triage
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
